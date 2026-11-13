"""company_scraper configuration: paths, role-family filters, and HTTP tuning."""

import os
import re
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent  # company_scraper/
REPO_DIR = PROJECT_DIR.parent
DB_PATH = REPO_DIR / "data" / "jobs.db"  # shared with job_scraper (unified jobs table)
COMPANIES_PATH = PROJECT_DIR / "companies.yaml"
LINKEDIN_PARSERS_PATH = REPO_DIR / "job_scraper" / "src" / "parsers.py"  # reused salary parser

# The 4 role families mirror the LinkedIn search queries; first match wins.
ROLE_FAMILIES = {
    "data scientist": re.compile(r"\bdata scientist", re.IGNORECASE),
    "applied scientist": re.compile(r"\bapplied (?:research )?scientist", re.IGNORECASE),
    "machine learning scientist": re.compile(
        r"\b(?:machine learning|ml)\s+(?:research\s+)?scientist", re.IGNORECASE),
    "machine learning engineer": re.compile(
        r"\b(?:machine learning|ml)\s+engineer|\bengineer\b.*\b(?:machine learning|ml)\b",
        re.IGNORECASE),
}

MAX_WORKERS = int(os.getenv("COMPANY_MAX_WORKERS", "8"))  # concurrent companies
REQUEST_TIMEOUT = int(os.getenv("COMPANY_REQUEST_TIMEOUT", "30"))  # seconds per HTTP call
REQUEST_RETRIES = int(os.getenv("COMPANY_REQUEST_RETRIES", "3"))
USER_AGENT = "linkedin-jobs-scraper/company_scraper (+https://github.com/ryq99/linkedin-jobs-scraper)"
