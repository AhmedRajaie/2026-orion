"""FastAPI backend for the dashboard. Grows via dashboard/tasks/.
Run: uv run uvicorn dashboard.backend.main:app --reload --port 8000
"""
import threading

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tradinglab.data_feed import DataFeed, load_symbol_full_history, resolve_price_field
from tradinglab.indicators import (
    sma, ema, rsi, macd, bollinger_bands,
    stochastic_oscillator, atr, adx, vwap, ichimoku, parabolic_sar, obv,
)
from tradinglab.simulator import PortfolioSimulator
from tradinglab.backtester import run_backtest
from tradinglab.strategies.sma import sma_crossover_weights
from tradinglab.strategies.mpt import mpt_window_strategy
from tradinglab.strategies.mean_reversion import weekly_loser_weights
from tradinglab.strategies.lstm import load_lstm_strategy
from tradinglab.strategies.nn import load_nn_strategy
from tradinglab.strategies.rl import load_rl_strategy
from tradinglab.observation import build_observation
from tradinglab.single_asset_backtest import run_ma_crossover_backtest
from tradinglab.hft_mean_reversion_backtest import run_hft_mean_reversion_backtest
from tradinglab.forecast import gbm_forecast
from tradinglab.metrics import total_return, sharpe, max_drawdown
from tradinglab.model_comparison import EVALUATORS, CheckpointNotFound, available_symbols_for

# strategy_service.py (this repo's own teammate branch) — a smaller,
# independent MA-crossover/weekly-mean-reversion service kept alive here as
# extra endpoints alongside the fuller set below. Aliased to avoid colliding
# with tradinglab.single_asset_backtest.run_ma_crossover_backtest, which has a
# different signature/return shape.
from .strategy_service import (
    list_assets,
    run_ma_crossover_backtest as strategy_service_ma_crossover_backtest,
    run_weekly_mean_reversion_backtest,
    to_jsonable,
)

DATA_DIR = "data/egx"

