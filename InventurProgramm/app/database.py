import sqlite3
import pathlib

PROJECT_DIR = pathlib.Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_DIR / "inventory.db"

# Verbindung
def get_connection() -> sqlite3.Connection:                  #Verbindung öffnen
    connection = sqlite3.connect(DATABASE_PATH)              #Verbindung definieren

    connection.row_factory = sqlite3.Row                    
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database() -> None:
    connection = get_connection()

    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS devices(
            id INTEGER PRIMARY KEY,
            public_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL UNIQUE,
            device_type TEXT NOT NULL,
            operating_system TEXT,
            latest_update_date TEXT,
            setup_complete INTEGER NOT NULL DEFAULT 0
                Check(setup_complete IN (0,1)),
            location TEXT DEFAULT 'Büro',
            condition TEXT NOT NULL DEFAULT 'ready'
                CHECK (condition IN ('ready', 'service', 'defective'))
            )

            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY,
            device_id INTEGER NOT NULL,
            borrower_name TEXT NOT NULL,
            checked_out_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            returned_at TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(id)
            )

            """
)
        connection.commit()
    finally:
        connection.close()