"""
handlers/payment.py — UC-P2: Record Payment

Flow:
  1. Extract name + amount from message
  2. Fuzzy-match name → resolve to resident(s)
  3. Score confidence
  4. HIGH → record payment (idempotency-safe)
  5. MEDIUM → ask clarifying question
  6. LOW → block + explain
"""
from typing import Optional
from intent.entities import extract_amount, extract_name_raw, resolve_name
from utils.confidence import score_payment, Confidence
from utils.formatters import (
    fmt_payment_ok, fmt_payment_duplicate, fmt_ask_amount,
    fmt_ask_name, fmt_ask_pick, fmt_no_resident, fmt_error
)
from db.queries import record_payment


class PaymentResult:
    def __init__(self, text: str, done: bool = False,
                 pending_state: Optional[dict] = None):
        self.text = text
        self.done = done                    # True → action completed
        self.pending_state = pending_state  # State to store for multi-turn


async def handle_payment(raw_text: str, user_id: int) -> PaymentResult:
    """
    Main UC-P2 handler. Returns a PaymentResult describing the outcome.
    """
    amount = extract_amount(raw_text)
    raw_name = extract_name_raw(raw_text)

    # ── Missing name ────────────────────────────────────────────────────────
    if not raw_name:
        return PaymentResult(text=fmt_ask_name(), done=False,
                             pending_state={"awaiting": "name_for_payment",
                                            "amount": amount})

    candidates = await resolve_name(raw_name)
    confidence = score_payment(raw_name, amount, candidates)

    # ── MEDIUM: missing amount ──────────────────────────────────────────────
    if confidence == Confidence.MEDIUM and not amount:
        name_display = candidates[0]["name"] if len(candidates) == 1 else raw_name
        return PaymentResult(
            text=fmt_ask_amount(name_display),
            done=False,
            pending_state={
                "awaiting": "amount_for_payment",
                "resident_id": str(candidates[0]["_id"]) if len(candidates) == 1 else None,
                "candidates": [str(c["_id"]) for c in candidates],
                "raw_name": raw_name,
            }
        )

    # ── MEDIUM: multiple residents ──────────────────────────────────────────
    if confidence == Confidence.MEDIUM and len(candidates) > 1:
        return PaymentResult(
            text=fmt_ask_pick(candidates),
            done=False,
            pending_state={
                "awaiting": "pick_resident_for_payment",
                "candidates": [str(c["_id"]) for c in candidates],
                "amount": amount,
            }
        )

    # ── LOW: no resident found ──────────────────────────────────────────────
    if confidence == Confidence.LOW:
        return PaymentResult(text=fmt_no_resident(raw_name), done=False)

    # ── HIGH: proceed ───────────────────────────────────────────────────────
    resident = candidates[0]
    try:
        await record_payment(resident, amount, recorded_by=user_id)
        new_pending = max(0.0, resident.get("pending_rent", 0) - amount)
        return PaymentResult(
            text=fmt_payment_ok(resident["name"], amount, new_pending),
            done=True
        )
    except ValueError as e:
        if "DUPLICATE" in str(e):
            return PaymentResult(
                text=fmt_payment_duplicate(resident["name"], amount),
                done=False
            )
        return PaymentResult(text=fmt_error(str(e)), done=False)
    except Exception as e:
        return PaymentResult(text=fmt_error(f"Could not record payment: {e}"), done=False)


async def handle_payment_with_resident(resident: dict, amount: float, user_id: int) -> str:
    """
    Called after multi-turn resolution (e.g. user replied with amount or picked resident).
    """
    try:
        await record_payment(resident, amount, recorded_by=user_id)
        new_pending = max(0.0, resident.get("pending_rent", 0) - amount)
        return fmt_payment_ok(resident["name"], amount, new_pending)
    except ValueError as e:
        if "DUPLICATE" in str(e):
            return fmt_payment_duplicate(resident["name"], amount)
        return fmt_error(str(e))
    except Exception as e:
        return fmt_error(f"Could not record payment: {e}")
