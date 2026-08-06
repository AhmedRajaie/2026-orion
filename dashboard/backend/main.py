"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


from tradinglab.data_feed import DataFeed
from fastapi import HTTPException
from pathlib import Path

def find_repo_root(marker="data"):
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / marker).exists():
            return parent
    raise FileNotFoundError("Couldn't find repo root containing 'data/'")

REPO_ROOT = find_repo_root()
feed = DataFeed.from_dir(str(REPO_ROOT / "data" / "egx"))

@app.get("/universe")
def get_universe():
    return feed.symbols

@app.get("/prices/{symbol}")
def get_prices(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    idx = feed.symbols.index(symbol)
    dates = [str(d)[:10] for d in feed.dates]
    close = feed.close[:, idx].tolist()
    return {"dates": dates, "close": close}
@app.get("/backtest/{symbol}")
def get_backtest(symbol: str, fast: int = 9, slow: int = 20, initial_capital: float = 1000):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    if fast < 1 or slow < 1 or fast >= slow:
        raise HTTPException(status_code=400, detail="fast must be >= 1 and less than slow")

    idx = feed.symbols.index(symbol)
    dates_all = [str(d)[:10] for d in feed.dates]
    close_all = feed.close[:, idx].tolist()

    n = len(close_all)
    ma_fast = [None] * n
    ma_slow = [None] * n
    for i in range(fast - 1, n):
        ma_fast[i] = sum(close_all[i-fast+1:i+1]) / fast
    for i in range(slow - 1, n):
        ma_slow[i] = sum(close_all[i-slow+1:i+1]) / slow

    cash = initial_capital
    shares = 0.0
    in_position = False
    buy_count = 0
    sell_count = 0
    buy_signals = []
    sell_signals = []
    portfolio = []

    for i in range(n):
        price = close_all[i]
        mf, ms = ma_fast[i], ma_slow[i]

        if mf is not None and ms is not None:
            if mf > ms and not in_position:
                shares = cash / price
                cash = 0.0
                in_position = True
                buy_count += 1
                buy_signals.append({"date": dates_all[i], "price": price})
            elif mf < ms and in_position:
                cash = shares * price
                shares = 0.0
                in_position = False
                sell_count += 1
                sell_signals.append({"date": dates_all[i], "price": price})

        portfolio.append(cash + shares * price)

    final_value = portfolio[-1]
    running_max = []
    peak = float("-inf")
    for v in portfolio:
        peak = max(peak, v)
        running_max.append(peak)
    drawdowns = [(v - p) / p for v, p in zip(portfolio, running_max)]
    max_drawdown_pct = min(drawdowns)

    return {
        "symbol": symbol,
        "fast": fast,
        "slow": slow,
        "dates": dates_all,
        "close": close_all,
        "ma9": ma_fast,
        "ma20": ma_slow,
        "portfolio": portfolio,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "final_value": final_value,
        "total_return_pct": (final_value / initial_capital - 1) * 100,
        "max_drawdown_pct": max_drawdown_pct * 100,
        "buy_count": buy_count,
        "sell_count": sell_count,
    }