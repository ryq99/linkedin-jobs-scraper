#!/usr/bin/env python3
"""One-time migration of historical v1 scrapes (8 columns) to the current schema.

Usage: python scripts/backfill_v1.py {tag|archive|fetch|transform|seed|s3-up|hf-push|card|all}

Phases are resumable and idempotent. Raw data is never destroyed: S3 originals
are archived to raw_v1/ first and the pre-migration HF revision is tagged
v1-schema. Row transforms reuse the production parsers so migrated history is
consistent with newly scraped data by construction.
"""

import argparse
import hashlib
import logging
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import boto3
import pandas as pd

import config
import crawler
import export
import parsers
import store
from schemas import JOB_FIELDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s backfill - %(message)s")
log = logging.getLogger("backfill")

CACHE = config.DATA_DIR / "backfill_cache"
MIGRATED = config.DATA_DIR / "backfill_migrated"
RAW_V1 = config.S3_PREFIX.rstrip("/").rsplit("/", 1)[0] + "/raw_v1"
V1_COLS = ["job_id", "job_title", "company_name", "location", "salary", "logo_url", "job_description", "scrape_dt"]


def _null(v):
    """Old-schema sentinel cleanup: '', 'Not available', NaN → None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    v = str(v).strip()
    return None if v in ("", "Not available", "nan") else v


def transform_row(old: dict) -> dict | None:
    """Map one v1 row onto the current schema. Unknowns stay None (never False).

    Returns None only for truly empty rows. The 2023-era scraper captured full
    postings without LinkedIn ids — those get a deterministic synthetic id
    ('v1-' + hash of title|company|location) so snapshots keep every row and
    the store can still dedup the same posting across days. job_url stays NULL
    for synthetic ids (no real id to build the URL from).
    """
    row = dict.fromkeys(JOB_FIELDS)
    for f in ("job_title", "company_name", "logo_url", "job_description", "scrape_dt"):
        row[f] = _null(old.get(f))

    if loc := _null(old.get("location")):
        row.update(parsers.parse_location(loc))

    if jid := _null(old.get("job_id")):
        row["job_id"] = jid
        row["job_url"] = crawler.job_url(jid)
    else:
        key = "|".join(filter(None, [row["job_title"], row["company_name"], row["location"]])) \
            or (row["job_description"] or "")[:500]
        if not key:
            return None  # truly empty row — nothing to identify it by
        row["job_id"] = "v1-" + hashlib.sha1(key.encode()).hexdigest()[:16]

    # v1 'salary' held whatever card line 3 was: real salary, benefits, or junk.
    if sal := _null(old.get("salary")):
        if parsed := parsers.parse_salary(sal):
            row.update(parsed)
        elif any(w in sal.lower() for w in parsers._BENEFIT_WORDS):
            row["benefits"] = re.sub(r"\s*benefits?$", "", sal).strip()
    return row


def phase_tag():
    from huggingface_hub import HfApi

    api = HfApi()
    tags = [t.name for t in api.list_repo_refs(config.HF_REPO_ID, repo_type="dataset").tags]
    if "v1-schema" in tags:
        log.info("Tag v1-schema already exists")
        return
    api.create_tag(config.HF_REPO_ID, tag="v1-schema", repo_type="dataset", token=export_token())
    log.info("Tagged current HF revision as v1-schema")


def export_token() -> str:
    return boto3.client("ssm", region_name=config.SSM_REGION).get_parameter(
        Name=config.SSM_HF_TOKEN, WithDecryption=True
    )["Parameter"]["Value"]


def phase_archive():
    subprocess.run(["aws", "s3", "sync", config.S3_PREFIX, RAW_V1], check=True)
    n = subprocess.run(["aws", "s3", "ls", RAW_V1 + "/"], check=True, capture_output=True, text=True)
    count = len(n.stdout.strip().splitlines())
    log.info("Archived to %s: %d objects", RAW_V1, count)


def phase_fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    subprocess.run(["aws", "s3", "sync", config.S3_PREFIX, str(CACHE)], check=True)
    log.info("Fetched %d CSVs to %s", len(list(CACHE.glob("*.csv"))), CACHE)


def phase_transform():
    MIGRATED.mkdir(parents=True, exist_ok=True)
    files = sorted(CACHE.glob("*.csv"))
    total = salary_hits = benefit_hits = synthetic = empty = dupes = 0
    for f in files:
        df = pd.read_csv(f, dtype=str)
        if "scrape_dt" not in df.columns:  # one 2025 file lacks it — derive from filename
            df["scrape_dt"] = f.stem.replace("linkedin-scrape_", "")
        assert list(df.columns) == V1_COLS, f"{f.name}: unexpected columns {list(df.columns)}"
        rows = [r for r in (transform_row(x) for x in df.to_dict("records")) if r is not None]
        empty += len(df) - len(rows)
        out = pd.DataFrame(rows, columns=JOB_FIELDS).drop_duplicates("job_id", keep="first")
        dupes += len(rows) - len(out)
        out.to_csv(MIGRATED / f.name, index=False)
        total += len(out)
        synthetic += out["job_id"].str.startswith("v1-").sum()
        salary_hits += out["salary_min"].notna().sum()
        benefit_hits += out["benefits"].notna().sum()
    log.info("Transformed %d files: %d rows kept (%d synthetic ids) | dropped: %d empty, %d intra-file dupes | "
             "salary parsed: %.1f%% | benefits recovered: %.1f%%",
             len(files), total, synthetic, empty, dupes, 100 * salary_hits / total, 100 * benefit_hits / total)


_SEED_SQL = f"""
INSERT INTO jobs ({", ".join(JOB_FIELDS)}, first_seen, last_seen, times_seen)
VALUES ({", ".join(f":{f}" for f in JOB_FIELDS)}, :first_seen, :last_seen, :times_seen)
ON CONFLICT(job_id) DO UPDATE SET
    first_seen = MIN(jobs.first_seen, excluded.first_seen),
    last_seen = MAX(jobs.last_seen, excluded.last_seen),
    times_seen = jobs.times_seen + excluded.times_seen
