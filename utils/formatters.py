"""
utils/formatters.py — Telegram message formatting helpers.
All messages are plain text (MarkdownV2 escaping included where noted).
"""
from typing import Any


def fmt_payment_ok(name: str, amount: float, pending: float) -> str:
    return (
        f"✅ Payment Recorded\n"
        f"👤 Resident : {name}\n"
        f"💰 Paid     : ₹{amount:,.0f}\n"
        f"📋 Pending  : ₹{pending:,.0f}"
    )


def fmt_payment_duplicate(name: str, amount: float) -> str:
    return (
        f"⚠️ Duplicate detected!\n"
        f"Payment of ₹{amount:,.0f} for {name} was already recorded today.\n"
        f"No changes made."
    )


def fmt_ask_amount(name: str) -> str:
    return f"💬 How much did *{name}* pay? (Please reply with the amount)"


def fmt_ask_name() -> str:
    return "💬 Which resident? Please provide the name."


def fmt_ask_pick(candidates: list[dict]) -> str:
    lines = ["👥 Multiple residents found. Which one do you mean?\n"]
    for i, r in enumerate(candidates, 1):
        lines.append(f"  {i}. {r['name']} — Room {r.get('room_no', '?')} ({r.get('building', '?')})")
    lines.append("\nReply with the number.")
    return "\n".join(lines)


def fmt_room_availability(rooms: list[dict]) -> str:
    if not rooms:
        return "🏠 No rooms available right now.\nAll beds are occupied."
    lines = ["🏠 *Available Rooms*\n"]
    for r in rooms:
        avail = r["total_beds"] - r["occupied_beds"]
        lines.append(
            f"  Building {r['building']} — Room {r['room_no']} : {avail} bed(s) free"
        )
    return "\n".join(lines)


def fmt_pending_list(residents: list[dict]) -> str:
    if not residents:
        return "✅ No pending dues! Everyone is up to date."
    lines = ["📋 *Pending Dues*\n"]
    total = 0.0
    for r in residents:
        due = r.get("pending_rent", 0)
        total += due
        lines.append(f"  • {r['name']} — ₹{due:,.0f}")
    lines.append(f"\n💰 Total Outstanding : ₹{total:,.0f}")
    return "\n".join(lines)


def fmt_pending_summary(count: int, total: float) -> str:
    return (
        f"📋 *Pending Dues Summary*\n"
        f"  {count} residents have pending dues.\n"
        f"  💰 Total Outstanding : ₹{total:,.0f}\n\n"
        f"Reply 'pending details' for the full list."
    )


def fmt_checkout_confirm(name: str, refund: float, pending: float, advance: float, maintenance: float) -> str:
    return (
        f"🔔 *Checkout Confirmation*\n\n"
        f"👤 Resident : {name}\n"
        f"💵 Advance  : ₹{advance:,.0f}\n"
        f"📋 Pending  : ₹{pending:,.0f}\n"
        f"🔧 Maint.   : ₹{maintenance:,.0f}\n"
        f"─────────────────\n"
        f"💰 Refund   : ₹{refund:,.0f}\n\n"
        f"Tap ✅ Confirm or ❌ Cancel below."
    )


def fmt_checkout_done(name: str, refund: float) -> str:
    return (
        f"✅ Checkout Complete\n"
        f"👤 {name} has been marked VACATED.\n"
        f"💰 Refund amount : ₹{refund:,.0f}"
    )


def fmt_cleaning_ok(room_no: str) -> str:
    return f"🧹 Cleaning logged for Room {room_no}."


def fmt_food_ok(note: str | None) -> str:
    note_str = f"\n📝 Note: {note}" if note else ""
    return f"🍱 Food/waste log recorded.{note_str}"


def fmt_resident_info(r: dict) -> str:
    return (
        f"👤 *Resident Info*\n\n"
        f"  Name       : {r.get('name', '—')}\n"
        f"  Phone      : {r.get('phone', '—')}\n"
        f"  Building   : {r.get('building', '—')}\n"
        f"  Room       : {r.get('room_no', '—')}  Bed: {r.get('bed_no', '—')}\n"
        f"  Rent       : ₹{r.get('rent', 0):,.0f}/month\n"
        f"  Advance    : ₹{r.get('advance', 0):,.0f}\n"
        f"  Pending    : ₹{r.get('pending_rent', 0):,.0f}\n"
        f"  Status     : {r.get('status', '—')}\n"
        f"  Admitted   : {str(r.get('admitted_on', '—'))[:10]}"
    )


def fmt_no_resident(name: str) -> str:
    return f"❌ No active resident found with name '{name}'."


def fmt_error(msg: str) -> str:
    return f"⚠️ {msg}"


def fmt_noise() -> str:
    return ""   # silent for noise messages (ok, 👍 etc.)


def fmt_unknown() -> str:
    return (
        "🤔 I didn't understand that.\n\n"
        "Here's what I can help with:\n"
        "  • 'new admission'\n"
        "  • '[Name] paid [amount]'\n"
        "  • 'room available?'\n"
        "  • 'who didn't pay?'\n"
        "  • '[Name] vacated'\n"
        "  • 'room [no] cleaned'\n"
        "  • 'food waste logged'\n"
        "  • '[Name] details'"
    )


def fmt_admission_sent(form_url: str) -> str:
    return (
        f"📋 *New Admission Form*\n\n"
        f"Click the button below to fill in the resident details.\n"
        f"The form will expire in 30 minutes."
    )
