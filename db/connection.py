"""
db/connection.py — Async MongoDB client using Motor.
Call get_db() anywhere to get the database handle.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import MONGO_URI, MONGO_DB

_client: AsyncIOMotorClient | None = None


async def connect():
    """Create the MongoDB connection (call once at bot startup)."""
    global _client
    _client = AsyncIOMotorClient(MONGO_URI)
    # Verify connectivity
    await _client.admin.command("ping")
    print(f"MongoDB connected -> {MONGO_DB}")


async def disconnect():
    """Gracefully close the MongoDB connection."""
    global _client
    if _client:
        _client.close()
        _client = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the database handle. connect() must have been called first."""
    if _client is None:
        raise RuntimeError("MongoDB not connected. Call connect() first.")
    return _client[MONGO_DB]


async def ensure_indexes():
    """Create all required MongoDB indexes for performance and constraints."""
    db = get_db()

    # Rooms — unique per building+room_no
    await db.rooms.create_index(
        [("building", 1), ("room_no", 1)], unique=True
    )

    # Residents — unique phone
    await db.residents.create_index("phone", unique=True)
    await db.residents.create_index([("name", 1), ("status", 1)])

    # Payments — idempotency fingerprint
    await db.payments.create_index("fingerprint", unique=True)
    await db.payments.create_index("resident_id")

    # Authorized Users — mapping user_id <-> phone
    await db.authorized_users.create_index("user_id", unique=True)
    await db.authorized_users.create_index("phone", unique=True)

    print("MongoDB indexes ensured")
