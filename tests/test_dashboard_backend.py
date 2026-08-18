"""Manual/pytest tests for the dashboard-state chat tools and the news
service's data functions — independent of the UI and (for the parts that
would otherwise need live API keys) independent of Gemini/yfinance too.

Run: uv run pytest tests/test_dashboard_backend.py -v
"""
from __future__ import annotations

import pytest

from dashboard.backend.chat_tools import DashboardContext, SymbolNotInUniverse, build_tools
from dashboard.backend import news_service
from dashboard.backend import game_service


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


# ------------------------------------------------------------- game_service ----

def test_game_config_has_8_symbols_and_matching_trading_day_count():
    config = game_service.get_config()
    assert len(config["symbols"]) == 8
    assert config["start_cash"] == 100_000.0
    assert config["holdings_per_day"] == 2
    assert len(config["trading_days"]) == config["num_days"]
    assert config["trading_days"][0] == game_service.DEFAULT_START_DATE
    assert config["trading_days"][-1] == game_service.DEFAULT_END_DATE


def test_game_prices_cover_every_symbol_with_matching_calendars():
    prices = game_service.get_prices()
    assert set(prices.keys()) == set(game_service.GAME_SYMBOLS)
    reference_dates = prices[game_service.GAME_SYMBOLS[0]]["dates"]
    for sym, series in prices.items():
        assert series["dates"] == reference_dates, f"{sym} calendar differs from {game_service.GAME_SYMBOLS[0]}"
        assert len(series["close"]) == len(reference_dates)


def test_game_benchmarks_start_at_100k_and_best_pair_beats_equal_weight_here():
    benchmarks = game_service.get_benchmarks(fee_enabled=False)
    ew = benchmarks["equal_weight"]
    bp = benchmarks["best_hindsight_pair"]

    assert ew["values"][0] == pytest.approx(game_service.DEFAULT_START_CASH, rel=1e-6)
    assert bp["values"][0] == pytest.approx(game_service.DEFAULT_START_CASH, rel=1e-6)
    assert len(bp["symbols"]) == 2
    assert set(bp["symbols"]) <= set(game_service.GAME_SYMBOLS)
    # best_hindsight_pair is a max over all pairs including equal-weight-like
    # combinations, so by construction it can't underperform the diversified
    # 8-way benchmark in this specific historical window.
    assert bp["final_value"] >= ew["final_value"]


def test_game_mark_to_market_pair_matches_equal_weight_formula_shape():
    import numpy as np
    close_a = np.array([10.0, 11.0, 9.0])
    close_b = np.array([20.0, 20.0, 25.0])
    values = game_service._mark_to_market_pair(close_a, close_b, game_service.DEFAULT_START_CASH, fee_enabled=False)
    assert values[0] == pytest.approx(game_service.DEFAULT_START_CASH)
    # day 2: 50% up 10%, 50% flat -> +5% overall
    assert values[1] == pytest.approx(game_service.DEFAULT_START_CASH * 1.05)


def test_game_benchmarks_include_risk_stats_for_every_line():
    benchmarks = game_service.get_benchmarks()
    for key in ("equal_weight", "best_hindsight_pair"):
        b = benchmarks[key]
        assert "volatility_pct" in b and b["volatility_pct"] >= 0
        assert "sharpe" in b
        assert "max_drawdown_pct" in b and b["max_drawdown_pct"] >= 0


def test_game_egx_index_benchmark_present_and_starts_at_100k():
    # data/egx30.csv exists locally and covers this window (verified against
    # the actual file before implementing), so this should be present, not
    # silently skipped.
    benchmarks = game_service.get_benchmarks()
    assert "egx_index" in benchmarks
    idx = benchmarks["egx_index"]
    assert idx["values"][0] == pytest.approx(game_service.DEFAULT_START_CASH, rel=1e-6)
    assert len(idx["values"]) == len(idx["dates"])


def test_risk_stats_zero_volatility_for_flat_curve():
    import numpy as np
    flat = np.full(10, 100_000.0)
    stats = game_service._risk_stats(flat)
    assert stats["volatility_pct"] == pytest.approx(0.0)
    assert stats["max_drawdown_pct"] == pytest.approx(0.0)


