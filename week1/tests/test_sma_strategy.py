"""The strategy must always return a valid portfolio."""
import numpy as np
from tradinglab.strategies.sma import sma_crossover_weights


def test_weights_sum_to_one():
    obs = np.random.default_rng(0).normal(0, 0.02, (5, 30, 4))
    w = sma_crossover_weights(obs)
    assert abs(w.sum() - 1.0) < 1e-9


def test_weights_non_negative():
    obs = np.random.default_rng(1).normal(0, 0.02, (5, 30, 4))
    w = sma_crossover_weights(obs)
    assert (w >= 0).all()


def test_shape_matches_universe():
    obs = np.zeros((8, 30, 4))
    assert sma_crossover_weights(obs).shape == (8,)
