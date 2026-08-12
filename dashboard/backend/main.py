from pathlib import Path
import json
import sys

import numpy as np

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


# ============================================================
# PROJECT PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

SRC_DIR = BASE_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ============================================================
# TRADINGLAB
# ============================================================

from tradinglab.data_feed import DataFeed
from tradinglab.simulator import PortfolioSimulator
from tradinglab.backtester import run_backtest
from tradinglab.strategies.sma import sma_crossover_weights
from tradinglab.charting import turnover_summary


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Trading Dashboard API",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATA
# ============================================================

DATA_PATH = BASE_DIR / "data" / "egx"

RESULTS_PATH = (
    BASE_DIR
    / "dashboard"
    / "data"
    / "model_results.json"
)


# ============================================================
# LOAD EGX DATA
# ============================================================

try:

    feed = DataFeed.from_dir(
        str(DATA_PATH)
    )

    print(
        "Loaded stocks:",
        feed.symbols
    )

except Exception as e:

    feed = None

    print(
        "ERROR loading DataFeed:",
        e
    )


# ============================================================
# BACKTEST SETTINGS
# ============================================================

START_CAPITAL = 1000.0

LOOKBACK = 30


# ============================================================
# NEW STRATEGY
# SMA20 + MOMENTUM
# ============================================================

def momentum_sma_weights(
    observation,
    sma_window=20,
    momentum_window=5
):
    """
    New Strategy:

    Select a stock when:

    1. Current close > SMA20
    2. 5-day momentum > 0

    Selected stocks receive equal weights.

    If no stock qualifies,
    hold cash.
    """

    observation = np.asarray(
        observation,
        dtype=float
    )

    # Expected shape:
    #
    # (number_of_stocks,
    #  lookback_days,
    #  features)

    n_assets, n_days, n_features = (
        observation.shape
    )

    # TradingLab OHLCV-style observation:
    # close = feature index 3

    CLOSE_INDEX = 3

    prices = observation[
        :,
        :,
        CLOSE_INDEX
    ]

    # --------------------------------------------------------
    # Check enough history
    # --------------------------------------------------------

    if n_days < max(
        sma_window,
        momentum_window + 1
    ):
        return np.zeros(
            n_assets,
            dtype=float
        )

    # --------------------------------------------------------
    # Current prices
    # --------------------------------------------------------

    current_prices = prices[:, -1]

    # --------------------------------------------------------
    # SMA20
    # --------------------------------------------------------

    sma20 = np.mean(
        prices[:, -sma_window:],
        axis=1
    )

    # --------------------------------------------------------
    # 5-day momentum
    # --------------------------------------------------------

    previous_prices = prices[
        :,
        -(momentum_window + 1)
    ]

    momentum = (
        current_prices / previous_prices
    ) - 1

    # --------------------------------------------------------
    # Conditions
    # --------------------------------------------------------

    above_sma = (
        current_prices > sma20
    )

    positive_momentum = (
        momentum > 0
    )

    selected = (
        above_sma
        &
        positive_momentum
    )

    # --------------------------------------------------------
    # Create weights
    # --------------------------------------------------------

    weights = np.zeros(
        n_assets,
        dtype=float
    )

    number_selected = np.sum(
        selected
    )

    if number_selected > 0:

        weights[selected] = (
            1.0 / number_selected
        )

    return weights


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok"
    }


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "message":
            "Trading Dashboard API is running",

        "health":
            "/health",

        "symbols":
            "/symbols",

        "stock":
            "/stock/{symbol}",

        "strategy_comparison":
            "/strategy-comparison",

        "model_results":
            "/model-results",
    }


# ============================================================
# SYMBOLS
# ============================================================

@app.get("/symbols")
def get_symbols():

    if feed is None:

        raise HTTPException(
            status_code=500,
            detail=(
                "DataFeed could not be loaded."
            )
        )

    return {
        "symbols":
            list(feed.symbols)
    }


# ============================================================
# STOCK DATA
# ============================================================

