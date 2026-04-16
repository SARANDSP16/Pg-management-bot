import asyncio
import sys
from config import GROQ_API_KEY
from db.connection import connect, disconnect, get_db
from intent.router import route_message, classify_intent_fast
from handlers.admission import handle_admission
from handlers.payment import handle_payment
from handlers.checkout import handle_checkout

async def test_all():
    print("[TEST] Starting E2E Tests...")
    
    # 1. Test DB Connection
    await connect()
    print("[OK] DB Connection passed.")

    db = get_db()
    # Clear test data if any
    await db.residents.delete_many({"name": "Test User"})
    await db.payments.delete_many({"resident_name": "Test User"})

    # 2. Test Fast Path Intent
    print("\n--- Testing Intent Router (Fast Path) ---")
    intent = classify_intent_fast("new admission")
    assert intent == "ADMISSION", f"Expected ADMISSION, got {intent}"
    print("[OK] Fast Path 'new admission' -> ADMISSION")

    # 3. Test Admission Template Generation
    print("\n--- Testing Admission Flow ---")
    template_msg = await handle_admission("new admission", 123456)
    assert "#ADMISSION" in template_msg
    print("[OK] Admission template generated successfully.")

    # 4. Test Admission Parsing & DB Insertion
    filled_form = """#ADMISSION
Name: Test User
Phone: 9999999999
Building: A
Room Number: 101
Bed Number: 1
Rent Amount: 6000
Advance Paid: 10000
Maintenance: 500
"""
    result_msg = await handle_admission(filled_form, 123456)
    if "[ERROR]" in result_msg or "Failed" in result_msg or "error" in result_msg.lower():
        print("[ERROR] Admission failed:", result_msg)
        sys.exit(1)
    print("[OK] Resident admitted successfully.")

    # 5. Test Payment
    print("\n--- Testing Payment Flow ---")
    pay_result = await handle_payment("Test User paid 6000", 123456)
    if "recorded" not in pay_result.text.lower() and "confirm" not in pay_result.text.lower():
         print("[ERROR] Payment parsing failed:", pay_result.text)
    else:
         print("[OK] Payment parsed correctly.")

    # 6. Test Checkout
    print("\n--- Testing Checkout Flow ---")
    checkout_result = await handle_checkout("Test User vacated", 123456)
    if not checkout_result.keyboard:
         print("[ERROR] Checkout failed or returned no keyboard.", checkout_result.text)
    else:
         print("[OK] Checkout parsed correctly.")

    await disconnect()
    print("\n[SUCCESS] ALL TESTS PASSED.")

if __name__ == "__main__":
    asyncio.run(test_all())
