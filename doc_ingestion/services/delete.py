from qdrant_client import models

from config.db import qdrant, supabase
from doc_ingestion.services.documents_chunks import (
    delete_chunks_for_document,
    get_chunks_for_document,
)
from doc_ingestion.services.documents_table import mark_document_deleted


def delete_document(tenant_id: str, doc_id: str):
    doc_id_int = int(doc_id)
    vector_ids = get_chunks_for_document(doc_id_int)

    if vector_ids:
        qdrant.delete(
            collection_name=f"tenant_{tenant_id}",
            points_selector=models.PointIdsList(points=vector_ids),
        )

    deleted_chunks = delete_chunks_for_document(doc_id_int)
    mark_document_deleted(doc_id_int)

    return {
        "document_id": doc_id_int,
        "deleted_chunks": deleted_chunks,
        "deleted_vectors": len(vector_ids),
    }


def delete_tenant(tenant_id: str):
    tenant_id_int = int(tenant_id)

    try:
        qdrant.delete_collection(f"tenant_{tenant_id}")
    except Exception:
        pass

    supabase.table("chunks").delete().eq("tenant_id", tenant_id_int).execute()
    supabase.table("doc").delete().eq("tenant_id", tenant_id_int).execute()

    return {"tenant_id": tenant_id_int, "status": "deleted"}
