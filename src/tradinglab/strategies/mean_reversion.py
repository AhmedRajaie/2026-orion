"""
mean_reversion.py — the opposite bet from trend-following.

SMA crossover (week 1) bets that a stock going UP will keep going up. Mean
reversion bets the opposite: a stock pushed too far from "normal" tends to snap
back. Same interface as every other strategy — observation -> weights — so it
drops straight into the same backtester and leaderboard.
"""
from __future__ import annotations
import numpy as np


def weekly_loser_weights(
    observation: np.ndarray,
    lookback_days: int = 5,
) -> np.ndarray:
    """Buy recent losers, sized in proportion to their five-day decline.

    This is the long-only version of the strategy described in the supplied
    video. Feature 0 of ``observation`` contains daily simple returns. We
    compound the latest ``lookback_days`` returns to obtain each asset's recent
    return, keep only negative returns, and normalize their magnitudes into
    portfolio weights. Recent winners receive zero weight because the Week 1
    simulator intentionally does not support short positions.

    If no asset declined during the lookback period, return all-zero weights so
    the unallocated portfolio remains in cash.
    """
    observation = np.asarray(observation, dtype=float)
    n_assets = observation.shape[0]

    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    if observation.shape[1] < lookback_days:
        return np.zeros(n_assets)

    recent_returns = observation[:, -lookback_days:, 0]
    period_returns = np.prod(1.0 + recent_returns, axis=1) - 1.0

    loser_strength = np.maximum(-period_returns, 0.0)
    total_strength = loser_strength.sum()
    if total_strength == 0:
        return np.zeros(n_assets)

    return loser_strength / total_strength


def rsi_mean_reversion_weights(observation: np.ndarray, oversold: float = 30.0, top_k: int = 2) -> np.ndarray:
    """Hold the most OVERSOLD stocks — the ones RSI says have been beaten down
    the hardest — betting they bounce back toward normal.

    observation: (n_assets, lookback, n_features). Feature 3 is RSI (0-100),
    already computed for you — this is the SAME rsi() you built in week 1,
    reused here as a signal instead of just a chart overlay.

    Rule: rank stocks by today's RSI, lowest first (most oversold). Hold the
    `top_k` lowest, equal-weight. If nothing is actually oversold (below the
    `oversold` threshold), hold nothing — genuine cash, all-zero weights —
    instead of forcing a bet that isn't there.
    """
    n_assets = observation.shape[0]
    rsi_today = observation[:, -1, 3]              # today's RSI, per stock

    # ---8<--- solution
    oversold_mask = rsi_today < oversold
    candidates = np.where(oversold_mask)[0]

    if len(candidates) == 0:
        return np.zeros(n_assets)          # nothing oversold — hold cash

    # among the oversold candidates, take the top_k MOST oversold (lowest RSI)
    ranked = candidates[np.argsort(rsi_today[candidates])]
    chosen = ranked[:top_k]

    weights = np.zeros(n_assets)
    weights[chosen] = 1.0 / len(chosen)
    return weights
    # ---8<--- end
