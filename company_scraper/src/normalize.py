"""ATS-agnostic helpers that turn native posting fields into `Job` values."""

import html
import importlib.util
import re
from html.parser import HTMLParser

import config
from schemas import Job

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


_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s?([kK])?"
# Pay-transparency ranges as company sites write them: "$207,000—$218,500 USD", "$150K - $200K".
_RANGE_RE = re.compile(r"\$\s?" + _NUM + r"\s*(?:—|–|-|to)\s*\$?\s?" + _NUM + r"(?:\s*(USD|CAD|EUR|GBP))?")


def _amount(num: str, k: str | None) -> float:
    return float(num.replace(",", "")) * (1000 if k else 1)


def _range_salary(text: str) -> dict:
    """First plausible two-sided $ range, preferring a USD-tagged one."""
    found = []
    for m in _RANGE_RE.finditer(text):
        lo, hi = _amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))
        if 10 <= lo <= hi < 2_000_000:  # rejects "$1B+" prose and inverted/garbage ranges
            found.append((m.group(5), lo, hi, m.group(0).strip()))
    if not found:
        return {}
    currency, lo, hi, raw = next((f for f in found if f[0] == "USD"), found[0])
    return {"salary_min": lo, "salary_max": hi, "salary_period": "hr" if hi < 1000 else "yr", "salary_raw": raw}


def salary_fields(text: str | None) -> dict:
    """Salary columns from free text: a two-sided $ range first (strictly more
    informative), else job_scraper's parse_salary (handles '$132K/yr' style)."""
    if not text:
        return {}
    return _range_salary(text) or _parsers.parse_salary(text) or {}


def make_job_id(ats: str, slug: str, native_id) -> str:
    """Namespaced primary key, stable across runs (the idempotency key)."""
    return f"company_site:{ats}:{slug}:{native_id}"


_WORKPLACE = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "On-site", "on-site": "On-site"}


def workplace_from_ats(value: str | None, location: str | None = None) -> str | None:
    """Maps an ATS workplace enum (e.g. 'hybrid', 'OnSite'); falls back to the location text."""
    if value and value.lower() in _WORKPLACE:
        return _WORKPLACE[value.lower()]
    return infer_workplace(location)


def employment_type(value: str | None) -> str | None:
    """Normalizes ATS commitment enums ('FullTime', 'Permanent', 'Intern') to LinkedIn's labels."""
    if not value:
        return None
    v = value.lower().replace("-", "").replace(" ", "")
    if "intern" in v:
        return "Internship"
    if "contract" in v or "temporary" in v:
        return "Contract"
    if "parttime" in v:
        return "Part-time"
    if "fulltime" in v or "permanent" in v or "regular" in v:
        return "Full-time"
    return value


def structured_salary(lo, hi, interval: str | None, raw: str | None = None) -> dict:
    """Salary columns from an ATS's structured range (preferred over text parsing)."""
    if lo is None and hi is None:
        return {}
    period = "hr" if interval and "hour" in interval.lower() else "yr"
    return {"salary_min": float(lo) if lo is not None else None,
            "salary_max": float(hi) if hi is not None else None,
            "salary_period": period, "salary_raw": raw}


def job_fields(values: dict) -> dict:
    """Drops keys that aren't Job columns (parser dicts can carry extras)."""
    return {k: v for k, v in values.items() if k in Job.__dataclass_fields__}
