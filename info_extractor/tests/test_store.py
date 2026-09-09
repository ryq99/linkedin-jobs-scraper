"""Offline tests for store.py against an in-memory SQLite DB (no shared file)."""

import json
import sqlite3

import pytest

import store
from schema import SCHEMA_VERSION, JobSkills

# Minimal stand-in for the scraper's `jobs` table — only the columns store.py
# reads. (id, description, expected-to-be-a-candidate)
_SEED_JOBS = [
    ("1", "Senior MLE, must have Python", "2026-01-01", True),
    ("2", "Data Scientist, SQL and stats", "2026-06-01", True),
    ("3", None, "2026-06-01", False),   # no description -> never a candidate
    ("4", "", "2026-06-01", False),     # empty description -> never a candidate
]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, job_description TEXT, first_seen TEXT)")
    c.executemany(
        "INSERT INTO jobs (job_id, job_description, first_seen) VALUES (?, ?, ?)",
        [(jid, desc, fs) for jid, desc, fs, _ in _SEED_JOBS],
    )
    c.commit()
    c.execute(store._CREATE_JOB_SKILLS)  # same table store.connect() would create
    c.commit()
    return c


def _ids(rows) -> set[str]:
    return {job_id for job_id, _ in rows}


def test_connect_is_idempotent(tmp_path):
    db = tmp_path / "jobs.db"
    store.connect(db).close()
    store.connect(db).close()  # second create must not raise
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name='job_skills'").fetchone()


def test_candidates_needs_nonempty_description(conn):
    assert _ids(store.candidates(conn)) == {"1", "2"}  # 3 (NULL) and 4 ("") excluded


def test_candidates_excludes_current_schema_and_includes_stale(conn):
    store.write_skills(conn, [JobSkills(job_id="1")])                    # current schema
    conn.execute("UPDATE job_skills SET schema_version = ? WHERE job_id = '1'", (SCHEMA_VERSION - 1,))
    assert "1" in _ids(store.candidates(conn))                           # stale -> re-extract
    store.write_skills(conn, [JobSkills(job_id="1")])                    # refresh to current
    assert "1" not in _ids(store.candidates(conn))                       # current -> done


def test_candidates_limit_caps_count(conn):
    assert len(store.candidates(conn, limit=1)) == 1


def test_candidates_recent_first_order(conn):
    # job 2 (2026-06-01) is newer than job 1 (2026-01-01) -> comes first
    assert [jid for jid, _ in store.candidates(conn)] == ["2", "1"]


def test_candidates_since_filters_by_first_seen(conn):
    assert _ids(store.candidates(conn, since="2026-03-01")) == {"2"}  # excludes job 1 (Jan)


def test_write_skills_roundtrip_serializes_enums_and_lists(conn):
    record = JobSkills(job_id="1", seniority="senior", tech_domain=["NLP", "RAG"], skills=["Python"])
    assert store.write_skills(conn, [record]) == 1

    seniority, tech_domain, skills = conn.execute(
        "SELECT seniority, tech_domain, skills FROM job_skills WHERE job_id='1'"
    ).fetchone()
    assert seniority == "senior"                       # enum -> plain string
    assert json.loads(tech_domain) == ["NLP", "RAG"]   # list -> JSON text
    assert json.loads(skills) == ["Python"]


def test_write_skills_overwrites_by_job_id(conn):
    store.write_skills(conn, [JobSkills(job_id="1", seniority="mid")])
    store.write_skills(conn, [JobSkills(job_id="1", seniority="senior")])
    rows = conn.execute("SELECT seniority FROM job_skills WHERE job_id='1'").fetchall()
    assert rows == [("senior",)]  # one row, latest value (INSERT OR REPLACE)


def _seed_job_skills(conn, job_id, first_seen):
    conn.execute("INSERT INTO jobs (job_id, job_description, first_seen) VALUES (?,?,?)",
                 (job_id, "desc", first_seen))
    store.write_skills(conn, [JobSkills(job_id=job_id)])


def test_job_skills_export_dates_and_outbox(tmp_path, monkeypatch):
    import export
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, job_description TEXT, first_seen TEXT)")
    c.execute(store._CREATE_JOB_SKILLS); c.execute(store._CREATE_S3_EXPORTS); c.commit()
    _seed_job_skills(c, "a", "2026-07-18T05:00")
    _seed_job_skills(c, "b", "2026-07-19T05:00")
    assert store.export_dates(c) == ["2026-07-18", "2026-07-19"]
    assert store.dates_needing_export(c) == ["2026-07-18", "2026-07-19"]

    calls = []
    monkeypatch.setattr(export, "save_results", lambda df, date: calls.append((date, len(df))))
    n = export.export_dates_to_s3(c, store.dates_needing_export(c))
    assert n == 2 and calls == [("2026-07-18", 1), ("2026-07-19", 1)]
    assert store.dates_needing_export(c) == []          # all recorded at current count

    # a date grows (more of its backlog extracted) -> it needs re-export
    _seed_job_skills(c, "c", "2026-07-19T06:00")
    assert store.dates_needing_export(c) == ["2026-07-19"]
