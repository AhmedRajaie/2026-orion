"""Strategy helpers for the EGX dashboard backend."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.tradinglab.data_feed import DataFeed
from src.tradinglab import metrics
from src.tradinglab.indicators import sma
from src.tradinglab.backtester import run_backtest
from src.tradinglab.simulator import PortfolioSimulator


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "egx"
DASHBOARD_DATA_DIR = ROOT_DIR / "dashboard" / "data"
TIKTOK_SCRIPT = ROOT_DIR / "week1" / "06-tiktok-strategy" / "tiktok_strategy.py"
REFERENCE_NOTEBOOK_DIR = ROOT_DIR / "week2" / "03-form-prediction-to-portfolio"


def load_json_artifact(filename: str) -> dict[str, Any] | None:
    """Load a pre-computed JSON artifact a notebook saved under dashboard/data/
    (e.g. the best-strategy export). Returns None rather than raising so the
    dashboard still works before that notebook has been run."""
    path = DASHBOARD_DATA_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def sharpe_from_portfolio_values(values: list[float] | np.ndarray) -> float:
    """Sharpe ratio of a daily portfolio-value curve, reusing tradinglab.metrics.sharpe
    (ma_crossover / weekly_mean_reversion track EGP value, not returns directly)."""
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return 0.0
    daily_returns = values[1:] / values[:-1] - 1.0
    return float(metrics.sharpe(daily_returns))


def _load_tiktok_module():
    """Load week1/06-tiktok-strategy/tiktok_strategy.py as a module by path --
    it's a standalone script (not part of the tradinglab package), so we import
    it directly rather than duplicating its strategy logic here."""
    spec = importlib.util.spec_from_file_location("tiktok_strategy", TIKTOK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_tiktok_strategy_backtest(
    initial_cash: float = 1000.0, data_dir: str | Path | None = None
) -> dict[str, Any]:
    """Run week1's TikTok Guru strategy through the project's standard
    walk-forward backtester (full EGX universe), reusing the existing
    make_tiktok_guru_strategy implementation rather than rewriting it."""
    tiktok = _load_tiktok_module()
    feed = DataFeed.from_dir(data_dir or DATA_DIR)
    sim = PortfolioSimulator(feed, benchmark="equal_weight", commission=tiktok.COMMISSION)
    result = run_backtest(sim, tiktok.make_tiktok_guru_strategy(week_days=5), lookback=30)

    port = result["portfolio"] * initial_cash
    bench = result["benchmark"] * initial_cash
    r = result["portfolio_returns"]
    peak = np.maximum.accumulate(port)
    dd_pct = np.divide(peak - port, peak, out=np.zeros_like(port), where=peak > 0)

    return {
        "label": "TikTok Guru Strategy",
        "initial_cash": float(initial_cash),
        "final_value": float(port[-1]),
        "benchmark_final_value": float(bench[-1]),
        "profit_loss": float(port[-1] - initial_cash),
        "return_percent": float(100 * (port[-1] / initial_cash - 1)),
        "max_drawdown_percent": float(dd_pct.max() * 100),
        "sharpe": float(metrics.sharpe(r)),
        "dates": [d.strftime("%Y-%m-%d") for d in result["dates"]],
        "portfolio_values": port.tolist(),
        "benchmark_values": bench.tolist(),
    }


def _notebook_stream_text(nb_path: Path) -> str:
    """Concatenate every stdout stream a notebook already printed when it was
    last executed. We read the ALREADY-COMPUTED outputs rather than re-running
    someone else's notebook."""
    with open(nb_path) as f:
        nb = json.load(f)
    chunks: list[str] = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        for out in cell.get("outputs", []):
            if out.get("output_type") == "stream":
                chunks.append("".join(out.get("text", [])))
    return "\n".join(chunks)


