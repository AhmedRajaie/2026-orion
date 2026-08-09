"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
"""FastAPI backend for the dashboard"""

from pathlib import Path
import numpy as np
import pandas as pd

from fastapi import FastAPI, Query
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
