"""
nn.py — Neural-network strategy for the dashboard.

Trains an ensemble of compact MLPs to predict the 5-day forward return of a
single asset from the canonical 9-feature technical set, then converts the
prediction into a long/cash trading rule:

    weights = [1.0]  if  predicted 5-day return > 0
              [0.0]  otherwise (stay in cash)

The strategy is a closure that captures the feed and a day counter so it can
look up the pre-computed standardized features for the current day. The
backtester calls the strategy sequentially starting at `lookback`, so the day
counter maps correctly to the feed's calendar index.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

from tradinglab.data_feed import DataFeed
from tradinglab.indicators import ema, sma, rsi, rolling_volatility

FEATURE_NAMES = [
    "return", "p/sma_fast", "p/sma_slow", "rsi", "volatility",
    "macd_hist", "return_5d", "return_10d", "volume_ratio",
]
N_FEATURES = len(FEATURE_NAMES)
HORIZON = 5


class MLP(nn.Module):
    """Compact MLP with BatchNorm + Dropout, sized for ~1700 training samples."""

    def __init__(self, input_size: int, dropout: float = 0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 16),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def build_features(feed: DataFeed, asset: int = 0) -> np.ndarray:
    """Compute the 9-feature matrix for one asset: (days, N_FEATURES)."""
    close = feed.close[:, asset]
    ret = feed.returns[:, asset]
    vol = feed.volume[:, asset]
    n = feed.n_days

    # MACD histogram
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    macd_line = ema12 - ema26
    first_valid = int(np.argmax(~np.isnan(macd_line)))
    macd_signal = np.full(n, np.nan)
    macd_signal[first_valid:] = ema(macd_line[first_valid:], 9)
    macd_hist = macd_line - macd_signal

    # Multi-day momentum
    ret5 = np.full(n, np.nan)
    ret5[5:] = close[5:] / close[:-5] - 1.0
    ret10 = np.full(n, np.nan)
    ret10[10:] = close[10:] / close[:-10] - 1.0

    # Volume ratio: today's volume / 20-day average
    vol_avg20 = np.full(n, np.nan)
    for i in range(19, n):
        vol_avg20[i] = vol[i - 19 : i + 1].mean()
    volume_ratio = vol / vol_avg20

    return np.column_stack([
        ret,
        close / sma(close, 10) - 1.0,
        close / sma(close, 30) - 1.0,
        rsi(close, 14) / 100.0,
        rolling_volatility(ret, 20),
        macd_hist,
        ret5,
        ret10,
        volume_ratio,
    ])


def train_nn_ensemble(
    feed: DataFeed,
    asset: int = 0,
    n_seeds: int = 3,
    epochs: int = 500,
    lr: float = 1e-3,
    batch_size: int = 64,
    patience: int = 30,
    weight_decay: float = 1e-4,
):
    """Train an ensemble of MLPs to predict 5-day forward returns.

    Returns (models, mu, sigma):
        models: list of trained MLP modules
        mu, sigma: standardization statistics fit on the training set only
    """
    X_full = build_features(feed, asset)
    close = feed.close[:, asset]
    n = feed.n_days

    # Label: 5-day forward return
    y_full = np.full(n, np.nan)
    y_full[:-HORIZON] = close[HORIZON:] / close[:-HORIZON] - 1.0

    valid = ~np.isnan(X_full).any(axis=1) & ~np.isnan(y_full)
    X = X_full[valid].astype(np.float32)
    y = y_full[valid].astype(np.float32)

    # Chronological 60/20/20 split
    n_samples = len(X)
    train_end = int(n_samples * 0.6)
    val_end = int(n_samples * 0.8)

    Xtr, ytr = X[:train_end], y[:train_end]
    Xva, yva = X[train_end:val_end], y[train_end:val_end]

    # Standardize on training set only
    mu = Xtr.mean(axis=0)
    sigma = Xtr.std(axis=0) + 1e-8
    Xtr = (Xtr - mu) / sigma
    Xva = (Xva - mu) / sigma

    Xtr_t = torch.tensor(Xtr)
    ytr_t = torch.tensor(ytr)
    Xva_t = torch.tensor(Xva)
    yva_t = torch.tensor(yva)

    loss_fn = nn.MSELoss()
    models = []

    for seed in range(n_seeds):
        torch.manual_seed(seed)
        np.random.seed(seed)

        model = MLP(N_FEATURES)
        train_ds = TensorDataset(Xtr_t, ytr_t)
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

        optimizer = torch.optim.Adam(
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
            for xb, yb in train_loader:
                optimizer.zero_grad()
                pred = model(xb)
                loss = loss_fn(pred, yb)
                loss.backward()
                optimizer.step()

            model.eval()
            with torch.no_grad():
                val_loss = loss_fn(model(Xva_t), yva_t).item()

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

    return models, mu, sigma


def make_nn_strategy(feed: DataFeed, asset: int = 0, models=None, mu=None, sigma=None):
    """Create a strategy function: observation -> weights.

    The strategy goes long (weight 1.0 on the asset) when the ensemble's
    predicted 5-day forward return is positive, otherwise holds cash.
    """
    if models is None or mu is None or sigma is None:
        models, mu, sigma = train_nn_ensemble(feed, asset)

    # Pre-compute standardized features for the whole feed; NaN warm-up -> 0
    X_full = build_features(feed, asset)
    X_std = np.nan_to_num((X_full - mu) / sigma).astype(np.float32)

    state = {"day": 0}

    def strategy(observation: np.ndarray) -> np.ndarray:
        lookback = observation.shape[1]
        day = lookback + state["day"]
        state["day"] += 1

        n_assets = observation.shape[0]
        if day >= len(X_std):
            return np.zeros(n_assets)

        features = X_std[day]

        with torch.no_grad():
            x = torch.tensor(features, dtype=torch.float32).unsqueeze(0)
            preds = [m(x).item() for m in models]
            pred = float(np.mean(preds))

        weights = np.zeros(n_assets)
        if pred > 0:
            weights[0] = 1.0
        return weights

    return strategy