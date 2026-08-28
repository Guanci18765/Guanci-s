from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import database_session, get_connection
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
    directory=Path(__file__).resolve().parent.parent / "templates"
)
templates.env.filters["date_de"] = format_date_de


def safe_next_url(value: str | None) -> str | None:
    """Erlaubt nur interne Weiterleitungen dieser Webapp."""

    if not value:
        return None

    if not value.startswith("/") or value.startswith("//"):
        return None

    return value


def destination_for(user, next_url: str | None) -> str:
    """Bestimmt das Ziel nach einer erfolgreichen Anmeldung."""

    safe_url = safe_next_url(next_url)

    if safe_url:
        return safe_url

    if user["role"] == "admin":
        return "/admin/"

    return "/account/"


def admin_login_redirect(next_url: str) -> RedirectResponse:
    return RedirectResponse(
        f"/login?next={next_url}",
        status_code=303,
    )


@router.get("/login")
def login_page(
    request: Request,
    next: str | None = None,
):
    user = current_user(request)

    if user:
        return RedirectResponse(
            destination_for(user, next),
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "csrf_token": csrf_token(request),
            "next_url": safe_next_url(next) or "",
            "error": None,
        },
    )


@router.get("/admin/login")
def old_admin_login() -> RedirectResponse:
    """Leitet alte Lesezeichen auf die gemeinsame Anmeldung um."""

    return RedirectResponse(
        "/login?next=/admin/",
        status_code=302,
    )


@router.post("/login")
async def login(request: Request):
    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    user = authenticate_user(
        form.get("username", ""),
        form.get("password", ""),
    )

    next_url = safe_next_url(form.get("next"))

    if not user:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "csrf_token": csrf_token(request),
                "next_url": next_url or "",
                "error": "Benutzername oder Passwort ist falsch.",
            },
            status_code=401,
        )

    # Die alte Sitzung wird entfernt, damit sich ein Angreifer
    # keine vorher bekannte Sitzungs-ID zunutze machen kann.
    request.session.clear()
    request.session["user_id"] = user["id"]
    request.session["full_name"] = user["full_name"]
    request.session["role"] = user["role"]
    request.session["session_version"] = user["session_version"]

    return RedirectResponse(
        destination_for(user, next_url),
        status_code=303,
    )


@router.post("/admin/logout")
@router.post("/logout")
async def logout(request: Request):
    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))
    request.session.clear()

    return RedirectResponse("/login", status_code=303)


