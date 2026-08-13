"""
forecast.py — a simple forward price PROJECTION, not a prediction system.

Fits a geometric Brownian motion (drift + volatility estimated from historical
daily log returns) and projects it forward analytically. GBM is the standard
"simplest honest model" for a price series: it says future daily returns look
like a random draw from the past distribution, nothing more. No new
dependency needed — numpy/scipy already ship with the project.

This is explicitly NOT a claim that the model can predict where the stock is
going. It is a statistical extrapolation of the asset's own historical drift
and volatility, useful as a baseline range, not a forecast to trade on.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

TRADING_DAYS = 252


def gbm_forecast(
    close: np.ndarray,
    horizon_years: float = 3.0,
    confidence: float = 0.80,
) -> dict:
    """Project `close` forward under GBM with drift/vol fit to its own history.

    Returns arrays of length horizon_days: the median path and the lower/upper
    bounds of a `confidence` interval (e.g. 0.80 -> 10th/90th percentile).
    """
    close = np.asarray(close, dtype=float)
    log_returns = np.diff(np.log(close))
    mu = float(np.mean(log_returns))
    sigma = float(np.std(log_returns))

    horizon_days = int(round(horizon_years * TRADING_DAYS))
    t = np.arange(1, horizon_days + 1)

    drift = (mu - 0.5 * sigma**2) * t
    spread = sigma * np.sqrt(t)

    last_price = close[-1]
    z_lo = norm.ppf((1 - confidence) / 2)
    z_hi = norm.ppf(1 - (1 - confidence) / 2)

    median = last_price * np.exp(drift)
    lower = last_price * np.exp(drift + z_lo * spread)
    upper = last_price * np.exp(drift + z_hi * spread)

    return {
        "horizon_days": horizon_days,
        "median": median,
        "lower": lower,
        "upper": upper,
        "confidence": confidence,
        "annualized_drift_pct": float(mu * TRADING_DAYS * 100.0),
        "annualized_volatility_pct": float(sigma * np.sqrt(TRADING_DAYS) * 100.0),
    }