app = FastAPI(title="Younit-style trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Two named universes (TASK_05) — "small" is the 6-stock teaching set, "full"
# is every symbol in data/egx. Everything universe-scoped (the /universe list,
# the multi-asset /backtest and /metrics, and which symbols are valid for the
# single-asset endpoints below) reads from whichever of these the request asks
# for, defaulting to "small".
SMALL_UNIVERSE_SYMBOLS = ["COMI", "HRHO", "TMGH", "SWDY", "FWRY", "ABUK"]
feeds = {
    "small": DataFeed.from_dir(DATA_DIR, symbols=SMALL_UNIVERSE_SYMBOLS),
    "full": DataFeed.from_dir(DATA_DIR),
}

# The base strategy from Notebook 4 (SMA crossover) and MPT max-Sharpe are
# plain observation->weights functions sharing run_backtest/PortfolioSimulator.
# HFT mean-reversion trades discrete fixed-notional positions per symbol
# against a shared cash pool instead — it doesn't fit that shape, so it gets
# its own engine (hft_mean_reversion_backtest.py) but returns the same
# dates/portfolio/benchmark/portfolio_returns shape so /backtest and /metrics
# can serve all three uniformly.
STRATEGIES = {"sma": sma_crossover_weights, "mpt": mpt_window_strategy}
STRATEGY_LABELS = {
    "sma": "SMA crossover (Notebook 4 baseline)",
    "mpt": "MPT max-Sharpe",
    "hft_mean_reversion": "HFT Mean-Reversion Rebound",
}

# LSTM: trained once in lstm.ipynb (pooled across the small universe, saved to
# models/lstm_dashboard.pt), loaded here as one more observation->weights
# function — same shape as sma_crossover_weights/mpt_window_strategy, so it
# slots into STRATEGIES/run_backtest with no special-casing. The model itself
# doesn't care how many assets are in a given day's observation (it scores
# each asset independently), so the one small-universe-trained model is used
# for both the small and full universe. If the checkpoint hasn't been trained
# yet, LSTM is silently omitted rather than crashing the whole server.
try:
    STRATEGIES["lstm"] = load_lstm_strategy("models/lstm_dashboard.pt")
    STRATEGY_LABELS["lstm"] = "LSTM (pooled, next-day return)"
except FileNotFoundError as e:
    print(f"[dashboard] {e}")

# NN: same idea as LSTM, but the pooled MLP trained in
# week2/01-features-and-model/notebook.ipynb's Part 6.
try:
    STRATEGIES["nn"] = load_nn_strategy("models/mlp_dashboard.pt")
    STRATEGY_LABELS["nn"] = "NN (pooled, next-day return)"
except FileNotFoundError as e:
    print(f"[dashboard] {e}")

# RL: PPO trained by scripts/run_train.py on the FULL 34-stock universe. Unlike
# the other strategies (which score each asset independently and generalize
# to any n_assets), a PPO policy's action layer is sized for the EXACT n_assets
# it trained on — this one only ever works on universe="full", enforced in
# _run_multi_asset_backtest below rather than silently producing garbage.
try:
    STRATEGIES["rl"] = load_rl_strategy("models/ppo_agent.zip")
    STRATEGY_LABELS["rl"] = "RL Agent (PPO, full universe only)"
except FileNotFoundError as e:
    print(f"[dashboard] {e}")

RL_ONLY_UNIVERSE = "full"

_SYMBOL_CACHE: dict[str, pd.DataFrame] = {}
# MPT re-optimizes (SLSQP) every trading day of the walk-forward loop, so the
# full 34-stock universe takes ~50s. The underlying data never changes within
# a server run, so cache the (universe, strategy) result the same way
# _SYMBOL_CACHE memoizes per-symbol history — first request pays the cost,
# every toggle back to it after that is instant.
_BACKTEST_CACHE: dict[tuple[str, str], dict] = {}


def _get_feed(universe: str) -> DataFeed:
    if universe not in feeds:
        raise HTTPException(status_code=400, detail=f"unknown universe '{universe}'. use 'small' or 'full'.")
    return feeds[universe]


def _symbol_history(symbol: str, universe: str = "small") -> pd.DataFrame:
    if symbol not in _get_feed(universe).symbols:
        raise HTTPException(status_code=404, detail=f"unknown symbol '{symbol}' in universe '{universe}'")
    if symbol not in _SYMBOL_CACHE:
        _SYMBOL_CACHE[symbol] = load_symbol_full_history(DATA_DIR, symbol)
    return _SYMBOL_CACHE[symbol]


def _run_multi_asset_backtest(universe: str, strategy: str):
    if strategy not in STRATEGY_LABELS:
        raise HTTPException(status_code=400, detail=f"unknown strategy '{strategy}'. use one of {sorted(STRATEGY_LABELS)}.")
    if strategy == "rl" and universe != RL_ONLY_UNIVERSE:
        raise HTTPException(
            status_code=400,
            detail=f"the RL agent was trained on the '{RL_ONLY_UNIVERSE}' universe only "
                    f"(its policy network is sized for that many assets) — switch to '{RL_ONLY_UNIVERSE}' to use it.",
        )
    key = (universe, strategy)
    if key not in _BACKTEST_CACHE:
        feed = _get_feed(universe)
        if strategy in STRATEGIES:
            sim = PortfolioSimulator(feed)
            _BACKTEST_CACHE[key] = run_backtest(sim, STRATEGIES[strategy], lookback=30)
        else:  # hft_mean_reversion
            _BACKTEST_CACHE[key] = run_hft_mean_reversion_backtest(feed, lookback=30)
    return _BACKTEST_CACHE[key]


@app.on_event("startup")
def _warm_backtest_cache():
    # MPT on the full universe is the slow path (~50s) — pay that cost once in
    # the background at server start instead of on whichever request happens
    # to hit it first.
    def warm():
        for universe in feeds:
            for strategy in STRATEGY_LABELS:
                try:
                    _run_multi_asset_backtest(universe, strategy)
                except Exception:
                    pass

    threading.Thread(target=warm, daemon=True).start()


def _slice_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df["date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["date"] <= pd.to_datetime(end)]
    if len(df) == 0:
        raise HTTPException(status_code=400, detail="date range excludes all available data")
    return df.reset_index(drop=True)


def _nan_to_none(values) -> list:
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v) for v in values]


