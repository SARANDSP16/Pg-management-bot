"""
handlers/admission.py — UC-P1: New Admission (Text template based)

Flow:
  1. User asks for new admission
  2. Bot returns a blank text template 
  3. User fills out the template
  4. Bot parses the template and admits resident
"""
from db.queries import admit_resident
from utils.formatters import fmt_error

_TEMPLATE = """Please copy this template, fill it out, and send it back:

#ADMISSION
Name: 
Phone: 
Building: 
Room Number: 
Bed Number: 
Rent Amount: 
Advance Paid: 
Maintenance: 0
"""

async def handle_admission(raw_text: str, user_id: int) -> str:
    """
    If raw_text contains #ADMISSION, parse and submit.
    Otherwise, return the empty template.
    """
    if "#ADMISSION" not in raw_text.upper():
        return _TEMPLATE

    # Parse the filled template
    data = {
        "name": "", "phone": "", "building": "", "room_no": "", "bed_no": "",
        "rent": 0.0, "advance": 0.0, "maintenance": 0.0,
        "rent_cycle_day": 1, "total_beds": 1
    }
    
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
            
        key = parts[0].strip().lower()
        val = parts[1].strip()
        
        try:
            if "name" in key: data["name"] = val
            elif "phone" in key: data["phone"] = val
            elif "building" in key: data["building"] = val.upper()
            elif "room" in key: data["room_no"] = val
            elif "bed" in key: data["bed_no"] = val
            elif "rent" in key: data["rent"] = float(val) if val else 0.0
            elif "advance" in key: data["advance"] = float(val) if val else 0.0
            elif "maintenance" in key: data["maintenance"] = float(val) if val else 0.0
        except ValueError:
            return fmt_error(f"Invalid number provided for {key.capitalize()}.")

    # Validate required fields
    if not all([data["name"], data["phone"], data["building"], data["room_no"], data["bed_no"]]):
        return fmt_error("Please make sure Name, Phone, Building, Room, and Bed are filled correctly.")
        
    try:
        resident = await admit_resident(data)
        
        return (
            f"✅ *New Admission Successful!*\n\n"
            f"👤 Name     : {resident['name']}\n"
            f"📞 Phone    : {resident['phone']}\n"
            f"🏠 Building : {resident['building']}\n"
            f"🛏 Room     : {resident['room_no']}  Bed: {resident['bed_no']}\n"
            f"💰 Rent     : ₹{resident['rent']:,.0f}/month\n"
            f"💵 Advance  : ₹{resident['advance']:,.0f}"
        )
    except Exception as e:
        return fmt_error(str(e))
