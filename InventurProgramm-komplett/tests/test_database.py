import os
import tempfile
import unittest
from pathlib import Path


class DatabaseTest(unittest.TestCase):
    def test_schema_and_active_loan_constraint(self):
        with tempfile.TemporaryDirectory() as directory:
            os.environ["DATABASE_PATH"] = str(Path(directory) / "test.db")
            import importlib
            import app.database as database

            importlib.reload(database)
            database.initialize_database()
            database.seed_demo_data()

            with database.database_session() as connection:
                device = connection.execute("SELECT * FROM devices LIMIT 1").fetchone()
                self.assertIsNotNone(device)
                connection.execute(
                    "INSERT INTO loans (device_id, borrower_name) VALUES (?, ?)",
                    (device["id"], "Test User"),
                )

            with self.assertRaises(Exception):
                with database.database_session() as connection:
                    connection.execute(
                        "INSERT INTO loans (device_id, borrower_name) VALUES (?, ?)",
                        (device["id"], "Second User"),
                    )


if __name__ == "__main__":
    unittest.main()
