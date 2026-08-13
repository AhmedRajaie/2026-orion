from dashboard.backend.main import _build_strategies


def test_build_strategies_all_keeps_model_strategies():
    names = [name for name, _ in _build_strategies("ALL")]

    assert "NN 5-day" in names
    assert "LSTM 1-day" in names
