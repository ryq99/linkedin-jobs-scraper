"""Offline tests for the Greenhouse adapter (HTTP faked)."""

from adapters import greenhouse

COMPANY = {"name": "Stripe", "ats": "greenhouse", "slug": "stripe"}
POSTINGS = {"jobs": [
    {"id": 1, "title": "Machine Learning Engineer, Payments", "absolute_url": "https://stripe.com/jobs/1",
     "location": {"name": "Remote in US"}, "first_published": "2026-11-01T00:00:00-04:00",
     "content": "&lt;p&gt;Build fraud models. Pay: $180K/yr - $250K/yr&lt;/p&gt;"},
    {"id": 2, "title": "Account Executive", "absolute_url": "https://stripe.com/jobs/2",
     "location": {"name": "NYC"}, "content": "&lt;p&gt;Sell.&lt;/p&gt;"},
]}


def test_fetch_filters_and_normalizes(monkeypatch):
    monkeypatch.setattr(greenhouse.base, "get_json", lambda session, url: POSTINGS)
    jobs = greenhouse.fetch(COMPANY, session=None, scrape_dt="2026-11-13-10-00")
    assert len(jobs) == 1  # the sales role is filtered out
    job = jobs[0]
    assert job.job_id == "company_site:greenhouse:stripe:1"
    assert (job.source, job.ats, job.search_query) == ("company_site", "greenhouse", "machine learning engineer")
    assert job.company_name == "Stripe" and job.workplace_type == "Remote"
    assert job.job_description.startswith("Build fraud models")
    assert job.salary_min == 180000 and job.salary_max == 250000
    assert job.posted_at_estimate == "2026-11-01T00:00:00-04:00"
