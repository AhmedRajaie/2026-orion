"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
"""FastAPI backend for the dashboard"""

from pathlib import Path
import numpy as np
import pandas as pd

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="EGX Trading Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

DATA_DIR = Path(__file__).parents[2] / "data" / "egx"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe():

    return sorted([f.stem for f in DATA_DIR.glob("*.csv")])


@app.get("/prices/{symbol}")
def prices(symbol: str):

    file = DATA_DIR / f"{symbol}.csv"

    if not file.exists():
        return {"error": "Unknown Symbol"}

    df = pd.read_csv(file)

    return {

        "dates": df["date"].tolist(),

        "close": df["close"].tolist(),

        "high": df["high"].tolist(),

        "low": df["low"].tolist(),

        "volume": df["volume"].tolist()

    }


@app.get("/indicators/{symbol}")
def indicators(symbol: str):

    file = DATA_DIR / f"{symbol}.csv"

    if not file.exists():
        return {"error": "Unknown Symbol"}

    df = pd.read_csv(file)

    df["MA9"] = df["close"].rolling(9).mean()

    df["MA20"] = df["close"].rolling(20).mean()

    return {

        "dates": df["date"].tolist(),

        "ma9": df["MA9"].replace({np.nan: None}).tolist(),

        "ma20": df["MA20"].replace({np.nan: None}).tolist()

    }


@app.get("/backtest/{symbol}")
def backtest(symbol: str):

    file = DATA_DIR / f"{symbol}.csv"

    if not file.exists():
        return {"error": "Unknown Symbol"}

    df = pd.read_csv(file)

    df["MA9"] = df["close"].rolling(9).mean()
    df["MA20"] = df["close"].rolling(20).mean()

    cash = 1000
    shares = 0

    buy = 0
    sell = 0

    portfolio = []

    buy_points = []
    sell_points = []

    for i in range(len(df)):

        price = df.loc[i, "close"]

        ma9 = df.loc[i, "MA9"]
        ma20 = df.loc[i, "MA20"]

        if pd.isna(ma9) or pd.isna(ma20):
            portfolio.append(cash)
            buy_points.append(None)
            sell_points.append(None)
            continue

        if ma9 > ma20 and shares == 0:

            shares = cash / price
            cash = 0

            buy += 1

            buy_points.append(price)
            sell_points.append(None)

        elif ma9 < ma20 and shares > 0:

            cash = shares * price
            shares = 0

            sell += 1

            sell_points.append(price)
            buy_points.append(None)

        else:

            buy_points.append(None)
            sell_points.append(None)

        value = cash if shares == 0 else shares * price

        portfolio.append(value)

    if shares > 0:
       cash = shares * df.iloc[-1]["close"]
       shares = 0
       portfolio[-1] = cash

    final_value = portfolio[-1]

    peak = portfolio[0]

    max_drawdown = 0

    for value in portfolio:

        if value > peak:
            peak = value

        dd = (peak - value) / peak

        if dd > max_drawdown:
            max_drawdown = dd

    return {

        "portfolio": round(final_value,2),

        "drawdown": round(max_drawdown*100,2),

        "buy": buy,

        "sell": sell,

        "equity": portfolio,

        "buy_points": buy_points,

        "sell_points": sell_points

    }

# TASK_02+ : add /universe, /prices/{symbol}, /indicators, /backtest here.
