from collections.abc import Callable
from functools import cached_property
from typing import Any

from config.settings import settings


class LazyClient:
    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory

    @cached_property
    def _client(self):
        return self._factory()

    def __getattr__(self, name: str):
        return getattr(self._client, name)


def _create_supabase_client():
    from supabase import create_client

    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL must be set")
    return create_client(settings.SUPABASE_URL, settings.FINAL_SUPABASE_KEY)


def _create_supabase_auth_client():
    from supabase import create_client

    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL must be set")
    if not settings.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY must be set")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def _create_qdrant_client():
    from qdrant_client import QdrantClient

    if not settings.QDRANT_URL:
        raise RuntimeError("QDRANT_URL must be set")
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


supabase = LazyClient(_create_supabase_client)
supabase_auth = LazyClient(_create_supabase_auth_client)
qdrant = LazyClient(_create_qdrant_client)
