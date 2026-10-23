import os
import re

from dotenv import load_dotenv

load_dotenv()


def normalize_model_name(raw_name: str) -> str:
    value = (raw_name or "gemini-2.5-flash").strip()
    if not value:
        return "gemini-2.5-flash"

    if "/" in value or ":" in value or "." in value:
        return value.lower()

    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "gemini-2.5-flash"


# Google AI Studio configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "aurora.db")
PORT = int(os.getenv("PORT", "8000"))
MODEL_NAME = normalize_model_name(os.getenv("MODEL_NAME", "gemini-2.5-flash"))