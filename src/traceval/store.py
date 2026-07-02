import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from traceval.model import Trace


class TraceStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    source TEXT,
                    outcome_label TEXT,
                    data TEXT
                )
            """)

    def save_trace(self, trace: Trace) -> None:
        outcome_label = trace.outcome.label if trace.outcome else None
        data_str = trace.model_dump_json()
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO traces (trace_id, source, outcome_label, data)
                VALUES (?, ?, ?, ?)
                """,
                (trace.trace_id, trace.source, outcome_label, data_str),
            )

    def get_trace(self, trace_id: str) -> Trace | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM traces WHERE trace_id = ?", (trace_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Trace.model_validate(json.loads(row[0]))

    def list_traces(self) -> Iterator[Trace]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM traces")
        for row in cursor:
            yield Trace.model_validate(json.loads(row[0]))

    def count_traces(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM traces")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self.conn.close()
