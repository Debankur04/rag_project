from auth.dto.Auth_dto import RefreshTokenRequest
from auth.services.refresh_token import refresh_token


def refresh_token_controller(payload: RefreshTokenRequest):
    return refresh_token(refresh_token_value=payload.refresh_token)
