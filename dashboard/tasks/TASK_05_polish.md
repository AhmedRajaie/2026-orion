# Task 05 — Polish v1 (Day 5)

**Goal:** make it presentable for the four-minute demo.

**Ideas (pick what improves it):**
- A dropdown to switch symbols (fetch `/universe` to fill it).
- Show the key metrics as text (total return, Sharpe, max drawdown) next to the
  equity curve. Add a `/metrics` endpoint using `tradinglab.metrics`.
- Tidy the layout: titles, spacing, consistent colors.
- A toggle to switch the WHOLE dashboard between two universes: the small
  6-stock teaching set and the full universe.

**Prompt (metrics endpoint):**
> Add `/metrics` returning total_return, sharpe, and max_drawdown of the backtest
> portfolio returns, using functions from `tradinglab.metrics`. Round to 3 dp.

**Prompt (universe toggle — backend):**
> In dashboard/backend/main.py, replace the single global `feed` with two named
> feeds:
>   feeds = {
>       "small": DataFeed.from_dir("data/egx", symbols=["COMI","HRHO","TMGH","SWDY","FWRY", "ABUK","ABUK"]),
>       "full":  DataFeed.from_dir("data/egx"),
>   }
> Update every existing endpoint (`/universe`, `/prices/{symbol}`, `/backtest`,
> `/metrics`) to accept a query parameter `universe: str = "small"`, defaulting
> to "small" so nothing breaks if the frontend omits it, and use `feeds[universe]`
> instead of the old global `feed` inside each one. Rebuild the `PortfolioSimulator`
> for that request using the selected feed. Return a 400 error for an unknown
> universe value rather than crashing.

**Prompt (universe toggle — frontend):**
> Add a toggle (two buttons or a small dropdown) labeled "Small universe" /
> "Full universe" near the top of the page, defaulting to "Small universe".
> Store the selection in a variable. Every existing fetch call (`/universe`,
> `/prices/{symbol}`, `/backtest`, `/metrics`) must include `?universe=` with
> the current selection, and switching the toggle should re-fetch and redraw
> every panel — price chart, equity curve, and the metrics text — not just one
> of them.

**Verify:** one clean page — price + indicator, equity curve vs benchmark, the
three numbers, and a working toggle that visibly changes every panel when
switched (a different symbol list in the dropdown, a different equity curve
shape, different metrics numbers). Demo it.