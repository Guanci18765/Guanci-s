from __future__ import annotations

from datetime import datetime


def format_date_de(
    value: str | None,
) -> str:
    """
    Formatiert ein gespeichertes ISO-Datum für die
    deutsche Anzeige.

    Beispiele:

    2026-08-25
    wird zu:
    25.08.2026

    2026-08-25 14:35:20
    wird zu:
    25.08.2026 14:35
    """

    if not value:
        return "Unbekannt"

    cleaned_value = value.strip()

    try:
        parsed_value = datetime.fromisoformat(
            cleaned_value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return cleaned_value

    contains_time = (
        " " in cleaned_value
        or "T" in cleaned_value
    )

    if contains_time:
        return parsed_value.strftime(
            "%d.%m.%Y %H:%M"
        )

    return parsed_value.strftime(
        "%d.%m.%Y"
    )


def parse_date_de(
    value: str | None,
) -> str | None:
    """
    Wandelt ein deutsches Eingabedatum in das
    ISO-Format für SQLite um.

    Beispiel:

    25.08.2026
    wird zu:
    2026-08-25
    """

    if not value:
        return None

    cleaned_value = value.strip()

    if not cleaned_value:
        return None

    try:
        parsed_value = datetime.strptime(
            cleaned_value,
            "%d.%m.%Y",
        )

    except ValueError as error:
        raise ValueError(
            "Das Datum muss im Format "
            "TT.MM.JJJJ eingegeben werden."
        ) from error

    return parsed_value.strftime(
        "%Y-%m-%d"
    )