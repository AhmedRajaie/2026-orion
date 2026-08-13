"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
"""FastAPI backend for the dashboard"""

from pathlib import Path
import math
import os
from typing import Any

import numpy as np
import pandas as pd

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
import torch.nn as nn

app = FastAPI(title="EGX Trading Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).parents[2] / "data" / "egx"
MODEL_START_DATE = pd.Timestamp("2022-01-01")


class ChatRequest(BaseModel):
    message: str
    symbol: str | None = None


class DashboardLSTM(nn.Module):
    def __init__(self, hidden_size=32):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden_size, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, values):
        output, _ = self.lstm(values)
        return self.head(output[:, -1, :]).squeeze(-1)


def model_equity(symbol: str):
    """Return the notebook-style model curves for one stock from 2022."""
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    frame = pd.read_csv(DATA_DIR / f"{symbol}.csv", parse_dates=["date"])
    frame = frame.sort_values("date").set_index("date")
    close = frame["close"].astype(float)
    returns = close.pct_change()
    data = pd.DataFrame({f"lag_{lag}": returns.shift(lag) for lag in range(1, 6)})
    data["target"] = returns
    data = data.dropna()

    dates = data.index[data.index >= MODEL_START_DATE]
    if len(dates) < 30:
        return {"error": "Not enough data from 2022 for this stock"}

    split = data.index.searchsorted(MODEL_START_DATE)
    train = data.iloc[:split]
    display_data = data.loc[dates]
    scaler = StandardScaler().fit(train.iloc[:, :5])
    X_train = scaler.transform(train.iloc[:, :5]).astype("float32")
    y_train = train["target"].to_numpy(dtype="float32")
    X_display = scaler.transform(display_data.iloc[:, :5]).astype("float32")

    mlp = MLPRegressor(
        hidden_layer_sizes=(32,), random_state=42, shuffle=False,
        max_iter=150, early_stopping=False
    )
    mlp.fit(X_train, y_train)
    mlp_predictions = mlp.predict(X_display)

    torch.manual_seed(42)
    lstm = DashboardLSTM(hidden_size=32)
    optimizer = torch.optim.Adam(lstm.parameters(), lr=0.001)
    loss_fn = nn.MSELoss()
    X_train_seq = torch.tensor(X_train.reshape(-1, 5, 1))
    y_train_tensor = torch.tensor(y_train)
    for _ in range(100):
        optimizer.zero_grad()
        loss = loss_fn(lstm(X_train_seq), y_train_tensor)
        loss.backward()
        optimizer.step()

    with torch.no_grad():
        lstm_predictions = lstm(torch.tensor(X_display.reshape(-1, 5, 1))).numpy()

    actual_returns = display_data["target"].to_numpy(dtype=float)
    sma_fast = close.rolling(9).mean()
    sma_slow = close.rolling(20).mean()
    sma_returns = actual_returns * (
        sma_fast.loc[dates].to_numpy() > sma_slow.loc[dates].to_numpy()
    )

    def curve(values):
        return (1000 * np.cumprod(1 + np.nan_to_num(values))).round(2).tolist()

    stock_returns = display_data["target"].to_numpy(dtype=float)

    return {
        "dates": [date.strftime("%Y-%m-%d") for date in dates],
        "sma": curve(sma_returns),
        "lstm": curve(np.where(lstm_predictions > 0, actual_returns, 0)),
        "mlp": curve(np.where(mlp_predictions > 0, actual_returns, 0)),
        "benchmark": curve(actual_returns),
        "stock": curve(stock_returns),
    }


