from __future__ import annotations

import sqlite3

from app.config import DATABASE_PATH, DATABASE_URL
from app.db import connection, initialize


TABLES = [
    "users",
    "assignments",
    "recipients",
    "documents",
    "chunks",
    "attempts",
    "messages",
    "evidence",
]


def main() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    source = sqlite3.connect(DATABASE_PATH)
    source.row_factory = sqlite3.Row
    initialize()

    with connection() as target:
        assignment_count = target.execute("SELECT count(*) AS n FROM assignments").fetchone()["n"]
        attempt_count = target.execute("SELECT count(*) AS n FROM attempts").fetchone()["n"]
        document_count = target.execute("SELECT count(*) AS n FROM documents").fetchone()["n"]
        if assignment_count == 1 and attempt_count == 0 and document_count == 0:
            target.execute("DELETE FROM assignments")

        for table in TABLES:
            rows = [dict(row) for row in source.execute(f"SELECT * FROM {table}").fetchall()]
            if not rows:
                continue
            columns = list(rows[0])
            placeholders = ",".join("?" for _ in columns)
            statement = (
                f"INSERT INTO {table} ({','.join(columns)}) "
                f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            )
            target.executemany(statement, [tuple(row[column] for column in columns) for row in rows])

    source.close()

    with connection() as target:
        for table in TABLES:
            count = target.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            print(f"{table}={count}")


if __name__ == "__main__":
    main()
