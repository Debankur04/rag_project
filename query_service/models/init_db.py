from rag_project.query_service.config.db_config import engine
from rag_project.query_service.models.base import Base

# import ALL models so metadata registers them
from rag_project.query_service.models.intent import Intent


def init_db():
    Base.metadata.create_all(bind=engine)