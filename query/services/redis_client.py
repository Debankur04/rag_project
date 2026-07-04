from redis.asyncio import Redis
from rag_project.config.settings import settings

redis_client: Redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_redis() -> Redis:
    return redis_client
