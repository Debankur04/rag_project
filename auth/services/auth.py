from typing import Any

from fastapi import HTTPException, Request, status

from config.db import supabase


def _auth_error(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _safe_user(user: Any) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": getattr(user, "id", None),
        "email": getattr(user, "email", None),
        "created_at": getattr(user, "created_at", None),
    }


def _session_payload(response: Any) -> dict[str, Any]:
    session = getattr(response, "session", None)
    if not session:
        raise _auth_error("Authentication failed", status.HTTP_401_UNAUTHORIZED)

    return {
        "access_token": getattr(session, "access_token", None),
        "refresh_token": getattr(session, "refresh_token", None),
        "expires_in": getattr(session, "expires_in", None),
        "token_type": getattr(session, "token_type", "bearer"),
        "user": _safe_user(getattr(response, "user", None)),
    }


def register_user(email: str, password: str) -> dict[str, Any]:
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        return {
            "message": "Registration successful",
            "user": _safe_user(getattr(response, "user", None)),
            "session": _session_payload(response) if getattr(response, "session", None) else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Unable to register user") from exc


def login_user(email: str, password: str) -> dict[str, Any]:
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return _session_payload(response)
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Invalid email or password", status.HTTP_401_UNAUTHORIZED) from exc


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    try:
        response = supabase.auth.refresh_session(refresh_token)
        return _session_payload(response)
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Invalid refresh token", status.HTTP_401_UNAUTHORIZED) from exc


def send_password_reset(email: str) -> dict[str, str]:
    try:
        supabase.auth.reset_password_email(email)
        return {"message": "Password reset email sent"}
    except Exception as exc:
        raise _auth_error("Unable to send password reset email") from exc


def reset_password(access_token: str, password: str) -> dict[str, str]:
    try:
        supabase.auth.update_user({"password": password}, jwt=access_token)
        return {"message": "Password updated"}
    except Exception as exc:
        raise _auth_error("Unable to reset password", status.HTTP_401_UNAUTHORIZED) from exc


def verify_request_token(request: Request) -> dict[str, Any]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _auth_error("Missing bearer token", status.HTTP_401_UNAUTHORIZED)

    try:
        user = supabase.auth.get_user(token)
        return {"user": _safe_user(getattr(user, "user", None))}
    except Exception as exc:
        raise _auth_error("Invalid bearer token", status.HTTP_401_UNAUTHORIZED) from exc


def logout_request(request: Request) -> dict[str, str]:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _auth_error("Missing bearer token", status.HTTP_401_UNAUTHORIZED)

    try:
        supabase.auth.sign_out(jwt=token)
        return {"message": "Logged out"}
    except Exception as exc:
        raise _auth_error("Unable to log out", status.HTTP_401_UNAUTHORIZED) from exc
