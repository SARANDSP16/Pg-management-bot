"""
bot.py — PG / Hostel Management AI Personal Assistant
Entry point. Starts both the Telegram bot and the FastAPI form server.

Architecture:
  Telegram Bot (python-telegram-bot)
    → LangGraph intent router
    → Handler modules (UC-P1 to UC-P8)
    → MongoDB (motor async)
  FastAPI form server (background thread)
    → Admission form UI
    → Notifies Telegram on submission
"""
import asyncio
import logging

from telegram import Update, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    CallbackQueryHandler, ContextTypes, filters
)

from config import (
    BOT_TOKEN, OWNER_PHONES, MANAGER_PHONES, ALL_AUTHORIZED_PHONES
)
from db.connection import connect, disconnect, ensure_indexes
from intent.router import route_message
from utils.formatters import fmt_unknown, fmt_error

# ─── Handlers ────────────────────────────────────────────────────────────────
from handlers.admission       import handle_admission
from handlers.payment         import handle_payment, handle_payment_with_resident
from handlers.room_availability import handle_room_availability
from handlers.pending         import handle_pending
from handlers.checkout        import handle_checkout, execute_checkout
from handlers.cleaning        import handle_cleaning
from handlers.food            import handle_food
from handlers.info_query      import handle_info_query

# DB queries needed for multi-turn resolution and auth
from db.queries import get_resident_by_id, get_authorized_user, save_authorized_user

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── In-memory multi-turn state ───────────────────────────────────────────────
# Maps telegram_user_id → pending state dict
_pending: dict[int, dict] = {}


# ─── Authorization helper ─────────────────────────────────────────────────────

async def is_authorized(user_id: int) -> bool:
    """[DISABLED] Authorization is currently open to everyone."""
    return True


async def get_user_role(user_id: int) -> str:
    user = await get_authorized_user(user_id)
    return user.get("role", "Manager") if user else "Manager"


# ─── Main Message Handler ─────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Routes every incoming text message through the intent router."""
    user_id  = update.effective_user.id
    chat_id  = update.effective_chat.id
    raw_text = update.message.text.strip()

    if not raw_text:
        return

    # [Auth Disabled] Anyone can use the system now
    pass

    # ── Multi-turn continuation ───────────────────────────────────────────────
    if user_id in _pending:
        handled = await _handle_pending_state(update, context, raw_text, user_id, chat_id)
        if handled:
            return

    # ── Fresh intent routing ──────────────────────────────────────────────────
    await update.message.chat.send_action("typing")

    state = await route_message(raw_text, user_id, chat_id)
    intent = state.get("intent", "NOISE")

    logger.info(f"[{user_id}] intent={intent} text='{raw_text[:60]}'")

    await _dispatch_intent(update, intent, raw_text, user_id)


async def _dispatch_intent(update: Update, intent: str, raw_text: str, user_id: int):
    """Call the appropriate handler and send back the response."""
    msg = update.message

    if intent == "NOISE":
        return  # Silently ignore

    elif intent == "ADMISSION":
        text = await handle_admission(raw_text, user_id)
        await msg.reply_text(text, parse_mode="Markdown")

    elif intent == "PAYMENT":
        result = await handle_payment(raw_text, user_id)
        if result.pending_state:
            _pending[user_id] = result.pending_state
        if result.text:
            await msg.reply_text(result.text, parse_mode="Markdown")

    elif intent == "ROOM_QUERY":
        text = await handle_room_availability(raw_text)
        await msg.reply_text(text, parse_mode="Markdown")

    elif intent == "PENDING":
        text = await handle_pending()
        await msg.reply_text(text, parse_mode="Markdown")

    elif intent == "CHECKOUT":
        result = await handle_checkout(raw_text, user_id)
        if result.pending_state:
            _pending[user_id] = result.pending_state
        await msg.reply_text(
            result.text,
            reply_markup=result.keyboard,
            parse_mode="Markdown"
        )

    elif intent == "CLEANING":
        text = await handle_cleaning(raw_text, user_id)
        await msg.reply_text(text)

    elif intent == "FOOD":
        text = await handle_food(raw_text, user_id)
        await msg.reply_text(text)

    elif intent == "INFO":
        text = await handle_info_query(raw_text)
        await msg.reply_text(text, parse_mode="Markdown")

    else:
        await msg.reply_text(fmt_unknown())


# ─── Multi-turn Continuation ──────────────────────────────────────────────────

