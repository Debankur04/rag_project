from auth.services.auth import reset_password, send_password_reset


def forgot_password(email: str) -> dict[str, str]:
    return send_password_reset(email=email)


def update_forgotten_password(access_token: str, password: str) -> dict[str, str]:
    return reset_password(access_token=access_token, password=password)
