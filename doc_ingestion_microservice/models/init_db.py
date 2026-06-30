from rag_project.doc_ingestion_microservice.config.db_config import engine
from rag_project.doc_ingestion_microservice.models.base import Base

# import ALL models so metadata registers them
from rag_project.doc_ingestion_microservice.models.documents import Document
from rag_project.doc_ingestion_microservice.models.chunks import Chunk

def init_db():
    Base.metadata.create_all(bind=engine)