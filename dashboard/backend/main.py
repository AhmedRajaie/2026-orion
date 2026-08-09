"""
FastAPI backend for the trading dashboard.

Run:
python -m uvicorn dashboard.backend.main:app --reload --port 8000
"""

import sys
import os
import numpy as np

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


# ============================================================
# FIND PROJECT ROOT
# ============================================================

while (
    not os.path.isdir("src")
    and os.path.dirname(os.getcwd()) != os.getcwd()
):
    os.chdir("..")

sys.path.insert(0, "src")


# ============================================================
# TRADINGLAB IMPORTS
# ============================================================

from tradinglab.data_feed import DataFeed
from tradinglab.simulator import PortfolioSimulator
from tradinglab.backtester import run_backtest
from tradinglab.strategies.sma import sma_crossover_weights
from tradinglab.charting import turnover_summary


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Trading Dashboard",
    version="2.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# CONSTANTS
# ============================================================

START_CAPITAL = 1000.0
LOOKBACK = 30

SMALL_SYMBOLS = [
    "COMI",
    "HRHO",
    "TMGH",
    "SWDY",
    "FWRY",
    "ABUK"
]


# ============================================================
# TWO UNIVERSES
# ============================================================

feeds = {
    "small": DataFeed.from_dir(
        "data/egx",
        symbols=SMALL_SYMBOLS
    ),

    "full": DataFeed.from_dir(
        "data/egx"
    )
}


print("Loaded file:", os.path.abspath(__file__))

print(
    "Small universe:",
    feeds["small"].symbols
)

print(
    "Small days:",
    feeds["small"].n_days
)

print(
    "Full universe:",
    feeds["full"].symbols
)

print(
    "Full days:",
    feeds["full"].n_days
)


# ============================================================
# UNIVERSE HELPER
# ============================================================

def get_feed(universe: str):

    universe = universe.lower()

    if universe not in feeds:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown universe '{universe}'. "
                f"Use 'small' or 'full'."
            )
        )

    return feeds[universe]


# ============================================================
# SMA
# ============================================================

def sma(prices, window):

    prices = np.asarray(
        prices,
        dtype=float
    )

    result = np.full(
        len(prices),
        np.nan,
        dtype=float
    )

    if len(prices) < window:
        return result

    for i in range(
        window - 1,
        len(prices)
    ):

        result[i] = np.mean(
            prices[
                i - window + 1:
                i + 1
            ]
        )

    return result


# ============================================================
# METRIC FUNCTIONS
# ============================================================

def total_return(returns):

    returns = np.asarray(
        returns,
        dtype=float
    )

    if len(returns) == 0:
        return 0.0

    return float(
        np.prod(
            1.0 + returns
        ) - 1.0
    )


def max_drawdown(returns):

    returns = np.asarray(
        returns,
        dtype=float
    )

    if len(returns) == 0:
        return 0.0

    curve = np.cumprod(
        1.0 + returns
    )

    peak = np.maximum.accumulate(
        curve
    )

    drawdown = (
        peak - curve
    ) / peak

    return float(
        np.max(drawdown)
    )


def sharpe_ratio(returns):

    returns = np.asarray(
        returns,
        dtype=float
    )

    if len(returns) <= 1:
        return 0.0

    std = np.std(returns)

    if std == 0:
        return 0.0

    return float(
        (
            np.mean(returns)
            / std
        )
        * np.sqrt(252)
    )


# ============================================================
# NEW STRATEGY
# SMA20 + 5-DAY MOMENTUM
# ============================================================

