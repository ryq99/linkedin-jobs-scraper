"""SQLite persistence — the scraper's cross-run memory: incremental scraping
(skip seen jobs), first/last-seen tracking, crash resumability."""

import sqlite3
import typing
from dataclasses import asdict, fields
from pathlib import Path

import pandas as pd

from schemas import JOB_FIELDS, Job

_DATA_COLS = [f for f in JOB_FIELDS if f != "job_id"]

def _column_type(py_type) -> str:
    """SQLite type from a dataclass annotation (unwraps Optional). All-TEXT
    columns would coerce numbers to strings and break `salary_min > 150000`."""
    args = typing.get_args(py_type)
    if args:
        py_type = next(a for a in args if a is not type(None))
    return {float: "REAL", int: "INTEGER", bool: "INTEGER"}.get(py_type, "TEXT")

_COL_TYPES = {f.name: _column_type(f.type) for f in fields(Job)}

_CREATE_JOBS = f"""CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    {", ".join(f"{col} {_COL_TYPES[col]}" for col in _DATA_COLS)},
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 1
)
"""

_CREATE_RUNS = """CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL, finished_at TEXT, queries TEXT,
    jobs_seen INTEGER, jobs_new INTEGER, status TEXT
)
"""

# Tracks which calendar dates' S3 date-file has been uploaded — the outbox that
# lets a successful run self-heal any date a failed run left un-exported.
_CREATE_S3_EXPORTS = """CREATE TABLE IF NOT EXISTS s3_exports (
    export_date TEXT PRIMARY KEY, job_count INTEGER, uploaded_at TEXT
)
"""

_UPSERT_JOB = f"""INSERT INTO jobs ({", ".join(JOB_FIELDS)}, first_seen, last_seen, times_seen)
VALUES ({", ".join(f":{f}" for f in JOB_FIELDS)}, :scrape_dt, :scrape_dt, 1)
ON CONFLICT(job_id) DO UPDATE SET
    {", ".join(f"{col} = excluded.{col}" for col in _DATA_COLS)},
    last_seen = excluded.last_seen,
    times_seen = jobs.times_seen + 1
"""

def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_CREATE_JOBS)
    conn.execute(_CREATE_RUNS)
    conn.execute(_CREATE_S3_EXPORTS)
    conn.commit()
    return conn

def seen_ids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT job_id FROM jobs")}

def upsert_job(conn: sqlite3.Connection, job: Job) -> None:
    """Insert, or refresh all fields + last_seen/times_seen on conflict."""
    conn.execute(_UPSERT_JOB, asdict(job))
    conn.commit()

def touch_last_seen(conn: sqlite3.Connection, job_ids: list[str], scrape_dt: str) -> None:
    """Mark already-known jobs as seen again (no detail re-fetch)."""
    conn.executemany(
        "UPDATE jobs SET last_seen = ?, times_seen = times_seen + 1 WHERE job_id = ?",
        [(scrape_dt, jid) for jid in job_ids],
    )
    conn.commit()

def record_run(conn, started_at, finished_at, queries, jobs_seen, jobs_new, status) -> None:
    conn.execute(
        "INSERT INTO runs (started_at, finished_at, queries, jobs_seen, jobs_new, status) VALUES (?, ?, ?, ?, ?, ?)",
        (started_at, finished_at, queries, jobs_seen, jobs_new, status),
    )
    conn.commit()

def rows_first_seen(conn: sqlite3.Connection, date_prefix: str) -> pd.DataFrame:
    """All jobs first seen on a given day ('YYYY-MM-DD'), for export."""
    return pd.read_sql_query("SELECT * FROM jobs WHERE first_seen LIKE ?", conn, params=(f"{date_prefix}%",))

def export_dates(conn: sqlite3.Connection) -> list[str]:
    """Every calendar date (YYYY-MM-DD) that has jobs, oldest first."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(first_seen, 1, 10) d FROM jobs ORDER BY d")]

def dates_needing_export(conn: sqlite3.Connection, today: str) -> list[str]:
    """Dates whose S3 file isn't recorded yet, plus `today` (still accumulating).
    This is the self-heal set: a date a failed run skipped stays un-recorded and
    gets picked up on the next successful run."""
    rows = conn.execute(
        "SELECT DISTINCT substr(first_seen, 1, 10) d FROM jobs "
        "WHERE substr(first_seen, 1, 10) NOT IN (SELECT export_date FROM s3_exports) "
        "   OR substr(first_seen, 1, 10) = ? ORDER BY d",
        (today,))
    return [r[0] for r in rows]

def mark_exported(conn: sqlite3.Connection, export_date: str, job_count: int) -> None:
    """Record that `export_date`'s S3 file was uploaded (idempotent upsert)."""
    conn.execute(
        "INSERT INTO s3_exports (export_date, job_count, uploaded_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(export_date) DO UPDATE SET job_count = excluded.job_count, uploaded_at = excluded.uploaded_at",
        (export_date, job_count))
    conn.commit()

def stats(conn: sqlite3.Connection) -> dict:
    return {
        "jobs": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
        "runs": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
        "last_run": conn.execute(
            "SELECT started_at, status, jobs_seen, jobs_new FROM runs ORDER BY run_id DESC LIMIT 1"
        ).fetchone(),
    }

def field_completeness(conn: sqlite3.Connection, date_prefix: str) -> dict[str, float]:
    """Fraction of non-null values per field among jobs first seen that day."""
    df = rows_first_seen(conn, date_prefix)
    return {} if df.empty else {c: round(float(df[c].notna().mean()), 3) for c in df.columns}
