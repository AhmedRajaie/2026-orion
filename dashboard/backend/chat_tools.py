"""chat_tools.py — small, structured Gemini tool functions for the dashboard
chat agent, grounded in what's ACTUALLY on screen right now.

Design: build_tools(context) closes each tool over the current request's
DashboardContext (symbol/universe/date-range/backtest params the frontend
just sent). The model can pick WHICH indicator to inspect, but can never
supply a different symbol/universe — that's bound, not model-fillable — so
the agent physically cannot answer about a stock that isn't selected. Every
tool recomputes from tradinglab (the same functions dashboard/backend/main.py
uses), not from numbers the frontend already cached, so answers can't drift
from what the underlying data actually says.

Each tool returns a small dict, never a raw dataframe/array — keeps prompts
cheap and answers exact rather than the model eyeballing a wall of numbers.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tradinglab.data_feed import DataFeed, load_symbol_full_history, resolve_price_field
from tradinglab.indicators import (
    sma, ema, rsi, macd, bollinger_bands,
    stochastic_oscillator, atr, adx, vwap, ichimoku, parabolic_sar, obv,
)
from tradinglab.single_asset_backtest import run_ma_crossover_backtest

DATA_DIR = "data/egx"

# Not a typing.Literal: google-genai's automatic-function-calling argument
# coercion (_extra_utils.py) only special-cases pydantic/list/dict/Union
# annotations and falls through to a bare isinstance(value, annotation) for
# anything else — which raises TypeError for Literal (not a valid isinstance
# target). Plain str + manual validation below sidesteps that; the allowed
# values are still documented in the docstring for the model to read.
INDICATOR_KEYS = (
    "sma", "ema", "rsi", "macd", "bollinger_bands", "stochastic",
    "atr", "adx", "vwap", "ichimoku", "parabolic_sar", "obv",
)


@dataclass
class DashboardContext:
    """What's currently on screen, as sent by the frontend with each chat
    message. `backtest` is None when no single-asset backtest is displayed —
    tools must say so rather than inventing default parameters."""

    symbol: str
    universe: str = "small"
    field: str = "close"
    start: str | None = None
    end: str | None = None
    backtest: dict | None = None  # {"fast": int, "slow": int, "capital": float}

    @classmethod
    def from_dict(cls, payload: dict) -> "DashboardContext":
        if not payload.get("symbol"):
            raise ValueError("context.symbol is required")
        return cls(
            symbol=str(payload["symbol"]).upper(),
            universe=payload.get("universe") or "small",
            field=payload.get("field") or "close",
            start=payload.get("start"),
            end=payload.get("end"),
            backtest=payload.get("backtest"),
        )


class SymbolNotInUniverse(ValueError):
    pass


def _feed_symbols(universe: str) -> list[str]:
    if universe == "small":
        return ["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK"]
    return DataFeed.from_dir(DATA_DIR).symbols


def _load(ctx: DashboardContext) -> pd.DataFrame:
    if ctx.symbol not in _feed_symbols(ctx.universe):
        raise SymbolNotInUniverse(
            f"{ctx.symbol} is not in the currently selected '{ctx.universe}' universe."
        )
    df = load_symbol_full_history(DATA_DIR, ctx.symbol)
    if ctx.start:
        df = df[df["date"] >= pd.to_datetime(ctx.start)]
    if ctx.end:
        df = df[df["date"] <= pd.to_datetime(ctx.end)]
    return df.reset_index(drop=True)


def _last_valid(arr: np.ndarray) -> float | None:
    valid = arr[~np.isnan(arr)] if np.issubdtype(arr.dtype, np.floating) else arr
    if len(valid) == 0:
        return None
    return round(float(valid[-1]), 4)


def build_tools(context: DashboardContext) -> list:
    """Return the list of tool callables, each closed over `context`. Passed
    straight to google-genai's `tools=` for automatic function calling."""

    def get_current_price() -> dict:
        """Get the most recent price for the currently selected stock.

        Returns the latest date, close/adjusted price, and the daily change
        vs. the prior trading day, for whichever symbol is currently
        selected on the dashboard.
        """
        try:
            df = _load(context)
        except SymbolNotInUniverse as e:
            return {"error": str(e)}
        if len(df) == 0:
            return {"error": "no price data in the currently visible date range"}
        close, resolved_field = resolve_price_field(df, context.field)
        last_price = float(close[-1])
        prev_price = float(close[-2]) if len(close) > 1 else None
        return {
            "symbol": context.symbol,
            "date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            "price": round(last_price, 4),
            "field": resolved_field,
            "change_pct_vs_prior_day": round((last_price / prev_price - 1) * 100, 3) if prev_price else None,
        }

    def get_indicator_values(indicator: str) -> dict:
        """Get the latest value(s) of a technical indicator for the currently
        selected stock and visible date range.

        Args:
            indicator: which indicator to compute — must be exactly one of
                "sma", "ema", "rsi", "macd", "bollinger_bands", "stochastic",
                "atr", "adx", "vwap", "ichimoku", "parabolic_sar", "obv".
                Uses each indicator's standard default window/parameters.
        """
        if indicator not in INDICATOR_KEYS:
            return {"error": f"unknown indicator '{indicator}'. use one of {INDICATOR_KEYS}."}
        try:
            df = _load(context)
        except SymbolNotInUniverse as e:
            return {"error": str(e)}
        if len(df) < 5:
            return {"error": "not enough data in the currently visible date range to compute indicators"}

        price, resolved_field = resolve_price_field(df, context.field)
        open_, high, low, close, volume = (df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close", "volume"))
        last_date = df["date"].iloc[-1].strftime("%Y-%m-%d")
        base = {"symbol": context.symbol, "indicator": indicator, "date": last_date, "field": resolved_field}

        if indicator == "sma":
            return {**base, "sma_20": _last_valid(sma(price, 20))}
        if indicator == "ema":
            return {**base, "ema_20": _last_valid(ema(price, 20))}
        if indicator == "rsi":
            value = _last_valid(rsi(price, 14))
            reading = None if value is None else ("overbought" if value >= 70 else "oversold" if value <= 30 else "neutral")
            return {**base, "rsi_14": value, "reading": reading}
        if indicator == "macd":
            line, signal, hist = macd(price)
            return {**base, "macd_line": _last_valid(line), "signal_line": _last_valid(signal), "histogram": _last_valid(hist)}
        if indicator == "bollinger_bands":
            mid, upper, lower = bollinger_bands(price)
            return {**base, "mid": _last_valid(mid), "upper": _last_valid(upper), "lower": _last_valid(lower), "price": round(float(price[-1]), 4)}
        if indicator == "stochastic":
            k, d = stochastic_oscillator(high, low, close)
            return {**base, "percent_k": _last_valid(k), "percent_d": _last_valid(d)}
        if indicator == "atr":
            return {**base, "atr_14": _last_valid(atr(high, low, close))}
        if indicator == "adx":
            adx_line, plus_di, minus_di = adx(high, low, close)
            return {**base, "adx": _last_valid(adx_line), "plus_di": _last_valid(plus_di), "minus_di": _last_valid(minus_di)}
        if indicator == "vwap":
            return {**base, "vwap_20": _last_valid(vwap(high, low, close, volume))}
        if indicator == "ichimoku":
            tenkan, kijun, span_a, span_b, _ = ichimoku(high, low, close)
            return {**base, "tenkan": _last_valid(tenkan), "kijun": _last_valid(kijun), "senkou_a": _last_valid(span_a), "senkou_b": _last_valid(span_b)}
        if indicator == "parabolic_sar":
            return {**base, "psar": _last_valid(parabolic_sar(high, low))}
        if indicator == "obv":
            return {**base, "obv": _last_valid(obv(close, volume))}
        return {"error": f"unknown indicator '{indicator}'"}

    def get_backtest_summary() -> dict:
        """Get the result of the single-asset MA-crossover backtest currently
        displayed on the dashboard for the selected stock (KPIs, and whether
        a golden/death cross is imminent).

        Returns an explicit note instead of guessing if no backtest is
        currently displayed.
        """
        if not context.backtest:
            return {"note": "no backtest is currently displayed on the dashboard"}
        try:
            df = _load(context)
        except SymbolNotInUniverse as e:
            return {"error": str(e)}
        fast = int(context.backtest.get("fast", 9))
        slow = int(context.backtest.get("slow", 20))
        capital = float(context.backtest.get("capital", 1000.0))
        if fast >= slow or len(df) < slow + 2:
            return {"error": "backtest parameters currently shown are invalid or the range is too short"}

        dates = pd.DatetimeIndex(df["date"])
        close, _ = resolve_price_field(df, context.field)
        result = run_ma_crossover_backtest(dates, close, fast=fast, slow=slow, capital=capital)
        return {
            "symbol": context.symbol,
            "fast_window": fast,
            "slow_window": slow,
            "kpis": result["kpis"],
            "crossover_alert": result["alert"],
        }

    def get_price_range_stats() -> dict:
        """Get high/low/average price and volatility stats for the stock and
        date range currently visible on the dashboard."""
        try:
            df = _load(context)
        except SymbolNotInUniverse as e:
            return {"error": str(e)}
        if len(df) == 0:
            return {"error": "no price data in the currently visible date range"}
        close, resolved_field = resolve_price_field(df, context.field)
        high_idx, low_idx = int(np.argmax(close)), int(np.argmin(close))
        returns = np.diff(close) / close[:-1]
        return {
            "symbol": context.symbol,
            "field": resolved_field,
            "range_start": df["date"].iloc[0].strftime("%Y-%m-%d"),
            "range_end": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            "trading_days": len(df),
            "highest_price": round(float(close[high_idx]), 4),
            "highest_price_date": df["date"].iloc[high_idx].strftime("%Y-%m-%d"),
            "lowest_price": round(float(close[low_idx]), 4),
            "lowest_price_date": df["date"].iloc[low_idx].strftime("%Y-%m-%d"),
            "period_return_pct": round((close[-1] / close[0] - 1) * 100, 3),
            "daily_volatility_pct": round(float(np.std(returns)) * 100, 3) if len(returns) else None,
        }

    return [get_current_price, get_indicator_values, get_backtest_summary, get_price_range_stats]
