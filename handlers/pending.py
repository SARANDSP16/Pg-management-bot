"""
handlers/pending.py — UC-P4: Pending Payments List

Returns list of all active residents with pending_rent > 0.
Summarizes if list exceeds MAX_PENDING_LIST.
"""
from db.queries import get_pending_residents
from utils.formatters import fmt_pending_list, fmt_pending_summary
from config import MAX_PENDING_LIST


async def handle_pending() -> str:
    residents = await get_pending_residents()

    if not residents:
        return "✅ No pending dues! Everyone is up to date."

    total = sum(r.get("pending_rent", 0) for r in residents)

    if len(residents) > MAX_PENDING_LIST:
        return fmt_pending_summary(len(residents), total)

    return fmt_pending_list(residents)
