from __future__ import annotations

from app.formatting import format_date_de

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import database_session, get_connection
from app.security import csrf_token, validate_csrf


router = APIRouter(prefix="/device")
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
templates.env.filters["date_de"] = format_date_de

def get_public_device(public_id: str):
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT d.*, l.id AS active_loan_id
            FROM devices AS d
            LEFT JOIN loans AS l
              ON l.device_id = d.id AND l.returned_at IS NULL
            WHERE d.public_id = ?
            """,
            (public_id,),
        ).fetchone()
    finally:
        connection.close()


def block_reason(device) -> str | None:
    # Eine bestehende Ausleihe darf noch zurückgegeben werden
    if device["active_loan_id"]:
        return "Dieses Gerät ist derzeit ausgeliehen."

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
def device_page(public_id: str, request: Request, message: str | None = None, error: str | None = None):
    device = get_public_device(public_id)
    if not device:
        return templates.TemplateResponse(request, "not_found.html", status_code=404)
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
async def borrow_device(public_id: str, request: Request):
    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))
    borrower_name = form.get("borrower_name", "").strip()
    if len(borrower_name) < 2 or len(borrower_name) > 100:
        return RedirectResponse(
            f"/device/{public_id}?error=Bitte+gib+deinen+vollständigen+Namen+ein.", status_code=303
        )

    try:
        with database_session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                """
                SELECT d.*, l.id AS active_loan_id
                FROM devices AS d
                LEFT JOIN loans AS l
                  ON l.device_id = d.id AND l.returned_at IS NULL
                WHERE d.public_id = ?
                """,
                (public_id,),
            ).fetchone()
            if not device:
                return RedirectResponse(f"/device/{public_id}", status_code=303)
            reason = block_reason(device)
            if reason:
                return RedirectResponse(f"/device/{public_id}?error={reason.replace(' ', '+')}", status_code=303)
            connection.execute(
                "INSERT INTO loans (device_id, borrower_name) VALUES (?, ?)",
                (device["id"], borrower_name),
            )
    except sqlite3.IntegrityError:
        return RedirectResponse(
            f"/device/{public_id}?error=Das+Gerät+wurde+gerade+von+jemand+anderem+ausgeliehen.",
            status_code=303,
        )
    return RedirectResponse(f"/device/{public_id}?message=Ausleihe+erfolgreich+gespeichert.", status_code=303)


@router.post("/{public_id}/return")
async def return_device(public_id: str, request: Request):
    form = dict(await request.form())
    validate_csrf(request, form.get("csrf_token"))
    with database_session() as connection:
        result = connection.execute(
            """
            UPDATE loans
            SET returned_at = CURRENT_TIMESTAMP
            WHERE device_id = (SELECT id FROM devices WHERE public_id = ?)
              AND returned_at IS NULL
            """,
            (public_id,),
        )
    message = "Rückgabe erfolgreich gespeichert." if result.rowcount else "Keine aktive Ausleihe gefunden."
    return RedirectResponse(f"/device/{public_id}?message={message.replace(' ', '+')}", status_code=303)

