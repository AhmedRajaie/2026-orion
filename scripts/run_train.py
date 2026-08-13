"""
run_train.py — train the RL agent locally (laptop or GPU PC).

Cleaner than the Colab notebook when you're on your own machine. From the repo
root:

    uv run python scripts/run_train.py

Change the settings below and re-run to experiment.
"""
from __future__ import annotations
import json, sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradinglab.train import train

if __name__ == "__main__":
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    os.makedirs("results/logs", exist_ok=True)
    os.makedirs("results/reports", exist_ok=True)
    log_path = f"results/logs/ppo_train_{run_id}.log"

    def log(line: str):
        print(line)
        with open(log_path, "a") as f:
            f.write(line + "\n")

    model, tr, te = train(
        data_dir="data/egx",
        timesteps=100_000,   # more = longer; try 200k on a GPU PC
        reward="excess",     # "return" | "excess" | "risk_adjusted"
        top_k=2,             # how many stocks the agent holds (raise with universe)
        lookback=30,
        # commission=0.001,  # uncomment to train under trading costs
    )
    log("TRAIN  agent %.3f  benchmark %.3f" % (tr["final_portfolio"], tr["final_benchmark"]))
    log("TEST   agent %.3f  benchmark %.3f" % (te["final_portfolio"], te["final_benchmark"]))
    log(f"beat benchmark on TEST: {te['final_portfolio'] > te['final_benchmark']}")

    os.makedirs("models", exist_ok=True)
    model.save("models/ppo_agent")
    log("saved -> models/ppo_agent.zip")

    report_path = f"results/reports/ppo_train_{run_id}.json"
    with open(report_path, "w") as f:
        json.dump({"run_id": run_id, "train": tr, "test": te}, f, indent=2, default=float)
    log(f"report -> {report_path}")
