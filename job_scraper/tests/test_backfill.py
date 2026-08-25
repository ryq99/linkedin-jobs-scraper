"""Tests for the v1→v2 row transform, using values sampled from real S3 CSVs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from backfill_v1 import transform_row
from schemas import JOB_FIELDS


def v1_row(**overrides) -> dict:
    row = {
        "job_id": "4417411287", "job_title": "Senior Data Product Scientist",
        "company_name": "AMC Global Media", "location": "New York, NY",
        "salary": "Not available", "logo_url": "https://logo.png",
        "job_description": "Great role.", "scrape_dt": "2023-03-09",
    }
    row.update(overrides)
    return row


def test_copy_through_and_derived_fields():
    row = transform_row(v1_row())
    assert set(row) == set(JOB_FIELDS)
    assert row["job_title"] == "Senior Data Product Scientist"
    assert row["job_url"] == "https://www.linkedin.com/jobs/view/4417411287/"
    assert row["scrape_dt"] == "2023-03-09"


def test_not_available_becomes_none():
    row = transform_row(v1_row(salary="Not available", job_description="Not available"))
    assert row["salary_raw"] is None
    assert row["job_description"] is None


def test_real_salary_is_parsed():
    row = transform_row(v1_row(salary="$132K/yr - $264K/yr"))
    assert row["salary_min"] == 132_000
    assert row["salary_max"] == 264_000
    assert row["salary_period"] == "yr"


def test_benefits_text_recovered_from_salary_column():
    row = transform_row(v1_row(salary="Medical, +1 benefit"))
    assert row["benefits"] == "Medical, +1"
    assert row["salary_min"] is None


def test_social_proof_junk_becomes_none():
    row = transform_row(v1_row(salary="6 company alumni work here"))
    assert row["salary_raw"] is None
    assert row["benefits"] is None


def test_workplace_type_split_from_location():
    row = transform_row(v1_row(location="San Francisco, CA (Remote)"))
    assert row["location"] == "San Francisco, CA"
    assert row["workplace_type"] == "Remote"


def test_unknowns_stay_none_not_false():
    row = transform_row(v1_row())
    for f in ("verified_job", "is_reposted", "is_promoted", "search_query", "applicants_total", "hiring_team"):
        assert row[f] is None


def test_missing_job_id_gets_deterministic_synthetic_id():
    a = transform_row(v1_row(job_id=None))
    b = transform_row(v1_row(job_id=None))
    c = transform_row(v1_row(job_id=None, job_title="Different Title"))
    assert a["job_id"].startswith("v1-") and len(a["job_id"]) == 19
    assert a["job_id"] == b["job_id"]        # same posting → same id across days
    assert a["job_id"] != c["job_id"]        # different posting → different id
    assert a["job_url"] is None              # no real id, no URL


def test_truly_empty_row_is_dropped():
    empty = {k: None for k in v1_row()}
    empty["scrape_dt"] = "2023-03-09"
    assert transform_row(empty) is None