def _parse_report_block(text: str) -> dict[str, float] | None:
    """Parse the standard tradinglab.report.report() print block:
    'total return : +X% / sharpe : X / max drawdown : X% / final value : X (benchmark X)'.
    Returns None if that block isn't present in the given text."""
    ret = re.search(r"total return\s*:\s*([+-]?[\d.]+)%", text)
    sharpe = re.search(r"sharpe\s*:\s*([+-]?[\d.]+)", text)
    dd = re.search(r"max drawdown\s*:\s*([\d.]+)%", text)
    final = re.search(r"final value\s*:\s*([\d,.]+)\s*\(benchmark\s*([\d,.]+)\)", text)
    if not (ret and sharpe and dd and final):
        return None
    return {
        "return_percent": float(ret.group(1)),
        "sharpe": float(sharpe.group(1)),
        "max_drawdown_percent": float(dd.group(1)),
        "final_value": float(final.group(1).replace(",", "")),
        "benchmark_value": float(final.group(2).replace(",", "")),
    }


def load_reference_notebook_results() -> dict[str, Any] | None:
    """Read the real, already-executed results out of the reference notebooks in
    week2/03-form-prediction-to-portfolio/ (mlp.ipynb, lstm.ipynb, pivot.ipynb).
    These already contain printed output from a real run -- we parse that
    existing text rather than hardcoding numbers or re-running someone else's
    notebook. Returns None if the notebooks aren't present."""
    if not REFERENCE_NOTEBOOK_DIR.exists():
        return None

    mlp_path = REFERENCE_NOTEBOOK_DIR / "mlp.ipynb"
    lstm_path = REFERENCE_NOTEBOOK_DIR / "lstm.ipynb"
    pivot_path = REFERENCE_NOTEBOOK_DIR / "pivot.ipynb"
    if not (mlp_path.exists() and lstm_path.exists() and pivot_path.exists()):
        return None

    mlp_text = _notebook_stream_text(mlp_path)
    lstm_text = _notebook_stream_text(lstm_path)
    pivot_text = _notebook_stream_text(pivot_path)

    seed_rows = []
    for m in re.finditer(
        r"^\s*(\d+)\s+([+-][\d.]+)\s+([\d,]+)\s+([\d,]+)\s+(YES|no)",
        pivot_text,
        re.MULTILINE,
    ):
        seed_rows.append(
            {
                "seed": int(m.group(1)),
                "ic": float(m.group(2)),
                "strategy_value": float(m.group(3).replace(",", "")),
                "benchmark_value": float(m.group(4).replace(",", "")),
                "beat_benchmark": m.group(5) == "YES",
            }
        )

    return {
        "source": "week2/03-form-prediction-to-portfolio (mlp.ipynb, lstm.ipynb, pivot.ipynb)",
        "mlp": _parse_report_block(mlp_text),
        "lstm": _parse_report_block(lstm_text),
        "pivot_single_run": _parse_report_block(pivot_text),
        "pivot_seed_table": seed_rows,
    }


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
        "fast_window": int(fast_window),
        "slow_window": int(slow_window),
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