async def _handle_pending_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    raw_text: str,
    user_id: int,
    chat_id: int
) -> bool:
    """
    Handle multi-turn conversation (e.g., bot asked for amount, user replies).
    Returns True if the message was consumed as a continuation.
    """
    state = _pending.get(user_id, {})
    awaiting = state.get("awaiting")

    if not awaiting:
        del _pending[user_id]
        return False

    msg = update.message

    # ── Waiting for an amount (for payment) ──────────────────────────────────
    if awaiting == "amount_for_payment":
        from utils.idempotency import generate_payment_fingerprint
        from intent.entities import extract_amount
        amount = extract_amount(raw_text)
        if not amount:
            await msg.reply_text("💬 Please enter a valid amount (numbers only, e.g. 5000)")
            return True

        resident_id = state.get("resident_id")
        if not resident_id:
            # Still need to pick a resident
            _pending[user_id] = {**state, "awaiting": "pick_resident_for_payment", "amount": amount}
            from utils.formatters import fmt_ask_pick
            candidates_ids = state.get("candidates", [])
            # Fetch them
            residents = [r for r in [await get_resident_by_id(rid) for rid in candidates_ids] if r]
            await msg.reply_text(fmt_ask_pick(residents))
            return True

        resident = await get_resident_by_id(resident_id)
        if not resident:
            await msg.reply_text(fmt_error("Resident not found."))
            del _pending[user_id]
            return True

        text = await handle_payment_with_resident(resident, amount, user_id)
        await msg.reply_text(text, parse_mode="Markdown")
        del _pending[user_id]
        return True

    # ── Waiting for user to pick a resident (for payment) ────────────────────
    if awaiting == "pick_resident_for_payment":
        try:
            pick = int(raw_text.strip()) - 1
            candidates_ids = state.get("candidates", [])
            if 0 <= pick < len(candidates_ids):
                resident = await get_resident_by_id(candidates_ids[pick])
                amount = state.get("amount")
                if not amount:
                    _pending[user_id] = {
                        "awaiting": "amount_for_payment",
                        "resident_id": str(resident["_id"]),
                    }
                    from utils.formatters import fmt_ask_amount
                    await msg.reply_text(fmt_ask_amount(resident["name"]))
                    return True
                text = await handle_payment_with_resident(resident, amount, user_id)
                await msg.reply_text(text, parse_mode="Markdown")
                del _pending[user_id]
                return True
        except (ValueError, IndexError):
            pass
        await msg.reply_text("⚠️ Please reply with a number from the list above.")
        return True

    # ── Waiting for user to pick a resident (for checkout) ───────────────────
    if awaiting == "pick_resident_for_checkout":
        try:
            pick = int(raw_text.strip()) - 1
            candidates_ids = state.get("candidates", [])
            if 0 <= pick < len(candidates_ids):
                resident = await get_resident_by_id(candidates_ids[pick])
                from handlers.checkout import _build_confirm_prompt
                result = _build_confirm_prompt(resident)
                _pending[user_id] = result.pending_state or {}
                await msg.reply_text(result.text, reply_markup=result.keyboard, parse_mode="Markdown")
                return True
        except (ValueError, IndexError):
            pass
        await msg.reply_text("⚠️ Please reply with a number from the list above.")
        return True

    # ── Unknown awaiting state ────────────────────────────────────────────────
    del _pending[user_id]
    return False


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the shared contact for phone verification."""
    contact = update.message.contact
    user_id = update.effective_user.id
    phone   = "".join(filter(str.isdigit, contact.phone_number))

    logger.info(f"Verification attempt: user_id={user_id}, phone={phone}")

    role = None
    if phone in OWNER_PHONES:
        role = "Owner"
    elif phone in MANAGER_PHONES:
        role = "Manager"

    if role:
        await save_authorized_user(user_id, phone, role)
        await update.message.reply_text(
            f"✅ *Verification Successful!*\n\n"
            f"Role: {role}\n"
            f"You are now authorized to use the PG Management system.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        # Show help menu
        await cmd_start(update, context)
    else:
        await update.message.reply_text(
            "❌ This phone number is not in the authorized list.\n\n"
            "Please contact the administrator to add your number to the system configuration."
        )


# ─── Callback Query Handler (Inline Buttons) ──────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if not await is_authorized(user_id):
        await query.edit_message_text("⛔ Unauthorized.")
        return

    # ── Checkout confirm ──────────────────────────────────────────────────────
    if data.startswith("checkout_confirm:"):
        resident_id = data.split(":", 1)[1]
        resident = await get_resident_by_id(resident_id)
        if not resident:
            await query.edit_message_text(fmt_error("Resident not found."))
            return
        text = await execute_checkout(resident)
        await query.edit_message_text(text, parse_mode="Markdown")
        _pending.pop(user_id, None)

    elif data == "checkout_cancel":
        await query.edit_message_text("❌ Checkout cancelled. No changes made.")
        _pending.pop(user_id, None)


# ─── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Manager"
    
    role = await get_user_role(user_id)
    await update.message.reply_text(
        f"👋 Hello {first_name}! I'm your PG Management Assistant.\n\n"
        f"🔑 Role: {role}\n\n"
        f"Here's what I can do:\n"
        f"  • 'new admission' → Register a resident\n"
        f"  • '[Name] paid [amount]' → Record payment\n"
        f"  • 'room available?' → Check vacancies\n"
        f"  • 'who didn't pay?' → Pending dues\n"
        f"  • '[Name] vacated' → Process checkout\n"
        f"  • 'room 102 cleaned' → Cleaning log\n"
        f"  • 'food waste noted' → Food log\n"
        f"  • '[Name] details' → Resident info"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update.effective_user.id):
        return
    text = await handle_room_availability("")
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update.effective_user.id):
        return
    text = await handle_pending()
    await update.message.reply_text(text, parse_mode="Markdown")



async def post_init(application):
    """Called after bot is built, before polling starts."""
    await connect()
    await ensure_indexes()
    logger.info("MongoDB connected and indexes ready")


async def post_shutdown(application):
    """Called when bot is shutting down."""
    await disconnect()
    logger.info("MongoDB disconnected")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Build and run Telegram bot
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("rooms",   cmd_rooms))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # NEW: Handle phone number shared via contact
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("PG Assistant Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()