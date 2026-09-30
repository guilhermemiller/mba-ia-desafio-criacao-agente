import os
import re

from dotenv import load_dotenv

load_dotenv()


def normalize_model_name(raw_name: str) -> str:
    value = (raw_name or "freecoding").strip()
    if not value:
        return "freecoding"

    if "/" in value or ":" in value or "." in value:
        return value.lower()

    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "freecoding"


# OpenAI-compatible local server support (e.g. LM Studio / local API proxy)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv(
    "OPENAI_BASE_URL", os.getenv("OPENAI_API_BASE", "http://localhost:20128/v1")
)
if OPENAI_API_KEY:
    os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY)
if OPENAI_BASE_URL:
    os.environ.setdefault("OPENAI_BASE_URL", OPENAI_BASE_URL)
    os.environ.setdefault("OPENAI_API_BASE", OPENAI_BASE_URL)

DATABASE_PATH = os.getenv("DATABASE_PATH", "aurora.db")
PORT = int(os.getenv("PORT", "8000"))
MODEL_NAME = normalize_model_name(os.getenv("MODEL_NAME", "freecoding"))
