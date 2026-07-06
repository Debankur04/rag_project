from typing import Any

from auth.services.auth import login_user


def signin(email: str, password: str) -> dict[str, Any]:
    return login_user(email=email, password=password)
