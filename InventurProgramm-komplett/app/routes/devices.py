from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import database_session, get_connection
from app.device_types import (
    INSPECTION_DEVICE_TYPES,
    device_is_configured,
)
from app.formatting import format_date_de
from app.security import current_user, csrf_token, validate_csrf


router = APIRouter(prefix="/device")

templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)
templates.env.filters["date_de"] = format_date_de


def device_redirect(
    public_id: str,
    *,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Leitet mit optionaler Meldung zur Geräteseite zurück."""

    parameters: dict[str, str] = {}

    if message:
        parameters["message"] = message
    if error:
        parameters["error"] = error

    url = f"/device/{public_id}"

    if parameters:
        url = f"{url}?{urlencode(parameters)}"

    return RedirectResponse(url=url, status_code=303)


def login_redirect(public_id: str) -> RedirectResponse:
    """Merkt sich das gescannte Gerät für die Zeit nach dem Login."""

    query = urlencode({"next": f"/device/{public_id}"})
    return RedirectResponse(f"/login?{query}", status_code=303)


def get_public_device(public_id: str) -> sqlite3.Row | None:
    """Lädt ein Gerät und seine aktive Ausleihe."""

    connection = get_connection()

    try:
        return connection.execute(
            """
            SELECT
                d.*,
                l.id AS active_loan_id,
                l.user_id AS active_user_id,
                l.expected_return_at AS active_expected_return_at,
                COALESCE(l.is_permanent, 0) AS active_is_permanent
            FROM devices AS d
            LEFT JOIN loans AS l
                ON l.device_id = d.id
                AND l.returned_at IS NULL
            WHERE d.public_id = ?
              AND d.deleted_at IS NULL
            """,
            (public_id,),
        ).fetchone()
    finally:
        connection.close()


def block_reason(device: sqlite3.Row) -> str | None:
    """Prüft alle serverseitigen Ausleihregeln."""

    if device["active_loan_id"]:
        return "Dieses Gerät ist derzeit ausgeliehen."

    if not device["is_active"]:
        return "Dieses Gerät gehört nicht mehr zum aktiven Inventar."

    if device["is_personal_device"]:
        return (
            "Dieses Gerät ist persönlich zugeordnet "
            "und kann nicht ausgeliehen werden."
        )

    if device["condition"] == "service":
        return "Dieses Gerät befindet sich im Service."

    if device["condition"] == "defective":
        return "Dieses Gerät ist als defekt markiert."

    if not device_is_configured(
        device["device_type"],
        device["setup_complete"],
    ):
        return "Das Setup dieses Geräts ist noch nicht abgeschlossen."

    return None


def user_may_return(user: sqlite3.Row, device: sqlite3.Row) -> bool:
    """Admins und der ursprüngliche Ausleiher dürfen zurückgeben."""

    if user["role"] == "admin":
        return True

    return (
        device["active_user_id"] is not None
        and device["active_user_id"] == user["id"]
    )


@router.get("/{public_id}")
def device_page(
    public_id: str,
    request: Request,
    message: str | None = None,
    error: str | None = None,
):
    """Zeigt nach der Anmeldung die gescannte Geräteseite."""

    user = current_user(request)

    if not user:
        return login_redirect(public_id)

    device = get_public_device(public_id)

    if not device:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {"csrf_token": csrf_token(request)},
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "device.html",
        {
            "device": device,
            "logged_in_user": user,
            "inspection_device_types": INSPECTION_DEVICE_TYPES,
            "block_reason": block_reason(device),
            "can_return": user_may_return(user, device),
            "csrf_token": csrf_token(request),
            "message": message,
            "error": error,
        },
    )


@router.post("/{public_id}/borrow")
async def borrow_device(public_id: str, request: Request):
    """Verknüpft eine neue Ausleihe mit dem angemeldeten Konto."""

    user = current_user(request)

    if not user:
        return login_redirect(public_id)

    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    expected_return_at_input = form.get(
        "expected_return_at",
        "",
    ).strip()

    if not expected_return_at_input:
        return device_redirect(
            public_id,
            error="Bitte wähle ein voraussichtliches Rückgabedatum aus.",
        )

    try:
        expected_return_date = date.fromisoformat(
            expected_return_at_input
        )
    except ValueError:
        return device_redirect(
            public_id,
            error="Das angegebene Rückgabedatum ist ungültig.",
        )

    if expected_return_date < date.today():
        return device_redirect(
            public_id,
            error="Das Rückgabedatum darf nicht in der Vergangenheit liegen.",
        )

    try:
        with database_session() as connection:
            # BEGIN IMMEDIATE verhindert zwei fast gleichzeitige
            # Ausleihen desselben Gerätes.
            connection.execute("BEGIN IMMEDIATE")

            device = connection.execute(
                """
                SELECT
                    d.*,
                    l.id AS active_loan_id
                FROM devices AS d
                LEFT JOIN loans AS l
                    ON l.device_id = d.id
                    AND l.returned_at IS NULL
                WHERE d.public_id = ?
                  AND d.deleted_at IS NULL
                """,
                (public_id,),
            ).fetchone()

            if not device:
                return device_redirect(
                    public_id,
                    error="Das Gerät wurde nicht gefunden.",
                )

            reason = block_reason(device)

            if reason:
                return device_redirect(public_id, error=reason)

            connection.execute(
                """
                INSERT INTO loans (
                    device_id,
                    user_id,
                    borrower_name,
                    expected_return_at,
                    is_permanent
                )
                VALUES (?, ?, ?, ?, 0)
                """,
                (
                    device["id"],
                    user["id"],
                    user["full_name"],
                    expected_return_date.isoformat(),
                ),
            )
    except sqlite3.IntegrityError:
        return device_redirect(
            public_id,
            error=(
                "Das Gerät wurde gerade von jemand anderem ausgeliehen."
            ),
        )

    return device_redirect(
        public_id,
        message="Ausleihe erfolgreich gespeichert.",
    )


@router.post("/{public_id}/return")
async def return_device(public_id: str, request: Request):
    """Erlaubt die Rückgabe nur dem Ausleiher oder einem Admin."""

    user = current_user(request)

    if not user:
        return login_redirect(public_id)

    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))

    with database_session() as connection:
        device = connection.execute(
            """
            SELECT
                d.id,
                l.id AS active_loan_id,
                l.user_id AS active_user_id
            FROM devices AS d
            LEFT JOIN loans AS l
                ON l.device_id = d.id
                AND l.returned_at IS NULL
            WHERE d.public_id = ?
              AND d.deleted_at IS NULL
            """,
            (public_id,),
        ).fetchone()

        if not device or not device["active_loan_id"]:
            return device_redirect(
                public_id,
                message="Keine aktive Ausleihe gefunden.",
            )

        # Bei historischen Ausleihen ohne user_id darf nur
        # ein Admin die Rückgabe durchführen.
        may_return = (
            user["role"] == "admin"
            or (
                device["active_user_id"] is not None
                and device["active_user_id"] == user["id"]
            )
        )

        if not may_return:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Nur der Ausleiher oder ein Admin darf "
                    "dieses Gerät zurückgeben."
                ),
            )

        connection.execute(
            """
            UPDATE loans
            SET returned_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND returned_at IS NULL
            """,
            (device["active_loan_id"],),
        )

    return device_redirect(
        public_id,
        message="Rückgabe erfolgreich gespeichert.",
    )
