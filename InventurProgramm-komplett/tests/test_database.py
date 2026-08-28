from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path


class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = str(
            Path(self.temporary_directory.name) / "test.db"
        )

        import app.database as database

        self.database = importlib.reload(database)
        self.database.initialize_database()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_current_device_schema(self) -> None:
        connection = self.database.get_connection()

        try:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(devices)"
                ).fetchall()
            }
        finally:
            connection.close()

        self.assertTrue(
            {
                "serial_number",
                "last_technical_inspection_date",
                "purchase_date",
                "technical_details",
            }.issubset(columns)
        )

    def test_users_have_session_version(self) -> None:
        connection = self.database.get_connection()

        try:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(users)"
                ).fetchall()
            }
        finally:
            connection.close()

        self.assertIn("session_version", columns)

    def test_only_one_active_loan_per_device(self) -> None:
        with self.database.database_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO devices (
                    public_id,
                    name,
                    device_type,
                    setup_complete
                )
                VALUES ('test-device', 'Testgerät', 'PC', 1)
                """
            )
            device_id = cursor.lastrowid

            connection.execute(
                """
                INSERT INTO loans (device_id, borrower_name)
                VALUES (?, 'Test User')
                """,
                (device_id,),
            )

        with self.assertRaises(Exception):
            with self.database.database_session() as connection:
                connection.execute(
                    """
                    INSERT INTO loans (device_id, borrower_name)
                    VALUES (?, 'Second User')
                    """,
                    (device_id,),
                )


if __name__ == "__main__":
    unittest.main()