"""  # existing (richer, live-scraped) field values deliberately win on conflict


def phase_seed():
    frames = [pd.read_csv(f, dtype=str) for f in sorted(MIGRATED.glob("*.csv"))]
    rows = pd.concat(frames, ignore_index=True).sort_values("scrape_dt", kind="stable")
    latest = rows.groupby("job_id", as_index=False).last()
    seen = rows.groupby("job_id")["scrape_dt"].agg(first_seen="min", last_seen="max", times_seen="count")
    merged = latest.merge(seen, on="job_id").where(lambda d: d.notna(), None)

    conn = store.connect(config.DB_PATH)
    before = store.stats(conn)["jobs"]
    conn.executemany(_SEED_SQL, merged.to_dict("records"))
    conn.commit()
    log.info("Seeded store: %d unique historical jobs (%d rows total) | store: %d → %d",
             len(merged), len(rows), before, store.stats(conn)["jobs"])


def phase_s3_up():
    subprocess.run(["aws", "s3", "sync", str(MIGRATED), config.S3_PREFIX], check=True)
    log.info("Uploaded %d migrated CSVs to %s", len(list(MIGRATED.glob("*.csv"))), config.S3_PREFIX)


def phase_hf_push():
    import datasets

    datasets.disable_progress_bars()
    splits = {}
    features = None
    for f in sorted(MIGRATED.glob("*.csv")):
        split = f.stem.replace("linkedin-scrape_", "").replace("-", "_")
        df = export.public_view(pd.read_csv(f, dtype=str))
        if df.empty:
            log.warning("%s: empty after junk-row cleanup, skipping split", f.name)
            continue
        df = df.where(df.notna(), None)  # real nulls in parquet, not "nan" strings
        # explicit all-string schema — all-None columns must not infer as 'null'
        features = features or datasets.Features({c: datasets.Value("string") for c in df.columns})
        splits[split] = datasets.Dataset.from_pandas(df, preserve_index=False, features=features)
    log.info("Pushing %d splits to %s (one commit, may take a while)...", len(splits), config.HF_REPO_ID)
    datasets.DatasetDict(splits).push_to_hub(config.HF_REPO_ID, token=export_token())
    log.info("Pushed")


def phase_card():
    # Must run AFTER hf-push: push_to_hub rewrites the README YAML with an
    # auto-generated per-split config, which this upload overrides.
    from huggingface_hub import HfApi

    HfApi().upload_file(path_or_fileobj=config.HF_README_PATH, path_in_repo="README.md",
                        repo_id=config.HF_REPO_ID, repo_type="dataset", token=export_token())
    log.info("Dataset card uploaded")


PHASES = {"tag": phase_tag, "archive": phase_archive, "fetch": phase_fetch, "transform": phase_transform,
          "seed": phase_seed, "s3-up": phase_s3_up, "hf-push": phase_hf_push, "card": phase_card}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=[*PHASES, "all"])
    phase = p.parse_args().phase
    for name in PHASES if phase == "all" else [phase]:
        log.info("=== phase: %s ===", name)
        PHASES[name]()


if __name__ == "__main__":
    main()
