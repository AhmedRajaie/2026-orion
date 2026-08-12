"""FastAPI backend for the dashboard.

Run:
uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradinglab.backtester import run_backtest
from tradinglab.data_feed import DataFeed
from tradinglab.metrics import max_drawdown, sharpe, total_return
from tradinglab.observation import build_observation
from tradinglab.simulator import PortfolioSimulator
from tradinglab.strategies.mean_reversion import weekly_loser_weights

app = FastAPI(title="Younit-style trading dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "egx"
DATA_FILE = REPO_ROOT / "data" / "egx" / "SAUD.csv"
NN_EQUITY_FILE = REPO_ROOT / "dashboard" / "data" / "nn_equity.json"


def get_asset_file(symbol: str) -> Path:
    symbol = symbol.upper()

    available_files = {
        file.stem.upper(): file
        for file in DATA_DIR.glob("*.csv")
        if file.is_file()
    }

    if symbol not in available_files:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown asset: {symbol}",
        )

    return available_files[symbol]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/portfolio/lstm")
def lstm_portfolio():
    """Return the optimized LSTM equity curve exported by the Day 3 notebook."""
    if not NN_EQUITY_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Run the Day 3 comparison notebook to export nn_equity.json.",
        )

    payload = json.loads(NN_EQUITY_FILE.read_text())
    dates = payload.get("dates", [])
    portfolio = np.asarray(payload.get("portfolio", []), dtype=float)
    benchmark = np.asarray(payload.get("benchmark", []), dtype=float)
    if not dates or len(dates) != len(portfolio) or len(dates) != len(benchmark):
        raise HTTPException(status_code=500, detail="Invalid LSTM equity export.")

    initial_cash = 1000.0
    portfolio_values = portfolio * initial_cash
    benchmark_values = benchmark * initial_cash
    running_peak = np.maximum.accumulate(portfolio_values)
    drawdown_percent = (portfolio_values - running_peak) / running_peak * 100
    daily_returns = np.diff(portfolio, prepend=1.0)
    daily_returns[1:] = portfolio[1:] / portfolio[:-1] - 1.0

    hyperparameters = payload.get("hyperparameters", {})
    equity_curve = [
        {
            "date": date,
            "portfolio_value": round(float(value), 2),
            "benchmark_value": round(float(benchmark_value), 2),
            "running_peak": round(float(peak), 2),
            "drawdown_percent": round(float(drawdown), 4),
        }
        for date, value, benchmark_value, peak, drawdown in zip(
            dates,
            portfolio_values,
            benchmark_values,
            running_peak,
            drawdown_percent,
        )
    ]

    return {
        "strategy": payload.get("strategy", "My LSTM"),
        "description": (
            "Optimized LSTM: select the strongest positive forecasts, hold an "
            "equal-weight portfolio, and rebalance every ten trading days."
        ),
        "initial_cash_egp": initial_cash,
        "final_portfolio_value_egp": round(float(portfolio_values[-1]), 2),
        "benchmark_final_value_egp": round(float(benchmark_values[-1]), 2),
        "total_return_percent": round(float((portfolio[-1] - 1) * 100), 2),
        "benchmark_return_percent": round(float((benchmark[-1] - 1) * 100), 2),
        "max_drawdown_percent": round(abs(float(drawdown_percent.min())), 2),
        "max_drawdown_egp": round(float((running_peak - portfolio_values).max()), 2),
        "sharpe": round(float(sharpe(daily_returns)), 3),
        "commission_percent": round(float(payload.get("commission", 0)) * 100, 3),
        "top_k": int(hyperparameters.get("top_k", 8)),
        "threshold_percent": round(float(hyperparameters.get("threshold", 0)) * 100, 4),
        "rebalance_days": int(hyperparameters.get("rebalance_days", 10)),
        "validation_sharpe": round(float(hyperparameters.get("validation_sharpe", 0)), 3),
        "validation_return_percent": round(
            float(hyperparameters.get("validation_return", 0)) * 100, 2
        ),
        "start_date": dates[0],
        "end_date": dates[-1],
        "equity_curve": equity_curve,
    }

@app.get("/universe")
def get_universe():
    if not DATA_DIR.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Data directory not found: {DATA_DIR}",
        )

    assets = sorted(
        file.stem.upper()
        for file in DATA_DIR.glob("*.csv")
        if file.is_file()
    )

    return {
        "count": len(assets),
        "assets": assets,
    }

@app.get("/prices/SAUD")
def get_saud_prices():
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=f"CSV file not found: {DATA_FILE}",
        )

    df = pd.read_csv(DATA_FILE)

    return {
        "symbol": "SAUD",
        "file": str(DATA_FILE.relative_to(REPO_ROOT)),
        "rows": len(df),
        "columns": df.columns.tolist(),
        "preview": df.head(5).to_dict(orient="records"),
    }
@app.get("/indicators/{symbol}")
def get_indicators(symbol: str):
    symbol = symbol.upper()
    data_file = get_asset_file(symbol)
    if not data_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"CSV file not found: {data_file}",
        )

    df = pd.read_csv(data_file)

    # Prepare the historical data
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df.dropna(subset=["date", "close"])
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    # Calculate moving averages using historical values only
    df["ma9"] = df["close"].rolling(window=9).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()

    # Convert dates into JSON-friendly strings
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # Convert NaN moving-average values into null
    result = (
        df[["date", "close", "ma9", "ma20"]]
        .astype(object)
        .where(pd.notna(df[["date", "close", "ma9", "ma20"]]), None)
        .to_dict(orient="records")
    )

    return {
        "symbol": symbol,
        "rows": len(result),
        "start_date": result[0]["date"] if result else None,
        "end_date": result[-1]["date"] if result else None,
        "data": result,
    }

@app.get("/backtest/{symbol}")
def backtest(symbol: str):
    symbol = symbol.upper()
    data_file = get_asset_file(symbol)
    if not data_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"CSV file not found: {data_file}",
        )

    df = pd.read_csv(data_file)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df.dropna(subset=["date", "close"])
        .drop_duplicates(subset=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )

    # Moving averages
    df["ma9"] = df["close"].rolling(window=9).mean()
    df["ma20"] = df["close"].rolling(window=20).mean()

    # Detect crossovers
    previous_ma9 = df["ma9"].shift(1)
    previous_ma20 = df["ma20"].shift(1)

    buy_condition = (
        (df["ma9"] > df["ma20"])
        & (previous_ma9 <= previous_ma20)
    )

    sell_condition = (
        (df["ma9"] < df["ma20"])
        & (previous_ma9 >= previous_ma20)
    )

    df["signal"] = 0
    df.loc[buy_condition, "signal"] = 1
    df.loc[sell_condition, "signal"] = -1

    initial_cash = 1000.0
    cash = initial_cash
    shares = 0.0

    pending_signal = 0
    pending_signal_date = None

    trades = []
    equity_curve = []

    for _, row in df.iterrows():
        date = row["date"]
        close = float(row["close"])

        # Execute the previous day's signal at today's close
        if pending_signal == 1 and shares == 0 and cash > 0:
            invested_amount = cash
            shares = cash / close
            cash = 0.0

            trades.append({
                "operation": "BUY",
                "signal_date": pending_signal_date,
                "execution_date": date.strftime("%Y-%m-%d"),
                "execution_price": round(close, 4),
                "shares": round(shares, 6),
                "amount_egp": round(invested_amount, 2),
            })

        elif pending_signal == -1 and shares > 0:
            sale_amount = shares * close

            trades.append({
                "operation": "SELL",
                "signal_date": pending_signal_date,
                "execution_date": date.strftime("%Y-%m-%d"),
                "execution_price": round(close, 4),
                "shares": round(shares, 6),
                "amount_egp": round(sale_amount, 2),
            })

            cash = sale_amount
            shares = 0.0

        portfolio_value = cash + shares * close

        equity_curve.append({
            "date": date.strftime("%Y-%m-%d"),
            "close": round(close, 4),
            "cash": round(cash, 2),
            "shares": round(shares, 6),
            "portfolio_value": round(portfolio_value, 2),
        })

        pending_signal = int(row["signal"])
        pending_signal_date = date.strftime("%Y-%m-%d")

    equity_df = pd.DataFrame(equity_curve)

    equity_df["running_peak"] = (
        equity_df["portfolio_value"].cummax()
    )

    equity_df["drawdown_egp"] = (
        equity_df["portfolio_value"]
        - equity_df["running_peak"]
    )

    equity_df["drawdown_percent"] = (
        equity_df["drawdown_egp"]
        / equity_df["running_peak"]
        * 100
    )

    final_value = float(equity_df["portfolio_value"].iloc[-1])
    max_drawdown_egp = abs(float(equity_df["drawdown_egp"].min()))
    max_drawdown_percent = abs(
        float(equity_df["drawdown_percent"].min())
    )

    buy_count = sum(
        trade["operation"] == "BUY" for trade in trades
    )
    sell_count = sum(
        trade["operation"] == "SELL" for trade in trades
    )

    return {
        "symbol": symbol,
        "initial_cash_egp": initial_cash,
        "final_portfolio_value_egp": round(final_value, 2),
        "total_return_percent": round(
            ((final_value / initial_cash) - 1) * 100,
            2,
        ),
        "max_drawdown_egp": round(max_drawdown_egp, 2),
        "max_drawdown_percent": round(max_drawdown_percent, 2),
        "buy_operations": buy_count,
        "sell_operations": sell_count,
        "total_operations": buy_count + sell_count,
        "open_position": shares > 0,
        "trades": trades,
        "equity_curve": equity_df.round(4).to_dict(
            orient="records"
        ),
    }


@app.get("/portfolio/mean-reversion")
def mean_reversion_portfolio():
    """Run the five-day loser strategy across the complete EGX universe."""
    initial_cash = 1000.0
    commission = 0.005
    lookback = 30
    signal_days = 5

    feed = DataFeed.from_dir(DATA_DIR)
    strategy = lambda observation: weekly_loser_weights(
        observation,
        lookback_days=signal_days,
    )

    result = run_backtest(
        PortfolioSimulator(feed, commission=commission),
        strategy,
        lookback=lookback,
    )
    result_no_cost = run_backtest(
        PortfolioSimulator(feed, commission=0.0),
        strategy,
        lookback=lookback,
    )

    portfolio = np.asarray(result["portfolio"], dtype=float) * initial_cash
    no_cost_portfolio = (
        np.asarray(result_no_cost["portfolio"], dtype=float) * initial_cash
    )
    benchmark = np.asarray(result["benchmark"], dtype=float) * initial_cash
    running_peak = np.maximum.accumulate(portfolio)
    drawdown_percent = (portfolio - running_peak) / running_peak * 100

    weights = np.asarray(result["weights"], dtype=float)
    weight_changes = np.diff(weights, axis=0, prepend=weights[:1])
    daily_turnover = np.abs(weight_changes).sum(axis=1) / 2
    trade_threshold = 1e-6
    total_trades = int((np.abs(weight_changes) > trade_threshold).sum())
    average_assets_held = float(
        (weights > trade_threshold).sum(axis=1).mean()
    )

    decision_day = feed.n_days - 2
    latest_observation = build_observation(feed, decision_day, lookback)
    recent_returns = latest_observation[:, -signal_days:, 0]
    five_day_returns = np.prod(1.0 + recent_returns, axis=1) - 1.0
    latest_weights = strategy(latest_observation)

    allocations = [
        {
            "symbol": symbol,
            "five_day_return_percent": round(float(period_return * 100), 4),
            "weight_percent": round(float(weight * 100), 4),
            "amount_egp": round(float(weight * initial_cash), 2),
        }
        for symbol, period_return, weight in zip(
            feed.symbols,
            five_day_returns,
            latest_weights,
        )
        if weight > trade_threshold
    ]
    allocations.sort(key=lambda row: row["weight_percent"], reverse=True)

    dates = [pd.Timestamp(date).strftime("%Y-%m-%d") for date in result["dates"]]
    equity_curve = [
        {
            "date": date,
            "portfolio_value": round(float(value), 2),
            "no_cost_value": round(float(no_cost_value), 2),
            "benchmark_value": round(float(benchmark_value), 2),
            "running_peak": round(float(peak), 2),
            "drawdown_percent": round(float(drawdown), 4),
        }
        for date, value, no_cost_value, benchmark_value, peak, drawdown in zip(
            dates,
            portfolio,
            no_cost_portfolio,
            benchmark,
            running_peak,
            drawdown_percent,
        )
    ]

    final_value = float(portfolio[-1])
    final_no_cost_value = float(no_cost_portfolio[-1])
    benchmark_final_value = float(benchmark[-1])
    portfolio_returns = np.asarray(result["portfolio_returns"], dtype=float)

    return {
        "strategy": "Five-day loser mean reversion",
        "description": (
            "Buy five-day losers in proportion to their decline; recent winners "
            "receive zero weight because the simulator is long-only."
        ),
        "universe_size": feed.n_assets,
        "signal_days": signal_days,
        "commission_percent": commission * 100,
        "initial_cash_egp": initial_cash,
        "final_portfolio_value_egp": round(final_value, 2),
        "no_cost_final_value_egp": round(final_no_cost_value, 2),
        "benchmark_final_value_egp": round(benchmark_final_value, 2),
        "commission_drag_egp": round(final_no_cost_value - final_value, 2),
        "total_return_percent": round(total_return(portfolio_returns) * 100, 2),
        "max_drawdown_egp": round(float(np.max(running_peak - portfolio)), 2),
        "max_drawdown_percent": round(max_drawdown(portfolio_returns) * 100, 2),
        "sharpe": round(sharpe(portfolio_returns), 3),
        "total_trades": total_trades,
        "average_assets_held": round(average_assets_held, 1),
        "average_daily_turnover_percent": round(float(daily_turnover.mean() * 100), 2),
        "latest_decision_date": pd.Timestamp(feed.dates[decision_day]).strftime(
            "%Y-%m-%d"
        ),
        "latest_allocations": allocations,
        "equity_curve": equity_curve,
    }
