from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", PROJECT_DIR / "inventory.db")
)


def get_connection() -> sqlite3.Connection:
    """Öffnet eine Verbindung zur SQLite-Datenbank."""

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10,
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    return connection


@contextmanager
def database_session() -> Iterator[sqlite3.Connection]:
    """
    Öffnet eine Datenbankverbindung.

    Bei Erfolg:
        Änderungen werden gespeichert.

    Bei einem Fehler:
        Änderungen werden zurückgesetzt.

    Am Ende:
        Verbindung wird immer geschlossen.
    """

    connection = get_connection()

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def initialize_database() -> None:
    """Erstellt die benötigten Tabellen und aktualisiert ältere Tabellen."""

    with database_session() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                public_id TEXT NOT NULL UNIQUE,

                name TEXT NOT NULL UNIQUE,

                device_type TEXT NOT NULL,

                operating_system TEXT,

                latest_update_date TEXT,

                setup_complete INTEGER NOT NULL DEFAULT 0
                    CHECK (setup_complete IN (0, 1)),

                location TEXT NOT NULL DEFAULT 'Büro',

                condition TEXT NOT NULL DEFAULT 'ready'
                    CHECK (
                        condition IN (
                            'ready',
                            'service',
                            'defective'
                        )
                    ),

                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1)),

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );


            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id INTEGER NOT NULL,

                borrower_name TEXT NOT NULL,

                checked_out_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                returned_at TEXT,

                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE RESTRICT
            );


            CREATE UNIQUE INDEX IF NOT EXISTS
                one_active_loan_per_device
            ON loans(device_id)
            WHERE returned_at IS NULL;


            CREATE INDEX IF NOT EXISTS
                loans_device_id_idx
            ON loans(device_id);
            """
        )

        # Prüfen, ob die bestehende Tabelle bereits is_active besitzt
        columns = connection.execute(
            """
            PRAGMA table_info(devices)
            """
        ).fetchall()

        column_names = {
            column["name"] for column in columns
        }

        # Bestehende Datenbank um is_active erweitern
        if "is_active" not in column_names:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1))
                """
            )


def seed_demo_data() -> None:
    """Fügt Beispieldaten ein, wenn noch keine Geräte existieren."""

    with database_session() as connection:
        device_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM devices
            """
        ).fetchone()[0]

        if device_count > 0:
            return

        devices = [
            (
                str(uuid.uuid4()),
                "MacBook Pro 14 – Design",
                "Laptop",
                "macOS 15.6",
                "2026-08-18",
                1,
                "Berlin · Schrank A",
                "ready",
                1,
            ),
            (
                str(uuid.uuid4()),
                "iPad Air – Sales 02",
                "Tablet",
                "iPadOS 18.5",
                "2026-08-12",
                1,
                "Berlin · Ausgabe",
                "ready",
                1,
            ),
            (
                str(uuid.uuid4()),
                "iPhone 15 – Event",
                "Smartphone",
                "iOS 18.5",
                "2026-07-30",
                0,
                "Berlin · IT-Service",
                "service",
                1,
            ),
        ]

        connection.executemany(
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
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            devices,
        )