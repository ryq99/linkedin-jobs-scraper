"""Local (Ollama) skill/competency extraction pipeline.

Synchronous loop — no Batch API. For each posting that needs extraction, ask the
local model to fill the JobSkills schema (enforced via Ollama's structured-output
`format`), validate the result with Pydantic, stamp provenance we own, and bulk-
write in chunks. Resumable: `store.candidates` re-derives the outstanding set, so
a killed run just leaves rows for the next.
"""

import json
import logging
import time
from datetime import datetime, timezone

import ollama

import config
import prompt
import store
from schema import JobSkills

log = logging.getLogger("extract")

# The model fills the JobSkills fields except these — job_id comes from the DB and
# provenance is stamped by us, so they're pruned from the schema the model sees.
_OWNED_FIELDS = {"job_id", "extract_model", "extract_dt", "schema_version"}


def _model_schema() -> dict:
    """JobSkills' JSON schema minus the fields we own — the extraction contract
    handed to Ollama's `format`. Enum `$defs` stay (still referenced by the kept
    fields), so the model is constrained to valid enum values."""
    schema = JobSkills.model_json_schema()
    schema["properties"] = {k: v for k, v in schema["properties"].items() if k not in _OWNED_FIELDS}
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in _OWNED_FIELDS]
    return schema


_FORMAT = _model_schema()


def make_client() -> ollama.Client:
    """Ollama client bound to the configured host + per-request timeout."""
    return ollama.Client(host=config.OLLAMA_HOST, timeout=config.REQUEST_TIMEOUT)


def extract_one(client: ollama.Client, model: str, job_id: str, description: str) -> JobSkills | None:
    """Extract one posting → validated JobSkills, or None on failure (logged).

    A single bad posting (model error, malformed JSON, schema violation) is
    skipped so it can't kill the run; it reappears in the next candidates() pass.
    """
    messages = [{"role": "system", "content": prompt.SYSTEM}]
    messages += prompt.build_messages(description[: config.MAX_DESCRIPTION_CHARS])
    try:
        resp = client.chat(model=model, messages=messages, format=_FORMAT, options={"temperature": 0})
        # The model fills only the pruned fields; add the ones we own, then let
        # JobSkills validate the whole record (enum/type checks included).
        fields = json.loads(resp.message.content)
        fields.update(
            job_id=job_id,
            extract_model=model,
            extract_dt=datetime.now(timezone.utc).isoformat(),
        )
        return JobSkills.model_validate(fields)
    except Exception as e:  # ollama/network error, invalid JSON, or schema violation
        log.warning("job %s extraction failed: %s", job_id, e)
        return None


def run(conn, limit: int | None = None, model: str | None = None) -> int:
    """Extract all candidate postings; bulk-write every COMMIT_CHUNK. Returns count."""
    model = model or config.OLLAMA_MODEL
    rows = store.candidates(conn, limit=limit)
    log.info("Extract | model=%s | %d postings to process", model, len(rows))

    client = make_client()
    deadline = time.monotonic() + config.MAX_RUN_SECONDS
    buffer: list[JobSkills] = []
    written = failed = 0
    for i, (job_id, description) in enumerate(rows, 1):
        if time.monotonic() > deadline:
            log.warning("run budget (%ds) reached at %d/%d — stopping", config.MAX_RUN_SECONDS, i - 1, len(rows))
            break
        record = extract_one(client, model, job_id, description)
        if record is None:
            failed += 1
            continue
        buffer.append(record)
        if len(buffer) >= config.COMMIT_CHUNK:
            written += store.write_skills(conn, buffer)
            buffer.clear()
            log.info("progress %d/%d (written=%d failed=%d)", i, len(rows), written, failed)
    if buffer:
        written += store.write_skills(conn, buffer)
    log.info("Done: wrote %d, failed %d, of %d candidates", written, failed, len(rows))
    return written
