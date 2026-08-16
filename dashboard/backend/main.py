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
import json
import re
import os

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


def _run_sma_backtest(prices, dates, initial, commission_rate: float = 0.0):
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
            # Buy: use available cash, charge commission on amount bought
            if price > 0 and cash > 0:
                amount = cash
                commission = commission_rate * amount
                net_amount = max(0.0, amount - commission)
                if net_amount > 0 and price > 0:
                    shares = net_amount / price
                    cash = 0.0
                    buys += 1
                    trades.append({
                        "index": t,
                        "date": dates[t],
                        "type": "buy",
                        "price": price,
                        "shares": shares,
                        "cash": cash,
                        "commission": float(commission),
                    })
        elif prev_pos == 1 and cur_pos == 0:
            # Sell: convert shares to cash, subtract commission on proceeds
            if shares > 0:
                proceeds = shares * price
                commission = commission_rate * proceeds
                cash = max(0.0, proceeds - commission)
                shares = 0.0
                sells += 1
                trades.append({
                    "index": t,
                    "date": dates[t],
                    "type": "sell",
                    "price": price,
                    "shares": 0.0,
                    "cash": cash,
                    "commission": float(commission),
                })
        equity.append(cash + shares * price)
        prev_pos = cur_pos

    metrics = _performance_metrics_from_equity(equity, initial)
    metrics.update({"buys": buys, "sells": sells, "equity": [float(x) for x in equity], "trades": trades})
    return metrics, sma9, sma20


def _run_drop_rise_backtest(prices, dates, initial, buy_threshold=0.05, sell_threshold=0.10, commission_rate: float = 0.0):
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
                commission = commission_rate * amount
                net_amount = max(0.0, amount - commission)
                if net_amount > 0:
                    share_qty = net_amount / price
                    shares += share_qty
                    # cash pays the amount + commission
                    cash -= (amount + commission)
                    buys += 1
                    trades.append({
                        "index": t,
                        "date": dates[t],
                        "type": "buy",
                        "price": price,
                        "shares": share_qty,
                        "cash": cash,
                        "commission": float(commission),
                    })
        elif change >= sell_threshold and shares > 0:
            amount = min(shares * price, change * portfolio_value)
            if amount > 0 and price > 0:
                commission = commission_rate * amount
                share_qty = amount / price
                shares -= share_qty
                proceeds = max(0.0, amount - commission)
                cash += proceeds
                sells += 1
                trades.append({
                    "index": t,
                    "date": dates[t],
                    "type": "sell",
                    "price": price,
                    "shares": share_qty,
                    "cash": cash,
                    "commission": float(commission),
                })
        equity.append(cash + shares * price)

    metrics = _performance_metrics_from_equity(equity, initial)
    metrics.update({"buys": buys, "sells": sells, "equity": [float(x) for x in equity], "trades": trades})
    return metrics


@app.get("/backtest/{symbol}")
def backtest(symbol: str, initial: float = 1000.0, commission_symbol: str | None = None, commission_rate: float = 0.0, apply_commission_to_all: bool = False):
    """Simple per-symbol backtest of two strategies.
    - Base SMA crossover strategy from notebook 4
    - Drop/rise strategy: buy on >5% drop, sell on >10% rise
    Optional query params:
      - commission_symbol: if set and equals `symbol`, commission_rate is applied to trades on this symbol
      - commission_rate: float (e.g. 0.001 == 10 bps)
    Returns prices, SMA lines, and both strategy performance summaries.
    """
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx].astype(float)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]

    # apply commission: either globally if apply_commission_to_all=True, or when commission_symbol matches
    if apply_commission_to_all:
        comm = float(commission_rate)
    else:
        comm = float(commission_rate) if (commission_symbol and commission_symbol == symbol) else 0.0

    base_metrics, sma9, sma20 = _run_sma_backtest(prices, dates, initial, commission_rate=comm)
    new_metrics = _run_drop_rise_backtest(prices, dates, initial, commission_rate=comm)

    return {
        "dates": dates,
        "price": prices.tolist(),
        "sma9": [None if np.isnan(x) else float(x) for x in sma9],
        "sma20": [None if np.isnan(x) else float(x) for x in sma20],
        "base": base_metrics,
        "new_strategy": new_metrics,
    }


@app.get("/metrics/{symbol}")
def metrics(symbol: str, initial: float = 1000.0, commission_symbol: str | None = None, commission_rate: float = 0.0, apply_commission_to_all: bool = False):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    idx = feed.symbols.index(symbol)
    prices = feed.close[:, idx].astype(float)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]
    if apply_commission_to_all:
        comm = float(commission_rate)
    else:
        comm = float(commission_rate) if (commission_symbol and commission_symbol == symbol) else 0.0
    base_metrics, _, _ = _run_sma_backtest(prices, dates, initial, commission_rate=comm)
    new_metrics = _run_drop_rise_backtest(prices, dates, initial, commission_rate=comm)
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

