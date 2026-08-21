from __future__ import annotations

import hmac
import os
import secrets

from fastapi import HTTPException, Request, status


def admin_credentials_are_valid(username: str, password: str) -> bool:
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "change-me")
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(
        password, expected_password
    )


def is_admin(request: Request) -> bool:
    return request.session.get("is_admin") is True


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, submitted_token: str | None) -> None:
    expected_token = request.session.get("csrf_token", "")
    if not submitted_token or not hmac.compare_digest(submitted_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ungültiges Formular-Token. Bitte lade die Seite neu.",
        )