def momentum_sma_weights(
    observation,
    sma_window=20,
    momentum_window=5
):

    observation = np.asarray(
        observation,
        dtype=float
    )

    # TradingLab observation shape:
    #
    # (assets, days, features)
    #
    # Example:
    # (6, 30, 5)

    if observation.ndim != 3:

        raise ValueError(
            "Expected TradingLab observation "
            "with shape (assets, days, features), "
            f"received {observation.shape}"
        )

    n_assets, n_days, n_features = (
        observation.shape
    )

    # Close price feature.
    #
    # This is the feature used by the
    # notebook/new strategy.
    CLOSE_INDEX = 3

    if n_features <= CLOSE_INDEX:

        raise ValueError(
            "Close price feature was not found."
        )

    prices = observation[
        :,
        :,
        CLOSE_INDEX
    ]

    # Not enough history

    if n_days < max(
        sma_window,
        momentum_window + 1
    ):

        return np.zeros(
            n_assets,
            dtype=float
        )

    # Current price

    current_prices = prices[:, -1]

    # SMA20

    sma_values = np.mean(
        prices[
            :,
            -sma_window:
        ],
        axis=1
    )

    # 5-day momentum

    previous_prices = prices[
        :,
        -(momentum_window + 1)
    ]

    # Avoid division by zero

    momentum = np.zeros(
        n_assets,
        dtype=float
    )

    valid = previous_prices != 0

    momentum[valid] = (
        current_prices[valid]
        / previous_prices[valid]
    ) - 1.0

    # Conditions

    above_sma = (
        current_prices > sma_values
    )

    positive_momentum = (
        momentum > 0
    )

    selected = (
        above_sma
        &
        positive_momentum
    )

    # Equal weights

    weights = np.zeros(
        n_assets,
        dtype=float
    )

    selected_count = np.sum(
        selected
    )

    if selected_count > 0:

        weights[selected] = (
            1.0 / selected_count
        )

    return weights


# ============================================================
# RUN BASE STRATEGY
# ============================================================

def run_base_strategy(feed):

    sim = PortfolioSimulator(
        feed
    )

    result = run_backtest(
        sim,
        lambda observation:
            sma_crossover_weights(
                observation,
                9,
                20
            ),
        lookback=LOOKBACK
    )

    return result


# ============================================================
# RUN NEW STRATEGY
# ============================================================

def run_new_strategy(feed):

    sim = PortfolioSimulator(
        feed
    )

    result = run_backtest(
        sim,
        momentum_sma_weights,
        lookback=LOOKBACK
    )

    return result


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ============================================================
# UNIVERSE
# ============================================================

@app.get("/universe")
def universe(universe: str = "small"):

    feed = get_feed(
        universe
    )

    return {
        "universe": universe,
        "symbols": feed.symbols,
        "days": feed.n_days
    }


# ============================================================
# PRICES + INDICATORS
# ============================================================

@app.get("/prices/{symbol}")
def prices(
    symbol: str,
    universe: str = "small"
):

    feed = get_feed(
        universe
    )

    symbol = symbol.upper()

    if symbol not in feed.symbols:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Stock '{symbol}' "
                f"not found in the "
                f"{universe} universe."
            )
        )

    stock_index = feed.symbols.index(
        symbol
    )

    price = np.asarray(
        feed.close[:, stock_index],
        dtype=float
    )

    ma9 = sma(
        price,
        9
    )

    ma20 = sma(
        price,
        20
    )

    dates = [
        str(date)
        for date in feed.dates
    ]

    return {

        "universe": universe,

        "symbol": symbol,

        "dates": dates,

        "price":
            np.nan_to_num(
                price
            ).tolist(),

        "ma9":
            np.nan_to_num(
                ma9
            ).tolist(),

        "ma20":
            np.nan_to_num(
                ma20
            ).tolist()
    }


# ============================================================
# BASE BACKTEST
#
# Task 04:
#
# Returns:
# {
#   portfolio: [...],
#   benchmark: [...]
# }
#
# Both start around 1.0
# ============================================================

@app.get("/backtest")
def backtest(
    universe: str = "small"
):

    feed = get_feed(
        universe
    )

    result = run_base_strategy(
        feed
    )

    portfolio = np.asarray(
        result["portfolio"],
        dtype=float
    )

    benchmark = np.asarray(
        result["benchmark"],
        dtype=float
    )

    dates = [
        str(date)
        for date in result["dates"]
    ]

    return {

        "universe": universe,

        "dates": dates,

        "portfolio":
            portfolio.tolist(),

        "benchmark":
            benchmark.tolist()
    }


# ============================================================
# METRICS
#
# Task 05
# ============================================================

@app.get("/metrics")
def metrics(
    universe: str = "small"
):

    feed = get_feed(
        universe
    )

    result = run_base_strategy(
        feed
    )

    returns = np.asarray(
        result[
            "portfolio_returns"
        ],
        dtype=float
    )

    return {

        "universe": universe,

        "total_return":
            round(
                total_return(
                    returns
                ),
                3
            ),

        "sharpe":
            round(
                sharpe_ratio(
                    returns
                ),
                3
            ),

        "max_drawdown":
            round(
                max_drawdown(
                    returns
                ),
                3
            )
    }


# ============================================================
# STRATEGY PERFORMANCE
#
# Base:
# SMA 9/20
#
# New:
# SMA20 + Momentum
# ============================================================

