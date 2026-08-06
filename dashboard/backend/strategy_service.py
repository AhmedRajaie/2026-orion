"""Strategy helpers for the EGX dashboard backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.tradinglab.indicators import sma


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "egx"


def list_assets(data_dir: str | Path | None = None) -> list[str]:
    """Return the available EGX asset symbols from the data folder."""
    folder = Path(data_dir or DATA_DIR)
    if not folder.exists():
        raise FileNotFoundError("EGX data folder was not found")
    return sorted([path.stem for path in folder.glob("*.csv") if path.is_file()])


def load_asset_frame(symbol: str, data_dir: str | Path | None = None) -> pd.DataFrame:
    """Load a single asset CSV and keep the close price column."""
    folder = Path(data_dir or DATA_DIR)
    path = folder / f"{symbol}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No data found for symbol {symbol}")

    frame = pd.read_csv(path, parse_dates=["date"]).sort_values("date")
    if "close" not in frame.columns:
        raise ValueError(f"Asset {symbol} is missing a close column")

    frame = frame[["date", "close"]].copy()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["close"]).reset_index(drop=True)
    if len(frame) < 2:
        raise ValueError(f"Asset {symbol} does not contain enough data for a backtest")
    return frame


def run_ma_crossover_backtest(
    symbol: str,
    initial_cash: float,
    fast_window: int,
    slow_window: int,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a simple moving-average crossover backtest for one EGX symbol."""
    frame = load_asset_frame(symbol, data_dir=data_dir)
    prices = frame["close"].to_numpy(dtype=float)

    fast_ma = sma(prices, fast_window)
    slow_ma = sma(prices, slow_window)

    cash = float(initial_cash)
    shares = 0
    portfolio_values: list[float] = []
    drawdown_values: list[float] = []
    peak_value = cash
    trades: list[dict[str, Any]] = []
    buy_count = 0
    sell_count = 0

    for idx, (price, fast, slow) in enumerate(zip(prices, fast_ma, slow_ma)):
        if np.isnan(fast) or np.isnan(slow):
            portfolio_value = cash + shares * price
            portfolio_values.append(float(portfolio_value))
            drawdown_values.append(0.0)
            continue

        if shares == 0 and fast > slow and cash >= price:
            whole_shares = int(cash // price)
            if whole_shares > 0:
                cost = whole_shares * price
                cash -= cost
                shares = whole_shares
                buy_count += 1
                trades.append(
                    {
                        "date": frame.iloc[idx]["date"].strftime("%Y-%m-%d"),
                        "operation": "BUY",
                        "price": float(price),
                        "shares": int(whole_shares),
                        "portfolio_value": float(cash + shares * price),
                    }
                )
        elif shares > 0 and fast < slow:
            shares_to_sell = shares
            proceeds = shares_to_sell * price
            cash += proceeds
            shares = 0
            sell_count += 1
            trades.append(
                {
                    "date": frame.iloc[idx]["date"].strftime("%Y-%m-%d"),
                    "operation": "SELL",
                    "price": float(price),
                    "shares": int(shares_to_sell),
                    "portfolio_value": float(cash),
                }
            )

        portfolio_value = cash + shares * price
        portfolio_values.append(float(portfolio_value))
        if portfolio_value > peak_value:
            peak_value = portfolio_value
        drawdown_values.append(float(peak_value - portfolio_value))

    final_price = float(prices[-1])
    final_value = cash + shares * final_price
    max_drawdown_egp = float(max(drawdown_values)) if drawdown_values else 0.0
    max_drawdown_percent = float(max_drawdown_egp / peak_value * 100.0) if peak_value > 0 else 0.0
    profit_loss = float(final_value - initial_cash)
    return_value = float(profit_loss / initial_cash * 100.0) if initial_cash else 0.0

    return {
        "symbol": symbol,
        "initial_cash": float(initial_cash),
        "final_value": float(final_value),
        "profit_loss": profit_loss,
        "return_percent": return_value,
        "max_drawdown_egp": max_drawdown_egp,
        "max_drawdown_percent": max_drawdown_percent,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "total_operations": buy_count + sell_count,
        "open_position": bool(shares > 0),
        "remaining_cash": float(cash),
        "remaining_shares": int(shares),
        "dates": [stamp.strftime("%Y-%m-%d") for stamp in frame["date"]],
        "prices": [float(value) if not np.isnan(value) else None for value in prices],
        "fast_ma": [float(value) if not np.isnan(value) else None for value in fast_ma],
        "slow_ma": [float(value) if not np.isnan(value) else None for value in slow_ma],
        "portfolio_values": [float(value) for value in portfolio_values],
        "drawdown_values": [float(value) for value in drawdown_values],
        "trades": trades,
    }


def to_jsonable(value: Any) -> Any:
    """Convert numpy/scalar values to JSON-friendly Python values."""
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [to_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) or np.isinf(value) else float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value
