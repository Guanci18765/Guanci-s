from __future__ import annotations

import os
import sqlite3
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

    Die aufrufende Funktion muss die Verbindung entweder
    selbst schließen oder database_session() verwenden.
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
    Verwaltet eine Datenbankverbindung automatisch.

    Bei Erfolg werden Änderungen gespeichert.
    Bei Fehlern werden Änderungen zurückgesetzt.
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

    Diese Funktion wird für einfache Migrationen
    vorhandener SQLite-Datenbanken verwendet.
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
    Erstellt Tabellen und ergänzt fehlende Spalten.

    Vorhandene Daten bleiben bei den Migrationen erhalten.
    """

    with database_session() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                username TEXT NOT NULL
                    COLLATE NOCASE
                    UNIQUE,

                full_name TEXT NOT NULL,

                password_hash TEXT NOT NULL,

                role TEXT NOT NULL DEFAULT 'user'
                    CHECK (
                        role IN ('user', 'admin')
                    ),

                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (
                        is_active IN (0, 1)
                    ),

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            );


            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                public_id TEXT NOT NULL UNIQUE,

                name TEXT NOT NULL UNIQUE,

                device_type TEXT NOT NULL,

                is_personal_device INTEGER NOT NULL DEFAULT 0
                    CHECK (
                        is_personal_device IN (0, 1)
                    ),

                operating_system TEXT,

                latest_update_date TEXT,

                purchase_date TEXT,

                technical_details TEXT,

                serial_number TEXT,

                last_technical_inspection_date TEXT,

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

                user_id INTEGER,

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
                    ON DELETE RESTRICT,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE RESTRICT
            );
            """
        )

        # -------------------------------------------------
        # Migrationen für devices
        # -------------------------------------------------

        device_columns = get_column_names(
            connection,
            "devices",
        )

        if "is_personal_device" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN is_personal_device
                    INTEGER NOT NULL DEFAULT 0
                    CHECK (
                        is_personal_device IN (0, 1)
                    )
                """
            )

        if "purchase_date" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN purchase_date TEXT
                """
            )

        if "technical_details" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN technical_details TEXT
                """
            )

        if "is_active" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN is_active
                    INTEGER NOT NULL DEFAULT 1
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

        # -------------------------------------------------
        # Migrationen für loans
        # -------------------------------------------------

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
                ADD COLUMN is_permanent
                    INTEGER NOT NULL DEFAULT 0
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

        if "serial_number" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN serial_number TEXT
                """
            )

        if (
            "last_technical_inspection_date"
            not in device_columns
        ):
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN last_technical_inspection_date TEXT
                """
            )

        if "user_id" not in loan_columns:
            # Alte Ausleihen bleiben gültig. Bei ihnen ist
            # user_id zunächst NULL; neue Ausleihen werden
            # immer mit einem Benutzerkonto verknüpft.
            connection.execute(
                """
                ALTER TABLE loans
                ADD COLUMN user_id INTEGER
                    REFERENCES users(id)
                    ON DELETE RESTRICT
                """
            )

        # -------------------------------------------------
        # Indizes
        # -------------------------------------------------

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
                loans_user_id_idx
            ON loans(user_id);


            CREATE INDEX IF NOT EXISTS
                users_role_active_idx
            ON users(role, is_active);


            CREATE INDEX IF NOT EXISTS
                active_loans_expected_return_idx
            ON loans(expected_return_at)
            WHERE
                returned_at IS NULL
                AND is_permanent = 0;


            CREATE INDEX IF NOT EXISTS
                archived_devices_idx
            ON devices(deleted_at)
            WHERE deleted_at IS NOT NULL;


            CREATE INDEX IF NOT EXISTS
                devices_serial_number_idx
            ON devices(serial_number)
            WHERE serial_number IS NOT NULL;
            """
        )


def seed_demo_data() -> None:
    """
    Bleibt für die Kompatibilität mit main.py vorhanden.

    Es werden bewusst keine Demogeräte angelegt.
    """

    return
