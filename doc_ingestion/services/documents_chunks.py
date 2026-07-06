from config.db import qdrant
from datetime import datetime

from doc_ingestion.models.chunks import Chunk
from doc_ingestion.models.documents import Document
from datetime import datetime

def bulk_insert_chunks(db, chunk_data_list):
    chunks = [
        Chunk(
            document_id=data["document_id"],
            tenant_id=data["tenant_id"],
            vector_id=data["vector_id"],
            chunk_index=data["chunk_index"],
            created_at=datetime.utcnow()
        )
        for data in chunk_data_list
    ]
    db.add_all(chunks)
    # No db.commit() here! We let the caller handle the transaction
    return chunks


def get_chunks_for_document(db, document_id):
    chunks = (
        db.query(Chunk.vector_id)
        .filter(Chunk.document_id == document_id)
        .all()
    )

    # match old Supabase output style (list of vector_ids)
    return [c[0] for c in chunks]



def delete_chunks_for_document(db, document_id):
    deleted = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .delete()
    )

    db.commit()
    return deleted



def list_documents_for_tenant(db, tenant_id):
    docs = (
        db.query(
            Document.id,
            Document.source_name,
            Document.status,
            Document.created_at
        )
        .filter(
            Document.tenant_id == tenant_id,
            Document.status != "deleted"
        )
        .all()
    )

    # convert to dict (like Supabase response)
    return [
        {
            "id": d.id,
            "source_name": d.source_name,
            "status": d.status,
            "created_at": d.created_at
        }
        for d in docs
    ]
