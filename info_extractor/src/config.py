"""Configuration for the info_extractor component.

Every operational setting is read from info_extractor/.env (see .env.example) —
there are no in-code defaults, so a missing key fails loudly at import instead of
silently running on a guessed value. Extraction runs on a local Ollama model, so
there is no API key or cost — just a running daemon with the model pulled.
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

# Local LLM (Ollama) — free, private, no API key.
OLLAMA_HOST = _require("OLLAMA_HOST")
OLLAMA_MODEL = _require("OLLAMA_MODEL")

# Request / run tuning.
MAX_DESCRIPTION_CHARS = int(_require("EXTRACT_MAX_DESC_CHARS"))    # trim to bound input tokens
NUM_PREDICT = int(_require("EXTRACT_NUM_PREDICT"))                # cap output tokens (stops runaway lists)
REQUEST_TIMEOUT = int(_require("EXTRACT_REQUEST_TIMEOUT"))        # per-posting inference cap (s)
COMMIT_CHUNK = int(_require("EXTRACT_COMMIT_CHUNK"))              # rows written per transaction
MAX_RUN_SECONDS = int(_require("EXTRACT_MAX_RUN_SECONDS"))         # whole-run wall-clock cap
