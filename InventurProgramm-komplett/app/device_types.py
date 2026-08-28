from __future__ import annotations


IT_DEVICE_TYPES: tuple[str, ...] = (
    "Handys",
    "PC",
    "Laptops",
    "Notebooks",
    "Tablets",
)


INSPECTION_DEVICE_TYPES: tuple[str, ...] = (
    "Kamera",
    "Messgeräte",
    "Werkzeug",
)


DEVICE_TYPES: tuple[str, ...] = (
    *IT_DEVICE_TYPES,
    *INSPECTION_DEVICE_TYPES,
)


def device_requires_setup(device_type: str) -> bool:
    """Nur IT-Geräte benötigen den Status 'Setup abgeschlossen'."""

    return device_type in IT_DEVICE_TYPES


def device_is_configured(
    device_type: str,
    setup_complete: int | bool,
) -> bool:
    """Prüft, ob der typabhängige Einrichtungsstatus erfüllt ist."""

    return (
        not device_requires_setup(device_type)
        or bool(setup_complete)
    )