@app.get("/stock/{symbol}")
def get_stock(symbol: str):

    if feed is None:

        raise HTTPException(
            status_code=500,
            detail=(
                "DataFeed could not be loaded."
            )
        )

    symbol = symbol.upper()

    if symbol not in feed.symbols:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Stock {symbol} not found."
            )
        )

    asset = list(
        feed.symbols
    ).index(symbol)

    # --------------------------------------------------------
    # Closing prices
    # --------------------------------------------------------

    close = feed.close[:, asset]

    prices = []

    for i, value in enumerate(close):

        if value is None:
            continue

        try:

            price = float(value)

            if price != price:
                continue

            prices.append(
                {
                    "day": i,
                    "close": price
                }
            )

        except Exception:
            continue

    # --------------------------------------------------------
    # Basic indicators
    # --------------------------------------------------------

    closes = [
        x["close"]
        for x in prices
    ]

    sma9 = []

    sma20 = []

    for i in range(
        len(closes)
    ):

        # SMA 9

        if i < 8:

            sma9.append(None)

        else:

            sma9.append(
                sum(
                    closes[
                        i - 8:i + 1
                    ]
                ) / 9
            )

        # SMA 20

        if i < 19:

            sma20.append(None)

        else:

            sma20.append(
                sum(
                    closes[
                        i - 19:i + 1
                    ]
                ) / 20
            )

    # --------------------------------------------------------
    # Add indicators
    # --------------------------------------------------------

    for i in range(
        len(prices)
    ):

        prices[i]["sma9"] = (
            sma9[i]
        )

        prices[i]["sma20"] = (
            sma20[i]
        )

    # --------------------------------------------------------
    # Current price
    # --------------------------------------------------------

    current_price = (
        closes[-1]
        if closes
        else None
    )

    return {
        "symbol": symbol,

        "current_price":
            current_price,

        "data":
            prices
    }


# ============================================================
# STRATEGY COMPARISON
# ============================================================

