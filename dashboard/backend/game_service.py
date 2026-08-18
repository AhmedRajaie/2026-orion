"""game_service.py — data + benchmarks for the Asset Management Game.

An 8-stock, always-invested, switch-between-days portfolio game. The
day-by-day play/switch state machine itself lives client-side in app.js
(matching this dashboard's existing pattern: main.py is stateless REST, the
frontend's `state` object drives everything interactive) — this module
supplies the raw price series and the two deterministic benchmarks for
whatever starting cash / date range / fee settings the player configured on
the setup screen, which are cheap to (re)compute per request rather than
hardcoded once.

Roster: COMI, HRHO, FWRY, PHDC were named explicitly (CIB, EFG Holding,
Fawry, Palm Hills — see scripts/fetch_egx_data.py's ticker comments for the
company-name mapping). TMGH, SWDY, ABUK complete the dashboard's existing
"small" 6-stock teaching universe (dashboard/backend/main.py). EFID
(Edita Food Industries, EGX30) is the 8th — flagged here since nothing in
the repo defines it; swap it by editing GAME_SYMBOLS if a different 8th
stock is wanted. The 8 symbols themselves are NOT configurable from the
setup screen (only starting cash / date range / fees are) — data coverage
was verified for this specific roster.
"""
from __future__ import annotations

import json
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.data_feed import load_egx30_returns
from tradinglab.metrics import volatility, sharpe, max_drawdown

DATA_DIR = "data/egx"
EGX30_INDEX_CSV = "data/egx30.csv"
GAME_SYMBOLS = ["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK", "PHDC", "EFID"]

# Setup-screen defaults — all three are player-configurable overrides now,
# these are just what the form pre-fills with.
DEFAULT_START_DATE = "2025-07-06"
DEFAULT_END_DATE = "2025-08-04"
DEFAULT_START_CASH = 100_000.0
HOLDINGS_PER_DAY = 2

LEADERBOARD_PATH = Path("results/reports/game_leaderboard.json")

# ------------------------------------------------------------- fee schedule ----
# EFG Hermes individual brokerage account agreement, EGX cash-equity trades.
# Applied per trade (a trade = one buy or one sell — a switch is 4 trades:
# sell A, sell B, buy C, buy D). Source values kept as separate named
# constants specifically so they're easy to re-check/update individually if
# EFG republishes rates; the ACTUAL fee formula below sums them into one
# effective rate + one practical minimum per the task's simplification (the
# individual per-component caps — EGX/MCDR at EGP 5,000, EFSA at EGP 250 —
# don't bind at this game's trade sizes: EGX's 0.012% cap requires a ~41.7M
# EGP trade, MCDR's similarly ~40M, EFSA's ~4M; a 100k-scale portfolio split
# into 2 positions never gets remotely close, so they're documented here as
# reference but not separately modeled).
BROKERAGE_COMMISSION_PCT = 0.5       # of trade value
BROKERAGE_COMMISSION_MIN_EGP = 15.0  # per trade — this is the practical floor
EGX_FEE_PCT = 0.012                  # exchange fee, of trade value
EGX_FEE_CAP_EGP = 5_000.0            # reference only, doesn't bind at this scale
MCDR_FEE_PCT = 0.0125                # clearing/settlement, of trade value
MCDR_FEE_CAP_EGP = 5_000.0           # reference only, doesn't bind at this scale
EFSA_FEE_PCT = 0.00625                # regulator fee, of trade value
EFSA_FEE_MIN_EGP = 1.0                # reference only, EGP 15 floor dominates
EFSA_FEE_MAX_EGP = 250.0              # reference only, doesn't bind at this scale
RISK_FUND_PCT = 0.02                  # non-commercial risk fund, of trade value

# The number every trade actually uses: sum of the five percentage
# components above, ~0.55075%.
EFFECTIVE_TRADE_FEE_PCT = (
    BROKERAGE_COMMISSION_PCT + EGX_FEE_PCT + MCDR_FEE_PCT + EFSA_FEE_PCT + RISK_FUND_PCT
)
TRADE_FEE_MIN_EGP = BROKERAGE_COMMISSION_MIN_EGP  # combined per-trade floor

# Annual custody fee — charged once per calendar year-end on portfolio
# value, not per trade. Off by default (game.py's DEFAULT_CUSTODY_FEE_ENABLED
# below): most playthroughs are weeks long, so this would almost never fire;
# it's here for players who deliberately pick a year-plus date range.
ANNUAL_CUSTODY_FEE_PCT = 0.01  # of EOY portfolio value

DEFAULT_FEE_ENABLED = True
DEFAULT_CUSTODY_FEE_ENABLED = False


def compute_trade_fee(trade_value: float, fee_enabled: bool = True) -> float:
    """Commission for one buy or one sell of `trade_value` EGP. 0 if fees
    are toggled off (players who want to test pure strategy)."""
    if not fee_enabled or trade_value <= 0:
        return 0.0
    return max(trade_value * EFFECTIVE_TRADE_FEE_PCT / 100.0, TRADE_FEE_MIN_EGP)