@app.get("/strategy-performance")
def strategy_performance(
    universe: str = "small"
):

    feed = get_feed(
        universe
    )

    # --------------------------------------------------------
    # BASE
    # --------------------------------------------------------

    base_result = run_base_strategy(
        feed
    )

    # --------------------------------------------------------
    # NEW
    # --------------------------------------------------------

    new_result = run_new_strategy(
        feed
    )

    # --------------------------------------------------------
    # RETURNS
    # --------------------------------------------------------

    base_returns = np.asarray(
        base_result[
            "portfolio_returns"
        ],
        dtype=float
    )

    new_returns = np.asarray(
        new_result[
            "portfolio_returns"
        ],
        dtype=float
    )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    base_total_return = total_return(
        base_returns
    )

    new_total_return = total_return(
        new_returns
    )

    base_max_dd = max_drawdown(
        base_returns
    )

    new_max_dd = max_drawdown(
        new_returns
    )

    base_sharpe = sharpe_ratio(
        base_returns
    )

    new_sharpe = sharpe_ratio(
        new_returns
    )

    # --------------------------------------------------------
    # FINAL VALUES
    # --------------------------------------------------------

    base_curve = (
        np.asarray(
            base_result["portfolio"],
            dtype=float
        )
        * START_CAPITAL
    )

    new_curve = (
        np.asarray(
            new_result["portfolio"],
            dtype=float
        )
        * START_CAPITAL
    )

    base_final_value = float(
        base_curve[-1]
    )

    new_final_value = float(
        new_curve[-1]
    )

    # --------------------------------------------------------
    # TRADES
    # --------------------------------------------------------

    try:

        base_trades = int(
            turnover_summary(
                base_result["weights"]
            )["total_trades"]
        )

    except Exception:

        base_weights = np.asarray(
            base_result["weights"]
        )

        base_trades = int(
            np.sum(
                np.any(
                    np.diff(
                        base_weights,
                        axis=0
                    ) != 0,
                    axis=1
                )
            )
        )

    try:

        new_trades = int(
            turnover_summary(
                new_result["weights"]
            )["total_trades"]
        )

    except Exception:

        new_weights = np.asarray(
            new_result["weights"]
        )

        new_trades = int(
            np.sum(
                np.any(
                    np.diff(
                        new_weights,
                        axis=0
                    ) != 0,
                    axis=1
                )
            )
        )

    # --------------------------------------------------------
    # DATES
    # --------------------------------------------------------

    dates = [
        str(date)
        for date in base_result["dates"]
    ]

    # --------------------------------------------------------
    # DRAWDown SERIES
    # --------------------------------------------------------

    def drawdown_series(returns):

        curve = np.cumprod(
            1.0 + np.asarray(
                returns,
                dtype=float
            )
        )

        peak = np.maximum.accumulate(
            curve
        )

        return (
            (peak - curve)
            / peak
            * 100.0
        )

    base_drawdown_series = (
        drawdown_series(
            base_returns
        )
    )

    new_drawdown_series = (
        drawdown_series(
            new_returns
        )
    )

    # --------------------------------------------------------
    # WINNER
    # --------------------------------------------------------

    if new_total_return > base_total_return:

        winner = (
            "New Strategy — "
            "SMA20 + Momentum"
        )

    else:

        winner = (
            "Base Strategy — "
            "SMA 9/20"
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {

        "universe":
            universe,

        "dates":
            dates,

        "base_curve":
            base_curve.tolist(),

        "new_curve":
            new_curve.tolist(),

        "base_drawdown":
            base_drawdown_series.tolist(),

        "new_drawdown":
            new_drawdown_series.tolist(),

        "base_strategy": {

            "name":
                "SMA 9/20",

            "final_value":
                round(
                    base_final_value,
                    2
                ),

            "total_return":
                round(
                    base_total_return * 100,
                    2
                ),

            "max_drawdown":
                round(
                    base_max_dd * 100,
                    2
                ),

            "sharpe":
                round(
                    base_sharpe,
                    3
                ),

            "total_trades":
                base_trades
        },

        "new_strategy": {

            "name":
                "SMA20 + Momentum",

            "final_value":
                round(
                    new_final_value,
                    2
                ),

            "total_return":
                round(
                    new_total_return * 100,
                    2
                ),

            "max_drawdown":
                round(
                    new_max_dd * 100,
                    2
                ),

            "sharpe":
                round(
                    new_sharpe,
                    3
                ),

            "total_trades":
                new_trades
        },

        "winner":
            winner
    }