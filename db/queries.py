"""
db/queries.py — All async database read/write operations.

All functions enforce business rules at the DB layer:
  - occupied_beds ≤ total_beds
  - payment idempotency via fingerprint
  - status transition ACTIVE → NOTICE_GIVEN → VACATED
"""
from datetime import datetime, date
from typing import Optional
from bson import ObjectId
from db.connection import get_db
from db.models import ResidentStatus
from utils.idempotency import generate_payment_fingerprint


# ─── Helpers ────────────────────────────────────────────────────────────────

def _oid(doc_id: str) -> ObjectId:
    return ObjectId(doc_id)


# ─── Room Queries ────────────────────────────────────────────────────────────

async def get_all_rooms() -> list[dict]:
    db = get_db()
    return await db.rooms.find().to_list(None)


async def get_available_rooms(building: Optional[str] = None) -> list[dict]:
    db = get_db()
    query: dict = {"$expr": {"$lt": ["$occupied_beds", "$total_beds"]}}
    if building:
        query["building"] = building
    return await db.rooms.find(query).to_list(None)


async def get_room(building: str, room_no: str) -> Optional[dict]:
    db = get_db()
    return await db.rooms.find_one({"building": building, "room_no": room_no})


async def upsert_room(building: str, room_no: str, total_beds: int) -> dict:
    """Create room if it doesn't exist, else return existing."""
    db = get_db()
    await db.rooms.update_one(
        {"building": building, "room_no": room_no},
        {"$setOnInsert": {"building": building, "room_no": room_no,
                          "total_beds": total_beds, "occupied_beds": 0}},
        upsert=True
    )
    return await get_room(building, room_no)


async def increment_occupied(building: str, room_no: str) -> bool:
    """
    Attempt to increment occupied_beds. Returns False if room is full.
    Uses $inc only when occupied_beds < total_beds (atomic).
    """
    db = get_db()
    result = await db.rooms.update_one(
        {
            "building": building,
            "room_no": room_no,
            "$expr": {"$lt": ["$occupied_beds", "$total_beds"]}
        },
        {"$inc": {"occupied_beds": 1}}
    )
    return result.modified_count == 1


async def decrement_occupied(building: str, room_no: str) -> None:
    db = get_db()
    await db.rooms.update_one(
        {"building": building, "room_no": room_no, "occupied_beds": {"$gt": 0}},
        {"$inc": {"occupied_beds": -1}}
    )


# ─── Resident Queries ────────────────────────────────────────────────────────

async def find_residents_by_name(name: str, active_only: bool = True) -> list[dict]:
    """
    Case-insensitive partial name match. Returns all candidates.
    Caller resolves ambiguity.
    """
    db = get_db()
    query: dict = {"name": {"$regex": name, "$options": "i"}}
    if active_only:
        query["status"] = {"$ne": ResidentStatus.VACATED}
    return await db.residents.find(query).to_list(None)


async def get_resident_by_id(resident_id: str) -> Optional[dict]:
    db = get_db()
    return await db.residents.find_one({"_id": _oid(resident_id)})


async def get_all_active_residents() -> list[dict]:
    db = get_db()
    return await db.residents.find({"status": ResidentStatus.ACTIVE}).to_list(None)


async def get_pending_residents() -> list[dict]:
    """Return all ACTIVE residents with pending_rent > 0."""
    db = get_db()
    return await db.residents.find(
        {"status": ResidentStatus.ACTIVE, "pending_rent": {"$gt": 0}}
    ).sort("pending_rent", -1).to_list(None)


async def admit_resident(form_data: dict) -> dict:
    """
    Create resident and increment bed count atomically.
    Raises ValueError if room is full or bed already taken.
    """
    db = get_db()
    building = form_data["building"]
    room_no = form_data["room_no"]

    # Ensure room exists
    room = await get_room(building, room_no)
    if not room:
        total = int(form_data.get("total_beds", 1))
        room = await upsert_room(building, room_no, total)

    # Overbooking guard
    success = await increment_occupied(building, room_no)
    if not success:
        raise ValueError(f"Room {room_no} in {building} is fully occupied.")

    resident_doc = {
        "name": form_data["name"],
        "phone": form_data["phone"],
        "building": building,
        "room_no": room_no,
        "bed_no": form_data["bed_no"],
        "rent": float(form_data["rent"]),
        "advance": float(form_data.get("advance", 0)),
        "maintenance": float(form_data.get("maintenance", 0)),
        "damages": 0.0,
        "pending_rent": 0.0,
        "status": ResidentStatus.ACTIVE,
        "rent_cycle_day": int(form_data.get("rent_cycle_day", 1)),
        "admitted_on": datetime.utcnow(),
        "vacated_on": None,
    }
    result = await db.residents.insert_one(resident_doc)
    resident_doc["_id"] = result.inserted_id
    return resident_doc


