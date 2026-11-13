"""company_scraper entry point: python src/main.py scrape [--only ATS] [--company NAME].

Fans out over companies.yaml in a bounded thread pool (HTTP-bound, embarrassingly
parallel); each company is isolated so one failure can't sink the batch. Writes
happen on the main thread (SQLite single writer).
"""

import argparse
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import yaml

import config
import store
from adapters import ashby, base, greenhouse, lever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("main")

EXIT_OK = 0
EXIT_ALL_FAILED = 3  # every routed company failed — likely network/ATS-wide breakage

ADAPTERS = {a.ATS: a.fetch for a in (greenhouse, lever, ashby)}  # ats name -> fetch(company, session, scrape_dt)


def load_companies(only: str | None = None, company: str | None = None) -> list[dict]:
    """Routable companies (known ATS with an adapter), optionally filtered."""
    entries = yaml.safe_load(config.COMPANIES_PATH.read_text())["companies"]
    routable = [c for c in entries if c.get("ats") in ADAPTERS]
    if only:
        routable = [c for c in routable if c["ats"] == only]
    if company:
        routable = [c for c in routable if c["name"].lower() == company.lower()]
    return routable


def scrape_company(company: dict, scrape_dt: str) -> list:
    """Fetches one company's matching postings (runs in a worker thread)."""
    time.sleep(random.uniform(0, 1.5))  # spread requests to the same ATS host
    return ADAPTERS[company["ats"]](company, base.new_session(), scrape_dt)


def cmd_scrape(args) -> int:
    started = datetime.now(timezone.utc)
    scrape_dt = started.strftime("%Y-%m-%d-%H-%M")  # same format as job_scraper's first_seen
    conn = store.connect(args.db)
    known = store.seen_ids(conn)
    companies = load_companies(args.only, args.company)
    log.info("Run %s | %d routable companies | %d company jobs already stored",
             scrape_dt, len(companies), len(known))

    ok, failed, seen, new = 0, [], 0, 0
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_company, c, scrape_dt): c for c in companies}
        for future in as_completed(futures):
            company = futures[future]
            try:
                jobs = future.result()
            except Exception as e:  # isolate: one company's failure never kills the run
                log.warning("%s (%s) failed: %s", company["name"], company["ats"], e)
                failed.append(company["name"])
                continue
            store.upsert_jobs(conn, jobs)
            fresh = sum(j.job_id not in known for j in jobs)
            ok, seen, new = ok + 1, seen + len(jobs), new + fresh
            log.info("%-22s %3d matching (%d new)", company["name"], len(jobs), fresh)

    status = "ok" if ok else "failed"
    store.record_run(conn, started.isoformat(), datetime.now(timezone.utc).isoformat(),
                     ok, len(failed), seen, new, status)
    log.info("Done: %d/%d companies ok, %d matching postings (%d new)%s",
             ok, len(companies), seen, new, f" | failed: {', '.join(failed)}" if failed else "")
    if companies and not ok:
        log.error("Every company failed — check network / ATS APIs")
        return EXIT_ALL_FAILED
    return EXIT_OK


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="company_scraper", description="Official career-site scraper (ATS APIs)")
    sub = p.add_subparsers(dest="command", required=True)
    sc = sub.add_parser("scrape", help="Scrape all routable companies")
    sc.add_argument("--only", default=None, help="Restrict to one ATS (greenhouse | lever | ashby)")
    sc.add_argument("--company", default=None, help="Restrict to one company name")
    sc.add_argument("--db", default=config.DB_PATH, help="SQLite DB (default: shared data/jobs.db)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    return cmd_scrape(args)


if __name__ == "__main__":
    raise SystemExit(main())
