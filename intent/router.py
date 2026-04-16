"""
intent/router.py — LangGraph-based intent classification + dispatch.

Graph: START → classify → extract → route → END

Intent labels (as returned by Ollama):
  ADMISSION | PAYMENT | ROOM_QUERY | PENDING | CHECKOUT |
  CLEANING  | FOOD    | INFO       | NOISE
"""
from __future__ import annotations
from typing import TypedDict, Optional, Any
import requests
from langgraph.graph import StateGraph, END

from config import GROQ_API_KEY, GROQ_MODEL


# ─── Graph State ─────────────────────────────────────────────────────────────

class RouterState(TypedDict):
    """Shared state object passed through every graph node."""
    raw_text: str
    user_id: int
    chat_id: int
    intent: Optional[str]
    entities: dict[str, Any]
    response: Optional[str]
    keyboard: Optional[Any]      # InlineKeyboardMarkup or None
    error: Optional[str]


# ─── Groq Intent Classifier ──────────────────────────────────────────────────

_INTENT_PROMPT = """\
You are an intent classifier for a PG hostel management assistant.
Classify the following message into EXACTLY ONE of these labels:
ADMISSION, PAYMENT, ROOM_QUERY, PENDING, CHECKOUT, CLEANING, FOOD, INFO, NOISE

Rules:
- ADMISSION → messages about adding/registering a new resident
- PAYMENT   → messages about someone paying rent or dues (must name a person)
- ROOM_QUERY → asking about room or bed availability
- PENDING   → asking who hasn't paid / pending dues
- CHECKOUT  → resident vacating / leaving / checking out
- CLEANING  → room or area cleaning logged
- FOOD      → food, meals, waste, diet logs
- INFO      → asking for details about a specific resident or general info
- NOISE     → greetings, acknowledgements (ok, thanks, 👍), unrelated chatter

Respond with ONLY the label word, nothing else."""


def classify_intent_groq(text: str) -> str:
    """Call Groq API to classify intent. Falls back to NOISE on error."""
    if not GROQ_API_KEY:
        print("[Router] Error: GROQ_API_KEY is missing in .env")
        return "NOISE"

    valid = {"ADMISSION", "PAYMENT", "ROOM_QUERY", "PENDING",
             "CHECKOUT", "CLEANING", "FOOD", "INFO", "NOISE"}
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": _INTENT_PROMPT},
            {"role": "user", "content": text}
        ],
        "temperature": 0.0,
        "max_tokens": 10
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        label = resp.json()["choices"][0]["message"]["content"].strip().upper()
        # Extract first word in case model outputs extra text
        first_word = label.split()[0] if label else "NOISE"
        return first_word if first_word in valid else "NOISE"
    except Exception as e:
        print(f"[Router] Groq API error: {e}")
        return "NOISE"


# ─── Keyword-based fast path (avoids LLM for obvious patterns) ───────────────

_KEYWORD_MAP = {
    "ADMISSION": ["new admission", "add student", "add resident", "new student", "new tenant", "onboard", "#admission"],
    "PAYMENT":   ["paid", "payment", "collected", "received"],
    "ROOM_QUERY":["room available", "bed available", "vacancy", "sharing available", "available room", "any room"],
    "PENDING":   ["pending", "didn't pay", "not paid", "dues", "defaulter", "who hasn't"],
    "CHECKOUT":  ["vacated", "vacate", "checked out", "left", "moving out", "notice given"],
    "CLEANING":  ["cleaned", "cleaning", "swept", "mopped"],
    "FOOD":      ["food", "meal", "waste", "diet", "breakfast", "dinner", "lunch"],
    "INFO":      ["details", "info", "information", "profile", "rent of", "who is"],
    "NOISE":     ["ok", "okay", "thanks", "thank you", "👍", "noted", "alright", "sure"],
}


def classify_intent_fast(text: str) -> Optional[str]:
    """Keyword fast path — check before calling Ollama."""
    lowered = text.lower().strip()

    # Noise check first (single-word or emoji)
    if len(lowered.split()) <= 2:
        for kw in _KEYWORD_MAP["NOISE"]:
            if kw in lowered:
                return "NOISE"

    for intent, keywords in _KEYWORD_MAP.items():
        for kw in keywords:
            if kw in lowered:
                return intent
    return None


def classify_intent(text: str) -> str:
    """Primary classifier: keyword fast path, then Groq fallback."""
    fast = classify_intent_fast(text)
    if fast:
        return fast
    return classify_intent_groq(text)


# ─── Graph Nodes ──────────────────────────────────────────────────────────────

def node_classify(state: RouterState) -> RouterState:
    intent = classify_intent(state["raw_text"])
    state["intent"] = intent
    state["entities"] = {}
    return state


# ─── Conditional Edge (routes to handler after classification) ────────────────

def route_intent(state: RouterState) -> str:
    return state.get("intent", "NOISE")


# ─── Build Graph ──────────────────────────────────────────────────────────────

def build_router() -> Any:
    """
    Build and compile the LangGraph routing graph.
    Handler nodes are registered externally (in bot.py) to avoid circular imports.
    Returns the compiled graph.
    """
    builder = StateGraph(RouterState)
    builder.add_node("classify", node_classify)
    builder.set_entry_point("classify")

    # All intents terminate after classify for now; handlers are invoked
    # by the dispatcher in bot.py based on state["intent"].
    # This keeps the graph simple and avoids circular import issues.
    builder.add_edge("classify", END)

    return builder.compile()


# Singleton compiled graph
_router_graph = None


def get_router():
    global _router_graph
    if _router_graph is None:
        _router_graph = build_router()
    return _router_graph


async def route_message(raw_text: str, user_id: int, chat_id: int) -> RouterState:
    """
    Main entry point. Classify intent from message and return populated state.
    """
    graph = get_router()
    initial_state: RouterState = {
        "raw_text": raw_text,
        "user_id": user_id,
        "chat_id": chat_id,
        "intent": None,
        "entities": {},
        "response": None,
        "keyboard": None,
        "error": None,
    }
    result = await graph.ainvoke(initial_state)
    return result
