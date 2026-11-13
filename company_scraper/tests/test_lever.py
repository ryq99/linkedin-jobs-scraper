"""Offline tests for the Lever adapter (HTTP faked)."""

from adapters import lever

COMPANY = {"name": "Spotify", "ats": "lever", "slug": "spotify"}
POSTINGS = [
    {"id": "abc", "text": "Senior Machine Learning Engineer - Personalization",
     "hostedUrl": "https://jobs.lever.co/spotify/abc", "workplaceType": "hybrid", "createdAt": 1792767640768,
     "categories": {"location": "New York, NY", "commitment": "Permanent"},
     "descriptionPlain": "Build recommenders.",
     "lists": [{"text": "What You'll Do", "content": "<li>Train models</li><li>Ship to prod</li>"}],
     "additionalPlain": "Salary: $180K/yr - $220K/yr",
     "salaryRange": {"min": 176000, "max": 260000, "currency": "USD", "interval": "per-year-salary"}},
    {"id": "def", "text": "Account Executive", "hostedUrl": "u", "categories": {}},
]


def test_fetch_filters_and_maps_structured_fields(monkeypatch):
    monkeypatch.setattr(lever.base, "get_json", lambda session, url: POSTINGS)
    (job,) = lever.fetch(COMPANY, session=None, scrape_dt="2026-11-13-10-00")
    assert job.job_id == "company_site:lever:spotify:abc" and job.ats == "lever"
    assert (job.workplace_type, job.employment_type) == ("Hybrid", "Full-time")
    assert "What You'll Do\nTrain models" in job.job_description
    assert (job.salary_min, job.salary_max, job.salary_period) == (176000.0, 260000.0, "yr")  # structured wins
    assert job.posted_at_estimate.startswith("2026-")


def test_falls_back_to_description_salary(monkeypatch):
    raw = {**POSTINGS[0], "salaryRange": None}
    monkeypatch.setattr(lever.base, "get_json", lambda session, url: [raw])
    (job,) = lever.fetch(COMPANY, session=None, scrape_dt="t")
    assert (job.salary_min, job.salary_max) == (180000, 220000)
