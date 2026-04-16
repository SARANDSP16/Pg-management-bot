"""
intent/entities.py — Extract structured entities from raw Telegram messages.

Extracted entities:
  name    → string (fuzzy matched against resident DB)
  amount  → float  (must be explicit, never guessed)
  room_no → string
  building → string
"""
import re
from typing import Optional
from fuzzywuzzy import process


# ─── Amount Extraction ───────────────────────────────────────────────────────

_AMOUNT_PATTERNS = [
    r"(?:rs\.?|₹|inr)?\s*(\d[\d,]*(?:\.\d{1,2})?)",  # ₹5000 / rs 5000 / 5000
]


def extract_amount(text: str) -> Optional[float]:
    """
    Extract the first explicit amount from the message.
    Returns None if no numeric amount found — NEVER guesses.
    """
    for pattern in _AMOUNT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Take first valid number
            for m in matches:
                cleaned = m.replace(",", "")
                try:
                    val = float(cleaned)
                    if val > 0:
                        return val
                except ValueError:
                    continue
    return None


# ─── Room / Building Extraction ──────────────────────────────────────────────

def extract_room_no(text: str) -> Optional[str]:
    """
    Extract room number like '102', 'room 102', 'rm-5'.
    """
    patterns = [
        r"room\s*#?\s*(\w+)",
        r"rm\s*[-#]?\s*(\w+)",
        r"\bR(\d+)\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()

    # Fallback: standalone number if text mentions 'room'
    if "room" in text.lower() or "rm" in text.lower():
        nums = re.findall(r"\b(\d{2,4})\b", text)
        if nums:
            return nums[0]
    return None


def extract_building(text: str) -> Optional[str]:
    """
    Extract building name/letter (A, B, Block-A, Building 2 etc.)
    """
    m = re.search(
        r"\b(?:block|building|blk)[\s\-]*([a-zA-Z0-9]+)\b",
        text, re.IGNORECASE
    )
    if m:
        return m.group(1).upper()
    # Single capital letter standing alone (e.g. 'A block')
    m2 = re.search(r"\b([A-Z])\s*block\b", text, re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    return None


# ─── Name Extraction ─────────────────────────────────────────────────────────

# Words to skip when trying to extract a name
_STOP_WORDS = {
    "paid", "vacated", "left", "checked", "out", "details", "info",
    "new", "admission", "room", "cleaning", "cleaned", "food", "waste",
    "pending", "available", "who", "what", "how", "did", "pay", "is",
    "the", "and", "for", "from", "a", "an", "ok", "yes", "no", "hi",
    "hello", "please", "can", "you", "me", "my", "our", "their","₹",
}

def extract_name_raw(text: str) -> Optional[str]:
    """
    Heuristic name extraction from raw message text.
    Returns the most likely candidate word/phrase (not yet validated).
    """
    # Remove amounts and common tokens
    cleaned = re.sub(r"(?:rs\.?|₹|inr)?\s*\d[\d,]*(?:\.\d+)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    tokens = [t for t in cleaned.split() if t.lower() not in _STOP_WORDS and len(t) > 1]

    if not tokens:
        return None

    # Capitalize as a proper name
    # Try to pick the first capitalized word, else just first token
    for t in tokens:
        if t[0].isupper():
            return t
    return tokens[0].capitalize()


async def resolve_name(raw_name: str) -> list[dict]:
    """
    Fuzzy match raw_name against all active residents in DB.
    Returns list of matching resident dicts sorted by score.
    """
    from db.queries import get_all_active_residents
    residents = await get_all_active_residents()
    if not residents:
        return []

    names = [r["name"] for r in residents]
    results = process.extract(raw_name, names, limit=5)

    # Accept matches with score >= 70
    matched = []
    for (matched_name, score) in results:
        if score >= 70:
            for r in residents:
                if r["name"] == matched_name:
                    matched.append(r)
                    break
    return matched


# ─── Note Extraction (for food/cleaning logs) ────────────────────────────────

def extract_note(text: str, after_keyword: str) -> Optional[str]:
    """
    Extract freeform note after a keyword.
    e.g. extract_note("food waste high today", "food") → "waste high today"
    """
    idx = text.lower().find(after_keyword.lower())
    if idx == -1:
        return None
    note = text[idx + len(after_keyword):].strip()
    return note if note else None
