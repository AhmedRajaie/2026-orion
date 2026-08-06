from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import pandas as pd
import numpy as np

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


@app.get("/data")
def data(symbol: str = DEFAULT_SYMBOL):
    df = load_symbol_data(symbol)

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

    final_value = portfolio_values[-1] if portfolio_values else initial_cash
    portfolio_series = pd.Series(portfolio_values)
    rolling_max = portfolio_series.cummax()
    drawdown = (portfolio_series - rolling_max) / rolling_max
    drawdown_pct = [float(x * 100) if not pd.isna(x) else 0.0 for x in drawdown.tolist()]

    returns = portfolio_series.pct_change().dropna()
    avg_return = float(returns.mean()) if not returns.empty else 0.0
    return_std = float(returns.std(ddof=0)) if not returns.empty else 0.0
    sharpe_ratio = float((avg_return / return_std) * np.sqrt(252)) if return_std > 0 else None

    dates = [str(row["date"]) if "date" in df.columns else str(index) for index, row in df.iterrows()]
    prices = [float(row["close"]) for _, row in df.iterrows()]
    sma_9 = [None if pd.isna(row["SMA9"]) else float(row["SMA9"]) for _, row in df.iterrows()]
    sma_20 = [None if pd.isna(row["SMA20"]) else float(row["SMA20"]) for _, row in df.iterrows()]

    insights = {
        "Symbol": symbol.upper(),
        "Initial Cash": initial_cash,
        "Final Portfolio Value": final_value,
        "Total Return (%)": float((final_value - initial_cash) / initial_cash * 100),
        "Max Drawdown (%)": float(min(drawdown_pct)) if drawdown_pct else 0.0,
        "Sharpe Ratio": round(sharpe_ratio, 4) if sharpe_ratio is not None else None,
        "Buy Signals": buy_count,
        "Sell Signals": sell_count,
    }

    metrics = {
        "total_return_pct": insights["Total Return (%)"],
        "final_portfolio_value": insights["Final Portfolio Value"],
        "max_drawdown_pct": insights["Max Drawdown (%)"],
        "sharpe_ratio": sharpe_ratio,
    }

    return {
        "symbol": symbol.upper(),
        "dates": dates,
        "prices": prices,
        "sma_9": sma_9,
        "sma_20": sma_20,
        "portfolio_value": [float(x) for x in portfolio_values],
        "drawdown": drawdown_pct,
        "insights": insights,
        "metrics": metrics,
    }
