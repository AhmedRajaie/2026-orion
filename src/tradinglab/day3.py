"""
day3.py - shared helpers for Week 2 Day 3.

This module keeps the "prediction -> weights -> backtest" path in one place so
the Day 3 notebooks and the dashboard can reuse the exact same logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch

from .data_feed import DataFeed
from .features import FEATURE_NAMES, SMA_FAST, SMA_SLOW
from .indicators import ema, rolling_volatility, rsi, sma
from .metrics import (
    directional_accuracy,
    information_coefficient,
    max_drawdown,
    sharpe,
    total_return,
)
from .ml import predict, train_model
from .models import DeepMLP, LSTMRegressor, MLP
from .simulator import PortfolioSimulator

BASELINE_FEATURES = ("return", "p/sma_fast", "p/sma_slow", "rsi", "volatility")
ALL_FEATURES = tuple(FEATURE_NAMES)


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


def _validate_feature_names(feature_names: Sequence[str]) -> tuple[str, ...]:
    chosen = tuple(feature_names)
    invalid = [name for name in chosen if name not in ALL_FEATURES]
    if invalid:
        raise ValueError(f"unknown feature(s): {invalid}")
    return chosen


def feature_table(feed: DataFeed, asset: int, feature_names: Sequence[str] = BASELINE_FEATURES) -> np.ndarray:
    """Return a per-stock feature matrix using only repository indicators."""
    feature_names = _validate_feature_names(feature_names)

    close = feed.close[:, asset]
    ret = feed.returns[:, asset]
    volume = feed.volume[:, asset]

    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    macd_line = ema12 - ema26
    macd_signal = np.full(feed.n_days, np.nan, dtype=float)
    valid_macd = np.flatnonzero(~np.isnan(macd_line))
    if len(valid_macd):
        first_valid = int(valid_macd[0])
        macd_signal[first_valid:] = ema(macd_line[first_valid:], 9)
    macd_hist = macd_line - macd_signal

    ret5 = np.full(feed.n_days, np.nan, dtype=float)
    ret10 = np.full(feed.n_days, np.nan, dtype=float)
    ret5[5:] = close[5:] / close[:-5] - 1.0
    ret10[10:] = close[10:] / close[:-10] - 1.0

    vol_avg20 = np.full(feed.n_days, np.nan, dtype=float)
    for i in range(19, feed.n_days):
        vol_avg20[i] = volume[i - 19 : i + 1].mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        volume_ratio = volume / vol_avg20

    feature_map = {
        "return": ret,
        "p/sma_fast": close / sma(close, SMA_FAST) - 1.0,
        "p/sma_slow": close / sma(close, SMA_SLOW) - 1.0,
        "rsi": rsi(close, 14) / 100.0,
        "volatility": rolling_volatility(ret, 20),
        "macd_hist": macd_hist,
        "return_5d": ret5,
        "return_10d": ret10,
        "volume_ratio": volume_ratio,
    }
    return np.column_stack([feature_map[name] for name in feature_names]).astype(np.float32)


def build_feature_tensor(
    feed: DataFeed,
    feature_names: Sequence[str] = BASELINE_FEATURES,
) -> np.ndarray:
    """Return (n_assets, n_days, n_features) once so repeated runs reuse it."""
    feature_names = _validate_feature_names(feature_names)
    return np.stack([feature_table(feed, asset, feature_names) for asset in range(feed.n_assets)])


def _target_vector(feed: DataFeed, asset: int) -> np.ndarray:
    y_full = np.full(feed.n_days, np.nan, dtype=np.float32)
    y_full[:-1] = feed.returns[1:, asset]
    return y_full


def build_pooled_dataset_from_tensor(
    feed: DataFeed,
    feature_tensor: np.ndarray,
    split_day: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pool train/test rows across stocks while respecting the calendar split."""
    days = np.arange(feed.n_days)
    Xtr_list: list[np.ndarray] = []
    ytr_list: list[np.ndarray] = []
    Xte_list: list[np.ndarray] = []
    yte_list: list[np.ndarray] = []

    for asset in range(feed.n_assets):
        X_full = feature_tensor[asset]
        y_full = _target_vector(feed, asset)
        valid = ~np.isnan(X_full).any(axis=1) & ~np.isnan(y_full)
        train_mask = valid & (days < split_day)
        test_mask = valid & (days >= split_day)
        Xtr_list.append(X_full[train_mask])
        ytr_list.append(y_full[train_mask])
        Xte_list.append(X_full[test_mask])
        yte_list.append(y_full[test_mask])

    return (
        np.vstack(Xtr_list).astype(np.float32),
        np.concatenate(ytr_list).astype(np.float32),
        np.vstack(Xte_list).astype(np.float32),
        np.concatenate(yte_list).astype(np.float32),
    )