@app.get("/strategy-comparison")
def strategy_comparison():

    if feed is None:

        raise HTTPException(
            status_code=500,
            detail=(
                "DataFeed could not be loaded."
            )
        )

    try:

        print(
            "Running strategy comparison..."
        )

        # ----------------------------------------------------
        # SIMULATOR
        # ----------------------------------------------------

        sim = PortfolioSimulator(
            feed
        )

        # ----------------------------------------------------
        # BASE STRATEGY
        # SMA 9/20
        # ----------------------------------------------------

        base_result = run_backtest(
            sim,

            lambda observation:
                sma_crossover_weights(
                    observation,
                    9,
                    20
                ),

            lookback=LOOKBACK
        )

        # ----------------------------------------------------
        # NEW STRATEGY
        # SMA20 + MOMENTUM
        # ----------------------------------------------------

        new_result = run_backtest(
            sim,

            momentum_sma_weights,

            lookback=LOOKBACK
        )

        # ====================================================
        # HELPER FUNCTIONS
        # ====================================================

        def calculate_total_return(
            returns
        ):

            returns = np.asarray(
                returns,
                dtype=float
            )

            return float(
                np.prod(
                    1 + returns
                ) - 1
            )


        def calculate_max_drawdown(
            returns
        ):

            returns = np.asarray(
                returns,
                dtype=float
            )

            curve = np.cumprod(
                1 + returns
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


        def calculate_sharpe(
            returns
        ):

            returns = np.asarray(
                returns,
                dtype=float
            )

            if (
                len(returns) > 1
                and np.std(returns) > 0
            ):

                return float(
                    (
                        np.mean(returns)
                        /
                        np.std(returns)
                    )
                    *
                    np.sqrt(252)
                )

            return 0.0


        # ====================================================
        # BASE METRICS
        # ====================================================

        base_returns = np.asarray(
            base_result[
                "portfolio_returns"
            ],
            dtype=float
        )

        base_portfolio = np.asarray(
            base_result[
                "portfolio"
            ],
            dtype=float
        )

        base_final_value = float(
            base_portfolio[-1]
            *
            START_CAPITAL
        )

        base_total_return = (
            calculate_total_return(
                base_returns
            )
        )

        base_max_drawdown = (
            calculate_max_drawdown(
                base_returns
            )
        )

        base_sharpe = (
            calculate_sharpe(
                base_returns
            )
        )

        base_summary = (
            turnover_summary(
                base_result[
                    "weights"
                ]
            )
        )

        base_total_trades = int(
            base_summary[
                "total_trades"
            ]
        )


        # ====================================================
        # NEW STRATEGY METRICS
        # ====================================================

        new_returns = np.asarray(
            new_result[
                "portfolio_returns"
            ],
            dtype=float
        )

        new_portfolio = np.asarray(
            new_result[
                "portfolio"
            ],
            dtype=float
        )

        new_final_value = float(
            new_portfolio[-1]
            *
            START_CAPITAL
        )

        new_total_return = (
            calculate_total_return(
                new_returns
            )
        )

        new_max_drawdown = (
            calculate_max_drawdown(
                new_returns
            )
        )

        new_sharpe = (
            calculate_sharpe(
                new_returns
            )
        )

        new_summary = (
            turnover_summary(
                new_result[
                    "weights"
                ]
            )
        )

        new_total_trades = int(
            new_summary[
                "total_trades"
            ]
        )


        # ====================================================
        # EQUITY CURVES
        # ====================================================

        base_curve = (
            base_portfolio
            *
            START_CAPITAL
        )

        new_curve = (
            new_portfolio
            *
            START_CAPITAL
        )


        # ====================================================
        # DRAWDOWN CURVES
        # ====================================================

        base_equity = np.cumprod(
            1 + base_returns
        )

        new_equity = np.cumprod(
            1 + new_returns
        )

        base_peak = np.maximum.accumulate(
            base_equity
        )

        new_peak = np.maximum.accumulate(
            new_equity
        )

        base_drawdown = (
            base_peak - base_equity
        ) / base_peak

        new_drawdown = (
            new_peak - new_equity
        ) / new_peak


        # ====================================================
        # DATES
        # ====================================================

        dates = [
            str(date)
            for date in
            base_result["dates"]
        ]


        # ====================================================
        # WINNER
        # ====================================================

        if (
            base_final_value
            >
            new_final_value
        ):

            winner = (
                "Base Strategy — SMA 9/20"
            )

        elif (
            new_final_value
            >
            base_final_value
        ):

            winner = (
                "New Strategy — SMA20 + Momentum"
            )

        else:

            winner = (
                "Both strategies have equal "
                "final value."
            )


        # ====================================================
        # PRINT RESULTS
        # ====================================================

        print(
            "Base final value:",
            base_final_value
        )

        print(
            "Base total return:",
            base_total_return
        )

        print(
            "Base max drawdown:",
            base_max_drawdown
        )

        print(
            "Base Sharpe:",
            base_sharpe
        )

        print(
            "Base trades:",
            base_total_trades
        )

        print(
            "New final value:",
            new_final_value
        )

        print(
            "New total return:",
            new_total_return
        )

        print(
            "New max drawdown:",
            new_max_drawdown
        )

        print(
            "New Sharpe:",
            new_sharpe
        )

        print(
            "New trades:",
            new_total_trades
        )


        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "status": "ok",

            "settings": {

                "start_capital":
                    START_CAPITAL,

                "lookback":
                    LOOKBACK
            },

            "base_strategy": {

                "name":
                    "SMA 9/20",

                "final_value":
                    base_final_value,

                "total_return":
                    base_total_return,

                "max_drawdown":
                    base_max_drawdown,

                "sharpe":
                    base_sharpe,

                "total_trades":
                    base_total_trades
            },

            "new_strategy": {

                "name":
                    "SMA20 + Momentum",

                "final_value":
                    new_final_value,

                "total_return":
                    new_total_return,

                "max_drawdown":
                    new_max_drawdown,

                "sharpe":
                    new_sharpe,

                "total_trades":
                    new_total_trades
            },

            "winner":
                winner,

            "dates":
                dates,

            "curves": {

                "base":
                    base_curve.tolist(),

                "new":
                    new_curve.tolist()
            },

            "drawdowns": {

                "base":
                    (
                        -base_drawdown
                        * 100
                    ).tolist(),

                "new":
                    (
                        -new_drawdown
                        * 100
                    ).tolist()
            }
        }


    except Exception as e:

        print(
            "Strategy comparison error:",
            repr(e)
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# MODEL RESULTS
# ============================================================

@app.get("/model-results")
def model_results():

    if not RESULTS_PATH.exists():

        return {

            "status":
                "not_found",

            "message":
                "model_results.json "
                "has not been created yet.",

            "train_losses":
                [],

            "test_losses":
                [],

            "predictions":
                [],

            "actual":
                []
        }

    try:

        with open(
            RESULTS_PATH,
            "r"
        ) as f:

            results = json.load(f)

        return {

            "status":
                "ok",

            **results
        }

    except Exception as e:

        return {

            "status":
                "error",

            "message":
                str(e),

            "train_losses":
                [],

            "test_losses":
                [],

            "predictions":
                [],

            "actual":
                []
        }