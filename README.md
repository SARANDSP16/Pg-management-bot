# PG Management AI Assistant — Complete Interview Guide

## 🧠 One-Line Summary
> A **Telegram-based AI assistant** for PG (Paying Guest) hostel management that handles resident admissions, rent payments, checkouts, and operational logs using a **LangGraph intent router + Groq LLM + MongoDB** backend — all through natural language chat.

---

## 🏗️ System Architecture

```text
User (WhatsApp-like Telegram Chat)
          │
          ▼
  python-telegram-bot (v21.5)
          │
          ▼
  bot.py  ── handle_message()
          │
          ├── [Multi-turn State] _pending dict (in-memory)
          │
          ▼
  intent/router.py ── LangGraph Graph
          │
          ├── node_classify()
          │     ├── [Fast Path] Keyword matching (zero-latency)
          │     └── [Fallback] Groq LLM API (llama-3.1-8b-instant)
          │
          ▼
  handlers/ (8 UC handlers)
          │
          ├── admission.py    → Text-template parse → DB insert
          ├── payment.py      → Entity extract → Confidence score → DB write
          ├── room_availability.py → DB read → Format
          ├── pending.py      → DB query → Format list
          ├── checkout.py     → Fuzzy name match → Inline KB confirm
          ├── cleaning.py     → Room extract → Log to DB
          ├── food.py         → Note extract → Log to DB
          └── info_query.py   → Fuzzy name → Resident profile
          │
          ▼
  db/ (Motor async MongoDB)
          │
          ├── connection.py   (singleton client + ensure_indexes)
          ├── models.py       (Pydantic v2 schemas)
          └── queries.py      (all CRUD operations)
```

---

## 📦 Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Bot Framework | `python-telegram-bot` v21.5 | Mature async PTB with full Telegram API |
| LLM | Groq API (`llama-3.1-8b-instant`) | Fast inference, free tier, OpenAI-compatible |
| Orchestration | LangGraph | Stateful graph-based routing, extensible |
| Database | MongoDB Atlas (Motor async) | Flexible schema, async driver, cloud-hosted |
| Validation | Pydantic v2 | Strong type safety for all DB models |
| Fuzzy Matching | FuzzyWuzzy (Levenshtein) | Name typo tolerance (score ≥ 70) |
| Config | python-dotenv | `.env`-based config with type-safe `config.py` |

---

## 🔄 Request Lifecycle (Step-by-Step)

### Example: "Raj paid 5000"

1. **Telegram→bot.py**: `handle_message()` receives the text
2. **Multi-turn check**: Not in `_pending` → fresh request
3. **Typing indicator**: `send_action("typing")` shows activity
4. **Intent routing** (`intent/router.py`):
   - `classify_intent_fast("Raj paid 5000")` → detects keyword `"paid"` → returns `"PAYMENT"` instantly (no LLM call)
5. **Dispatch** → `handle_payment("Raj paid 5000", user_id)`
6. **Entity extraction** (`intent/entities.py`):
   - `extract_amount()` → `5000.0` via regex
   - `extract_name_raw()` → `"Raj"` (stop-word filter)
7. **Fuzzy name resolution** → queries MongoDB for active residents → FuzzyWuzzy matches "Raj" → `[resident_doc]`
8. **Confidence scoring** (`utils/confidence.py`):
   - name ✅, amount ✅, 1 candidate ✅ → `Confidence.HIGH`
9. **Payment recorded** (`db/queries.py`):
   - SHA-256 fingerprint = `hash(resident_id:5000.00:2026-04-16)`
   - Idempotency check → not duplicate
   - `payments.insert_one(...)`, `pending_rent` decremented
10. **Response**: `fmt_payment_ok()` → "✅ Payment Recorded — ₹5,000 — Pending: ₹0"

---

## 🎯 Intent Classification — Two-Level Strategy

### Level 1: Keyword Fast Path (Zero-latency)
```python
_KEYWORD_MAP = {
    "PAYMENT":  ["paid", "payment", "collected", "received"],
    "PENDING":  ["pending", "didn't pay", "not paid", "dues"],
    "CHECKOUT": ["vacated", "vacate", "checked out", "left"],
    # ...
}
```
- Most real-world messages match → **no LLM cost**
- Returns in microseconds

### Level 2: Groq LLM Fallback
- Only fires when keyword matching returns `None`
- Uses `llama-3.1-8b-instant` (fastest Groq model)
- Zero-shot classification: system prompt defines all 9 labels
- Response is one word → `max_tokens=10`

---

## 🧩 8 Use Cases (UC-P1 to UC-P8)

| # | Intent | Handler | Key Logic |
|---|---|---|---|
| UC-P1 | ADMISSION | `admission.py` | Text template → parse key:value lines → `admit_resident()` |
| UC-P2 | PAYMENT | `payment.py` | Extract name+amount → fuzzy match → confidence → idempotent insert |
| UC-P3 | ROOM_QUERY | `room_availability.py` | `$expr` query for `occupied < total` → format list |
| UC-P4 | PENDING | `pending.py` | `pending_rent > 0` query → sorted by amount desc |
| UC-P5 | CHECKOUT | `checkout.py` | Fuzzy match → refund calc → Inline KB confirm → mark VACATED |
| UC-P6 | CLEANING | `cleaning.py` | Regex room extraction → `cleaning_logs` insert |
| UC-P7 | FOOD | `food.py` | Strip trigger words → `food_logs` insert |
| UC-P8 | INFO | `info_query.py` | Fuzzy name → profile display OR general stats |

---

## 🔒 Key Design Patterns

