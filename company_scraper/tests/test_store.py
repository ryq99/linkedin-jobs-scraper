"""Offline tests for the shared-table migration + idempotent upsert."""

import sqlite3

import pytest

import store
from schemas import JOB_FIELDS, Job


def _linkedin_db(path):
    """A jobs table shaped like job_scraper's (no source/ats) with one LinkedIn row."""
    cols = [f for f in JOB_FIELDS if f not in ("job_id", "source", "ats")]
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE jobs (job_id TEXT PRIMARY KEY, {', '.join(cols)}, "
                 "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, times_seen INTEGER NOT NULL DEFAULT 1)")
    conn.execute("INSERT INTO jobs (job_id, job_url, search_query, scrape_dt, first_seen, last_seen) "
                 "VALUES ('4400000001', 'u', 'q', 't', 't', 't')")
    conn.commit()
    conn.close()


def _job(**kw):
    base = dict(job_id="company_site:greenhouse:stripe:1", job_url="u", search_query="data scientist",
                scrape_dt="2026-11-13-10-00", ats="greenhouse")
    return Job(**{**base, **kw})


def test_requires_existing_jobs_table(tmp_path):
    with pytest.raises(RuntimeError):
        store.connect(tmp_path / "empty.db")


def test_migration_backfills_linkedin_and_is_idempotent(tmp_path):
    db = tmp_path / "jobs.db"
    _linkedin_db(db)
    store.connect(db).close()
    conn = store.connect(db)  # second connect must not re-ALTER
    assert conn.execute("SELECT source FROM jobs WHERE job_id='4400000001'").fetchone() == ("linkedin",)


def test_upsert_tags_source_and_tracks_reseen(tmp_path):
    db = tmp_path / "jobs.db"
    _linkedin_db(db)
    conn = store.connect(db)
    store.upsert_jobs(conn, [_job(job_title="Data Scientist")])
    store.upsert_jobs(conn, [_job(job_title="Senior Data Scientist", scrape_dt="2026-11-20-10-00")])
    row = conn.execute("SELECT source, ats, job_title, first_seen, last_seen, times_seen FROM jobs "
                       "WHERE job_id='company_site:greenhouse:stripe:1'").fetchone()
    assert row == ("company_site", "greenhouse", "Senior Data Scientist", "2026-11-13-10-00", "2026-11-20-10-00", 2)
    assert store.seen_ids(conn) == {"company_site:greenhouse:stripe:1"}
