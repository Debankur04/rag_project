from fastapi import APIRouter, Request

from rag_project.auth.dto.Auth_dto import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from rag_project.auth.services.auth import (
    login_user,
    logout_request,
    refresh_access_token,
    register_user,
    reset_password,
    send_password_reset,
    verify_request_token,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterRequest):
    return register_user(payload.email, payload.password)


@router.post("/login")
def login(payload: LoginRequest):
    return login_user(payload.email, payload.password)


@router.post("/logout")
def logout(request: Request):
    return logout_request(request)


@router.post("/refresh")
def refresh_token(payload: RefreshTokenRequest):
    return refresh_access_token(payload.refresh_token)


@router.get("/verify")
def verify_token(request: Request):
    return verify_request_token(request)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    return send_password_reset(payload.email)


@router.post("/reset-password")
def reset_password_endpoint(payload: ResetPasswordRequest):
    return reset_password(payload.access_token, payload.password)
