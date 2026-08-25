"""Load the committed example settings so config (which requires every key) can
import during tests/CI without a real .env present."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.example")
