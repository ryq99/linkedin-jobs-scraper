"""info_extractor entry point: python src/main.py extract [...].

Run from the component dir (pytest/pythonpath = src), e.g.
    python info_extractor/src/main.py extract --limit 5
Requires a running Ollama daemon with the configured model pulled.
"""

import argparse
import logging

import config
import extract
import prompt
import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("main")


def cmd_extract(args) -> int:
    conn = store.connect(config.DB_PATH)
    model = args.model or config.OLLAMA_MODEL

    if args.dry_run:
        rows = store.candidates(conn, limit=args.limit)
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

    extract.run(conn, limit=args.limit, model=args.model)
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="info_extractor", description="Local LLM job-skill extraction")
    sub = p.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("extract", help="Extract JobSkills from postings needing it")
    ex.add_argument("--limit", type=int, default=None, help="Max postings this run (default: all)")
    ex.add_argument("--model", default=None, help="Override OLLAMA_MODEL for this run")
    ex.add_argument("--dry-run", action="store_true", help="Show candidate count + one rendered request; no inference")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    return cmd_extract(args)


if __name__ == "__main__":
    raise SystemExit(main())
