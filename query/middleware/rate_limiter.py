import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from query.services.redis_client import get_redis
from config.settings import settings

logger = logging.getLogger(__name__)

SKIP_PATHS = {
    "/docs",
    "/docs/",
    "/redoc",
    "/redoc/",
    "/openapi.json",
    "/docs/oauth2-redirect",
    "/favicon.ico",
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in SKIP_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_ip}:{request.method}:{request.url.path}"

        try:
            redis = get_redis()
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)
        except Exception as exc:
            logger.warning("Rate limiter skipped because Redis is unavailable: %s", exc)
            return await call_next(request)

        if current > settings.RATE_LIMIT_REQUESTS:
            logger.warning("Rate limit exceeded for %s on %s", client_ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded ({settings.RATE_LIMIT_REQUESTS} requests "
                        f"per {settings.RATE_LIMIT_WINDOW_SECONDS} seconds)"
                    )
                },
            )

        return await call_next(request)
