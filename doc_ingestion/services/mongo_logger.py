import datetime
import logging

from config.db import supabase


logger = logging.getLogger(__name__)
INGESTION_LOG_TABLE = "ingestion_logs"


def _record(
    ingestion_id: str,
    tenant_id: int,
    file_name: str,
    status: str,
    detail: str,
):
    return {
        "ingestion_id": ingestion_id,
        "tenant_id": tenant_id,
        "file_name": file_name,
        "status": status,
        "detail": detail,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


def log_ingestion_sync(
    ingestion_id: str,
    tenant_id: int,
    file_name: str,
    status: str,
    detail: str,
):
    payload = _record(ingestion_id, tenant_id, file_name, status, detail)
    supabase.table(INGESTION_LOG_TABLE).insert(payload).execute()
    logger.debug("Ingestion log inserted for %s", ingestion_id)


async def log_ingestion_async(
    ingestion_id: str,
    tenant_id: int,
    file_name: str,
    status: str,
    detail: str,
):
    payload = _record(ingestion_id, tenant_id, file_name, status, detail)
    supabase.table(INGESTION_LOG_TABLE).insert(payload).execute()
    logger.debug("Ingestion log inserted for %s", ingestion_id)
