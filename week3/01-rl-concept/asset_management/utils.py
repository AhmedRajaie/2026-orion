"""Data generation and plotting helpers for the asset-management exercise."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


DEFAULT_TICKERS = ("ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON", "ZETA", "ETA", "THETA")


def trading_dates(start: date = date(2026, 7, 6), end: date = date(2026, 8, 4)) -> list[date]:
    """Return every calendar day in the assignment's simulation period."""
    if end < start:
        raise ValueError("end must be on or after start")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def generate_synthetic_prices(
    n_days: int,
    n_stocks: int = 8,
    seed: int = 7,
) -> np.ndarray:
    """Generate positive, moderately correlated daily prices with random walks."""
    if n_days < 2:
        raise ValueError("At least two days of prices are required.")
    if n_stocks < 2:
        raise ValueError("At least two stocks are required.")

    rng = np.random.default_rng(seed)
    starting_prices = rng.uniform(45.0, 160.0, size=n_stocks)
    # Each stock has a small distinct drift; a shared shock makes the series market-like.
    drifts = rng.normal(0.0005, 0.00045, size=n_stocks)
    volatilities = rng.uniform(0.010, 0.025, size=n_stocks)
    market_shocks = rng.normal(0.0, 0.006, size=(n_days - 1, 1))
    idiosyncratic_shocks = rng.normal(0.0, 1.0, size=(n_days - 1, n_stocks))
    log_returns = drifts + market_shocks + idiosyncratic_shocks * volatilities

    prices = np.empty((n_days, n_stocks), dtype=float)
    prices[0] = starting_prices
    prices[1:] = starting_prices * np.exp(np.cumsum(log_returns, axis=0))
    return prices


def plot_training(history: dict[str, list[float]], output_dir: str | Path, show: bool = False) -> None:
    """Save the three required assignment charts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(history["episode_rewards"], alpha=0.30, label="episode reward")
    window = min(25, len(history["episode_rewards"]))
    if window:
        rolling = np.convolve(history["episode_rewards"], np.ones(window) / window, mode="valid")
        ax.plot(range(window - 1, len(history["episode_rewards"])), rolling, label=f"{window}-episode average")
    ax.set(title="Q-Learning training rewards", xlabel="Episode", ylabel="Cumulative reward")
    ax.grid(alpha=0.3); ax.legend(); fig.tight_layout()
    fig.savefig(output_path / "episode_rewards.png", dpi=150)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(history["epsilons"])
    ax.set(title="Epsilon decay", xlabel="Episode", ylabel="Exploration rate")
    ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(output_path / "epsilon_decay.png", dpi=150)

    if show:
        plt.show()
    else:
        plt.close("all")


def plot_portfolio(values: list[float], dates: list[date], output_dir: str | Path, show: bool = False) -> None:
    """Save a portfolio-value graph from a single evaluation episode."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, values, marker="o", markersize=3)
    ax.set(title="Evaluation portfolio value", xlabel="Date", ylabel="Portfolio value")
    ax.grid(alpha=0.3); fig.autofmt_xdate(); fig.tight_layout()
    fig.savefig(output_path / "portfolio_value.png", dpi=150)
    if show:
        plt.show()
    else:
        plt.close(fig)
