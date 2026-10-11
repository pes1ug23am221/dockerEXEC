"""
executor/job_queue.py
---------------------
SQLite-backed durable job queue.

State machine:
  QUEUED → DISPATCHED → RUNNING → COMPLETED
                      ↘ FAILED

Jobs persisted to data/queue.db so they survive server restarts.
On boot, any job stuck in QUEUED or DISPATCHED is recovered and
re-enqueued for execution.
"""

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "queue.db"

# Thread-local storage so each thread gets its own connection
_local = threading.local()

# Valid states
QUEUED = "QUEUED"
DISPATCHED = "DISPATCHED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

RECOVERY_STATES = {QUEUED, DISPATCHED}


def _get_conn() -> sqlite3.Connection:
    """Returns a thread-local SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for concurrency
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    """Creates the queue table if it doesn't exist."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT    NOT NULL UNIQUE,
            access_code TEXT    NOT NULL,
            state       TEXT    NOT NULL DEFAULT 'QUEUED',
            queued_at   TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL,
            error_msg   TEXT
        )
    """)
    conn.commit()


def enqueue(job_id: str, access_code: str) -> int:
    """
    Adds a new job to the queue in QUEUED state.
    Returns the internal queue row ID.
    Idempotent: if the job_id already exists, returns its existing row ID.
    """
    conn = _get_conn()
    now = _now()
    try:
        cur = conn.execute(
            """
            INSERT INTO job_queue (job_id, access_code, state, queued_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, access_code, QUEUED, now, now),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # Job already exists — return existing row id
        row = conn.execute(
            "SELECT id FROM job_queue WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row["id"] if row else -1


def transition(job_id: str, new_state: str, error_msg: str | None = None) -> bool:
    """
    Moves a job to the given state.
    Returns True if the update affected a row, False if job not found.
    """
    conn = _get_conn()
    now = _now()
    cur = conn.execute(
        "UPDATE job_queue SET state = ?, updated_at = ?, error_msg = ? WHERE job_id = ?",
        (new_state, now, error_msg, job_id),
    )
    conn.commit()
    return cur.rowcount > 0


def get_job(job_id: str) -> dict | None:
    """Returns the queue record for a job_id, or None if not found."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM job_queue WHERE job_id = ?", (job_id,)
    ).fetchone()
    return dict(row) if row else None


def list_jobs(state: str | None = None) -> list[dict]:
    """Lists all jobs, optionally filtered by state."""
    conn = _get_conn()
    if state:
        rows = conn.execute(
            "SELECT * FROM job_queue WHERE state = ? ORDER BY id ASC", (state,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM job_queue ORDER BY id ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_recoverable_jobs() -> list[dict]:
    """
    Returns all jobs in QUEUED or DISPATCHED state (i.e., interrupted by a crash).
    These should be re-executed or re-queued on server startup.
    """
    conn = _get_conn()
    placeholders = ",".join("?" * len(RECOVERY_STATES))
    rows = conn.execute(
        f"SELECT * FROM job_queue WHERE state IN ({placeholders}) ORDER BY id ASC",
        tuple(RECOVERY_STATES),
    ).fetchall()
    return [dict(r) for r in rows]


def queue_position(job_id: str) -> int:
    """
    Returns the 1-based queue position of a QUEUED job relative to all QUEUED jobs.
    Returns 0 if the job is not in QUEUED state.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT job_id FROM job_queue WHERE state = ? ORDER BY id ASC", (QUEUED,)
    ).fetchall()
    ids = [r["job_id"] for r in rows]
    try:
        return ids.index(job_id) + 1
    except ValueError:
        return 0


def pending_count() -> int:
    """Returns total number of jobs in QUEUED state."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM job_queue WHERE state = ?", (QUEUED,)
    ).fetchone()
    return row["c"] if row else 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Initialize table on module import
init_db()
