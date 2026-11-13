"""Offline tests for ATS-agnostic normalization helpers."""

import pytest

import normalize


@pytest.mark.parametrize("title,family", [
    ("Senior Data Scientist, Ads", "data scientist"),
    ("Applied Scientist II", "applied scientist"),
    ("Applied Research Scientist", "applied scientist"),
    ("Staff Machine Learning Scientist", "machine learning scientist"),
    ("ML Engineer, Ranking", "machine learning engineer"),
    ("Software Engineer, Machine Learning", "machine learning engineer"),
    ("Senior Product Manager", None),
    ("Data Engineer", None),
    (None, None),
])
def test_match_family(title, family):
    assert normalize.match_family(title) == family


def test_html_to_text_unescapes_and_breaks_blocks():
    raw = "&lt;p&gt;About the team&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"
    text = normalize.html_to_text(raw)
    assert "<" not in text and "About the team" in text
    assert "Python\n" in text and text.endswith("SQL")


@pytest.mark.parametrize("loc,expected", [
    ("Remote - US", "Remote"), ("San Francisco, CA (Hybrid)", "Hybrid"),
    ("Seattle, WA", "On-site"), (None, None)])
def test_infer_workplace(loc, expected):
    assert normalize.infer_workplace(loc) == expected


def test_salary_fields_reuses_linkedin_parser():
    fields = normalize.salary_fields("The base pay range is $150K/yr - $200K/yr plus equity.")
    assert fields.get("salary_min") == 150000 and fields.get("salary_max") == 200000


def test_job_id_is_namespaced():
    assert normalize.make_job_id("greenhouse", "stripe", 123) == "company_site:greenhouse:stripe:123"


@pytest.mark.parametrize("value,loc,expected", [
    ("hybrid", None, "Hybrid"), ("OnSite", None, "On-site"), ("Remote", None, "Remote"),
    (None, "Remote - US", "Remote"), ("unspecified", "Austin, TX", "On-site")])
def test_workplace_from_ats(value, loc, expected):
    assert normalize.workplace_from_ats(value, loc) == expected


@pytest.mark.parametrize("value,expected", [
    ("FullTime", "Full-time"), ("Permanent", "Full-time"), ("Intern", "Internship"),
    ("Contract", "Contract"), ("Part-time", "Part-time"), (None, None)])
def test_employment_type(value, expected):
    assert normalize.employment_type(value) == expected


def test_structured_salary_hourly_and_empty():
    assert normalize.structured_salary(50, 70, "per-hour-wage")["salary_period"] == "hr"
    assert normalize.structured_salary(None, None, "1 YEAR") == {}


@pytest.mark.parametrize("text,expected", [
    ("Pay: $207,000—$218,500 USD", (207000, 218500, "yr")),
    ("range $180,000—$190,000 CAD and $207,000—$218,500 USD", (207000, 218500, "yr")),  # USD preferred
    ("$150K - $200K plus equity", (150000, 200000, "yr")),
    ("$45.50 - $60 per hour", (45.5, 60, "hr")),
    ("our $1B+ ads business", None),  # not a range
])
def test_range_salary_fallback(text, expected):
    got = normalize.salary_fields(text)
    if expected is None:
        assert got == {}
    else:
        assert (got["salary_min"], got["salary_max"], got["salary_period"]) == expected
