"""The chart tool built in notebook 1."""
import matplotlib
matplotlib.use("Agg")
import numpy as np
from tradinglab.charting import plot_price


def test_plot_price_draws_close_only():
    ax = plot_price(range(5), [1., 2, 3, 4, 5])
    assert len(ax.lines) == 1


def test_plot_price_draws_overlays():
    ax = plot_price(range(5), [1., 2, 3, 4, 5],
                    overlays={"sma": [1., 1, 1, 1, 1], "ema": [2., 2, 2, 2, 2]})
    assert len(ax.lines) == 3          # close + 2 overlays
