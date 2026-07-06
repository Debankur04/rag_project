from auth.dto.Auth_dto import RegisterRequest
from auth.services.signup import signup


def signup_controller(payload: RegisterRequest):
    return signup(email=payload.email, password=payload.password)
