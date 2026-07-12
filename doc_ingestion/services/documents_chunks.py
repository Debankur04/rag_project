from datetime import datetime

from config.db import supabase


CHUNK_TABLE = "chunks"
DOC_TABLE = "docs"


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def bulk_insert_chunks(chunk_data_list):
    if not chunk_data_list:
        return []

    rows = [
        {
            "document_id": data["document_id"],
            "vector_id": data["vector_id"],
            "chunk_index": data["chunk_index"],
            "content": data["content"],
            "created_at": _utc_now(),
        }
        for data in chunk_data_list
    ]
    response = supabase.table(CHUNK_TABLE).insert(rows).execute()
    return response.data or []


def get_chunks_for_document(document_id):
    response = (
        supabase.table(CHUNK_TABLE)
        .select("vector_id")
        .eq("document_id", int(document_id))
        .execute()
    )
    return [row["vector_id"] for row in response.data or [] if row.get("vector_id")]


def delete_chunks_for_document(document_id):
    existing = get_chunks_for_document(document_id)
    supabase.table(CHUNK_TABLE).delete().eq("document_id", int(document_id)).execute()
    return len(existing)


def list_documents_for_user(user_id):
    response = (
        supabase.table(DOC_TABLE)
        .select("id,filename,status,created_at")
        .eq("user_id", int(user_id))
        .neq("status", "deleted")
        .execute()
    )
    return [
        {
            "id": row["id"],
            "source_name": row.get("filename"),
            "status": row.get("status"),
            "created_at": row.get("created_at"),
        }
        for row in response.data or []
    ]
