"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""

import os
import numpy as np
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from tradinglab.backtester import run_backtest
from tradinglab.data_feed import DataFeed
from tradinglab.indicators import sma
from tradinglab.metrics import max_drawdown, total_return
from tradinglab.simulator import PortfolioSimulator
from tradinglab.strategies.lstm import make_lstm_strategy, train_lstm_ensemble
from tradinglab.strategies.mpt import mpt_window_strategy
from tradinglab.strategies.nn import make_nn_strategy
from tradinglab.strategies.sma import sma_crossover_weights

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

CONFIG = {
    "openai": {
        "api_key": OPENAI_API_KEY,
        "base_url": None,
        "model": "gpt-5-mini",
    },
    "anthropic": {
        "api_key": ANTHROPIC_API_KEY,
        "base_url": "https://api.anthropic.com/v1/",
        "model": "claude-sonnet-5",
    },
    "gemini": {
        "api_key": GEMINI_API_KEY,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-flash-latest",
    },
    "mock": {"api_key": None, "base_url": None, "model": "gpt-5-mini"},
}


def _active_llm_provider() -> str:
    """Use the provider selected in .env, or a configured provider if omitted."""
    requested = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if requested:
        return requested
    return next(
        (name for name in ("gemini", "anthropic", "openai") if CONFIG[name]["api_key"]),
        "mock",
    )


def _fallback_llm_providers(primary: str) -> list[str]:
    """Configured alternatives, used only after a provider reports quota exhaustion."""
    return [
        name for name in ("anthropic", "openai", "gemini")
        if name != primary and CONFIG[name]["api_key"]
    ]


def _is_quota_error(error: Exception) -> bool:
    message = str(error).lower()
    return "429" in message or "quota" in message or "resource_exhausted" in message

app = FastAPI(title="Younit-style trading dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data/egx")
feed = DataFeed.from_dir(DATA_DIR)

def make_tiktok_guru_strategy(week_days=5, sensitivity=1.0):
    """Weekly contrarian strategy using the same TradingLab simulator."""
    state = {"weights": None, "day_count": 0}

    def strategy(observation):
        n_assets = observation.shape[0]
        current = state["weights"]
        if current is None:
            current = np.ones(n_assets, dtype=float) / n_assets
            state["weights"] = current

        if state["day_count"] % week_days == 0:
            weekly_returns = observation[:, -week_days:, 0]
            return_nd = np.prod(1.0 + weekly_returns, axis=1) - 1.0
            new_weights = current * (1.0 - sensitivity * return_nd)
            new_weights = np.clip(new_weights, 0.0, None)
            total = new_weights.sum()
            current = (np.ones(n_assets) / n_assets if total <= 0
                       else new_weights / total)
            state["weights"] = current

        state["day_count"] += 1
        return state["weights"]

    return strategy


# Cache trained NN model components per symbol (training takes a few seconds)
_nn_model_cache: dict[str, tuple] = {}


def _get_nn_strategy(symbol: str):
    """Return a FRESH NN strategy closure for a single-symbol feed.

    The trained ensemble models and standardization statistics are cached per
    symbol; the closure itself (with its day counter) is recreated on every
    call so backtests always start from day 0.
    """
    if symbol not in _nn_model_cache:
        from tradinglab.strategies.nn import train_nn_ensemble

        single_feed = DataFeed.from_dir(DATA_DIR, symbols=[symbol])
        models, mu, sigma = train_nn_ensemble(single_feed, asset=0)
        _nn_model_cache[symbol] = (models, mu, sigma)

    models, mu, sigma = _nn_model_cache[symbol]
    single_feed = DataFeed.from_dir(DATA_DIR, symbols=[symbol])
    return make_nn_strategy(single_feed, asset=0, models=models, mu=mu, sigma=sigma)


# Cache trained LSTM model components per symbol (training takes a few seconds)
_lstm_model_cache: dict[str, tuple] = {}


