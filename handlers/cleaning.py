"""
handlers/cleaning.py — UC-P6: Cleaning Log
"""
from intent.entities import extract_room_no, extract_building, extract_note
from utils.confidence import score_cleaning, Confidence
from utils.formatters import fmt_cleaning_ok, fmt_error
from db.queries import log_cleaning


async def handle_cleaning(raw_text: str, user_id: int) -> str:
    room_no = extract_room_no(raw_text)
    building = extract_building(raw_text)
    note = extract_note(raw_text, "cleaned")

    if score_cleaning(room_no) == Confidence.MEDIUM:
        return "🧹 Which room was cleaned? (e.g., 'room 102 cleaned')"

    try:
        await log_cleaning(room_no=room_no, user_id=user_id,
                           building=building, note=note)
        return fmt_cleaning_ok(room_no)
    except Exception as e:
        return fmt_error(f"Could not log cleaning: {e}")
