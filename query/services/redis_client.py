from config.settings import settings

redis_client = None


def get_redis():
    global redis_client
    if redis_client is None:
        from redis.asyncio import Redis

        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_client
