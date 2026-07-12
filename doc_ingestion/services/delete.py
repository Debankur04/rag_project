from config.db import qdrant, supabase
from doc_ingestion.services.documents_chunks import (
    delete_chunks_for_document,
    get_chunks_for_document,
)
from doc_ingestion.services.documents_table import mark_document_deleted


DOC_TABLE = "docs"
CHUNK_TABLE = "chunks"


def _document_belongs_to_user(doc_id: int, user_id: int) -> bool:
    response = (
        supabase.table(DOC_TABLE)
        .select("id")
        .eq("id", doc_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def delete_document(user_id: int, doc_id: str):
    doc_id_int = int(doc_id)
    if not _document_belongs_to_user(doc_id_int, user_id):
        raise ValueError("Document not found for current user")

    vector_ids = get_chunks_for_document(doc_id_int)
    if vector_ids:
        from qdrant_client import models

        qdrant.delete(
            collection_name=f"user_{user_id}",
            points_selector=models.PointIdsList(points=vector_ids),
        )

    deleted_chunks = delete_chunks_for_document(doc_id_int)
    mark_document_deleted(doc_id_int)

    return {
        "document_id": doc_id_int,
        "deleted_chunks": deleted_chunks,
        "deleted_vectors": len(vector_ids),
    }


def delete_user_documents(user_id: int):
    try:
        qdrant.delete_collection(f"user_{user_id}")
    except Exception:
        pass

    docs = (
        supabase.table(DOC_TABLE)
        .select("id")
        .eq("user_id", user_id)
        .execute()
    )
    doc_ids = [row["id"] for row in docs.data or []]
    for doc_id in doc_ids:
        supabase.table(CHUNK_TABLE).delete().eq("document_id", doc_id).execute()

    supabase.table(DOC_TABLE).delete().eq("user_id", user_id).execute()
    return {"user_id": user_id, "deleted_documents": len(doc_ids)}
