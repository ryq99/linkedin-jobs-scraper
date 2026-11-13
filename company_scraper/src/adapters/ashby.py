"""Ashby adapter — public Job Board API (structured compensation via includeCompensation)."""

import normalize
from adapters import base
from schemas import Job

ATS = "ashby"
_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def fetch(company: dict, session, scrape_dt: str) -> list[Job]:
    """All of `company`'s listed Ashby postings in the 4 role families."""
    jobs = []
    for raw in base.get_json(session, _API.format(slug=company["slug"])).get("jobs", []):
        if raw.get("isListed") is False:  # unlisted = not publicly posted
            continue
        family = normalize.match_family(raw.get("title"))
        if family:
            jobs.append(to_job(raw, company, family, scrape_dt))
    return jobs


def _salary(raw: dict, description: str | None) -> dict:
    """Structured base-salary component if present, else parse the description."""
    comp = raw.get("compensation") or {}
    for part in comp.get("summaryComponents") or []:
        if part.get("compensationType") == "Salary":
            found = normalize.structured_salary(part.get("minValue"), part.get("maxValue"),
                                                part.get("interval"), comp.get("compensationTierSummary"))
            if found:
                return found
    return normalize.salary_fields(description)


def to_job(raw: dict, company: dict, family: str, scrape_dt: str) -> Job:
    """Maps one Ashby posting to a Job."""
    location = raw.get("location")
    description = (raw.get("descriptionPlain") or "").strip() or normalize.html_to_text(raw.get("descriptionHtml"))
    return Job(
        job_id=normalize.make_job_id(ATS, company["slug"], raw["id"]),
        job_url=raw.get("jobUrl") or "",
        search_query=family,
        scrape_dt=scrape_dt,
        job_title=raw.get("title"),
        company_name=company["name"],
        location=location,
        workplace_type=normalize.workplace_from_ats(raw.get("workplaceType"), location),
        employment_type=normalize.employment_type(raw.get("employmentType")),
        job_description=description,
        posted_at_estimate=raw.get("publishedAt"),
        apply_type="external",
        ats=ATS,
        **normalize.job_fields(_salary(raw, description)),
    )
