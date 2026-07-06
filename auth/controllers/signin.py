from auth.dto.Auth_dto import LoginRequest
from auth.services.signin import signin


def signin_controller(payload: LoginRequest):
    return signin(email=payload.email, password=payload.password)
