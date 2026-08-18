"""news_service.py — news + sentiment for whichever stock is currently
selected on the dashboard.

get_news(ticker) is the swappable entry point: tries yfinance first (no key
needed), falls back to Finnhub (needs FINNHUB_API_KEY) if yfinance comes back
empty — which is the expected case for most EGX tickers, since Yahoo Finance
covers Cairo-listed stocks under a ".CA" suffix and coverage there is
inconsistent. Results are cached in-memory per ticker for TTL_SECONDS, same
pattern as the _SYMBOL_CACHE/_BACKTEST_CACHE dicts in main.py.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict

import requests

from .gemini_client import GeminiNotConfigured, get_client, get_model_name

TTL_SECONDS = 15 * 60


@dataclass
class NewsItem:
    title: str
    url: str
    publisher: str
    published_at: str | None  # ISO 8601, or None if the source didn't give one


class NoNewsFound(Exception):
    pass


def _yahoo_symbol(egx_symbol: str) -> str:
    """EGX (Cairo exchange) tickers need a .CA suffix on Yahoo Finance."""
    return f"{egx_symbol.upper()}.CA"


def _from_yfinance(ticker: str) -> list[NewsItem]:
    import yfinance as yf

    raw = yf.Ticker(_yahoo_symbol(ticker)).news or []
    items = []
    for entry in raw:
        # yfinance's news payload nests fields under "content" in current
        # versions; fall back to the flat legacy shape if that's absent.
        content = entry.get("content", entry)
        url = (content.get("clickThroughUrl") or content.get("canonicalUrl") or {})
        if isinstance(url, dict):
            url = url.get("url", "")
        title = content.get("title") or entry.get("title")
        if not title:
            continue
        items.append(NewsItem(
            title=title,
            url=url or "",
            publisher=(content.get("provider") or {}).get("displayName", "") if isinstance(content.get("provider"), dict) else content.get("publisher", ""),
            published_at=content.get("pubDate") or content.get("displayTime"),
        ))
    return items


def _from_finnhub(ticker: str) -> list[NewsItem]:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return []
    import datetime as _dt
    to_date = _dt.date.today()
    from_date = to_date - _dt.timedelta(days=14)
    resp = requests.get(
        "https://finnhub.io/api/v1/company-news",
        params={"symbol": ticker.upper(), "from": from_date.isoformat(), "to": to_date.isoformat(), "token": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    items = []
    for entry in resp.json() or []:
        if not entry.get("headline"):
            continue
        published_at = None
        if entry.get("datetime"):
            published_at = _dt.datetime.utcfromtimestamp(entry["datetime"]).isoformat() + "Z"
        items.append(NewsItem(
            title=entry["headline"],
            url=entry.get("url", ""),
            publisher=entry.get("source", ""),
            published_at=published_at,
        ))
    return items


def get_news(ticker: str) -> list[NewsItem]:
    """Fetch recent news for `ticker`. Tries yfinance first (no key needed);
    falls back to Finnhub if that comes back empty and FINNHUB_API_KEY is
    set. Returns an empty list (not an error) if nothing is found anywhere —
    callers decide how to present that."""
    try:
        items = _from_yfinance(ticker)
    except Exception:
        items = []
    if items:
        return items
    try:
        return _from_finnhub(ticker)
    except Exception:
        return []


def _summarize_with_gemini(ticker: str, items: list[NewsItem]) -> dict:
    """One structured-JSON call: 2-4 sentence summary + sentiment label/score
    + a one-line reason. Shares the Feature-1 Gemini client wrapper."""
    client = get_client()
    headlines = "\n".join(f"- {it.title} ({it.publisher})" for it in items[:15])
    prompt = (
        f"Here are recent news headlines for the stock {ticker}:\n{headlines}\n\n"
        "Respond with ONLY a JSON object with these exact keys: "
        '"summary" (2-4 plain-language sentences on what is currently going on with the stock), '
        '"sentiment_label" (one of "Positive", "Neutral", "Negative"), '
        '"sentiment_score" (a number from -1 to 1), '
        '"sentiment_reason" (one sentence explaining the sentiment read).'
    )
    response = client.models.generate_content(model=get_model_name(), contents=prompt)
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text)


_CACHE: dict[str, tuple[float, dict]] = {}


def get_news_with_sentiment(ticker: str, refresh: bool = False) -> dict:
    """The endpoint-facing entry point: cached news + Gemini summary/sentiment
    for `ticker`. Cache TTL is TTL_SECONDS; `refresh=True` bypasses it."""
    ticker = ticker.upper()
    now = time.time()
    if not refresh and ticker in _CACHE:
        cached_at, payload = _CACHE[ticker]
        if now - cached_at < TTL_SECONDS:
            return payload

    items = get_news(ticker)
    if not items:
        payload = {"symbol": ticker, "headlines": [], "summary": None, "sentiment": None,
                    "message": "No recent news found for this symbol."}
        _CACHE[ticker] = (now, payload)
        return payload

    try:
        analysis = _summarize_with_gemini(ticker, items)
    except GeminiNotConfigured as e:
        payload = {
            "symbol": ticker,
            "headlines": [asdict(it) for it in items],
            "summary": None, "sentiment": None,
            "message": str(e),
        }
        _CACHE[ticker] = (now, payload)
        return payload
    except Exception as e:
        payload = {
            "symbol": ticker,
            "headlines": [asdict(it) for it in items],
            "summary": None, "sentiment": None,
            "message": f"Could not summarize news right now ({e.__class__.__name__}).",
        }
        _CACHE[ticker] = (now, payload)
        return payload

    payload = {
        "symbol": ticker,
        "headlines": [asdict(it) for it in items],
        "summary": analysis.get("summary"),
        "sentiment": {
            "label": analysis.get("sentiment_label"),
            "score": analysis.get("sentiment_score"),
            "reason": analysis.get("sentiment_reason"),
        },
        "message": None,
    }
    _CACHE[ticker] = (now, payload)
    return payload
