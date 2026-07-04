import re

from pydantic import BaseModel, Field, field_validator


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _EmailMixin(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_RE.match(normalized):
            raise ValueError("Invalid email address")
        return normalized


class RegisterRequest(_EmailMixin):
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(_EmailMixin):
    password: str = Field(..., min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16)


class ForgotPasswordRequest(_EmailMixin):
    pass


class ResetPasswordRequest(BaseModel):
    access_token: str = Field(..., min_length=16)
    password: str = Field(..., min_length=8, max_length=128)
