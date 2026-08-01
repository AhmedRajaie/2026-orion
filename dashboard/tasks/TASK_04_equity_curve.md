# Task 04 — Equity curve vs benchmark (Day 4)

**Goal:** the money chart — your strategy's growth vs the benchmark.

**Prompt (backend):**
> Add `/backtest` that runs the SMA crossover strategy and returns
> `{ "portfolio":[...], "benchmark":[...] }`. Use:
>   from tradinglab.simulator import PortfolioSimulator
>   from tradinglab.backtester import run_backtest
>   from tradinglab.strategies.sma import sma_crossover_weights
> Build the feed + simulator, call run_backtest with lookback=30, and return the
> 'portfolio' and 'benchmark' curves as lists.

**Prompt (frontend):**
> Add a new `.panel` with `<canvas id="equityChart">`. Fetch `/backtest` and draw
> two lines (strategy vs benchmark), both starting at 1.0. Title it clearly.

**Verify:** two equity curves. Notice the strategy trails the benchmark — good,
that's the truth, and it sets up week 2.
