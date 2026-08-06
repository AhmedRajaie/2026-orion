"""Backtest helpers for the dashboard and quick experiments."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from .indicators import sma
from .metrics import max_drawdown


@dataclass
class TradeEvent:
    date: str
    side: str
    price: float


@dataclass
class BacktestResult:
    dates: list[str]
    equity_curve: list[float]
    trades: list[TradeEvent]
    final_value: float
    max_drawdown_pct: float
    max_drawdown_value: float
    num_buys: int
    num_sells: int


def run_ma_crossover_backtest(
    dates,
    close,
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
) -> BacktestResult:
    close = np.asarray(close, dtype=float)
    if len(close) < slow_window:
        raise ValueError("Not enough history for the slow moving average")

    fast_ma = sma(close, fast_window)
    slow_ma = sma(close, slow_window)
    weights = np.zeros_like(close, dtype=float)
    for t in range(len(close)):
        if t < slow_window - 1:
            continue
        if fast_ma[t] > slow_ma[t]:
            weights[t] = 1.0

    trades: list[TradeEvent] = []
    prev_weight = 0.0
    for t, weight in enumerate(weights):
        if prev_weight == 0.0 and weight == 1.0:
            trades.append(TradeEvent(date=str(dates[t])[:10], side="buy", price=float(close[t])))
        elif prev_weight == 1.0 and weight == 0.0:
            trades.append(TradeEvent(date=str(dates[t])[:10], side="sell", price=float(close[t])))
        prev_weight = weight

    returns = close[1:] / close[:-1] - 1.0
    strategy_returns = weights[:-1] * returns
    equity_curve = (initial_cash * np.cumprod(1.0 + strategy_returns)).tolist()

    peak = np.maximum.accumulate(equity_curve)
    drawdowns = peak - np.asarray(equity_curve)
    max_drawdown_value = float(np.max(drawdowns)) if len(drawdowns) else 0.0
    max_drawdown_pct = max_drawdown(strategy_returns)

    result = BacktestResult(
        dates=[str(d)[:10] for d in dates[1:]],
        equity_curve=equity_curve,
        trades=trades,
        final_value=float(equity_curve[-1]) if equity_curve else float(initial_cash),
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown_value=max_drawdown_value,
        num_buys=sum(1 for t in trades if t.side == "buy"),
        num_sells=sum(1 for t in trades if t.side == "sell"),
    )
    return result