def _get_lstm_strategy(symbol: str):
    """Return a FRESH LSTM strategy closure for a single-symbol feed."""
    if symbol not in _lstm_model_cache:
        single_feed = DataFeed.from_dir(DATA_DIR, symbols=[symbol])
        models, train_mean, train_std = train_lstm_ensemble(single_feed, asset=0)
        _lstm_model_cache[symbol] = (models, train_mean, train_std)

    models, train_mean, train_std = _lstm_model_cache[symbol]
    single_feed = DataFeed.from_dir(DATA_DIR, symbols=[symbol])
    return make_lstm_strategy(single_feed, asset=0, models=models, train_mean=train_mean, train_std=train_std)


def _build_strategies(symbol: str):
    """Build the strategy list for a symbol or ALL comparison.

    For the ALL case, we still include the NN and LSTM models by using the first
    symbol in the universe as the model's training proxy. This keeps those
    strategies visible in the portfolio view without breaking the full-universe
    backtest logic.
    """
    model_symbol = symbol if symbol != "ALL" else (feed.symbols[0] if feed.symbols else symbol)

    strategies = [
        ("SMA crossover", lambda obs: sma_crossover_weights(obs, 9, 20)),
        ("MPT window", mpt_window_strategy),
        ("TikTok contrarian", make_tiktok_guru_strategy(week_days=5)),
        ("NN 5-day", _get_nn_strategy(model_symbol)),
        ("LSTM 1-day", _get_lstm_strategy(model_symbol)),
    ]

    return strategies


class ChatRequest(BaseModel):
    symbol: Optional[str] = None
    question: Optional[str] = None
    messages: list[dict[str, str]] = Field(default_factory=list)


class DebateRequest(BaseModel):
    symbol: Optional[str] = None
    headlines: list[str] = Field(default_factory=list)


def _load_symbol_ohlcv(symbol: str) -> dict[str, float | int | None]:
    csv_file = DATA_DIR / f"{symbol}.csv"
    if not csv_file.exists():
        return {}

    import pandas as pd

    df = pd.read_csv(csv_file, parse_dates=["date"]).set_index("date").sort_index()
    date = feed.dates[-1]
    if date not in df.index:
        df = df.reindex(feed.dates).ffill()

    row = df.loc[date]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]

    return {
        "date": date.strftime("%Y-%m-%d"),
        "open": float(row.get("open", float("nan"))) if "open" in row.index else None,
        "high": float(row.get("high", float("nan"))) if "high" in row.index else None,
        "low": float(row.get("low", float("nan"))) if "low" in row.index else None,
        "close": float(row.get("adj_close", row.get("close", float("nan")))) if "adj_close" in row.index or "close" in row.index else None,
        "volume": int(row.get("volume", 0)) if "volume" in row.index else None,
    }


def _symbol_metrics(symbol: str) -> dict[str, float | str]:
    idx = feed.symbols.index(symbol)
    closes = feed.close[:, idx]
    latest = float(closes[-1])
    previous = float(closes[-2])
    daily_change = ((latest - previous) / previous) * 100
    total_ret = (latest / float(closes[0]) - 1) * 100
    drawdown = max_drawdown(feed.returns[:, idx]) * 100

    sma9_series = sma(closes, 9)
    sma20_series = sma(closes, 20)
    latest_sma9 = float(sma9_series[-1])
    latest_sma20 = float(sma20_series[-1])
    trend = "Bullish" if latest_sma9 > latest_sma20 else "Bearish"

    signal = "Hold"
    if len(sma9_series) >= 2 and len(sma20_series) >= 2:
        prev_sma9 = sma9_series[-2]
        prev_sma20 = sma20_series[-2]
        if prev_sma9 <= prev_sma20 and latest_sma9 > latest_sma20:
            signal = "BUY"
        elif prev_sma9 >= prev_sma20 and latest_sma9 < latest_sma20:
            signal = "SELL"

    return {
        "symbol": symbol,
        "latest_price": latest,
        "daily_change_pct": daily_change,
        "total_return_pct": total_ret,
        "max_drawdown_pct": drawdown,
        "sma9": latest_sma9,
        "sma20": latest_sma20,
        "trend": trend,
        "signal": signal,
    }


