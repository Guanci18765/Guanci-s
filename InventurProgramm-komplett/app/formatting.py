from __future__ import annotations

from datetime import date, datetime


def format_date_de(value: object) -> str:
    """Formatiert ISO-Datumswerte für die deutsche Anzeige."""

    if value is None:
        return "Nicht angegeben"

    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")

    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")

    text = str(value).strip()

    if not text:
        return "Nicht angegeben"

    try:
        return datetime.strptime(
            text,
            "%d.%m.%Y",
        ).strftime("%d.%m.%Y")
    except ValueError:
        pass

    try:
        return date.fromisoformat(
            text[:10]
        ).strftime("%d.%m.%Y")
    except ValueError:
        return text


def parse_date_de(value: str | None) -> str | None:
    """Wandelt TT.MM.JJJJ in das SQLite-Format JJJJ-MM-TT um."""

    text = (value or "").strip()

    if not text:
        return None

    try:
        return datetime.strptime(
            text,
            "%d.%m.%Y",
        ).date().isoformat()
    except ValueError:
        pass

    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ValueError(
            "Bitte gib ein gültiges Datum im Format "
            "TT.MM.JJJJ ein."
        ) from error