### 1. Payment Idempotency (SHA-256 Fingerprint)
```python
fingerprint = SHA256(f"{resident_id}:{amount:.2f}:{date}")
# Before insert → check if fingerprint exists
# Same message sent twice → rejected gracefully
```
> **Interview point**: Prevents double-payments even if the user sends the same message twice or the network retries.

### 2. Three-Level Confidence Scoring
```
HIGH   → All entities found, 1 match → Auto-execute
MEDIUM → Missing amount OR multiple matches → Ask clarifying question
LOW    → No matching resident → Block with explanation
```

### 3. Multi-Turn Conversation State
```python
_pending: dict[int, dict] = {}
# user_id → {"awaiting": "amount_for_payment", "resident_id": "..."}
```
- In-memory dict keyed by Telegram `user_id`
- Survives across messages in the same session
- Cleaned up on completion or cancellation

### 4. Atomic Overbooking Prevention
```python
# MongoDB atomic update — only increments if occupied < total
db.rooms.update_one(
    {"$expr": {"$lt": ["$occupied_beds", "$total_beds"]}},
    {"$inc": {"occupied_beds": 1}}
)
# Returns modified_count == 0 → room is full
```

### 5. LangGraph for Extensibility
- Graph: `START → classify → END`
- Adding a new use case = adding a new node + edge
- State is a typed dict passed through all nodes

---

## 🗄️ MongoDB Collections

| Collection | Purpose | Key Indexes |
|---|---|---|
| `residents` | Active/vacated residents | `phone` (unique), `(name, status)` |
| `rooms` | Room bed capacity | `(building, room_no)` (unique) |
| `payments` | All payment records | `fingerprint` (unique), `resident_id` |
| `cleaning_logs` | Cleaning events | timestamp |
| `food_logs` | Food/waste events | timestamp |
| `authorized_users` | Phone ↔ Telegram user_id | `user_id` (unique), `phone` (unique) |

---

## 🧮 Refund Calculation at Checkout

```
Refund = Advance − (pending_rent + maintenance + damages)
       = max(0, result)   # never negative
```

Example:
- Advance: ₹10,000
- Pending rent: ₹2,000
- Maintenance: ₹500
- Damages: ₹0
- **Refund: ₹7,500** ✅

---

## ⚠️ Bugs Fixed

| # | File | Bug | Fix Applied |
|---|---|---|---|
| 1 | `bot.py` | Duplicate import of `Update, InlineKeyboardMarkup` (line 19 & 70) | Removed duplicate import |
| 2 | `bot.py` | Dead comment `# ... inside handle_message ...` left in module scope | Removed stray comment |
| 3 | `bot.py` | `ensure_indexes()` never called in `post_init` | Added `await ensure_indexes()` call |
| 4 | `db/connection.py` | `ensure_indexes()` is defined but never called during startup | Called from `post_init` now |
| 5 | `requirements.txt` | `fastapi`, `uvicorn`, `jinja2`, `python-multipart` are unused (FastAPI server removed) | Cleaned up unused deps |
| 6 | `intent/router.py` | `classify_intent_groq()` is synchronous `requests.post` called inside async graph — blocks event loop | Converted to `asyncio.to_thread` wrapper |
| 7 | `handlers/payment.py` | `Confidence.HIGH` path passes `amount=None` to `record_payment` when only name was found but no amount | Guard added before HIGH path |
| 8 | `utils/formatters.py` | `fmt_admission_sent()` references `form_url` but is never called (dead code from old FastAPI flow) | Removed unused function |
| 9 | `bot.py` | `_handle_pending_state` for `"awaiting": "pick_resident_for_checkout"` calls `_build_confirm_prompt` which returns `CheckoutResult` but `result.pending_state` could be `None` causing unhandled assignment | Added null-safe `or {}` |
| 10 | `intent/entities.py` | `fuzzywuzzy` import may warn about C extension; `python-Levenshtein` already in requirements but `fuzzywuzzy` should use `from rapidfuzz` | Noted in requirements (not breaking) |

---

## 🎤 Common Interview Questions

**Q: Why use MongoDB instead of PostgreSQL?**
> Resident data is semi-structured (not all residents have damages, some have different fields), MongoDB's flexible schema fits naturally. Also, Motor provides first-class async support for Python's asyncio.

**Q: Why LangGraph instead of just if/elif?**
> LangGraph gives us a typed, composable, and extensible graph. Adding a new use case is just adding a node. It also handles async execution natively and is auditable (you can trace state through each node).

**Q: How do you prevent duplicate payments?**
> SHA-256 fingerprint based on `(resident_id, amount, date)`. Before every insert, we query the fingerprint index. If it exists, we raise `ValueError("DUPLICATE")` and return a user-friendly message.

**Q: What happens if the Groq API is down?**
> The keyword fast path handles most real-world messages. The LLM fallback is only needed for complex or ambiguous messages. If Groq fails, `classify_intent_groq()` catches all exceptions and returns `"NOISE"` as safe default.

**Q: How is the checkout safe from accidental execution?**
> Even at `Confidence.HIGH`, checkout always shows an InlineKeyboardMarkup with Confirm/Cancel buttons. The database write only happens on the `checkout_confirm:` callback — a two-step confirmation.

**Q: How do you handle typos in names?**
> FuzzyWuzzy (Levenshtein distance) with a threshold of score ≥ 70. If multiple residents match above threshold, the bot asks the user to pick from a numbered list (multi-turn MEDIUM confidence flow).

---

## 🚀 How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env (BOT_TOKEN, MONGO_URI, GROQ_API_KEY are required)

# 3. Run the bot
python bot.py

# 4. Run E2E tests
python test_e2e.py
```
