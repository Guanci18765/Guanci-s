from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import (
    HTTPSRedirectMiddleware,
)
from starlette.middleware.sessions import (
    SessionMiddleware,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent

# Die .env wird geladen, bevor Module importiert
# werden, die Umgebungsvariablen verwenden.
load_dotenv(
    PROJECT_DIR / ".env"
)


from app.database import (  # noqa: E402
    initialize_database,
    seed_demo_data,
)
from app.routes import (  # noqa: E402
    admin,
    auth,
    devices,
)
from app.security import (  # noqa: E402
    current_user,
    ensure_initial_admin,
)


@asynccontextmanager
async def lifespan(
    _: FastAPI,
):
    initialize_database()
    ensure_initial_admin()

    if (
        os.getenv(
            "SEED_DEMO_DATA",
            "false",
        ).lower()
        == "true"
    ):
        seed_demo_data()

    yield


app = FastAPI(
    title="Inventurprogramm",
    lifespan=lifespan,
)


app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SESSION_SECRET",
        "local-development-secret-change-me",
    ),
    same_site="lax",
    https_only=(
        os.getenv(
            "FORCE_HTTPS",
            "false",
        ).lower()
        == "true"
    ),
)


if (
    os.getenv(
        "FORCE_HTTPS",
        "false",
    ).lower()
    == "true"
):
    app.add_middleware(
        HTTPSRedirectMiddleware
    )


app.mount(
    "/static",
    StaticFiles(
        directory=APP_DIR / "static"
    ),
    name="static",
)


app.include_router(
    auth.router
)

app.include_router(
    admin.router
)

app.include_router(
    devices.router
)


@app.get(
    "/",
    include_in_schema=False,
)
def home(request: Request) -> RedirectResponse:
    user = current_user(request)

    if not user:
        target = "/login"
    elif user["role"] == "admin":
        target = "/admin/"
    else:
        target = "/account/"

    return RedirectResponse(url=target, status_code=302)
