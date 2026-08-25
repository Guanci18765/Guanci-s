from __future__ import annotations

import hmac
import os
import secrets

from fastapi import HTTPException, Request, status


def admin_credentials_are_valid(
    username: str,
    password: str,
) -> bool:
    expected_user = os.getenv(
        "ADMIN_USERNAME",
        "admin",
    )

    expected_password = os.getenv(
        "ADMIN_PASSWORD",
        "change-me",
    )

    return (
        hmac.compare_digest(
            username,
            expected_user,
        )
        and hmac.compare_digest(
            password,
            expected_password,
        )
    )


def kiosk_pin_is_valid(pin: str) -> bool:
    """
    Prüft den eingegebenen Kiosk-PIN.

    Ohne KIOSK_PIN in der .env ist eine
    Kiosk-Anmeldung nicht möglich.
    """

    expected_pin = os.getenv(
        "KIOSK_PIN",
        "",
    )

    if not expected_pin or not pin:
        return False

    return hmac.compare_digest(
        pin,
        expected_pin,
    )


def is_admin(request: Request) -> bool:
    """Prüft, ob die Sitzung als Admin angemeldet ist."""

    return request.session.get("is_admin") is True


def is_kiosk(request: Request) -> bool:
    """Prüft, ob die Sitzung als Kiosk angemeldet ist."""

    return request.session.get("is_kiosk") is True


def can_return_device(request: Request) -> bool:
    """
    Rückgaben dürfen nur durch einen Admin
    oder ein angemeldetes Kiosk-Gerät erfolgen.
    """

    return (
        is_admin(request)
        or is_kiosk(request)
    )


def csrf_token(request: Request) -> str:
    """Erstellt oder liefert den CSRF-Token der Sitzung."""

    token = request.session.get("csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token

    return token


def validate_csrf(
    request: Request,
    submitted_token: str | None,
) -> None:
    """Prüft den CSRF-Token eines Formulars."""

    expected_token = request.session.get(
        "csrf_token",
        "",
    )

    if (
        not submitted_token
        or not hmac.compare_digest(
            submitted_token,
            expected_token,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Ungültiges Formular-Token. "
                "Bitte lade die Seite neu."
            ),
        )