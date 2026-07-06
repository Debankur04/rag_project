import asyncio
import logging
from datetime import datetime
from celery.utils.log import get_task_logger
from query.services.celery_app import celery_app
from query.services.cache import query_cache
from query.services.mongo_logger import log_query_sync
from query.services.query import run_query
from query.services.prompt import prompt_builder

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 5},
)
def process_query_task(self, query_id: str, tenant_id: int, query_text: str):
    logger.info("Starting query worker for %s", query_id)

    try:
        prompt = prompt_builder(query=query_text)
        result = asyncio.run(run_query(
            tenant_id=str(tenant_id),
            user_query=query_text,
            prompt=prompt,
            db=None,
        ))

        response_payload = {
            "answer": result["answer"],
            "token_usage": result["token_usage"],
        }

        asyncio.run(query_cache.set(query_text, response_payload))

        log_query_sync(
            query_id=query_id,
            query_text=query_text,
            response=response_payload,
            intent=None,
            status="success",
        )

        return response_payload

    except Exception as exc:
        logger.exception("Query worker failed for %s", query_id)

        log_query_sync(
            query_id=query_id,
            query_text=query_text,
            response={"error": str(exc)},
            intent=None,
            status="failed",
        )

        raise self.retry(exc=exc)
