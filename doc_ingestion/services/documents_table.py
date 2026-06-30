from rag_project.doc_ingestion.models.documents import Document
from datetime import datetime
import hashlib
from pathlib import Path
from sqlalchemy.orm import Session
from rag_project.doc_ingestion.models.chunks import Chunk


def compute_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_existing_document(db: Session, tenant_id: int, content_hash: str):
    # Find ingested documents with the same hash
    docs = (
        db.query(Document)
        .filter(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash,
            Document.status == "ingested"
        )
        .all()
    )

    # Validate that the document ACTUALLY has chunks
    for doc in docs:
        chunk_count = db.query(Chunk).filter(Chunk.document_id == doc.id).count()
        if chunk_count > 0:
            return doc
        else:
            # Document is marked ingested but has no chunks - fix its state
            doc.status = "failed"
            db.commit()

    return None


def create_document(
    db: Session,
    tenant_id: int,
    file_name: str,
    file_path: Path,
    file_url: str   # ✅ added
):
    content_hash = compute_file_hash(file_path)

    # 🔥 prevent duplicate ingestion
    existing = get_existing_document(db, tenant_id, content_hash)
    if existing:
        return existing.id, content_hash, existing

    try:
        doc = Document(
            tenant_id=tenant_id,
            filename=file_name,        # ✅ fixed
            url=file_url,              # ✅ added
            content_hash=content_hash,
            status="pending",
            created_at=datetime.utcnow()
        )

        db.add(doc)
        db.commit()
        db.refresh(doc)

        return doc.id, content_hash, doc

    except Exception as e:
        db.rollback()
        raise e


def mark_document_processing(db: Session, document_id: int):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        doc.status = "processing"
        doc.updated_at = datetime.utcnow()
        db.commit()
    return doc

def mark_document_ingested(db: Session, document_id: int):
    doc = db.query(Document).filter(Document.id == document_id).first()

    if doc:
        doc.status = "ingested"
        doc.updated_at=datetime.utcnow()
        db.commit()

    return doc


def mark_document_failed(db: Session, document_id: int):
    doc = db.query(Document).filter(Document.id == document_id).first()

    if doc:
        doc.status = "failed"
        doc.updated_at=datetime.utcnow()
        db.commit()

    return doc


def mark_document_deleted(db: Session, document_id: int):
    doc = db.query(Document).filter(Document.id == document_id).first()

    if doc:
        doc.status = "deleted"
        doc.updated_at=datetime.utcnow()
        db.commit()

    return doc