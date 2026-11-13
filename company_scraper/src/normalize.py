"""ATS-agnostic helpers that turn native posting fields into `Job` values."""

import html
import importlib.util
import re
from html.parser import HTMLParser

import config

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


def _load_linkedin_parsers():
    """Load job_scraper's parsers.py under a private name (avoids shadowing our modules)."""
    spec = importlib.util.spec_from_file_location("_linkedin_parsers", config.LINKEDIN_PARSERS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_parsers = _load_linkedin_parsers()


def match_family(title: str | None) -> str | None:
    """Returns the first role family whose pattern matches `title`, else None."""
    if not title:
        return None
    for family, pattern in config.ROLE_FAMILIES.items():
        if pattern.search(title):
            return family
    return None


class _TextExtractor(HTMLParser):
    """Collects visible text, breaking lines at block-level tags."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(raw: str | None) -> str | None:
    """Converts (possibly entity-escaped) posting HTML into plain text."""
    if not raw:
        return None
    extractor = _TextExtractor()
    extractor.feed(html.unescape(raw))  # Greenhouse double-escapes: &lt;p&gt; -> <p>
    text = "".join(extractor.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)  # collapse runs of blank lines
    return text.strip() or None


def infer_workplace(location: str | None) -> str | None:
    """Best-effort Remote/Hybrid/On-site from the location string."""
    if not location:
        return None
    lowered = location.lower()
    if "remote" in lowered:
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"
    return "On-site"


def salary_fields(text: str | None) -> dict:
    """Salary columns parsed from free text via job_scraper's parse_salary."""
    if not text:
        return {}
    return _parsers.parse_salary(text) or {}


def make_job_id(ats: str, slug: str, native_id) -> str:
    """Namespaced primary key, stable across runs (the idempotency key)."""
    return f"company_site:{ats}:{slug}:{native_id}"
