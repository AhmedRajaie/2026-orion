"""
nn.py — load a trained MLP (the "NN model") as an observation->weights
strategy. Thin wrapper around predictor.py's model_to_strategy, which was
already built for exactly this shape: an MLP that only ever sees the LAST
timestep of the observation window (one day's features), unlike the LSTM
strategy which wants the whole window.
"""
from __future__ import annotations

from pathlib import Path

import torch

from ..models import MLP
from .predictor import model_to_strategy


def load_nn_strategy(checkpoint_path: str | Path, top_k: int = 2):
    """Load a checkpoint saved by week2/01-features-and-model/notebook.ipynb's
    pooled-MLP training (or the dashboard's own pooled-MLP script) and return
    a ready-to-use observation->weights strategy function.

    Raises FileNotFoundError if the checkpoint doesn't exist yet.
    """
    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"no NN checkpoint at {checkpoint_path} — train the pooled MLP first "
            "(see week2/01-features-and-model/notebook.ipynb)."
        )
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

    model = MLP(n_features=ckpt["n_features"], hidden=ckpt["hidden"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    return model_to_strategy(model, top_k=top_k)
