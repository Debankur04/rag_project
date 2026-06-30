import json
import logging
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from rag_project.doc_ingestion_microservice.services.add_pdf import ingest_pdf
from rag_project.doc_ingestion_microservice.services.mongo_logger import log_ingestion_sync
from rag_project.doc_ingestion_microservice.services.pubsub import pubsub
from rag_project.doc_ingestion_microservice.config.db_config import SessionLocal
from rag_project.doc_ingestion_microservice.config.settings import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def publish_status(payload: dict) -> None:
    pubsub.publish(settings.DOC_STATUS_TOPIC, payload)


def _download_to_temp(file_name: str, supabase_url: str) -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "doc_ingestion"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid4()}_{file_name}"

    with httpx.Client(timeout=60.0) as client:
        response = client.get(supabase_url)
        response.raise_for_status()
        temp_path.write_bytes(response.content)

    return temp_path


def handle_ingestion_request(message) -> None:
    try:
        raw_data = message.data
        if isinstance(raw_data, bytes):
            payload = json.loads(raw_data.decode("utf-8"))
        else:
            payload = json.loads(raw_data)
    except Exception as exc:
        logger.exception("Failed to parse ingestion request payload: %s", exc)
        return

    ingestion_id = payload.get("ingestion_id") or str(uuid4())
    tenant_id = payload.get("tenant_id")
    file_name = payload.get("file_name")
    supabase_url = payload.get("supabase_url")

    if not tenant_id or not file_name or not supabase_url:
        logger.error("Invalid ingestion request payload: %s", payload)
        return

    logger.info("Received ingestion request %s for tenant %s file %s", ingestion_id, tenant_id, file_name)
    publish_status({
        "ingestion_id": ingestion_id,
        "tenant_id": tenant_id,
        "file_name": file_name,
        "status": "received",
    })

    temp_path = None
    try:
        temp_path = _download_to_temp(file_name, supabase_url)
        with SessionLocal() as db:
            ingest_pdf(db=db, tenant_id=str(tenant_id), file_path=str(temp_path), url=supabase_url)

        publish_status({
            "ingestion_id": ingestion_id,
            "tenant_id": tenant_id,
            "file_name": file_name,
            "status": "complete",
        })

        log_ingestion_sync(
            ingestion_id=ingestion_id,
            tenant_id=tenant_id,
            file_name=file_name,
            status="complete",
            detail="Document ingestion completed successfully.",
        )

    except Exception as exc:
        logger.exception("Ingestion failed for %s", ingestion_id)
        publish_status({
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

    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                logger.warning("Unable to delete temporary file %s", temp_path)

    try:
        if hasattr(message, "ack"):
            message.ack()
    except Exception:
        logger.debug("Message ack failed or is not available.")


def start_worker() -> None:
    topic = settings.DOC_INGESTION_REQUEST_TOPIC
    logger.info("Starting ingestion worker, subscribing to '%s'", topic)
    pubsub.subscribe(topic, handle_ingestion_request)
    logger.info("Worker is now listening for ingestion requests.")

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Ingestion worker shutdown requested.")


if __name__ == "__main__":
    start_worker()
