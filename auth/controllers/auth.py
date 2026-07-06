from fastapi import APIRouter, Request

from auth.dto.Auth_dto import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from auth.controllers.forgot_password import (
    forgot_password_controller,
    reset_password_controller,
)
from auth.controllers.refresh_token import refresh_token_controller
from auth.controllers.signin import signin_controller
from auth.controllers.signup import signup_controller
from auth.services.auth import (
    logout_request,
    verify_request_token,
)


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterRequest):
    return signup_controller(payload)


@router.post("/login")
def login(payload: LoginRequest):
    return signin_controller(payload)


@router.post("/logout")
def logout(request: Request):
    return logout_request(request)


@router.post("/refresh")
def refresh_token(payload: RefreshTokenRequest):
    return refresh_token_controller(payload)


@router.get("/verify")
def verify_token(request: Request):
    return verify_request_token(request)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    return forgot_password_controller(payload)


@router.post("/reset-password")
def reset_password_endpoint(payload: ResetPasswordRequest):
    return reset_password_controller(payload)
