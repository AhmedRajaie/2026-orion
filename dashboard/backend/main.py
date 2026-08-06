"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

feed = DataFeed.from_dir("data/egx")


def _jsonable(values):
    out = []
    for value in values:
        if value is None:
            out.append(None)
            continue
        try:
            if not np.isfinite(value):
                out.append(None)
            else:
                out.append(float(value))
        except Exception:
            out.append(None)
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe():
    return feed.symbols


@app.get("/prices/{symbol}")
def prices(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="Unknown symbol")

    idx = feed.symbols.index(symbol)
    return {
        "dates": feed.dates.strftime("%Y-%m-%d").tolist(),
        "close": feed.close[:, idx].tolist(),
    }


@app.get("/indicators/{symbol}")
def indicators(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="Unknown symbol")

    idx = feed.symbols.index(symbol)
    prices = np.asarray(feed.close[:, idx], dtype=float)
    fast_ma = sma(prices, 9)
    slow_ma = sma(prices, 20)
    return {
        "symbol": symbol,
        "dates": feed.dates.strftime("%Y-%m-%d").tolist(),
        "close": _jsonable(prices),
        "fast_ma": _jsonable(fast_ma),
        "slow_ma": _jsonable(slow_ma),
    }


@app.get("/backtest/{symbol}")
def backtest(symbol: str, fast_window: int = 9, slow_window: int = 20, initial_cash: float = 1000.0):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="Unknown symbol")
    if fast_window < 1:
        raise HTTPException(status_code=400, detail="fast_window must be at least 1")
    if slow_window < 2:
        raise HTTPException(status_code=400, detail="slow_window must be at least 2")
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")
    if initial_cash <= 0:
        raise HTTPException(status_code=400, detail="initial_cash must be greater than 0")

    idx = feed.symbols.index(symbol)
    prices = np.asarray(feed.close[:, idx], dtype=float)
    dates = [d.strftime("%Y-%m-%d") for d in feed.dates]

    fast_ma = sma(prices, fast_window)
    slow_ma = sma(prices, slow_window)

    cash = float(initial_cash)
    shares = 0
    trades = []
    portfolio_values = []
    cash_history = []
    shares_history = []
    buy_markers = []
    sell_markers = []
    buy_hold_values = []

    last_valid_portfolio_value = float(initial_cash)
    last_valid_buy_hold_value = float(initial_cash)

    buy_hold_cash = float(initial_cash)
    buy_hold_shares = 0
    buy_hold_active = False

    for i, price in enumerate(prices):
        valid_price = np.isfinite(price) and price > 0

        if i == 0:
            if valid_price:
                last_valid_portfolio_value = float(cash + shares * price)
            portfolio_values.append(float(last_valid_portfolio_value))
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(None)
            sell_markers.append(None)
            if valid_price:
                last_valid_buy_hold_value = float(buy_hold_cash)
            buy_hold_values.append(float(last_valid_buy_hold_value))
            continue

        if valid_price:
            prev_fast = fast_ma[i - 1]
            prev_slow = slow_ma[i - 1]
            bought = False
            sold = False

            if np.isfinite(prev_fast) and np.isfinite(prev_slow) and prev_fast > prev_slow and shares == 0:
                shares_to_buy = int(cash // price)
                if shares_to_buy > 0:
                    cash -= shares_to_buy * price
                    shares += shares_to_buy
                    bought = True
                    trades.append({
                        "type": "BUY",
                        "date": dates[i],
                        "price": float(price),
                        "shares": int(shares_to_buy),
                        "cash_after": float(cash),
                        "portfolio_value_after": float(cash + shares * price),
                    })
            elif np.isfinite(prev_fast) and np.isfinite(prev_slow) and prev_fast < prev_slow and shares > 0 and i != len(prices) - 1:
                shares_sold = shares
                cash += shares * price
                shares = 0
                sold = True
                trades.append({
                    "type": "SELL",
                    "date": dates[i],
                    "price": float(price),
                    "shares": int(shares_sold),
                    "cash_after": float(cash),
                    "portfolio_value_after": float(cash),
                })

            portfolio_value = cash + shares * price if valid_price else last_valid_portfolio_value
            last_valid_portfolio_value = float(portfolio_value)
            portfolio_values.append(float(portfolio_value))
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(float(price) if bought else None)
            sell_markers.append(float(price) if sold else None)

            if not buy_hold_active and valid_price:
                shares_to_buy_bh = int(buy_hold_cash // price)
                if shares_to_buy_bh > 0:
                    buy_hold_cash -= shares_to_buy_bh * price
                    buy_hold_shares += shares_to_buy_bh
                    buy_hold_active = True
            if buy_hold_active:
                buy_hold_value = buy_hold_cash + buy_hold_shares * price
                last_valid_buy_hold_value = float(buy_hold_value)
            buy_hold_values.append(float(last_valid_buy_hold_value))
        else:
            portfolio_values.append(float(last_valid_portfolio_value))
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(None)
            sell_markers.append(None)
            buy_hold_values.append(float(last_valid_buy_hold_value))

    # Rebuild trades with the correct shares count for sell operations.
    corrected_trades = []
    for entry in trades:
        if entry["type"] == "SELL":
            corrected_trades.append(entry)
        else:
            corrected_trades.append(entry)

    buy_operations = sum(1 for entry in corrected_trades if entry["type"] == "BUY")
    sell_operations = sum(1 for entry in corrected_trades if entry["type"] == "SELL")

    portfolio_values_json = _jsonable(np.asarray(portfolio_values, dtype=float))
    cash_history_json = _jsonable(np.asarray(cash_history, dtype=float))
    shares_history_json = _jsonable(np.asarray(shares_history, dtype=float))
    buy_markers_json = _jsonable(np.asarray(buy_markers, dtype=float))
    sell_markers_json = _jsonable(np.asarray(sell_markers, dtype=float))
    buy_hold_values_json = _jsonable(np.asarray(buy_hold_values, dtype=float))

    if len(portfolio_values_json) != len(dates):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if len(cash_history_json) != len(dates):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if len(shares_history_json) != len(dates):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if len(buy_markers_json) != len(dates):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if len(sell_markers_json) != len(dates):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if len(buy_hold_values_json) != len(dates):
        raise HTTPException(status_code=500, detail="Backtest validation failed")

    if cash < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if shares < 0:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if abs(buy_operations - sell_operations) > 1:
        raise HTTPException(status_code=500, detail="Backtest validation failed")

    final_portfolio_value = portfolio_values_json[-1]
    if final_portfolio_value is None or final_portfolio_value < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")

    running_peak = None
    max_drawdown_egp = 0.0
    max_drawdown_pct = 0.0
    for value in portfolio_values_json:
        if value is None:
            continue
        if running_peak is None or value > running_peak:
            running_peak = value
        drawdown = running_peak - value
        if drawdown > max_drawdown_egp:
            max_drawdown_egp = drawdown
            if running_peak > 0:
                max_drawdown_pct = (drawdown / running_peak) * 100
            else:
                max_drawdown_pct = 0.0

    valid_days = 0
    exposure_days = 0
    for price, share_count in zip(prices, shares_history):
        if np.isfinite(price) and price > 0:
            valid_days += 1
        if share_count > 0:
            exposure_days += 1
    if valid_days == 0:
        exposure_pct = 0.0
    else:
        exposure_pct = (exposure_days / valid_days) * 100

    initial_portfolio_value = float(initial_cash)
    final_portfolio_value_value = float(final_portfolio_value)
    profit_loss_egp = final_portfolio_value_value - initial_portfolio_value
    total_return_pct = ((final_portfolio_value_value / initial_portfolio_value) - 1.0) * 100.0 if initial_portfolio_value > 0 else 0.0
    buy_hold_final_value = float(buy_hold_values_json[-1] if buy_hold_values_json else initial_portfolio_value)
    buy_hold_return_pct = ((buy_hold_final_value / initial_portfolio_value) - 1.0) * 100.0 if initial_portfolio_value > 0 else 0.0
    excess_return_pct_points = total_return_pct - buy_hold_return_pct

    return {
        "symbol": symbol,
        "parameters": {
            "fast_window": fast_window,
            "slow_window": slow_window,
            "initial_cash": float(initial_cash),
        },
        "dates": dates,
        "close": _jsonable(prices),
        "fast_ma": _jsonable(fast_ma),
        "slow_ma": _jsonable(slow_ma),
        "buy_markers": buy_markers_json,
        "sell_markers": sell_markers_json,
        "portfolio_values": portfolio_values_json,
        "buy_hold_values": buy_hold_values_json,
        "cash_history": cash_history_json,
        "shares_history": shares_history_json,
        "trades": corrected_trades,
        "kpis": {
            "initial_portfolio_value": round(initial_portfolio_value, 2),
            "final_portfolio_value": round(final_portfolio_value_value, 2),
            "profit_loss_egp": round(profit_loss_egp, 2),
            "total_return_pct": round(total_return_pct, 2),
            "maximum_drawdown_egp": round(max_drawdown_egp, 2),
            "maximum_drawdown_pct": round(max_drawdown_pct, 2),
            "buy_operations": buy_operations,
            "sell_operations": sell_operations,
            "total_operations": buy_operations + sell_operations,
            "completed_trades": sell_operations,
            "final_cash": round(cash, 2),
            "final_shares": int(shares),
            "current_position": "Invested" if shares > 0 else "Cash",
            "exposure_days": exposure_days,
            "exposure_pct": round(exposure_pct, 2),
            "buy_hold_final_value": round(buy_hold_final_value, 2),
            "buy_hold_return_pct": round(buy_hold_return_pct, 2),
            "excess_return_pct_points": round(excess_return_pct_points, 2),
        },
    }

# TASK_02+ : add /indicators, /backtest here.
