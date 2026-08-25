from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.security import (
    csrf_token,
    is_kiosk,
    kiosk_pin_is_valid,
    validate_csrf,
)


router = APIRouter(
    prefix="/kiosk",
)

templates = Jinja2Templates(
    directory=(
        Path(__file__).resolve().parent.parent
        / "templates"
    )
)


def kiosk_login_redirect() -> RedirectResponse:
    """Leitet zur Kiosk-Anmeldung weiter."""

    return RedirectResponse(
        url="/kiosk/login",
        status_code=303,
    )


@router.get("/login")
def kiosk_login_page(
    request: Request,
):
    """Zeigt die Kiosk-Anmeldung an."""

    if is_kiosk(request):
        return RedirectResponse(
            url="/kiosk/",
            status_code=302,
        )

    return templates.TemplateResponse(
        request,
        "kiosk/login.html",
        {
            "csrf_token": csrf_token(request),
            "error": None,
        },
    )


@router.post("/login")
async def kiosk_login(
    request: Request,
):
    """Meldet den Browser als Kiosk-Gerät an."""

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    pin = form.get(
        "pin",
        "",
    ).strip()

    if not kiosk_pin_is_valid(pin):
        return templates.TemplateResponse(
            request,
            "kiosk/login.html",
            {
                "csrf_token": csrf_token(request),
                "error": "Der Kiosk-PIN ist falsch.",
            },
            status_code=401,
        )

    # Der Browser erhält eine signierte Sitzung.
    request.session["is_kiosk"] = True

    # Ein Kiosk-Browser soll nicht gleichzeitig
    # als Administrator angemeldet bleiben.
    request.session.pop(
        "is_admin",
        None,
    )

    return RedirectResponse(
        url="/kiosk/",
        status_code=303,
    )


@router.get("/")
def kiosk_home(
    request: Request,
):
    """Zeigt den aktiven Kiosk-Modus an."""

    if not is_kiosk(request):
        return kiosk_login_redirect()

    return templates.TemplateResponse(
        request,
        "kiosk/index.html",
        {
            "csrf_token": csrf_token(request),
        },
    )


@router.post("/logout")
async def kiosk_logout(
    request: Request,
):
    """Beendet den Kiosk-Modus dieses Browsers."""

    form = dict(
        await request.form()
    )

    validate_csrf(
        request,
        form.get("csrf_token"),
    )

    request.session.pop(
        "is_kiosk",
        None,
    )

    return RedirectResponse(
        url="/kiosk/login",
        status_code=303,
    )