def _price_field(df: pd.DataFrame, field: str):
    try:
        return resolve_price_field(df, field)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/universe")
def universe(universe: str = "small"):
    return _get_feed(universe).symbols


@app.get("/prices/{symbol}")
def prices(symbol: str, universe: str = "small", field: str = "close", start: str | None = None, end: str | None = None):
    df = _slice_range(_symbol_history(symbol, universe), start, end)
    close, resolved_field = _price_field(df, field)
    return {
        "dates": df["date"].dt.strftime("%Y-%m-%d").tolist(),
        "close": close.tolist(),
        "field": resolved_field,
    }


@app.get("/indicators/{symbol}")
def indicators(
    symbol: str,
    universe: str = "small",
    field: str = "close",
    sma_window: int = 20,
    ema_window: int = 20,
    rsi_window: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_window: int = 20,
    bb_std: float = 2.0,
    stoch_k: int = 14,
    stoch_d: int = 3,
    atr_window: int = 14,
    adx_window: int = 14,
    vwap_window: int = 20,
    ichimoku_tenkan: int = 9,
    ichimoku_kijun: int = 26,
    ichimoku_senkou_b: int = 52,
    psar_step: float = 0.02,
    psar_max: float = 0.2,
    start: str | None = None,
    end: str | None = None,
):
    df = _slice_range(_symbol_history(symbol, universe), start, end)
    price, resolved_field = _price_field(df, field)
    open_, high, low, close, volume = (df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close", "volume"))

    ma_fast = sma(price, sma_window)
    ema_line = ema(price, ema_window)
    rsi_values = rsi(price, rsi_window)
    macd_line, macd_signal_line, macd_hist = macd(price, macd_fast, macd_slow, macd_signal)
    bb_mid, bb_upper, bb_lower = bollinger_bands(price, bb_window, bb_std)
    stoch_k_line, stoch_d_line = stochastic_oscillator(high, low, close, stoch_k, stoch_d)
    atr_line = atr(high, low, close, atr_window)
    adx_line, plus_di, minus_di = adx(high, low, close, adx_window)
    vwap_line = vwap(high, low, close, volume, vwap_window)
    tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku(high, low, close, ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_b)
    psar_line = parabolic_sar(high, low, psar_step, psar_max)
    obv_line = obv(close, volume)

    return {
        "dates": df["date"].dt.strftime("%Y-%m-%d").tolist(),
        "field": resolved_field,
        "open": open_.tolist(),
        "high": high.tolist(),
        "low": low.tolist(),
        "close": close.tolist(),
        "volume": volume.tolist(),
        "price": price.tolist(),
        "sma": _nan_to_none(ma_fast),
        "ema": _nan_to_none(ema_line),
        "rsi": _nan_to_none(rsi_values),
        "macd_line": _nan_to_none(macd_line),
        "macd_signal": _nan_to_none(macd_signal_line),
        "macd_hist": _nan_to_none(macd_hist),
        "bb_upper": _nan_to_none(bb_upper),
        "bb_mid": _nan_to_none(bb_mid),
        "bb_lower": _nan_to_none(bb_lower),
        "stoch_k": _nan_to_none(stoch_k_line),
        "stoch_d": _nan_to_none(stoch_d_line),
        "atr": _nan_to_none(atr_line),
        "adx": _nan_to_none(adx_line),
        "plus_di": _nan_to_none(plus_di),
        "minus_di": _nan_to_none(minus_di),
        "vwap": _nan_to_none(vwap_line),
        "ichimoku_tenkan": _nan_to_none(tenkan),
        "ichimoku_kijun": _nan_to_none(kijun),
        "ichimoku_senkou_a": _nan_to_none(senkou_a),
        "ichimoku_senkou_b": _nan_to_none(senkou_b),
        "ichimoku_chikou": _nan_to_none(chikou),
        "psar": _nan_to_none(psar_line),
        "obv": _nan_to_none(obv_line),
    }


@app.get("/backtest/single")
def backtest_single(
    symbol: str,
    universe: str = "small",
    field: str = "close",
    fast: int = 9,
    slow: int = 20,
    capital: float = 1000.0,
    start: str | None = None,
    end: str | None = None,
):
    if fast >= slow:
        raise HTTPException(status_code=400, detail="fast period must be less than slow period")

    df = _slice_range(_symbol_history(symbol, universe), start, end)
    dates = pd.DatetimeIndex(df["date"])
    close, resolved_field = _price_field(df, field)

    result = run_ma_crossover_backtest(dates, close, fast=fast, slow=slow, capital=capital)
    date_strs = [d.strftime("%Y-%m-%d") for d in result["dates"]]

    def signal_feed(indices):
        return [
            {"date": date_strs[i], "price": float(close[i]), "portfolio_value": float(result["portfolio_value"][i])}
            for i in indices
        ]

    def trade_json(t):
        return {
            "buy_date": t["buy_date"].strftime("%Y-%m-%d"),
            "buy_price": float(t["buy_price"]),
            "sell_date": t["sell_date"].strftime("%Y-%m-%d") if t["sell_date"] is not None else None,
            "sell_price": float(t["sell_price"]) if t["sell_price"] is not None else None,
            "holding_days": t["holding_days"],
            "return_pct": t["return_pct"],
            "win": t["win"],
            "open": t["open"],
        }

    return {
        "dates": date_strs,
        "field": resolved_field,
        "close": result["close"].tolist(),
        "ma_fast": _nan_to_none(result["ma_fast"]),
        "ma_slow": _nan_to_none(result["ma_slow"]),
        "portfolio_value": _nan_to_none(result["portfolio_value"]),
        "buy_and_hold_value": result["buy_and_hold_value"].tolist(),
        "buy_signals": signal_feed(result["buy_indices"]),
        "sell_signals": signal_feed(result["sell_indices"]),
        "trades": [trade_json(t) for t in result["trades"]],
        "kpis": result["kpis"],
        "alert": result["alert"],
    }


@app.get("/forecast/{symbol}")
def forecast(symbol: str, universe: str = "small", field: str = "close", years: float = 3.0, confidence: float = 0.80):
    df = _symbol_history(symbol, universe)
    close, resolved_field = _price_field(df, field)
    fc = gbm_forecast(close, horizon_years=years, confidence=confidence)

    last_date = df["date"].iloc[-1]
    future_dates = pd.bdate_range(last_date, periods=fc["horizon_days"] + 1)[1:]

    return {
        "field": resolved_field,
        "history": {
            "dates": df["date"].dt.strftime("%Y-%m-%d").tolist(),
            "close": close.tolist(),
        },
        "forecast": {
            "dates": future_dates.strftime("%Y-%m-%d").tolist(),
            "median": fc["median"].tolist(),
            "lower": fc["lower"].tolist(),
            "upper": fc["upper"].tolist(),
        },
        "confidence": fc["confidence"],
        "annualized_drift_pct": fc["annualized_drift_pct"],
        "annualized_volatility_pct": fc["annualized_volatility_pct"],
        "disclaimer": (
            "Statistical projection from this asset's own historical drift and "
            "volatility (geometric Brownian motion). Not a prediction and not "
            "a guarantee of future performance."
        ),
    }


@app.get("/strategies")
def list_strategies():
    return [{"key": k, "label": v} for k, v in STRATEGY_LABELS.items()]


@app.get("/backtest")
def backtest(universe: str = "small", strategy: str = "sma"):
    result = _run_multi_asset_backtest(universe, strategy)
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in result["dates"]],
        "portfolio": result["portfolio"].tolist(),
        "benchmark": result["benchmark"].tolist(),
        "strategy": strategy,
        "strategy_label": STRATEGY_LABELS[strategy],
    }


