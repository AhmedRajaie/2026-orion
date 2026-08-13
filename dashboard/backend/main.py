import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
FEATURES_PATH = ROOT / "dashboard" / "data" / "features.json"
DAY3_EQUITY_PATHS = {
    "mlp": (ROOT / "dashboard" / "data" / "day3_mlp_equity.json", "Professor's MLP"),
    "lstm": (ROOT / "dashboard" / "data" / "day3_lstm_equity.json", "Professor's LSTM"),
    "equal_weight": (ROOT / "dashboard" / "data" / "day3_equal_weight_equity.json", "Equal-Weight Benchmark"),
    "my_mlp": (ROOT / "dashboard" / "data" / "day3_my_mlp_equity.json", "My MLP"),
    "my_lstm": (ROOT / "dashboard" / "data" / "day3_my_lstm_equity.json", "My LSTM"),
}
DAY3_START_CAPITAL = 1000.0
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

os.chdir(ROOT)
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_CHAT_MODEL = "gemini-flash-latest"
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

NEWS_CACHE_TTL = timedelta(minutes=15)
news_cache: dict[str, dict] = {}

from tradinglab.backtester import run_backtest
from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma
from tradinglab.metrics import max_drawdown, sharpe, total_return
from tradinglab.simulator import PortfolioSimulator
from tradinglab.strategies.sma import sma_crossover_weights
from tradinglab.strategies.scalping import ScalpingStrategy

app = FastAPI()


