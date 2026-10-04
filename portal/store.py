"""SQLite storage for submissions."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    reference TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    student_id TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    name TEXT NOT NULL,
    programme TEXT NOT NULL,
    level TEXT NOT NULL,
    department TEXT NOT NULL,
    supervisor TEXT NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    file_name TEXT NOT NULL,
    stored_file TEXT NOT NULL,
    file_type TEXT NOT NULL,
    poster_width_mm REAL,
    poster_height_mm REAL,
    orientation TEXT,
    status TEXT NOT NULL DEFAULT 'received'
);
"""

STATUSES = ("received", "accepted", "withdrawn")


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def find_by_student(self, student_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM submissions WHERE student_id = ?", (student_id,)).fetchone()
        return dict(row) if row else None

    def add(self, record: dict) -> dict:
        record = dict(record)
        record["id"] = uuid.uuid4().hex
        record["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            record["reference"] = f"PGS-{datetime.now().year}-{count + 1:04d}"
            cols = ", ".join(record)
            marks = ", ".join("?" for _ in record)
            conn.execute(f"INSERT INTO submissions ({cols}) VALUES ({marks})", list(record.values()))
        return record

    def all(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get(self, submission_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        return dict(row) if row else None

    def set_status(self, submission_id: str, status: str) -> bool:
        if status not in STATUSES:
            return False
        with self._conn() as conn:
            cur = conn.execute("UPDATE submissions SET status = ? WHERE id = ?", (status, submission_id))
        return cur.rowcount == 1
