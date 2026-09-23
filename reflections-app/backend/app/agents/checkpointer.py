"""LangGraph Postgres saver with ClubALL's Reflections table names."""

from __future__ import annotations

import re

from langgraph.checkpoint.postgres import PostgresSaver


TABLES = {
    "checkpoint_migrations": "checkpoint_migrations_reflections_app",
    "checkpoint_blobs": "checkpoint_blobs_reflections_app",
    "checkpoint_writes": "checkpoint_writes_reflections_app",
    "checkpoints": "checkpoints_reflections_app",
}


def _rename(sql: str) -> str:
    for old, new in TABLES.items():
        sql = re.sub(rf"\b{old}\b", new, sql)
    return sql


class ReflectionsPostgresSaver(PostgresSaver):
    MIGRATIONS = [_rename(statement) for statement in PostgresSaver.MIGRATIONS]
    SELECT_SQL = _rename(PostgresSaver.SELECT_SQL)
    SELECT_PENDING_SENDS_SQL = _rename(PostgresSaver.SELECT_PENDING_SENDS_SQL)
    UPSERT_CHECKPOINT_BLOBS_SQL = _rename(PostgresSaver.UPSERT_CHECKPOINT_BLOBS_SQL)
    UPSERT_CHECKPOINTS_SQL = _rename(PostgresSaver.UPSERT_CHECKPOINTS_SQL)
    UPSERT_CHECKPOINT_WRITES_SQL = _rename(PostgresSaver.UPSERT_CHECKPOINT_WRITES_SQL)
    INSERT_CHECKPOINT_WRITES_SQL = _rename(PostgresSaver.INSERT_CHECKPOINT_WRITES_SQL)

    def setup(self) -> None:
        migrations = TABLES["checkpoint_migrations"]
        with self._cursor() as cur:
            cur.execute(self.MIGRATIONS[0])
            row = cur.execute(
                f"SELECT v FROM {migrations} ORDER BY v DESC LIMIT 1"
            ).fetchone()
            version = -1 if row is None else row["v"]
            for number, migration in enumerate(
                self.MIGRATIONS[version + 1 :], start=version + 1
            ):
                cur.execute(migration)
                cur.execute(f"INSERT INTO {migrations} (v) VALUES (%s)", (number,))
        if self.pipe:
            self.pipe.sync()

    def delete_thread(self, thread_id: str) -> None:
        with self._cursor(pipeline=True) as cur:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                cur.execute(
                    f"DELETE FROM {TABLES[table]} WHERE thread_id = %s",
                    (str(thread_id),),
                )
