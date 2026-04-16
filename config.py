"""
config.py — Central configuration loader.
All modules import from here, never from os.environ directly.
"""
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── Telegram ───────────────────────────────────────────────
BOT_TOKEN: str = os.environ["BOT_TOKEN"]

# ─── MongoDB ────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB: str = os.getenv("MONGO_DB", "pg_management")

# ─── Groq ───────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ─── Personas (Authorized Phones) ───────────────────────────
def _parse_phones(env_key: str) -> set[str]:
    raw = os.getenv(env_key, "")
    # Remove any spaces, dashes, or + signs
    return {
        "".join(filter(str.isdigit, x.strip())) 
        for x in raw.split(",") if x.strip()
    }

OWNER_PHONES: set[str] = _parse_phones("OWNER_PHONES")
MANAGER_PHONES: set[str] = _parse_phones("MANAGER_PHONES")
ALL_AUTHORIZED_PHONES: set[str] = OWNER_PHONES | MANAGER_PHONES

# ─── Business Rules ─────────────────────────────────────────
SESSION_EXPIRY_MINUTES: int = 30   # form session timeout
MAX_PENDING_LIST: int = 10         # summarize if more than this
