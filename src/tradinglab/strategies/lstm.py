"""
lstm.py — LSTM strategy for the dashboard.

Based on the enhanced LSTM notebook (LSTM1.ipynb). Uses a 2-layer LSTM with
dropout, feature standardization, gradient clipping, ReduceLROnPlateau, and
early stopping to predict the next-day return from a 20-day lookback window.

The strategy goes long (weight 1.0) when the LSTM predicts a positive
next-day return, otherwise holds cash.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from tradinglab.data_feed import DataFeed

LOOKBACK = 20


class LSTMRegressor(nn.Module):
    """2-layer LSTM with dropout + MLP head, sized for ~2000 samples."""

    def __init__(self, input_size=1, hidden_size=64, num_layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        output, (hidden, cell) = self.lstm(x)
        last_output = output[:, -1, :]
        return self.head(last_output).squeeze(-1)


def _build_sequences(returns: np.ndarray, lookback: int = LOOKBACK):
    """Build (X, y) supervised windows from a returns series."""
    X, y = [], []
    for i in range(lookback, len(returns)):
        X.append(returns[i - lookback : i])
        y.append(returns[i])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def train_lstm_ensemble(
    feed: DataFeed,
    asset: int = 0,
    n_seeds: int = 3,
    epochs: int = 500,
    lr: float = 1e-3,
    patience: int = 30,
    weight_decay: float = 1e-4,
):
    """Train an ensemble of LSTMs to predict next-day returns.

    Returns (models, train_mean, train_std):
        models: list of trained LSTMRegressor modules
        train_mean, train_std: standardization stats fit on the training set
    """
    returns = feed.returns[:, asset].astype(np.float32)
    X, y = _build_sequences(returns, LOOKBACK)

    # Chronological 70/15/15 split
    n = len(X)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]

    # Standardize using training statistics only
    train_mean = X_train.mean()
    train_std = X_train.std()
    X_train_s = (X_train - train_mean) / train_std
    X_val_s = (X_val - train_mean) / train_std
    y_train_s = (y_train - train_mean) / train_std
    y_val_s = (y_val - train_mean) / train_std

    X_train_t = torch.tensor(X_train_s).unsqueeze(-1)
    X_val_t = torch.tensor(X_val_s).unsqueeze(-1)
    y_train_t = torch.tensor(y_train_s)
    y_val_t = torch.tensor(y_val_s)

    criterion = nn.MSELoss()
    models = []

    for seed in range(n_seeds):
        torch.manual_seed(seed)
        np.random.seed(seed)

        model = LSTMRegressor()
        optimizer = torch.optim.AdamW(
            model.parameters(), lr=lr, weight_decay=weight_decay
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=0.5, patience=10
        )

        best_val = float("inf")
        best_state = None
        epochs_no_improve = 0

        for _ in range(epochs):
            model.train()
            optimizer.zero_grad()
            pred = model(X_train_t)
            loss = criterion(pred, y_train_t)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            model.eval()
            with torch.no_grad():
                val_loss = criterion(model(X_val_t), y_val_t).item()

            scheduler.step(val_loss)

            if val_loss < best_val:
                best_val = val_loss
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                epochs_no_improve = 0
            else:
                epochs_no_improve += 1
                if epochs_no_improve >= patience:
                    break

        model.load_state_dict(best_state)
        models.append(model)

    return models, train_mean, train_std


def make_lstm_strategy(feed: DataFeed, asset: int = 0, models=None, train_mean=None, train_std=None):
    """Create a strategy function: observation -> weights.

    Goes long (weight 1.0) when the LSTM ensemble predicts a positive
    next-day return, otherwise holds cash.
    """
    if models is None or train_mean is None or train_std is None:
        models, train_mean, train_std = train_lstm_ensemble(feed, asset)

    returns = feed.returns[:, asset].astype(np.float32)
    state = {"day": 0}

    def strategy(observation: np.ndarray) -> np.ndarray:
        lookback = observation.shape[1]
        day = lookback + state["day"]
        state["day"] += 1

        n_assets = observation.shape[0]
        if day >= len(returns):
            return np.zeros(n_assets)

        # Build the 20-day window ending at `day`
        if day < LOOKBACK:
            return np.zeros(n_assets)

        window = returns[day - LOOKBACK : day]
        window_s = (window - train_mean) / train_std
        x = torch.tensor(window_s, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)

        with torch.no_grad():
            preds = [m(x).item() for m in models]
            pred = float(np.mean(preds))

        weights = np.zeros(n_assets)
        if pred > 0:
            weights[0] = 1.0
        return weights

    return strategy