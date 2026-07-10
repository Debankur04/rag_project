import datetime
import logging
from typing import Optional

from config.db import supabase


logger = logging.getLogger(__name__)
QUERY_LOG_TABLE = "query_logs"


def _payload(
    query_id: str,
    query_text: str,
    response: dict,
    intent: Optional[str],
    status: str,
):
    return {
        "query_id": query_id,
        "query_text": query_text,
        "response": response,
        "intent": intent or "unknown",
        "status": status,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


async def log_query_async(
    query_id: str,
    query_text: str,
    response: dict,
    intent: Optional[str],
    status: str,
):
    payload = _payload(query_id, query_text, response, intent, status)
    supabase.table(QUERY_LOG_TABLE).insert(payload).execute()
    logger.debug("Query log inserted for %s", query_id)


def log_query_sync(
    query_id: str,
    query_text: str,
    response: dict,
    intent: Optional[str],
    status: str,
):
    payload = _payload(query_id, query_text, response, intent, status)
    supabase.table(QUERY_LOG_TABLE).insert(payload).execute()
    logger.debug("Query log inserted for %s", query_id)
