"""gemini_client.py — thin, swappable wrapper around the Gemini API.

Both the chat agent (chat_service.py) and the news summarizer (news_service.py)
share this one client instead of each doing their own SDK setup. Swapping
providers later means changing this file only.

Reads GEMINI_API_KEY from the environment (loaded from .env via python-dotenv
if present) — never hardcoded. GEMINI_MODEL is optional and defaults to the
current flash model; override it in .env if a different model is preferred.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-3.7-flash"


class GeminiNotConfigured(RuntimeError):
    """Raised when GEMINI_API_KEY isn't set — callers turn this into a clean
    error response instead of letting the dashboard crash."""


@lru_cache(maxsize=1)
def get_client():
    """Return a cached google-genai Client, or raise GeminiNotConfigured."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise GeminiNotConfigured(
            "GEMINI_API_KEY is not set. Add it to a .env file in the repo root "
            "(see dashboard/README.md)."
        )
    from google import genai  # deferred: only import the SDK if it's actually used

    return genai.Client(api_key=api_key)


def get_model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
