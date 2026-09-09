"""S3 export for job_skills — daily-by-date CSVs, mirroring the scraper's layout.

One file per posting-date, {S3_PREFIX}/job_skills_{YYYY-MM-DD}.csv, holding the
extracted records for postings first-seen that date. List columns stay JSON text
(as stored). Re-exports a date whenever its job_skills count changes (count-based
outbox in store), so backfilled days refresh automatically.
"""

import logging

import config
import store

log = logging.getLogger("export")


def save_results(df, date: str) -> None:
    """Write one date's job_skills to its S3 date-file (overwrites that date)."""
    import awswrangler as wr

    path = f"{config.S3_PREFIX.rstrip('/')}/job_skills_{date}.csv"
    wr.s3.to_csv(df=df, path=path, index=False)
    log.info("Saved %d job_skills rows to %s", len(df), path)


def export_dates_to_s3(conn, dates: list[str]) -> int:
    """Export each date's job_skills to its S3 date-file and record it. Returns rows."""
    total = 0
    for date in dates:
        df = store.job_skills_for_date(conn, date)
        if df.empty:
            continue
        save_results(df, date)
        store.mark_exported(conn, date, len(df))
        total += len(df)
    return total
