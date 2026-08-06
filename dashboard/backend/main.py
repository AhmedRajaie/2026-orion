"""FastAPI backend for the dashboard."""
from pathlib import Path
import sys

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma

app = FastAPI(title="Trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

feed = DataFeed.from_dir("data/egx")


def _dates_to_strings(dates) -> list[str]:
    return [date.strftime("%Y-%m-%d") for date in dates]


def _get_close_prices(symbol: str) -> tuple[list[str], np.ndarray]:
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    index = feed.symbols.index(symbol)
    return _dates_to_strings(feed.dates), feed.close[:, index]


def _serialize_series(values) -> list[float | None]:
    serialized: list[float | None] = []
    for value in values:
        if value is None:
            serialized.append(None)
            continue
        try:
            if np.isnan(value):
                serialized.append(None)
            else:
                serialized.append(float(value))
        except TypeError:
            serialized.append(float(value))
    return serialized


def _sanitize_numeric_series(values) -> list[float | None]:
    sanitized: list[float | None] = []
    for value in values:
        if value is None:
            sanitized.append(None)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            sanitized.append(None)
            continue
        if not np.isfinite(numeric):
            sanitized.append(None)
        else:
            sanitized.append(numeric)
    return sanitized


def _sanitize_price_series(values) -> list[float | None]:
    sanitized: list[float | None] = []
    for value in values:
        if value is None:
            sanitized.append(None)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            sanitized.append(None)
            continue
        if not np.isfinite(numeric) or numeric <= 0.0:
            sanitized.append(None)
        else:
            sanitized.append(numeric)
    return sanitized


def _round_metric(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/universe")
def universe() -> list[str]:
    return feed.symbols


@app.get("/prices/{symbol}")
def prices(symbol: str) -> dict[str, list[float] | list[str]]:
    dates, close_prices = _get_close_prices(symbol)
    return {"dates": dates, "close": [float(value) for value in close_prices]}


@app.get("/indicators/{symbol}")
def indicators(symbol: str, window: int = 20) -> dict[str, list[float | None] | list[str]]:
    dates, close_prices = _get_close_prices(symbol)
    values = sma(close_prices, window)
    return {"dates": dates, "sma": _serialize_series(values)}


@app.get("/strategy/{symbol}")
def strategy(symbol: str) -> dict[str, list[float] | list[str] | int]:
    dates, close_prices = _get_close_prices(symbol)
    close = [float(value) for value in close_prices]
    sma9 = sma(close_prices, 9)
    sma20 = sma(close_prices, 20)

    cash = 1000.0
    shares = 0.0
    buy_count = 0
    sell_count = 0
    peak_value = 1000.0
    max_drawdown = 0.0
    portfolio: list[float] = []
    buy_points: list[str] = []
    sell_points: list[str] = []

    for index, price in enumerate(close):
        price_value = float(price)
        signal_buy = not np.isnan(sma9[index]) and not np.isnan(sma20[index]) and sma9[index] > sma20[index]
        signal_sell = not np.isnan(sma9[index]) and not np.isnan(sma20[index]) and sma9[index] < sma20[index]

        if shares <= 1e-12 and signal_buy and cash > 0.0:
            shares = cash / price_value
            cash = 0.0
            buy_count += 1
            buy_points.append(dates[index])
        elif shares > 1e-12 and signal_sell:
            cash += shares * price_value
            shares = 0.0
            sell_count += 1
            sell_points.append(dates[index])

        portfolio_value = cash + shares * price_value
        portfolio.append(float(portfolio_value))

        if portfolio_value > peak_value:
            peak_value = portfolio_value
        else:
            drawdown = (peak_value - portfolio_value) / peak_value if peak_value > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return {
        "dates": dates,
        "portfolio": portfolio,
        "buy_points": buy_points,
        "sell_points": sell_points,
        "final_value": float(portfolio[-1]) if portfolio else 1000.0,
        "max_drawdown": float(max_drawdown),
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


@app.get("/backtest/{symbol}")
def backtest(
    symbol: str,
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
) -> dict[str, object]:
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    if fast_window < 1:
        raise HTTPException(status_code=400, detail="fast_window must be at least 1")
    if slow_window < 2:
        raise HTTPException(status_code=400, detail="slow_window must be at least 2")
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")
    if initial_cash <= 0.0:
        raise HTTPException(status_code=400, detail="initial_cash must be greater than zero")

    symbol_index = feed.symbols.index(symbol)
    dates = _dates_to_strings(feed.dates)
    close_prices = feed.close[:, symbol_index]
    close_series = _sanitize_price_series(close_prices)
    fast_ma_series = _sanitize_numeric_series(sma(close_prices, fast_window))
    slow_ma_series = _sanitize_numeric_series(sma(close_prices, slow_window))

    cash = float(initial_cash)
    shares = 0
    portfolio_values: list[float] = []
    cash_history: list[float] = []
    shares_history: list[float] = []
    buy_markers: list[float | None] = [None] * len(dates)
    sell_markers: list[float | None] = [None] * len(dates)
    trades: list[dict[str, object]] = []
    last_portfolio_value = float(initial_cash)

    for index, price in enumerate(close_series):
        if price is not None and price > 0.0:
            fast_previous = fast_ma_series[index - 1] if index > 0 else None
            slow_previous = slow_ma_series[index - 1] if index > 0 else None

            if shares == 0 and fast_previous is not None and slow_previous is not None and fast_previous > slow_previous:
                shares_to_buy = int(cash // price)
                if shares_to_buy > 0:
                    cash -= shares_to_buy * price
                    shares += shares_to_buy
                    buy_markers[index] = price
                    trades.append(
                        {
                            "type": "BUY",
                            "date": dates[index],
                            "price": price,
                            "shares": shares_to_buy,
                            "cash_after": cash,
                            "portfolio_value_after": cash + shares * price,
                        }
                    )
            elif shares > 0 and fast_previous is not None and slow_previous is not None and fast_previous < slow_previous:
                cash += shares * price
                sell_markers[index] = price
                trades.append(
                    {
                        "type": "SELL",
                        "date": dates[index],
                        "price": price,
                        "shares": shares,
                        "cash_after": cash,
                        "portfolio_value_after": cash + shares * price,
                    }
                )
                shares = 0

            portfolio_value = cash + shares * price
        else:
            portfolio_value = last_portfolio_value

        portfolio_values.append(float(portfolio_value))
        cash_history.append(float(cash))
        shares_history.append(float(shares))
        last_portfolio_value = float(portfolio_value)

    if shares > 0:
        final_valid_price = None
        for price in reversed(close_series):
            if price is not None and price > 0.0:
                final_valid_price = price
                break
        if final_valid_price is not None:
            last_portfolio_value = cash + shares * final_valid_price
            portfolio_values[-1] = float(last_portfolio_value)

    buy_hold_cash = float(initial_cash)
    buy_hold_shares = 0
    buy_hold_values: list[float] = []
    last_buy_hold_value = float(initial_cash)

    for index, price in enumerate(close_series):
        if buy_hold_shares == 0 and price is not None and price > 0.0:
            shares_to_buy = int(buy_hold_cash // price)
            if shares_to_buy > 0:
                buy_hold_cash -= shares_to_buy * price
                buy_hold_shares += shares_to_buy

        if buy_hold_shares > 0 and price is not None and price > 0.0:
            value = buy_hold_cash + buy_hold_shares * price
            last_buy_hold_value = float(value)
        else:
            value = float(last_buy_hold_value)

        buy_hold_values.append(float(value))

    running_peak = float(initial_cash)
    max_drawdown_egp = 0.0
    max_drawdown_pct = 0.0
    for value in portfolio_values:
        if value > running_peak:
            running_peak = float(value)
        drawdown_egp = running_peak - value
        drawdown_pct = (drawdown_egp / running_peak * 100.0) if running_peak > 0.0 else 0.0
        if drawdown_egp > max_drawdown_egp:
            max_drawdown_egp = float(drawdown_egp)
        if drawdown_pct > max_drawdown_pct:
            max_drawdown_pct = float(drawdown_pct)

    final_portfolio_value = float(portfolio_values[-1]) if portfolio_values else float(initial_cash)
    initial_portfolio_value = float(initial_cash)
    profit_loss_egp = float(final_portfolio_value - initial_portfolio_value)
    total_return_pct = float((final_portfolio_value / initial_portfolio_value - 1.0) * 100.0) if initial_portfolio_value > 0.0 else 0.0

    buy_operations = sum(1 for trade in trades if trade["type"] == "BUY")
    sell_operations = sum(1 for trade in trades if trade["type"] == "SELL")
    completed_trades = sell_operations
    exposure_days = sum(1 for shares in shares_history if shares > 0)
    number_of_valid_days = sum(1 for price in close_series if price is not None and price > 0.0)
    exposure_pct = float((exposure_days / number_of_valid_days * 100.0) if number_of_valid_days > 0 else 0.0)

    buy_hold_final_value = float(buy_hold_values[-1]) if buy_hold_values else float(initial_cash)
    buy_hold_return_pct = float((buy_hold_final_value / initial_portfolio_value - 1.0) * 100.0) if initial_portfolio_value > 0.0 else 0.0
    excess_return_pct_points = float(total_return_pct - buy_hold_return_pct)

    chart_arrays = [
        close_series,
        fast_ma_series,
        slow_ma_series,
        buy_markers,
        sell_markers,
        portfolio_values,
        cash_history,
        shares_history,
        buy_hold_values,
    ]
    if not all(len(arr) == len(dates) for arr in chart_arrays):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if cash < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if shares < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if abs(buy_operations - sell_operations) > 1:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if final_portfolio_value < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")

    return {
        "symbol": symbol,
        "parameters": {
            "fast_window": fast_window,
            "slow_window": slow_window,
            "initial_cash": float(initial_cash),
        },
        "dates": dates,
        "close": close_series,
        "fast_ma": fast_ma_series,
        "slow_ma": slow_ma_series,
        "buy_markers": buy_markers,
        "sell_markers": sell_markers,
        "portfolio_values": portfolio_values,
        "buy_hold_values": buy_hold_values,
        "cash_history": cash_history,
        "shares_history": shares_history,
        "trades": trades,
        "kpis": {
            "initial_portfolio_value": _round_metric(initial_portfolio_value),
            "final_portfolio_value": _round_metric(final_portfolio_value),
            "profit_loss_egp": _round_metric(profit_loss_egp),
            "total_return_pct": _round_metric(total_return_pct),
            "maximum_drawdown_egp": _round_metric(max_drawdown_egp),
            "maximum_drawdown_pct": _round_metric(max_drawdown_pct),
            "buy_operations": buy_operations,
            "sell_operations": sell_operations,
            "total_operations": buy_operations + sell_operations,
            "completed_trades": completed_trades,
            "final_cash": _round_metric(cash),
            "final_shares": round(float(shares), 2),
            "current_position": "Invested" if shares > 0 else "Cash",
            "exposure_days": exposure_days,
            "exposure_pct": _round_metric(exposure_pct),
            "buy_hold_final_value": _round_metric(buy_hold_final_value),
            "buy_hold_return_pct": _round_metric(buy_hold_return_pct),
            "excess_return_pct_points": _round_metric(excess_return_pct_points),
        },
    }
