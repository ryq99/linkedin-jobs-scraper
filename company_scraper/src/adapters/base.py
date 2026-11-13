"""Shared HTTP plumbing for ATS adapters.

Every adapter exposes `fetch(company, session, scrape_dt) -> list[Job]`: pull the
company's postings from its ATS API, keep only the 4 role families, normalize.
"""

import logging
import random
import time

import requests

import config

log = logging.getLogger("adapters")


def new_session() -> requests.Session:
    """One session per worker thread (requests.Session is not thread-safe)."""
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    return session


def get_json(session: requests.Session, url: str, **kwargs) -> dict | list:
    """GET with timeout + exponential backoff on network errors, 429 and 5xx."""
    for attempt in range(1, config.REQUEST_RETRIES + 1):
        try:
            resp = session.get(url, timeout=config.REQUEST_TIMEOUT, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()  # 4xx (e.g. bad slug) is permanent — fails without retry below
            return resp.json()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status is not None and status < 500 and status != 429:
                raise
            last = e
        except requests.RequestException as e:
            last = e
        if attempt < config.REQUEST_RETRIES:
            delay = 2 ** attempt + random.uniform(0, 1)
            log.warning("GET %s failed (%s), retry %d in %.1fs", url, last, attempt, delay)
            time.sleep(delay)
    raise last
