"""FastAPI backend for the dashboard.

Run:
uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""

from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Younit-style trading dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = REPO_ROOT / "data" / "egx" / "SAUD.csv"
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
DATA_DIR = REPO_ROOT / "data" / "egx"


@app.get("/health")
def health():
    return {"status": "ok"}

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