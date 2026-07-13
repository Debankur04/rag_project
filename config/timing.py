import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from config.settings import settings


def timing_enabled() -> bool:
    return settings.TIMING_ENABLED


def _format_extra(extra: dict[str, Any] | None) -> str:
    if not extra:
        return ""
    parts = []
    for key, value in extra.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return " " + " ".join(parts) if parts else ""


def print_timing(
    stage: str,
    elapsed_ms: float,
    request_id: str | None = None,
    **extra: Any,
) -> None:
    if not timing_enabled():
        return

    request_part = f" request={request_id}" if request_id else ""
    print(
        f"[timing]{request_part} stage={stage} elapsed_ms={elapsed_ms:.2f}"
        f"{_format_extra(extra)}",
        flush=True,
    )


@contextmanager
def timed_stage(stage: str, request_id: str | None = None, **extra: Any):
    if not timing_enabled():
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print_timing(stage, elapsed_ms, request_id=request_id, **extra)


@asynccontextmanager
async def async_timed_stage(stage: str, request_id: str | None = None, **extra: Any):
    if not timing_enabled():
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print_timing(stage, elapsed_ms, request_id=request_id, **extra)
