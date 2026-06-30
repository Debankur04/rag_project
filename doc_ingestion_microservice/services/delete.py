from qdrant_client import models
from rag_project.doc_ingestion_microservice.config.db import qdrant
from rag_project.doc_ingestion_microservice.services.documents_chunks import get_chunks_for_document, delete_chunks_for_document
from rag_project.doc_ingestion_microservice.services.documents_table import mark_document_deleted
from rag_project.doc_ingestion_microservice.models.chunks import Chunk
from rag_project.doc_ingestion_microservice.models.documents import Document


def delete_document(
    db,
    tenant_id: str,
    doc_id: str,
):
    # Ensure doc_id is an integer for SQLAlchemy
    doc_id_int = int(doc_id)
    print(f"[*] Attempting to delete document {doc_id_int} for tenant {tenant_id}")

    vector_ids = get_chunks_for_document(db, doc_id_int)
    print(f"[*] Found {len(vector_ids)} chunks in Qdrant to delete")

    if vector_ids:
        qdrant.delete(
            collection_name=f"tenant_{tenant_id}",
            points_selector=models.PointIdsList(
                points=vector_ids
            )
        )
        print(f"[*] Deleted points from Qdrant collection tenant_{tenant_id}")


    num_chunks_deleted = delete_chunks_for_document(db, doc_id_int)
    print(f"[*] Deleted {num_chunks_deleted} chunk entries from SQL")

    mark_document_deleted(db, doc_id_int)
    print(f"[*] Document {doc_id_int} marked as deleted in SQL")





def delete_tenant(db, tenant_id: str):
    try:
        qdrant.delete_collection(f"tenant_{tenant_id}")
        print(f"[*] Deleted Qdrant collection tenant_{tenant_id}")
    except Exception as e:
        print(f"[!] Qdrant collection delete skipped: {e}")
    
    # Delete from SQL
    try:
        tenant_id_int = int(tenant_id)
        db.query(Chunk).filter(Chunk.tenant_id == tenant_id_int).delete()
        db.query(Document).filter(Document.tenant_id == tenant_id_int).delete()
        db.commit()
        print(f"[*] Deleted all SQL entries for tenant {tenant_id_int}")
    except Exception as e:
        db.rollback()
        print(f"[!] SQL cleanup for tenant {tenant_id} failed: {e}")
