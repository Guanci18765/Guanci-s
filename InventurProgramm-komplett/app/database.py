from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_DIR = Path(__file__).resolve().parent.parent

DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
        str(PROJECT_DIR / "inventory.db"),
    )
)


def get_connection() -> sqlite3.Connection:
    """
    Öffnet eine Verbindung zur SQLite-Datenbank.

    Der Aufrufer muss die Verbindung anschließend
    wieder schließen.
    """

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10,
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    connection.execute(
        "PRAGMA busy_timeout = 5000"
    )

    return connection


@contextmanager
def database_session() -> Iterator[sqlite3.Connection]:
    """
    Öffnet eine Datenbankverbindung.

    Bei Erfolg werden Änderungen gespeichert.
    Bei einem Fehler werden Änderungen zurückgesetzt.
    Die Verbindung wird immer geschlossen.
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


def get_column_names(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """
    Gibt die Namen aller Spalten einer Tabelle zurück.
    """

    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        column["name"]
        for column in columns
    }


def initialize_database() -> None:
    """
    Erstellt die Tabellen und ergänzt fehlende Spalten
    in einer bereits vorhandenen Datenbank.
    """

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
                    CHECK (
                        setup_complete IN (0, 1)
                    ),

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
                    CHECK (
                        is_active IN (0, 1)
                    ),

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                deleted_at TEXT,

                deletion_reason TEXT
            );


            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id INTEGER NOT NULL,

                borrower_name TEXT NOT NULL,

                checked_out_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                expected_return_at TEXT,

                is_permanent INTEGER NOT NULL DEFAULT 0
                    CHECK (
                        is_permanent IN (0, 1)
                    ),

                returned_at TEXT,

                overdue_notification_sent_at TEXT,

                FOREIGN KEY (device_id)
                    REFERENCES devices(id)
                    ON DELETE RESTRICT
            );
            """
        )

        device_columns = get_column_names(
            connection,
            "devices",
        )

        if "is_active" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (
                        is_active IN (0, 1)
                    )
                """
            )

        if "deleted_at" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN deleted_at TEXT
                """
            )

        if "deletion_reason" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN deletion_reason TEXT
                """
            )

        loan_columns = get_column_names(
            connection,
            "loans",
        )

        if "expected_return_at" not in loan_columns:
            connection.execute(
                """
                ALTER TABLE loans
                ADD COLUMN expected_return_at TEXT
                """
            )

        if "is_permanent" not in loan_columns:
            connection.execute(
                """
                ALTER TABLE loans
                ADD COLUMN is_permanent INTEGER NOT NULL DEFAULT 0
                    CHECK (
                        is_permanent IN (0, 1)
                    )
                """
            )

        if (
            "overdue_notification_sent_at"
            not in loan_columns
        ):
            connection.execute(
                """
                ALTER TABLE loans
                ADD COLUMN overdue_notification_sent_at TEXT
                """
            )

        connection.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                one_active_loan_per_device
            ON loans(device_id)
            WHERE returned_at IS NULL;


            CREATE INDEX IF NOT EXISTS
                loans_device_id_idx
            ON loans(device_id);


            CREATE INDEX IF NOT EXISTS
                active_loans_expected_return_idx
            ON loans(expected_return_at)
            WHERE returned_at IS NULL;


            CREATE INDEX IF NOT EXISTS
                devices_deleted_at_idx
            ON devices(deleted_at);
            """
        )


def seed_demo_data() -> None:
    """
    Fügt Beispieldaten nur ein, wenn SEED_DEMO_DATA=true
    gesetzt wurde und noch keine Geräte vorhanden sind.
    """

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