# Modify the ingestion pipeline so that every uploaded chunk is automatically indexed into a local Elasticsearch instance (running via Docker Compose) using tenant and document metadata, while keeping PostgreSQL as the metadata store and Qdrant as the dense vector store for Hybrid RAG.

import os
from pathlib import Path
from uuid import uuid4

from config.db import qdrant
from doc_ingestion.services.documents_chunks import bulk_insert_chunks
from doc_ingestion.services.documents_table import (
    compute_file_hash,
    create_document,
    get_existing_document,
    mark_document_failed,
    mark_document_ingested,
    mark_document_processing,
)
from query.rag.bm25 import bulk_index_chunks, delete_document_chunks


CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
embeddings = None


def _get_embeddings():
    global embeddings
    if embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL_NAME)
    return embeddings


def ocr_image(pdf_path: str) -> str:
    import cv2
    import pytesseract
    from pdf2image import convert_from_path

    try:
        pages = convert_from_path(pdf_path)
        ocr_text = ""
        prefix = str(uuid4())[:8]

        for index, page in enumerate(pages):
            image_path = f"temp_page_{prefix}_{index}.png"
            page.save(image_path, "PNG")

            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
            ocr_text += f"\n\n--- Page {index + 1} ---\n{pytesseract.image_to_string(gray)}"

            if os.path.exists(image_path):
                os.remove(image_path)

        return ocr_text
    except Exception as exc:
        print(f"Error during OCR processing: {exc}")
        return ""


def read_pdf_with_fallback(file_path: str):
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_core.documents import Document

    loader = PyPDFLoader(file_path)
    pages = loader.load()

    if pages and any(page.page_content.strip() for page in pages):
        return pages

    text = ocr_image(file_path)
    if not text.strip():
        return []

    return [Document(page_content=text, metadata={"source": file_path})]


def _ensure_collection(user_id: int):
    from qdrant_client.models import Distance, VectorParams

    collection_name = f"user_{user_id}"
    if qdrant.collection_exists(collection_name=collection_name):
        return

    dim = len(_get_embeddings().embed_query("dimension_probe"))
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )


def ingest_pdf(user_id: int, file_path: str, source: str | None = None):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from qdrant_client import models

    file_path_obj = Path(file_path)
    file_name = source or file_path_obj.name
    content_hash = compute_file_hash(file_path_obj)

    existing = get_existing_document(
        user_id=user_id,
        content_hash=content_hash,
    )
    if existing:
        return {
            "id": existing.id,
            "user_id": existing.user_id,
            "file_name": existing.filename,
            "status": existing.status,
            "duplicate": True,
        }

    document_id, _, _ = create_document(
        user_id=user_id,
        file_name=file_name,
        file_path=file_path_obj,
        file_url=file_name,
    )
    mark_document_processing(document_id)

    inserted_vector_ids = []

    try:
        _ensure_collection(user_id)

        pages = read_pdf_with_fallback(str(file_path_obj))
        if not pages:
            raise RuntimeError("No readable content found in PDF")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        chunks = splitter.split_documents(pages)

        points = []
        chunk_data_list = []
        sparse_chunks = []
        for index, chunk in enumerate(chunks):
            vector_id = str(uuid4())
            vector = _get_embeddings().embed_query(chunk.page_content)

            points.append(
                models.PointStruct(
                    id=vector_id,
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "source": file_name,
                        "chunk_index": index,
                        "text": chunk.page_content,
                        "user_id": user_id,
                    },
                )
            )
            inserted_vector_ids.append(vector_id)
            chunk_data_list.append(
                {
                    "document_id": document_id,
                    "vector_id": vector_id,
                    "chunk_index": index,
                    "content": chunk.page_content,
                }
            )
            sparse_chunks.append(
                {
                    "user_id": user_id,
                    "document_id": document_id,
                    "vector_id": vector_id,
                    "chunk_index": index,
                    "source": file_name,
                    "text": chunk.page_content,
                }
            )

        if not points:
            raise RuntimeError("No text chunks could be extracted from the document")

        bulk_insert_chunks(chunk_data_list)
        bulk_index_chunks(sparse_chunks)
        print("chunks inserted")
        qdrant.upsert(collection_name=f"user_{user_id}", points=points)
        mark_document_ingested(document_id)

        return {
            "id": document_id,
            "user_id": user_id,
            "file_name": file_name,
            "status": "ingested",
            "chunk_count": len(points),
            "duplicate": False,
        }

    except Exception:
        if inserted_vector_ids:
            try:
                qdrant.delete(
                    collection_name=f"user_{user_id}",
                    points_selector=models.PointIdsList(points=inserted_vector_ids),
                )
            except Exception as rollback_error:
                print(f"Failed to roll back Qdrant vectors: {rollback_error}")
        delete_document_chunks(user_id=user_id, document_id=document_id)

        mark_document_failed(document_id)
        raise