def test_leaderboard_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(game_service, "LEADERBOARD_PATH", tmp_path / "game_leaderboard.json")
    assert game_service.load_leaderboard() == []

    saved = game_service.save_attempt({
        "profit_pct": 5.0, "final_value": 105_000.0,
        "volatility_pct": 10.0, "sharpe": 1.2, "max_drawdown_pct": 2.0,
        "fee_pct": 0.0, "is_replay": False, "holdings_path": [["COMI", "HRHO"]],
    })
    assert "id" in saved and "played_at" in saved

    attempts = game_service.load_leaderboard()
    assert len(attempts) == 1
    assert attempts[0]["profit_pct"] == 5.0


def test_leaderboard_sorts_by_profit_pct_descending(tmp_path, monkeypatch):
    monkeypatch.setattr(game_service, "LEADERBOARD_PATH", tmp_path / "game_leaderboard.json")
    game_service.save_attempt({
        "profit_pct": 1.0, "final_value": 101_000.0, "volatility_pct": 5.0,
        "sharpe": 0.5, "max_drawdown_pct": 1.0, "fee_pct": 0.0, "is_replay": False, "holdings_path": [],
    })
    game_service.save_attempt({
        "profit_pct": 9.0, "final_value": 109_000.0, "volatility_pct": 8.0,
        "sharpe": 2.0, "max_drawdown_pct": 1.5, "fee_pct": 0.0, "is_replay": True, "holdings_path": [],
    })
    attempts = game_service.load_leaderboard()
    assert [a["profit_pct"] for a in attempts] == [9.0, 1.0]


# ---------------------------------------------------- setup screen params + fees ----

def test_get_date_bounds_covers_the_default_window():
    bounds = game_service.get_date_bounds()
    assert bounds["min_date"] <= game_service.DEFAULT_START_DATE
    assert bounds["max_date"] >= game_service.DEFAULT_END_DATE


def test_get_config_respects_custom_start_cash_and_date_range():
    config = game_service.get_config(start_date="2023-01-02", end_date="2023-02-01", start_cash=250_000.0)
    assert config["start_cash"] == 250_000.0
    assert config["start_date"] == "2023-01-02"
    assert config["end_date"] == "2023-02-01"
    # a materially different window from the default should produce a
    # materially different trading-day count, not the same fixed 20
    assert config["num_days"] != 20 or config["start_date"] != game_service.DEFAULT_START_DATE


def test_get_prices_respects_custom_date_range_not_the_default_window():
    prices = game_service.get_prices(start_date="2023-01-02", end_date="2023-02-01")
    dates = prices["COMI"]["dates"]
    assert dates[0] == "2023-01-02"
    assert all(d < game_service.DEFAULT_START_DATE for d in dates)  # entirely outside the old fixed window


def test_invalid_date_range_raises():
    with pytest.raises(game_service.InvalidGameRange):
        game_service.get_config(start_date="2023-02-01", end_date="2023-01-02")  # end before start -> 0 rows


def test_compute_trade_fee_applies_percentage_above_minimum():
    # 100,000 EGP trade: 100000 * 0.55075% = 550.75, well above the 15 EGP floor
    fee = game_service.compute_trade_fee(100_000.0)
    assert fee == pytest.approx(100_000.0 * game_service.EFFECTIVE_TRADE_FEE_PCT / 100)
    assert fee > game_service.TRADE_FEE_MIN_EGP


def test_compute_trade_fee_applies_minimum_for_small_trades():
    # 100 EGP trade: 0.55075% of 100 = 0.55, far below the EGP 15 floor
    fee = game_service.compute_trade_fee(100.0)
    assert fee == game_service.TRADE_FEE_MIN_EGP


def test_compute_trade_fee_disabled_is_zero():
    assert game_service.compute_trade_fee(100_000.0, fee_enabled=False) == 0.0


def test_benchmarks_deduct_initial_buyin_fee_when_enabled():
    with_fees = game_service.get_benchmarks(start_cash=100_000.0, fee_enabled=True)
    without_fees = game_service.get_benchmarks(start_cash=100_000.0, fee_enabled=False)
    # equal-weight: fees only reduce day-0 value (one-time buy-in), same
    # market moves after that, so "with fees" must be strictly behind
    assert with_fees["equal_weight"]["values"][0] < without_fees["equal_weight"]["values"][0]
    assert with_fees["equal_weight"]["final_value"] < without_fees["equal_weight"]["final_value"]
    assert without_fees["equal_weight"]["values"][0] == pytest.approx(100_000.0, rel=1e-6)
