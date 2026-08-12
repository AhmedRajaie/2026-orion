"""FastAPI backend for the four-strategy dashboard.

Run:
    uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradinglab import metrics as trading_metrics
from tradinglab.data_feed import DataFeed
from tradinglab.day3 import BASELINE_FEATURES, build_dashboard_artifact, run_shared_model_portfolio
from tradinglab.indicators import sma
from tradinglab.observation import build_observation
from tradinglab.strategies.sma import sma_crossover_weights

app = FastAPI(title="Trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SMALL_UNIVERSE_SYMBOLS = ["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK"]
FEEDS = {
    "small": DataFeed.from_dir("data/egx", symbols=SMALL_UNIVERSE_SYMBOLS),
    "full": DataFeed.from_dir("data/egx"),
}

STRATEGY_ORDER = ("mlp", "lstm", "sma", "video")
STRATEGY_LABELS = {
    "mlp": "MLP Portfolio",
    "lstm": "LSTM Portfolio",
    "sma": "SMA Portfolio",
    "video": "Video Strategy",
}
STRATEGY_DESCRIPTIONS = {
    "mlp": (
        "Week 2 Day 3 best MLP portfolio. A shared MLP predicts next-day returns "
        "and equally weights the stocks with positive predictions."
    ),
    "lstm": (
        "Week 2 Day 3 strongest LSTM portfolio variant. A shared LSTM predicts "
        "next-day returns and equally weights the stocks with positive predictions."
    ),
    "sma": (
        "Week 1 multi-asset SMA crossover strategy. The portfolio equally weights "
        "the stocks whose fast average is above the slow average and otherwise holds cash."
    ),
    "video": (
        "The final Week 1 TikTok / video contrarian strategy. It sells before buying, "
        "uses a five-day return rule, and trades fixed EGP notionals with no shorting."
    ),
}
BENCHMARK_LABEL = "Equal-weight universe benchmark"

EPSILON = 1e-9
SHARE_TRADE_THRESHOLD = 1e-8
WEIGHT_SUM_TOLERANCE = 1e-6

SMA_FAST_WINDOW = 9
SMA_SLOW_WINDOW = 20
SMA_LOOKBACK = 30

VIDEO_LOOKBACK_DAYS = 5
VIDEO_BUY_THRESHOLD = -0.05
VIDEO_SELL_THRESHOLD = 0.10
VIDEO_BUY_NOTIONAL = 5.0
VIDEO_SELL_NOTIONAL = 10.0

MLP_LOOKBACK = 30
MLP_FEATURES = BASELINE_FEATURES + ("return_5d", "return_10d")
MLP_CONFIG = {
    "feature_names": MLP_FEATURES,
    "hidden": 64,
    "n_hidden_layers": 1,
    "epochs": 200,
    "lr": 1e-3,
    "seed": 0,
    "commission": 0.0,
    "benchmark": "equal_weight",
}

LSTM_LOOKBACK = 30
LSTM_CONFIG = {
    "feature_names": BASELINE_FEATURES,
    "hidden": 64,
    "seq_len": 10,
    "epochs": 200,
    "lr": 1e-3,
    "seed": 0,
    "commission": 0.0,
    "benchmark": "equal_weight",
}

BEST_NEURAL_ARTIFACT_PATH = Path("dashboard/data/best_neural_strategy.json")

TRADE_COLUMNS = [
    {"key": "date", "label": "Date"},
    {"key": "operation", "label": "Operation"},
    {"key": "symbol", "label": "Symbol"},
    {"key": "price", "label": "Price"},
    {"key": "shares", "label": "Shares / units"},
    {"key": "notional", "label": "Notional"},
    {"key": "portfolio_value_after", "label": "Portfolio value after"},
]


def get_feed_for_universe(universe: str) -> DataFeed:
    feed = FEEDS.get(universe)
    if feed is None:
        raise HTTPException(status_code=400, detail="universe must be 'small' or 'full'")
    return feed


def normalize_strategy_name(strategy: str) -> str:
    normalized = strategy.lower()
    if normalized not in STRATEGY_ORDER:
        raise HTTPException(status_code=400, detail="strategy must be one of: mlp, lstm, sma, video")
    return normalized


def get_symbol_or_404(feed: DataFeed, symbol: str | None) -> str:
    chosen = symbol or feed.symbols[0]
    if chosen not in feed.symbols:
        raise HTTPException(status_code=404, detail="Unknown symbol")
    return chosen


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def _format_date(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _parse_requested_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="start_date must be a valid YYYY-MM-DD date") from exc


def _strategy_earliest_start_day(feed: DataFeed, strategy: str) -> int:
    strategy = normalize_strategy_name(strategy)
    split_day = int(feed.n_days * 0.7)
    if strategy == "mlp":
        return max(split_day, MLP_LOOKBACK, 1)
    if strategy == "lstm":
        return max(split_day, LSTM_LOOKBACK, LSTM_CONFIG["seq_len"])
    if strategy == "sma":
        return SMA_LOOKBACK
    return VIDEO_LOOKBACK_DAYS + 1


def _common_earliest_start_day(feed: DataFeed) -> int:
    return max(_strategy_earliest_start_day(feed, strategy) for strategy in STRATEGY_ORDER)


def _latest_start_day(feed: DataFeed) -> int:
    return max(0, feed.n_days - 2)


def _error_detail(message: str, *, strategy: str, earliest_start_date: str, universe: str) -> dict[str, Any]:
    return {
        "message": message,
        "strategy": strategy,
        "earliest_start_date": earliest_start_date,
        "universe": universe,
    }


def _resolve_start_day(feed: DataFeed, strategy: str, universe: str, start_date: str | None) -> tuple[str, int, str]:
    earliest_start_day = _strategy_earliest_start_day(feed, strategy)
    default_requested = _format_date(feed.dates[_common_earliest_start_day(feed)])
    requested_value = start_date or default_requested
    requested_date = _parse_requested_date(requested_value)

    market_start = feed.dates[0].date()
    market_end = feed.dates[-1].date()
    if requested_date < market_start or requested_date > market_end:
        raise HTTPException(
            status_code=400,
            detail=f"start_date must fall within available market history: {market_start} to {market_end}",
        )

    actual_day = int(feed.dates.searchsorted(pd.Timestamp(requested_date)))
    if actual_day >= feed.n_days:
        raise HTTPException(
            status_code=400,
            detail=f"start_date is after the available market history end date {market_end}",
        )

    earliest_start_date = _format_date(feed.dates[earliest_start_day])
    if actual_day < earliest_start_day:
        label = STRATEGY_LABELS[strategy]
        raise HTTPException(
            status_code=400,
            detail=_error_detail(
                f"{label} is unavailable for {requested_value}. First valid start date is {earliest_start_date}.",
                strategy=strategy,
                earliest_start_date=earliest_start_date,
                universe=universe,
            ),
        )

    if actual_day > _latest_start_day(feed):
        latest_date = _format_date(feed.dates[_latest_start_day(feed)])
        raise HTTPException(
            status_code=400,
            detail=f"start_date must be on or before {latest_date} so at least one future market observation exists",
        )

    return requested_value, actual_day, _format_date(feed.dates[actual_day])


def _normalize_target_weights(weights: np.ndarray) -> np.ndarray:
    target = np.asarray(weights, dtype=float)
    target = np.nan_to_num(target, nan=0.0, posinf=0.0, neginf=0.0)
    target[target < 0] = 0.0
    total = float(target.sum())
    if total > 1.0 + WEIGHT_SUM_TOLERANCE:
        target = target / total
    return target


def _daily_returns_from_values(values: np.ndarray) -> np.ndarray:
    curve = np.asarray(values, dtype=float)
    if len(curve) < 2:
        return np.array([], dtype=float)
    prev = curve[:-1]
    curr = curve[1:]
    returns = np.zeros(len(curve) - 1, dtype=float)
    valid = np.isfinite(prev) & np.isfinite(curr) & (prev > 0)
    returns[valid] = curr[valid] / prev[valid] - 1.0
    return returns


def _drawdown_series_pct(values: np.ndarray) -> np.ndarray:
    curve = np.asarray(values, dtype=float)
    if len(curve) == 0:
        return np.array([], dtype=float)
    running_peak = np.maximum.accumulate(curve)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = (curve / running_peak - 1.0) * 100.0
    return np.nan_to_num(drawdown, nan=0.0, posinf=0.0, neginf=0.0)


def _max_drawdown_egp(values: np.ndarray) -> float:
    curve = np.asarray(values, dtype=float)
    if len(curve) == 0:
        return 0.0
    running_peak = np.maximum.accumulate(curve)
    return float(np.max(running_peak - curve))


def _build_equal_weight_benchmark(feed: DataFeed, start_day: int, initial_cash: float) -> np.ndarray:
    benchmark_returns = np.asarray(feed.returns.mean(axis=1), dtype=float)
    values = [float(initial_cash)]
    current = float(initial_cash)
    for day_index in range(start_day + 1, feed.n_days):
        current *= 1.0 + float(benchmark_returns[day_index])
        values.append(float(current))
    return np.asarray(values, dtype=float)


def _add_trade_rows(
    trades: list[dict[str, Any]],
    *,
    date_str: str,
    symbols: list[str],
    prices: np.ndarray,
    share_delta: np.ndarray,
    portfolio_value_after: float,
) -> tuple[int, int]:
    buy_operations = 0
    sell_operations = 0
    for asset_index, delta in enumerate(share_delta):
        price = float(prices[asset_index])
        if not np.isfinite(price) or price <= 0:
            continue
        if delta > SHARE_TRADE_THRESHOLD:
            buy_operations += 1
            trades.append(
                {
                    "date": date_str,
                    "operation": "BUY",
                    "symbol": symbols[asset_index],
                    "price": price,
                    "shares": float(delta),
                    "notional": float(delta * price),
                    "portfolio_value_after": float(portfolio_value_after),
                }
            )
        elif delta < -SHARE_TRADE_THRESHOLD:
            sell_operations += 1
            trades.append(
                {
                    "date": date_str,
                    "operation": "SELL",
                    "symbol": symbols[asset_index],
                    "price": price,
                    "shares": float(abs(delta)),
                    "notional": float(abs(delta) * price),
                    "portfolio_value_after": float(portfolio_value_after),
                }
            )
    return buy_operations, sell_operations


def _rebalance_fractional(
    holdings: np.ndarray,
    prices: np.ndarray,
    target_weights: np.ndarray,
    portfolio_value: float,
    *,
    date_str: str,
    symbols: list[str],
    trades: list[dict[str, Any]],
) -> tuple[np.ndarray, float, int, int]:
    target = _normalize_target_weights(target_weights)
    desired_shares = np.zeros_like(holdings, dtype=float)
    valid = np.isfinite(prices) & (prices > 0)
    desired_shares[valid] = portfolio_value * target[valid] / prices[valid]
    share_delta = desired_shares - holdings
    buy_operations, sell_operations = _add_trade_rows(
        trades,
        date_str=date_str,
        symbols=symbols,
        prices=prices,
        share_delta=share_delta,
        portfolio_value_after=portfolio_value,
    )
    new_holdings = desired_shares
    invested_value = float(np.dot(new_holdings[valid], prices[valid]))
    cash = float(max(portfolio_value - invested_value, 0.0))
    return new_holdings, cash, buy_operations, sell_operations


def _simulate_weight_strategy(
    feed: DataFeed,
    weights_by_day: np.ndarray,
    *,
    start_day: int,
    initial_cash: float,
) -> dict[str, Any]:
    weights = np.asarray(weights_by_day, dtype=float)
    if weights.shape != (feed.n_days, feed.n_assets):
        raise ValueError("weights_by_day must align with the feed shape")

    close = np.asarray(feed.close, dtype=float)
    holdings = np.zeros(feed.n_assets, dtype=float)
    cash = float(initial_cash)
    trades: list[dict[str, Any]] = []

    dates: list[str] = []
    portfolio_values: list[float] = []
    positions_history: list[int] = []
    invested_history: list[float] = []

    total_buy_operations = 0
    total_sell_operations = 0

    start_prices = close[start_day]
    start_date = _format_date(feed.dates[start_day])
    holdings, cash, buys, sells = _rebalance_fractional(
        holdings,
        start_prices,
        weights[start_day],
        float(initial_cash),
        date_str=start_date,
        symbols=list(feed.symbols),
        trades=trades,
    )
    total_buy_operations += buys
    total_sell_operations += sells

    dates.append(start_date)
    portfolio_values.append(float(initial_cash))
    invested_history.append(float(np.dot(holdings, start_prices)))
    positions_history.append(int(np.sum(holdings > SHARE_TRADE_THRESHOLD)))

    for day_index in range(start_day + 1, feed.n_days):
        today_prices = close[day_index]
        portfolio_value = float(cash + np.dot(holdings, today_prices))
        if day_index <= feed.n_days - 2:
            holdings, cash, buys, sells = _rebalance_fractional(
                holdings,
                today_prices,
                weights[day_index],
                portfolio_value,
                date_str=_format_date(feed.dates[day_index]),
                symbols=list(feed.symbols),
                trades=trades,
            )
            total_buy_operations += buys
            total_sell_operations += sells

        dates.append(_format_date(feed.dates[day_index]))
        portfolio_values.append(portfolio_value)
        invested_history.append(float(np.dot(holdings, today_prices)))
        positions_history.append(int(np.sum(holdings > SHARE_TRADE_THRESHOLD)))

    return {
        "dates": dates,
        "portfolio_values": np.asarray(portfolio_values, dtype=float),
        "positions_history": np.asarray(positions_history, dtype=int),
        "invested_history": np.asarray(invested_history, dtype=float),
        "trades": trades,
        "total_buy_operations": int(total_buy_operations),
        "total_sell_operations": int(total_sell_operations),
    }


def _build_common_response(
    *,
    strategy: str,
    universe: str,
    requested_start_date: str,
    actual_start_date: str,
    initial_cash: float,
    dates: list[str],
    portfolio_values: np.ndarray,
    benchmark_values: np.ndarray,
    positions_history: np.ndarray,
    invested_history: np.ndarray,
    trades: list[dict[str, Any]],
    parameters: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(dates) != len(portfolio_values):
        raise ValueError("dates and portfolio_values are misaligned")
    if len(benchmark_values) != len(portfolio_values):
        raise ValueError("benchmark_values and portfolio_values are misaligned")
    if len(positions_history) != len(portfolio_values):
        raise ValueError("positions_history and portfolio_values are misaligned")
    if len(invested_history) != len(portfolio_values):
        raise ValueError("invested_history and portfolio_values are misaligned")

    equity = np.asarray(portfolio_values, dtype=float) / float(initial_cash)
    benchmark_equity = np.asarray(benchmark_values, dtype=float) / float(initial_cash)
    drawdown = _drawdown_series_pct(portfolio_values)
    daily_returns = _daily_returns_from_values(portfolio_values)

    total_return_pct = (float(portfolio_values[-1]) / float(initial_cash) - 1.0) * 100.0
    benchmark_return_pct = (float(benchmark_values[-1]) / float(initial_cash) - 1.0) * 100.0
    buy_operations = sum(1 for trade in trades if trade["operation"] == "BUY")
    sell_operations = sum(1 for trade in trades if trade["operation"] == "SELL")
    open_positions = int(positions_history[-1]) if len(positions_history) else 0
    current_state = "Invested" if open_positions > 0 else "Cash"
    market_exposure_pct = (
        float(np.mean(np.asarray(positions_history) > 0) * 100.0) if len(positions_history) else 0.0
    )

    kpis = {
        "initial_portfolio_value": float(initial_cash),
        "final_portfolio_value": float(portfolio_values[-1]),
        "profit_loss_egp": float(portfolio_values[-1] - initial_cash),
        "total_return_pct": float(total_return_pct),
        "benchmark_return_pct": float(benchmark_return_pct),
        "excess_return_pct": float(total_return_pct - benchmark_return_pct),
        "sharpe_ratio": float(trading_metrics.sharpe(daily_returns)) if len(daily_returns) else 0.0,
        "maximum_drawdown_pct": float(drawdown.min()) if len(drawdown) else 0.0,
        "maximum_drawdown_egp": float(_max_drawdown_egp(portfolio_values)),
        "current_drawdown_pct": float(drawdown[-1]) if len(drawdown) else 0.0,
        "total_buy_operations": int(buy_operations),
        "total_sell_operations": int(sell_operations),
        "total_operations": int(buy_operations + sell_operations),
        "market_exposure_pct": float(market_exposure_pct),
        "current_portfolio_state": current_state,
        "positions_currently_held": int(open_positions),
    }

    response = {
        "strategy": strategy,
        "strategy_label": STRATEGY_LABELS[strategy],
        "strategy_description": STRATEGY_DESCRIPTIONS[strategy],
        "requested_start_date": requested_start_date,
        "actual_start_date": actual_start_date,
        "end_date": dates[-1] if dates else actual_start_date,
        "initial_cash": float(initial_cash),
        "universe": universe,
        "benchmark_label": BENCHMARK_LABEL,
        "dates": dates,
        "portfolio_values": np.asarray(portfolio_values, dtype=float),
        "equity": equity,
        "benchmark_values": np.asarray(benchmark_values, dtype=float),
        "benchmark_equity": benchmark_equity,
        "drawdown": drawdown,
        "trades": trades,
        "trade_columns": TRADE_COLUMNS,
        "kpis": kpis,
        "parameters": parameters,
        "extra": extra or {},
    }
    return _jsonable(response)


@lru_cache(maxsize=1)
def load_best_neural_artifact() -> dict[str, Any]:
    if not BEST_NEURAL_ARTIFACT_PATH.exists():
        raise FileNotFoundError(
            f"Missing dashboard artifact: {BEST_NEURAL_ARTIFACT_PATH.as_posix()}"
        )
    return json.loads(BEST_NEURAL_ARTIFACT_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_neural_artifact(strategy: str, universe: str) -> dict[str, Any]:
    strategy = normalize_strategy_name(strategy)
    if strategy not in {"mlp", "lstm"}:
        raise ValueError("load_neural_artifact only supports mlp and lstm")

    if strategy == "mlp" and universe == "full" and BEST_NEURAL_ARTIFACT_PATH.exists():
        return load_best_neural_artifact()

    feed = get_feed_for_universe(universe)
    if strategy == "mlp":
        run = run_shared_model_portfolio(
            feed,
            "mlp",
            feature_names=MLP_CONFIG["feature_names"],
            lookback=MLP_LOOKBACK,
            hidden=MLP_CONFIG["hidden"],
            n_hidden_layers=MLP_CONFIG["n_hidden_layers"],
            epochs=MLP_CONFIG["epochs"],
            lr=MLP_CONFIG["lr"],
            seed=MLP_CONFIG["seed"],
            commission=MLP_CONFIG["commission"],
            benchmark=MLP_CONFIG["benchmark"],
        )
        return build_dashboard_artifact(
            strategy_id="mlp",
            strategy_name="MLP Portfolio",
            strategy_description=STRATEGY_DESCRIPTIONS["mlp"],
            run=run,
        )

    run = run_shared_model_portfolio(
        feed,
        "lstm",
        feature_names=LSTM_CONFIG["feature_names"],
        lookback=LSTM_LOOKBACK,
        hidden=LSTM_CONFIG["hidden"],
        seq_len=LSTM_CONFIG["seq_len"],
        epochs=LSTM_CONFIG["epochs"],
        lr=LSTM_CONFIG["lr"],
        seed=LSTM_CONFIG["seed"],
        commission=LSTM_CONFIG["commission"],
        benchmark=LSTM_CONFIG["benchmark"],
    )
    return build_dashboard_artifact(
        strategy_id="lstm",
        strategy_name="LSTM Portfolio",
        strategy_description=STRATEGY_DESCRIPTIONS["lstm"],
        run=run,
    )


def _weight_matrix_from_artifact(feed: DataFeed, artifact: dict[str, Any]) -> np.ndarray:
    config = artifact["config"]
    start_day = int(config["start_day"])
    end_day = int(config["end_day"])
    weights = np.asarray(artifact["weights"], dtype=float)
    matrix = np.zeros((feed.n_days, feed.n_assets), dtype=float)
    matrix[start_day:end_day] = weights
    return matrix


@lru_cache(maxsize=4)
def get_sma_weight_history(universe: str) -> np.ndarray:
    feed = get_feed_for_universe(universe)
    weights_by_day = np.zeros((feed.n_days, feed.n_assets), dtype=float)
    for day_index in range(SMA_LOOKBACK, feed.n_days - 1):
        observation = build_observation(feed, day_index, SMA_LOOKBACK)
        weights_by_day[day_index] = sma_crossover_weights(
            observation,
            fast=SMA_FAST_WINDOW,
            slow=SMA_SLOW_WINDOW,
        )
    return weights_by_day


def build_strategy_response(
    strategy: str,
    *,
    universe: str,
    start_date: str | None,
    initial_cash: float,
) -> dict[str, Any]:
    strategy = normalize_strategy_name(strategy)
    if initial_cash <= 0:
        raise HTTPException(status_code=400, detail="initial_cash must be greater than 0")

    feed = get_feed_for_universe(universe)
    requested_start_date, start_day, actual_start_date = _resolve_start_day(
        feed,
        strategy,
        universe,
        start_date,
    )

    if strategy in {"mlp", "lstm"}:
        artifact = load_neural_artifact(strategy, universe)
        weights_by_day = _weight_matrix_from_artifact(feed, artifact)
        simulation = _simulate_weight_strategy(
            feed,
            weights_by_day,
            start_day=start_day,
            initial_cash=initial_cash,
        )
        benchmark_values = _build_equal_weight_benchmark(feed, start_day, initial_cash)
        config = artifact["config"]
        feature_names = list(artifact.get("feature_names", []))
        parameters = {
            "model": strategy.upper(),
            "universe": universe,
            "start_date": actual_start_date,
            "initial_cash": float(initial_cash),
            "benchmark_label": BENCHMARK_LABEL,
        }
        extra = {
            "architecture_hidden": int(config["hidden"]),
            "hidden_layers": int(config.get("n_hidden_layers", 1)) if strategy == "mlp" else None,
            "sequence_length": int(config.get("seq_len", 0)) if strategy == "lstm" else None,
            "epochs": int(config["epochs"]),
            "learning_rate": float(config["lr"]),
            "seed": int(config["seed"]),
            "feature_names": feature_names,
            "selection_rule": "Equal-weight the stocks with positive predicted returns",
            "oos_valid_start_date": _format_date(feed.dates[_strategy_earliest_start_day(feed, strategy)]),
            "oos_valid_end_date": _format_date(feed.dates[-1]),
            "average_stocks_held_full_period": artifact["metrics"].get("average_stocks_held"),
        }
        return _build_common_response(
            strategy=strategy,
            universe=universe,
            requested_start_date=requested_start_date,
            actual_start_date=actual_start_date,
            initial_cash=initial_cash,
            dates=simulation["dates"],
            portfolio_values=simulation["portfolio_values"],
            benchmark_values=benchmark_values,
            positions_history=simulation["positions_history"],
            invested_history=simulation["invested_history"],
            trades=simulation["trades"],
            parameters=parameters,
            extra=extra,
        )

    if strategy == "sma":
        weights_by_day = get_sma_weight_history(universe)
        simulation = _simulate_weight_strategy(
            feed,
            weights_by_day,
            start_day=start_day,
            initial_cash=initial_cash,
        )
        benchmark_values = _build_equal_weight_benchmark(feed, start_day, initial_cash)
        parameters = {
            "fast_window": SMA_FAST_WINDOW,
            "slow_window": SMA_SLOW_WINDOW,
            "universe": universe,
            "start_date": actual_start_date,
            "initial_cash": float(initial_cash),
            "benchmark_label": BENCHMARK_LABEL,
        }
        extra = {
            "signal_definition": "Hold equally weighted uptrends where SMA(9) > SMA(20); otherwise hold cash",
            "lookback_window_days": SMA_LOOKBACK,
            "average_stocks_held": float(np.mean(simulation["positions_history"])) if len(simulation["positions_history"]) else 0.0,
        }
        return _build_common_response(
            strategy=strategy,
            universe=universe,
            requested_start_date=requested_start_date,
            actual_start_date=actual_start_date,
            initial_cash=initial_cash,
            dates=simulation["dates"],
            portfolio_values=simulation["portfolio_values"],
            benchmark_values=benchmark_values,
            positions_history=simulation["positions_history"],
            invested_history=simulation["invested_history"],
            trades=simulation["trades"],
            parameters=parameters,
            extra=extra,
        )

    benchmark_values = _build_equal_weight_benchmark(feed, start_day, initial_cash)
    result = run_video_strategy(
        feed,
        start_day=start_day,
        initial_cash=initial_cash,
        lookback_days=VIDEO_LOOKBACK_DAYS,
        buy_threshold=VIDEO_BUY_THRESHOLD,
        sell_threshold=VIDEO_SELL_THRESHOLD,
        buy_notional=VIDEO_BUY_NOTIONAL,
        sell_notional=VIDEO_SELL_NOTIONAL,
    )
    parameters = {
        "lookback_days": VIDEO_LOOKBACK_DAYS,
        "buy_threshold_pct": VIDEO_BUY_THRESHOLD * 100.0,
        "sell_threshold_pct": VIDEO_SELL_THRESHOLD * 100.0,
        "buy_notional": VIDEO_BUY_NOTIONAL,
        "sell_notional": VIDEO_SELL_NOTIONAL,
        "universe": universe,
        "start_date": actual_start_date,
        "initial_cash": float(initial_cash),
        "benchmark_label": BENCHMARK_LABEL,
    }
    extra = {
        "signal_definition": "Sell 10 EGP after a 5-day rise of at least 10%; buy 5 EGP after a 5-day decline of at least 5%",
        "execution_order": "Sell-first, then buy",
        "fractional_shares": True,
        "short_selling": False,
    }
    return _build_common_response(
        strategy=strategy,
        universe=universe,
        requested_start_date=requested_start_date,
        actual_start_date=actual_start_date,
        initial_cash=initial_cash,
        dates=result["dates"],
        portfolio_values=result["portfolio_values"],
        benchmark_values=benchmark_values,
        positions_history=result["positions_history"],
        invested_history=result["invested_history"],
        trades=result["trades"],
        parameters=parameters,
        extra=extra,
    )


def run_video_strategy(
    feed: DataFeed,
    *,
    start_day: int,
    initial_cash: float,
    lookback_days: int,
    buy_threshold: float,
    sell_threshold: float,
    buy_notional: float,
    sell_notional: float,
) -> dict[str, Any]:
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    if buy_threshold >= 0:
        raise ValueError("buy_threshold must be negative")
    if sell_threshold <= 0:
        raise ValueError("sell_threshold must be positive")
    if buy_notional <= 0 or sell_notional <= 0:
        raise ValueError("trade notionals must be greater than zero")

    close = np.asarray(feed.close, dtype=float)
    n_days, n_stocks = close.shape

    weekly_signals = np.full_like(close, np.nan, dtype=float)
    for day_index in range(n_days):
        recent_index = day_index - 1
        earlier_index = day_index - 1 - lookback_days
        if recent_index < 0 or earlier_index < 0:
            continue
        recent = close[recent_index]
        earlier = close[earlier_index]
        valid = np.isfinite(recent) & np.isfinite(earlier) & (recent > 0) & (earlier > 0)
        weekly_signals[day_index, valid] = recent[valid] / earlier[valid] - 1.0

    cash = float(initial_cash)
    holdings = np.zeros(n_stocks, dtype=float)
    latest_valid_price = np.asarray(close[start_day], dtype=float).copy()
    trades: list[dict[str, Any]] = []

    dates: list[str] = []
    portfolio_values: list[float] = []
    positions_history: list[int] = []
    invested_history: list[float] = []

    for day_index in range(start_day, n_days):
        today_prices = close[day_index]
        today_signal = weekly_signals[day_index]

        valid_prices = np.isfinite(today_prices) & (today_prices > 0)
        latest_valid_price[valid_prices] = today_prices[valid_prices]

        invested_before = float(np.dot(holdings, latest_valid_price))
        portfolio_value = float(cash + invested_before)

        for asset_index in range(n_stocks):
            price = today_prices[asset_index]
            signal = today_signal[asset_index]
            if not (np.isfinite(price) and price > 0 and np.isfinite(signal)):
                continue
            if signal >= sell_threshold and holdings[asset_index] > EPSILON:
                position_value = float(holdings[asset_index] * price)
                actual_notional = min(sell_notional, position_value)
                if actual_notional <= EPSILON:
                    continue
                shares_to_sell = min(actual_notional / price, holdings[asset_index])
                holdings[asset_index] -= shares_to_sell
                if holdings[asset_index] < EPSILON:
                    holdings[asset_index] = 0.0
                cash += actual_notional
                trades.append(
                    {
                        "date": _format_date(feed.dates[day_index]),
                        "operation": "SELL",
                        "symbol": feed.symbols[asset_index],
                        "price": float(price),
                        "shares": float(shares_to_sell),
                        "notional": float(actual_notional),
                        "portfolio_value_after": float(portfolio_value),
                    }
                )

        for asset_index in range(n_stocks):
            price = today_prices[asset_index]
            signal = today_signal[asset_index]
            if not (np.isfinite(price) and price > 0 and np.isfinite(signal)):
                continue
            if signal <= buy_threshold:
                actual_notional = min(buy_notional, cash)
                if actual_notional <= EPSILON:
                    continue
                shares_to_buy = actual_notional / price
                holdings[asset_index] += shares_to_buy
                cash -= actual_notional
                if cash < EPSILON:
                    cash = max(cash, 0.0)
                trades.append(
                    {
                        "date": _format_date(feed.dates[day_index]),
                        "operation": "BUY",
                        "symbol": feed.symbols[asset_index],
                        "price": float(price),
                        "shares": float(shares_to_buy),
                        "notional": float(actual_notional),
                        "portfolio_value_after": float(portfolio_value),
                    }
                )

        invested_after = 0.0
        open_positions = 0
        for asset_index in range(n_stocks):
            if holdings[asset_index] <= EPSILON:
                continue
            price_for_value = latest_valid_price[asset_index]
            if np.isfinite(price_for_value) and price_for_value > 0:
                invested_after += float(holdings[asset_index] * price_for_value)
                open_positions += 1

        dates.append(_format_date(feed.dates[day_index]))
        portfolio_values.append(float(cash + invested_after))
        positions_history.append(int(open_positions))
        invested_history.append(float(invested_after))

    return {
        "dates": dates,
        "portfolio_values": np.asarray(portfolio_values, dtype=float),
        "positions_history": np.asarray(positions_history, dtype=int),
        "invested_history": np.asarray(invested_history, dtype=float),
        "trades": trades,
    }


def _legacy_single_stock_backtest(
    feed: DataFeed,
    symbol: str,
    *,
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
) -> dict[str, Any]:
    if fast_window < 1:
        raise HTTPException(status_code=400, detail="fast_window must be at least 1")
    if slow_window < 2:
        raise HTTPException(status_code=400, detail="slow_window must be at least 2")
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")
    if initial_cash <= 0:
        raise HTTPException(status_code=400, detail="initial_cash must be greater than 0")

    asset_index = feed.symbols.index(symbol)
    prices = np.asarray(feed.close[:, asset_index], dtype=float)
    dates = [_format_date(day) for day in feed.dates]
    fast_ma = sma(prices, fast_window)
    slow_ma = sma(prices, slow_window)

    cash = float(initial_cash)
    shares = 0
    trades = []
    portfolio_values = []
    cash_history = []
    shares_history = []
    buy_markers = []
    sell_markers = []
    buy_hold_values = []

    last_valid_portfolio_value = float(initial_cash)
    last_valid_buy_hold_value = float(initial_cash)

    buy_hold_cash = float(initial_cash)
    buy_hold_shares = 0
    buy_hold_active = False

    for i, price in enumerate(prices):
        valid_price = np.isfinite(price) and price > 0

        if i == 0:
            if valid_price:
                last_valid_portfolio_value = float(cash + shares * price)
            portfolio_values.append(last_valid_portfolio_value)
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(None)
            sell_markers.append(None)
            buy_hold_values.append(float(buy_hold_cash))
            continue

        if valid_price:
            prev_fast = fast_ma[i - 1]
            prev_slow = slow_ma[i - 1]
            bought = False
            sold = False

            if np.isfinite(prev_fast) and np.isfinite(prev_slow) and prev_fast > prev_slow and shares == 0:
                shares_to_buy = int(cash // price)
                if shares_to_buy > 0:
                    cash -= shares_to_buy * price
                    shares += shares_to_buy
                    bought = True
                    trades.append(
                        {
                            "type": "BUY",
                            "date": dates[i],
                            "price": float(price),
                            "shares": int(shares_to_buy),
                            "cash_after": float(cash),
                            "portfolio_value_after": float(cash + shares * price),
                        }
                    )
            elif (
                np.isfinite(prev_fast)
                and np.isfinite(prev_slow)
                and prev_fast < prev_slow
                and shares > 0
                and i != len(prices) - 1
            ):
                shares_sold = shares
                cash += shares * price
                shares = 0
                sold = True
                trades.append(
                    {
                        "type": "SELL",
                        "date": dates[i],
                        "price": float(price),
                        "shares": int(shares_sold),
                        "cash_after": float(cash),
                        "portfolio_value_after": float(cash),
                    }
                )

            last_valid_portfolio_value = float(cash + shares * price)
            portfolio_values.append(last_valid_portfolio_value)
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(float(price) if bought else None)
            sell_markers.append(float(price) if sold else None)

            if not buy_hold_active:
                shares_to_buy_bh = int(buy_hold_cash // price)
                if shares_to_buy_bh > 0:
                    buy_hold_cash -= shares_to_buy_bh * price
                    buy_hold_shares += shares_to_buy_bh
                    buy_hold_active = True
            last_valid_buy_hold_value = float(buy_hold_cash + buy_hold_shares * price)
            buy_hold_values.append(last_valid_buy_hold_value)
        else:
            portfolio_values.append(last_valid_portfolio_value)
            cash_history.append(float(cash))
            shares_history.append(int(shares))
            buy_markers.append(None)
            sell_markers.append(None)
            buy_hold_values.append(last_valid_buy_hold_value)

    drawdown = _drawdown_series_pct(np.asarray(portfolio_values, dtype=float))
    valid_days = sum(1 for price in prices if np.isfinite(price) and price > 0)
    exposure_days = sum(1 for share_count in shares_history if share_count > 0)
    exposure_pct = (exposure_days / valid_days * 100.0) if valid_days else 0.0

    final_portfolio_value = float(portfolio_values[-1])
    buy_hold_final_value = float(buy_hold_values[-1])
    total_return_pct = ((final_portfolio_value / initial_cash) - 1.0) * 100.0
    buy_hold_return_pct = ((buy_hold_final_value / initial_cash) - 1.0) * 100.0

    return {
        "symbol": symbol,
        "parameters": {
            "fast_window": fast_window,
            "slow_window": slow_window,
            "initial_cash": float(initial_cash),
        },
        "dates": dates,
        "close": prices,
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "buy_markers": buy_markers,
        "sell_markers": sell_markers,
        "portfolio_values": portfolio_values,
        "buy_hold_values": buy_hold_values,
        "cash_history": cash_history,
        "shares_history": shares_history,
        "trades": trades,
        "kpis": {
            "initial_portfolio_value": float(initial_cash),
            "final_portfolio_value": final_portfolio_value,
            "profit_loss_egp": final_portfolio_value - initial_cash,
            "total_return_pct": total_return_pct,
            "maximum_drawdown_egp": _max_drawdown_egp(np.asarray(portfolio_values, dtype=float)),
            "maximum_drawdown_pct": float(drawdown.min()) if len(drawdown) else 0.0,
            "buy_operations": sum(1 for trade in trades if trade["type"] == "BUY"),
            "sell_operations": sum(1 for trade in trades if trade["type"] == "SELL"),
            "total_operations": len(trades),
            "final_cash": float(cash),
            "final_shares": int(shares),
            "current_position": "Invested" if shares > 0 else "Cash",
            "exposure_days": exposure_days,
            "exposure_pct": exposure_pct,
            "buy_hold_final_value": buy_hold_final_value,
            "buy_hold_return_pct": buy_hold_return_pct,
            "excess_return_pct_points": total_return_pct - buy_hold_return_pct,
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/strategies")
def strategies() -> list[dict[str, Any]]:
    return [
        {
            "id": strategy,
            "label": STRATEGY_LABELS[strategy],
            "description": STRATEGY_DESCRIPTIONS[strategy],
            "supported_universes": ["small", "full"],
        }
        for strategy in STRATEGY_ORDER
    ]


@app.get("/universe")
def universe(universe: str = "full") -> list[str]:
    return list(get_feed_for_universe(universe).symbols)


@app.get("/strategy-metadata")
def strategy_metadata(universe: str = "full") -> dict[str, Any]:
    feed = get_feed_for_universe(universe)
    latest_start_day = _latest_start_day(feed)
    metadata = {
        "universe": universe,
        "market_history_start_date": _format_date(feed.dates[0]),
        "market_history_end_date": _format_date(feed.dates[-1]),
        "latest_start_date": _format_date(feed.dates[latest_start_day]),
    }
    for strategy in STRATEGY_ORDER:
        earliest_day = _strategy_earliest_start_day(feed, strategy)
        metadata[strategy] = {
            "earliest_start_date": _format_date(feed.dates[earliest_day]),
            "latest_start_date": _format_date(feed.dates[latest_start_day]),
            "strategy_label": STRATEGY_LABELS[strategy],
        }
    metadata["common_earliest_start_date"] = _format_date(feed.dates[_common_earliest_start_day(feed)])
    return metadata


@app.get("/strategy/{strategy_name}")
def strategy_endpoint(
    strategy_name: str,
    universe: str = "full",
    start_date: str | None = None,
    initial_cash: float = 1000.0,
) -> dict[str, Any]:
    try:
        return build_strategy_response(
            strategy_name,
            universe=universe,
            start_date=start_date,
            initial_cash=initial_cash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/prices/{symbol}")
def prices(symbol: str, universe: str = "full") -> dict[str, Any]:
    feed = get_feed_for_universe(universe)
    chosen = get_symbol_or_404(feed, symbol)
    asset_index = feed.symbols.index(chosen)
    return _jsonable(
        {
            "symbol": chosen,
            "universe": universe,
            "dates": [_format_date(day) for day in feed.dates],
            "close": feed.close[:, asset_index],
        }
    )


@app.get("/indicators/{symbol}")
def indicators(symbol: str, universe: str = "full", fast_window: int = 9, slow_window: int = 20) -> dict[str, Any]:
    feed = get_feed_for_universe(universe)
    chosen = get_symbol_or_404(feed, symbol)
    if fast_window < 1:
        raise HTTPException(status_code=400, detail="fast_window must be at least 1")
    if slow_window < 2:
        raise HTTPException(status_code=400, detail="slow_window must be at least 2")
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")

    asset_index = feed.symbols.index(chosen)
    prices = np.asarray(feed.close[:, asset_index], dtype=float)
    fast_ma = sma(prices, fast_window)
    slow_ma = sma(prices, slow_window)
    return _jsonable(
        {
            "symbol": chosen,
            "universe": universe,
            "dates": [_format_date(day) for day in feed.dates],
            "close": prices,
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
        }
    )


@app.get("/backtest/{symbol}")
def legacy_sma_backtest(
    symbol: str,
    universe: str = "full",
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
) -> dict[str, Any]:
    feed = get_feed_for_universe(universe)
    chosen = get_symbol_or_404(feed, symbol)
    result = _legacy_single_stock_backtest(
        feed,
        chosen,
        fast_window=fast_window,
        slow_window=slow_window,
        initial_cash=initial_cash,
    )
    return _jsonable(result)
