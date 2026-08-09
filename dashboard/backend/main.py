"""FastAPI backend for the dashboard.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from __future__ import annotations

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradinglab import metrics as trading_metrics
from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SMALL_UNIVERSE_SYMBOLS = ["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK"]
FEEDS = {
    "small": DataFeed.from_dir("data/egx", symbols=SMALL_UNIVERSE_SYMBOLS),
    "full": DataFeed.from_dir("data/egx"),
}

EPSILON = 1e-12


def get_feed_for_universe(universe: str) -> DataFeed:
    feed = FEEDS.get(universe)
    if feed is None:
        raise HTTPException(status_code=400, detail="universe must be 'small' or 'full'")
    return feed


def get_symbol_or_404(feed: DataFeed, symbol: str | None) -> str:
    chosen = symbol or feed.symbols[0]
    if chosen not in feed.symbols:
        raise HTTPException(status_code=404, detail="Unknown symbol")
    return chosen


def validate_contrarian_parameters(
    lookback_days: int,
    buy_threshold: float,
    sell_threshold: float,
    buy_notional: float,
    sell_notional: float,
    initial_cash: float,
) -> None:
    if lookback_days < 1:
        raise HTTPException(status_code=400, detail="lookback_days must be at least 1")
    if buy_threshold >= 0:
        raise HTTPException(status_code=400, detail="buy_threshold must be negative")
    if sell_threshold <= 0:
        raise HTTPException(status_code=400, detail="sell_threshold must be positive")
    if buy_notional <= 0:
        raise HTTPException(status_code=400, detail="buy_notional must be greater than 0")
    if sell_notional <= 0:
        raise HTTPException(status_code=400, detail="sell_notional must be greater than 0")
    if initial_cash <= 0:
        raise HTTPException(status_code=400, detail="initial_cash must be greater than 0")


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def _equity_to_returns(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return np.array([], dtype=float)

    returns = np.zeros(len(values) - 1, dtype=float)
    prev = values[:-1]
    curr = values[1:]
    valid = np.isfinite(prev) & np.isfinite(curr) & (prev > 0)
    returns[valid] = curr[valid] / prev[valid] - 1.0
    return returns


def _max_drawdown_egp(values: np.ndarray) -> float:
    curve = np.asarray(values, dtype=float)
    running_peak = np.maximum.accumulate(curve)
    drawdown = running_peak - curve
    return float(np.max(drawdown)) if len(drawdown) else 0.0


def _round_metrics(metrics: dict) -> dict:
    rounded = {}
    for key, value in metrics.items():
        if isinstance(value, (int, np.integer)):
            rounded[key] = int(value)
        elif isinstance(value, (float, np.floating)):
            numeric = float(value)
            rounded[key] = round(numeric, 3) if np.isfinite(numeric) else None
        else:
            rounded[key] = value
    return rounded


def run_weekly_contrarian_backtest(
    feed: DataFeed,
    lookback_days: int = 5,
    buy_threshold: float = -0.05,
    sell_threshold: float = 0.10,
    buy_notional: float = 5.0,
    sell_notional: float = 10.0,
    initial_cash: float = 1000.0,
    selected_symbol: str | None = None,
) -> dict:
    if feed.n_days <= lookback_days:
        raise ValueError("not enough history for the chosen lookback_days")

    chosen_symbol = selected_symbol or feed.symbols[0]
    if chosen_symbol not in feed.symbols:
        raise ValueError(f"Unknown symbol '{chosen_symbol}'")

    dates = feed.dates
    symbols = feed.symbols
    close = np.asarray(feed.close, dtype=float)
    n_days = feed.n_days
    n_stocks = feed.n_assets
    selected_index = symbols.index(chosen_symbol)

    weekly_signals = np.full_like(close, fill_value=np.nan, dtype=float)
    for t in range(n_days):
        idx_recent = t - 1
        idx_earlier = t - 1 - lookback_days
        if idx_recent < 0 or idx_earlier < 0:
            continue

        recent = close[idx_recent]
        earlier = close[idx_earlier]
        for j in range(n_stocks):
            p_recent = recent[j]
            p_earlier = earlier[j]
            if not (np.isfinite(p_recent) and np.isfinite(p_earlier)):
                continue
            if p_recent <= 0 or p_earlier <= 0:
                continue
            weekly_signals[t, j] = p_recent / p_earlier - 1.0

    cash = float(initial_cash)
    holdings = np.zeros(n_stocks, dtype=float)
    latest_valid_price = np.full(n_stocks, np.nan, dtype=float)

    benchmark_cash = float(initial_cash)
    benchmark_holdings = np.zeros(n_stocks, dtype=float)
    benchmark_latest_valid_price = np.full(n_stocks, np.nan, dtype=float)

    first_prices = close[0]
    valid_benchmark_start = np.isfinite(first_prices) & (first_prices > 0)
    benchmark_assets = int(valid_benchmark_start.sum())
    if benchmark_assets > 0:
        equal_notional = initial_cash / benchmark_assets
        for j in range(n_stocks):
            if not valid_benchmark_start[j]:
                continue
            benchmark_holdings[j] = equal_notional / first_prices[j]
            benchmark_latest_valid_price[j] = first_prices[j]
        benchmark_cash = 0.0

    portfolio_values = np.full(n_days, np.nan, dtype=float)
    benchmark_values = np.full(n_days, np.nan, dtype=float)
    cash_history = np.full(n_days, np.nan, dtype=float)
    invested_history = np.full(n_days, np.nan, dtype=float)
    positions_history = np.zeros(n_days, dtype=int)
    daily_buy_ops = np.zeros(n_days, dtype=int)
    daily_sell_ops = np.zeros(n_days, dtype=int)
    selected_buy_markers = [None] * n_days
    selected_sell_markers = [None] * n_days

    total_buy_operations = 0
    total_sell_operations = 0
    skipped_buy_operations = 0
    trade_log: list[dict] = []

    for t in range(n_days):
        today_price = close[t]
        signal = weekly_signals[t]

        for j in range(n_stocks):
            price = today_price[j]
            if np.isfinite(price) and price > 0:
                latest_valid_price[j] = price
                benchmark_latest_valid_price[j] = price

        sells_today = 0
        for j in range(n_stocks):
            sig = signal[j]
            price = today_price[j]
            if not (np.isfinite(sig) and np.isfinite(price) and price > 0):
                continue
            if sig >= sell_threshold and holdings[j] > EPSILON:
                position_value = holdings[j] * price
                actual_sell_value = min(sell_notional, position_value)
                if actual_sell_value <= EPSILON:
                    continue
                shares_to_sell = min(actual_sell_value / price, holdings[j])
                holdings[j] -= shares_to_sell
                if holdings[j] < EPSILON:
                    holdings[j] = 0.0
                cash += actual_sell_value
                sells_today += 1
                total_sell_operations += 1
                if j == selected_index:
                    selected_sell_markers[t] = float(price)
                trade_log.append({
                    "date": dates[t].strftime("%Y-%m-%d"),
                    "symbol": symbols[j],
                    "operation": "SELL",
                    "signal_return": float(sig),
                    "price": float(price),
                    "notional": float(actual_sell_value),
                    "shares": float(shares_to_sell),
                    "cash_after": float(cash),
                    "position_after": float(holdings[j]),
                    "position_shares_after": float(holdings[j]),
                })

        daily_sell_ops[t] = sells_today

        buys_today = 0
        for j in range(n_stocks):
            sig = signal[j]
            price = today_price[j]
            if not (np.isfinite(sig) and np.isfinite(price) and price > 0):
                continue
            if sig <= buy_threshold:
                actual_buy_value = min(buy_notional, cash)
                if actual_buy_value <= EPSILON:
                    skipped_buy_operations += 1
                    continue
                shares_to_buy = actual_buy_value / price
                holdings[j] += shares_to_buy
                cash -= actual_buy_value
                if cash < EPSILON:
                    cash = max(cash, 0.0)
                buys_today += 1
                total_buy_operations += 1
                if j == selected_index:
                    selected_buy_markers[t] = float(price)
                trade_log.append({
                    "date": dates[t].strftime("%Y-%m-%d"),
                    "symbol": symbols[j],
                    "operation": "BUY",
                    "signal_return": float(sig),
                    "price": float(price),
                    "notional": float(actual_buy_value),
                    "shares": float(shares_to_buy),
                    "cash_after": float(cash),
                    "position_after": float(holdings[j]),
                    "position_shares_after": float(holdings[j]),
                })

        daily_buy_ops[t] = buys_today

        invested = 0.0
        open_positions = 0
        for j in range(n_stocks):
            if holdings[j] <= EPSILON:
                continue
            price_for_value = latest_valid_price[j]
            if np.isfinite(price_for_value) and price_for_value > 0:
                invested += holdings[j] * price_for_value
                open_positions += 1

        benchmark_invested = 0.0
        for j in range(n_stocks):
            if benchmark_holdings[j] <= EPSILON:
                continue
            price_for_value = benchmark_latest_valid_price[j]
            if np.isfinite(price_for_value) and price_for_value > 0:
                benchmark_invested += benchmark_holdings[j] * price_for_value

        portfolio_values[t] = cash + invested
        benchmark_values[t] = benchmark_cash + benchmark_invested
        cash_history[t] = cash
        invested_history[t] = invested
        positions_history[t] = open_positions

    portfolio_returns = _equity_to_returns(portfolio_values)
    benchmark_returns = _equity_to_returns(benchmark_values)

    total_return = trading_metrics.total_return(portfolio_returns) if len(portfolio_returns) else 0.0
    sharpe_ratio = trading_metrics.sharpe(portfolio_returns) if len(portfolio_returns) else 0.0
    max_drawdown = trading_metrics.max_drawdown(portfolio_returns) if len(portfolio_returns) else 0.0
    benchmark_total_return = (
        trading_metrics.total_return(benchmark_returns) if len(benchmark_returns) else 0.0
    )

    final_portfolio_value = float(portfolio_values[-1])
    profit_loss = final_portfolio_value - initial_cash
    final_invested_value = float(invested_history[-1])
    maximum_drawdown_egp = _max_drawdown_egp(portfolio_values)

    metrics = {
        "total_return": float(total_return),
        "sharpe": float(sharpe_ratio),
        "max_drawdown": float(max_drawdown),
        "final_portfolio_value": float(final_portfolio_value),
        "profit_loss_egp": float(profit_loss),
        "maximum_drawdown_egp": float(maximum_drawdown_egp),
        "buy_operations": int(total_buy_operations),
        "sell_operations": int(total_sell_operations),
        "total_operations": int(total_buy_operations + total_sell_operations),
        "skipped_buy_operations": int(skipped_buy_operations),
        "final_cash": float(cash),
        "final_invested_value": float(final_invested_value),
        "open_positions": int((holdings > EPSILON).sum()),
        "unique_stocks_traded": int(len({trade["symbol"] for trade in trade_log})),
        "average_positions_held": float(np.mean(positions_history)) if len(positions_history) else 0.0,
        "benchmark_total_return": float(benchmark_total_return),
        "excess_return": float(total_return - benchmark_total_return),
    }

    return {
        "strategy": {
            "name": "Weekly contrarian strategy",
            "description": (
                "Buy 5 EGP after a weekly decline of at least 5% and sell 10 EGP "
                "after a weekly rise of at least 10%."
            ),
        },
        "symbols": list(symbols),
        "selected_symbol": chosen_symbol,
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "portfolio": portfolio_values / initial_cash,
        "benchmark": benchmark_values / initial_cash,
        "portfolio_values_egp": portfolio_values,
        "benchmark_values_egp": benchmark_values,
        "cash_history": cash_history,
        "invested_value_history": invested_history,
        "number_of_positions_history": positions_history,
        "daily_buy_operations": daily_buy_ops,
        "daily_sell_operations": daily_sell_ops,
        "selected_asset": {
            "dates": [d.strftime("%Y-%m-%d") for d in dates],
            "close": close[:, selected_index],
            "buy_markers": selected_buy_markers,
            "sell_markers": selected_sell_markers,
        },
        "trades": trade_log,
        "metrics": metrics,
    }


def _legacy_single_stock_backtest(
    feed: DataFeed,
    symbol: str,
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
) -> dict:
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
            portfolio_values.append(last_valid_portfolio_value)
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(None)
            sell_markers.append(None)
            buy_hold_values.append(float(buy_hold_cash))
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
            elif (
                np.isfinite(prev_fast)
                and np.isfinite(prev_slow)
                and prev_fast < prev_slow
                and shares > 0
                and i != len(prices) - 1
            ):
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

            last_valid_portfolio_value = float(cash + shares * price)
            portfolio_values.append(last_valid_portfolio_value)
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(float(price) if bought else None)
            sell_markers.append(float(price) if sold else None)

            if not buy_hold_active:
                shares_to_buy_bh = int(buy_hold_cash // price)
                if shares_to_buy_bh > 0:
                    buy_hold_cash -= shares_to_buy_bh * price
                    buy_hold_shares += shares_to_buy_bh
                    buy_hold_active = True
            last_valid_buy_hold_value = float(buy_hold_cash + buy_hold_shares * price)
            buy_hold_values.append(last_valid_buy_hold_value)
        else:
            portfolio_values.append(last_valid_portfolio_value)
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(None)
            sell_markers.append(None)
            buy_hold_values.append(last_valid_buy_hold_value)

    buy_operations = sum(1 for trade in trades if trade["type"] == "BUY")
    sell_operations = sum(1 for trade in trades if trade["type"] == "SELL")

    running_peak = None
    max_drawdown_egp = 0.0
    max_drawdown_pct = 0.0
    for value in portfolio_values:
        if running_peak is None or value > running_peak:
            running_peak = value
        drawdown = running_peak - value
        if drawdown > max_drawdown_egp:
            max_drawdown_egp = drawdown
            max_drawdown_pct = (drawdown / running_peak * 100.0) if running_peak > 0 else 0.0

    valid_days = sum(1 for price in prices if np.isfinite(price) and price > 0)
    exposure_days = sum(1 for share_count in shares_history if share_count > 0)
    exposure_pct = (exposure_days / valid_days * 100.0) if valid_days else 0.0

    final_portfolio_value = float(portfolio_values[-1])
    buy_hold_final_value = float(buy_hold_values[-1])
    total_return_pct = ((final_portfolio_value / initial_cash) - 1.0) * 100.0
    buy_hold_return_pct = ((buy_hold_final_value / initial_cash) - 1.0) * 100.0

    return {
        "symbol": symbol,
        "parameters": {
            "fast_window": fast_window,
            "slow_window": slow_window,
            "initial_cash": float(initial_cash),
        },
        "dates": dates,
        "close": prices,
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "buy_markers": buy_markers,
        "sell_markers": sell_markers,
        "portfolio_values": portfolio_values,
        "buy_hold_values": buy_hold_values,
        "cash_history": cash_history,
        "shares_history": shares_history,
        "trades": trades,
        "kpis": {
            "initial_portfolio_value": float(initial_cash),
            "final_portfolio_value": final_portfolio_value,
            "profit_loss_egp": final_portfolio_value - initial_cash,
            "total_return_pct": total_return_pct,
            "maximum_drawdown_egp": max_drawdown_egp,
            "maximum_drawdown_pct": max_drawdown_pct,
            "buy_operations": buy_operations,
            "sell_operations": sell_operations,
            "total_operations": buy_operations + sell_operations,
            "completed_trades": sell_operations,
            "final_cash": float(cash),
            "final_shares": int(shares),
            "current_position": "Invested" if shares > 0 else "Cash",
            "exposure_days": exposure_days,
            "exposure_pct": exposure_pct,
            "buy_hold_final_value": buy_hold_final_value,
            "buy_hold_return_pct": buy_hold_return_pct,
            "excess_return_pct_points": total_return_pct - buy_hold_return_pct,
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe(universe: str = "small"):
    feed = get_feed_for_universe(universe)
    return feed.symbols


@app.get("/prices/{symbol}")
def prices(symbol: str, universe: str = "small"):
    feed = get_feed_for_universe(universe)
    chosen = get_symbol_or_404(feed, symbol)
    idx = feed.symbols.index(chosen)
    return _jsonable({
        "symbol": chosen,
        "universe": universe,
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": feed.close[:, idx],
    })


@app.get("/indicators/{symbol}")
def indicators(symbol: str, universe: str = "small", fast_window: int = 9, slow_window: int = 20):
    feed = get_feed_for_universe(universe)
    chosen = get_symbol_or_404(feed, symbol)
    if fast_window < 1:
        raise HTTPException(status_code=400, detail="fast_window must be at least 1")
    if slow_window < 2:
        raise HTTPException(status_code=400, detail="slow_window must be at least 2")
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")

    idx = feed.symbols.index(chosen)
    prices = np.asarray(feed.close[:, idx], dtype=float)
    fast_ma = sma(prices, fast_window)
    slow_ma = sma(prices, slow_window)
    return _jsonable({
        "symbol": chosen,
        "universe": universe,
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": prices,
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
    })


@app.get("/backtest")
def backtest(
    universe: str = "small",
    symbol: str | None = None,
    lookback_days: int = 5,
    buy_threshold: float = -0.05,
    sell_threshold: float = 0.10,
    buy_notional: float = 5.0,
    sell_notional: float = 10.0,
    initial_cash: float = 1000.0,
):
    feed = get_feed_for_universe(universe)
    validate_contrarian_parameters(
        lookback_days=lookback_days,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        initial_cash=initial_cash,
    )
    chosen = get_symbol_or_404(feed, symbol)

    try:
        result = run_weekly_contrarian_backtest(
            feed,
            lookback_days=lookback_days,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            buy_notional=buy_notional,
            sell_notional=sell_notional,
            initial_cash=initial_cash,
            selected_symbol=chosen,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["universe"] = universe
    result["parameters"] = {
        "lookback_days": lookback_days,
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "initial_cash": initial_cash,
    }
    return _jsonable(result)


@app.get("/metrics")
def metrics(
    universe: str = "small",
    lookback_days: int = 5,
    buy_threshold: float = -0.05,
    sell_threshold: float = 0.10,
    buy_notional: float = 5.0,
    sell_notional: float = 10.0,
    initial_cash: float = 1000.0,
):
    feed = get_feed_for_universe(universe)
    validate_contrarian_parameters(
        lookback_days=lookback_days,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        initial_cash=initial_cash,
    )

    try:
        result = run_weekly_contrarian_backtest(
            feed,
            lookback_days=lookback_days,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            buy_notional=buy_notional,
            sell_notional=sell_notional,
            initial_cash=initial_cash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = {
        "strategy_name": "Weekly contrarian strategy",
        "universe": universe,
        "parameters": {
            "lookback_days": lookback_days,
            "buy_threshold": buy_threshold,
            "sell_threshold": sell_threshold,
            "buy_notional": buy_notional,
            "sell_notional": sell_notional,
            "initial_cash": initial_cash,
        },
    }
    response.update(_round_metrics(result["metrics"]))
    return _jsonable(response)


@app.get("/backtest/{symbol}")
def legacy_sma_backtest(
    symbol: str,
    universe: str = "small",
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
):
    feed = get_feed_for_universe(universe)
    chosen = get_symbol_or_404(feed, symbol)
    result = _legacy_single_stock_backtest(
        feed,
        chosen,
        fast_window=fast_window,
        slow_window=slow_window,
        initial_cash=initial_cash,
    )
    return _jsonable(result)
