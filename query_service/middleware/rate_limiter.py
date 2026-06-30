import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi import HTTPException
from rag_project.query_service.services.redis_client import get_redis
from rag_project.query_service.config.settings import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path != "/query" or request.method != "POST":
            return await call_next(request)

        redis = get_redis()
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_ip}"

        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)

        if current > settings.RATE_LIMIT_REQUESTS:
            logger.warning("Rate limit exceeded for %s", client_ip)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({settings.RATE_LIMIT_REQUESTS} requests per {settings.RATE_LIMIT_WINDOW_SECONDS} seconds)",
            )

        return await call_next(request)
