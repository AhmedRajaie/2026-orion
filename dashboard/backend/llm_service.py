"""News-sentiment and chat-agent services for the dashboard (Day 4 -- "give it
language"), layered on llm_client.chat(). Follows the two extras notebooks:
`extras/llm-news-sentiment.ipynb` (headline -> score/summary) and
`extras/rag-market-chat.ipynb` (answer grounded in a small notes corpus) --
extended so the chat agent is grounded in the LIVE dashboard state instead of
just static notes, per the Day 4 brief ("answer questions about what's on the
dashboard").
"""
from __future__ import annotations

import json
import re
from typing import Any

from .llm_client import DEFAULT_PROVIDER, chat

# Illustrative headlines -- NOT a real news feed (this project uses no external
# APIs). Mirrors extras/llm-news-sentiment.ipynb's own placeholder set, extended
# to a few more EGX symbols. Clearly labeled as sample data in every response.
SAMPLE_HEADLINES: dict[str, list[str]] = {
    "COMI": ["Bank posts record quarterly profit, beating analyst estimates", "Analysts raise price target on strong loan growth"],
    "HRHO": ["Firm faces regulatory review into lending practices", "Weak trading revenue reported for the quarter"],
    "SWDY": ["Wins large infrastructure contract abroad", "Expands into new regional market"],
    "ABUK": ["Fertilizer export volumes climb on strong demand", "Input costs pressure margins this quarter"],
    "TMGH": ["New residential project launch sees strong pre-sales", "Delivery timeline pushed back on one project"],
    "FWRY": ["Payment volumes grow as merchant network expands", "Increased competition in digital payments space"],
    "EFID": ["New product line drives revenue growth", "Raw material costs weigh on margins"],
    "EAST": ["Tobacco sales volumes hold steady", "Regulatory duties increase cost pressure"],
    "ETEL": ["Network rollout progresses ahead of schedule", "Subscriber growth slows in core segment"],
    "CIEB": ["Bank reports higher net interest income", "Loan-loss provisions tick up"],
    "ADIB": ["Islamic banking arm posts strong deposit growth", "Compliance costs rise industry-wide"],
    "ORAS": ["Construction backlog reaches a new high", "Project delays reported on one contract"],
    "PHDC": ["Real estate sales beat expectations", "Financing costs squeeze developer margins"],
}


def get_sample_headlines(symbol: str) -> list[str]:
    return SAMPLE_HEADLINES.get(symbol.upper(), [])


SENTIMENT_PROMPT = (
    "You are a financial sentiment rater. Given headlines about a stock, reply "
    'with ONLY a JSON object like {"score": 0.4} where score is between -1 '
    "(very negative) and 1 (very positive). If given no headlines, return 0."
)

SUMMARY_PROMPT = (
    "You are a financial news summarizer. In 2-3 short sentences, summarize the "
    "tone and substance of these headlines for a retail investor glancing at a "
    "dashboard. Be neutral and factual -- do not give trading advice. If there "
    "are no headlines, say plainly that there is no recent headline data for "
    "this stock in this demo dataset."
)


def _extract_score(text: str) -> float:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return 0.0
    try:
        return max(-1.0, min(1.0, float(json.loads(m.group())["score"])))
    except Exception:
        return 0.0


def _heuristic_score(items: list[str]) -> float:
    text = " ".join(items).lower()
    pos_words = ["record", "profit", "wins", "raise", "expands", "growth", "strong", "beat", "high"]
    neg_words = ["review", "weak", "faces", "cut", "loss", "delay", "pressure", "slow", "fall"]
    pos = sum(w in text for w in pos_words)
    neg = sum(w in text for w in neg_words)
    return round((pos - neg) / max(pos + neg, 1), 2)


def _fallback_summary(items: list[str]) -> str:
    if not items:
        return "No recent headline data for this stock in this demo dataset."
    return "Recent headlines: " + "; ".join(items) + "."


