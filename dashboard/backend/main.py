from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from functools import lru_cache
import sys
import pandas as pd
import numpy as np


def _build_dates(df: pd.DataFrame):
    return [str(row["date"]) if "date" in df.columns else str(index) for index, row in df.iterrows()]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FOLDER = Path(__file__).resolve().parents[2] / "data" / "egx"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYMBOL = "ADIB"

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stocks")
def list_stocks():
    if not DATA_FOLDER.exists():
        raise HTTPException(status_code=500, detail="Data folder not found")

    symbols = [path.stem.upper() for path in sorted(DATA_FOLDER.glob("*.csv"))]
    return {"symbols": symbols}


def load_symbol_data(symbol: str):
    csv_path = DATA_FOLDER / f"{symbol.upper()}.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Symbol not found: {symbol}")

    df = pd.read_csv(csv_path)
    if "close" not in df.columns:
        raise HTTPException(status_code=500, detail="CSV missing required 'close' column")

    df["SMA9"] = df["close"].rolling(9).mean()
    df["SMA20"] = df["close"].rolling(20).mean()
    return df


def _summarize_series(portfolio_values, initial_cash=1000.0):
    portfolio_series = pd.Series(portfolio_values)
    rolling_max = portfolio_series.cummax()
    drawdown = (portfolio_series - rolling_max) / rolling_max
    drawdown_pct = [float(x * 100) if not pd.isna(x) else 0.0 for x in drawdown.tolist()]

    returns = portfolio_series.pct_change().dropna()
    avg_return = float(returns.mean()) if not returns.empty else 0.0
    return_std = float(returns.std(ddof=0)) if not returns.empty else 0.0
    sharpe_ratio = float((avg_return / return_std) * np.sqrt(252)) if return_std > 0 else None

    final_value = float(portfolio_series.iloc[-1]) if not portfolio_series.empty else float(initial_cash)
    return {
        "final_portfolio_value": final_value,
        "total_return_pct": float((final_value - initial_cash) / initial_cash * 100),
        "max_drawdown_pct": float(min(drawdown_pct)) if drawdown_pct else 0.0,
        "sharpe_ratio": sharpe_ratio,
        "drawdown": drawdown_pct,
        "portfolio_value": [float(x) for x in portfolio_values],
    }


def _simulate_sma(df: pd.DataFrame):
    initial_cash = 1000.0
    cash = initial_cash
    position = 0.0
    portfolio_values = []
    buy_count = 0
    sell_count = 0

    for _, row in df.iterrows():
        price = float(row["close"])
        sma9 = row["SMA9"]
        sma20 = row["SMA20"]

        if np.isnan(sma9) or np.isnan(sma20):
            portfolio_values.append(float(cash + position * price))
            continue

        if sma9 > sma20 and position == 0.0:
            position = cash / price
            cash = 0.0
            buy_count += 1
        elif sma9 < sma20 and position > 0.0:
            cash = position * price
            position = 0.0
            sell_count += 1

        portfolio_values.append(float(cash + position * price))

    metrics = _summarize_series(portfolio_values, initial_cash)
    metrics.update({"buy_signals": buy_count, "sell_signals": sell_count})
    return metrics


def _simulate_mean_reversion(df: pd.DataFrame):
    initial_cash = 1000.0
    cash = initial_cash
    position = 0.0
    portfolio_values = []
    buy_count = 0
    sell_count = 0

    rolling_mean = df["close"].rolling(20).mean().shift(1)
    for index, row in df.iterrows():
        price = float(row["close"])
        mean_value = float(rolling_mean.iloc[index]) if index < len(rolling_mean) else np.nan

        if np.isnan(mean_value):
            portfolio_values.append(float(cash + position * price))
            continue

        if price < mean_value and position == 0.0:
            position = cash / price
            cash = 0.0
            buy_count += 1
        elif price >= mean_value and position > 0.0:
            cash = position * price
            position = 0.0
            sell_count += 1

        portfolio_values.append(float(cash + position * price))

    metrics = _summarize_series(portfolio_values, initial_cash)
    metrics.update({"buy_signals": buy_count, "sell_signals": sell_count})
    return metrics


def _simulate_buy_and_hold(df: pd.DataFrame):
    initial_cash = 1000.0
    cash = initial_cash
    position = 0.0
    portfolio_values = []
    buy_count = 0

    for index, row in df.iterrows():
        price = float(row["close"])
        if index == 0 and position == 0.0:
            position = cash / price
            cash = 0.0
            buy_count += 1
        portfolio_values.append(float(cash + position * price))

    metrics = _summarize_series(portfolio_values, initial_cash)
    metrics.update({"buy_signals": buy_count, "sell_signals": 0})
    return metrics


