"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma

app = FastAPI(title="Younit-style trading dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

feed = DataFeed.from_dir("data/egx")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe():
    return feed.symbols


@app.get("/prices/{symbol}")
def prices(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")

    idx = feed.symbols.index(symbol)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": feed.close[:, idx].tolist(),
    }


@app.get("/indicators/{symbol}")
def indicators(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")

    idx = feed.symbols.index(symbol)
    close = feed.close[:, idx]

    sma9 = sma(close, 9)
    sma20 = sma(close, 20)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],

        "sma9": [
            None if value != value else float(value)
            for value in sma9
        ],

        "sma20": [
            None if value != value else float(value)
            for value in sma20
        ],
    }


# TASK_02+ : add /backtest here.