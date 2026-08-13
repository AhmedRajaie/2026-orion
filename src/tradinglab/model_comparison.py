"""
model_comparison.py — reload a per-stock checkpoint (trained in
week2/01-features-and-model/notebook.ipynb's Part 5 for NN, lstm.ipynb's
Part 4 for LSTM) and re-run INFERENCE ONLY (never retraining) to serve the
dashboard's Model Comparison feature: metrics, loss history, and predicted-
vs-actual arrays for one (model, stock) pair.

The expensive part — training — already happened in the notebook and is
captured in the checkpoint (weights + loss history). Re-deriving the same
train/test split and re-running a forward pass is cheap and deterministic
(same pure functions, same data), which is what "reuse saved results, don't
recompute from scratch" means here — recomputing a full backward-pass
training run would violate that; a few milliseconds of forward passes to
reconstruct predictions that were never persisted as arrays does not.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .data_feed import DataFeed, load_symbol_full_history
from .features import build_dataset, train_test_split, to_sequences
from .models import MLP, LSTMRegressor
from .ml import predict
from .metrics import directional_accuracy
from .single_signal_backtest import run_signal_backtest

MODELS_DIR = "models"


class CheckpointNotFound(FileNotFoundError):
    pass


def _error_metrics(preds: np.ndarray, actual: np.ndarray) -> dict:
    rmse = float(np.sqrt(np.mean((preds - actual) ** 2)))
    mae = float(np.mean(np.abs(preds - actual)))
    non_trivial = np.abs(actual) > 1e-4
    mape = float(np.mean(np.abs((preds[non_trivial] - actual[non_trivial]) / actual[non_trivial])) * 100) if non_trivial.any() else None
    da = float(directional_accuracy(preds, actual)) * 100.0
    # A stock whose test-period price barely moves at all makes RMSE/MAPE and
    # especially directional accuracy meaningless (there's no direction to
    # call) rather than genuinely bad -- flag it instead of silently ranking
    # it as a "worst performer".
    low_liquidity = bool(np.std(actual) < 1e-6)
    return {
        "rmse": rmse, "mae": mae, "mape": mape,
        "directional_accuracy_pct": da, "low_liquidity": low_liquidity,
    }


def evaluate_nn_checkpoint(symbol: str, data_dir: str = "data/egx", capital: float = 1000.0) -> dict:
    """Reload the per-stock NN (MLP) checkpoint and reconstruct its test-set
    predictions, metrics, loss history, and a signal-following backtest."""
    path = Path(MODELS_DIR) / f"mlp_{symbol}.pt"
    if not path.exists():
        raise CheckpointNotFound(f"no NN checkpoint for '{symbol}' — run week2/01-features-and-model/notebook.ipynb's Part 5.")
    ckpt = torch.load(path, map_location="cpu", weights_only=False)

    model = MLP(n_features=ckpt["n_features"], hidden=ckpt["hidden"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    df = load_symbol_full_history(data_dir, symbol)
    dates = df["date"]
    close = df["close"].to_numpy()
    returns = (close[1:] / close[:-1] - 1.0).astype(np.float32)

    X = returns[:-1].reshape(-1, 1)
    y = returns[1:]
    X_train, y_train, X_test, y_test = train_test_split(X, y, train_frac=0.7)
    cut = int(len(X) * 0.7)
    # y[i] aligns with dates[i+2] (one diff for returns, one more for the
    # X/y lag) -- see the module docstring's index-alignment note.
    dates_test = dates.iloc[cut + 2:].reset_index(drop=True)

    train_preds = predict(model, X_train)
    test_preds = predict(model, X_test)

    signal_bt = run_signal_backtest(dates_test, test_preds, y_test, capital=capital)

    return {
        "model": "nn", "symbol": symbol,
        "dates_train": dates.iloc[2:2 + len(y_train)].dt.strftime("%Y-%m-%d").tolist(),
        "dates_test": dates_test.dt.strftime("%Y-%m-%d").tolist(),
        "y_train": y_train.tolist(), "train_preds": train_preds.tolist(),
        "y_test": y_test.tolist(), "test_preds": test_preds.tolist(),
        "train_loss_history": ckpt.get("train_loss_history"),
        "test_loss_history": ckpt.get("test_loss_history"),
        "metrics": _error_metrics(test_preds, y_test),
        "signal_backtest": signal_bt,
    }


def evaluate_lstm_checkpoint(symbol: str, data_dir: str = "data/egx", capital: float = 1000.0) -> dict:
    """Reload the per-stock LSTM checkpoint and reconstruct its test-set
    predictions, metrics, loss history, and a signal-following backtest."""
    path = Path(MODELS_DIR) / f"lstm_{symbol}.pt"
    if not path.exists():
        raise CheckpointNotFound(f"no LSTM checkpoint for '{symbol}' — run lstm.ipynb's Part 4.")
    ckpt = torch.load(path, map_location="cpu", weights_only=False)

    model = LSTMRegressor(n_features=ckpt["n_features"], hidden=ckpt["hidden"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    mean, std = ckpt["scaler_mean"], ckpt["scaler_std"]
    seq_len = ckpt["seq_len"]

    solo_feed = DataFeed.from_dir(data_dir, symbols=[symbol])
    X, y = build_dataset(solo_feed, 0)
    X_train, y_train, X_test, y_test = train_test_split(X, y, train_frac=0.7)

    X_train_scaled = (X_train - mean) / std
    X_test_scaled = (X_test - mean) / std
    X_train_seq, y_train_seq = to_sequences(X_train_scaled, y_train, seq_len)
    X_test_seq, y_test_seq = to_sequences(X_test_scaled, y_test, seq_len)

    # dates for feature_columns(feed, 0)[i] is solo_feed.dates[i]; build_dataset
    # drops leading NaN rows (indicator warm-up) uniformly from the front, and
    # to_sequences additionally drops the first seq_len rows of each split.
    cut = int(len(X) * 0.7)
    warmup = solo_feed.n_days - len(X)  # rows build_dataset's clean() dropped off the front
    train_start = warmup + seq_len
    test_start = warmup + cut + seq_len
    dates_train = solo_feed.dates[train_start: train_start + len(y_train_seq)]
    dates_test = solo_feed.dates[test_start: test_start + len(y_test_seq)]

    train_preds = predict(model, X_train_seq)
    test_preds = predict(model, X_test_seq)

    signal_bt = run_signal_backtest(dates_test, test_preds, y_test_seq, capital=capital)

    return {
        "model": "lstm", "symbol": symbol,
        "dates_train": [d.strftime("%Y-%m-%d") for d in dates_train],
        "dates_test": [d.strftime("%Y-%m-%d") for d in dates_test],
        "y_train": y_train_seq.tolist(), "train_preds": train_preds.tolist(),
        "y_test": y_test_seq.tolist(), "test_preds": test_preds.tolist(),
        "train_loss_history": ckpt.get("train_loss_history"),
        "test_loss_history": ckpt.get("test_loss_history"),
        "metrics": _error_metrics(test_preds, y_test_seq),
        "signal_backtest": signal_bt,
    }


EVALUATORS = {"nn": evaluate_nn_checkpoint, "lstm": evaluate_lstm_checkpoint}


def available_symbols_for(model_key: str) -> list[str]:
    prefix = {"nn": "mlp_", "lstm": "lstm_"}[model_key]
    return sorted(
        p.stem[len(prefix):] for p in Path(MODELS_DIR).glob(f"{prefix}*.pt")
        if p.stem != f"{prefix}dashboard"
    )
