"""
lstm.py — turn a trained LSTMRegressor into an observation->weights strategy,
the sequence-model counterpart of predictor.py's model_to_strategy.

Why this isn't just predictor.py: model_to_strategy uses only the LAST
timestep of the observation window (`observation[:, -1, :]`), matching an MLP
that only ever saw one day at a time. An LSTM wants the WHOLE window instead —
and build_observation(feed, day, lookback) already returns exactly
(n_assets, lookback, n_features), which IS LSTMRegressor's (batch, seq_len,
n_features) shape with batch=n_assets. No reshaping needed, just scaling.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from ..models import LSTMRegressor
from ..ml import predict
from .predictor import predictions_to_weights


def lstm_model_to_strategy(model: LSTMRegressor, mean: np.ndarray, std: np.ndarray, top_k: int = 2):
    """Wrap a trained LSTM (plus the feature scaler it was trained with) as a
    backtester strategy: observation -> weights.

    mean/std: per-feature scaler fit on the TRAINING split only (see
    lstm.ipynb) — the same scaling has to be applied at inference time or the
    model sees an out-of-distribution input.
    """

    def strategy(observation: np.ndarray) -> np.ndarray:
        scaled = (observation.astype("float32") - mean) / std
        preds = predict(model, scaled.astype("float32"))   # one prediction per asset
        return predictions_to_weights(preds, top_k)

    return strategy


def load_lstm_strategy(checkpoint_path: str | Path, top_k: int = 2):
    """Load a checkpoint saved by lstm.ipynb (state_dict + architecture +
    scaler) and return a ready-to-use observation->weights strategy function.

    Raises FileNotFoundError if the checkpoint doesn't exist yet — run
    lstm.ipynb first, it trains the pooled model and saves this file as its
    last step.
    """
    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"no LSTM checkpoint at {checkpoint_path} — run lstm.ipynb first, "
            "its last cells train the pooled model this dashboard strategy uses."
        )
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

    model = LSTMRegressor(n_features=ckpt["n_features"], hidden=ckpt["hidden"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    return lstm_model_to_strategy(model, ckpt["scaler_mean"], ckpt["scaler_std"], top_k=top_k)
