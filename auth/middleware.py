from fastapi import Request, status
from fastapi.responses import JSONResponse

from auth.services.auth import get_app_user_from_access_token


PUBLIC_PATHS = {
    "/",
    "/health",
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    "/auth/forgot-password",
    "/auth/reset-password",

    "/docs",
    "/docs/",
    "/redoc",
    "/redoc/",

    "/openapi.json",
    "/docs/oauth2-redirect",
    "/favicon.ico",
}


async def access_token_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing bearer token"},
        )

    try:
        request.state.app_user = get_app_user_from_access_token(token)
        request.state.user = request.state.app_user["auth_user"]
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid bearer token"},
        )

    return await call_next(request)
