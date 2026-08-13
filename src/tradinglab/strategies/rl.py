"""
rl.py — load a trained PPO agent (scripts/run_train.py or
notebooks/colab_train.ipynb) as an observation->weights strategy.

Unlike the other strategies, the PPO policy doesn't output weights directly —
env.py's action_to_weights (top_k softmax over the raw policy output) is how
PortfolioEnv itself turns an action into weights during training, so applying
the SAME conversion here is what makes running the trained policy outside the
gym env equivalent to running it inside one.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..env import action_to_weights


def load_rl_strategy(checkpoint_path: str | Path, top_k: int = 2):
    """Load a PPO checkpoint (.zip, stable-baselines3 format) and return a
    ready-to-use observation->weights strategy function.

    Raises FileNotFoundError if the checkpoint doesn't exist yet — run
    scripts/run_train.py first.
    """
    checkpoint_path = Path(checkpoint_path)
    zip_path = checkpoint_path if checkpoint_path.suffix == ".zip" else checkpoint_path.with_suffix(".zip")
    if not zip_path.exists():
        raise FileNotFoundError(
            f"no PPO checkpoint at {zip_path} — run scripts/run_train.py first, "
            "it trains and saves this file as its last step."
        )
    from stable_baselines3 import PPO   # deferred: heavy import, only needed if RL is actually used
    model = PPO.load(str(checkpoint_path))

    def strategy(observation: np.ndarray) -> np.ndarray:
        action, _ = model.predict(observation.astype(np.float32), deterministic=True)
        return action_to_weights(np.asarray(action, dtype=np.float64), top_k)

    return strategy
