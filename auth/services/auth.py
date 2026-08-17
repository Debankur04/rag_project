from typing import Any

from fastapi import HTTPException, Request, status

from config.db import supabase_auth


def _auth_error(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _read_field(value: Any, field: str) -> Any:
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def _safe_user(user: Any) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": _read_field(user, "id"),
        "email": _read_field(user, "email"),
        "created_at": _read_field(user, "created_at"),
    }


def _app_user_from_auth_user(auth_user: dict[str, Any]) -> dict[str, Any]:
    auth_user_id = auth_user.get("id")
    if not auth_user_id:
        raise RuntimeError("Supabase Auth user does not contain an id")

    return {
        "id": str(auth_user_id),
        "email": auth_user.get("email"),
    }


def _session_payload(response: Any) -> dict[str, Any]:
    session = _read_field(response, "session")
    if not session:
        raise _auth_error("Authentication failed", status.HTTP_401_UNAUTHORIZED)

    auth_user = _safe_user(_read_field(response, "user"))
    app_user = _app_user_from_auth_user(auth_user) if auth_user else None

    return {
        "access_token": _read_field(session, "access_token"),
        "refresh_token": _read_field(session, "refresh_token"),
        "expires_in": _read_field(session, "expires_in"),
        "token_type": _read_field(session, "token_type") or "bearer",
        "user": auth_user,
        "app_user": app_user,
    }


def register_user(email: str, password: str) -> dict[str, Any]:
    try:
        response = supabase_auth.auth.sign_up(
            {
                "email": email,
                "password": password,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Unable to register user") from exc

    auth_user = _safe_user(_read_field(response, "user"))
    return {
        "message": "Registration successful. Please check your email if confirmation is enabled.",
        "user": auth_user,
        "app_user": _app_user_from_auth_user(auth_user) if auth_user else None,
        "session": _session_payload(response) if _read_field(response, "session") else None,
    }


def login_user(email: str, password: str) -> dict[str, Any]:
    try:
        response = supabase_auth.auth.sign_in_with_password(
            {
                "email": email,
                "password": password,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Invalid email or password", status.HTTP_401_UNAUTHORIZED) from exc

    return _session_payload(response)


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    try:
        response = supabase_auth.auth.refresh_session(refresh_token)
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Invalid refresh token", status.HTTP_401_UNAUTHORIZED) from exc

    return _session_payload(response)


def send_password_reset(email: str) -> dict[str, str]:
    try:
        supabase_auth.auth.reset_password_email(email)
        return {"message": "Password reset email sent"}
    except Exception as exc:
        raise _auth_error("Unable to send password reset email") from exc


def reset_password(access_token: str, password: str) -> dict[str, str]:
    try:
        supabase_auth.auth.update_user({"password": password}, jwt=access_token)
        return {"message": "Password updated"}
    except Exception as exc:
        raise _auth_error("Unable to reset password", status.HTTP_401_UNAUTHORIZED) from exc


def verify_request_token(request: Request) -> dict[str, Any]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _auth_error("Missing bearer token", status.HTTP_401_UNAUTHORIZED)

    try:
        auth_user = get_user_from_access_token(token)
        return {
            "user": auth_user,
            "app_user": _app_user_from_auth_user(auth_user),
        }
    except Exception as exc:
        raise _auth_error("Invalid bearer token", status.HTTP_401_UNAUTHORIZED) from exc


def get_user_from_access_token(token: str) -> dict[str, Any]:
    response = supabase_auth.auth.get_user(token)
    auth_user = _safe_user(_read_field(response, "user"))
    if not auth_user:
        raise RuntimeError("Invalid bearer token")
    return auth_user


def get_app_user_from_access_token(token: str) -> dict[str, Any]:
    auth_user = get_user_from_access_token(token)
    return _app_user_from_auth_user(auth_user)


def logout_request(request: Request) -> dict[str, str]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _auth_error("Missing bearer token", status.HTTP_401_UNAUTHORIZED)

    try:
        get_user_from_access_token(token)
    except Exception as exc:
        raise _auth_error("Invalid bearer token", status.HTTP_401_UNAUTHORIZED) from exc

    try:
        supabase_auth.auth.sign_out()
    except Exception:
        pass

    return {"message": "Logged out"}