@app.get("/metrics")
def metrics(universe: str = "small", strategy: str = "sma"):
    result = _run_multi_asset_backtest(universe, strategy)
    returns = result["portfolio_returns"]
    response = {
        "total_return": round(total_return(returns), 3),
        "sharpe": round(sharpe(returns), 3),
        "max_drawdown": round(max_drawdown(returns), 3),
        "strategy": strategy,
        "strategy_label": STRATEGY_LABELS[strategy],
    }
    # Win rate / trade counts only make sense for a discrete-trade strategy —
    # SMA and MPT rebalance continuous weights daily and never "close a trade".
    if strategy == "hft_mean_reversion":
        k = result["kpis"]
        response.update({
            "win_rate_pct": round(k["win_rate_pct"], 1),
            "num_trades_closed": k["num_trades_closed"],
            "num_positions_open_at_end": k["num_positions_open_at_end"],
            "avg_holding_days": round(k["avg_holding_days"], 1),
        })
    return response


# ------------------------------------------------------- model comparison ----
# "Model" here means a per-stock checkpoint from a notebook (NN from week2's
# notebook, LSTM from lstm.ipynb) — distinct from "strategy" (a pooled,
# universe-wide observation->weights function used by /backtest above). The
# same trained artifacts show up in both: e.g. models/lstm_dashboard.pt is the
# "lstm" STRATEGY, while models/lstm_<SYMBOL>.pt are the per-stock "lstm"
# MODEL checkpoints this section serves.
MODEL_LABELS = {"nn": "NN (MLP)", "lstm": "LSTM"}

