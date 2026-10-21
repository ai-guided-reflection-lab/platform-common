"""Run against PostgreSQL with TEST_DATABASE_URL; all test data is temporary."""
import os
from pathlib import Path
import unittest

import psycopg

MIGRATIONS = Path(__file__).resolve().parents[1] / "platform_app" / "migrations"
TOOLS = ("socratic", "reflections", "student-agent", "self-directed-learning", "debate", "aiducate")


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL")
class MigrationCompatibilityTests(unittest.TestCase):
    def test_upgrade_preserves_assignments_and_retired_integration_data(self):
        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
            # Temporary tables shadow real tables and disappear on disconnect.
            conn.execute("CREATE TEMP TABLE assignments_platform (id integer PRIMARY KEY, tool text)")
            conn.execute("CREATE TEMP TABLE lti_launch_states_platform (state_hash text)")
            conn.execute("INSERT INTO lti_launch_states_platform VALUES ('historical-state')")
            for index, tool in enumerate((*TOOLS, None)):
                conn.execute("INSERT INTO assignments_platform VALUES (%s, %s)", (index, tool))
            before = conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall()
            for name in ("004_debate.sql", "007_activity_choices.sql", "012_remove_lti13.sql"):
                conn.execute((MIGRATIONS / name).read_text())
                self.assertEqual(conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall(), before)
            self.assertEqual(conn.execute("SELECT * FROM lti_launch_states_platform").fetchall(), [("historical-state",)])
            # Re-running the constraint migration is safe and still rejects typos.
            conn.execute((MIGRATIONS / "004_debate.sql").read_text())
            with self.assertRaises(psycopg.errors.CheckViolation):
                with conn.transaction():
                    conn.execute("INSERT INTO assignments_platform VALUES (99, 'unknown-tool')")
            self.assertEqual(conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall(), before)
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