def get_news_sentiment(symbol: str, provider: str = DEFAULT_PROVIDER) -> dict[str, Any]:
    """Sample-data sentiment score + LLM summary for one symbol. Always
    labeled `is_sample_data: True` -- this project uses no external news API."""
    symbol = symbol.upper()
    items = get_sample_headlines(symbol)
    headline_text = "; ".join(items) if items else "(no headlines available)"
    user_msg = [{"role": "user", "content": f"Headlines for {symbol}: {headline_text}"}]

    # generous max_tokens: Gemini's "thinking" tokens count against the budget,
    # and a tight limit here can silently exhaust it before any visible text
    # comes out (finish_reason="length", content=None) -- same issue fixed in
    # week2/04-llm-news-sentiment/01-intro_llm_prompting.ipynb
    score_reply = chat(user_msg, system=SENTIMENT_PROMPT, provider=provider, max_tokens=300)
    summary_reply = chat(user_msg, system=SUMMARY_PROMPT, provider=provider, max_tokens=600)

    is_mock = score_reply.startswith("[MOCK REPLY]")
    score = _heuristic_score(items) if is_mock else _extract_score(score_reply)
    summary = _fallback_summary(items) if summary_reply.startswith("[MOCK REPLY]") else summary_reply

    return {
        "symbol": symbol,
        "headlines": items,
        "score": score,
        "summary": summary,
        "is_sample_data": True,
        "provider": "mock" if is_mock else provider,
    }


# --- Static market notes, reused from extras/rag-market-chat.ipynb --------
MARKET_NOTES = [
    "A moving average smooths price by averaging the last N days; crossovers signal trend changes.",
    "The EGX30 is the main Egyptian stock index, tracking 30 large listed companies.",
    "CIB (COMI) is Egypt's largest private-sector bank.",
    "Volatility is the standard deviation of returns; higher volatility means higher risk.",
    "A benchmark is what you compare a strategy against; beating it is the goal.",
    "A Sharpe ratio measures return earned per unit of risk taken; higher is generally better.",
    "Max drawdown is the worst peak-to-trough decline in a portfolio's value over the period measured.",
]

CHAT_SYSTEM_TEMPLATE = """You are "Bull," the loud, over-caffeinated trading-floor mascot built into the EGX Strategy Lab dashboard.

PERSONALITY:
- You are aggressively, hilariously pro-stock-market. You think buying good businesses and staying invested is basically the greatest idea humans ever had, and you say so with maximum enthusiasm.
- You talk like a hype-man at a trading floor: bold claims, trading slang, the occasional ALL-CAPS moment, playful trash-talk about "boring" savings accounts and mattress money. You are never actually mean to the user, only theatrically extra.
- You are funny ON PURPOSE. Exaggerate for comedic effect. Self-aware jokes about your own hype are encouraged.
- Keep replies to a few sentences unless the question genuinely needs more.

NON-NEGOTIABLE RULE: underneath the bravado you are precise and honest about NUMBERS. Never invent a return, price, strategy name, or metric that isn't in the DASHBOARD CONTEXT or MARKET NOTES below. If you don't have a number, say so (loudly, but honestly) instead of making one up. If someone asks for a real "should I buy X" call, give your hyped opinion but clearly land the message on: this is entertainment, not financial advice -- do your own research.

DASHBOARD CONTEXT (the only source of truth for live numbers -- use it, don't guess):
{context}

GENERAL MARKET NOTES (background definitions you can draw on):
{notes}
"""


def build_dashboard_context(context: dict[str, Any] | None) -> str:
    if not context:
        return "(no dashboard data has been loaded yet in this session)"
    return json.dumps(context, indent=2, default=str)


def _pct(v: Any) -> str:
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "n/a"


def _num(v: Any, digits: int = 2) -> str:
    return f"{v:.{digits}f}" if isinstance(v, (int, float)) else "n/a"