def _format_stock_context(symbol: str) -> str:
    metrics = _symbol_metrics(symbol)
    ohlcv = _load_symbol_ohlcv(symbol)
    lines = [
        f"Selected symbol: {symbol}",
        f"Date: {ohlcv.get('date', feed.dates[-1].strftime('%Y-%m-%d'))}",
        f"Latest price: {metrics['latest_price']:.2f}",
        f"Daily change: {metrics['daily_change_pct']:.2f}%",
        f"Total return: {metrics['total_return_pct']:.2f}%",
        f"Max drawdown: {metrics['max_drawdown_pct']:.2f}%",
        f"SMA9: {metrics['sma9']:.2f}",
        f"SMA20: {metrics['sma20']:.2f}",
        f"Trend: {metrics['trend']}",
        f"Signal: {metrics['signal']}",
    ]

    if ohlcv.get("open") is not None:
        lines.append(f"Open: {ohlcv['open']:.2f}")
    if ohlcv.get("high") is not None:
        lines.append(f"High: {ohlcv['high']:.2f}")
    if ohlcv.get("low") is not None:
        lines.append(f"Low: {ohlcv['low']:.2f}")
    if ohlcv.get("volume") is not None:
        lines.append(f"Volume: {ohlcv['volume']:,}")

    lines.append("Use these facts to answer follow-up questions about trend, drawdown, SMA, and benchmark performance.")
    return "\n".join(lines)


def _market_rows() -> list[dict[str, float | str]]:
    """Return the same ranking data shown by the Market Intelligence panel."""
    rows = []
    for symbol in feed.symbols:
        metrics = _symbol_metrics(symbol)
        score = (
            metrics["total_return_pct"]
            - 0.5 * abs(metrics["max_drawdown_pct"])
            + 0.25 * metrics["daily_change_pct"]
            + (5.0 if metrics["trend"] == "Bullish" else 0.0)
        )
        rows.append({**metrics, "score": score})
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def _strategy_comparison_results(symbol: str) -> dict[str, object]:
    """Run all strategies on a single-symbol feed and return comparison data.

    If symbol == "ALL", run on the full universe feed (all symbols).
    """
    if symbol == "ALL":
        single_feed = feed
        display = "ALL"
    else:
        single_feed = DataFeed.from_dir(DATA_DIR, symbols=[symbol])
        display = symbol

    sim = PortfolioSimulator(single_feed)
    results = []

    for name, strat in _build_strategies(display):
        backtest = run_backtest(sim, strat, lookback=30)
        final_portfolio = float(backtest["portfolio"][-1])
        final_benchmark = float(backtest["benchmark"][-1])
        trades = int((abs(backtest["weights"][1:] - backtest["weights"][:-1]).sum(axis=1) > 1e-6).sum())
        strategy_result = {
            "name": name,
            "dates": [d.strftime("%Y-%m-%d") for d in backtest["dates"]],
            "portfolio": backtest["portfolio"].tolist(),
            "benchmark": backtest["benchmark"].tolist(),
            "final_portfolio": final_portfolio,
            "final_benchmark": final_benchmark,
            "total_return_pct": total_return(backtest["portfolio_returns"]) * 100,
            "benchmark_return_pct": total_return(backtest["benchmark_returns"]) * 100,
            "max_drawdown_pct": max_drawdown(backtest["portfolio_returns"]) * 100,
            "num_trades": trades,
            "beat_benchmark": final_portfolio > final_benchmark,
        }
        results.append(strategy_result)

    return {
        "dates": results[0]["dates"] if results else [],
        "strategies": results,
        "benchmark_name": f"Equal-weight benchmark ({display})",
        "symbol": display,
    }


@lru_cache(maxsize=64)
def _get_strategy_comparison(symbol: str) -> dict[str, object]:
    return _strategy_comparison_results(symbol)


