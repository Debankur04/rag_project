from auth.dto.Auth_dto import ForgotPasswordRequest, ResetPasswordRequest
from auth.services.forgot_password import forgot_password, update_forgotten_password


def forgot_password_controller(payload: ForgotPasswordRequest):
    return forgot_password(email=payload.email)


def reset_password_controller(payload: ResetPasswordRequest):
    return update_forgotten_password(
        access_token=payload.access_token,
        password=payload.password,
    )
