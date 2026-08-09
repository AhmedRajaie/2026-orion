"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import numpy as np

# Ensure the repo root is on sys.path even when uvicorn is launched from inside dashboard/backend.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tradinglab.backtest import BacktestResult, run_drop_rise_backtest, run_ma_crossover_backtest
from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma
from tradinglab.metrics import total_return, sharpe, max_drawdown

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = ROOT / "data" / "egx"
FRONTEND_DIR = ROOT / "dashboard" / "frontend"
feed = DataFeed.from_dir(DATA_DIR)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe():
    return {"symbols": feed.symbols}


@app.get("/prices/{symbol}")
def prices(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="unknown symbol")

    idx = feed.symbols.index(symbol)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]
    close = [float(x) for x in feed.close[:, idx]]
    return {"dates": dates, "close": close}


def parse_symbols(symbols: str | None) -> list[str]:
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols query parameter is required")

    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="symbols query parameter is required")

    invalid = [s for s in requested if s not in feed.symbols]
    if invalid:
        raise HTTPException(status_code=404, detail=f"unknown symbols: {', '.join(invalid)}")

    return requested


def aggregate_portfolio_results(symbols: list[str], results: list[BacktestResult]) -> tuple[list[float], list[dict]]:
    equity_curves = [np.asarray(result.equity_curve) for result in results]
    portfolio_curve = np.sum(equity_curves, axis=0).tolist()
    trades = []
    for symbol, result in zip(symbols, results):
        trades.extend([
            {**t.__dict__, "symbol": symbol} for t in result.trades
        ])
    return portfolio_curve, trades


@app.get("/indicators/{symbol}")
def indicators(symbol: str, window: int = 20):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="unknown symbol")

    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx]
    values = sma(prices, window)
    sma_values = [None if value != value else float(value) for value in values]
    return {"dates": [d.strftime("%Y-%m-%d") for d in feed.dates], "sma": sma_values}


@app.get("/backtest/{symbol}")
def backtest(symbol: str, fast: int = 9, slow: int = 20, initial_cash: float = 1000.0):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="unknown symbol")

    idx = feed.symbols.index(symbol)
    close = feed.close[:, idx]

    sma_result = run_ma_crossover_backtest(
        dates=feed.dates,
        close=close,
        fast_window=fast,
        slow_window=slow,
        initial_cash=initial_cash,
    )

    drop_rise_result = run_drop_rise_backtest(
        dates=feed.dates,
        close=close,
        initial_cash=initial_cash,
    )

    return {
        "symbol": symbol,
        "dates": sma_result.dates,
        "benchmark": [float(x) for x in np.cumprod(1.0 + (close[1:] / close[:-1] - 1.0))],
        "sma": {
            "equity_curve": sma_result.equity_curve,
            "trades": [t.__dict__ for t in sma_result.trades],
            "final_value": sma_result.final_value,
            "max_drawdown_pct": sma_result.max_drawdown_pct,
            "max_drawdown_value": sma_result.max_drawdown_value,
            "num_buys": sma_result.num_buys,
            "num_sells": sma_result.num_sells,
        },
        "drop_rise": {
            "equity_curve": drop_rise_result.equity_curve,
            "trades": [t.__dict__ for t in drop_rise_result.trades],
            "final_value": drop_rise_result.final_value,
            "max_drawdown_pct": drop_rise_result.max_drawdown_pct,
            "max_drawdown_value": drop_rise_result.max_drawdown_value,
            "num_buys": drop_rise_result.num_buys,
            "num_sells": drop_rise_result.num_sells,
        },
    }


@app.get("/backtest")
def backtest_portfolio(
    symbols: str,
    fast: int = 9,
    slow: int = 20,
    initial_cash: float = 1000.0,
    commission: float = 0.0,
):
    selected = parse_symbols(symbols)
    close_subset = feed.close[:, [feed.symbols.index(s) for s in selected]]

    sma_results = [
        run_ma_crossover_backtest(
            dates=feed.dates,
            close=close_subset[:, i],
            fast_window=fast,
            slow_window=slow,
            initial_cash=initial_cash / len(selected),
            commission=commission,
        )
        for i in range(close_subset.shape[1])
    ]
    drop_rise_results = [
        run_drop_rise_backtest(
            dates=feed.dates,
            close=close_subset[:, i],
            initial_cash=initial_cash / len(selected),
            commission=commission,
        )
        for i in range(close_subset.shape[1])
    ]

    benchmark_returns = feed.returns[:, [feed.symbols.index(s) for s in selected]].mean(axis=1)
    portfolio_benchmark = (initial_cash * np.cumprod(1.0 + benchmark_returns[1:])).tolist()
    sma_curve, sma_trades = aggregate_portfolio_results(selected, sma_results)
    drop_rise_curve, drop_rise_trades = aggregate_portfolio_results(selected, drop_rise_results)

    return {
        "symbols": selected,
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates[1:]],
        "benchmark": portfolio_benchmark,
        "sma": {
            "equity_curve": sma_curve,
            "trades": sma_trades,
            "final_value": float(sma_curve[-1]) if sma_curve else float(initial_cash),
        },
        "drop_rise": {
            "equity_curve": drop_rise_curve,
            "trades": drop_rise_trades,
            "final_value": float(drop_rise_curve[-1]) if drop_rise_curve else float(initial_cash),
        },
    }


@app.get("/metrics")
def portfolio_metrics(
    symbols: str,
    fast: int = 9,
    slow: int = 20,
    initial_cash: float = 1000.0,
    commission: float = 0.0,
):
    selected = parse_symbols(symbols)
    close_subset = feed.close[:, [feed.symbols.index(s) for s in selected]]

    sma_results = [
        run_ma_crossover_backtest(
            dates=feed.dates,
            close=close_subset[:, i],
            fast_window=fast,
            slow_window=slow,
            initial_cash=initial_cash / len(selected),
            commission=commission,
        )
        for i in range(close_subset.shape[1])
    ]
    drop_rise_results = [
        run_drop_rise_backtest(
            dates=feed.dates,
            close=close_subset[:, i],
            initial_cash=initial_cash / len(selected),
            commission=commission,
        )
        for i in range(close_subset.shape[1])
    ]

    sma_curve, _ = aggregate_portfolio_results(selected, sma_results)
    drop_rise_curve, _ = aggregate_portfolio_results(selected, drop_rise_results)

    sma_returns = np.diff(np.asarray(sma_curve)) / np.asarray(sma_curve)[:-1]
    drop_rise_returns = np.diff(np.asarray(drop_rise_curve)) / np.asarray(drop_rise_curve)[:-1]

    return {
        "symbols": selected,
        "sma": {
            "total_return": total_return(sma_returns),
            "sharpe": sharpe(sma_returns),
            "max_drawdown": max_drawdown(sma_returns),
            "final_value": float(sma_curve[-1]) if sma_curve else float(initial_cash),
            "initial_cash": initial_cash,
        },
        "drop_rise": {
            "total_return": total_return(drop_rise_returns),
            "sharpe": sharpe(drop_rise_returns),
            "max_drawdown": max_drawdown(drop_rise_returns),
            "final_value": float(drop_rise_curve[-1]) if drop_rise_curve else float(initial_cash),
            "initial_cash": initial_cash,
        },
    }



