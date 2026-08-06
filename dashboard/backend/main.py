import json
import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
FEATURES_PATH = ROOT / "dashboard" / "data" / "features.json"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

os.chdir(ROOT)

from tradinglab.backtester import run_backtest
from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma
from tradinglab.metrics import max_drawdown, sharpe, total_return
from tradinglab.simulator import PortfolioSimulator
from tradinglab.strategies.sma import sma_crossover_weights

app = FastAPI()


def round2(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return round(float(value), 2)


def round2_list(values):
    return [round2(v) for v in values]


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

feeds = {
    # NOTE: removed the duplicate "ABUK" entry that was here before
    "small": DataFeed.from_dir("data/egx", symbols=["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK"]),
    "full": DataFeed.from_dir("data/egx"),
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/features")
def get_features():
    if not FEATURES_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Features file not found: {FEATURES_PATH}")

    with FEATURES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/universe")
def get_universe(universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")
    return feeds[universe].symbols


@app.get("/prices/{symbol}")
def get_prices(symbol: str, universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    idx = feed.symbols.index(symbol)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": round2_list(feed.close[:, idx].tolist()),
    }


@app.get("/indicators/{symbol}")
def get_indicators(symbol: str, window: int = 20, universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    idx = feed.symbols.index(symbol)
    close_prices = feed.close[:, idx]
    sma_values = sma(close_prices, window)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "sma": [None if pd.isna(v) else round2(v) for v in sma_values.tolist()],
    }


@app.get("/backtest")
def get_backtest(universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    simulator = PortfolioSimulator(feeds[universe])
    result = run_backtest(simulator, sma_crossover_weights, lookback=30)
    return {
        "portfolio": round2_list(result["portfolio"]),
        "benchmark": round2_list(result["benchmark"]),
    }


@app.get("/metrics")
def get_metrics(universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    simulator = PortfolioSimulator(feeds[universe])
    result = run_backtest(simulator, sma_crossover_weights, lookback=30)
    portfolio_returns = result["portfolio_returns"]

    return {
        "total_return": round2(total_return(portfolio_returns)),
        "sharpe": round2(sharpe(portfolio_returns)),
        "max_drawdown": round2(max_drawdown(portfolio_returns)),
    }


@app.get("/strategy/{symbol}")
def get_strategy(symbol: str, universe: str = "small", cash: float = 1000.0):
    """Reproduce the notebook MA9/MA20 crossover backtest using the shared feed."""
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    idx = feed.symbols.index(symbol)
    close_series = pd.Series(feed.close[:, idx], index=feed.dates)
    ma9 = close_series.rolling(9).mean()
    ma20 = close_series.rolling(20).mean()

    starting_cash = float(cash)
    cash = starting_cash
    shares = 0.0
    buy_count = 0
    sell_count = 0
    buy_markers = [None] * len(close_series)
    sell_markers = [None] * len(close_series)
    trade_log = []
    portfolio_values = []
    portfolio_dates = []

    for i, price in enumerate(close_series):
        ma9_val = ma9.iloc[i]
        ma20_val = ma20.iloc[i]
        prev_ma9_val = ma9.iloc[i - 1] if i > 0 else None
        prev_ma20_val = ma20.iloc[i - 1] if i > 0 else None

        if pd.isna(ma9_val) or pd.isna(ma20_val):
            continue

        if shares == 0:
            if (
                prev_ma9_val is not None
                and prev_ma20_val is not None
                and not pd.isna(prev_ma9_val)
                and not pd.isna(prev_ma20_val)
                and prev_ma9_val <= prev_ma20_val
                and ma9_val > ma20_val
            ):
                shares = cash / float(price)
                cash = 0.0
                buy_count += 1
                buy_markers[i] = float(price)
                portfolio_value = cash + (shares * float(price))
                trade_log.append({
                    "date": feed.dates[i].strftime("%Y-%m-%d"),
                    "action": "buy",
                    "price": float(price),
                    "shares": float(shares),
                    "portfolio_value": float(portfolio_value),
                })
        elif shares > 0:
            if (
                prev_ma9_val is not None
                and prev_ma20_val is not None
                and not pd.isna(prev_ma9_val)
                and not pd.isna(prev_ma20_val)
                and prev_ma9_val >= prev_ma20_val
                and ma9_val < ma20_val
            ):
                trade_shares = float(shares)
                cash = shares * float(price)
                shares = 0.0
                sell_count += 1
                sell_markers[i] = float(price)
                portfolio_value = cash + (shares * float(price))
                trade_log.append({
                    "date": feed.dates[i].strftime("%Y-%m-%d"),
                    "action": "sell",
                    "price": float(price),
                    "shares": trade_shares,
                    "portfolio_value": float(portfolio_value),
                })

        portfolio_value = cash + (shares * float(price))
        portfolio_values.append(portfolio_value)
        portfolio_dates.append(feed.dates[i])

    if portfolio_values:
        portfolio_series = pd.Series(portfolio_values)
        running_max = portfolio_series.cummax()
        drawdown = (portfolio_series - running_max) / running_max
        max_drawdown_pct = float(drawdown.min() * 100)
        final_value = float(portfolio_series.iloc[-1])
        drawdown_series = [
            {
                "date": portfolio_dates[i].strftime("%Y-%m-%d"),
                "drawdown_pct": round2(float(drawdown.iloc[i] * 100)),
            }
            for i in range(len(portfolio_values))
        ]
    else:
        max_drawdown_pct = 0.0
        final_value = cash
        drawdown_series = []

    current_shares = float(shares) if shares > 0 else 0.0
    open_position = current_shares > 0
    pnl = final_value - starting_cash
    return_pct = (pnl / starting_cash * 100) if starting_cash != 0 else 0.0

    stats = {
        "final_value": round2(final_value),
        "buy_count": int(buy_count),
        "sell_count": int(sell_count),
        "max_drawdown_pct": round2(max_drawdown_pct),
    }

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": round2_list(close_series.tolist()),
        "ma9": [None if pd.isna(v) else round2(v) for v in ma9.tolist()],
        "ma20": [None if pd.isna(v) else round2(v) for v in ma20.tolist()],
        "buy_markers": buy_markers,
        "sell_markers": sell_markers,
        "trade_log": trade_log,
        "stats": stats,
        "pnl": round2(pnl),
        "return_pct": round2(return_pct),
        "open_position": open_position,
        "current_shares": round2(current_shares),
        "drawdown_series": drawdown_series,
    }