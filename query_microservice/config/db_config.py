from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from rag_project.query_microservice.config.settings import settings


user = quote_plus(settings.DB_USER)
password = quote_plus(settings.DB_PASSWORD)
host = settings.DB_HOST
port = settings.DB_PORT
db_name = settings.DB_NAME

db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"

engine = create_engine(
    db_url,
    connect_args={
        "sslmode": "verify-full",
        "sslrootcert": r"certs\prod-ca-2021.crt"
    },
    pool_pre_ping=True,
    pool_recycle=3600
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
