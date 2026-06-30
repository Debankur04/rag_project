from sqlalchemy import Column, String, TIMESTAMP, BigInteger
from rag_project.doc_ingestion.models.base import Base


class Document(Base):
    __tablename__ = "doc"

    id = Column(BigInteger, primary_key=True, index=True)
    tenant_id = Column(BigInteger, index=True)

    filename = Column(String)        # ✅ matches DB
    url = Column(String)             # ✅ matches DB

    content_hash = Column(String, index=True)
    status = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)