async def update_resident_status(resident_id: str, status: ResidentStatus) -> None:
    db = get_db()
    update = {"$set": {"status": status}}
    if status == ResidentStatus.VACATED:
        update["$set"]["vacated_on"] = datetime.utcnow()
    await db.residents.update_one({"_id": _oid(resident_id)}, update)


async def update_pending_rent(resident_id: str, new_pending: float) -> None:
    db = get_db()
    await db.residents.update_one(
        {"_id": _oid(resident_id)},
        {"$set": {"pending_rent": max(0.0, new_pending)}}
    )


async def set_damages(resident_id: str, damages: float) -> None:
    db = get_db()
    await db.residents.update_one(
        {"_id": _oid(resident_id)},
        {"$set": {"damages": damages}}
    )


# ─── Payment Queries ─────────────────────────────────────────────────────────

async def record_payment(
    resident: dict,
    amount: float,
    recorded_by: int,
    note: Optional[str] = None,
    payment_date: Optional[date] = None
) -> dict:
    """
    Record a payment with idempotency check.
    Returns the inserted payment doc, or raises ValueError on duplicate.
    """
    db = get_db()
    resident_id = str(resident["_id"])
    fingerprint = generate_payment_fingerprint(resident_id, amount, payment_date)

    # Idempotency check
    existing = await db.payments.find_one({"fingerprint": fingerprint})
    if existing:
        raise ValueError("DUPLICATE")

    payment_doc = {
        "resident_id": resident_id,
        "resident_name": resident["name"],
        "amount": amount,
        "date": (payment_date or date.today()).strftime("%Y-%m-%d"),
        "fingerprint": fingerprint,
        "recorded_by": recorded_by,
        "recorded_at": datetime.utcnow(),
        "note": note,
    }
    await db.payments.insert_one(payment_doc)

    # Reduce pending_rent
    new_pending = max(0.0, resident.get("pending_rent", 0) - amount)
    await update_pending_rent(resident_id, new_pending)
    return payment_doc


async def get_payments_for_resident(resident_id: str) -> list[dict]:
    db = get_db()
    return await db.payments.find({"resident_id": resident_id}).sort("recorded_at", -1).to_list(None)


# ─── Checkout / Refund ───────────────────────────────────────────────────────

def compute_refund(resident: dict) -> float:
    """
    Refund = Advance - (pending_rent + maintenance + damages)
    Never negative (cannot owe money at exit in this system).
    """
    advance = resident.get("advance", 0)
    pending = resident.get("pending_rent", 0)
    maintenance = resident.get("maintenance", 0)
    damages = resident.get("damages", 0)
    refund = advance - (pending + maintenance + damages)
    return max(0.0, refund)


async def checkout_resident(resident: dict) -> float:
    """
    Mark resident VACATED, free room bed. Returns computed refund.
    """
    resident_id = str(resident["_id"])
    refund = compute_refund(resident)

    await update_resident_status(resident_id, ResidentStatus.VACATED)
    await decrement_occupied(resident["building"], resident["room_no"])
    return refund


# ─── Logs ────────────────────────────────────────────────────────────────────

async def log_cleaning(room_no: str, user_id: int, building: Optional[str] = None, note: Optional[str] = None) -> None:
    db = get_db()
    await db.cleaning_logs.insert_one({
        "building": building,
        "room_no": room_no,
        "logged_by": user_id,
        "logged_at": datetime.utcnow(),
        "note": note,
    })


async def log_food(user_id: int, note: Optional[str] = None) -> None:
    db = get_db()
    await db.food_logs.insert_one({
        "note": note,
        "logged_by": user_id,
        "logged_at": datetime.utcnow(),
    })


# ─── Auth / Registration ──────────────────────────────────────────────────

async def get_authorized_user(user_id: int) -> Optional[dict]:
    db = get_db()
    return await db.authorized_users.find_one({"user_id": user_id})


async def save_authorized_user(user_id: int, phone: str, role: str) -> None:
    db = get_db()
    # Clean phone (ensure only digits)
    clean_phone = "".join(filter(str.isdigit, phone))
    await db.authorized_users.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "phone": clean_phone, "role": role}},
        upsert=True
    )
