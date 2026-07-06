from config.db_config import engine
from doc_ingestion.models.base import Base

def init_db():
    Base.metadata.create_all(bind=engine)