"""
handlers/room_availability.py — UC-P3: Room Availability Query
"""
from intent.entities import extract_building
from db.queries import get_available_rooms
from utils.formatters import fmt_room_availability


async def handle_room_availability(raw_text: str) -> str:
    building = extract_building(raw_text)
    available = await get_available_rooms(building=building)
    return fmt_room_availability(available)
