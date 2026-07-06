from typing import Any

from auth.services.auth import register_user


def signup(email: str, password: str) -> dict[str, Any]:
    return register_user(email=email, password=password)
