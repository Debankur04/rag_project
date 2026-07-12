from typing import Any

from fastapi import HTTPException, Request, status

from config.db import supabase, supabase_auth


USER_TABLE = "users"


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


def _utc_now_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat()


def get_or_create_app_user(email: str) -> dict[str, Any]:
    normalized_email = email.strip().lower()
    response = (
        supabase.table(USER_TABLE)
        .select("*")
        .eq("email", normalized_email)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]

    created = (
        supabase.table(USER_TABLE)
        .insert({"email": normalized_email, "created_at": _utc_now_iso()})
        .execute()
    )
    if not created.data:
        raise RuntimeError("Unable to create application user")
    return created.data[0]


def update_last_login(user_id: int) -> None:
    supabase.table(USER_TABLE).update({"last_login": _utc_now_iso()}).eq("id", user_id).execute()


def _session_payload(response: Any) -> dict[str, Any]:
    session = getattr(response, "session", None)
    if not session:
        raise _auth_error("Authentication failed", status.HTTP_401_UNAUTHORIZED)

    auth_user = _safe_user(getattr(response, "user", None))
    try:
        app_user = get_or_create_app_user(auth_user["email"]) if auth_user and auth_user.get("email") else None
        if app_user:
            update_last_login(app_user["id"])
    except Exception as exc:
        raise _auth_error(
            "Login succeeded, but user profile sync failed. Check SUPABASE_SERVICE_ROLE_KEY or users table RLS policy.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "access_token": getattr(session, "access_token", None),
        "refresh_token": getattr(session, "refresh_token", None),
        "expires_in": getattr(session, "expires_in", None),
        "token_type": getattr(session, "token_type", "bearer"),
        "user": auth_user,
        "app_user": app_user,
    }


def register_user(email: str, password: str) -> dict[str, Any]:
    try:
        response = supabase_auth.auth.sign_up({"email": email, "password": password})
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error("Unable to register user") from exc

    try:
        auth_user = _safe_user(getattr(response, "user", None))
        app_user = get_or_create_app_user(auth_user["email"]) if auth_user and auth_user.get("email") else None
        return {
            "message": "Registration successful. Please check your email and login again.",
            "user": auth_user,
            "app_user": app_user,
            "session": _session_payload(response) if getattr(response, "session", None) else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _auth_error(
            "Registration succeeded, but user profile sync failed. Check SUPABASE_SERVICE_ROLE_KEY or users table RLS policy.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc


def login_user(email: str, password: str) -> dict[str, Any]:
    try:
        response = supabase_auth.auth.sign_in_with_password({"email": email, "password": password})
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
        return {"user": get_user_from_access_token(token)}
    except Exception as exc:
        raise _auth_error("Invalid bearer token", status.HTTP_401_UNAUTHORIZED) from exc


def get_user_from_access_token(token: str) -> dict[str, Any] | None:
    user = supabase.auth.get_user(token)
    return _safe_user(getattr(user, "user", None))


def get_app_user_from_access_token(token: str) -> dict[str, Any]:
    auth_user = get_user_from_access_token(token)
    if not auth_user or not auth_user.get("email"):
        raise RuntimeError("Access token does not contain an email")
    app_user = get_or_create_app_user(auth_user["email"])
    return {
        "id": app_user["id"],
        "email": app_user["email"],
        "auth_user": auth_user,
    }


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
