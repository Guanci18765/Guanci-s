from __future__ import annotations

import io
import os
import sqlite3
import uuid
from pathlib import Path

import qrcode
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.database import (
    database_session,
    get_connection,
)
from app.formatting import (
    format_date_de,
    parse_date_de,
)
from app.security import (
    admin_credentials_are_valid,
    csrf_token,
    is_admin,
    validate_csrf,
)


router = APIRouter(
    prefix="/admin"
)


templates = Jinja2Templates(
    directory=(
        Path(__file__).resolve().parent.parent
        / "templates"
    )
)


templates.env.filters["date_de"] = format_date_de


# ---------------------------------------------------------
# Zulässige Gerätetypen
# ---------------------------------------------------------
#
# Neue Gerätetypen werden ausschließlich hier eingetragen.
# Die Werte werden im Geräteformular und im Dashboardfilter
# verwendet.

DEVICE_TYPES: tuple[str, ...] = (
    "Handys",
    "PC",
    "Laptops",
    "Notebooks",
    "Tablets",
    "Kamera",
    "Messgeräte",
    "Werkzeug",
)


def login_redirect() -> RedirectResponse:
    """
    Leitet nicht angemeldete Benutzer zur
    Admin-Anmeldung weiter.
    """

    return RedirectResponse(
        "/admin/login",
        status_code=303,
    )


def render_device_form(
    request: Request,
    *,
    device,
    error: str | None,
    status_code: int = 200,
):
    """
    Rendert das Formular zum Erstellen oder
    Bearbeiten eines Gerätes.

    Die Gerätetypen werden zentral aus DEVICE_TYPES
    an das Template übergeben.
    """

    return templates.TemplateResponse(
        request,
        "admin/device_form.html",
        {
            "device": device,
            "device_types": DEVICE_TYPES,
            "error": error,
            "csrf_token": csrf_token(request),
        },
        status_code=status_code,
    )


def device_values(
    form: dict[str, str],
) -> tuple[
    str,
    str,
    str | None,
    str | None,
    int,
    str,
    str,
    int,
    int,
]:
    """
    Prüft und verarbeitet die Werte aus dem Geräteformular.

    Die Reihenfolge der zurückgegebenen Werte muss mit
    der Reihenfolge der Spalten in den INSERT- und
    UPDATE-Abfragen übereinstimmen.
    """

    name = form.get(
        "name",
        "",
    ).strip()

    device_type = form.get(
        "device_type",
        "",
    ).strip()

    operating_system = (
        form.get(
            "operating_system",
            "",
        ).strip()
        or None
    )

    latest_update_date = parse_date_de(
        form.get(
            "latest_update_date",
            "",
        ).strip()
    )

    setup_complete = (
        1
        if form.get("setup_complete") == "1"
        else 0
    )

    location = (
        form.get(
            "location",
            "",
        ).strip()
        or "Büro"
    )

    condition = form.get(
        "condition",
        "ready",
    )

    is_active = (
        1
        if form.get("is_active", "1") == "1"
        else 0
    )

    # Persönliche Geräte sind fest zugeordnet
    # und dürfen nicht über die öffentliche
    # QR-Seite ausgeliehen werden.
    is_personal_device = (
        1
        if form.get(
            "is_personal_device",
            "0",
        ) == "1"
        else 0
    )

    if not name:
        raise ValueError(
            "Der Gerätename ist ein Pflichtfeld."
        )

    if not DEVICE_TYPES:
        raise ValueError(
            "In admin.py wurden noch keine "
            "Gerätetypen eingetragen."
        )

    if device_type not in DEVICE_TYPES:
        raise ValueError(
            "Bitte wähle einen gültigen "
            "Gerätetyp aus."
        )

    if condition not in {
        "ready",
        "service",
        "defective",
    }:
        raise ValueError(
            "Der Gerätezustand ist ungültig."
        )

    return (
        name,
        device_type,
        operating_system,
        latest_update_date,
        setup_complete,
        location,
        condition,
        is_active,
        is_personal_device,
    )


# ---------------------------------------------------------
# Admin-Anmeldung
# ---------------------------------------------------------


@router.get("/login")
def login_page(request: Request):
    """
    Zeigt die Admin-Anmeldung an.
    """

    if is_admin(request):
        return RedirectResponse(
            "/admin/",
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "csrf_token": csrf_token(request),
            "error": None,
        },
    )


