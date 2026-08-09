"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys
# Ensure project's src/ is on sys.path so 'tradinglab' package (in src/) imports correctly
ROOT = Path(__file__).resolve().parents[2]
src_path = ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma
from tradinglab import metrics as metrics_module
import numpy as np

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}

# TASK_02+ : add /universe, /prices/{symbol}, /indicators, /backtest here.

# Load a small DataFeed from the committed CSVs. Synchronous and simple.
feed = DataFeed.from_dir("data/egx")

@app.get("/universe")
def universe():
    return {"symbols": feed.symbols}

@app.get("/prices/{symbol}")
def prices(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    # dates: convert DatetimeIndex to YYYY-MM-DD strings
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]
    close = feed.close[:, idx].tolist()
    return {"dates": dates, "close": close}


@app.get("/indicators/{symbol}")
def indicators(symbol: str, window: int = 20):
    """Return indicator series for a symbol. Currently supports SMA via ?window=."""
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx]
    sma_arr = sma(prices, window)
    # Convert NaN -> None so JSON has nulls
    sma_list = [None if np.isnan(float(x)) else float(x) for x in sma_arr]
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]
    return {"dates": dates, "sma": sma_list}


def _performance_metrics_from_equity(equity, initial):
    eq_arr = np.array(equity, dtype=float)
    returns = eq_arr[1:] / eq_arr[:-1] - 1.0 if len(eq_arr) > 1 else np.array([])
    total_return = metrics_module.total_return(returns) if len(returns) > 0 else 0.0
    annualized_return = metrics_module.annualized_return(returns) if len(returns) > 0 else 0.0
    return {
        "final_value": float(eq_arr[-1]) if eq_arr.size else float(initial),
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "sharpe_ratio": float(metrics_module.sharpe(returns)) if len(returns) > 0 else 0.0,
        "max_drawdown_pct": float(metrics_module.max_drawdown(returns)) if len(returns) > 0 else 0.0,
    }


def _run_sma_backtest(prices, dates, initial):
    sma9 = sma(prices, 9)
    sma20 = sma(prices, 20)
    pos = np.zeros_like(prices, dtype=int)
    valid = ~np.isnan(sma9) & ~np.isnan(sma20)
    pos[valid] = (sma9[valid] > sma20[valid]).astype(int)

    cash = float(initial)
    shares = 0.0
    equity = []
    trades = []
    buys = 0
    sells = 0
    prev_pos = 0

    for t in range(len(prices)):
        price = float(prices[t])
        cur_pos = int(pos[t])
        if prev_pos == 0 and cur_pos == 1:
            if price > 0 and cash > 0:
                shares = cash / price
                cash = 0.0
                buys += 1
                trades.append({
                    "index": t,
                    "date": dates[t],
                    "type": "buy",
                    "price": price,
                    "shares": shares,
                    "cash": cash,
                })
        elif prev_pos == 1 and cur_pos == 0:
            if shares > 0:
                cash = shares * price
                shares = 0.0
                sells += 1
                trades.append({
                    "index": t,
                    "date": dates[t],
                    "type": "sell",
                    "price": price,
                    "shares": 0.0,
                    "cash": cash,
                })
        equity.append(cash + shares * price)
        prev_pos = cur_pos

    metrics = _performance_metrics_from_equity(equity, initial)
    metrics.update({"buys": buys, "sells": sells, "equity": [float(x) for x in equity], "trades": trades})
    return metrics, sma9, sma20


def _run_drop_rise_backtest(prices, dates, initial, buy_threshold=0.05, sell_threshold=0.10):
    cash = float(initial)
    shares = 0.0
    equity = [float(initial)]
    trades = []
    buys = 0
    sells = 0

    for t in range(1, len(prices)):
        prev_price = float(prices[t - 1])
        price = float(prices[t])
        change = (price / prev_price - 1.0) if prev_price > 0 else 0.0
        portfolio_value = cash + shares * price
        if change <= -buy_threshold and portfolio_value > 0:
            amount = min(cash, abs(change) * portfolio_value)
            if amount > 0 and price > 0:
                share_qty = amount / price
                shares += share_qty
                cash -= amount
                buys += 1
                trades.append({
                    "index": t,
                    "date": dates[t],
                    "type": "buy",
                    "price": price,
                    "shares": share_qty,
                    "cash": cash,
                })
        elif change >= sell_threshold and shares > 0:
            amount = min(shares * price, change * portfolio_value)
            if amount > 0 and price > 0:
                share_qty = amount / price
                shares -= share_qty
                cash += amount
                sells += 1
                trades.append({
                    "index": t,
                    "date": dates[t],
                    "type": "sell",
                    "price": price,
                    "shares": share_qty,
                    "cash": cash,
                })
        equity.append(cash + shares * price)

    metrics = _performance_metrics_from_equity(equity, initial)
    metrics.update({"buys": buys, "sells": sells, "equity": [float(x) for x in equity], "trades": trades})
    return metrics


@app.get("/backtest/{symbol}")
def backtest(symbol: str, initial: float = 1000.0):
    """Simple per-symbol backtest of two strategies.
    - Base SMA crossover strategy from notebook 4
    - Drop/rise strategy: buy on >5% drop, sell on >10% rise
    Returns prices, SMA lines, and both strategy performance summaries.
    """
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx].astype(float)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]

    base_metrics, sma9, sma20 = _run_sma_backtest(prices, dates, initial)
    new_metrics = _run_drop_rise_backtest(prices, dates, initial)

    return {
        "dates": dates,
        "price": prices.tolist(),
        "sma9": [None if np.isnan(x) else float(x) for x in sma9],
        "sma20": [None if np.isnan(x) else float(x) for x in sma20],
        "base": base_metrics,
        "new_strategy": new_metrics,
    }


@app.get("/metrics/{symbol}")
def metrics(symbol: str, initial: float = 1000.0):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx].astype(float)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]
    base_metrics, _, _ = _run_sma_backtest(prices, dates, initial)
    new_metrics = _run_drop_rise_backtest(prices, dates, initial)
    return {
        "symbol": symbol,
        "base": {
            "total_return": base_metrics["total_return"],
            "sharpe_ratio": base_metrics["sharpe_ratio"],
            "max_drawdown_pct": base_metrics["max_drawdown_pct"],
        },
        "new_strategy": {
            "total_return": new_metrics["total_return"],
            "sharpe_ratio": new_metrics["sharpe_ratio"],
            "max_drawdown_pct": new_metrics["max_drawdown_pct"],
        },
    }

# TASK_02+ : add /universe, /prices/{symbol}, /indicators, /backtest here.
