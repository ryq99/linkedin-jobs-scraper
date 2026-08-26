"""Offline tests for store.py against an in-memory SQLite DB (no shared file)."""

import json
import sqlite3

import pytest

import store
from schema import SCHEMA_VERSION, JobSkills

# Minimal stand-in for the scraper's `jobs` table — only the columns store.py
# reads. (id, description, expected-to-be-a-candidate)
_SEED_JOBS = [
    ("1", "Senior MLE, must have Python", True),
    ("2", "Data Scientist, SQL and stats", True),
    ("3", None, False),   # no description -> never a candidate
    ("4", "", False),     # empty description -> never a candidate
]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, job_description TEXT)")
    c.executemany(
        "INSERT INTO jobs (job_id, job_description) VALUES (?, ?)",
        [(jid, desc) for jid, desc, _ in _SEED_JOBS],
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


def test_write_skills_roundtrip_serializes_enums_and_lists(conn):
    record = JobSkills(job_id="1", role_family="MLE", modeling_area=["NLP", "RAG"], must_have_skills=["Python"])
    assert store.write_skills(conn, [record]) == 1

    role_family, modeling_area, must_have = conn.execute(
        "SELECT role_family, modeling_area, must_have_skills FROM job_skills WHERE job_id='1'"
    ).fetchone()
    assert role_family == "MLE"                       # enum -> plain string
    assert json.loads(modeling_area) == ["NLP", "RAG"]  # list -> JSON text
    assert json.loads(must_have) == ["Python"]


def test_write_skills_overwrites_by_job_id(conn):
    store.write_skills(conn, [JobSkills(job_id="1", seniority="mid")])
    store.write_skills(conn, [JobSkills(job_id="1", seniority="senior")])
    rows = conn.execute("SELECT seniority FROM job_skills WHERE job_id='1'").fetchall()
    assert rows == [("senior",)]  # one row, latest value (INSERT OR REPLACE)