@router.post("/login")
async def login(request: Request):
    """
    Prüft die Admin-Zugangsdaten und erstellt
    bei Erfolg eine Admin-Sitzung.
    """

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    login_valid = admin_credentials_are_valid(
        form.get("username", ""),
        form.get("password", ""),
    )

    if not login_valid:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {
                "csrf_token": csrf_token(request),
                "error": (
                    "Benutzername oder Passwort "
                    "ist falsch."
                ),
            },
            status_code=401,
        )

    request.session["is_admin"] = True

    return RedirectResponse(
        "/admin/",
        status_code=303,
    )


@router.post("/logout")
async def logout(request: Request):
    """
    Beendet die aktuelle Admin-Sitzung.
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
        "/admin/login",
        status_code=303,
    )


# ---------------------------------------------------------
# Admin-Dashboard
# ---------------------------------------------------------


@router.get("/")
def dashboard(request: Request):
    """
    Lädt Geräte, Ausleihen, überfällige Ausleihen
    und archivierte Geräte für das Admin-Dashboard.
    """

    if not is_admin(request):
        return login_redirect()

    connection = get_connection()

    try:
        # Aktiver Gerätebestand inklusive einer
        # eventuell vorhandenen aktiven Ausleihe.
        devices = connection.execute(
            """
            SELECT
                d.*,

                l.borrower_name
                    AS active_borrower,

                l.checked_out_at,

                l.expected_return_at
                    AS active_expected_return_at,

                COALESCE(
                    l.is_permanent,
                    0
                ) AS active_is_permanent

            FROM devices AS d

            LEFT JOIN loans AS l
                ON l.device_id = d.id
                AND l.returned_at IS NULL

            WHERE d.deleted_at IS NULL

            ORDER BY
                d.name COLLATE NOCASE
            """
        ).fetchall()

        # Die zwölf zuletzt angelegten Ausleihen.
        loans = connection.execute(
            """
            SELECT
                l.*,
                d.name AS device_name

            FROM loans AS l

            JOIN devices AS d
                ON d.id = l.device_id

            WHERE d.deleted_at IS NULL

            ORDER BY
                l.checked_out_at DESC

            LIMIT 12
            """
        ).fetchall()

        # Eine Ausleihe ist überfällig, wenn:
        #
        # - sie noch nicht zurückgegeben wurde,
        # - sie nicht dauerhaft ist,
        # - ein Rückgabedatum vorhanden ist,
        # - das Rückgabedatum vor dem heutigen Tag liegt.
        overdue_loans = connection.execute(
            """
            SELECT
                l.id,
                l.device_id,
                l.borrower_name,
                l.checked_out_at,
                l.expected_return_at,

                d.name AS device_name,
                d.device_type,
                d.public_id,

                CAST(
                    JULIANDAY(
                        DATE(
                            'now',
                            'localtime'
                        )
                    )
                    -
                    JULIANDAY(
                        DATE(
                            l.expected_return_at
                        )
                    )
                    AS INTEGER
                ) AS overdue_days

            FROM loans AS l

            JOIN devices AS d
                ON d.id = l.device_id

            WHERE l.returned_at IS NULL

              AND COALESCE(
                    l.is_permanent,
                    0
                  ) = 0

              AND l.expected_return_at IS NOT NULL

              AND DATE(
                    l.expected_return_at
                  )
                  <
                  DATE(
                      'now',
                      'localtime'
                  )

              AND d.deleted_at IS NULL

            ORDER BY
                DATE(
                    l.expected_return_at
                ) ASC,

                d.name COLLATE NOCASE
            """
        ).fetchall()

        # Archivierte Geräte bleiben in der Datenbank.
        # Dadurch bleibt ihr Ausleihverlauf erhalten.
        deleted_devices = connection.execute(
            """
            SELECT
                d.*,

                STRFTIME(
                    '%d.%m.%Y %H:%M',
                    d.deleted_at,
                    'localtime'
                ) AS deleted_at_de,

                COUNT(
                    l.id
                ) AS loan_count

            FROM devices AS d

            LEFT JOIN loans AS l
                ON l.device_id = d.id

            WHERE d.deleted_at IS NOT NULL

            GROUP BY
                d.id

            ORDER BY
                d.deleted_at DESC
            """
        ).fetchall()

    finally:
        connection.close()

    # Persönliche Geräte gelten als gesperrt,
    # weil sie nicht für die allgemeine Ausleihe
    # zur Verfügung stehen.
    counts = {
        "all": len(devices),

        "available": sum(
            1
            for device in devices
            if (
                device["is_active"]
                and not device["active_borrower"]
                and device["condition"] == "ready"
                and device["setup_complete"]
                and not device["is_personal_device"]
            )
        ),

        "loaned": sum(
            1
            for device in devices
            if device["active_borrower"]
        ),

        "blocked": sum(
            1
            for device in devices
            if (
                not device["active_borrower"]
                and (
                    not device["is_active"]
                    or device["is_personal_device"]
                    or device["condition"] != "ready"
                    or not device["setup_complete"]
                )
            )
        ),

        "overdue": len(
            overdue_loans
        ),

        "deleted": len(
            deleted_devices
        ),
    }

    # Nur tatsächlich verwendete Gerätetypen
    # werden im Dashboardfilter angezeigt.
    available_device_types = sorted(
        {
            device["device_type"]
            for device in devices
        },
        key=str.casefold,
    )

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "devices": devices,
            "loans": loans,
            "overdue_loans": overdue_loans,
            "deleted_devices": deleted_devices,
            "device_types": available_device_types,
            "counts": counts,
            "csrf_token": csrf_token(request),
        },
    )


# ---------------------------------------------------------
# Neues Gerät
# ---------------------------------------------------------


@router.get("/devices/new")
def new_device_page(request: Request):
    """
    Zeigt das Formular zum Anlegen eines Gerätes an.
    """

    if not is_admin(request):
        return login_redirect()

    return render_device_form(
        request,
        device=None,
        error=None,
    )


@router.post("/devices/new")
async def create_device(request: Request):
    """
    Prüft das Formular und legt ein neues Gerät an.
    """

    if not is_admin(request):
        return login_redirect()

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    try:
        values = device_values(
            form
        )

        with database_session() as connection:
            connection.execute(
                """
                INSERT INTO devices (
                    public_id,
                    name,
                    device_type,
                    operating_system,
                    latest_update_date,
                    setup_complete,
                    location,
                    condition,
                    is_active,
                    is_personal_device
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    str(
                        uuid.uuid4()
                    ),
                    *values,
                ),
            )

    except (
        ValueError,
        sqlite3.IntegrityError,
    ) as error:
        message = (
            str(error)
            if isinstance(
                error,
                ValueError,
            )
            else (
                "Der Gerätename existiert bereits."
            )
        )

        return render_device_form(
            request,
            device=form,
            error=message,
            status_code=400,
        )

    return RedirectResponse(
        "/admin/",
        status_code=303,
    )


