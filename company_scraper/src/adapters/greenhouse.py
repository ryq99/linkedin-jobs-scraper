"""Greenhouse adapter — public Job Board API (one call returns every posting + HTML)."""

import normalize
from adapters import base
from schemas import Job

ATS = "greenhouse"
_API = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch(company: dict, session, scrape_dt: str) -> list[Job]:
    """All of `company`'s Greenhouse postings in the 4 role families."""
    data = base.get_json(session, _API.format(slug=company["slug"]))
    jobs = []
    for raw in data.get("jobs", []):
        family = normalize.match_family(raw.get("title"))
        if family:
            jobs.append(to_job(raw, company, family, scrape_dt))
    return jobs


def to_job(raw: dict, company: dict, family: str, scrape_dt: str) -> Job:
    """Maps one Greenhouse posting to a Job."""
    location = (raw.get("location") or {}).get("name")
    description = normalize.html_to_text(raw.get("content"))
    fields = {k: v for k, v in normalize.salary_fields(description).items() if k in Job.__dataclass_fields__}
    return Job(
        job_id=normalize.make_job_id(ATS, company["slug"], raw["id"]),
        job_url=raw.get("absolute_url") or "",
        search_query=family,
        scrape_dt=scrape_dt,
        job_title=raw.get("title"),
        company_name=company["name"],
        location=location,
        workplace_type=normalize.infer_workplace(location),
        job_description=description,
        posted_at_estimate=raw.get("first_published") or raw.get("updated_at"),
        apply_type="external",
        ats=ATS,
        **fields,
    )
