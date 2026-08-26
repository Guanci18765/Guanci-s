from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


# Das Hauptverzeichnis des Projekts.
PROJECT_DIR = Path(__file__).resolve().parent.parent


# Der Datenbankpfad kann über die Umgebungsvariable
# DATABASE_PATH geändert werden.
#
# Wenn DATABASE_PATH nicht gesetzt ist, wird inventory.db
# im Hauptverzeichnis des Projekts verwendet.
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

    # Abfrageergebnisse können dadurch über Spaltennamen
    # angesprochen werden, zum Beispiel device["name"].
    connection.row_factory = sqlite3.Row

    # Aktiviert die Überprüfung von Fremdschlüsseln.
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    # SQLite wartet bei einer kurzfristig gesperrten
    # Datenbank bis zu fünf Sekunden.
    connection.execute(
        "PRAGMA busy_timeout = 5000"
    )

    return connection


@contextmanager
def database_session() -> Iterator[sqlite3.Connection]:
    """
    Verwaltet eine Datenbankverbindung automatisch.

    Bei erfolgreicher Ausführung:
        Änderungen werden gespeichert.

    Bei einem Fehler:
        Änderungen werden zurückgesetzt.

    Am Ende:
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

    Die Funktion wird für einfache Datenbankmigrationen
    beim Programmstart verwendet.
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
    Erstellt die benötigten Tabellen und Indizes.

    Bereits vorhandene Datenbanken werden um fehlende
    Spalten ergänzt. Vorhandene Daten bleiben dabei erhalten.
    """

    with database_session() as connection:
        connection.executescript(
            """
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

        # -------------------------------------------------
        # Migrationen für die Gerätetabelle
        # -------------------------------------------------

        device_columns = get_column_names(
            connection,
            "devices",
        )

        # Kennzeichnet Geräte, die einer Person dauerhaft
        # zugeordnet werden dürfen.
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

        # Alte Datenbanken besitzen möglicherweise noch
        # keinen eigenen Aktivstatus.
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

        # deleted_at wird für das Gerätearchiv verwendet.
        # Archivierte Geräte bleiben in der Datenbank und
        # behalten dadurch ihren Ausleihverlauf.
        if "deleted_at" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN deleted_at TEXT
                """
            )

        # Begründung, warum ein Gerät archiviert wurde.
        if "deletion_reason" not in device_columns:
            connection.execute(
                """
                ALTER TABLE devices
                ADD COLUMN deletion_reason TEXT
                """
            )

        # -------------------------------------------------
        # Migrationen für die Ausleihtabelle
        # -------------------------------------------------

        loan_columns = get_column_names(
            connection,
            "loans",
        )

        # Geplantes Rückgabedatum einer normalen Ausleihe.
        if "expected_return_at" not in loan_columns:
            connection.execute(
                """
                ALTER TABLE loans
                ADD COLUMN expected_return_at TEXT
                """
            )

        # Speichert, ob eine Ausleihe dauerhaft angelegt wurde.
        # Dauerhafte Ausleihen benötigen kein Rückgabedatum.
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

        # Diese Spalte bleibt für eine mögliche spätere
        # E-Mail-Benachrichtigung erhalten.
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

        # -------------------------------------------------
        # Datenbankindizes
        # -------------------------------------------------

        connection.executescript(
            """
            -- Verhindert, dass dasselbe Gerät gleichzeitig
            -- mehrfach aktiv ausgeliehen wird.
            CREATE UNIQUE INDEX IF NOT EXISTS
                one_active_loan_per_device
            ON loans(device_id)
            WHERE returned_at IS NULL;


            -- Beschleunigt die Suche nach allen Ausleihen
            -- eines bestimmten Geräts.
            CREATE INDEX IF NOT EXISTS
                loans_device_id_idx
            ON loans(device_id);


            -- Beschleunigt die Suche nach überfälligen
            -- normalen Ausleihen.
            CREATE INDEX IF NOT EXISTS
                active_loans_expected_return_idx
            ON loans(expected_return_at)
            WHERE
                returned_at IS NULL
                AND is_permanent = 0;


            -- Beschleunigt das Laden des Gerätearchivs.
            CREATE INDEX IF NOT EXISTS
                archived_devices_idx
            ON devices(deleted_at)
            WHERE deleted_at IS NOT NULL;
            """
        )


def seed_demo_data() -> None:
    """
    Aus Kompatibilitätsgründen bleibt die Funktion vorhanden.

    Es werden bewusst keine Demogeräte mehr angelegt.
    Dadurch funktioniert ein eventuell noch vorhandener Import
    in main.py weiterhin, ohne Beispieldaten einzufügen.
    """

    return