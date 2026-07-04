import os
from pathlib import Path
from uuid import uuid4

import cv2
import pytesseract
from pdf2image import convert_from_path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from qdrant_client.models import Distance, VectorParams
from qdrant_client import models

# from supabase_operations import db_operations
from rag_project.doc_ingestion.services.documents_table import compute_file_hash, get_existing_document, create_document, mark_document_ingested, mark_document_failed, mark_document_processing
from rag_project.doc_ingestion.services.documents_chunks import bulk_insert_chunks, delete_chunks_for_document
from rag_project.config.db import qdrant
from rag_project.doc_ingestion.services.pubsub import pubsub
from rag_project.config.settings import settings

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
embeddings = None


def _get_embeddings():
    global embeddings
    if embeddings is None:
        embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)
    return embeddings




def ocr_image(pdf_path: str) -> str:
    try:
        pages = convert_from_path(pdf_path)
        
        ocr_text = ""
        prefix = str(uuid4())[:8]
        for i, page in enumerate(pages):
            image_path = f"temp_page_{prefix}_{i}.png"
            page.save(image_path, "PNG")

            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]

            page_text = pytesseract.image_to_string(gray)
            ocr_text += f"\n\n--- Page {i+1} ---\n{page_text}"
            
            if os.path.exists(image_path):
                os.remove(image_path)

        return ocr_text
    except Exception as e:
        print(f"❌ Error during OCR processing: {e}")
        return ""


def read_pdf_with_fallback(file_path: str):
    loader = PyPDFLoader(file_path)
    pages = loader.load()

    if pages and any(p.page_content.strip() for p in pages):
        return pages

    text = ocr_image(file_path)
    if not text.strip():
        return []

    return [Document(page_content=text, metadata={"source": file_path})]



def _ensure_collection(tenant_id: str):
    collection_name = f"tenant_{tenant_id}"
    try:
        if qdrant.collection_exists(collection_name=collection_name):
            return
            
        dim = len(_get_embeddings().embed_query("dimension_probe"))
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=dim,
                distance=Distance.COSINE
            )
        )
        print(f"[*] Created new Qdrant collection: {collection_name}")
    except Exception as e:
        print(f"⚠️ Could not verify/create collection {collection_name}: {e}")





def ingest_pdf(
    db,
    tenant_id: str,
    file_path: str,
    url: str
):
    file_path = Path(file_path)
    file_name = file_path.name

    
    content_hash = compute_file_hash(file_path)

    existing = get_existing_document(
        db=db,
        tenant_id=tenant_id,
        content_hash=content_hash
    )

    if existing:
        print("ℹ️ Document already ingested. Skipping.")
        return

    document_id, _, _ = create_document(
        db=db,
        tenant_id=tenant_id,
        file_name=file_name,
        file_path=file_path,
        file_url=url
    )
    mark_document_processing(db, document_id)

    _ensure_collection(tenant_id)

    inserted_vector_ids = []

    try:

        pages = read_pdf_with_fallback(str(file_path))
        if not pages:
            raise RuntimeError("No readable content found in PDF")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )
        chunks = splitter.split_documents(pages)

        points = []
        chunk_data_list = []
        for idx, chunk in enumerate(chunks):
            vector_id = str(uuid4())
            vector = _get_embeddings().embed_query(chunk.page_content)

            points.append(models.PointStruct(
                id=vector_id,
                vector=vector,
                payload={
                    "document_id": document_id,
                    "source": file_name,
                    "chunk_index": idx,
                    "text": chunk.page_content
                }
            ))

            inserted_vector_ids.append(vector_id)

            chunk_data_list.append({
                "document_id": document_id,
                "tenant_id": tenant_id,
                "vector_id": vector_id,
                "chunk_index": idx
            })

        if not points:
            raise RuntimeError("No text chunks could be extracted from the document.")

        # Batch insert to SQL (No commit yet)
        bulk_insert_chunks(db, chunk_data_list)

        pubsub.publish(settings.DOC_STATUS_TOPIC, {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "file_name": file_name,
            "status": "processing",
            "stage": "chunk_created",
            "chunk_count": len(points),
        })

        # Batch upsert to Qdrant
        qdrant.upsert(
            collection_name=f"tenant_{tenant_id}",
            points=points
        )

        # Atomic commit: Chunks + Status Update
        mark_document_ingested(db, document_id)
        print(f"✅ Ingested '{file_name}' successfully.")

    except Exception as e:
        print(f"❌ Ingestion failed: {e}")
        db.rollback()  # Rollback any uncommitted SQL chunks

        if inserted_vector_ids:
            try:
                qdrant.delete(
                    collection_name=f"tenant_{tenant_id}",
                    points_selector=models.PointIdsList(
                        points=inserted_vector_ids
                    )
                )
            except Exception as q_e:
                print(f"⚠️ Failed to rollback Qdrant vectors: {q_e}")

        # Mark document as failed (commits the failed status)
        mark_document_failed(db, document_id)
