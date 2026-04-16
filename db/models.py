"""
db/models.py — Pydantic v2 data models (schemas) for all collections.
These are used for validation on write and for type hints throughout the app.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


# ─── Enums ──────────────────────────────────────────────────────────────────

class ResidentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NOTICE_GIVEN = "NOTICE_GIVEN"
    VACATED = "VACATED"


# ─── Room ───────────────────────────────────────────────────────────────────

class Room(BaseModel):
    building: str
    room_no: str
    total_beds: int
    occupied_beds: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def available_beds(self) -> int:
        return self.total_beds - self.occupied_beds

    @property
    def is_full(self) -> bool:
        return self.occupied_beds >= self.total_beds


# ─── Resident ───────────────────────────────────────────────────────────────

class Resident(BaseModel):
    name: str
    phone: str
    building: str
    room_no: str
    bed_no: str
    rent: float                  # monthly rent amount
    advance: float = 0.0         # security deposit paid
    maintenance: float = 0.0     # monthly maintenance charge
    damages: float = 0.0         # one-time damage charge (set at checkout)
    pending_rent: float = 0.0    # outstanding dues
    status: ResidentStatus = ResidentStatus.ACTIVE
    rent_cycle_day: int = 1      # day of month rent is due (1–28)
    admitted_on: datetime = Field(default_factory=datetime.utcnow)
    vacated_on: Optional[datetime] = None


# ─── Payment ────────────────────────────────────────────────────────────────

class Payment(BaseModel):
    resident_id: str             # MongoDB _id of resident (as string)
    resident_name: str
    amount: float
    date: str                    # YYYY-MM-DD — used in idempotency fingerprint
    fingerprint: str             # SHA256(resident_id + amount + date)
    recorded_by: int             # Telegram user_id of who recorded
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    note: Optional[str] = None


# ─── Cleaning Log ────────────────────────────────────────────────────────────

class CleaningLog(BaseModel):
    building: Optional[str] = None
    room_no: str
    logged_by: int               # Telegram user_id
    logged_at: datetime = Field(default_factory=datetime.utcnow)
    note: Optional[str] = None


# ─── Food Log ────────────────────────────────────────────────────────────────

class FoodLog(BaseModel):
    note: Optional[str] = None
    logged_by: int
    logged_at: datetime = Field(default_factory=datetime.utcnow)