def _symbol_frame(symbol: str) -> pd.DataFrame | None:
    file = DATA_DIR / f"{symbol.upper()}.csv"
    if not file.exists():
        return None
    df = pd.read_csv(file, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    if "close" not in df.columns:
        return None
    return df


def _chat_market_snapshot(symbol: str) -> dict[str, Any] | None:
    df = _symbol_frame(symbol)
    if df is None:
        return None

    close = df["close"].astype(float)
    ma9 = close.rolling(9).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close
    daily_return = (last_close / prev_close - 1.0) * 100.0
    avg_volume = float(df["volume"].mean())
    last_volume = float(df["volume"].iloc[-1])
    volume_ratio = (last_volume / avg_volume) if avg_volume else 1.0
    trend = "uptrend" if ma9 > ma20 else "downtrend"
    price_change = ((last_close - prev_close) / prev_close) * 100.0
    return {
        "symbol": symbol.upper(),
        "last_close": round(last_close, 2),
        "daily_return": round(daily_return, 2),
        "price_change": round(price_change, 2),
        "ma9": round(float(ma9), 2),
        "ma20": round(float(ma20), 2),
        "trend": trend,
        "volume_ratio": round(volume_ratio, 2),
    }


def _agent_debate(symbol: str, user_message: str) -> dict[str, Any]:
    snapshot = _chat_market_snapshot(symbol)
    if snapshot is None:
        return {"error": "Unknown Symbol"}

    direction = "bullish" if "buy" in user_message.lower() or "long" in user_message.lower() else "bearish" if "sell" in user_message.lower() or "short" in user_message.lower() else "neutral"
    sentiment_score = 0.0
    if snapshot["trend"] == "uptrend":
        sentiment_score += 1.2
    if snapshot["daily_return"] > 0:
        sentiment_score += 1.0
    if snapshot["volume_ratio"] > 1.1:
        sentiment_score += 0.7
    if snapshot["daily_return"] < 0:
        sentiment_score -= 1.0
    if snapshot["trend"] == "downtrend":
        sentiment_score -= 1.2

    bullish = {
        "name": "Bullish Agent",
        "stance": "Long bias",
        "points": [
            f"Price is {snapshot['last_close']:.2f} and moving average 9-day is above 20-day ({snapshot['ma9']:.2f} > {snapshot['ma20']:.2f}).",
            f"Daily move is {snapshot['daily_return']:.2f}% with volume ratio {snapshot['volume_ratio']:.2f}, which supports momentum.",
            "The prompt is aligned with a continuation setup unless a major resistance is broken."
        ],
        "score": max(0.0, round(50 + sentiment_score * 10, 1))
    }

    bearish = {
        "name": "Bearish Agent",
        "stance": "Risk-off bias",
        "points": [
            f"The move is only {snapshot['daily_return']:.2f}% and could fade if momentum slows below the recent trend.",
            f"A lower volume environment or reversal at resistance would weaken the bullish setup.",
            "The current setup still needs confirmation before taking aggressive long exposure."
        ],
        "score": max(0.0, round(50 - sentiment_score * 9, 1))
    }

    risk = {
        "name": "Risk Analyst",
        "stance": "Balanced bias",
        "points": [
            f"The stock has a {snapshot['trend']} structure, so the signal is conditional on confirmation.",
            "We should size the position carefully and watch for a break either above or below the moving-average zone.",
            "This is a good candidate for a measured trade rather than large conviction."
        ],
        "score": round(50 + (0.5 if snapshot['trend'] == 'uptrend' else -0.5) * 10, 1)
    }

    if direction == "bullish":
        final_signal = "BUY" if sentiment_score >= 0 else "WATCH"
    elif direction == "bearish":
        final_signal = "SELL" if sentiment_score <= 0 else "WATCH"
    else:
        final_signal = "BUY" if sentiment_score > 0 else "SELL" if sentiment_score < 0 else "WATCH"

    final_summary_lines = [
        f"{snapshot['symbol']} is currently trading at {snapshot['last_close']:.2f} EGP.",
        f"The short-term trend is {snapshot['trend']} with a daily return of {snapshot['daily_return']:.2f}%.",
        f"The multi-agent view leans {final_signal.lower()} with risk management and confirmation before entering a position."
    ]

    return {
        "symbol": snapshot["symbol"],
        "signal": final_signal,
        "reply": "\n".join(final_summary_lines),
        "summary": final_summary_lines[2],
        "agents": [bullish, bearish, risk],
        "sentiment": "Positive" if sentiment_score > 0 else "Negative" if sentiment_score < 0 else "Neutral",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(message: ChatRequest):
    symbol = (message.symbol or "EGAL").upper()
    if not symbol:
        symbol = "EGAL"

    analysis = _agent_debate(symbol, message.message)
    if "error" in analysis:
        return {"error": analysis["error"]}

    agent_summary = "\n".join(
        [
            f"{agent['name']} ({agent['stance']}): {', '.join(agent['points'])}"
            for agent in analysis["agents"]
        ]
    )

    return {
        "symbol": analysis["symbol"],
        "signal": analysis["signal"],
        "reply": analysis["reply"],
        "summary": analysis["summary"],
        "sentiment": analysis["sentiment"],
        "agents": analysis["agents"],
        "full_response": agent_summary,
    }


@app.get("/model-comparison/{symbol}")
def model_comparison(symbol: str):
    symbol = symbol.upper()
    file = DATA_DIR / f"{symbol}.csv"
    if not file.exists():
        return {"error": "Unknown Symbol"}
    return model_equity(symbol)


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


@app.get("/weekly-strategy")
def weekly_strategy(symbols: list[str] | None = Query(default=None)):
    """Run the notebook's weekly buy/sell strategy for selected symbols."""
    available = sorted(f.stem for f in DATA_DIR.glob("*.csv"))
    selected = available if not symbols else [s.upper() for s in symbols if s.upper() in available]
    if not selected:
        return {"error": "No valid symbols selected"}

    frames = {}
    for symbol in selected:
        frame = pd.read_csv(DATA_DIR / f"{symbol}.csv", parse_dates=["date"])
        frames[symbol] = frame.set_index("date").sort_index()["close"]

    prices = pd.DataFrame(frames).sort_index().ffill().dropna()
    weekly_prices = prices.resample("W-FRI").last().ffill()
    weekly_returns = weekly_prices.pct_change()

    buy_drop = -0.05
    sell_gain = 0.10
    buy_amount = 5.0
    sell_amount = 10.0
    initial_cash = 10000.0
    cash = initial_cash
    positions = pd.Series(0.0, index=selected)
    portfolio_values = []
    weights_history = []
    buy_count = 0
    sell_count = 0

    for index, date in enumerate(weekly_prices.index):
        week_price = weekly_prices.loc[date]
        if index > 0:
            week_return = weekly_returns.loc[date]
            for symbol in selected:
                if week_return[symbol] <= buy_drop:
                    positions[symbol] += buy_amount / week_price[symbol]
                    cash -= buy_amount
                    buy_count += 1
            for symbol in selected:
                if week_return[symbol] >= sell_gain:
                    quantity = min(sell_amount / week_price[symbol], positions[symbol])
                    positions[symbol] -= quantity
                    cash += quantity * week_price[symbol]
                    if quantity > 0:
                        sell_count += 1

        holdings = positions * week_price
        value = cash + holdings.sum()
        portfolio_values.append(value)
        weights_history.append((holdings / value if value > 0 else holdings * 0).tolist())

    portfolio = np.asarray(portfolio_values, dtype=float)
    portfolio_returns = np.zeros_like(portfolio)
    portfolio_returns[1:] = portfolio[1:] / portfolio[:-1] - 1.0
    benchmark_returns = weekly_returns.reindex(weekly_prices.index).mean(axis=1).fillna(0.0).to_numpy()
    benchmark = np.cumprod(1.0 + benchmark_returns) * initial_cash
    peak = np.maximum.accumulate(portfolio)
    drawdown = (peak - portfolio) / peak

    daily_returns = prices.pct_change().fillna(0.0)
    sma_fast = prices.rolling(9).mean()
    sma_slow = prices.rolling(20).mean()
    sma_portfolio = np.ones(len(prices), dtype=float) * initial_cash
    for index in range(len(prices) - 1):
        if index < 19:
            weights = np.zeros(len(selected))
        else:
            hold = (sma_fast.iloc[index] > sma_slow.iloc[index]).to_numpy(dtype=float)
            weights = hold / hold.sum() if hold.sum() else np.zeros(len(selected))
        next_returns = daily_returns.iloc[index + 1].to_numpy()
        sma_portfolio[index + 1] = sma_portfolio[index] * (1.0 + float(np.dot(weights, next_returns)))
    sma_peak = np.maximum.accumulate(sma_portfolio)
    sma_drawdown = (sma_peak - sma_portfolio) / sma_peak

    egx30_curve = None
    egx30_daily_curve = None
    egx30_path = DATA_DIR.parent / "egx30.csv"
    if egx30_path.exists():
        egx30 = pd.read_csv(egx30_path)
        egx30["date"] = pd.to_datetime(egx30["Date"], format="%m/%d/%Y")
        egx30["price"] = egx30["Price"].str.replace(",", "", regex=False).astype(float)
        egx30_prices = egx30.set_index("date")["price"].sort_index()
        egx30_aligned = egx30_prices.reindex(weekly_prices.index).ffill().bfill()
        if not egx30_aligned.isna().any():
            egx30_returns = egx30_aligned.pct_change().fillna(0.0).to_numpy()
            egx30_curve = np.cumprod(1.0 + egx30_returns) * initial_cash
        egx30_daily_aligned = egx30_prices.reindex(prices.index).ffill().bfill()
        if not egx30_daily_aligned.isna().any():
            egx30_daily_returns = egx30_daily_aligned.pct_change().fillna(0.0).to_numpy()
            egx30_daily_curve = np.cumprod(1.0 + egx30_daily_returns) * initial_cash

    return {
        "symbols": selected,
        "dates": [date.strftime("%Y-%m-%d") for date in weekly_prices.index],
        "prices": {symbol: weekly_prices[symbol].round(6).tolist() for symbol in selected},
        "portfolio": portfolio.round(6).tolist(),
        "benchmark": benchmark.round(6).tolist(),
        "sma_portfolio": sma_portfolio.round(6).tolist(),
        "sma_drawdown": sma_drawdown.round(6).tolist(),
        "sma_dates": [date.strftime("%Y-%m-%d") for date in prices.index],
        "sma_benchmark": (np.cumprod(1.0 + daily_returns.mean(axis=1).to_numpy()) * initial_cash).round(6).tolist(),
        "sma_egx30": None if egx30_daily_curve is None else egx30_daily_curve.round(6).tolist(),
        "egx30": None if egx30_curve is None else egx30_curve.round(6).tolist(),
        "drawdown": drawdown.round(6).tolist(),
        "weights": weights_history,
        "buy": buy_count,
        "sell": sell_count,
        "final_value": round(float(portfolio[-1]), 2),
        "total_return": round(float(portfolio[-1] / initial_cash - 1.0), 6),
        "max_drawdown": round(float(drawdown.max()), 6),
        "sma_return": round(float(sma_portfolio[-1] / initial_cash - 1.0), 6),
        "sma_max_drawdown": round(float(sma_drawdown.max()), 6),
        "benchmark_return": round(float(benchmark[-1] / initial_cash - 1.0), 6),
        "egx30_return": None if egx30_curve is None else round(float(egx30_curve[-1] / initial_cash - 1.0), 6),
    }

# TASK_02+ : add /universe, /prices/{symbol}, /indicators, /backtest here.
