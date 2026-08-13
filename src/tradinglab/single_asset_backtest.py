"""
single_asset_backtest.py — walk-forward MA-crossover backtest for ONE stock.

Distinct from backtester.py/simulator.py (which allocate weights across the
whole universe): this is the "buy the stock / sell the stock" model the
dashboard's strategy simulator needs, with explicit buy/sell trades, a
buy-and-hold comparison, and per-trade KPIs (win rate, holding period).

Convention matches simulator.py: a crossover detected using data through day
t is acted on at day t's own close — the moving averages at day t are built
only from prices up to and including day t, so this is never look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import sma
from .metrics import sharpe as sharpe_ratio, TRADING_DAYS


def run_ma_crossover_backtest(
    dates: pd.DatetimeIndex,
    close: np.ndarray,
    fast: int = 9,
    slow: int = 20,
    capital: float = 1000.0,
) -> dict:
    """Backtest a fast/slow MA crossover on one asset's close series.

    Returns dates/close/ma arrays (for charting), the buy & sell indices,
    a portfolio value curve, a buy-and-hold comparison curve, the list of
    round-trip trades, summary KPIs, and a crossover-proximity alert.
    """
    close = np.asarray(close, dtype=float)
    n = len(close)

    ma_fast = sma(close, fast)
    ma_slow = sma(close, slow)
    diff = ma_fast - ma_slow

    cash = capital
    shares = 0.0
    in_position = False

    portfolio_value = np.full(n, np.nan)
    buy_indices: list[int] = []
    sell_indices: list[int] = []
    trades: list[dict] = []
    open_trade: dict | None = None

    for i in range(n):
        if i == 0 or np.isnan(diff[i]) or np.isnan(diff[i - 1]):
            portfolio_value[i] = cash + shares * close[i]
            continue

        prev_diff, curr_diff = diff[i - 1], diff[i]
        price_today = close[i]

        golden_cross = prev_diff <= 0 and curr_diff > 0
        death_cross = prev_diff >= 0 and curr_diff < 0

        if not in_position and golden_cross:
            shares = cash / price_today
            cash = 0.0
            in_position = True
            buy_indices.append(i)
            open_trade = {"buy_index": i, "buy_date": dates[i], "buy_price": price_today}
        elif in_position and death_cross:
            cash = shares * price_today
            shares = 0.0
            in_position = False
            sell_indices.append(i)
            holding_days = (dates[i] - open_trade["buy_date"]).days
            return_pct = (price_today / open_trade["buy_price"] - 1.0) * 100.0
            trades.append({
                **open_trade,
                "sell_index": i,
                "sell_date": dates[i],
                "sell_price": price_today,
                "holding_days": holding_days,
                "return_pct": return_pct,
                "win": bool(return_pct > 0),
                "open": False,
            })
            open_trade = None

        portfolio_value[i] = cash + shares * price_today

    if open_trade is not None:
        # Still holding at the end of the window — report unrealized, not a
        # closed trade (doesn't count toward win rate / holding period).
        trades.append({
            **open_trade,
            "sell_index": None,
            "sell_date": None,
            "sell_price": None,
            "holding_days": (dates[-1] - open_trade["buy_date"]).days,
            "return_pct": (close[-1] / open_trade["buy_price"] - 1.0) * 100.0,
            "win": None,
            "open": True,
        })

    buy_and_hold = capital * close / close[0]

    kpis = _summarize(dates, close, portfolio_value, capital, trades, buy_and_hold)
    alert = _crossover_alert(diff, close)

    return {
        "dates": dates,
        "close": close,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
        "portfolio_value": portfolio_value,
        "buy_and_hold_value": buy_and_hold,
        "buy_indices": buy_indices,
        "sell_indices": sell_indices,
        "trades": trades,
        "kpis": kpis,
        "alert": alert,
    }


def _summarize(dates, close, portfolio_value, capital, trades, buy_and_hold) -> dict:
    final_value = float(portfolio_value[-1])
    closed = [t for t in trades if not t["open"]]
    wins = [t for t in closed if t["win"]]

    port_rets = np.diff(portfolio_value) / portfolio_value[:-1]
    port_rets = np.nan_to_num(port_rets)

    asset_rets = np.diff(close) / close[:-1]
    running_peak = np.maximum.accumulate(portfolio_value)
    drawdown = (portfolio_value - running_peak) / running_peak

    daily_change_pct = float((close[-1] / close[-2] - 1.0) * 100.0) if len(close) > 1 else 0.0

    return {
        "current_price": float(close[-1]),
        "daily_change_pct": daily_change_pct,
        "final_value": final_value,
        "total_return_pct": float((final_value / capital - 1.0) * 100.0),
        "max_drawdown_pct": float(np.nanmin(drawdown) * -100.0) if len(drawdown) else 0.0,
        "win_rate_pct": float(len(wins) / len(closed) * 100.0) if closed else 0.0,
        "num_buys": int(sum(1 for t in trades)),
        "num_sells": int(len(closed)),
        "sharpe": float(sharpe_ratio(port_rets)),
        "avg_holding_days": float(np.mean([t["holding_days"] for t in closed])) if closed else 0.0,
        "volatility_pct": float(np.std(asset_rets) * np.sqrt(TRADING_DAYS) * 100.0) if len(asset_rets) else 0.0,
        "expected_return_pct": float(np.mean(asset_rets) * TRADING_DAYS * 100.0) if len(asset_rets) else 0.0,
        "buy_and_hold_final_value": float(buy_and_hold[-1]),
        "buy_and_hold_return_pct": float((buy_and_hold[-1] / capital - 1.0) * 100.0),
    }


def _crossover_alert(diff: np.ndarray, close: np.ndarray, threshold_pct: float = 1.0) -> dict:
    """Flag when MA-fast and MA-slow are close and converging — a crossover
    may be imminent, but hasn't happened yet."""
    valid = ~np.isnan(diff)
    valid_idx = np.flatnonzero(valid)
    if len(valid_idx) < 2:
        return {"active": False, "direction": None, "distance_pct": None}

    i, j = valid_idx[-1], valid_idx[-2]
    today, yesterday = diff[i], diff[j]
    distance_pct = float(abs(today) / close[i] * 100.0)
    converging = abs(today) < abs(yesterday)
    same_side = np.sign(today) == np.sign(yesterday) or today == 0

    active = bool(converging and same_side and distance_pct < threshold_pct)
    direction = "golden" if today < 0 else "death"

    return {"active": active, "direction": direction, "distance_pct": distance_pct}
