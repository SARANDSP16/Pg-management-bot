"""
utils/confidence.py — Confidence scoring for intent + entity quality.

Levels:
  HIGH   → intent clear, all required entities present → AUTO execute
  MEDIUM → intent clear, entity ambiguous or missing → ASK user
  LOW    → intent unclear or conflicting → BLOCK + ask
"""
from enum import Enum
from typing import Optional


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def score_payment(name: Optional[str], amount: Optional[float], candidates: list) -> Confidence:
    """
    Score confidence for UC-P2 (Record Payment).
    Requires BOTH name and amount, and exactly ONE matching resident.
    """
    if not amount:
        return Confidence.MEDIUM   # missing amount → ask
    if not name:
        return Confidence.MEDIUM   # missing name → ask
    if len(candidates) == 0:
        return Confidence.LOW      # no resident found → block
    if len(candidates) > 1:
        return Confidence.MEDIUM   # ambiguous resident → ask to pick
    return Confidence.HIGH


def score_checkout(name: Optional[str], candidates: list) -> Confidence:
    """Score confidence for UC-P5 (Checkout)."""
    if not name:
        return Confidence.MEDIUM
    if len(candidates) == 0:
        return Confidence.LOW
    if len(candidates) > 1:
        return Confidence.MEDIUM
    return Confidence.HIGH         # even HIGH still requires confirmation click


def score_info(name: Optional[str], candidates: list) -> Confidence:
    """Score confidence for UC-P8 (Info Query)."""
    if not name:
        return Confidence.MEDIUM
    if len(candidates) == 0:
        return Confidence.LOW
    if len(candidates) > 1:
        return Confidence.MEDIUM
    return Confidence.HIGH


def score_room(building: Optional[str]) -> Confidence:
    """Room queries are always answerable (may just show all buildings)."""
    return Confidence.HIGH


def score_cleaning(room_no: Optional[str]) -> Confidence:
    if not room_no:
        return Confidence.MEDIUM
    return Confidence.HIGH
