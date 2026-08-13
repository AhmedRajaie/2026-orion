"""
single_signal_backtest.py — "if I traded on this model's calls" backtest for
the dashboard's Model Comparison feature. Long-only, long/flat, driven purely
by the SIGN of a per-day predicted return.

Same lookahead convention as the rest of the project (simulator.py): the
signal on day t is decided from data available through day t, and earns
whatever return is REALIZED on day t (i.e. `actual_returns[t]` is already the
held-out label the model was scored against — e.g. a notebook's `y_test` — so
there is no future information here, just a trading interpretation of a
prediction that was already made honestly).
"""
from __future__ import annotations

import numpy as np

from .metrics import sharpe as sharpe_ratio


def run_signal_backtest(
    dates,
    predicted_returns: np.ndarray,
    actual_returns: np.ndarray,
    capital: float = 1000.0,
) -> dict:
    """Long-only long/flat: go long (full capital in the stock) whenever
    `predicted_returns[t] > 0`, flat (cash, zero return) otherwise. Reports
    the same portfolio_value/kpis shape single_asset_backtest.py uses, plus a
    buy-and-hold curve over the same window for comparison.
    """
    predicted_returns = np.asarray(predicted_returns, dtype=float)
    actual_returns = np.asarray(actual_returns, dtype=float)
    n = len(predicted_returns)

    portfolio_value = np.empty(n)
    buy_and_hold_value = capital * np.cumprod(1.0 + actual_returns)

    value = capital
    in_position = False
    buy_indices: list[int] = []
    sell_indices: list[int] = []
    trades: list[dict] = []
    entry_index = None
    entry_value = None

    for t in range(n):
        want_long = predicted_returns[t] > 0

        if want_long and not in_position:
            in_position = True
            buy_indices.append(t)
            entry_index = t
            entry_value = value
        elif not want_long and in_position:
            in_position = False
            sell_indices.append(t)
            trades.append({
                "entry_index": entry_index,
                "exit_index": t,
                "holding_days": t - entry_index,
                "return_pct": (value / entry_value - 1.0) * 100.0,
                "win": value > entry_value,
                "open": False,
            })
            entry_index = None

        value *= (1.0 + (actual_returns[t] if in_position else 0.0))
        portfolio_value[t] = value

    if in_position:
        trades.append({
            "entry_index": entry_index,
            "exit_index": None,
            "holding_days": n - 1 - entry_index,
            "return_pct": (value / entry_value - 1.0) * 100.0,
            "win": None,
            "open": True,
        })

    running_peak = np.maximum.accumulate(portfolio_value)
    drawdown = (portfolio_value - running_peak) / running_peak
    port_rets = np.diff(portfolio_value, prepend=capital) / np.concatenate([[capital], portfolio_value[:-1]])

    closed = [t for t in trades if not t["open"]]
    wins = [t for t in closed if t["win"]]

    kpis = {
        "final_value": float(portfolio_value[-1]),
        "total_return_pct": float((portfolio_value[-1] / capital - 1.0) * 100.0),
        "max_drawdown_pct": float(np.nanmin(drawdown) * -100.0) if n else 0.0,
        "num_buys": len(buy_indices),
        "num_sells": len(sell_indices),
        "win_rate_pct": float(len(wins) / len(closed) * 100.0) if closed else 0.0,
        "avg_holding_days": float(np.mean([t["holding_days"] for t in closed])) if closed else 0.0,
        "sharpe": float(sharpe_ratio(port_rets)),
        "buy_and_hold_final_value": float(buy_and_hold_value[-1]),
        "buy_and_hold_return_pct": float((buy_and_hold_value[-1] / capital - 1.0) * 100.0),
    }

    return {
        "dates": dates,
        "portfolio_value": portfolio_value,
        "buy_and_hold_value": buy_and_hold_value,
        "buy_indices": buy_indices,
        "sell_indices": sell_indices,
        "trades": trades,
        "kpis": kpis,
    }