def run_weekly_mean_reversion_backtest(
    initial_cash: float,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the notebook-style weekly mean reversion strategy on the full universe."""
    folder = Path(data_dir or DATA_DIR)
    feed = DataFeed.from_dir(folder)

    prices = feed.close.astype(float)
    dates = feed.dates
    symbols = feed.symbols
    n_days = feed.n_days

    week_codes = pd.Series(dates).dt.to_period("W-FRI")
    week_end_mask = week_codes != week_codes.shift(-1)
    week_end_indices = np.flatnonzero(week_end_mask)
    if len(week_end_indices) < 2:
        raise ValueError("Not enough weekly data to run the weekly mean reversion strategy")

    weekly_close = prices[week_end_indices]
    weekly_change = weekly_close[1:] / weekly_close[:-1] - 1.0
    decision_indices = week_end_indices[1:]
    decision_map = {idx: i for i, idx in enumerate(decision_indices)}

    current_cash = float(initial_cash)
    current_shares = np.zeros(feed.n_assets, dtype=float)
    transaction_records: list[dict[str, Any]] = []

    daily_cash = np.zeros(n_days, dtype=float)
    daily_holdings_value = np.zeros(n_days, dtype=float)
    daily_total_value = np.zeros(n_days, dtype=float)

    for t in range(n_days):
        today_prices = prices[t]
        if t in decision_map:
            change = weekly_change[decision_map[t]]

            for asset_idx, pct in enumerate(change):
                if pct >= 0.10:
                    price = today_prices[asset_idx]
                    if price <= 0 or current_shares[asset_idx] <= 0:
                        continue

                    sell_value = min(10.0, current_shares[asset_idx] * price)
                    if sell_value <= 0:
                        continue

                    shares_sold = sell_value / price
                    current_shares[asset_idx] -= shares_sold
                    current_cash += sell_value
                    transaction_records.append(
                        {
                            "date": dates[t].strftime("%Y-%m-%d"),
                            "asset": symbols[asset_idx],
                            "action": "SELL",
                            "price": float(price),
                            "amount_egp": float(sell_value),
                            "shares": float(shares_sold),
                            "cash_after": float(current_cash),
                            "position_after": float(current_shares[asset_idx]),
                            "signal": f"weekly change {pct:.2%} >= 10%",
                        }
                    )

            for asset_idx, pct in enumerate(change):
                if pct <= -0.015 and current_cash >= 5.0:
                    price = today_prices[asset_idx]
                    if price <= 0:
                        continue

                    shares_bought = 5.0 / price
                    current_shares[asset_idx] += shares_bought
                    current_cash -= 5.0
                    transaction_records.append(
                        {
                            "date": dates[t].strftime("%Y-%m-%d"),
                            "asset": symbols[asset_idx],
                            "action": "BUY",
                            "price": float(price),
                            "amount_egp": 5.0,
                            "shares": float(shares_bought),
                            "cash_after": float(current_cash),
                            "position_after": float(current_shares[asset_idx]),
                            "signal": f"weekly change {pct:.2%} <= -1.5%",
                        }
                    )

        daily_cash[t] = current_cash
        daily_holdings_value[t] = float(np.dot(current_shares, today_prices))
        daily_total_value[t] = float(current_cash + daily_holdings_value[t])

    portfolio_returns = np.zeros(n_days, dtype=float)
    if n_days > 1:
        portfolio_returns[1:] = daily_total_value[1:] / daily_total_value[:-1] - 1.0

    cumulative_curve = daily_total_value / float(initial_cash)
    peak_curve = np.maximum.accumulate(cumulative_curve)
    drawdown_pct = (peak_curve - cumulative_curve) / np.where(peak_curve == 0, 1.0, peak_curve)

    final_value = float(daily_total_value[-1])
    profit_loss = float(final_value - initial_cash)
    return_value = float(profit_loss / initial_cash * 100.0) if initial_cash else 0.0
    max_drawdown_egp = float(np.max((peak_curve - cumulative_curve) * float(initial_cash)))
    max_drawdown_percent = float(np.max(drawdown_pct) * 100.0)
    buy_count = int(sum(1 for tx in transaction_records if tx["action"] == "BUY"))
    sell_count = int(sum(1 for tx in transaction_records if tx["action"] == "SELL"))

    return {
        "initial_cash": float(initial_cash),
        "final_value": final_value,
        "profit_loss": profit_loss,
        "return_percent": return_value,
        "max_drawdown_egp": max_drawdown_egp,
        "max_drawdown_percent": max_drawdown_percent,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "total_operations": buy_count + sell_count,
        "trade_count": len(transaction_records),
        "dates": [stamp.strftime("%Y-%m-%d") for stamp in dates],
        "portfolio_values": [float(value) for value in daily_total_value],
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
