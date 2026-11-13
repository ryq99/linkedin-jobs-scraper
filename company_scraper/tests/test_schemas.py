"""The unified jobs table contract: company Job ⊇ job_scraper Job."""

import importlib.util

import config
import schemas


def test_company_job_is_superset_of_linkedin_job():
    path = config.REPO_DIR / "job_scraper" / "src" / "schemas.py"
    spec = importlib.util.spec_from_file_location("_linkedin_schemas", path)
    linkedin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(linkedin)
    assert set(linkedin.JOB_FIELDS) <= set(schemas.JOB_FIELDS)
    assert set(schemas.JOB_FIELDS) - set(linkedin.JOB_FIELDS) == {"source", "ats"}
