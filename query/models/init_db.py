from config.db_config import engine
from query.models.base import Base

# import ALL models so metadata registers them
from query.models.intent import Intent


def init_db():
    Base.metadata.create_all(bind=engine)