_MODEL_EVAL_CACHE: dict[tuple[str, str], dict] = {}


@app.get("/models")
def list_models():
    return [
        {
            "key": key,
            "label": MODEL_LABELS[key],
            "symbols": available_symbols_for(key),
            "wired_as_strategy": key in STRATEGIES,
        }
        for key in EVALUATORS
    ]


@app.get("/models/{model}/{symbol}")
def model_comparison(model: str, symbol: str, capital: float = 1000.0):
    if model not in EVALUATORS:
        raise HTTPException(status_code=400, detail=f"unknown model '{model}'. use one of {sorted(EVALUATORS)}.")
    key = (model, symbol)
    if key not in _MODEL_EVAL_CACHE:
        try:
            _MODEL_EVAL_CACHE[key] = EVALUATORS[model](symbol, capital=capital)
        except CheckpointNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
    result = _MODEL_EVAL_CACHE[key]

    bt = result["signal_backtest"]
    return {
        "model": result["model"],
        "model_label": MODEL_LABELS[model],
        "symbol": symbol,
        "dates_train": result["dates_train"],
        "dates_test": result["dates_test"],
        "y_train": result["y_train"],
        "train_preds": result["train_preds"],
        "y_test": result["y_test"],
        "test_preds": result["test_preds"],
        "train_loss_history": result["train_loss_history"],
        "test_loss_history": result["test_loss_history"],
        "metrics": result["metrics"],
        "portfolio_value": bt["portfolio_value"].tolist(),
        "buy_and_hold_value": bt["buy_and_hold_value"].tolist(),
        "buy_indices": bt["buy_indices"],
        "sell_indices": bt["sell_indices"],
        "kpis": bt["kpis"],
    }


# ---------------------------------------------------- performance results ----
_PERFORMANCE_RESULTS_CACHE: dict | None = None


