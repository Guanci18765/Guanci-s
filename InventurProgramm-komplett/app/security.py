from __future__ import annotations

import hmac
import os
import secrets
import sqlite3

from fastapi import HTTPException, Request, status
from pwdlib import PasswordHash

from app.database import database_session, get_connection


# Passwörter werden ausschließlich als sichere Hashes gespeichert.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Erzeugt den Datenbankwert für ein Passwort."""

    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Vergleicht ein Passwort mit seinem gespeicherten Hash."""

    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


def ensure_initial_admin() -> None:
    """Legt beim ersten Start den Admin aus der .env an."""

    username = os.getenv("ADMIN_USERNAME", "admin").strip()
    full_name = os.getenv(
        "ADMIN_FULL_NAME",
        "Administrator",
    ).strip()
    password = os.getenv("ADMIN_PASSWORD", "")

    if not username or not full_name or not password:
        raise RuntimeError(
            "ADMIN_USERNAME, ADMIN_FULL_NAME und "
            "ADMIN_PASSWORD müssen in der .env stehen."
        )

    with database_session() as connection:
        existing_admin = connection.execute(
            """
            SELECT id
            FROM users
            WHERE role = 'admin'
            LIMIT 1
            """
        ).fetchone()

        if existing_admin:
            return

        connection.execute(
            """
            INSERT INTO users (
                username,
                full_name,
                password_hash,
                role
            )
            VALUES (?, ?, ?, 'admin')
            """,
            (
                username,
                full_name,
                hash_password(password),
            ),
        )


def authenticate_user(
    username: str,
    password: str,
) -> sqlite3.Row | None:
    """Prüft die gemeinsame Anmeldung für User und Admins."""

    connection = get_connection()

    try:
        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE username = ? COLLATE NOCASE
              AND is_active = 1
            """,
            (username.strip(),),
        ).fetchone()
    finally:
        connection.close()

    if not user:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    return user


def current_user(request: Request) -> sqlite3.Row | None:
    """
    Liefert den aktuell angemeldeten aktiven Benutzer.

    Die Datenbank wird erneut geprüft, damit eine Kontosperre
    sofort wirksam wird.
    """

    user_id = request.session.get("user_id")
    session_version = request.session.get("session_version")

    if (
        not isinstance(user_id, int)
        or not isinstance(session_version, int)
    ):
        return None

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT
                id,
                username,
                full_name,
                role,
                is_active,
                session_version,
                created_at
            FROM users
            WHERE id = ?
              AND is_active = 1
              AND session_version = ?
            """,
            (
                user_id,
                session_version,
            ),
        ).fetchone()
    finally:
        connection.close()


def is_admin(request: Request) -> bool:
    """Prüft die Rolle des angemeldeten Kontos."""

    user = current_user(request)
    return bool(user and user["role"] == "admin")


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

    expected_token = request.session.get("csrf_token", "")

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
