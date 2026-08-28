from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import (
    database_session,
    get_connection,
)
from app.formatting import format_date_de
from app.security import (
    authenticate_user,
    csrf_token,
    current_user,
    hash_password,
    is_admin,
    validate_csrf,
)


router = APIRouter()


templates = Jinja2Templates(
    directory=(
        Path(__file__).resolve().parent.parent
        / "templates"
    )
)

templates.env.filters["date_de"] = format_date_de


# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------


def safe_next_url(
    value: str | None,
) -> str | None:
    """
    Erlaubt nur interne Weiterleitungen.

    Dadurch kann ein manipulierter Login-Link den
    Benutzer nicht auf eine fremde Website umleiten.
    """

    if not value:
        return None

    if not value.startswith("/"):
        return None

    if value.startswith("//"):
        return None

    return value


def destination_for(
    user: sqlite3.Row,
    next_url: str | None,
) -> str:
    """
    Bestimmt das Ziel nach erfolgreicher Anmeldung.
    """

    safe_url = safe_next_url(
        next_url
    )

    if safe_url:
        return safe_url

    if user["role"] == "admin":
        return "/admin/"

    return "/account/"


def login_redirect(
    next_url: str,
) -> RedirectResponse:
    """
    Leitet zur gemeinsamen Anmeldung weiter und
    merkt sich die ursprünglich gewünschte Seite.
    """

    parameters = urlencode(
        {
            "next": next_url,
        }
    )

    return RedirectResponse(
        url=f"/login?{parameters}",
        status_code=303,
    )


def users_redirect(
    *,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """
    Leitet zur Benutzerverwaltung zurück.

    Eine Erfolgs- oder Fehlermeldung kann dabei
    über die URL übertragen werden.
    """

    parameters: dict[str, str] = {}

    if message:
        parameters["message"] = message

    if error:
        parameters["error"] = error

    url = "/admin/users"

    if parameters:
        url = (
            f"{url}?"
            f"{urlencode(parameters)}"
        )

    return RedirectResponse(
        url=url,
        status_code=303,
    )


def load_users() -> list[sqlite3.Row]:
    """
    Lädt alle Benutzerkonten für die Administration.

    Zusätzlich wird gezählt, wie viele aktive
    Ausleihen jedes Konto besitzt.
    """

    connection = get_connection()

    try:
        users = connection.execute(
            """
            SELECT
                u.id,
                u.username,
                u.full_name,
                u.role,
                u.is_active,
                u.created_at,

                COUNT(
                    CASE
                        WHEN l.returned_at IS NULL
                        THEN 1
                    END
                ) AS active_loan_count

            FROM users AS u

            LEFT JOIN loans AS l
                ON l.user_id = u.id

            GROUP BY
                u.id

            ORDER BY
                u.full_name COLLATE NOCASE
            """
        ).fetchall()

        return users

    finally:
        connection.close()


def render_user_management(
    request: Request,
    *,
    message: str | None = None,
    error: str | None = None,
    status_code: int = 200,
):
    """
    Rendert die Benutzerverwaltung.
    """

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "users": load_users(),
            "message": message,
            "error": error,
            "csrf_token": csrf_token(request),
        },
        status_code=status_code,
    )


# ---------------------------------------------------------
# Gemeinsame Anmeldung
# ---------------------------------------------------------


@router.get("/login")
def login_page(
    request: Request,
    next: str | None = None,
):
    """
    Zeigt die gemeinsame Anmeldung für Benutzer
    und Administratoren.
    """

    user = current_user(
        request
    )

    if user:
        return RedirectResponse(
            url=destination_for(
                user,
                next,
            ),
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "csrf_token": csrf_token(request),
            "next_url": (
                safe_next_url(next)
                or ""
            ),
            "error": None,
        },
    )


@router.get("/admin/login")
def old_admin_login() -> RedirectResponse:
    """
    Leitet alte Admin-Login-Lesezeichen auf die
    neue gemeinsame Anmeldung weiter.
    """

    return login_redirect(
        "/admin/"
    )


