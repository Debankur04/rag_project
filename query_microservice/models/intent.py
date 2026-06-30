from sqlalchemy import Column, String
from rag_project.query_microservice.models.base import Base
import uuid
from sqlalchemy.dialects.postgresql import UUID

class Intent(Base):
    __tablename__ = "intent"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query = Column(String)
    intent = Column(String)