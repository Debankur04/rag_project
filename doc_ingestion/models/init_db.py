from rag_project.doc_ingestion.config.db_config import engine
from rag_project.doc_ingestion.models.base import Base

# import ALL models so metadata registers them
from rag_project.doc_ingestion.models.documents import Document
from rag_project.doc_ingestion.models.chunks import Chunk

def init_db():
    Base.metadata.create_all(bind=engine)