def _format_dashboard_chat_context(symbol: str, include_strategies: bool = False) -> str:
    """Ground every chat response in fresh dashboard facts instead of static prompts."""
    selected = _format_stock_context(symbol)
    top_stocks = _market_rows()[:5]
    ranking = "\n".join(
        f"{rank}. {row['symbol']}: score {row['score']:.2f}, return {row['total_return_pct']:.2f}%, "
        f"drawdown {row['max_drawdown_pct']:.2f}%, {row['trend']}"
        for rank, row in enumerate(top_stocks, start=1)
    )
    context = (
        f"SELECTED STOCK\n{selected}\n\n"
        f"TOP MARKET RANKING\n{ranking}"
    )
    if not include_strategies:
        return context

    strategies = _get_strategy_comparison(symbol)["strategies"]
    strategy_summary = "\n".join(
        f"- {item['name']}: return {item['total_return_pct']:.2f}%, "
        f"benchmark {item['benchmark_return_pct']:.2f}%, drawdown {item['max_drawdown_pct']:.2f}%, "
        f"trades {item['num_trades']}"
        for item in strategies
    )
    return f"{context}\n\nSTRATEGY RESULTS FOR {symbol}\n{strategy_summary}"


def _mock_llm_response(messages: list[dict[str, str]], system: str, symbol: str) -> str:
    metrics = _symbol_metrics(symbol)
    strategies = _get_strategy_comparison(symbol)["strategies"]
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    text = last_user.lower()

    def fmt_pct(value: float) -> str:
        return f"{value:.2f}%"

    if any(keyword in text for keyword in ["analyze this stock", "analyze", "tell me about", "overview"]):
        return (
            f"{symbol} is currently {metrics['trend'].lower()} with a latest price of {metrics['latest_price']:.2f}. "
            f"The daily change is {fmt_pct(metrics['daily_change_pct'])}, total return is {fmt_pct(metrics['total_return_pct'])}, "
            f"and the current signal is {metrics['signal']}. SMA9 is {metrics['sma9']:.2f} and SMA20 is {metrics['sma20']:.2f}."
        )

    if "drawdown" in text:
        return (
            f"The maximum drawdown for {symbol} is {fmt_pct(metrics['max_drawdown_pct'])}. "
            f"That measures the largest percentage drop from a peak to a trough over the sample."
        )

    if "sma9" in text or "sma 9" in text or "sma20" in text or "sma 20" in text:
        direction = "above" if metrics['sma9'] > metrics['sma20'] else "below"
        return (
            f"SMA9 is currently {metrics['sma9']:.2f} and SMA20 is {metrics['sma20']:.2f}. "
            f"That means SMA9 is {direction} SMA20, which indicates a {metrics['trend'].lower()} trend. "
            f"The signal is {metrics['signal']} based on the crossover."
        )

    if "why" in text or "bearish" in text or "bullish" in text:
        return (
            f"The stock is {metrics['trend'].lower()} because SMA9 is {metrics['sma9']:.2f} and SMA20 is {metrics['sma20']:.2f}. "
            f"The most recent daily move was {fmt_pct(metrics['daily_change_pct'])}, and the current rule says {metrics['signal']}."
        )

    if "compare" in text and "abuk" in text:
        other = _symbol_metrics("ABUK")
        return (
            f"Compared to ABUK, {symbol} has a latest price of {metrics['latest_price']:.2f} versus {other['latest_price']:.2f}. "
            f"{symbol} has total return {fmt_pct(metrics['total_return_pct'])} and ABUK has {fmt_pct(other['total_return_pct'])}. "
            f"{symbol} is {metrics['trend'].lower()} while ABUK is {other['trend'].lower()}."
        )

    if any(keyword in text for keyword in ["strategy", "best", "benchmark", "compare all"]):
        best = max(strategies, key=lambda s: s["final_portfolio"])
        if "lowest drawdown" in text:
            lowest = min(strategies, key=lambda s: s["max_drawdown_pct"])
            return (
                f"The strategy with the lowest drawdown is {lowest['name']} at {fmt_pct(lowest['max_drawdown_pct'])}. "
                f"It achieved a total return of {fmt_pct(lowest['total_return_pct'])}."
            )
        if "did" in text and "beat" in text:
            beats = [s for s in strategies if s["beat_benchmark"]]
            if not beats:
                return "None of the strategies beat the benchmark in the current universe."
            beat_names = ", ".join([s["name"] for s in beats])
            return f"The strategies that beat the benchmark are: {beat_names}."
        return (
            f"The best performing strategy is {best['name']} with a final portfolio value of {best['final_portfolio']:.2f}. "
            f"It beat the benchmark by {fmt_pct(best['total_return_pct'] - best['benchmark_return_pct'])}."
        )

    return (
        f"For {symbol}, the latest price is {metrics['latest_price']:.2f}, the daily change is {fmt_pct(metrics['daily_change_pct'])}, "
        f"and the current signal is {metrics['signal']}. Ask me for drawdown, SMA, trend, benchmark comparison, or strategy performance."
    )