@app.get("/data")
def data(symbol: str = DEFAULT_SYMBOL):
    df = load_symbol_data(symbol)

    sma_metrics = _simulate_sma(df)
    dates = _build_dates(df)
    prices = [float(row["close"]) for _, row in df.iterrows()]
    sma_9 = [None if pd.isna(row["SMA9"]) else float(row["SMA9"]) for _, row in df.iterrows()]
    sma_20 = [None if pd.isna(row["SMA20"]) else float(row["SMA20"]) for _, row in df.iterrows()]

    insights = {
        "Symbol": symbol.upper(),
        "Initial Cash": 1000.0,
        "Final Portfolio Value": sma_metrics["final_portfolio_value"],
        "Total Return (%)": sma_metrics["total_return_pct"],
        "Max Drawdown (%)": sma_metrics["max_drawdown_pct"],
        "Sharpe Ratio": round(sma_metrics["sharpe_ratio"], 4) if sma_metrics["sharpe_ratio"] is not None else None,
        "Buy Signals": sma_metrics["buy_signals"],
        "Sell Signals": sma_metrics["sell_signals"],
    }

    metrics = {
        "total_return_pct": insights["Total Return (%)"],
        "final_portfolio_value": insights["Final Portfolio Value"],
        "max_drawdown_pct": insights["Max Drawdown (%)"],
        "sharpe_ratio": sma_metrics["sharpe_ratio"],
    }

    return {
        "symbol": symbol.upper(),
        "dates": dates,
        "prices": prices,
        "sma_9": sma_9,
        "sma_20": sma_20,
        "portfolio_value": sma_metrics["portfolio_value"],
        "drawdown": sma_metrics["drawdown"],
        "insights": insights,
        "metrics": metrics,
    }


@app.get("/simulations")
def simulations(symbol: str = DEFAULT_SYMBOL):
    df = load_symbol_data(symbol)
    dates = _build_dates(df)

    simulation_specs = [
        ("sma_crossover", "SMA Crossover", "#38bdf8", _simulate_sma(df)),
        ("mean_reversion", "Mean Reversion", "#4ade80", _simulate_mean_reversion(df)),
        ("buy_and_hold", "Buy & Hold", "#fbbf24", _simulate_buy_and_hold(df)),
    ]

    payload = []
    for simulation_id, name, color, metrics in simulation_specs:
        payload.append(
            {
                "id": simulation_id,
                "name": name,
                "color": color,
                "portfolio_value": metrics["portfolio_value"],
                "drawdown": metrics["drawdown"],
                "metrics": {
                    "final_portfolio_value": metrics["final_portfolio_value"],
                    "total_return_pct": metrics["total_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "sharpe_ratio": metrics["sharpe_ratio"],
                },
            }
        )

    return {"symbol": symbol.upper(), "dates": dates, "simulations": payload}


@lru_cache(maxsize=1)
def _tiktok_06_backtest():
    """Run the real Week 1 / 06 strategy on the full EGX universe once."""
    from tradinglab.data_feed import DataFeed
    from tradinglab.simulator import PortfolioSimulator
    from tradinglab.backtester import run_backtest

    commission = 0.005
    week_days = 5
    sensitivity = 1.0
    state = {"weights": None, "day_count": 0}

    def strategy(observation):
        n_assets = observation.shape[0]
        current = state["weights"]
        if current is None or current.sum() == 0:
            current = np.ones(n_assets) / n_assets
            state["weights"] = current

        if state["day_count"] % week_days == 0:
            daily_returns = observation[:, -week_days:, 0]
            weekly_return = np.prod(1 + daily_returns, axis=1) - 1
            next_weights = np.clip(current * (1 - weekly_return * sensitivity), 0, None)
            total = next_weights.sum()
            current = np.zeros(n_assets) if total <= 0 else next_weights / total
            state["weights"] = current

        state["day_count"] += 1
        return state["weights"]

    feed = DataFeed.from_dir(DATA_FOLDER)
    tiktok = run_backtest(
        PortfolioSimulator(feed, benchmark="equal_weight", commission=commission),
        strategy,
        lookback=30,
    )
    egx30 = run_backtest(
        PortfolioSimulator(feed, benchmark="egx30", commission=commission),
        strategy=lambda observation: np.ones(observation.shape[0]) / observation.shape[0],
        lookback=30,
    )

    start_cash = 1000.0
    tiktok_values = tiktok["portfolio"] * start_cash
    equal_values = tiktok["benchmark"] * start_cash
    egx30_values = egx30["benchmark"] * start_cash
    metrics = _summarize_series(tiktok_values, start_cash)

    return {
        "name": "TikTok 06 Strategy",
        "dates": [str(date.date()) for date in tiktok["dates"]],
        "portfolio_value": [float(value) for value in tiktok_values],
        "equal_weight": [float(value) for value in equal_values],
        "egx30": [float(value) for value in egx30_values],
        "metrics": {
            "final_portfolio_value": metrics["final_portfolio_value"],
            "total_return_pct": metrics["total_return_pct"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "sharpe_ratio": metrics["sharpe_ratio"],
        },
    }


@app.get("/production/tiktok-06")
def production_tiktok_06():
    return _tiktok_06_backtest()
