from celery import Celery
from rag_project.doc_ingestion.config.settings import settings

celery_app = Celery(
    "doc_ingestion_microservice",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_publish_retry=True,
    worker_max_tasks_per_child=100,
)
