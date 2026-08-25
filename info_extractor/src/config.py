"""Configuration for the info_extractor component.

Every operational setting is read from info_extractor/.env (see .env.example) —
there are no in-code defaults, so a missing key fails loudly at import instead of
silently running on a guessed value. The Anthropic API key is not read here; the
SDK picks it up from the environment at call time (so offline tests and
--dry-run don't need it).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_COMPONENT_DIR = Path(__file__).resolve().parent.parent  # info_extractor/
load_dotenv(_COMPONENT_DIR / ".env")


def _require(name: str) -> str:
    """Return an env setting, or fail loudly if it isn't in .env."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"info_extractor: required setting {name!r} missing from info_extractor/.env")
    return value


# Shared SQLite DB the scraper writes; the .env path is relative to the component
# dir (absolute paths in .env also work).
DB_PATH = (_COMPONENT_DIR / _require("DB_PATH")).resolve()

# Models: Haiku is the daily batch workhorse; Opus audits a validation sample.
EXTRACT_MODEL = _require("EXTRACT_MODEL")
VALIDATION_MODEL = _require("EXTRACT_VALIDATION_MODEL")

# Batch / request tuning.
BATCH_SIZE = int(_require("EXTRACT_BATCH_SIZE"))                    # rows per Batch submission
MAX_OUTPUT_TOKENS = int(_require("EXTRACT_MAX_TOKENS"))            # one JobSkills record is small
MAX_DESCRIPTION_CHARS = int(_require("EXTRACT_MAX_DESC_CHARS"))    # trim to bound input tokens
POLL_SECONDS = int(_require("EXTRACT_POLL_SECONDS"))              # batch-status poll interval
MAX_RUN_SECONDS = int(_require("EXTRACT_MAX_RUN_SECONDS"))         # whole-run wall-clock cap
