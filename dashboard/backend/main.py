"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .llm_service import chat_reply, get_news_sentiment
from .strategy_service import (
    list_assets,
    load_json_artifact,
    load_reference_notebook_results,
    run_ma_crossover_backtest,
    run_tiktok_strategy_backtest,
    run_weekly_mean_reversion_backtest,
    sharpe_from_portfolio_values,
    to_jsonable,
)

app = FastAPI(title="EGX Strategy Lab")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class BacktestRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    initial_cash: float = Field(1000.0, gt=0)
    fast_window: int = Field(9, gt=0)
    slow_window: int = Field(20, gt=0)

    @property
    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        if self.fast_window >= self.slow_window:
            errors.append("fast_window must be smaller than slow_window")
        return errors


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/assets")
def assets() -> dict[str, list[str]]:
    try:
        symbols = list_assets()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="EGX data folder is unavailable") from exc
    return {"assets": symbols}


@app.post("/backtest")
def backtest(request: BacktestRequest) -> dict:
    if request.validation_errors:
        raise HTTPException(status_code=400, detail=request.validation_errors[0])

    try:
        result = run_ma_crossover_backtest(
            symbol=request.symbol.upper(),
            initial_cash=request.initial_cash,
            fast_window=request.fast_window,
            slow_window=request.slow_window,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"No data found for symbol {request.symbol}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Backtest failed") from exc

    return to_jsonable(result)


@app.get("/api/strategy-performance")
def strategy_performance(
    symbol: str,
    initial_cash: float = 1000.0,
    fast_window: int = 9,
    slow_window: int = 20,
) -> dict:
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")

    try:
        ma_result = run_ma_crossover_backtest(
            symbol=symbol.upper(),
            initial_cash=initial_cash,
            fast_window=fast_window,
            slow_window=slow_window,
        )
        weekly_result = run_weekly_mean_reversion_backtest(initial_cash=initial_cash)
        tiktok_result = run_tiktok_strategy_backtest(initial_cash=initial_cash)
        ma_result["sharpe"] = sharpe_from_portfolio_values(ma_result["portfolio_values"])
        weekly_result["sharpe"] = sharpe_from_portfolio_values(weekly_result["portfolio_values"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Strategy performance computation failed") from exc

    return to_jsonable({
        "ma_crossover": ma_result,
        "weekly_mean_reversion": weekly_result,
        "tiktok_strategy": tiktok_result,
        # MLP vs LSTM full-universe portfolio strategy, precomputed by
        # week2/day3/day3_prediction_to_portfolio.ipynb and saved to dashboard/data/.
        # None until that notebook has been run at least once.
        "best_strategy": load_json_artifact("day3_strategy.json"),
        # The instructor's own already-executed reference notebooks, for a
        # mine-vs-reference comparison. None if those notebooks are missing.
        "reference_notebooks": load_reference_notebook_results(),
    })


@app.get("/api/news-sentiment")
def news_sentiment(symbol: str) -> dict:
    """Day 4 -- news-sentiment extra. Sample-headline sentiment score + LLM
    summary for one symbol. Not a real news feed (no external APIs in this
    project) -- response is always labeled `is_sample_data: True`."""
    try:
        return to_jsonable(get_news_sentiment(symbol.upper()))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="News sentiment failed") from exc


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest) -> dict:
    """Day 4 -- dashboard chat agent. Grounded in whatever dashboard data the
    frontend passes in `context` (already-fetched strategy performance, the
    selected symbol, etc.) so it answers from real numbers, not guesses."""
    try:
        reply = chat_reply(request.message, history=request.history, context=request.context)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Chat failed") from exc
    return {"reply": reply}