def local_fallback_answer(message: str, context: dict[str, Any] | None) -> str:
    """Bull's own numbers-only comeback when the real LLM call is unavailable
    (rate-limited, no key, etc.). No AI writing involved -- just Bull's voice
    wrapped around whatever's actually in `context`, so a throttled API never
    means a useless reply. Still only ever states numbers that are in `context`."""
    context = context or {}
    q = message.lower()
    lines: list[str] = []

    best = context.get("best_strategy") or {}
    ma = context.get("ma_crossover")
    weekly = context.get("weekly_mean_reversion")
    tiktok = context.get("tiktok_strategy")
    news = context.get("news_sentiment")
    stock = context.get("selected_stock_backtest")
    seeds = best.get("seed_stability")

    wants_best = any(w in q for w in ["best", "top", "winner", "strongest"])
    wants_bench = any(w in q for w in ["benchmark", "buy and hold", "equal weight", "equal-weight"])
    wants_ma = any(w in q for w in ["crossover", "moving average", " ma "])
    wants_weekly = "weekly" in q or "mean reversion" in q
    wants_tiktok = "tiktok" in q
    wants_news = any(w in q for w in ["news", "sentiment", "headline"])
    wants_seed = any(w in q for w in ["seed", "stable", "stability", "luck", "robust"])
    wants_stock = any(w in q for w in ["this stock", "selected stock", "backtest"])

    if wants_best and best:
        m = best.get("metrics", {})
        lines.append(
            f"THE BELT GOES TO {best.get('name', 'the best strategy')} ({best.get('model_type', '?')})! "
            f"Return {_pct(m.get('return_pct'))}, max drawdown {_pct(m.get('max_drawdown_pct'))}, "
            f"Sharpe {_num(m.get('sharpe'))}, final value {_num(m.get('final_value'))} EGP."
        )
    if wants_seed and seeds:
        lines.append(
            f"Seed check across {len(seeds.get('seeds', []))} seeds: mean return {_pct(seeds.get('mean_return_pct'))}, "
            f"std {_num(seeds.get('std_return_pct'))} pts, profitable in "
            f"{round((seeds.get('profitable_seed_fraction') or 0) * 100)}% of runs. {seeds.get('verdict', '')}"
        )
    if (wants_bench or (wants_best and not best)) and best.get("comparison_table"):
        bench_row = next((r for r in best["comparison_table"] if "Benchmark" in r.get("Strategy", "")), None)
        if bench_row:
            lines.append(
                f"Benchmark (equal-weight): return {_pct(bench_row.get('Return %'))}, "
                f"drawdown {_pct(bench_row.get('Max Drawdown %'))}, Sharpe {_num(bench_row.get('Sharpe'))}."
            )
    if wants_ma and ma:
        lines.append(
            f"MA Crossover: return {_pct(ma.get('return_percent'))}, drawdown {_pct(ma.get('max_drawdown_percent'))}, "
            f"Sharpe {_num(ma.get('sharpe'))}, final value {_num(ma.get('final_value'))} EGP."
        )
    if wants_weekly and weekly:
        lines.append(
            f"Weekly Mean Reversion: return {_pct(weekly.get('return_percent'))}, "
            f"drawdown {_pct(weekly.get('max_drawdown_percent'))}, Sharpe {_num(weekly.get('sharpe'))}."
        )
    if wants_tiktok and tiktok:
        lines.append(
            f"TikTok Guru Strategy: return {_pct(tiktok.get('return_percent'))}, "
            f"drawdown {_pct(tiktok.get('max_drawdown_percent'))}, Sharpe {_num(tiktok.get('sharpe'))}."
        )
    if wants_news and news:
        lines.append(f"News sentiment for {news.get('symbol', 'the stock')}: score {news.get('score')} -- {news.get('summary', '')}")
    if wants_stock and stock:
        lines.append(
            f"{stock.get('symbol', 'This stock')}'s MA-crossover backtest: return {_pct(stock.get('return_percent'))}, "
            f"drawdown {_pct(stock.get('max_drawdown_percent'))}, final value {_num(stock.get('final_value'))} EGP."
        )

    if lines:
        prefix = "(quick numbers -- my AI brain is rate-limited right now, but I never bluff on data) "
        return prefix + " ".join(lines)

    available = []
    if best:
        available.append(f"best strategy = {best.get('name')}")
    if ma:
        available.append(f"MA crossover on {context.get('selected_symbol', '?')}")
    if weekly:
        available.append("weekly mean reversion")
    if tiktok:
        available.append("tiktok strategy")
    if news:
        available.append(f"news sentiment for {news.get('symbol')}")

    if not available:
        return (
            "Whoa, hold up -- nothing's loaded on this dashboard yet! Run a backtest or pull up some stock news "
            "and I'll come back swinging with real numbers. Can't hype what isn't on screen."
        )
    return (
        "My AI brain's throttled for a second (rate limit, not laziness) so I can't freestyle this one, but here's "
        f"what's actually loaded right now: {', '.join(available)}. Ask me about one of those by name and I'll shout "
        "the real numbers at you."
    )


def chat_reply(
    message: str,
    history: list[dict[str, str]] | None = None,
    context: dict[str, Any] | None = None,
    provider: str = DEFAULT_PROVIDER,
) -> str:
    system = CHAT_SYSTEM_TEMPLATE.format(
        context=build_dashboard_context(context),
        notes="\n".join(f"- {n}" for n in MARKET_NOTES),
    )
    messages = list(history or []) + [{"role": "user", "content": message}]
    reply = chat(messages, system=system, provider=provider, max_tokens=500)
    if reply.startswith("[MOCK REPLY]"):
        return local_fallback_answer(message, context)
    return reply