@router.get("/account/")
def account_page(request: Request):
    user = current_user(request)

    if not user:
        return admin_login_redirect("/account/")

    if user["role"] == "admin":
        return RedirectResponse("/admin/", status_code=302)

    connection = get_connection()

    try:
        loans = connection.execute(
            """
            SELECT
                l.*,
                d.name AS device_name,
                d.public_id
            FROM loans AS l
            JOIN devices AS d ON d.id = l.device_id
            WHERE l.user_id = ?
            ORDER BY l.checked_out_at DESC
            LIMIT 50
            """,
            (user["id"],),
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


def load_users():
    """Lädt Benutzerkonten einschließlich aktiver Ausleihen."""

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT
                u.*,
                COUNT(
                    CASE
                        WHEN l.id IS NOT NULL
                         AND l.returned_at IS NULL THEN 1
                    END
                ) AS active_loan_count
            FROM users AS u
            LEFT JOIN loans AS l ON l.user_id = u.id
            GROUP BY u.id
            ORDER BY u.full_name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()


def render_user_management(
    request: Request,
    *,
    error: str | None = None,
    message: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "admin/user_manage.html",
        {
            "users": load_users(),
            "error": error,
            "message": message,
            "csrf_token": csrf_token(request),
        },
        status_code=status_code,
    )


def users_redirect(
    *,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    parameters: dict[str, str] = {}

    if message:
        parameters["message"] = message
    if error:
        parameters["error"] = error

    url = "/admin/users/manage"
    if parameters:
        url = f"{url}?{urlencode(parameters)}"

    return RedirectResponse(url, status_code=303)


@router.get("/admin/users")
def user_menu(request: Request):
    if not is_admin(request):
        return admin_login_redirect("/admin/users")

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {},
    )


@router.get("/admin/users/new")
def new_user_page(
    request: Request,
    message: str | None = None,
):
    if not is_admin(request):
        return admin_login_redirect("/admin/users/new")

    return templates.TemplateResponse(
        request,
        "admin/user_create.html",
        {
            "message": message,
            "error": None,
            "form_values": {},
            "csrf_token": csrf_token(request),
        },
    )


@router.get("/admin/users/manage")
def user_management(
    request: Request,
    message: str | None = None,
    error: str | None = None,
):
    if not is_admin(request):
        return admin_login_redirect("/admin/users/manage")

    return render_user_management(
        request,
        message=message,
        error=error,
    )


@router.post("/admin/users/new")
async def create_user(request: Request):
    if not is_admin(request):
        return admin_login_redirect("/admin/users/new")

    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    username = form.get("username", "").strip()
    full_name = form.get("full_name", "").strip()
    password = form.get("password", "")
    role = form.get("role", "user")

    error: str | None = None

    if len(username) < 3 or len(username) > 50:
        error = "Der Benutzername muss 3 bis 50 Zeichen lang sein."
    elif len(full_name) < 2 or len(full_name) > 100:
        error = "Der vollständige Name muss 2 bis 100 Zeichen lang sein."
    elif len(password) < 10:
        error = "Das Passwort muss mindestens 10 Zeichen lang sein."
    elif role not in {"user", "admin"}:
        error = "Die gewählte Rolle ist ungültig."

    if not error:
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
            error = "Dieser Benutzername existiert bereits."

    if error:
        return templates.TemplateResponse(
            request,
            "admin/user_create.html",
            {
                "message": None,
                "error": error,
                "form_values": {
                    "username": username,
                    "full_name": full_name,
                    "role": role,
                },
                "csrf_token": csrf_token(request),
            },
            status_code=400,
        )

    query = urlencode({"message": "Benutzerkonto wurde angelegt."})
    return RedirectResponse(
        f"/admin/users/new?{query}",
        status_code=303,
    )


@router.post("/admin/users/{user_id}/toggle")
async def toggle_user(
    user_id: int,
    request: Request,
):
    admin = current_user(request)

    if not admin or admin["role"] != "admin":
        return admin_login_redirect("/admin/users/manage")

    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    if user_id == admin["id"]:
        return users_redirect(
            error="Das eigene Administratorkonto kann nicht gesperrt werden."
        )

    with database_session() as connection:
        target = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if not target:
            return users_redirect(error="Benutzerkonto wurde nicht gefunden.")

        if target["role"] == "admin" and target["is_active"]:
            active_admin_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE role = 'admin'
                  AND is_active = 1
                """
            ).fetchone()[0]

            if active_admin_count <= 1:
                return users_redirect(
                    error="Der letzte aktive Administrator kann nicht gesperrt werden."
                )

        connection.execute(
            """
            UPDATE users
            SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END
            WHERE id = ?
            """,
            (user_id,),
        )

    return users_redirect(message="Kontostatus wurde geändert.")


@router.post("/admin/users/{user_id}/password")
async def reset_user_password(
    user_id: int,
    request: Request,
):
    admin = current_user(request)

    if not admin or admin["role"] != "admin":
        return admin_login_redirect("/admin/users/manage")

    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    password = form.get("password", "")

    if len(password) < 10:
        return users_redirect(
            error="Das neue Passwort muss mindestens 10 Zeichen lang sein."
        )

    with database_session() as connection:
        result = connection.execute(
            """
            UPDATE users
            SET
                password_hash = ?,
                session_version = session_version + 1
            WHERE id = ?
            """,
            (
                hash_password(password),
                user_id,
            ),
        )

        if result.rowcount == 0:
            return users_redirect(error="Benutzerkonto wurde nicht gefunden.")

    if user_id == admin["id"]:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    return users_redirect(message="Das Passwort wurde geändert.")


@router.post("/admin/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
):
    admin = current_user(request)

    if not admin or admin["role"] != "admin":
        return admin_login_redirect("/admin/users/manage")

    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    if user_id == admin["id"]:
        return users_redirect(
            error="Das eigene Administratorkonto kann nicht gelöscht werden."
        )

    with database_session() as connection:
        target = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if not target:
            return users_redirect(error="Benutzerkonto wurde nicht gefunden.")

        active_loan = connection.execute(
            """
            SELECT 1
            FROM loans
            WHERE user_id = ?
              AND returned_at IS NULL
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        if active_loan:
            return users_redirect(
                error=(
                    "Das Benutzerkonto besitzt noch eine aktive Ausleihe. "
                    "Das Gerät muss zuerst zurückgegeben werden."
                )
            )

        if target["role"] == "admin" and target["is_active"]:
            active_admin_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE role = 'admin'
                  AND is_active = 1
                """
            ).fetchone()[0]

            if active_admin_count <= 1:
                return users_redirect(
                    error="Der letzte aktive Administrator kann nicht gelöscht werden."
                )

        # Abgeschlossene Ausleihen bleiben mit dem gespeicherten
        # Ausleihernamen erhalten, werden aber vom Konto getrennt.
        connection.execute(
            "UPDATE loans SET user_id = NULL WHERE user_id = ?",
            (user_id,),
        )
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        )

    return users_redirect(message="Benutzerkonto wurde gelöscht.")
