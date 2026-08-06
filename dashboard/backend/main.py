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

from tradinglab.backtest import run_ma_crossover_backtest
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

    result = run_ma_crossover_backtest(
        dates=feed.dates,
        close=close,
        fast_window=fast,
        slow_window=slow,
        initial_cash=initial_cash,
    )

    return {
        "symbol": symbol,
        "dates": result.dates,
        "equity_curve": result.equity_curve,
        "trades": [t.__dict__ for t in result.trades],
        "final_value": result.final_value,
        "max_drawdown_pct": result.max_drawdown_pct,
        "max_drawdown_value": result.max_drawdown_value,
        "num_buys": result.num_buys,
        "num_sells": result.num_sells,
        "initial_cash": initial_cash,
    }


@app.get("/metrics/{symbol}")
def metrics(symbol: str, fast: int = 9, slow: int = 20, initial_cash: float = 1000.0):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="unknown symbol")

    idx = feed.symbols.index(symbol)
    close = feed.close[:, idx]
    result = run_ma_crossover_backtest(
        dates=feed.dates,
        close=close,
        fast_window=fast,
        slow_window=slow,
        initial_cash=initial_cash,
    )
    returns = np.diff(np.asarray(result.equity_curve)) / np.asarray(result.equity_curve)[:-1]
    return {
        "symbol": symbol,
        "total_return": total_return(returns),
        "sharpe": sharpe(returns),
        "max_drawdown": max_drawdown(returns),
        "final_value": result.final_value,
        "initial_cash": initial_cash,
    }



