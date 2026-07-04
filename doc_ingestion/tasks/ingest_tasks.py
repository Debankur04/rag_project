
import uuid
import tempfile
from pathlib import Path
from celery.utils.log import get_task_logger
import httpx
from rag_project.doc_ingestion.services.pubsub import pubsub
from rag_project.doc_ingestion.services.mongo_logger import log_ingestion_sync
from rag_project.doc_ingestion.services.add_pdf import ingest_pdf
from rag_project.config.db_config import SessionLocal
from rag_project.config.settings import settings
from .celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 5},
)
def ingest_document(self, tenant_id: int, file_name: str, supabase_url: str, ingestion_id: str):
    logger.info("Starting ingestion task %s for tenant %s", ingestion_id, tenant_id)
    status_payload = {
        "ingestion_id": ingestion_id,
        "tenant_id": tenant_id,
        "file_name": file_name,
        "status": "processing",
    }
    pubsub.publish(settings.DOC_STATUS_TOPIC, status_payload)

    temp_dir = Path(tempfile.gettempdir()) / "doc_ingestion"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid.uuid4()}_{file_name}"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(supabase_url)
            response.raise_for_status()
            temp_path.write_bytes(response.content)

        with SessionLocal() as db:
            ingest_pdf(db=db, tenant_id=str(tenant_id), file_path=str(temp_path), url=supabase_url)

        pubsub.publish(settings.DOC_STATUS_TOPIC, {
            "ingestion_id": ingestion_id,
            "tenant_id": tenant_id,
            "file_name": file_name,
            "status": "success",
        })

        log_ingestion_sync(
            ingestion_id=ingestion_id,
            tenant_id=tenant_id,
            file_name=file_name,
            status="success",
            detail="Document successfully ingested",
        )

        return {"status": "success", "ingestion_id": ingestion_id}

    except Exception as exc:
        logger.exception("Document ingestion failed %s", ingestion_id)
        pubsub.publish(settings.DOC_STATUS_TOPIC, {
            "ingestion_id": ingestion_id,
            "tenant_id": tenant_id,
            "file_name": file_name,
            "status": "failed",
            "error": str(exc),
        })

        log_ingestion_sync(
            ingestion_id=ingestion_id,
            tenant_id=tenant_id,
            file_name=file_name,
            status="failed",
            detail=str(exc),
        )

        raise self.retry(exc=exc)
