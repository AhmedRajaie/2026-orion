"""chat_service.py — orchestrates one chat turn: builds the tool set for the
current dashboard context, hands it to Gemini with automatic function calling,
and returns the model's grounded answer.

google-genai's ToolUnion accepts plain Python callables directly (see
chat_tools.py's docstrings/type hints, which the SDK turns into schemas) and
runs the whole call-tool/feed-result-back loop itself — no manual
function_call/function_response plumbing needed here.
"""
from __future__ import annotations

from google.genai import types

from .chat_tools import DashboardContext, build_tools
from .gemini_client import GeminiNotConfigured, get_client, get_model_name

SYSTEM_INSTRUCTION = (
    "You are a trading dashboard assistant. Answer ONLY using the tool "
    "functions provided — they reflect exactly what's currently on screen "
    "(the selected stock, visible date range, and any displayed backtest). "
    "Never use outside knowledge about stocks, prices, or news. If a tool "
    "returns an error or says something isn't currently displayed (e.g. no "
    "backtest shown, or the question is about a different symbol/date range "
    "than what's selected), say so plainly instead of guessing or inventing "
    "an answer. Keep answers short and concrete — cite the actual numbers "
    "the tools returned."
)


class ChatError(Exception):
    pass


def _to_content(message: dict) -> dict:
    role = message.get("role")
    if role not in ("user", "model"):
        raise ChatError(f"invalid history role '{role}'")
    return {"role": role, "parts": [{"text": message.get("text", "")}]}


def run_chat_turn(message: str, history: list[dict], context: dict) -> dict:
    """Run one turn of the dashboard chat agent.

    Args:
        message: the user's new message.
        history: prior turns as [{"role": "user"|"model", "text": str}, ...].
        context: the DashboardContext payload (symbol/universe/dates/backtest
            params) describing what's currently on screen.

    Returns: {"reply": str}
    """
    if not message or not message.strip():
        raise ChatError("message must not be empty")

    try:
        client = get_client()
    except GeminiNotConfigured as e:
        raise ChatError(str(e)) from e

    try:
        ctx = DashboardContext.from_dict(context)
    except ValueError as e:
        raise ChatError(str(e)) from e

    tools = build_tools(ctx)
    chat = client.chats.create(
        model=get_model_name(),
        config=types.GenerateContentConfig(
            tools=tools,
            system_instruction=SYSTEM_INSTRUCTION,
        ),
        history=[_to_content(m) for m in history],
    )

    try:
        response = chat.send_message(message)
    except Exception as e:
        raise ChatError(f"Gemini request failed: {e.__class__.__name__}: {e}") from e

    reply = (response.text or "").strip()
    if not reply:
        reply = "I couldn't generate a response — please try rephrasing your question."
    return {"reply": reply}
