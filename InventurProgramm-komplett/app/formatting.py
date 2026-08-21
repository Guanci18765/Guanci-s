from datetime import datetime


def format_date_de(value: str | None) -> str:
    """Formatiert ein Datum für die Anzeige als TT.MM.JJJJ."""

    if not value:
        return "Unbekannt"

    value = str(value).strip()

    possible_formats = (
        "%Y-%m-%d",
        "%d.%m.%Y",
    )

    for date_format in possible_formats:
        try:
            date = datetime.strptime(
                value,
                date_format,
            )

            return date.strftime("%d.%m.%Y")

        except ValueError:
            continue

    return value


def parse_date_de(value: str | None) -> str | None:
    """
    Prüft die Benutzereingabe und wandelt sie
    für SQLite in JJJJ-MM-TT um.
    """

    if not value:
        return None

    value = str(value).strip()

    possible_formats = (
        "%d.%m.%Y",
        "%Y-%m-%d",
    )

    for date_format in possible_formats:
        try:
            date = datetime.strptime(
                value,
                date_format,
            )

            return date.strftime("%Y-%m-%d")

        except ValueError:
            continue

    raise ValueError(
        "Das Update-Datum muss im Format "
        "TT.MM.JJJJ angegeben werden."
    )