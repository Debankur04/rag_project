from sqlalchemy import Column, String, Integer, TIMESTAMP, BigInteger,ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from rag_project.doc_ingestion_microservice.models.base import Base
import uuid

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    document_id = Column(BigInteger, ForeignKey("doc.id"))
    tenant_id = Column(BigInteger)
    vector_id = Column(String)
    chunk_index = Column(Integer)
    created_at = Column(TIMESTAMP)