@app.get("/performance-results")
def performance_results():
    global _PERFORMANCE_RESULTS_CACHE
    if _PERFORMANCE_RESULTS_CACHE is not None:
        return _PERFORMANCE_RESULTS_CACHE

    model_rows = []
    for model_key in EVALUATORS:
        for symbol in available_symbols_for(model_key):
            cache_key = (model_key, symbol)
            if cache_key not in _MODEL_EVAL_CACHE:
                try:
                    _MODEL_EVAL_CACHE[cache_key] = EVALUATORS[model_key](symbol)
                except CheckpointNotFound:
                    continue
            r = _MODEL_EVAL_CACHE[cache_key]
            model_rows.append({
                "kind": "model",
                "key": model_key,
                "label": MODEL_LABELS[model_key],
                "symbol": symbol,
                "rmse": r["metrics"]["rmse"],
                "mae": r["metrics"]["mae"],
                "mape": r["metrics"]["mape"],
                "directional_accuracy_pct": r["metrics"]["directional_accuracy_pct"],
                "low_liquidity": r["metrics"]["low_liquidity"],
                "total_return_pct": r["signal_backtest"]["kpis"]["total_return_pct"],
                "sharpe": r["signal_backtest"]["kpis"]["sharpe"],
                "max_drawdown_pct": r["signal_backtest"]["kpis"]["max_drawdown_pct"],
                "win_rate_pct": r["signal_backtest"]["kpis"]["win_rate_pct"],
            })

    strategy_rows = []
    for universe in feeds:
        for strategy_key in STRATEGY_LABELS:
            if strategy_key == "rl" and universe != RL_ONLY_UNIVERSE:
                continue
            result = _run_multi_asset_backtest(universe, strategy_key)
            returns = result["portfolio_returns"]
            row = {
                "kind": "strategy",
                "key": strategy_key,
                "label": STRATEGY_LABELS[strategy_key],
                "universe": universe,
                "total_return_pct": round(total_return(returns) * 100, 2),
                "sharpe": round(sharpe(returns), 3),
                "max_drawdown_pct": round(max_drawdown(returns) * 100, 2),
            }
            if strategy_key == "hft_mean_reversion":
                row["win_rate_pct"] = round(result["kpis"]["win_rate_pct"], 1)
            strategy_rows.append(row)

    # Best-per-stock (models only — strategies are universe-wide, not per-stock)
    best_per_stock: dict[str, dict] = {}
    for row in model_rows:
        if row["low_liquidity"]:
            continue
        current = best_per_stock.get(row["symbol"])
        if current is None or row["directional_accuracy_pct"] > current["directional_accuracy_pct"]:
            best_per_stock[row["symbol"]] = row

    _PERFORMANCE_RESULTS_CACHE = {
        "models": model_rows,
        "strategies": strategy_rows,
        "best_per_stock": {symbol: {"key": r["key"], "label": r["label"]} for symbol, r in best_per_stock.items()},
    }
    return _PERFORMANCE_RESULTS_CACHE


