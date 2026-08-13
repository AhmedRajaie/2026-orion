# results/

Output home for everything the models/scripts/notebooks in this repo produce.
Trained model *weights* the dashboard loads at runtime still live in `models/`
(the backend imports fixed paths like `models/lstm_dashboard.pt`) — this
folder is for things generated *from* a run, not the checkpoints themselves.

- `model_outputs/` — raw predictions, evaluation arrays, exported per-symbol
  comparison CSVs (train/test predictions, metrics tables).
- `reports/` — generated summaries, leaderboards, training run reports.
- `figures/` — charts and plots (comparison PNGs, equity curves, etc.).
- `logs/` — run logs from training/evaluation scripts (e.g.
  `scripts/run_train.py`), one file per run, timestamped.

## Convention

When a script or notebook produces an artifact worth keeping, write it here
instead of the repo root, and prefer a timestamp or run-id in the filename
(e.g. `results/logs/ppo_train_2026-08-13.log`) so repeated runs don't clobber
each other silently.
