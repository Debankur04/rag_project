import datetime
import logging
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from rag_project.doc_ingestion.config.settings import settings

logger = logging.getLogger(__name__)

mongo_client = MongoClient(settings.MONGO_URI)
mongo_async_client = AsyncIOMotorClient(settings.MONGO_URI)

mongo_db = mongo_client[settings.MONGO_DB]
mongo_async_db = mongo_async_client[settings.MONGO_DB]


def log_ingestion_sync(
    ingestion_id: str,
    tenant_id: int,
    file_name: str,
    status: str,
    detail: str,
):
    record = {
        "ingestion_id": ingestion_id,
        "tenant_id": tenant_id,
        "file_name": file_name,
        "status": status,
        "detail": detail,
        "timestamp": datetime.datetime.utcnow(),
    }
    mongo_db.ingestion_logs.insert_one(record)
    logger.debug("Recorded ingestion log %s", ingestion_id)


async def log_ingestion_async(
    ingestion_id: str,
    tenant_id: int,
    file_name: str,
    status: str,
    detail: str,
):
    record = {
        "ingestion_id": ingestion_id,
        "tenant_id": tenant_id,
        "file_name": file_name,
        "status": status,
        "detail": detail,
        "timestamp": datetime.datetime.utcnow(),
    }
    await mongo_async_db.ingestion_logs.insert_one(record)
    logger.debug("Recorded async ingestion log %s", ingestion_id)