# ------------------------------------------------ extra portfolio endpoint ----
# Five-day loser mean reversion across the FULL universe, with an explicit
# commission-drag comparison and a "what would I buy today" allocation list.
# Ported from a teammate branch (origin/Kanzy_Kabesh) that was left half-merged
# with unresolved conflict markers in this file — ma_strategy is distinct from
# both STRATEGIES["mpt"]/["sma"] above and strategy_service.py's endpoints
# below, so it's kept as its own route rather than dropped.
@app.get("/portfolio/mean-reversion")
def mean_reversion_portfolio():
    """Run the five-day loser strategy across the complete EGX universe."""
    initial_cash = 1000.0
    commission = 0.005
    lookback = 30
    signal_days = 5

    feed = DataFeed.from_dir(DATA_DIR)
    strategy = lambda observation: weekly_loser_weights(
        observation,
        lookback_days=signal_days,
    )

    result = run_backtest(
        PortfolioSimulator(feed, commission=commission),
        strategy,
        lookback=lookback,
    )
    result_no_cost = run_backtest(
        PortfolioSimulator(feed, commission=0.0),
        strategy,
        lookback=lookback,
    )

    portfolio = np.asarray(result["portfolio"], dtype=float) * initial_cash
    no_cost_portfolio = (
        np.asarray(result_no_cost["portfolio"], dtype=float) * initial_cash
    )
    benchmark = np.asarray(result["benchmark"], dtype=float) * initial_cash
    running_peak = np.maximum.accumulate(portfolio)
    drawdown_percent = (portfolio - running_peak) / running_peak * 100

    weights = np.asarray(result["weights"], dtype=float)
    weight_changes = np.diff(weights, axis=0, prepend=weights[:1])
    daily_turnover = np.abs(weight_changes).sum(axis=1) / 2
    trade_threshold = 1e-6
    total_trades = int((np.abs(weight_changes) > trade_threshold).sum())
    average_assets_held = float(
        (weights > trade_threshold).sum(axis=1).mean()
    )

    decision_day = feed.n_days - 2
    latest_observation = build_observation(feed, decision_day, lookback)
    recent_returns = latest_observation[:, -signal_days:, 0]
    five_day_returns = np.prod(1.0 + recent_returns, axis=1) - 1.0
    latest_weights = strategy(latest_observation)

    allocations = [
        {
            "symbol": symbol,
            "five_day_return_percent": round(float(period_return * 100), 4),
            "weight_percent": round(float(weight * 100), 4),
            "amount_egp": round(float(weight * initial_cash), 2),
        }
        for symbol, period_return, weight in zip(
            feed.symbols,
            five_day_returns,
            latest_weights,
        )
        if weight > trade_threshold
    ]
    allocations.sort(key=lambda row: row["weight_percent"], reverse=True)

    dates = [pd.Timestamp(date).strftime("%Y-%m-%d") for date in result["dates"]]
    equity_curve = [
        {
            "date": date,
            "portfolio_value": round(float(value), 2),
            "no_cost_value": round(float(no_cost_value), 2),
            "benchmark_value": round(float(benchmark_value), 2),
            "running_peak": round(float(peak), 2),
            "drawdown_percent": round(float(drawdown), 4),
        }
        for date, value, no_cost_value, benchmark_value, peak, drawdown in zip(
            dates,
            portfolio,
            no_cost_portfolio,
            benchmark,
            running_peak,
            drawdown_percent,
        )
    ]

    final_value = float(portfolio[-1])
    final_no_cost_value = float(no_cost_portfolio[-1])
    benchmark_final_value = float(benchmark[-1])
    portfolio_returns = np.asarray(result["portfolio_returns"], dtype=float)

    return {
        "strategy": "Five-day loser mean reversion",
        "description": (
            "Buy five-day losers in proportion to their decline; recent winners "
            "receive zero weight because the simulator is long-only."
        ),
        "universe_size": feed.n_assets,
        "signal_days": signal_days,
        "commission_percent": commission * 100,
        "initial_cash_egp": initial_cash,
        "final_portfolio_value_egp": round(final_value, 2),
        "no_cost_final_value_egp": round(final_no_cost_value, 2),
        "benchmark_final_value_egp": round(benchmark_final_value, 2),
        "commission_drag_egp": round(final_no_cost_value - final_value, 2),
        "total_return_percent": round(total_return(portfolio_returns) * 100, 2),
        "max_drawdown_egp": round(float(np.max(running_peak - portfolio)), 2),
        "max_drawdown_percent": round(max_drawdown(portfolio_returns) * 100, 2),
        "sharpe": round(sharpe(portfolio_returns), 3),
        "total_trades": total_trades,
        "average_assets_held": round(average_assets_held, 1),
        "average_daily_turnover_percent": round(float(daily_turnover.mean() * 100), 2),
        "latest_decision_date": pd.Timestamp(feed.dates[decision_day]).strftime(
            "%Y-%m-%d"
        ),
        "latest_allocations": allocations,
        "equity_curve": equity_curve,
    }


# ------------------------------------------------- strategy_service routes ----
# The independent MA-crossover / weekly-mean-reversion service this repo's
# amrr_waell branch built before the botched merge. Kept as its own routes
# (different paths/methods than everything above) rather than dropped.
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


@app.get("/assets")
def assets() -> dict[str, list[str]]:
    try:
        symbols = list_assets()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="EGX data folder is unavailable") from exc
    return {"assets": symbols}


@app.post("/backtest")
def backtest_service(request: BacktestRequest) -> dict:
    if request.validation_errors:
        raise HTTPException(status_code=400, detail=request.validation_errors[0])

    try:
        result = strategy_service_ma_crossover_backtest(
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
        ma_result = strategy_service_ma_crossover_backtest(
            symbol=symbol.upper(),
            initial_cash=initial_cash,
            fast_window=fast_window,
            slow_window=slow_window,
        )
        weekly_result = run_weekly_mean_reversion_backtest(initial_cash=initial_cash)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Strategy performance computation failed") from exc

    return to_jsonable({
        "ma_crossover": ma_result,
        "weekly_mean_reversion": weekly_result,
    })


# Serves the frontend itself at http://localhost:8000 (index.html at "/",
# app.js alongside it). Mounted last so it only catches requests the API
# routes above didn't already claim.
app.mount("/", StaticFiles(directory="dashboard/frontend", html=True), name="frontend")
