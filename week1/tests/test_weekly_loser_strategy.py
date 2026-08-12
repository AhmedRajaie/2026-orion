import numpy as np

from tradinglab.strategies.mean_reversion import weekly_loser_weights


def observation_from_returns(returns):
    returns = np.asarray(returns, dtype=float)
    observation = np.zeros((returns.shape[0], returns.shape[1], 5))
    observation[:, :, 0] = returns
    return observation


def test_weekly_losers_are_bought_in_proportion_to_decline():
    observation = observation_from_returns([
        [-0.01, -0.01, -0.01, -0.01, -0.01],
        [0.02, 0.00, 0.00, 0.00, 0.00],
        [-0.02, -0.02, -0.02, -0.02, -0.02],
    ])

    weights = weekly_loser_weights(observation, lookback_days=5)

    assert np.all(weights >= 0)
    assert np.isclose(weights.sum(), 1.0)
    assert weights[1] == 0.0
    assert weights[2] > weights[0]


def test_all_winners_means_cash():
    observation = observation_from_returns([
        [0.01, 0.01, 0.01, 0.01, 0.01],
        [0.02, 0.02, 0.02, 0.02, 0.02],
    ])

    weights = weekly_loser_weights(observation, lookback_days=5)

    assert np.array_equal(weights, np.zeros(2))


def test_short_observation_means_cash():
    observation = observation_from_returns([
        [-0.01, -0.01, -0.01],
        [-0.02, -0.02, -0.02],
    ])

    weights = weekly_loser_weights(observation, lookback_days=5)

    assert np.array_equal(weights, np.zeros(2))


def test_invalid_lookback_is_rejected():
    observation = observation_from_returns([[-0.01]])

    try:
        weekly_loser_weights(observation, lookback_days=0)
    except ValueError as error:
        assert "lookback_days" in str(error)
    else:
        raise AssertionError("expected ValueError")
