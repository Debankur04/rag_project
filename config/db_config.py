from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import settings


def _database_url() -> str:
    user = quote_plus(settings.DB_USER)
    password = quote_plus(settings.DB_PASSWORD)
    return (
        f"postgresql+psycopg2://{user}:{password}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


connect_args = {"sslmode": settings.DB_SSLMODE}
if settings.DB_SSLROOTCERT:
    connect_args["sslrootcert"] = settings.DB_SSLROOTCERT

engine = create_engine(
    _database_url(),
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
