"""info_extractor entry point: python src/main.py extract [...].

Run from the component dir (pytest/pythonpath = src), e.g.
    python info_extractor/src/main.py extract --limit 5
Requires a running Ollama daemon with the configured model pulled.
"""

import argparse
import logging

import config
import export
import extract
import prompt
import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("main")


def cmd_extract(args) -> int:
    conn = store.connect(config.DB_PATH)
    model = args.model or config.OLLAMA_MODEL

    if args.dry_run:
        rows = store.candidates(conn, limit=args.limit, since=args.since)
        print(f"model         : {model}")
        print(f"candidates    : {len(rows)} postings need extraction")
        if rows:
            job_id, description = rows[0]
            messages = [{"role": "system", "content": prompt.SYSTEM}]
            messages += prompt.build_messages(description[: config.MAX_DESCRIPTION_CHARS])
            print(f"\n--- sample request (job {job_id}) ---")
            for m in messages:
                print(f"[{m['role']}]\n{m['content'][:600]}\n")
        return 0

    extract.run(conn, limit=args.limit, model=args.model, since=args.since)
    if not args.no_export:  # publish any date whose job_skills changed (self-heal)
        n = export.export_dates_to_s3(conn, store.dates_needing_export(conn))
        log.info("S3: exported %d job_skills rows across changed dates", n)
    return 0


def cmd_export(args) -> int:
    conn = store.connect(config.DB_PATH)
    dates = store.export_dates(conn) if args.rebuild else store.dates_needing_export(conn)
    n = export.export_dates_to_s3(conn, dates)
    log.info("Exported %d job_skills rows across %d date files", n, len(dates))
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="info_extractor", description="Local LLM job-skill extraction")
    sub = p.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract", help="Extract JobSkills from postings needing it")
    ex.add_argument("--limit", type=int, default=None, help="Max postings this run (default: all)")
    ex.add_argument("--since", default=None, help="Only postings first seen on/after YYYY-MM-DD (newest first)")
    ex.add_argument("--model", default=None, help="Override OLLAMA_MODEL for this run")
    ex.add_argument("--dry-run", action="store_true", help="Show candidate count + one rendered request; no inference")
    ex.add_argument("--no-export", action="store_true", help="Skip the S3 publish after extraction")

    xp = sub.add_parser("export", help="Publish job_skills date-files to S3 (changed dates; --rebuild for all)")
    xp.add_argument("--rebuild", action="store_true", help="Export every date file, not just changed ones")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "export":
        return cmd_export(args)
    return cmd_extract(args)


if __name__ == "__main__":
    raise SystemExit(main())
