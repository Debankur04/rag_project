import datetime
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from rag_project.query_microservice.config.settings import settings

logger = logging.getLogger(__name__)

mongo_client = MongoClient(settings.MONGO_URI)
mongo_async_client = AsyncIOMotorClient(settings.MONGO_URI)

mongo_db = mongo_client[settings.MONGO_DB]
mongo_async_db = mongo_async_client[settings.MONGO_DB]


async def log_query_async(
    query_id: str,
    query_text: str,
    response: dict,
    intent: Optional[str],
    status: str,
):
    payload = {
        "query_id": query_id,
        "query_text": query_text,
        "response": response,
        "intent": intent or "unknown",
        "status": status,
        "timestamp": datetime.datetime.utcnow(),
    }
    await mongo_async_db.query_logs.insert_one(payload)
    logger.debug("Async query log inserted for %s", query_id)


def log_query_sync(
    query_id: str,
    query_text: str,
    response: dict,
    intent: Optional[str],
    status: str,
):
    payload = {
        "query_id": query_id,
        "query_text": query_text,
        "response": response,
        "intent": intent or "unknown",
        "status": status,
        "timestamp": datetime.datetime.utcnow(),
    }
    mongo_db.query_logs.insert_one(payload)
    logger.debug("Sync query log inserted for %s", query_id)
