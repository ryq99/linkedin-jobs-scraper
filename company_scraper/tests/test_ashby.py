"""Offline tests for the Ashby adapter (HTTP faked)."""

from adapters import ashby

COMPANY = {"name": "OpenAI", "ats": "ashby", "slug": "openai"}
BOARD = {"jobs": [
    {"id": "1", "title": "Applied Scientist, Safety", "location": "San Francisco", "workplaceType": "OnSite",
     "employmentType": "FullTime", "publishedAt": "2026-11-05T02:20:02+00:00",
     "jobUrl": "https://jobs.ashbyhq.com/openai/1", "descriptionPlain": "Do safety research.", "isListed": True,
     "compensation": {"compensationTierSummary": "$207K – $285K • Offers Equity", "summaryComponents": [
         {"compensationType": "EquityCashValue", "minValue": None, "maxValue": None, "interval": "1 YEAR"},
         {"compensationType": "Salary", "minValue": 207000, "maxValue": 285000, "interval": "1 YEAR"}]}},
    {"id": "2", "title": "Data Scientist", "isListed": False},  # unlisted -> skipped
    {"id": "3", "title": "Recruiter", "isListed": True},
]}


def test_fetch_skips_unlisted_and_parses_compensation(monkeypatch):
    monkeypatch.setattr(ashby.base, "get_json", lambda session, url: BOARD)
    (job,) = ashby.fetch(COMPANY, session=None, scrape_dt="2026-11-13-10-00")
    assert job.job_id == "company_site:ashby:openai:1" and job.search_query == "applied scientist"
    assert (job.workplace_type, job.employment_type) == ("On-site", "Full-time")
    assert (job.salary_min, job.salary_max, job.salary_period) == (207000.0, 285000.0, "yr")
    assert job.salary_raw == "$207K – $285K • Offers Equity"
