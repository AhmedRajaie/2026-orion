"""Tests for the day-3 indicators. Run: uv run pytest week1/day3-indicators/tests/"""
import numpy as np
from tradinglab import indicators as ind


def test_sma_known_values():
    p = np.array([1, 2, 3, 4, 5], dtype=float)
    out = ind.sma(p, 3)
    assert np.isnan(out[:2]).all()          # first (window-1) are NaN
    assert out[2] == 2.0                     # mean(1,2,3)
    assert out[4] == 4.0                     # mean(3,4,5)


def test_sma_length_matches_input():
    p = np.arange(50, dtype=float)
    assert len(ind.sma(p, 10)) == len(p)


def test_ema_reacts_faster_than_sma():
    p = np.concatenate([np.ones(20), np.ones(20) * 2])  # a jump up at index 20
    e = ind.ema(p, 10); s = ind.sma(p, 10)
    # A few steps after the jump, EMA is closer to the new level than SMA.
    assert e[25] > s[25]


def test_rsi_bounds():
    rng = np.random.default_rng(0)
    p = np.cumprod(1 + rng.normal(0, 0.02, 200))
    r = ind.rsi(p, 14)
    valid = r[~np.isnan(r)]
    assert (valid >= 0).all() and (valid <= 100).all()


def test_rsi_all_gains_is_100():
    p = np.arange(1, 30, dtype=float)        # only rises
    r = ind.rsi(p, 14)
    assert np.nanmax(r) == 100.0


def test_volatility_zero_for_constant():
    assert ind.rolling_volatility(np.zeros(30), 20)[-1] == 0.0