def round2(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return round(float(value), 2)


def round2_list(values):
    return [round2(v) for v in values]


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

feeds = {
    # NOTE: removed the duplicate "ABUK" entry that was here before
    "small": DataFeed.from_dir("data/egx", symbols=["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK"]),
    "full": DataFeed.from_dir("data/egx"),
}

# Factories, not shared instances: ScalpingStrategy is stateful (it remembers
# open trades between days), so every request needs its OWN fresh instance —
# reusing one across requests would leak yesterday's positions into today's.
STRATEGY_FACTORIES = {
    "sma": lambda: (sma_crossover_weights, "SMA 9/20 crossover"),
    "scalping": lambda: (ScalpingStrategy(), "Scalping (dip entry, profit target / stop-loss)"),
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/features")
def get_features():
    if not FEATURES_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Features file not found: {FEATURES_PATH}")

    with FEATURES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/universe")
def get_universe(universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")
    return feeds[universe].symbols


@app.get("/prices/{symbol}")
def get_prices(symbol: str, universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    idx = feed.symbols.index(symbol)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": round2_list(feed.close[:, idx].tolist()),
    }


@app.get("/indicators/{symbol}")
def get_indicators(symbol: str, window: int = 20, universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    idx = feed.symbols.index(symbol)
    close_prices = feed.close[:, idx]
    sma_values = sma(close_prices, window)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "sma": [None if pd.isna(v) else round2(v) for v in sma_values.tolist()],
    }


@app.get("/backtest")
def get_backtest(universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    simulator = PortfolioSimulator(feeds[universe])
    result = run_backtest(simulator, sma_crossover_weights, lookback=30)
    return {
        "portfolio": round2_list(result["portfolio"]),
        "benchmark": round2_list(result["benchmark"]),
    }


@app.get("/metrics")
def get_metrics(universe: str = "small"):
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    simulator = PortfolioSimulator(feeds[universe])
    result = run_backtest(simulator, sma_crossover_weights, lookback=30)
    portfolio_returns = result["portfolio_returns"]

    return {
        "total_return": round2(total_return(portfolio_returns)),
        "sharpe": round2(sharpe(portfolio_returns)),
        "max_drawdown": round2(max_drawdown(portfolio_returns)),
    }


@app.get("/strategy/{symbol}")
def get_strategy(symbol: str, universe: str = "small", cash: float = 1000.0):
    """Reproduce the notebook MA9/MA20 crossover backtest using the shared feed."""
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    idx = feed.symbols.index(symbol)
    close_series = pd.Series(feed.close[:, idx], index=feed.dates)
    ma9 = close_series.rolling(9).mean()
    ma20 = close_series.rolling(20).mean()

    starting_cash = float(cash)
    cash = starting_cash
    shares = 0.0
    buy_count = 0
    sell_count = 0
    buy_markers = [None] * len(close_series)
    sell_markers = [None] * len(close_series)
    trade_log = []
    portfolio_values = []
    portfolio_dates = []

    for i, price in enumerate(close_series):
        ma9_val = ma9.iloc[i]
        ma20_val = ma20.iloc[i]
        prev_ma9_val = ma9.iloc[i - 1] if i > 0 else None
        prev_ma20_val = ma20.iloc[i - 1] if i > 0 else None

        if pd.isna(ma9_val) or pd.isna(ma20_val):
            continue

        if shares == 0:
            if (
                prev_ma9_val is not None
                and prev_ma20_val is not None
                and not pd.isna(prev_ma9_val)
                and not pd.isna(prev_ma20_val)
                and prev_ma9_val <= prev_ma20_val
                and ma9_val > ma20_val
            ):
                shares = cash / float(price)
                cash = 0.0
                buy_count += 1
                buy_markers[i] = float(price)
                portfolio_value = cash + (shares * float(price))
                trade_log.append({
                    "date": feed.dates[i].strftime("%Y-%m-%d"),
                    "action": "buy",
                    "price": float(price),
                    "shares": float(shares),
                    "portfolio_value": float(portfolio_value),
                })
        elif shares > 0:
            if (
                prev_ma9_val is not None
                and prev_ma20_val is not None
                and not pd.isna(prev_ma9_val)
                and not pd.isna(prev_ma20_val)
                and prev_ma9_val >= prev_ma20_val
                and ma9_val < ma20_val
            ):
                trade_shares = float(shares)
                cash = shares * float(price)
                shares = 0.0
                sell_count += 1
                sell_markers[i] = float(price)
                portfolio_value = cash + (shares * float(price))
                trade_log.append({
                    "date": feed.dates[i].strftime("%Y-%m-%d"),
                    "action": "sell",
                    "price": float(price),
                    "shares": trade_shares,
                    "portfolio_value": float(portfolio_value),
                })

        portfolio_value = cash + (shares * float(price))
        portfolio_values.append(portfolio_value)
        portfolio_dates.append(feed.dates[i])

    if portfolio_values:
        portfolio_series = pd.Series(portfolio_values)
        running_max = portfolio_series.cummax()
        drawdown = (portfolio_series - running_max) / running_max
        max_drawdown_pct = float(drawdown.min() * 100)
        final_value = float(portfolio_series.iloc[-1])
        drawdown_series = [
            {
                "date": portfolio_dates[i].strftime("%Y-%m-%d"),
                "drawdown_pct": round2(float(drawdown.iloc[i] * 100)),
            }
            for i in range(len(portfolio_values))
        ]
    else:
        max_drawdown_pct = 0.0
        final_value = cash
        drawdown_series = []

    current_shares = float(shares) if shares > 0 else 0.0
    open_position = current_shares > 0
    pnl = final_value - starting_cash
    return_pct = (pnl / starting_cash * 100) if starting_cash != 0 else 0.0

    stats = {
        "final_value": round2(final_value),
        "buy_count": int(buy_count),
        "sell_count": int(sell_count),
        "max_drawdown_pct": round2(max_drawdown_pct),
    }

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": round2_list(close_series.tolist()),
        "ma9": [None if pd.isna(v) else round2(v) for v in ma9.tolist()],
        "ma20": [None if pd.isna(v) else round2(v) for v in ma20.tolist()],
        "buy_markers": buy_markers,
        "sell_markers": sell_markers,
        "trade_log": trade_log,
        "stats": stats,
        "pnl": round2(pnl),
        "return_pct": round2(return_pct),
        "open_position": open_position,
        "current_shares": round2(current_shares),
        "drawdown_series": drawdown_series,
    }


@app.get("/strategies")
def get_strategies(universe: str = "small"):
    """Base strategy (SMA9/20) and new strategy (scalping) backtested together,
    for the Strategy Performance comparison panel: one equity curve + three
    metrics per strategy, all from the same run_backtest/metrics functions
    every other endpoint here uses."""
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {universe}")

    feed = feeds[universe]
    dates = None
    benchmark = None
    strategies = {}

    for key, factory in STRATEGY_FACTORIES.items():
        strategy_fn, _ = factory()
        simulator = PortfolioSimulator(feed)
        result = run_backtest(simulator, strategy_fn, lookback=30)

        if dates is None:
            dates = [d.strftime("%Y-%m-%d") for d in result["dates"]]
            benchmark = round2_list(result["benchmark"])

        portfolio_returns = result["portfolio_returns"]
        strategies[key] = {
            "portfolio": round2_list(result["portfolio"]),
            "total_return": round2(total_return(portfolio_returns)),
            "sharpe": round2(sharpe(portfolio_returns)),
            "max_drawdown": round2(max_drawdown(portfolio_returns)),
        }

    return {"dates": dates, "benchmark": benchmark, **strategies}


@app.get("/day3-comparison")
def get_day3_comparison():
    """Week 2 Day 3 -- five full-universe strategies (result_mlp, result_lstm,
    result_equal_weight, result_my_mlp, result_my_lstm) backtested on the same
    test period, read from the equity curves the notebook writes to
    dashboard/data/. Ranked by final EGP, same math as the notebook's own
    ranking cell: portfolio[-1] * start_capital."""
    dates = None
    benchmark = None
    strategies = {}
    ranking = []

    for key, (path, label) in DAY3_EQUITY_PATHS.items():
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Equity file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            curve = json.load(handle)

        if dates is None:
            dates = curve["dates"]
            benchmark = round2_list(curve["benchmark"])

        portfolio = round2_list(curve["portfolio"])
        strategies[key] = {"label": label, "portfolio": portfolio}

        final_value = round2(curve["portfolio"][-1] * DAY3_START_CAPITAL)
        benchmark_final = round2(curve["benchmark"][-1] * DAY3_START_CAPITAL)
        ranking.append({
            "key": key,
            "label": label,
            "final_value": final_value,
            "beat_benchmark": final_value > benchmark_final,
        })

    ranking.sort(key=lambda row: row["final_value"], reverse=True)

    return {
        "dates": dates,
        "benchmark": benchmark,
        "strategies": strategies,
        "ranking": ranking,
    }


class ChatRequest(BaseModel):
    question: str
    symbol: Optional[str] = None
    universe: str = "small"


def build_dashboard_context(symbol: Optional[str], universe: str) -> dict:
    """Gathers real, currently-available dashboard data by calling the same
    functions the /strategy, /strategies, and /day3-comparison endpoints use,
    so the chat model is grounded in numbers that actually exist."""
    if universe not in feeds:
        universe = "small"

    context: dict = {
        "universe": universe,
        "available_symbols": feeds[universe].symbols,
    }

    if symbol and symbol in feeds[universe].symbols:
        strategy = get_strategy(symbol, universe=universe)
        context["selected_symbol"] = symbol
        context["selected_symbol_strategy"] = {
            "latest_date": strategy["dates"][-1] if strategy["dates"] else None,
            "latest_close_price": strategy["close"][-1] if strategy["close"] else None,
            "final_value": strategy["stats"]["final_value"],
            "buy_count": strategy["stats"]["buy_count"],
            "sell_count": strategy["stats"]["sell_count"],
            "max_drawdown_pct": strategy["stats"]["max_drawdown_pct"],
            "pnl": strategy["pnl"],
            "return_pct": strategy["return_pct"],
            "open_position": strategy["open_position"],
            "current_shares": strategy["current_shares"],
        }

    strategies_perf = get_strategies(universe=universe)
    context["strategy_comparison"] = {
        key: {
            "total_return": value["total_return"],
            "sharpe": value["sharpe"],
            "max_drawdown": value["max_drawdown"],
        }
        for key, value in strategies_perf.items()
        if key not in ("dates", "benchmark")
    }

    day3 = get_day3_comparison()
    context["day3_strategy_ranking"] = day3["ranking"]

    now = datetime.utcnow()
    fresh_news = {
        sym: {"sentiment": entry["sentiment"], "summary": entry["summary"]}
        for sym, entry in news_cache.items()
        if now - entry["cached_at"] < NEWS_CACHE_TTL
    }
    context["news_sentiment"] = fresh_news if fresh_news else "No news sentiment has been fetched for any symbol yet."

    return context


@app.post("/chat")
def chat(payload: ChatRequest):
    if gemini_client is None:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured on the server.")

    context = build_dashboard_context(payload.symbol, payload.universe)

    prompt = (
        "You are a read-only assistant embedded in a trading dashboard. Answer the user's "
        "question using ONLY the JSON data below, which reflects what is currently loaded in "
        "the dashboard. Never invent, estimate, or infer any number that is not present in this "
        "data. If the question cannot be answered from this data, say so plainly and briefly "
        "explain what the user would need to select or load to get that answer. Keep answers to "
        "1-3 sentences.\n\n"
        f"DASHBOARD DATA:\n{json.dumps(context, default=str)}\n\n"
        f"QUESTION: {payload.question}"
    )

    try:
        response = gemini_client.models.generate_content(model=GEMINI_CHAT_MODEL, contents=prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chat model request failed: {exc}")

    return {"answer": response.text}