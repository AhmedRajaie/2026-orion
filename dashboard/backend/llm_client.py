"""Shared LLM client for the dashboard -- same multi-provider pattern used in
week2/04-llm-news-sentiment/*.ipynb: one `openai`-compatible client talks to
OpenAI, Anthropic, or Gemini by swapping api_key/base_url/model, with a
clearly-labeled mock fallback so the dashboard still works with no key at all.

Degrades gracefully (rather than raising) whenever a provider's key is
missing or rejected -- same resilience added to the Day 4 notebooks, so a
bad/absent credential never breaks a dashboard request.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]

# Load .env once, the same way the notebooks do, without adding a hard
# dependency on python-dotenv being pre-imported by the caller.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

DEFAULT_PROVIDER = "gemini"

PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "openai": {
        "api_key": os.environ.get("OPENAI_API_KEY"),
        "base_url": None,
        "model": "gpt-5-mini",
    },
    "anthropic": {
        "api_key": os.environ.get("ANTHROPIC_API_KEY"),
        "base_url": "https://api.anthropic.com/v1/",
        "model": "claude-sonnet-5",
    },
    "gemini": {
        "api_key": os.environ.get("GEMINI_API_KEY"),
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-flash-latest",
    },
}


def _mock_reply(messages: list[dict[str, str]], system: str | None) -> str:
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    sys_note = f" [as instructed: {system[:40]}...]" if system else " [no system prompt given]"
    return f'[MOCK REPLY]{sys_note} You said: "{last_user[:60]}" -- imagine a real, helpful answer here.'


def chat(
    messages: list[dict[str, str]],
    system: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    max_tokens: int = 800,
    _retries_left: int = 1,
) -> str:
    """Send messages, get back reply text. Never raises on a missing/rejected
    key -- degrades to a clearly-labeled mock reply instead, same safety net
    as PROVIDER="mock". Retries once (short fixed backoff) on a 429 -- the
    free-tier quota this project runs on throttles in short bursts (a few
    seconds), not just a hard daily cap, so one retry recovers most of them."""
    if provider == "mock":
        return _mock_reply(messages, system)

    cfg = PROVIDER_CONFIG.get(provider)
    if cfg is None or not cfg.get("api_key"):
        return _mock_reply(messages, system)

    import time

    from openai import OpenAI, RateLimitError

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"]) if cfg["base_url"] else OpenAI(api_key=cfg["api_key"])
    full_messages = ([{"role": "system", "content": system}] if system else []) + messages

    try:
        resp = client.chat.completions.create(model=cfg["model"], messages=full_messages, max_tokens=max_tokens)
        content = resp.choices[0].message.content
        return content if content else _mock_reply(messages, system)
    except RateLimitError:
        if _retries_left > 0:
            time.sleep(6)
            return chat(messages, system=system, provider=provider, max_tokens=max_tokens, _retries_left=_retries_left - 1)
        return _mock_reply(messages, system)
    except Exception:
        return _mock_reply(messages, system)
