"""Export sinks: S3 daily-by-date CSV (full schema, private) + HF split (public).

S3 layout: one file per calendar date, {S3_PREFIX}/linkedin-scrape_{YYYY-MM-DD}.csv,
holding all jobs first-seen that date. On each successful run the pipeline exports
every un-exported date (self-heal). HF keeps one split per run (unchanged).
"""

import logging
import re

import boto3
import pandas as pd

import config
import store
from schemas import PRIVATE_FIELDS

log = logging.getLogger("export")

def public_view(df: pd.DataFrame) -> pd.DataFrame:
    """Drop login/Premium-gated columns — the public dataset gets public data only."""
    return df.drop(columns=[c for c in PRIVATE_FIELDS if c in df.columns])

def save_results(df: pd.DataFrame, date: str) -> None:
    """Write one date's jobs to its S3 date-file (overwrites that date)."""
    import awswrangler as wr

    path = f"{config.S3_PREFIX.rstrip('/')}/linkedin-scrape_{date}.csv"
    wr.s3.to_csv(df=df, path=path, index=False)
    log.info("Saved %d rows to %s", len(df), path)

def export_dates_to_s3(conn, dates: list[str]) -> int:
    """Export each date's jobs to its S3 date-file and record it. Returns rows written."""
    total = 0
    for date in dates:
        df = store.rows_first_seen(conn, date)
        if df.empty:
            continue
        save_results(df, date)
        store.mark_exported(conn, date, len(df))
        total += len(df)
    return total

# date-only file: linkedin-scrape_2026-08-26.csv ; legacy: ..._2026-08-26-10-00.csv
_DATE_FILE = re.compile(r"linkedin-scrape_(\d{4}-\d{2}-\d{2})\.csv$")
_LEGACY_FILE = re.compile(r"linkedin-scrape_(\d{4}-\d{2}-\d{2})-\d{2}-\d{2}\.csv$")

def delete_legacy_timestamp_files() -> int:
    """Delete run-timestamp CSVs, but only for dates whose date-only file now exists."""
    import awswrangler as wr

    prefix = config.S3_PREFIX.rstrip("/")
    objs = wr.s3.list_objects(f"{prefix}/linkedin-scrape_*.csv")
    have_date_file = {m.group(1) for o in objs if (m := _DATE_FILE.search(o))}
    deletable = [o for o in objs
                 if (m := _LEGACY_FILE.search(o)) and m.group(1) in have_date_file]
    if deletable:
        wr.s3.delete_objects(deletable)
    log.info("Deleted %d legacy timestamp files", len(deletable))
    return len(deletable)

def save_to_hf(df: pd.DataFrame, scrape_dt: str) -> None:
    import datasets
    from huggingface_hub import HfApi

    datasets.disable_progress_bars()  # keep scrape.log readable
    token = boto3.client("ssm", region_name=config.SSM_REGION).get_parameter(
        Name=config.SSM_HF_TOKEN, WithDecryption=True
    )["Parameter"]["Value"]
    split = scrape_dt.replace("-", "_")
    # str-or-None (not .astype(str), which turns NULLs into "None"/"nan" strings)
    df = public_view(df).map(lambda v: None if pd.isna(v) else str(v))
    datasets.DatasetDict({split: datasets.Dataset.from_pandas(df, preserve_index=False)}).push_to_hub(
        config.HF_REPO_ID, token=token)
    HfApi().upload_file(
        path_or_fileobj=config.HF_README_PATH, path_in_repo="README.md",
        repo_id=config.HF_REPO_ID, repo_type="dataset", token=token,
    )
    log.info("Pushed %d rows to HF %s (split=%s)", len(df), config.HF_REPO_ID, split)

def require_export_config() -> None:
    if not (config.S3_PREFIX and config.HF_REPO_ID):
        raise RuntimeError("S3_PREFIX and HF_REPO_ID must be set for export")