@router.post("/login")
async def login(
    request: Request,
):
    """
    Prüft Benutzername und Passwort.

    Die Rolle des Kontos entscheidet anschließend,
    ob das Benutzerkonto oder das Admin-Dashboard
    geöffnet wird.
    """

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    username = form.get(
        "username",
        "",
    ).strip()

    password = form.get(
        "password",
        "",
    )

    next_url = safe_next_url(
        form.get("next")
    )

    user = authenticate_user(
        username,
        password,
    )

    if not user:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "csrf_token": csrf_token(request),
                "next_url": next_url or "",
                "error": (
                    "Benutzername oder Passwort "
                    "ist falsch."
                ),
            },
            status_code=401,
        )

    # Die alte Sitzung wird vollständig entfernt.
    # Das schützt vor Session-Fixation.
    request.session.clear()

    request.session["user_id"] = (
        user["id"]
    )

    request.session["full_name"] = (
        user["full_name"]
    )

    request.session["role"] = (
        user["role"]
    )

    return RedirectResponse(
        url=destination_for(
            user,
            next_url,
        ),
        status_code=303,
    )


# ---------------------------------------------------------
# Abmeldung
# ---------------------------------------------------------


@router.post("/logout")
@router.post("/admin/logout")
async def logout(
    request: Request,
):
    """
    Beendet eine Benutzer- oder Admin-Sitzung.
    """

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    request.session.clear()

    return RedirectResponse(
        url="/login",
        status_code=303,
    )


# ---------------------------------------------------------
# Benutzerkonto
# ---------------------------------------------------------


@router.get("/account/")
def account_page(
    request: Request,
):
    """
    Zeigt einem Benutzer seine eigenen Ausleihen.
    """

    user = current_user(
        request
    )

    if not user:
        return login_redirect(
            "/account/"
        )

    if user["role"] == "admin":
        return RedirectResponse(
            url="/admin/",
            status_code=302,
        )

    connection = get_connection()

    try:
        loans = connection.execute(
            """
            SELECT
                l.id,
                l.checked_out_at,
                l.expected_return_at,
                l.returned_at,
                l.is_permanent,

                d.name AS device_name,
                d.public_id

            FROM loans AS l

            JOIN devices AS d
                ON d.id = l.device_id

            WHERE l.user_id = ?

            ORDER BY
                l.checked_out_at DESC

            LIMIT 50
            """,
            (
                user["id"],
            ),
        ).fetchall()

    finally:
        connection.close()

    return templates.TemplateResponse(
        request,
        "auth/account.html",
        {
            "user": user,
            "loans": loans,
            "csrf_token": csrf_token(request),
        },
    )


# ---------------------------------------------------------
# Benutzerverwaltung
# ---------------------------------------------------------


@router.get("/admin/users")
def user_management(
    request: Request,
    message: str | None = None,
    error: str | None = None,
):
    """
    Zeigt die Benutzerverwaltung.

    Diese Seite darf ausschließlich von einem
    Administrator geöffnet werden.
    """

    if not is_admin(request):
        return login_redirect(
            "/admin/users"
        )

    return render_user_management(
        request,
        message=message,
        error=error,
    )


# ---------------------------------------------------------
# Neues Benutzerkonto
# ---------------------------------------------------------