def _clean_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep only fields accepted by chat-completions APIs and a short history."""
    cleaned = []
    for message in messages[-12:]:
        role, content = message.get("role"), message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            cleaned.append({"role": role, "content": content.strip()})
    return cleaned


def _llm_chat(messages, system=None, provider=None, max_tokens=400, symbol=None):
    provider = provider or _active_llm_provider()
    if provider == "mock":
        if not messages:
            return "No chat history provided."
        selected_symbol = symbol or feed.symbols[0]
        return _mock_llm_response(messages, system or "", selected_symbol)

    cfg = CONFIG.get(provider)
    if not cfg or not cfg["api_key"]:
        raise RuntimeError(f"LLM provider '{provider}' is not configured correctly.")

    from openai import OpenAI

    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"]) if cfg["base_url"] else OpenAI(api_key=cfg["api_key"])
    full_messages = ([{"role": "system", "content": system}] if system else []) + messages
    resp = client.chat.completions.create(
        model=cfg["model"], messages=full_messages, max_tokens=max_tokens, temperature=0.35
    )
    return resp.choices[0].message.content


@app.post("/chat")
def chat(request: ChatRequest):
    if request.symbol and request.symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")

    symbol = request.symbol or feed.symbols[0]
    question = request.question or ""
    strategy_terms = ("strategy", "strategies", "benchmark", "backtest", "drawdown", "trades")
    dashboard_context = _format_dashboard_chat_context(
        symbol,
        include_strategies=any(term in question.lower() for term in strategy_terms),
    )

    system_prompt = (
        "You are a helpful stock assistant for the Egyptian equities dashboard. "
        "Use only the live dashboard facts supplied in the current user message. "
        "Answer the specific question directly, cite the relevant figures, and distinguish facts from inference. "
        "If the data cannot answer the question, say so. This is educational information, not financial advice."
    )

    messages = _clean_messages(request.messages)
    if request.question:
        messages.append(
            {
                "role": "user",
                "content": f"{dashboard_context}\n\nUSER QUESTION\n{request.question}",
            }
        )

    if not messages:
        raise HTTPException(status_code=400, detail="question or messages required")

    try:
        answer = _llm_chat(messages, system=system_prompt, symbol=request.symbol)
        return {"answer": answer, "provider": _active_llm_provider()}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM request failed: {exc}")


@app.post("/investment-debate")
def investment_debate(request: DebateRequest):
    """Run a quota-efficient bull/bear/judge workflow from the debate notebook."""
    symbol = request.symbol or feed.symbols[0]
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")

    headlines = [headline.strip() for headline in request.headlines if headline.strip()][:12]
    if not headlines:
        raise HTTPException(status_code=400, detail="add at least one headline")

    headline_text = "\n".join(f"- {headline}" for headline in headlines)
    evidence = f"{_format_stock_context(symbol)}\n\nHeadlines supplied by the user:\n{headline_text}"
    debate_system = (
        "You are an Egyptian-equities investment committee simulating three viewpoints from the supplied "
        "dashboard facts and headlines only. Return exactly BULL:, BEAR:, and VERDICT: sections. "
        "Give 3-4 sentences for bull and bear, then a neutral 4-6 sentence verdict ending BUY, SELL, or HOLD. "
        "This is educational analysis, not financial advice."
    )

    try:
        provider = _active_llm_provider()
        if provider == "mock":
            metrics = _symbol_metrics(symbol)
            bull_case = (
                f"{symbol}'s {metrics['trend'].lower()} trend and {metrics['daily_change_pct']:.2f}% daily move can support a positive case. "
                "The supplied headlines may reinforce that view, but they require source verification."
            )
            bear_case = (
                f"{symbol}'s maximum drawdown of {metrics['max_drawdown_pct']:.2f}% highlights meaningful downside risk. "
                "The supplied headlines should not be treated as verified investment research."
            )
            verdict = "HOLD — review verified news and your own risk tolerance before making an investment decision."
        else:
            reply = _llm_chat(
                [{"role": "user", "content": evidence}],
                system=debate_system,
                provider=provider,
                max_tokens=700,
            )
            sections = {"BULL": "", "BEAR": "", "VERDICT": ""}
            current = None
            for line in reply.splitlines():
                heading = line.strip().rstrip(":").upper()
                if heading in sections:
                    current = heading
                elif current:
                    sections[current] += ("\n" if sections[current] else "") + line.strip()
            bull_case = sections["BULL"] or reply
            bear_case = sections["BEAR"] or "The model did not return a separate bear section."
            verdict = sections["VERDICT"] or "HOLD — review the available evidence carefully."
        return {"symbol": symbol, "bull_case": bull_case, "bear_case": bear_case, "verdict": verdict, "provider": provider}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        if _is_quota_error(exc):
            metrics = _symbol_metrics(symbol)
            return {
                "symbol": symbol,
                "bull_case": (
                    f"{symbol}'s {metrics['trend'].lower()} trend and {metrics['daily_change_pct']:.2f}% daily move support a positive technical case. "
                    "The supplied headline still needs verification."
                ),
                "bear_case": (
                    f"The maximum drawdown of {metrics['max_drawdown_pct']:.2f}% highlights meaningful downside risk. "
                    "Treat unverified headlines as context, not evidence."
                ),
                "verdict": "HOLD — the live provider quota is temporarily exhausted, so verify the headline and try again later.",
                "provider": "dashboard fallback (Gemini quota reached)",
            }
        raise HTTPException(status_code=500, detail=f"LLM debate failed: {exc}")


@app.get("/strategy-comparison")
def strategy_comparison(symbol: Optional[str] = Query(None)):
    """Compare strategies for a single symbol or ALL (defaults to the first symbol)."""
    if symbol is None:
        symbol = feed.symbols[0]
    if symbol != "ALL" and symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    return _get_strategy_comparison(symbol)


@app.get("/backtest")
def backtest(symbol: Optional[str] = Query(None)):
    """Backtest all strategies for a single symbol or ALL (defaults to the first symbol)."""
    if symbol is None:
        symbol = feed.symbols[0]
    if symbol != "ALL" and symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    return _get_strategy_comparison(symbol)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe():
    return feed.symbols


@app.get("/prices/{symbol}")
def prices(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")

    idx = feed.symbols.index(symbol)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "close": feed.close[:, idx].tolist(),
    }


@app.get("/indicators/{symbol}")
def indicators(symbol: str):
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")

    idx = feed.symbols.index(symbol)
    close = feed.close[:, idx]

    sma9 = sma(close, 9)
    sma20 = sma(close, 20)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],

        "sma9": [
            None if value != value else float(value)
            for value in sma9
        ],

        "sma20": [
            None if value != value else float(value)
            for value in sma20
        ],
    }


# TASK_02+ : add /backtest here.

@app.get("/market-overview")
def market_overview():
    """Rank the whole universe using return, risk and current trend."""
    rows = _market_rows()
    return {"count": len(rows), "stocks": rows}


@app.get("/compare")
def compare_stocks(symbols: str = Query(...)):
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="Provide at least one symbol")
    invalid = [s for s in requested if s not in feed.symbols]
    if invalid:
        raise HTTPException(status_code=404, detail=f"symbol not found: {', '.join(invalid)}")

    series = []
    for symbol in requested:
        idx = feed.symbols.index(symbol)
        series.append({
            "symbol": symbol,
            "values": feed.close[:, idx].tolist(),
        })

    return {
        "symbols": requested,
        "dates": [d.strftime("%Y-%m-%d") for d in feed.dates],
        "series": series,
        "stocks": [_symbol_metrics(s) for s in requested],
    }