# ---------------------------------------------------------
# Gerät bearbeiten
# ---------------------------------------------------------


@router.get("/devices/{public_id}/edit")
def edit_device_page(
    public_id: str,
    request: Request,
):
    """
    Zeigt das Bearbeitungsformular eines Gerätes an.
    """

    if not is_admin(request):
        return login_redirect()

    connection = get_connection()

    try:
        device = connection.execute(
            """
            SELECT *
            FROM devices
            WHERE public_id = ?
              AND deleted_at IS NULL
            """,
            (public_id,),
        ).fetchone()

    finally:
        connection.close()

    if not device:
        return RedirectResponse(
            "/admin/",
            status_code=303,
        )

    return render_device_form(
        request,
        device=device,
        error=None,
    )


@router.post("/devices/{public_id}/edit")
async def update_device(
    public_id: str,
    request: Request,
):
    """
    Prüft und speichert Änderungen an einem Gerät.
    """

    if not is_admin(request):
        return login_redirect()

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    try:
        values = device_values(
            form
        )

        with database_session() as connection:
            result = connection.execute(
                """
                UPDATE devices

                SET
                    name = ?,
                    device_type = ?,
                    operating_system = ?,
                    latest_update_date = ?,
                    setup_complete = ?,
                    location = ?,
                    condition = ?,
                    is_active = ?,
                    is_personal_device = ?

                WHERE public_id = ?
                  AND deleted_at IS NULL
                """,
                (
                    *values,
                    public_id,
                ),
            )

            if result.rowcount == 0:
                raise ValueError(
                    "Gerät wurde nicht gefunden."
                )

    except (
        ValueError,
        sqlite3.IntegrityError,
    ) as error:
        message = (
            str(error)
            if isinstance(
                error,
                ValueError,
            )
            else (
                "Der Gerätename existiert bereits."
            )
        )

        # Das Formular benötigt die public_id,
        # damit es weiterhin als Bearbeitungsseite
        # und nicht als neues Gerät dargestellt wird.
        form["public_id"] = public_id

        return render_device_form(
            request,
            device=form,
            error=message,
            status_code=400,
        )

    return RedirectResponse(
        "/admin/",
        status_code=303,
    )