def get_date_bounds() -> dict:
    """The actual common date range across all 8 symbols' full history —
    what the setup screen's date pickers should be bounded to."""
    starts, ends = [], []
    for sym in GAME_SYMBOLS:
        df = pd.read_csv(f"{DATA_DIR}/{sym}.csv", parse_dates=["date"])
        starts.append(df["date"].min())
        ends.append(df["date"].max())
    return {
        "min_date": max(starts).strftime("%Y-%m-%d"),  # latest of the "earliest available" per symbol
        "max_date": min(ends).strftime("%Y-%m-%d"),     # earliest of the "latest available" per symbol
    }


def _load_symbol(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = pd.read_csv(f"{DATA_DIR}/{symbol}.csv", parse_dates=["date"])
    df = df[(df["date"] >= start_date) & (df["date"] <= end_date)].sort_values("date").reset_index(drop=True)
    return df


class InvalidGameRange(ValueError):
    pass


def load_game_prices(start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
    """One DataFrame per symbol, restricted to [start_date, end_date]. Raises
    InvalidGameRange if any symbol's trading-day calendar doesn't match the
    others' exactly (the game assumes a single shared calendar) or if the
    range produces fewer than 2 trading days (nothing to play)."""
    frames = {sym: _load_symbol(sym, start_date, end_date) for sym in GAME_SYMBOLS}
    reference_dates = frames[GAME_SYMBOLS[0]]["date"].tolist()
    if len(reference_dates) < 2:
        raise InvalidGameRange(
            f"{start_date} to {end_date} contains fewer than 2 trading days for {GAME_SYMBOLS[0]} — "
            "pick a wider range."
        )
    for sym, df in frames.items():
        if df["date"].tolist() != reference_dates:
            raise InvalidGameRange(f"{sym}'s trading calendar doesn't match {GAME_SYMBOLS[0]}'s in this date range")
    return frames


def get_config(start_date: str | None = None, end_date: str | None = None, start_cash: float | None = None) -> dict:
    start_date = start_date or DEFAULT_START_DATE
    end_date = end_date or DEFAULT_END_DATE
    start_cash = DEFAULT_START_CASH if start_cash is None else start_cash

    frames = load_game_prices(start_date, end_date)
    dates = frames[GAME_SYMBOLS[0]]["date"].dt.strftime("%Y-%m-%d").tolist()
    return {
        "symbols": GAME_SYMBOLS,
        "start_cash": start_cash,
        "start_date": dates[0],
        "end_date": dates[-1],
        "holdings_per_day": HOLDINGS_PER_DAY,
        "trading_days": dates,
        "num_days": len(dates),
        "fee": {
            "effective_pct": round(EFFECTIVE_TRADE_FEE_PCT, 5),
            "min_egp": TRADE_FEE_MIN_EGP,
            "default_enabled": DEFAULT_FEE_ENABLED,
            "annual_custody_pct": ANNUAL_CUSTODY_FEE_PCT,
            "default_custody_enabled": DEFAULT_CUSTODY_FEE_ENABLED,
        },
    }


def get_prices(start_date: str | None = None, end_date: str | None = None) -> dict:
    start_date = start_date or DEFAULT_START_DATE
    end_date = end_date or DEFAULT_END_DATE
    frames = load_game_prices(start_date, end_date)
    return {
        sym: {
            "dates": df["date"].dt.strftime("%Y-%m-%d").tolist(),
            "open": df["open"].tolist(),
            "high": df["high"].tolist(),
            "low": df["low"].tolist(),
            "close": df["close"].tolist(),
        }
        for sym, df in frames.items()
    }


def _apply_annual_custody_fees(values: np.ndarray, dates: pd.Series, custody_fee_enabled: bool) -> np.ndarray:
    """Mark down the value curve by ANNUAL_CUSTODY_FEE_PCT on every Dec-31
    that falls within the played range — a level shift applied to every
    subsequent day (the fee reduces the position going forward, same as
    real custody fees do), not just that one day's point."""
    if not custody_fee_enabled:
        return values
    values = values.copy()
    year_ends = dates[(dates.dt.month == 12) & (dates.dt.day == 31)].index.tolist()
    for idx in year_ends:
        fee = values[idx] * ANNUAL_CUSTODY_FEE_PCT / 100.0
        values[idx:] -= fee
    return values


def _mark_to_market_equal_weight(close: np.ndarray, start_cash: float, fee_enabled: bool) -> np.ndarray:
    """close: (n_days, n_assets). Buy-and-hold, equal weight from day 0,
    never rebalanced — pays the initial buy-in fee once (8 buy trades, one
    per asset) and nothing after, since it never trades again."""
    n_assets = close.shape[1]
    per_asset_cash = start_cash / n_assets
    fee_per_asset = compute_trade_fee(per_asset_cash, fee_enabled)
    invested_per_asset = per_asset_cash - fee_per_asset
    shares = invested_per_asset / close[0]
    return (shares * close).sum(axis=1)


def _mark_to_market_pair(close_a: np.ndarray, close_b: np.ndarray, start_cash: float, fee_enabled: bool) -> np.ndarray:
    """Buy-and-hold one fixed pair, 50/50, from day 0 — never switched, so
    it only ever pays its initial buy-in fee (2 buy trades)."""
    half = start_cash / 2
    fee = compute_trade_fee(half, fee_enabled)
    invested = half - fee
    shares_a = invested / close_a[0]
    shares_b = invested / close_b[0]
    return shares_a * close_a + shares_b * close_b


def _risk_stats(values: np.ndarray) -> dict:
    """Volatility/Sharpe/max-drawdown from a value curve's day-over-day
    returns, reusing tradinglab.metrics so these numbers are computed the
    same way as everywhere else in the dashboard (0% risk-free rate)."""
    returns = np.diff(values) / values[:-1]
    return {
        "volatility_pct": round(volatility(returns) * 100, 3),
        "sharpe": round(sharpe(returns, risk_free=0.0), 3),
        "max_drawdown_pct": round(max_drawdown(returns) * 100, 3),
    }


def _load_egx_index_values(dates: list[str], start_cash: float) -> np.ndarray | None:
    """EGX30 index, scaled to the same starting cash as every other line on
    the comparison chart. Returns None if the local file is missing or
    doesn't cover this window (load_egx30_returns' own >50%-coverage rule),
    rather than fetching anything over the network. Index benchmark isn't a
    tradeable position in this game, so no commission is modeled on it."""
    if not Path(EGX30_INDEX_CSV).exists():
        return None
    date_index = pd.DatetimeIndex(pd.to_datetime(dates))
    returns = load_egx30_returns(EGX30_INDEX_CSV, date_index)
    if returns is None:
        return None
    returns = returns.copy()
    returns[0] = 0.0  # day 0 is the base, not a return
    return start_cash * np.cumprod(1.0 + returns)


def get_benchmarks(
    start_date: str | None = None,
    end_date: str | None = None,
    start_cash: float | None = None,
    fee_enabled: bool = DEFAULT_FEE_ENABLED,
    custody_fee_enabled: bool = DEFAULT_CUSTODY_FEE_ENABLED,
) -> dict:
    start_date = start_date or DEFAULT_START_DATE
    end_date = end_date or DEFAULT_END_DATE
    start_cash = DEFAULT_START_CASH if start_cash is None else start_cash

    frames = load_game_prices(start_date, end_date)
    date_series = frames[GAME_SYMBOLS[0]]["date"]
    dates = date_series.dt.strftime("%Y-%m-%d").tolist()
    close = np.column_stack([frames[sym]["close"].to_numpy(dtype=float) for sym in GAME_SYMBOLS])

    equal_weight_values = _apply_annual_custody_fees(
        _mark_to_market_equal_weight(close, start_cash, fee_enabled), date_series, custody_fee_enabled
    )

    best = None
    for i, j in combinations(range(len(GAME_SYMBOLS)), 2):
        values = _mark_to_market_pair(close[:, i], close[:, j], start_cash, fee_enabled)
        values = _apply_annual_custody_fees(values, date_series, custody_fee_enabled)
        final = float(values[-1])
        if best is None or final > best["final_value"]:
            best = {
                "symbols": [GAME_SYMBOLS[i], GAME_SYMBOLS[j]],
                "values": values,
                "final_value": final,
            }

    def summarize(values: np.ndarray) -> dict:
        final_value = float(values[-1])
        profit = final_value - start_cash
        return {
            "dates": dates,
            "values": [round(float(v), 2) for v in values],
            "final_value": round(final_value, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit / start_cash * 100, 3),
            **_risk_stats(values),
        }

    result = {
        "equal_weight": summarize(equal_weight_values),
        "best_hindsight_pair": {**summarize(best["values"]), "symbols": best["symbols"]},
    }

    egx_index_values = _load_egx_index_values(dates, start_cash)
    if egx_index_values is not None:
        result["egx_index"] = summarize(egx_index_values)

    return result


# --------------------------------------------------------------- leaderboard ----
# Local JSON file under results/reports/ — matches the convention set up for
# this repo's results/ folder ("reports/ — generated summaries, leaderboards,
# training run reports"). No database in this project, so a small JSON file
# is the lightest thing that satisfies "persist locally".

def load_leaderboard() -> list[dict]:
    if not LEADERBOARD_PATH.exists():
        return []
    try:
        return json.loads(LEADERBOARD_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_attempt(entry: dict) -> dict:
    LEADERBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    attempts = load_leaderboard()
    saved = {
        "id": int(time.time() * 1000),
        "played_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **entry,
    }
    attempts.append(saved)
    attempts.sort(key=lambda a: a.get("profit_pct", 0), reverse=True)
    LEADERBOARD_PATH.write_text(json.dumps(attempts, indent=2))
    return saved
