"""Persistence into the shared `jobs` table (owned/created by job_scraper).

company_scraper never edits job_scraper code: it adds its two provenance columns
via an idempotent migration. `source` defaults to 'linkedin', so SQLite backfills
every existing row and auto-tags future LinkedIn inserts (which never name the
column); company rows set 'company_site' explicitly.
"""

import sqlite3
from dataclasses import asdict
from pathlib import Path

from schemas import JOB_FIELDS, Job

_BUSY_TIMEOUT_MS = 10_000  # job_scraper may be writing concurrently
_PROVENANCE_COLS = {"source": "TEXT DEFAULT 'linkedin'", "ats": "TEXT"}
_DATA_COLS = [f for f in JOB_FIELDS if f != "job_id"]

_UPSERT_JOB = f"""INSERT INTO jobs ({", ".join(JOB_FIELDS)}, first_seen, last_seen, times_seen)
VALUES ({", ".join(f":{f}" for f in JOB_FIELDS)}, :scrape_dt, :scrape_dt, 1)
ON CONFLICT(job_id) DO UPDATE SET
    {", ".join(f"{c} = excluded.{c}" for c in _DATA_COLS)},
    last_seen = excluded.last_seen,
    times_seen = jobs.times_seen + 1
"""

_CREATE_RUNS = """CREATE TABLE IF NOT EXISTS company_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL, finished_at TEXT,
    companies_ok INTEGER, companies_failed INTEGER,
    jobs_seen INTEGER, jobs_new INTEGER, status TEXT
)
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Opens the shared DB, migrates provenance columns, ensures company_runs.

    Raises:
        RuntimeError: if the `jobs` table doesn't exist yet (run job_scraper first).
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone():
        raise RuntimeError("shared `jobs` table missing — run job_scraper once to create it")
    migrate(conn)
    conn.execute(_CREATE_RUNS)
    conn.commit()
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Adds `source`/`ats` if absent; fails loudly on any other schema drift."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    for col, ddl in _PROVENANCE_COLS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
    missing = set(JOB_FIELDS) - existing - set(_PROVENANCE_COLS)
    if missing:
        raise RuntimeError(f"jobs table lacks columns company_scraper writes: {sorted(missing)}")
    conn.commit()


def seen_ids(conn: sqlite3.Connection) -> set[str]:
    """job_ids already stored from company sites (for new-vs-seen counts)."""
    return {r[0] for r in conn.execute("SELECT job_id FROM jobs WHERE source = 'company_site'")}


def upsert_jobs(conn: sqlite3.Connection, jobs: list[Job]) -> None:
    """Idempotent bulk upsert keyed on the namespaced job_id; one transaction."""
    conn.executemany(_UPSERT_JOB, [asdict(j) for j in jobs])
    conn.commit()


def record_run(conn, started_at, finished_at, companies_ok, companies_failed,
               jobs_seen, jobs_new, status) -> None:
    """Appends one row to company_runs (read by the weekly --skip-if-recent guard)."""
    conn.execute(
        "INSERT INTO company_runs (started_at, finished_at, companies_ok, companies_failed,"
        " jobs_seen, jobs_new, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (started_at, finished_at, companies_ok, companies_failed, jobs_seen, jobs_new, status))
    conn.commit()