def _extract_test_loss_from_nb(nb_path):
    """Try to find a final test loss floating value inside a notebook's outputs or source.
    Returns float or None.
    """
    try:
        with open(nb_path, "r", encoding="utf-8") as f:
            nb = json.load(f)
    except Exception:
        return None

    texts = []
    for cell in nb.get("cells", []):
        # source lines
        for s in cell.get("source", []):
            texts.append(str(s))
        # outputs (text/plain, stream, etc.)
        for out in cell.get("outputs", []):
            if out.get("output_type") == "stream":
                texts.append("\n".join(out.get("text", [])))
            for k in ("text", "data"):
                v = out.get(k)
                if not v:
                    continue
                if isinstance(v, str):
                    texts.append(v)
                elif isinstance(v, dict):
                    # data can contain 'text/plain'
                    tp = v.get("text/plain") or v.get("text")
                    if tp:
                        if isinstance(tp, list):
                            texts.append("\n".join(tp))
                        else:
                            texts.append(str(tp))
                elif isinstance(v, list):
                    texts.append("\n".join(v))

    combined = "\n".join(texts)
    # common patterns: 'final test loss: 0.00123', 'MLP test loss: 0.01402', 'LSTM (5-step window) test loss: 0.00186'
    # find all floats after 'test loss' or 'test_loss' or 'final test loss'
    m = re.findall(r"test[ _]?loss[^0-9\n\r:]*:?[\s]*([0-9]*\.[0-9]+)", combined, flags=re.IGNORECASE)
    if m:
        try:
            return float(m[-1])
        except Exception:
            pass
    # fallback: any standalone float near 'final'
    m2 = re.findall(r"final[^\n\r]*:\s*([0-9]*\.[0-9]+)", combined, flags=re.IGNORECASE)
    if m2:
        try:
            return float(m2[-1])
        except Exception:
            pass
    # last resort: any float in the notebook (take last)
    all_floats = re.findall(r"([0-9]*\.[0-9]+)", combined)
    if all_floats:
        try:
            return float(all_floats[-1])
        except Exception:
            pass
    return None


@app.get("/compare")
def compare():
    """Return a small JSON with final test losses for MLP and LSTM.
    If dashboard/data/model_compare.json exists it will be returned; otherwise
    attempt to extract numbers from the week2 notebooks and save the file.
    """
    data_dir = ROOT / "dashboard" / "data"
    model_file = data_dir / "model_compare.json"
    # if file already exists, return it
    if model_file.exists():
        try:
            with open(model_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # try to extract from known notebook locations
    candidates = {
        "mlp": [ROOT / "week2" / "01-mlp" / "task_week2.ipynb", ROOT / "week2" / "01-mlp" / "notebook.ipynb"],
        "lstm": [ROOT / "week2" / "02-lstm" / "notebook.ipynb", ROOT / "week2" / "01-mlp" / "lstm.ipynb", ROOT / "week2" / "03-form-prediction-to-portfolio" / "lstm.ipynb"],
    }

    result = {"mlp": None, "lstm": None}
    for key, paths in candidates.items():
        for p in paths:
            if p.exists():
                v = _extract_test_loss_from_nb(str(p))
                if v is not None:
                    result[key] = float(v)
                    break

    # ensure folder exists and write file for future quick reads
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(model_file, "w", encoding="utf-8") as f:
            json.dump(result, f)
    except Exception:
        pass

    return result


# --- Week2 endpoints: expose notebook-produced JSON files for frontend panels ---
@app.get("/mlp")
def mlp():
    """Return the MLP equity JSON saved by the week2 notebook: dashboard/data/nn_equity.json"""
    data_dir = ROOT / "dashboard" / "data"
    f = data_dir / "nn_equity.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="mlp equity file not found")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/lstm")
def lstm():
    """Return the LSTM equity JSON saved by the week2 notebook: dashboard/data/lstm_equity.json"""
    data_dir = ROOT / "dashboard" / "data"
    f = data_dir / "lstm_equity.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="lstm equity file not found")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/loss")
def loss():
    """Return the MLP loss file saved by week2 notebook: dashboard/data/mlp_loss.json"""
    data_dir = ROOT / "dashboard" / "data"
    f = data_dir / "mlp_loss.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="mlp loss file not found")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/predictor")
def predictor():
    """Return predictor_equity.json if present (optional notebook output)."""
    data_dir = ROOT / "dashboard" / "data"
    f = data_dir / "predictor_equity.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="predictor equity file not found")
    try:
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
