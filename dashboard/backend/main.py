"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}

# TASK_02+ : add /universe, /prices/{symbol}, /indicators, /backtest here.


"""
FastAPI backend for the dashboard.
"""

import sys
import os
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

while not os.path.isdir("src") and os.path.dirname(os.getcwd()) != os.getcwd():
    os.chdir("..")

sys.path.insert(0, "src")

from tradinglab.data_feed import DataFeed

app = FastAPI(title="Trading Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

feed = DataFeed.from_dir("data/egx")


def sma(prices, window):
    prices = np.asarray(prices, dtype=float)
    out = np.full_like(prices, np.nan)

    for i in range(window - 1, len(prices)):
        out[i] = prices[i-window+1:i+1].mean()

    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/backtest")
def backtest():

    stock = 0

    price = feed.close[:, stock]

    ma9 = sma(price, 9)
    ma20 = sma(price, 20)

    cash = 1000
    shares = 0

    portfolio = []

    buy_days = []
    sell_days = []

    buy_count = 0
    sell_count = 0

    for i in range(len(price)):

        if np.isnan(ma9[i]) or np.isnan(ma20[i]):
            portfolio.append(cash)
            continue

        if ma9[i] > ma20[i] and shares == 0:

            shares = cash / price[i]
            cash = 0

            buy_days.append(i)
            buy_count += 1

        elif ma9[i] < ma20[i] and shares > 0:

            cash = shares * price[i]
            shares = 0

            sell_days.append(i)
            sell_count += 1

        portfolio.append(cash + shares * price[i])

    if shares > 0:
        cash = shares * price[-1]

    portfolio = np.array(portfolio)

    running_max = np.maximum.accumulate(portfolio)

    drawdown = running_max - portfolio

    max_drawdown = drawdown.max()

    return {

        "symbol": feed.symbols[stock],

        "price": price.tolist(),

        "ma9": np.nan_to_num(ma9).tolist(),

        "ma20": np.nan_to_num(ma20).tolist(),

        "portfolio": round(float(cash), 2),

        "drawdown": round(float(max_drawdown), 2),

        "buy_count": buy_count,

        "sell_count": sell_count
    }