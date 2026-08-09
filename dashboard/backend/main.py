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
from tradinglab.simulator import PortfolioSimulator
from tradinglab.backtester import run_backtest
from tradinglab.strategies.sma import sma_crossover_weights
from tradinglab.metrics import total_return, max_drawdown
from .strategy_new import run_universe_weekly_threshold  # if this errors, try: from dashboard.backend.strategy_new import run_universe_weekly_threshold

COMPARISON_UNIVERSE = ['COMI', 'HRHO', 'TMGH', 'SWDY', 'FWRY', 'ABUK']
COMPARISON_CAPITAL = 1000.0
@app.get("/strategy-comparison")
def get_strategy_comparison():
    comp_feed = DataFeed.from_dir(str(REPO_ROOT / "data" / "egx"), symbols=COMPARISON_UNIVERSE)
    sim = PortfolioSimulator(comp_feed, commission=0.005)
    base_result = run_backtest(sim, lambda o: sma_crossover_weights(o, 9, 20), lookback=30)

    base_dates = [str(d)[:10] for d in base_result["dates"]]
    base_equity = (base_result["portfolio"] * COMPARISON_CAPITAL).tolist()

    per_stock_seed = COMPARISON_CAPITAL / len(COMPARISON_UNIVERSE)
    new_portfolio_equity = run_universe_weekly_threshold(
        COMPARISON_UNIVERSE, str(REPO_ROOT / "data" / "egx"), per_stock_seed,
        min_date=base_dates[0], max_date=base_dates[-1]
    )
    new_returns = new_portfolio_equity.pct_change().dropna()

    return {
        "universe": COMPARISON_UNIVERSE,
        "base": {
            "name": "SMA 9/20 Crossover (Notebook 4)",
            "dates": base_dates,
            "equity": base_equity,
            "total_return_pct": total_return(base_result["portfolio_returns"]) * 100,
            "max_drawdown_pct": max_drawdown(base_result["portfolio_returns"]) * 100,
            "final_value": base_equity[-1],
        },
        "new": {
            "name": "Weekly Threshold (-5% buy $5 / +10% sell $10)",
            "dates": [str(d)[:10] for d in new_portfolio_equity.index],
            "equity": new_portfolio_equity.tolist(),
            "total_return_pct": total_return(new_returns) * 100,
            "max_drawdown_pct": max_drawdown(new_returns) * 100,
            "final_value": float(new_portfolio_equity.iloc[-1]),
        },
    }