"""SQLite persistence for extracted JobSkills.

Writes one `job_skills` row per posting into the shared `data/jobs.db`: the
scraper owns `jobs`, this module owns `job_skills`, keyed `job_id` back to it.
Reads `jobs.job_description` via raw SQL (no import of the scraper's schema) so
the component stays self-contained.
"""

import json
import sqlite3
import typing
from pathlib import Path

import pandas as pd

from schema import JOBSKILLS_FIELDS, SCHEMA_VERSION, JobSkills

# Tracks which posting-date's job_skills S3 file was uploaded, with the row count
# so a date re-exports when more of that day's backlog gets extracted later.
_CREATE_S3_EXPORTS = """CREATE TABLE IF NOT EXISTS job_skills_s3_exports (
    export_date TEXT PRIMARY KEY, job_count INTEGER, uploaded_at TEXT
)
"""

# Wait out the scraper's writes on the shared file instead of erroring — an
# operational knob peer to the WAL pragma, not a tunable business setting.
_BUSY_TIMEOUT_MS = 5000

# List-typed fields have no SQLite array type → stored as JSON text.
_JSON_FIELDS = {
    name for name, field in JobSkills.model_fields.items()
    if typing.get_origin(field.annotation) is list
}


def _sqlite_type(annotation) -> str:
    """SQLite affinity for a JobSkills field: INTEGER for ints, else TEXT.

    Enums store as their `.value` string and lists as JSON text — both TEXT.
    Unwraps `Optional[...]` to the underlying type first.
    """
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    base = args[0] if args else annotation
    return "INTEGER" if base is int else "TEXT"


_COLUMNS = ", ".join(
    f"{name} {_sqlite_type(field.annotation)}" + (" PRIMARY KEY" if name == "job_id" else "")
    for name, field in JobSkills.model_fields.items()
)
_CREATE_JOB_SKILLS = f"CREATE TABLE IF NOT EXISTS job_skills ({_COLUMNS})"

# Re-extraction fully overwrites the record (nothing to preserve, unlike the
# scraper's first_seen/times_seen), so REPLACE is the idempotent write.
_INSERT_SKILLS = (
    f"INSERT OR REPLACE INTO job_skills ({', '.join(JOBSKILLS_FIELDS)}) "
    f"VALUES ({', '.join(f':{f}' for f in JOBSKILLS_FIELDS)})"
)

# Postings needing extraction: have a description, and either no job_skills row
# or one written under an older schema. Optional `since` bounds to recent
# postings; recent-first order (first_seen DESC) so partial progress always
# covers the most relevant data. LIMIT -1 means unbounded.
_CANDIDATES = """SELECT j.job_id, j.job_description
FROM jobs j LEFT JOIN job_skills s ON s.job_id = j.job_id
WHERE j.job_description IS NOT NULL AND j.job_description != ''
  AND (:since IS NULL OR j.first_seen >= :since)
  AND (s.job_id IS NULL OR s.schema_version < :schema_version)
ORDER BY j.first_seen DESC LIMIT :limit"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open the shared DB and ensure the `job_skills` table exists.

    Creates only `job_skills` — the scraper owns `jobs`. No mkdir: `data/`
    already exists, and running before the scraper fails loudly on the missing
    `jobs` table (which is the correct signal).
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    conn.execute(_CREATE_JOB_SKILLS)
    conn.execute(_CREATE_S3_EXPORTS)
    conn.commit()
    return conn


def candidates(conn: sqlite3.Connection, limit: int | None = None,
               since: str | None = None) -> list[tuple[str, str]]:
    """(job_id, job_description) for postings not yet extracted at this schema,
    newest first. `since` (YYYY-MM-DD) bounds to postings first seen on/after it."""
    params = {"schema_version": SCHEMA_VERSION, "since": since, "limit": -1 if limit is None else limit}
    return conn.execute(_CANDIDATES, params).fetchall()


def export_dates(conn: sqlite3.Connection) -> list[str]:
    """Every posting-date that has at least one job_skills row, oldest first."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(j.first_seen, 1, 10) d FROM job_skills s "
        "JOIN jobs j ON j.job_id = s.job_id ORDER BY d")]

def dates_needing_export(conn: sqlite3.Connection) -> list[str]:
    """Posting-dates whose current job_skills count differs from what was last
    exported (or was never exported). Count-based because a date's job_skills set
    grows as more of that day's backlog is extracted across runs."""
    rows = conn.execute(
        "SELECT cur.d FROM ("
        "  SELECT substr(j.first_seen, 1, 10) d, COUNT(*) c"
        "  FROM job_skills s JOIN jobs j ON j.job_id = s.job_id GROUP BY d"
        ") cur LEFT JOIN job_skills_s3_exports e ON e.export_date = cur.d "
        "WHERE e.job_count IS NULL OR e.job_count != cur.c ORDER BY cur.d")
    return [r[0] for r in rows]

def job_skills_for_date(conn: sqlite3.Connection, date: str) -> pd.DataFrame:
    """All job_skills rows for postings first-seen on `date` (YYYY-MM-DD)."""
    return pd.read_sql_query(
        "SELECT s.* FROM job_skills s JOIN jobs j ON j.job_id = s.job_id "
        "WHERE substr(j.first_seen, 1, 10) = ?", conn, params=(date,))

def mark_exported(conn: sqlite3.Connection, export_date: str, job_count: int) -> None:
    """Record that `export_date`'s job_skills S3 file was uploaded (idempotent)."""
    conn.execute(
        "INSERT INTO job_skills_s3_exports (export_date, job_count, uploaded_at) "
        "VALUES (?, ?, datetime('now')) ON CONFLICT(export_date) DO UPDATE SET "
        "job_count = excluded.job_count, uploaded_at = excluded.uploaded_at",
        (export_date, job_count))
    conn.commit()


def write_skills(conn: sqlite3.Connection, records: typing.Iterable[JobSkills]) -> int:
    """Bulk-upsert JobSkills, idempotent by job_id. Returns the number written."""
    rows = []
    for record in records:
        row = record.model_dump(mode="json")  # enums -> .value strings
        for field in _JSON_FIELDS:
            row[field] = json.dumps(row[field])
        rows.append(row)
    conn.executemany(_INSERT_SKILLS, rows)
    conn.commit()
    return len(rows)
