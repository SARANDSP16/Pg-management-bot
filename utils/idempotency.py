"""
utils/idempotency.py — Payment deduplication.

A SHA-256 fingerprint is generated from (resident_id, amount, date).
Before inserting any payment, check if the fingerprint already exists.
Same message sent twice → same fingerprint → duplicate rejected.
"""
import hashlib
from datetime import date


def generate_payment_fingerprint(resident_id: str, amount: float, payment_date: date | None = None) -> str:
    """
    Generate a deterministic fingerprint for a payment.
    Uses today's date if payment_date is not given.
    """
    if payment_date is None:
        payment_date = date.today()

    date_str = payment_date.strftime("%Y-%m-%d")
    raw = f"{resident_id}:{amount:.2f}:{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()
