# Day 1 — Asset Management Game (Tabular Q-Learning)

This standalone solution adapts `day1a_gridworld_qtable.ipynb`: it keeps the
epsilon-greedy policy, Q-table, Bellman update, and reset/step training loop,
but replaces GridWorld with `StockTradingEnv`.

It simulates eight deterministic synthetic price series from **July 6 to
August 4, 2026**. The agent always owns exactly two stocks (one share each).
Every action selects a valid target pair; the environment automatically
generates all 28 possible pairs. The tabular state contains day, owned pair,
discretized normalized current prices, and discretized daily movements.
Rewards are next-day portfolio changes after transaction costs.

## Run

From this directory:

```bash
python main.py --episodes 800
```

The command prints final profit, total reward, daily portfolio history, and
actions. It saves the required charts in `outputs/`:

- `portfolio_value.png`
- `episode_rewards.png`
- `epsilon_decay.png`

## Files

- `stock_env.py` — custom environment with `reset()` and `step(action)`
- `q_learning.py` — tabular Q-table, epsilon-greedy selection, Bellman update
- `train.py` — training and greedy evaluation loops
- `utils.py` — synthetic data, dates, and plots
- `main.py` — runnable entry point