def _to_sequences(X: np.ndarray, y: np.ndarray, seq_len: int) -> tuple[np.ndarray, np.ndarray]:
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for i in range(seq_len, len(X)):
        xs.append(X[i - seq_len : i])
        ys.append(y[i])
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def build_pooled_sequences_from_tensor(
    feed: DataFeed,
    feature_tensor: np.ndarray,
    split_day: int,
    seq_len: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build sequence datasets per stock first, then pool them."""
    days = np.arange(feed.n_days)
    Xtr_list: list[np.ndarray] = []
    ytr_list: list[np.ndarray] = []
    Xte_list: list[np.ndarray] = []
    yte_list: list[np.ndarray] = []

    for asset in range(feed.n_assets):
        X_full = feature_tensor[asset]
        y_full = _target_vector(feed, asset)
        valid = ~np.isnan(X_full).any(axis=1) & ~np.isnan(y_full)
        train_mask = valid & (days < split_day)
        test_mask = valid & (days >= split_day)

        X_train_stock = X_full[train_mask]
        y_train_stock = y_full[train_mask]
        X_test_stock = X_full[test_mask]
        y_test_stock = y_full[test_mask]

        if len(X_train_stock) > seq_len:
            xs, ys = _to_sequences(X_train_stock, y_train_stock, seq_len)
            Xtr_list.append(xs)
            ytr_list.append(ys)
        if len(X_test_stock) > seq_len:
            xs, ys = _to_sequences(X_test_stock, y_test_stock, seq_len)
            Xte_list.append(xs)
            yte_list.append(ys)

    return (
        np.vstack(Xtr_list).astype(np.float32),
        np.concatenate(ytr_list).astype(np.float32),
        np.vstack(Xte_list).astype(np.float32),
        np.concatenate(yte_list).astype(np.float32),
    )


def positive_equal_weight_weights(predicted_returns: np.ndarray) -> np.ndarray:
    """Hold every positively predicted stock equally; otherwise stay in cash."""
    preds = np.asarray(predicted_returns, dtype=float)
    positive = preds > 0
    weights = np.zeros_like(preds, dtype=np.float32)
    count = int(positive.sum())
    if count:
        weights[positive] = 1.0 / count
    return weights


def prediction_matrix_to_weights(predictions: np.ndarray) -> np.ndarray:
    return np.vstack([positive_equal_weight_weights(row) for row in predictions]).astype(np.float32)


def _build_shared_model(
    model_type: str,
    n_features: int,
    hidden: int,
    n_hidden_layers: int,
):
    if model_type == "mlp":
        if n_hidden_layers <= 1:
            return MLP(n_features, hidden=hidden)
        return DeepMLP(n_features, hidden=hidden, n_hidden_layers=n_hidden_layers)
    if model_type == "lstm":
        return LSTMRegressor(n_features=n_features, hidden=hidden)
    raise ValueError(f"unknown model_type '{model_type}'")


def train_shared_model(
    feed: DataFeed,
    model_type: str,
    split_day: int,
    feature_names: Sequence[str] = BASELINE_FEATURES,
    *,
    feature_tensor: np.ndarray | None = None,
    hidden: int = 32,
    n_hidden_layers: int = 1,
    seq_len: int = 10,
    epochs: int = 150,
    lr: float = 1e-3,
    seed: int = 0,
) -> dict[str, Any]:
    feature_names = _validate_feature_names(feature_names)
    feature_tensor = build_feature_tensor(feed, feature_names) if feature_tensor is None else feature_tensor

    set_seed(seed)
    if model_type == "mlp":
        X_train, y_train, X_test, y_test = build_pooled_dataset_from_tensor(feed, feature_tensor, split_day)
    elif model_type == "lstm":
        X_train, y_train, X_test, y_test = build_pooled_sequences_from_tensor(
            feed,
            feature_tensor,
            split_day,
            seq_len,
        )
    else:
        raise ValueError(f"unknown model_type '{model_type}'")

    model = _build_shared_model(model_type, X_train.shape[-1], hidden, n_hidden_layers)
    history = train_model(model, X_train, y_train, X_test, y_test, epochs=epochs, lr=lr)
    test_predictions = predict(model, X_test)

    return {
        "model": model,
        "history": history,
        "X_train": X_train,
        "y_train": y_train,
        "X_test": X_test,
        "y_test": y_test,
        "test_predictions": np.asarray(test_predictions, dtype=np.float32),
        "prediction_metrics": {
            "test_mse": float(np.mean((test_predictions - y_test) ** 2)),
            "directional_accuracy": directional_accuracy(test_predictions, y_test),
            "information_coefficient": information_coefficient(test_predictions, y_test),
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "final_train_loss": float(history["train"][-1]),
            "final_test_loss": float(history["test"][-1]),
        },
    }


def infer_prediction_matrix(
    model,
    feed: DataFeed,
    model_type: str,
    start_day: int,
    end_day: int,
    feature_names: Sequence[str] = BASELINE_FEATURES,
    *,
    feature_tensor: np.ndarray | None = None,
    seq_len: int = 10,
) -> np.ndarray:
    feature_names = _validate_feature_names(feature_names)
    feature_tensor = build_feature_tensor(feed, feature_names) if feature_tensor is None else feature_tensor
    predictions: list[np.ndarray] = []

    for day_index in range(start_day, end_day):
        if model_type == "mlp":
            batch = np.nan_to_num(feature_tensor[:, day_index, :]).astype(np.float32)
        elif model_type == "lstm":
            batch = np.nan_to_num(feature_tensor[:, day_index - seq_len + 1 : day_index + 1, :]).astype(np.float32)
        else:
            raise ValueError(f"unknown model_type '{model_type}'")
        predictions.append(np.asarray(predict(model, batch), dtype=np.float32))

    return np.vstack(predictions).astype(np.float32)


def summarize_backtest(result: dict[str, Any]) -> dict[str, Any]:
    weights = np.asarray(result["weights"], dtype=float)
    portfolio_returns = np.asarray(result["portfolio_returns"], dtype=float)
    benchmark_returns = np.asarray(result["benchmark_returns"], dtype=float)
    holdings = (weights > 1e-6).sum(axis=1) if len(weights) else np.array([], dtype=int)

    return {
        "final_value": float(result["portfolio"][-1]),
        "benchmark_final_value": float(result["benchmark"][-1]),
        "total_return": total_return(portfolio_returns),
        "benchmark_return": total_return(benchmark_returns),
        "excess_return": total_return(portfolio_returns) - total_return(benchmark_returns),
        "sharpe": sharpe(portfolio_returns),
        "benchmark_sharpe": sharpe(benchmark_returns),
        "max_drawdown": max_drawdown(portfolio_returns),
        "benchmark_max_drawdown": max_drawdown(benchmark_returns),
        "average_stocks_held": float(holdings.mean()) if len(holdings) else 0.0,
        "minimum_stocks_held": int(holdings.min()) if len(holdings) else 0,
        "maximum_stocks_held": int(holdings.max()) if len(holdings) else 0,
        "percentage_days_invested": float(np.mean(holdings > 0)) if len(holdings) else 0.0,
        "n_days": int(len(portfolio_returns)),
    }


def run_shared_model_portfolio(
    feed: DataFeed,
    model_type: str,
    split_day: int | None = None,
    feature_names: Sequence[str] = BASELINE_FEATURES,
    *,
    feature_tensor: np.ndarray | None = None,
    lookback: int = 30,
    hidden: int = 32,
    n_hidden_layers: int = 1,
    seq_len: int = 10,
    epochs: int = 150,
    lr: float = 1e-3,
    seed: int = 0,
    commission: float = 0.0,
    benchmark: str = "equal_weight",
) -> dict[str, Any]:
    """Train one shared model, convert predictions to weights, and backtest it."""
    split_day = int(feed.n_days * 0.7) if split_day is None else int(split_day)
    feature_names = _validate_feature_names(feature_names)
    feature_tensor = build_feature_tensor(feed, feature_names) if feature_tensor is None else feature_tensor

    training = train_shared_model(
        feed,
        model_type,
        split_day,
        feature_names,
        feature_tensor=feature_tensor,
        hidden=hidden,
        n_hidden_layers=n_hidden_layers,
        seq_len=seq_len,
        epochs=epochs,
        lr=lr,
        seed=seed,
    )

    start_day = max(split_day, lookback, seq_len if model_type == "lstm" else 1)
    end_day = feed.n_days - 1
    predictions = infer_prediction_matrix(
        training["model"],
        feed,
        model_type,
        start_day,
        end_day,
        feature_names,
        feature_tensor=feature_tensor,
        seq_len=seq_len,
    )
    weights = prediction_matrix_to_weights(predictions)

    weights_by_day = np.zeros((feed.n_days, feed.n_assets), dtype=np.float32)
    weights_by_day[start_day:end_day] = weights

    sim = PortfolioSimulator(feed, benchmark=benchmark, commission=commission)
    result = sim.run(weights_by_day, start_day, end_day)
    result["weights"] = weights_by_day[start_day:end_day]
    result["predictions"] = predictions
    result["actual_returns"] = feed.returns[start_day + 1 : end_day + 1].astype(np.float32)
    result["signal_dates"] = feed.dates[start_day:end_day]
    result["symbols"] = list(feed.symbols)
    result["feature_names"] = list(feature_names)
    result["config"] = {
        "model_type": model_type,
        "split_day": int(split_day),
        "split_date": str(feed.dates[split_day]),
        "start_day": int(start_day),
        "start_date": str(feed.dates[start_day]),
        "first_realized_date": str(feed.dates[start_day + 1]),
        "end_day": int(end_day),
        "end_date": str(feed.dates[end_day]),
        "lookback": int(lookback),
        "hidden": int(hidden),
        "n_hidden_layers": int(n_hidden_layers),
        "seq_len": int(seq_len),
        "epochs": int(epochs),
        "lr": float(lr),
        "seed": int(seed),
        "commission": float(commission),
        "benchmark": benchmark,
    }
    result["prediction_metrics"] = training["prediction_metrics"]
    result["metrics"] = summarize_backtest(result)

    return {
        "model": training["model"],
        "history": training["history"],
        "training": training,
        "result": result,
    }


def aggregate_run_metrics(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        raise ValueError("aggregate_run_metrics requires at least one run")

    returns = np.array([run["result"]["metrics"]["total_return"] for run in runs], dtype=float)
    sharpes = np.array([run["result"]["metrics"]["sharpe"] for run in runs], dtype=float)
    drawdowns = np.array([run["result"]["metrics"]["max_drawdown"] for run in runs], dtype=float)
    excess = np.array([run["result"]["metrics"]["excess_return"] for run in runs], dtype=float)
    beat = np.array([run["result"]["metrics"]["final_value"] > run["result"]["metrics"]["benchmark_final_value"] for run in runs], dtype=bool)
    seeds = [run["result"]["config"]["seed"] for run in runs]

    best_idx = int(np.argmax(returns))
    worst_idx = int(np.argmin(returns))
    return {
        "mean_total_return": float(returns.mean()),
        "std_total_return": float(returns.std()),
        "mean_sharpe": float(sharpes.mean()),
        "mean_max_drawdown": float(drawdowns.mean()),
        "mean_excess_return": float(excess.mean()),
        "beat_benchmark_count": int(beat.sum()),
        "beat_benchmark_pct": float(beat.mean()),
        "best_seed": int(seeds[best_idx]),
        "worst_seed": int(seeds[worst_idx]),
    }


def weight_change_summary(weights: np.ndarray, threshold: float = 1e-6) -> dict[str, np.ndarray]:
    weights = np.asarray(weights, dtype=float)
    prev = np.vstack([np.zeros((1, weights.shape[1]), dtype=float), weights[:-1]])
    delta = weights - prev
    return {
        "delta": delta,
        "daily_buys": (delta > threshold).sum(axis=1).astype(int),
        "daily_sells": (delta < -threshold).sum(axis=1).astype(int),
    }


def build_dashboard_artifact(
    strategy_id: str,
    strategy_name: str,
    strategy_description: str,
    run: dict[str, Any],
) -> dict[str, Any]:
    result = run["result"]
    return {
        "strategy": {
            "id": strategy_id,
            "name": strategy_name,
            "description": strategy_description,
        },
        "symbols": list(result["symbols"]),
        "dates": [str(date)[:10] for date in result["dates"]],
        "signal_dates": [str(date)[:10] for date in result["signal_dates"]],
        "portfolio": np.asarray(result["portfolio"], dtype=float).tolist(),
        "benchmark": np.asarray(result["benchmark"], dtype=float).tolist(),
        "weights": np.asarray(result["weights"], dtype=float).tolist(),
        "predictions": np.asarray(result["predictions"], dtype=float).tolist(),
        "actual_returns": np.asarray(result["actual_returns"], dtype=float).tolist(),
        "metrics": result["metrics"],
        "prediction_metrics": result["prediction_metrics"],
        "config": result["config"],
        "feature_names": list(result["feature_names"]),
        "benchmark_name": "Equal-weight benchmark",
    }


def save_dashboard_artifact(path: str | Path, artifact: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(artifact), indent=2), encoding="utf-8")


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
