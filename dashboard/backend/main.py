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


@app.get("/backtest/{symbol}")
def backtest(symbol: str, initial: float = 1000.0):
    """Simple walk-forward backtest:
    - Buy (go long) when SMA(9) > SMA(20)
    - Sell (go to cash) when SMA(9) < SMA(20)
    - Fractional shares allowed, no costs/slippage
    Returns dates, price, sma9, sma20, equity series, trades and summary metrics.
    """
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx].astype(float)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]

    # compute SMAs
    sma9 = sma(prices, 9)
    sma20 = sma(prices, 20)

    # positions: 1 if sma9 > sma20 and both not NaN, else 0
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
        # entry
        if prev_pos == 0 and cur_pos == 1:
            # buy at close
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
        # exit
        elif prev_pos == 1 and cur_pos == 0:
            # sell at close
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
        # record equity
        eq = cash + shares * price
        equity.append(eq)
        prev_pos = cur_pos

    # summary
    final_value = equity[-1] if equity else float(initial)
    eq_arr = np.array(equity, dtype=float)
    running_max = np.maximum.accumulate(eq_arr)
    drawdowns = running_max - eq_arr
    max_drawdown_abs = float(np.nanmax(drawdowns)) if drawdowns.size else 0.0
    max_drawdown_pct = float(np.nanmax(drawdowns / running_max)) if drawdowns.size else 0.0

    # performance metrics
    total_return = (float(final_value) / float(initial)) - 1.0
    T = len(eq_arr)
    # daily returns of equity
    if T > 1:
        daily_rets = eq_arr[1:] / eq_arr[:-1] - 1.0
        mean_ret = float(np.nanmean(daily_rets))
        std_ret = float(np.nanstd(daily_rets))
        ann_factor = 252.0
        sharpe_ratio = float((mean_ret / std_ret) * np.sqrt(ann_factor)) if std_ret > 0 else 0.0
        years = T / ann_factor
        annualized_return = float((float(final_value) / float(initial)) ** (1.0 / years) - 1.0) if years > 0 else float(total_return)
    else:
        daily_rets = np.array([])
        mean_ret = 0.0
        std_ret = 0.0
        sharpe_ratio = 0.0
        annualized_return = 0.0

    return {
        "dates": dates,
        "price": prices.tolist(),
        "sma9": [None if np.isnan(x) else float(x) for x in sma9],
        "sma20": [None if np.isnan(x) else float(x) for x in sma20],
        "equity": eq_arr.tolist(),
        "trades": trades,
        "final_value": float(final_value),
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown_abs": max_drawdown_abs,
        "max_drawdown_pct": max_drawdown_pct,
        "buys": buys,
        "sells": sells,
    }

# TASK_02+ : add /universe, /prices/{symbol}, /indicators, /backtest here.
