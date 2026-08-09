from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
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
DEFAULT_SYMBOL = "ADIB"


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
