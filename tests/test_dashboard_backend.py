"""Manual/pytest tests for the dashboard-state chat tools and the news
service's data functions — independent of the UI and (for the parts that
would otherwise need live API keys) independent of Gemini/yfinance too.

Run: uv run pytest tests/test_dashboard_backend.py -v
"""
from __future__ import annotations

import pytest

from dashboard.backend.chat_tools import DashboardContext, SymbolNotInUniverse, build_tools
from dashboard.backend import news_service


# ------------------------------------------------------------- chat_tools ----

def test_dashboard_context_requires_symbol():
    with pytest.raises(ValueError):
        DashboardContext.from_dict({})


def test_dashboard_context_defaults():
    ctx = DashboardContext.from_dict({"symbol": "comi"})
    assert ctx.symbol == "COMI"  # normalized to upper
    assert ctx.universe == "small"
    assert ctx.field == "close"
    assert ctx.backtest is None


def test_build_tools_returns_four_callables():
    ctx = DashboardContext.from_dict({"symbol": "COMI"})
    tools = build_tools(ctx)
    assert len(tools) == 4
    assert all(callable(t) for t in tools)


def _tools_by_name(ctx: DashboardContext) -> dict:
    return {t.__name__: t for t in build_tools(ctx)}


def test_get_current_price_for_valid_symbol():
    ctx = DashboardContext.from_dict({"symbol": "COMI", "universe": "small"})
    tools = _tools_by_name(ctx)
    result = tools["get_current_price"]()
    assert "error" not in result
    assert result["symbol"] == "COMI"
    assert isinstance(result["price"], float)
    assert result["date"]


def test_get_current_price_rejects_symbol_outside_universe():
    # HRHO is valid, but not in a universe that only contains it if we lie
    # about the universe — use a symbol that's real but outside "small".
    ctx = DashboardContext.from_dict({"symbol": "SAUD", "universe": "small"})
    tools = _tools_by_name(ctx)
    result = tools["get_current_price"]()
    assert "error" in result
    assert "SAUD" in result["error"]


def test_get_indicator_values_rsi_reports_reading():
    ctx = DashboardContext.from_dict({"symbol": "COMI", "universe": "small"})
    tools = _tools_by_name(ctx)
    result = tools["get_indicator_values"](indicator="rsi")
    assert "error" not in result
    assert result["indicator"] == "rsi"
    assert result["reading"] in ("overbought", "oversold", "neutral", None)


def test_get_indicator_values_covers_every_declared_indicator_key():
    ctx = DashboardContext.from_dict({"symbol": "COMI", "universe": "small"})
    tools = _tools_by_name(ctx)
    for key in ("sma", "ema", "rsi", "macd", "bollinger_bands", "stochastic",
                "atr", "adx", "vwap", "ichimoku", "parabolic_sar", "obv"):
        result = tools["get_indicator_values"](indicator=key)
        assert "error" not in result, f"{key} -> {result}"


def test_get_backtest_summary_without_displayed_backtest():
    ctx = DashboardContext.from_dict({"symbol": "COMI"})  # no "backtest" key
    tools = _tools_by_name(ctx)
    result = tools["get_backtest_summary"]()
    assert result == {"note": "no backtest is currently displayed on the dashboard"}


def test_get_backtest_summary_with_displayed_backtest():
    ctx = DashboardContext.from_dict({
        "symbol": "COMI", "universe": "small",
        "backtest": {"fast": 9, "slow": 20, "capital": 1000.0},
    })
    tools = _tools_by_name(ctx)
    result = tools["get_backtest_summary"]()
    assert "error" not in result
    assert result["fast_window"] == 9
    assert "kpis" in result and "crossover_alert" in result


def test_get_price_range_stats_respects_visible_range():
    ctx = DashboardContext.from_dict({"symbol": "COMI", "universe": "small", "start": "2020-01-01", "end": "2020-12-31"})
    tools = _tools_by_name(ctx)
    result = tools["get_price_range_stats"]()
    assert "error" not in result
    assert result["range_start"].startswith("2020")
    assert result["range_end"].startswith("2020")
    assert result["highest_price"] >= result["lowest_price"]


# ------------------------------------------------------------ news_service ----

def _fake_item(title: str) -> news_service.NewsItem:
    return news_service.NewsItem(
        title=title, url="https://example.com/a",
        publisher="Example Wire", published_at="2026-08-01T00:00:00Z",
    )


def test_get_news_falls_back_to_finnhub_when_yfinance_empty(monkeypatch):
    monkeypatch.setattr(news_service, "_from_yfinance", lambda ticker: [])
    monkeypatch.setattr(news_service, "_from_finnhub", lambda ticker: [_fake_item("fallback headline")])
    items = news_service.get_news("COMI")
    assert len(items) == 1
    assert items[0].title == "fallback headline"


def test_get_news_returns_empty_list_not_exception_when_both_sources_fail(monkeypatch):
    def boom(ticker):
        raise RuntimeError("network down")
    monkeypatch.setattr(news_service, "_from_yfinance", boom)
    monkeypatch.setattr(news_service, "_from_finnhub", boom)
    assert news_service.get_news("COMI") == []


def test_get_news_with_sentiment_no_news_found(monkeypatch):
    news_service._CACHE.clear()
    monkeypatch.setattr(news_service, "get_news", lambda ticker: [])
    result = news_service.get_news_with_sentiment("NOPE", refresh=True)
    assert result["headlines"] == []
    assert result["summary"] is None
    assert "No recent news" in result["message"]


def test_get_news_with_sentiment_reports_missing_gemini_key_without_crashing(monkeypatch):
    from dashboard.backend.gemini_client import GeminiNotConfigured

    news_service._CACHE.clear()
    monkeypatch.setattr(news_service, "get_news", lambda ticker: [_fake_item("headline one")])

    def raise_not_configured(*args, **kwargs):
        raise GeminiNotConfigured("GEMINI_API_KEY is not set.")

    monkeypatch.setattr(news_service, "_summarize_with_gemini", raise_not_configured)
    result = news_service.get_news_with_sentiment("COMI", refresh=True)
    assert result["summary"] is None
    assert len(result["headlines"]) == 1
    assert "GEMINI_API_KEY" in result["message"]


def test_get_news_with_sentiment_caches_within_ttl(monkeypatch):
    news_service._CACHE.clear()
    calls = {"n": 0}

    def fake_get_news(ticker):
        calls["n"] += 1
        return [_fake_item("headline one")]

    monkeypatch.setattr(news_service, "get_news", fake_get_news)
    monkeypatch.setattr(news_service, "_summarize_with_gemini", lambda ticker, items: {
        "summary": "test summary", "sentiment_label": "Neutral", "sentiment_score": 0.0, "sentiment_reason": "test",
    })

    news_service.get_news_with_sentiment("COMI")
    news_service.get_news_with_sentiment("COMI")  # should hit cache, not call get_news again
    assert calls["n"] == 1
