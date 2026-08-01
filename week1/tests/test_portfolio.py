"""The core: a portfolio's return is the weighted average of its holdings'."""
import numpy as np
from tradinglab.portfolio import portfolio_return


def test_single_asset():
    w = np.array([1.0, 0.0, 0.0]); r = np.array([0.10, 0.05, -0.20])
    assert abs(portfolio_return(w, r) - 0.10) < 1e-12


def test_equal_weight_is_mean():
    w = np.array([0.5, 0.5]); r = np.array([0.10, 0.20])
    assert abs(portfolio_return(w, r) - 0.15) < 1e-12


def test_all_cash_style_zero():
    w = np.array([0.0, 0.0]); r = np.array([0.9, -0.9])
    assert portfolio_return(w, r) == 0.0
