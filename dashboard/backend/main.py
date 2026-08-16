"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
import os
import json
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
load_dotenv()

import httpx
import xml.etree.ElementTree as ET
import anthropic
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


from tradinglab.data_feed import DataFeed


def find_repo_root():
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "data" / "egx").exists():
            return parent
    raise FileNotFoundError("Couldn't find repo root containing 'data/egx/'")


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
from .strategy_new import run_universe_weekly_threshold

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


@app.get("/compare")
def get_compare():
    path = REPO_ROOT / "dashboard" / "data" / "model_compare.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="model_compare.json not found — run the Day 3 notebook first")
    return json.loads(path.read_text())


@app.get("/leaderboard")
def get_leaderboard():
    path = REPO_ROOT / "dashboard" / "data" / "leaderboard.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="leaderboard.json not found — run the Day 5 notebook first")
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Day 4 — chat agent + news sentiment
# ---------------------------------------------------------------------------

def get_anthropic_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set — check your .env file")
    return anthropic.Anthropic(api_key=api_key)


def build_dashboard_context(symbol: str | None = None) -> str:
    lines = [f"Universe of stocks tracked: {', '.join(feed.symbols)}"]

    if symbol and symbol in feed.symbols:
        bt = get_backtest(symbol)
        lines.append(
            f"Currently selected stock: {symbol}. MA9/MA20 crossover backtest — "
            f"total return {bt['total_return_pct']:.2f}%, max drawdown {bt['max_drawdown_pct']:.2f}%, "
            f"final value {bt['final_value']:.2f} EGP, {bt['buy_count']} buys / {bt['sell_count']} sells."
        )

    try:
        comp = get_strategy_comparison()
        lines.append(
            f"Strategy comparison (universe {', '.join(comp['universe'])}): "
            f"base SMA crossover total return {comp['base']['total_return_pct']:.2f}% "
            f"(max drawdown {comp['base']['max_drawdown_pct']:.2f}%); "
            f"new weekly-threshold strategy total return {comp['new']['total_return_pct']:.2f}% "
            f"(max drawdown {comp['new']['max_drawdown_pct']:.2f}%)."
        )
    except Exception:
        pass

    compare_path = REPO_ROOT / "dashboard" / "data" / "model_compare.json"
    if compare_path.exists():
        try:
            mc = json.loads(compare_path.read_text())
            lines.append(
                f"Model comparison — MLP test loss {mc['mlp_test_loss']:.6f} (IC {mc['mlp_ic']:+.3f}), "
                f"final backtest value {mc['mlp_final_value']:.2f} EGP; "
                f"LSTM test loss {mc['lstm_test_loss']:.6f} (IC {mc['lstm_ic']:+.3f}), "
                f"final backtest value {mc['lstm_final_value']:.2f} EGP; "
                f"benchmark final value {mc['benchmark_final_value']:.2f} EGP."
            )
        except Exception:
            pass

    leaderboard_path = REPO_ROOT / "dashboard" / "data" / "leaderboard.json"
    if leaderboard_path.exists():
        try:
            lb = json.loads(leaderboard_path.read_text())
            risk = lb.get("risk", {})
            parts = []
            for name in ("sma", "mpt", "benchmark"):
                if name in risk:
                    r = risk[name]
                    parts.append(
                        f"{name}: return {r['total_return_pct']:+.2f}%, "
                        f"volatility {r['volatility_pct']:.2f}%, "
                        f"max drawdown {r['max_drawdown_pct']:.2f}%, "
                        f"final value {r['final_value']:.2f} EGP"
                    )
            if parts:
                lines.append("Leaderboard (walk-forward test period) — " + "; ".join(parts) + ".")
        except Exception:
            pass

    return "\n".join(lines)


class ChatRequest(BaseModel):
    message: str
    symbol: str | None = None


@app.post("/chat")
def chat(req: ChatRequest):
    client = get_anthropic_client()
    context = build_dashboard_context(req.symbol)

    system_prompt = (
        "You are a helpful assistant embedded in a trading strategy dashboard. "
        "Answer questions using ONLY the dashboard data given below. "
        "If something isn't covered by this data, say so plainly rather than guessing. "
        "Keep answers concise (2-4 sentences). Describe what the backtested data shows — "
        "never recommend buying or selling anything.\n\n"
        f"Current dashboard data:\n{context}"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": req.message}],
        )
        reply = "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")

    return {"reply": reply}


@app.get("/news/{symbol}")
def get_news(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")

    query = quote(f"{symbol} EGX Egypt stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        headlines = [item.find("title").text for item in root.findall(".//item")[:8] if item.find("title") is not None]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Couldn't fetch news: {e}")

    if not headlines:
        return {"symbol": symbol, "headlines": [], "summary": "No recent news found for this symbol."}

    client = get_anthropic_client()
    headline_block = "\n".join(f"- {h}" for h in headlines)
    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            system=(
                "You summarize stock news headlines into a brief sentiment readout. "
                "State whether the tone is bullish, bearish, or mixed/neutral, and why, "
                "in 2-3 sentences. Do not give investment advice."
            ),
            messages=[{"role": "user", "content": f"Headlines for {symbol}:\n{headline_block}"}],
        )
        summary = "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary failed: {e}")

    return {"symbol": symbol, "headlines": headlines, "summary": summary}