@router.post("/admin/users/new")
async def create_user(
    request: Request,
):
    """
    Erstellt ein neues Benutzer- oder Admin-Konto.
    """

    if not is_admin(request):
        return login_redirect(
            "/admin/users"
        )

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    username = form.get(
        "username",
        "",
    ).strip()

    full_name = form.get(
        "full_name",
        "",
    ).strip()

    password = form.get(
        "password",
        "",
    )

    role = form.get(
        "role",
        "user",
    )

    if (
        len(username) < 3
        or len(username) > 50
    ):
        return render_user_management(
            request,
            error=(
                "Der Benutzername muss zwischen "
                "3 und 50 Zeichen lang sein."
            ),
            status_code=400,
        )

    if (
        len(full_name) < 2
        or len(full_name) > 100
    ):
        return render_user_management(
            request,
            error=(
                "Der vollständige Name muss zwischen "
                "2 und 100 Zeichen lang sein."
            ),
            status_code=400,
        )

    if len(password) < 10:
        return render_user_management(
            request,
            error=(
                "Das Passwort muss mindestens "
                "10 Zeichen lang sein."
            ),
            status_code=400,
        )

    if len(password) > 200:
        return render_user_management(
            request,
            error=(
                "Das Passwort ist zu lang."
            ),
            status_code=400,
        )

    if role not in {
        "user",
        "admin",
    }:
        return render_user_management(
            request,
            error=(
                "Die ausgewählte Benutzerrolle "
                "ist ungültig."
            ),
            status_code=400,
        )

    try:
        with database_session() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    username,
                    full_name,
                    password_hash,
                    role
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    username,
                    full_name,
                    hash_password(password),
                    role,
                ),
            )

    except sqlite3.IntegrityError:
        return render_user_management(
            request,
            error=(
                "Dieser Benutzername "
                "existiert bereits."
            ),
            status_code=400,
        )

    return users_redirect(
        message=(
            "Benutzerkonto erfolgreich angelegt."
        ),
    )


# ---------------------------------------------------------
# Passwort zurücksetzen
# ---------------------------------------------------------


@router.post(
    "/admin/users/{user_id}/password"
)
async def change_user_password(
    user_id: int,
    request: Request,
):
    """
    Erlaubt einem Administrator, das Passwort
    eines Benutzerkontos zurückzusetzen.
    """

    if not is_admin(request):
        return login_redirect(
            "/admin/users"
        )

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    new_password = form.get(
        "new_password",
        "",
    )

    password_confirmation = form.get(
        "password_confirmation",
        "",
    )

    if len(new_password) < 10:
        return users_redirect(
            error=(
                "Das Passwort muss mindestens "
                "10 Zeichen lang sein."
            ),
        )

    if len(new_password) > 200:
        return users_redirect(
            error=(
                "Das Passwort ist zu lang."
            ),
        )

    if (
        new_password
        != password_confirmation
    ):
        return users_redirect(
            error=(
                "Die Passwörter stimmen "
                "nicht überein."
            ),
        )

    with database_session() as connection:
        result = connection.execute(
            """
            UPDATE users

            SET password_hash = ?

            WHERE id = ?
            """,
            (
                hash_password(
                    new_password
                ),
                user_id,
            ),
        )

    if result.rowcount == 0:
        return users_redirect(
            error=(
                "Das Benutzerkonto wurde "
                "nicht gefunden."
            ),
        )

    return users_redirect(
        message=(
            "Passwort erfolgreich geändert."
        ),
    )


# ---------------------------------------------------------
# Konto sperren oder aktivieren
# ---------------------------------------------------------


@router.post(
    "/admin/users/{user_id}/toggle"
)
async def toggle_user(
    user_id: int,
    request: Request,
):
    """
    Sperrt ein aktives Konto oder aktiviert
    ein gesperrtes Konto wieder.
    """

    admin = current_user(
        request
    )

    if (
        not admin
        or admin["role"] != "admin"
    ):
        return login_redirect(
            "/admin/users"
        )

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    # Ein Admin darf sein eigenes Konto nicht
    # versehentlich sperren.
    if user_id == admin["id"]:
        return users_redirect(
            error=(
                "Du kannst dein eigenes "
                "Admin-Konto nicht sperren."
            ),
        )

    with database_session() as connection:
        account = connection.execute(
            """
            SELECT
                id,
                is_active

            FROM users

            WHERE id = ?
            """,
            (
                user_id,
            ),
        ).fetchone()

        if not account:
            return users_redirect(
                error=(
                    "Das Benutzerkonto wurde "
                    "nicht gefunden."
                ),
            )

        new_status = (
            0
            if account["is_active"]
            else 1
        )

        connection.execute(
            """
            UPDATE users

            SET is_active = ?

            WHERE id = ?
            """,
            (
                new_status,
                user_id,
            ),
        )

    if new_status:
        message = (
            "Benutzerkonto wurde aktiviert."
        )
    else:
        message = (
            "Benutzerkonto wurde gesperrt."
        )

    return users_redirect(
        message=message,
    )