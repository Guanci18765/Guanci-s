from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import database_session, get_connection
from app.formatting import format_date_de
from app.security import csrf_token, validate_csrf


router = APIRouter(prefix="/device")

templates = Jinja2Templates(
    directory=(
        Path(__file__).resolve().parent.parent
        / "templates"
    )
)

templates.env.filters["date_de"] = format_date_de


def device_redirect(
    public_id: str,
    *,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """
    Leitet zurück auf die öffentliche Geräteseite.

    Nachrichten und Fehlermeldungen werden korrekt
    für die URL codiert.
    """

    parameters: dict[str, str] = {}

    if message:
        parameters["message"] = message

    if error:
        parameters["error"] = error

    url = f"/device/{public_id}"

    if parameters:
        url = f"{url}?{urlencode(parameters)}"

    return RedirectResponse(
        url=url,
        status_code=303,
    )


def get_public_device(
    public_id: str,
) -> sqlite3.Row | None:
    """
    Sucht ein Gerät anhand seiner öffentlichen ID.

    Zusätzlich wird geprüft, ob eine aktive Ausleihe
    für das Gerät existiert.
    """

    connection = get_connection()

    try:
        device = connection.execute(
            """
            SELECT
                d.*,
                l.id AS active_loan_id,
                l.expected_return_at
                    AS active_expected_return_at
            FROM devices AS d

            LEFT JOIN loans AS l
                ON l.device_id = d.id
                AND l.returned_at IS NULL

            WHERE d.public_id = ?
            """,
            (public_id,),
        ).fetchone()

        return device

    finally:
        connection.close()


def block_reason(
    device: sqlite3.Row,
) -> str | None:
    """
    Prüft, ob das Gerät ausgeliehen werden darf.

    None bedeutet:
        Das Gerät darf ausgeliehen werden.

    Ein Text bedeutet:
        Das Gerät ist gesperrt.
    """

    # Ein bereits ausgeliehenes Gerät darf nicht
    # erneut ausgeliehen werden.
    if device["active_loan_id"]:
        return "Dieses Gerät ist derzeit ausgeliehen."

    # Eine bestehende Ausleihe kann weiterhin
    # zurückgegeben werden, auch wenn das Gerät
    # währenddessen inaktiv gestellt wurde.
    if not device["is_active"]:
        return (
            "Dieses Gerät gehört nicht mehr "
            "zum aktiven Inventar."
        )

    if device["condition"] == "service":
        return (
            "Dieses Gerät befindet sich im Service."
        )

    if device["condition"] == "defective":
        return (
            "Dieses Gerät ist als defekt markiert."
        )

    if not device["setup_complete"]:
        return (
            "Das Setup dieses Geräts ist "
            "noch nicht abgeschlossen."
        )

    return None


@router.get("/{public_id}")
def device_page(
    public_id: str,
    request: Request,
    message: str | None = None,
    error: str | None = None,
):
    """
    Zeigt die öffentliche Geräteseite an.
    """

    device = get_public_device(public_id)

    if not device:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "device.html",
        {
            "device": device,
            "block_reason": block_reason(device),
            "csrf_token": csrf_token(request),
            "message": message,
            "error": error,
        },
    )


@router.post("/{public_id}/borrow")
async def borrow_device(
    public_id: str,
    request: Request,
):
    """
    Speichert eine neue Geräteausleihe.
    """

    form = dict(await request.form())

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    borrower_name = (
        form.get("borrower_name", "").strip()
    )

    if (
        len(borrower_name) < 2
        or len(borrower_name) > 100
    ):
        return device_redirect(
            public_id,
            error=(
                "Bitte gib deinen vollständigen Namen ein."
            ),
        )

    expected_return_at_input = (
        form.get("expected_return_at", "").strip()
    )

    if not expected_return_at_input:
        return device_redirect(
            public_id,
            error=(
                "Bitte wähle ein voraussichtliches "
                "Rückgabedatum aus."
            ),
        )

    try:
        expected_return_date = date.fromisoformat(
            expected_return_at_input
        )

    except ValueError:
        return device_redirect(
            public_id,
            error=(
                "Das angegebene Rückgabedatum "
                "ist ungültig."
            ),
        )

    if expected_return_date < date.today():
        return device_redirect(
            public_id,
            error=(
                "Das Rückgabedatum darf nicht "
                "in der Vergangenheit liegen."
            ),
        )

    # Durch isoformat() wird das Datum immer
    # als YYYY-MM-DD gespeichert.
    expected_return_at = (
        expected_return_date.isoformat()
    )

    try:
        with database_session() as connection:
            # Verhindert, dass zwei Personen das
            # Gerät gleichzeitig ausleihen.
            connection.execute(
                "BEGIN IMMEDIATE"
            )

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
                return device_redirect(
                    public_id,
                    error=reason,
                )

            connection.execute(
                """
                INSERT INTO loans (
                    device_id,
                    borrower_name,
                    expected_return_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    device["id"],
                    borrower_name,
                    expected_return_at,
                ),
            )

    except sqlite3.IntegrityError:
        return device_redirect(
            public_id,
            error=(
                "Das Gerät wurde gerade von "
                "jemand anderem ausgeliehen."
            ),
        )

    return device_redirect(
        public_id,
        message=(
            "Ausleihe erfolgreich gespeichert."
        ),
    )


@router.post("/{public_id}/return")
async def return_device(
    public_id: str,
    request: Request,
):
    """
    Beendet die aktive Ausleihe eines Geräts.
    """

    form = dict(await request.form())

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    with database_session() as connection:
        result = connection.execute(
            """
            UPDATE loans

            SET returned_at = CURRENT_TIMESTAMP

            WHERE device_id = (
                SELECT id
                FROM devices
                WHERE public_id = ?
            )

            AND returned_at IS NULL
            """,
            (public_id,),
        )

        return_was_saved = result.rowcount > 0

    if return_was_saved:
        message = (
            "Rückgabe erfolgreich gespeichert."
        )
    else:
        message = (
            "Keine aktive Ausleihe gefunden."
        )

    return device_redirect(
        public_id,
        message=message,
    )