# ---------------------------------------------------------
# Gerät archivieren
# ---------------------------------------------------------


@router.post("/devices/{public_id}/delete")
async def delete_device(
    public_id: str,
    request: Request,
):
    """
    Archiviert ein Gerät.

    Das Gerät und sein Ausleihverlauf werden nicht
    physisch aus der Datenbank gelöscht.
    """

    if not is_admin(request):
        return login_redirect()

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    connection = get_connection()

    try:
        device = connection.execute(
            """
            SELECT *
            FROM devices
            WHERE public_id = ?
              AND deleted_at IS NULL
            """,
            (public_id,),
        ).fetchone()

    finally:
        connection.close()

    if not device:
        return RedirectResponse(
            "/admin/",
            status_code=303,
        )

    confirmation = form.get(
        "confirmation",
        "",
    ).strip()

    deletion_reason = form.get(
        "deletion_reason",
        "",
    ).strip()

    if confirmation != "ARCHIVIEREN":
        return render_device_form(
            request,
            device=device,
            error=(
                "Gib zur Bestätigung das Wort "
                "ARCHIVIEREN vollständig ein."
            ),
            status_code=400,
        )

    if len(deletion_reason) < 3:
        return render_device_form(
            request,
            device=device,
            error=(
                "Bitte gib einen nachvollziehbaren "
                "Archivierungsgrund ein."
            ),
            status_code=400,
        )

    if len(deletion_reason) > 500:
        return render_device_form(
            request,
            device=device,
            error=(
                "Der Archivierungsgrund darf höchstens "
                "500 Zeichen lang sein."
            ),
            status_code=400,
        )

    with database_session() as connection:
        # Ein aktuell ausgeliehenes Gerät muss vor
        # der Archivierung zurückgegeben werden.
        active_loan = connection.execute(
            """
            SELECT id
            FROM loans
            WHERE device_id = ?
              AND returned_at IS NULL
            """,
            (device["id"],),
        ).fetchone()

        if active_loan:
            return render_device_form(
                request,
                device=device,
                error=(
                    "Das Gerät ist noch ausgeliehen. "
                    "Es muss zuerst zurückgegeben werden."
                ),
                status_code=409,
            )

        connection.execute(
            """
            UPDATE devices

            SET
                is_active = 0,
                deleted_at = CURRENT_TIMESTAMP,
                deletion_reason = ?

            WHERE id = ?
              AND deleted_at IS NULL
            """,
            (
                deletion_reason,
                device["id"],
            ),
        )

    return RedirectResponse(
        "/admin/",
        status_code=303,
    )


# ---------------------------------------------------------
# QR-Code
# ---------------------------------------------------------


@router.get("/devices/{public_id}/qr.png")
def device_qr(
    public_id: str,
    request: Request,
):
    """
    Erstellt den QR-Code für die öffentliche
    Geräteseite.

    PUBLIC_BASE_URL muss eine Adresse enthalten,
    die das Kioskgerät im Netzwerk erreichen kann.
    """

    if not is_admin(request):
        return login_redirect()

    connection = get_connection()

    try:
        device_exists = connection.execute(
            """
            SELECT 1
            FROM devices
            WHERE public_id = ?
              AND deleted_at IS NULL
            """,
            (public_id,),
        ).fetchone()

    finally:
        connection.close()

    if not device_exists:
        return Response(
            status_code=404
        )

    base_url = os.getenv(
        "PUBLIC_BASE_URL",
        str(request.base_url),
    ).rstrip("/")

    device_url = (
        f"{base_url}/device/{public_id}"
    )

    image = qrcode.make(
        device_url
    )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG",
    )

    return Response(
        buffer.getvalue(),
        media_type="image/png",
    )