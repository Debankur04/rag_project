from typing import Any

from auth.services.auth import refresh_access_token


def refresh_token(refresh_token_value: str) -> dict[str, Any]:
    return refresh_access_token(refresh_token=refresh_token_value)
