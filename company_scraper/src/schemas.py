"""Job record for company-site postings.

Mirrors job_scraper's `Job` field-for-field (same unified `jobs` table) plus two
provenance columns, `source` and `ats`. LinkedIn-only fields (applicant counts,
Premium insights, hiring team) exist for schema parity but stay None here.
tests/test_schemas.py asserts this is a superset of job_scraper's fields.
"""

from dataclasses import dataclass, fields


@dataclass
class Job:
    """One posting from a company's official career site."""

    # identity
    job_id: str  # "company_site:{ats}:{slug}:{native_id}" — never collides with LinkedIn ids
    job_url: str
    search_query: str  # the matched role family
    scrape_dt: str

    # core
    job_title: str | None = None
    company_name: str | None = None
    location: str | None = None
    workplace_type: str | None = None  # Remote | Hybrid | On-site
    employment_type: str | None = None
    job_description: str | None = None
    logo_url: str | None = None
    verified_job: bool = False

    # salary (parsed from the description)
    salary_raw: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_period: str | None = None

    # posting meta
    posted_age_text: str | None = None
    posted_at_estimate: str | None = None
    is_reposted: bool = False
    is_promoted: bool = False
    apply_type: str | None = None
    applicants_clicked: str | None = None
    benefits: str | None = None

    # company
    about_company: str | None = None
    company_headcount: int | None = None
    headcount_growth_2y: str | None = None
    median_tenure: float | None = None

    # LinkedIn Premium insights (always None for company sites)
    applicants_total: int | None = None
    applicants_past_day: int | None = None
    seniority_dist: str | None = None
    education_dist: str | None = None

    # people
    hiring_team: str | None = None

    # provenance (company_scraper-owned columns on the shared table)
    source: str = "company_site"
    ats: str | None = None


JOB_FIELDS = [f.name for f in fields(Job)]
