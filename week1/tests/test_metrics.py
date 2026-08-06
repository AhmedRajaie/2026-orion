"""Tests for day-4 metrics. Run: uv run pytest week1/day4-backtest/tests/"""
import numpy as np
from tradinglab import metrics as met


def test_total_return_simple():
    # +10% then +10% compounds to +21%
    assert abs(met.total_return(np.array([0.1, 0.1])) - 0.21) < 1e-9


def test_total_return_zero():
    assert met.total_return(np.zeros(100)) == 0.0


def test_volatility_zero_for_constant():
    assert met.volatility(np.zeros(100)) == 0.0


def test_sharpe_zero_when_flat():
    assert met.sharpe(np.zeros(100)) == 0.0


def test_max_drawdown_known():
    # up 100% then down 50% -> drawdown of 50%
    dd = met.max_drawdown(np.array([1.0, -0.5]))
    assert abs(dd - 0.5) < 1e-9


def test_max_drawdown_never_negative():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, 300)
    assert met.max_drawdown(r) >= 0
