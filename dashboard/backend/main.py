"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .strategy_service import list_assets, run_ma_crossover_backtest, to_jsonable

app = FastAPI(title="EGX Strategy Lab")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
