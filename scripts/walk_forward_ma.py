"""
walk_forward_ma.py — single-stock MA crossover walk-forward backtest.

Run from the repo root:
    uv run python scripts/walk_forward_ma.py --symbol COMI

This uses the repo's DataFeed and indicator helpers, starts with 1000 EGP,
buys the stock when MA9 > MA20, sells when MA9 < MA20, and reports:
  - final portfolio value
  - max drawdown
  - buy/sell counts
It also plots the price with MAs and the equity curve.
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import matplotlib.pyplot as plt
import numpy as np

from tradinglab.charting import plot_equity, plot_price
from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma
from tradinglab.metrics import max_drawdown


def compute_ma_crossover_strategy(close: np.ndarray, fast: int = 9, slow: int = 20):
    fast_ma = sma(close, fast)
    slow_ma = sma(close, slow)
    weights = np.zeros_like(close, dtype=float)
    for t in range(len(close)):
        if t < slow - 1:
            continue
        if fast_ma[t] > slow_ma[t]:
            weights[t] = 1.0
    return fast_ma, slow_ma, weights


def count_trades(weights: np.ndarray) -> tuple[int, int]:
    buys = 0
    sells = 0
    prev_weight = 0.0
    for weight in weights:
        if prev_weight == 0.0 and weight == 1.0:
            buys += 1
        elif prev_weight == 1.0 and weight == 0.0:
            sells += 1
        prev_weight = weight
    return buys, sells


def run_walk_forward(close: np.ndarray, dates, start_capital: float = 1000.0):
    close = np.asarray(close, dtype=float)
    fast_ma, slow_ma, weights = compute_ma_crossover_strategy(close, fast=9, slow=20)

    returns = close[1:] / close[:-1] - 1.0
    strategy_returns = weights[:-1] * returns

    portfolio_curve = start_capital * np.cumprod(1.0 + strategy_returns)
    benchmark_curve = start_capital * np.cumprod(1.0 + returns)

    final_value = float(portfolio_curve[-1])
    drawdown = max_drawdown(strategy_returns)
    buys, sells = count_trades(weights[:-1])
    metrics = {
        "final_value": final_value,
        "max_drawdown": drawdown,
        "buy_count": buys,
        "sell_count": sells,
        "portfolio_curve": portfolio_curve,
        "benchmark_curve": benchmark_curve,
        "equity_dates": dates[1:],
        "price_dates": dates,
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "weights": weights,
    }
    return metrics


def plot_results(symbol: str, close: np.ndarray, dates, fast_ma: np.ndarray, slow_ma: np.ndarray,
                 weights: np.ndarray, portfolio_curve: np.ndarray, benchmark_curve: np.ndarray,
                 equity_dates, start_capital: float):
    ax_price = plot_price(
        dates,
        close,
        overlays={"MA9": fast_ma, "MA20": slow_ma},
        title=f"{symbol} close price with MA9 / MA20",
    )

    buy_signals = np.where((weights[:-1] == 0.0) & (weights[1:] == 1.0))[0] + 1
    sell_signals = np.where((weights[:-1] == 1.0) & (weights[1:] == 0.0))[0] + 1

    ax_price.scatter(dates[buy_signals], close[buy_signals], marker="^", color="green", s=80, label="BUY")
    ax_price.scatter(dates[sell_signals], close[sell_signals], marker="v", color="red", s=80, label="SELL")
    ax_price.legend()

    plot_equity(
        portfolio_curve / start_capital,
        benchmark_curve / start_capital,
        dates=equity_dates,
        title=f"MA9/MA20 strategy vs buy-and-hold ({symbol})",
    )
    plt.show()


def parse_args():
    parser = argparse.ArgumentParser(description="Walk-forward MA9/MA20 crossover backtest")
    parser.add_argument("--symbol", default=None, help="Stock symbol from data/egx to test")
    parser.add_argument("--data-dir", default="data/egx", help="Directory containing EGX stock CSVs")
    parser.add_argument("--capital", type=float, default=1000.0, help="Starting capital in EGP")
    return parser.parse_args()


def main():
    args = parse_args()
    feed = DataFeed.from_dir(args.data_dir)

    symbol = args.symbol or feed.symbols[0]
    if symbol not in feed.symbols:
        raise ValueError(f"Symbol '{symbol}' not found. Available symbols: {', '.join(feed.symbols)}")

    symbol_index = feed.symbols.index(symbol)
    close = feed.close[:, symbol_index]
    dates = feed.dates

    result = run_walk_forward(close, dates, start_capital=args.capital)

    print(f"Symbol               : {symbol}")
    print(f"Start capital        : {args.capital:.2f} EGP")
    print(f"Final portfolio value: {result['final_value']:.2f} EGP")
    print(f"Max drawdown         : {result['max_drawdown']:.1%}")
    print(f"Buy operations       : {result['buy_count']}")
    print(f"Sell operations      : {result['sell_count']}")

    plot_results(
        symbol=symbol,
        close=close,
        dates=dates,
        fast_ma=result["fast_ma"],
        slow_ma=result["slow_ma"],
        weights=result["weights"],
        portfolio_curve=result["portfolio_curve"],
        benchmark_curve=result["benchmark_curve"],
        equity_dates=result["equity_dates"],
        start_capital=args.capital,
    )

if __name__ == "__main__":
    main()
