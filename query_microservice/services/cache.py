import hashlib
import json
from typing import Any, Optional

from rag_project.query_microservice.config.settings import settings
from rag_project.query_microservice.services.redis_client import get_redis


class QueryCache:
    def __init__(self):
        self.redis = get_redis()
        self.ttl = settings.CACHE_TTL_SECONDS

    @staticmethod
    def _build_key(query_text: str) -> str:
        fingerprint = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
        return f"query_cache:{fingerprint}"

    async def get(self, query_text: str) -> Optional[dict]:
        key = self._build_key(query_text)
        cached = await self.redis.get(key)
        if not cached:
            return None
        try:
            return json.loads(cached)
        except Exception:
            return None

    async def set(self, query_text: str, value: Any) -> None:
        key = self._build_key(query_text)
        payload = json.dumps(value)
        await self.redis.set(key, payload, ex=self.ttl)


query_cache = QueryCache()
