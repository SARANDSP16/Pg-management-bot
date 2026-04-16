"""
handlers/checkout.py — UC-P5: Checkout / Refund

Flow:
  1. Extract name, resolve to ACTIVE resident
  2. Score confidence
  3. If HIGH → present confirmation keyboard (CONFIRM required — no silent mutation)
  4. On CONFIRM callback → compute refund, mark VACATED, free bed
"""
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from intent.entities import extract_name_raw, resolve_name
from utils.confidence import score_checkout, Confidence
from utils.formatters import (
    fmt_checkout_confirm, fmt_checkout_done,
    fmt_ask_name, fmt_ask_pick, fmt_no_resident, fmt_error
)
from db.queries import checkout_resident, compute_refund


class CheckoutResult:
    def __init__(self, text: str, keyboard=None, done: bool = False,
                 pending_state: Optional[dict] = None):
        self.text = text
        self.keyboard = keyboard
        self.done = done
        self.pending_state = pending_state


async def handle_checkout(raw_text: str, user_id: int) -> CheckoutResult:
    """Entry point for UC-P5. Returns confirmation prompt or error."""
    raw_name = extract_name_raw(raw_text)

    if not raw_name:
        return CheckoutResult(text=fmt_ask_name(), pending_state={"awaiting": "name_for_checkout"})

    candidates = await resolve_name(raw_name)
    confidence = score_checkout(raw_name, candidates)

    if confidence == Confidence.LOW:
        return CheckoutResult(text=fmt_no_resident(raw_name))

    if confidence == Confidence.MEDIUM and len(candidates) > 1:
        return CheckoutResult(
            text=fmt_ask_pick(candidates),
            pending_state={
                "awaiting": "pick_resident_for_checkout",
                "candidates": [str(c["_id"]) for c in candidates],
            }
        )

    resident = candidates[0]
    return _build_confirm_prompt(resident)


def _build_confirm_prompt(resident: dict) -> CheckoutResult:
    refund = compute_refund(resident)
    resident_id = str(resident["_id"])

    text = fmt_checkout_confirm(
        name=resident["name"],
        refund=refund,
        pending=resident.get("pending_rent", 0),
        advance=resident.get("advance", 0),
        maintenance=resident.get("maintenance", 0),
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm Checkout", callback_data=f"checkout_confirm:{resident_id}"),
        InlineKeyboardButton("❌ Cancel",           callback_data="checkout_cancel"),
    ]])
    return CheckoutResult(
        text=text,
        keyboard=keyboard,
        done=False,
        pending_state={"awaiting": "checkout_confirm", "resident_id": resident_id}
    )


async def execute_checkout(resident: dict) -> str:
    """Called after user confirms via callback button."""
    try:
        refund = await checkout_resident(resident)
        return fmt_checkout_done(resident["name"], refund)
    except Exception as e:
        return fmt_error(f"Checkout failed: {e}")
