"""
handlers/info_query.py — UC-P8: Informational Queries

Handles:
  - "[Name] details" / "[Name] info"
  - "rent?" / "who is [Name]?"
  - General stats
"""
from intent.entities import extract_name_raw, resolve_name
from utils.confidence import score_info, Confidence
from utils.formatters import (
    fmt_resident_info, fmt_ask_name, fmt_ask_pick, fmt_no_resident
)


async def handle_info_query(raw_text: str) -> str:
    raw_name = extract_name_raw(raw_text)

    # No name → return general stats
    if not raw_name:
        return await _general_stats()

    candidates = await resolve_name(raw_name)
    confidence = score_info(raw_name, candidates)

    if confidence == Confidence.LOW:
        return fmt_no_resident(raw_name)

    if confidence == Confidence.MEDIUM and len(candidates) > 1:
        return fmt_ask_pick(candidates)

    if confidence == Confidence.MEDIUM and len(candidates) == 0:
        return fmt_no_resident(raw_name)

    # HIGH — single match
    resident = candidates[0]
    return fmt_resident_info(resident)


async def _general_stats() -> str:
    from db.queries import get_all_rooms, get_all_active_residents, get_pending_residents
    rooms = await get_all_rooms()
    active = await get_all_active_residents()
    pending = await get_pending_residents()

    total_beds = sum(r.get("total_beds", 0) for r in rooms)
    occupied = sum(r.get("occupied_beds", 0) for r in rooms)
    available = total_beds - occupied
    pending_total = sum(r.get("pending_rent", 0) for r in pending)

    return (
        f"🏠 *PG Overview*\n\n"
        f"  Total Beds     : {total_beds}\n"
        f"  Occupied       : {occupied}\n"
        f"  Available      : {available}\n"
        f"  Active Residents: {len(active)}\n"
        f"  Pending Dues   : {len(pending)} residents  (₹{pending_total:,.0f} total)"
    )
