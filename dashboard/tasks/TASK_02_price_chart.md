# Task 02 — Price chart (Day 2)

**Goal:** show one stock's closing price as a line chart.

**Context:** the backend can import the library:
`from tradinglab.data_feed import DataFeed`.

**Prompt (paste into Copilot Chat):**
> In dashboard/backend/main.py, using `from tradinglab.data_feed import DataFeed`
> and `feed = DataFeed.from_dir("data/egx")`, add two GET endpoints:
> 1. `/universe` returning the list `feed.symbols`.
> 2. `/prices/{symbol}` returning `{ "dates": [...], "close": [...] }` for that
>    symbol (dates as "YYYY-MM-DD" strings). Return 404 if the symbol is unknown.
> Keep it simple and synchronous.

**Then, frontend:**
> In index.html add a `<canvas id="priceChart">` inside a `.panel`. In app.js,
> fetch `/universe`, pick the first symbol, fetch `/prices/{symbol}`, and draw a
> Chart.js line chart of close vs dates.

**Verify:** a price line appears. Try changing the symbol in the URL.
