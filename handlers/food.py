"""
handlers/food.py — UC-P7: Food / Waste Log
"""
from utils.formatters import fmt_food_ok, fmt_error
from db.queries import log_food


async def handle_food(raw_text: str, user_id: int) -> str:
    # Keep the full message as note (strip known trigger words)
    triggers = ["food", "waste", "meal", "breakfast", "lunch", "dinner", "diet"]
    note = raw_text.strip()
    for t in triggers:
        note = note.replace(t, "").strip()
    note = note if note else raw_text.strip()

    try:
        await log_food(user_id=user_id, note=note or None)
        return fmt_food_ok(note or None)
    except Exception as e:
        return fmt_error(f"Could not log food entry: {e}")
