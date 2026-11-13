"""Lever adapter — public Postings API (one call per company, full description inline)."""

from datetime import datetime, timezone

import normalize
from adapters import base
from schemas import Job

ATS = "lever"
_API = "https://api.lever.co/v0/postings/{slug}?mode=json"


def fetch(company: dict, session, scrape_dt: str) -> list[Job]:
    """All of `company`'s Lever postings in the 4 role families."""
    jobs = []
    for raw in base.get_json(session, _API.format(slug=company["slug"])):
        family = normalize.match_family(raw.get("text"))
        if family:
            jobs.append(to_job(raw, company, family, scrape_dt))
    return jobs


def _description(raw: dict) -> str | None:
    """Opening + sectioned lists ('What you'll do', ...) + closing, as plain text."""
    parts = [raw.get("descriptionPlain") or ""]
    for section in raw.get("lists") or []:
        parts.append(f"{section.get('text', '')}\n{normalize.html_to_text(section.get('content')) or ''}")
    parts.append(raw.get("additionalPlain") or "")
    return "\n\n".join(p.strip() for p in parts if p and p.strip()) or None


def to_job(raw: dict, company: dict, family: str, scrape_dt: str) -> Job:
    """Maps one Lever posting to a Job."""
    cats = raw.get("categories") or {}
    location = cats.get("location")
    description = _description(raw)
    rng = raw.get("salaryRange") or {}
    salary = (normalize.structured_salary(rng.get("min"), rng.get("max"), rng.get("interval"))
              or normalize.salary_fields(description))
    created = raw.get("createdAt")  # epoch milliseconds
    return Job(
        job_id=normalize.make_job_id(ATS, company["slug"], raw["id"]),
        job_url=raw.get("hostedUrl") or "",
        search_query=family,
        scrape_dt=scrape_dt,
        job_title=raw.get("text"),
        company_name=company["name"],
        location=location,
        workplace_type=normalize.workplace_from_ats(raw.get("workplaceType"), location),
        employment_type=normalize.employment_type(cats.get("commitment")),
        job_description=description,
        posted_at_estimate=(datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()
                            if created else None),
        apply_type="external",
        ats=ATS,
        **normalize.job_fields(salary),
    )
