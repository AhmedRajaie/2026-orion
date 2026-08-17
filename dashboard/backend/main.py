"""FastAPI backend for the dashboard."""
from pathlib import Path
import sys
import time
import traceback
import logging

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tradinglab.data_feed import DataFeed
from tradinglab.features import build_dataset, feature_columns, to_sequences
from tradinglab.indicators import sma
from tradinglab.models import DeepMLP, LSTMRegressor
from tradinglab.simulator import PortfolioSimulator

app = FastAPI(title="Trading dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

feed = DataFeed.from_dir(ROOT / "data" / "egx")

logger = logging.getLogger("dashboard.backend")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def _dates_to_strings(dates) -> list[str]:
    return [date.strftime("%Y-%m-%d") for date in dates]


def _get_close_prices(symbol: str) -> tuple[list[str], np.ndarray]:
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    index = feed.symbols.index(symbol)
    return _dates_to_strings(feed.dates), feed.close[:, index]


def _serialize_series(values) -> list[float | None]:
    serialized: list[float | None] = []
    for value in values:
        if value is None:
            serialized.append(None)
            continue
        try:
            if np.isnan(value):
                serialized.append(None)
            else:
                serialized.append(float(value))
        except TypeError:
            serialized.append(float(value))
    return serialized


def _sanitize_numeric_series(values) -> list[float | None]:
    sanitized: list[float | None] = []
    for value in values:
        if value is None:
            sanitized.append(None)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            sanitized.append(None)
            continue
        if not np.isfinite(numeric):
            sanitized.append(None)
        else:
            sanitized.append(numeric)
    return sanitized


def _sanitize_price_series(values) -> list[float | None]:
    sanitized: list[float | None] = []
    for value in values:
        if value is None:
            sanitized.append(None)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            sanitized.append(None)
            continue
        if not np.isfinite(numeric) or numeric <= 0.0:
            sanitized.append(None)
        else:
            sanitized.append(numeric)
    return sanitized


def _round_metric(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _build_dataset_with_indices(symbol_index: int):
    close = feed.close[:, symbol_index]
    X_full = feature_columns(feed, symbol_index)
    y_full = np.full(feed.n_days, np.nan)
    y_full[:-1] = feed.returns[1:, symbol_index]
    valid = ~np.isnan(X_full).any(axis=1) & ~np.isnan(y_full)
    indices = np.where(valid)[0]
    return X_full[valid].astype(np.float32), y_full[valid].astype(np.float32), indices


def _build_signal_weights(preds, top_n: int = 3):
    preds = np.asarray(preds, dtype=float)
    weights = np.zeros_like(preds, dtype=float)
    if len(preds) == 0:
        return weights
    positive = np.where(preds > 0)[0]
    if len(positive) == 0:
        return weights
    top = positive[np.argsort(preds[positive])[::-1][: min(top_n, len(positive))]]
    weights[top] = 1.0 / len(top)
    return weights


def _train_mlp(X, y, epochs: int = 20, hidden: int = 16, n_hidden_layers: int = 1):
    torch.manual_seed(0)
    np.random.seed(0)
    model = DeepMLP(n_features=X.shape[1], hidden=hidden, n_hidden_layers=n_hidden_layers)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = torch.nn.MSELoss()
    Xtr = torch.tensor(X, dtype=torch.float32)
    ytr = torch.tensor(y, dtype=torch.float32)
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(Xtr), ytr)
        loss.backward()
        optimizer.step()
    return model


def _train_lstm(X, y, seq_len: int = 5, epochs: int = 60, hidden: int = 32):
    torch.manual_seed(0)
    np.random.seed(0)
    Xseq, yseq = to_sequences(X, y, seq_len)
    if len(Xseq) == 0:
        raise ValueError("Not enough data to build sequence inputs.")
    split = int(len(Xseq) * 0.7)
    X_train, y_train = Xseq[:split], yseq[:split]
    model = LSTMRegressor(n_features=Xseq.shape[2], hidden=hidden)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = torch.nn.MSELoss()
    Xtr = torch.tensor(X_train, dtype=torch.float32)
    ytr = torch.tensor(y_train, dtype=torch.float32)
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(Xtr), ytr)
        loss.backward()
        optimizer.step()
    return model, Xseq, yseq


def _regression_metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    if actual.size == 0 or pred.size == 0:
        raise ValueError("Regression metrics require non-empty prediction and target arrays.")
    if actual.shape != pred.shape:
        raise ValueError("Regression metrics require actual and predicted arrays of the same shape.")

    diff = pred - actual
    mse = np.mean(diff ** 2)
    mae = np.mean(np.abs(diff))
    rmse = np.sqrt(mse)
    ss_res = np.sum(diff ** 2)
    ss_tot = np.sum((actual - actual.mean()) ** 2)
    r2 = 1.0
    if np.isfinite(ss_tot) and ss_tot > 0:
        r2 = 1.0 - ss_res / ss_tot

    if not np.isfinite(mse) or not np.isfinite(mae) or not np.isfinite(rmse) or not np.isfinite(r2):
        raise ValueError("Regression metrics produced non-finite values.")

    return {
        "mse": float(round(float(mse), 6)),
        "rmse": float(round(float(rmse), 6)),
        "mae": float(round(float(mae), 6)),
        "r2": float(round(float(r2), 4)),
    }


def _build_prediction_portfolio(top_n: int = 3, train_frac: float = 0.7, epochs: int = 20, hidden: int = 16, n_hidden_layers: int = 1):
    predictions = []
    test_indices = None
    for asset_index in range(feed.n_assets):
        X, y, indices = _build_dataset_with_indices(asset_index)
        split = int(len(X) * train_frac)
        if split >= len(X):
            raise HTTPException(status_code=400, detail="Not enough data to train prediction portfolio.")
        if test_indices is None:
            test_indices = indices[split:]
        model = _train_mlp(X[:split], y[:split], epochs=epochs, hidden=hidden, n_hidden_layers=n_hidden_layers)
        with torch.no_grad():
            preds = model(torch.tensor(X[split:], dtype=torch.float32)).cpu().numpy()
        predictions.append(preds)

    if test_indices is None or len(test_indices) == 0:
        raise HTTPException(status_code=400, detail="No prediction test period available.")

    predictions = np.column_stack(predictions)
    weight_matrix = np.zeros((feed.n_days, feed.n_assets), dtype=float)
    for row_idx, day_idx in enumerate(test_indices):
        weight_matrix[day_idx] = _build_signal_weights(predictions[row_idx], top_n)

    start_day = int(test_indices[0])
    return weight_matrix, start_day


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/universe")
def universe() -> list[str]:
    return feed.symbols


@app.get("/prices/{symbol}")
def prices(symbol: str) -> dict[str, list[float] | list[str]]:
    dates, close_prices = _get_close_prices(symbol)
    return {"dates": dates, "close": [float(value) for value in close_prices]}


@app.get("/indicators/{symbol}")
def indicators(symbol: str, window: int = 20) -> dict[str, list[float | None] | list[str]]:
    dates, close_prices = _get_close_prices(symbol)
    values = sma(close_prices, window)
    return {"dates": dates, "sma": _serialize_series(values)}


@app.get("/strategy/{symbol}")
def strategy(symbol: str) -> dict[str, list[float] | list[str] | int]:
    dates, close_prices = _get_close_prices(symbol)
    close = [float(value) for value in close_prices]
    sma9 = sma(close_prices, 9)
    sma20 = sma(close_prices, 20)

    cash = 1000.0
    shares = 0.0
    buy_count = 0
    sell_count = 0
    peak_value = 1000.0
    max_drawdown = 0.0
    portfolio: list[float] = []
    buy_points: list[str] = []
    sell_points: list[str] = []

    for index, price in enumerate(close):
        price_value = float(price)
        signal_buy = not np.isnan(sma9[index]) and not np.isnan(sma20[index]) and sma9[index] > sma20[index]
        signal_sell = not np.isnan(sma9[index]) and not np.isnan(sma20[index]) and sma9[index] < sma20[index]

        if shares <= 1e-12 and signal_buy and cash > 0.0:
            shares = cash / price_value
            cash = 0.0
            buy_count += 1
            buy_points.append(dates[index])
        elif shares > 1e-12 and signal_sell:
            cash += shares * price_value
            shares = 0.0
            sell_count += 1
            sell_points.append(dates[index])

        portfolio_value = cash + shares * price_value
        portfolio.append(float(portfolio_value))

        if portfolio_value > peak_value:
            peak_value = portfolio_value
        else:
            drawdown = (peak_value - portfolio_value) / peak_value if peak_value > 0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return {
        "dates": dates,
        "portfolio": portfolio,
        "buy_points": buy_points,
        "sell_points": sell_points,
        "final_value": float(portfolio[-1]) if portfolio else 1000.0,
        "max_drawdown": float(max_drawdown),
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


@app.get("/prediction_portfolio")
def prediction_portfolio(
    top_n: int = 3,
    train_frac: float = 0.7,
    epochs: int = 20,
    hidden: int = 16,
    n_hidden_layers: int = 1,
    commission: float = 0.0,
) -> dict[str, object]:
    weight_matrix, start_day = _build_prediction_portfolio(
        top_n=top_n,
        train_frac=train_frac,
        epochs=epochs,
        hidden=hidden,
        n_hidden_layers=n_hidden_layers,
    )
    sim = PortfolioSimulator(feed, benchmark="equal_weight", commission=commission)
    end_day = feed.n_days - 1
    result = sim.run(weight_matrix, start=start_day - 1, end=end_day)
    return {
        "dates": _dates_to_strings(result["dates"]),
        "portfolio": [float(x) for x in result["portfolio"]],
        "benchmark": [float(x) for x in result["benchmark"]],
        "top_n": top_n,
        "strategy": "prediction_portfolio",
    }


# @app.get("/model_compare")
# def model_compare(symbol: str = "ABUK", seq_len: int = 5, hidden: int = 16) -> dict[str, object]:
#     request_start = time.time()
#     stage = "validate input"
#     logger.info("Incoming /model_compare request: symbol=%s, seq_len=%s, hidden=%s", symbol, seq_len, hidden)
#     try:
#         if symbol not in feed.symbols:
#             raise HTTPException(status_code=404, detail="symbol not found")
#         symbol_index = feed.symbols.index(symbol)

#         X, y, _ = _build_dataset_with_indices(symbol_index)
#         if len(X) < 2:
#             raise HTTPException(status_code=400, detail="Not enough cleaned data rows for model comparison.")

#         split = int(len(X) * 0.7)
#         if split < 1 or split >= len(X):
#             raise HTTPException(status_code=400, detail="Not enough data for a valid train/test split for model comparison.")

#         stage = "train mlp"
#         model = _train_mlp(X[:split], y[:split], epochs=20, hidden=hidden, n_hidden_layers=1)
#         logger.info("MLP model trained for symbol=%s; train rows=%s, test rows=%s", symbol, split, len(X) - split)

#         mlp_pred_train = model(torch.tensor(X[:split], dtype=torch.float32)).cpu().numpy()
#         mlp_pred_test = model(torch.tensor(X[split:], dtype=torch.float32)).cpu().numpy()
#         mlp_train_metrics = _regression_metrics(y[:split], mlp_pred_train)
#         mlp_test_metrics = _regression_metrics(y[split:], mlp_pred_test)

#         stage = "train lstm"

@app.get("/model_compare")
def model_compare(
    symbol: str = "ABUK",
    seq_len: int = 5,
    hidden: int = 16,
) -> dict[str, object]:

    request_start = time.time()
    stage = "validate input"

    logger.info(
        "Incoming /model_compare request: symbol=%s, seq_len=%s, hidden=%s",
        symbol,
        seq_len,
        hidden,
    )

    try:

        # ---------------------------------------------------------
        # Validate symbol
        # ---------------------------------------------------------

        if symbol not in feed.symbols:
            raise HTTPException(
                status_code=404,
                detail="symbol not found",
            )

        symbol_index = feed.symbols.index(symbol)

        # ---------------------------------------------------------
        # Build dataset
        # ---------------------------------------------------------

        X, y, _ = _build_dataset_with_indices(symbol_index)

        if len(X) < 2:
            raise HTTPException(
                status_code=400,
                detail="Not enough cleaned data rows for model comparison.",
            )

        split = int(len(X) * 0.7)

        if split < 1 or split >= len(X):
            raise HTTPException(
                status_code=400,
                detail="Not enough data for a valid train/test split.",
            )

        # ---------------------------------------------------------
        # Train MLP
        # ---------------------------------------------------------

        stage = "train mlp"

        model = _train_mlp(
            X[:split],
            y[:split],
            epochs=20,
            hidden=hidden,
            n_hidden_layers=1,
        )

        logger.info(
            "MLP model trained for symbol=%s; train rows=%s; test rows=%s",
            symbol,
            split,
            len(X) - split,
        )

        # ---------------------------------------------------------
        # IMPORTANT
        # Switch model into inference mode
        # ---------------------------------------------------------

        model.eval()

        # ---------------------------------------------------------
        # Predict WITHOUT gradients
        # ---------------------------------------------------------

        with torch.no_grad():

            mlp_pred_train = model(
                torch.tensor(
                    X[:split],
                    dtype=torch.float32,
                )
            ).cpu().numpy()

            mlp_pred_test = model(
                torch.tensor(
                    X[split:],
                    dtype=torch.float32,
                )
            ).cpu().numpy()

        # ---------------------------------------------------------
        # Metrics
        # ---------------------------------------------------------

        mlp_train_metrics = _regression_metrics(
            y[:split],
            mlp_pred_train,
        )

        mlp_test_metrics = _regression_metrics(
            y[split:],
            mlp_pred_test,
        )

        # ---------------------------------------------------------
        # Continue with LSTM
        # ---------------------------------------------------------

        stage = "train lstm"

        try:

            lstm_model, Xseq, yseq = _train_lstm(
                X,
                y,
                seq_len=seq_len,
                epochs=60,
                hidden=hidden,
            )

        except ValueError as exc:

            raise HTTPException(
                status_code=400,
                detail=str(exc),
            )

        # ---------------------------------------------------------
        # Validate sequence dataset
        # ---------------------------------------------------------

        if len(Xseq) < 2:
            raise HTTPException(
                status_code=400,
                detail="Not enough LSTM sequence rows for model comparison.",
            )

        split_seq = int(len(Xseq) * 0.7)

        if split_seq < 1 or split_seq >= len(Xseq):
            raise HTTPException(
                status_code=400,
                detail="Not enough LSTM data for a valid train/test split.",
            )

        logger.info(
            "LSTM model trained for symbol=%s; sequence rows=%s; train rows=%s; test rows=%s",
            symbol,
            len(Xseq),
            split_seq,
            len(Xseq) - split_seq,
        )

        # ---------------------------------------------------------
        # IMPORTANT
        # Switch LSTM into evaluation mode
        # ---------------------------------------------------------

        lstm_model.eval()

        # ---------------------------------------------------------
        # Predict WITHOUT gradients
        # ---------------------------------------------------------

        with torch.no_grad():

            lstm_pred_train = lstm_model(
                torch.tensor(
                    Xseq[:split_seq],
                    dtype=torch.float32,
                )
            ).cpu().numpy()

            lstm_pred_test = lstm_model(
                torch.tensor(
                    Xseq[split_seq:],
                    dtype=torch.float32,
                )
            ).cpu().numpy()

        # ---------------------------------------------------------
        # Calculate metrics
        # ---------------------------------------------------------

        lstm_train_metrics = _regression_metrics(
            yseq[:split_seq],
            lstm_pred_train,
        )

        lstm_test_metrics = _regression_metrics(
            yseq[split_seq:],
            lstm_pred_test,
        )

        # ---------------------------------------------------------
        # Build response
        # ---------------------------------------------------------

        response = {
            "success": True,
            "symbol": symbol,
            "mlp": {
                "train": mlp_train_metrics,
                "test": mlp_test_metrics,
            },
            "lstm": {
                "train": lstm_train_metrics,
                "test": lstm_test_metrics,
            },
        }

        duration = time.time() - request_start

        logger.info(
            "Model comparison completed for symbol=%s in %.3fs",
            symbol,
            duration,
        )

        return response

    except HTTPException:

        logger.warning(
            "Model comparison failed at stage=%s for symbol=%s",
            stage,
            symbol,
        )

        raise

    except Exception as exc:

        tb = traceback.format_exc()

        logger.exception(
            "Unexpected error in /model_compare at stage=%s for symbol=%s",
            stage,
            symbol,
        )

        return {
            "success": False,
            "error": str(exc),
            "traceback": tb,
            "stage": stage,
        }

    #     try:
    #         lstm_model, Xseq, yseq = _train_lstm(X, y, seq_len=seq_len, epochs=60, hidden=hidden)
    #     except ValueError as exc:
    #         raise HTTPException(status_code=400, detail=str(exc))

    #     if len(Xseq) < 2:
    #         raise HTTPException(status_code=400, detail="Not enough LSTM sequence rows for model comparison.")

    #     split_seq = int(len(Xseq) * 0.7)
    #     if split_seq < 1 or split_seq >= len(Xseq):
    #         raise HTTPException(status_code=400, detail="Not enough LSTM data for a valid train/test split.")

    #     logger.info("LSTM model trained for symbol=%s; sequence rows=%s, train rows=%s, test rows=%s", symbol, len(Xseq), split_seq, len(Xseq) - split_seq)
    #     lstm_pred_train = lstm_model(torch.tensor(Xseq[:split_seq], dtype=torch.float32)).cpu().numpy()
    #     lstm_pred_test = lstm_model(torch.tensor(Xseq[split_seq:], dtype=torch.float32)).cpu().numpy()
    #     lstm_train_metrics = _regression_metrics(yseq[:split_seq], lstm_pred_train)
    #     lstm_test_metrics = _regression_metrics(yseq[split_seq:], lstm_pred_test)

    #     response = {
    #         "success": True,
    #         "symbol": symbol,
    #         "mlp": {
    #             "train": mlp_train_metrics,
    #             "test": mlp_test_metrics,
    #         },
    #         "lstm": {
    #             "train": lstm_train_metrics,
    #             "test": lstm_test_metrics,
    #         },
    #     }
    #     duration = time.time() - request_start
    #     logger.info("Model comparison completed for symbol=%s in %.3fs", symbol, duration)
    #     return response
    # except HTTPException:
    #     logger.warning("Model comparison failed at stage=%s for symbol=%s", stage, symbol)
    #     raise
    # except Exception as exc:
    #     tb = traceback.format_exc()
    #     logger.exception("Unexpected error in /model_compare at stage=%s for symbol=%s", stage, symbol)
    #     return {
    #         "success": False,
    #         "error": str(exc),
    #         "traceback": tb,
    #         "stage": stage,
    #     }


@app.get("/backtest/{symbol}")
def backtest(
    symbol: str,
    fast_window: int = 9,
    slow_window: int = 20,
    initial_cash: float = 1000.0,
) -> dict[str, object]:
    if symbol not in feed.symbols:
        raise HTTPException(status_code=404, detail="symbol not found")
    if fast_window < 1:
        raise HTTPException(status_code=400, detail="fast_window must be at least 1")
    if slow_window < 2:
        raise HTTPException(status_code=400, detail="slow_window must be at least 2")
    if fast_window >= slow_window:
        raise HTTPException(status_code=400, detail="fast_window must be smaller than slow_window")
    if initial_cash <= 0.0:
        raise HTTPException(status_code=400, detail="initial_cash must be greater than zero")

    symbol_index = feed.symbols.index(symbol)
    dates = _dates_to_strings(feed.dates)
    close_prices = feed.close[:, symbol_index]
    close_series = _sanitize_price_series(close_prices)
    fast_ma_series = _sanitize_numeric_series(sma(close_prices, fast_window))
    slow_ma_series = _sanitize_numeric_series(sma(close_prices, slow_window))

    cash = float(initial_cash)
    shares = 0
    portfolio_values: list[float] = []
    cash_history: list[float] = []
    shares_history: list[float] = []
    buy_markers: list[float | None] = [None] * len(dates)
    sell_markers: list[float | None] = [None] * len(dates)
    trades: list[dict[str, object]] = []
    last_portfolio_value = float(initial_cash)

    for index, price in enumerate(close_series):
        if price is not None and price > 0.0:
            fast_previous = fast_ma_series[index - 1] if index > 0 else None
            slow_previous = slow_ma_series[index - 1] if index > 0 else None

            if shares == 0 and fast_previous is not None and slow_previous is not None and fast_previous > slow_previous:
                shares_to_buy = int(cash // price)
                if shares_to_buy > 0:
                    cash -= shares_to_buy * price
                    shares += shares_to_buy
                    buy_markers[index] = price
                    trades.append(
                        {
                            "type": "BUY",
                            "date": dates[index],
                            "price": price,
                            "shares": shares_to_buy,
                            "cash_after": cash,
                            "portfolio_value_after": cash + shares * price,
                        }
                    )
            elif shares > 0 and fast_previous is not None and slow_previous is not None and fast_previous < slow_previous:
                cash += shares * price
                sell_markers[index] = price
                trades.append(
                    {
                        "type": "SELL",
                        "date": dates[index],
                        "price": price,
                        "shares": shares,
                        "cash_after": cash,
                        "portfolio_value_after": cash + shares * price,
                    }
                )
                shares = 0

            portfolio_value = cash + shares * price
        else:
            portfolio_value = last_portfolio_value

        portfolio_values.append(float(portfolio_value))
        cash_history.append(float(cash))
        shares_history.append(float(shares))
        last_portfolio_value = float(portfolio_value)

    if shares > 0:
        final_valid_price = None
        for price in reversed(close_series):
            if price is not None and price > 0.0:
                final_valid_price = price
                break
        if final_valid_price is not None:
            last_portfolio_value = cash + shares * final_valid_price
            portfolio_values[-1] = float(last_portfolio_value)

    buy_hold_cash = float(initial_cash)
    buy_hold_shares = 0
    buy_hold_values: list[float] = []
    last_buy_hold_value = float(initial_cash)

    for index, price in enumerate(close_series):
        if buy_hold_shares == 0 and price is not None and price > 0.0:
            shares_to_buy = int(buy_hold_cash // price)
            if shares_to_buy > 0:
                buy_hold_cash -= shares_to_buy * price
                buy_hold_shares += shares_to_buy

        if buy_hold_shares > 0 and price is not None and price > 0.0:
            value = buy_hold_cash + buy_hold_shares * price
            last_buy_hold_value = float(value)
        else:
            value = float(last_buy_hold_value)

        buy_hold_values.append(float(value))

    running_peak = float(initial_cash)
    max_drawdown_egp = 0.0
    max_drawdown_pct = 0.0
    for value in portfolio_values:
        if value > running_peak:
            running_peak = float(value)
        drawdown_egp = running_peak - value
        drawdown_pct = (drawdown_egp / running_peak * 100.0) if running_peak > 0.0 else 0.0
        if drawdown_egp > max_drawdown_egp:
            max_drawdown_egp = float(drawdown_egp)
        if drawdown_pct > max_drawdown_pct:
            max_drawdown_pct = float(drawdown_pct)

    final_portfolio_value = float(portfolio_values[-1]) if portfolio_values else float(initial_cash)
    initial_portfolio_value = float(initial_cash)
    profit_loss_egp = float(final_portfolio_value - initial_portfolio_value)
    total_return_pct = float((final_portfolio_value / initial_portfolio_value - 1.0) * 100.0) if initial_portfolio_value > 0.0 else 0.0

    buy_operations = sum(1 for trade in trades if trade["type"] == "BUY")
    sell_operations = sum(1 for trade in trades if trade["type"] == "SELL")
    completed_trades = sell_operations
    exposure_days = sum(1 for shares in shares_history if shares > 0)
    number_of_valid_days = sum(1 for price in close_series if price is not None and price > 0.0)
    exposure_pct = float((exposure_days / number_of_valid_days * 100.0) if number_of_valid_days > 0 else 0.0)

    buy_hold_final_value = float(buy_hold_values[-1]) if buy_hold_values else float(initial_cash)
    buy_hold_return_pct = float((buy_hold_final_value / initial_portfolio_value - 1.0) * 100.0) if initial_portfolio_value > 0.0 else 0.0
    excess_return_pct_points = float(total_return_pct - buy_hold_return_pct)

    chart_arrays = [
        close_series,
        fast_ma_series,
        slow_ma_series,
        buy_markers,
        sell_markers,
        portfolio_values,
        cash_history,
        shares_history,
        buy_hold_values,
    ]
    if not all(len(arr) == len(dates) for arr in chart_arrays):
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if cash < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if shares < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if abs(buy_operations - sell_operations) > 1:
        raise HTTPException(status_code=500, detail="Backtest validation failed")
    if final_portfolio_value < -1e-9:
        raise HTTPException(status_code=500, detail="Backtest validation failed")

    return {
        "symbol": symbol,
        "parameters": {
            "fast_window": fast_window,
            "slow_window": slow_window,
            "initial_cash": float(initial_cash),
        },
        "dates": dates,
        "close": close_series,
        "fast_ma": fast_ma_series,
        "slow_ma": slow_ma_series,
        "buy_markers": buy_markers,
        "sell_markers": sell_markers,
        "portfolio_values": portfolio_values,
        "buy_hold_values": buy_hold_values,
        "cash_history": cash_history,
        "shares_history": shares_history,
        "trades": trades,
        "kpis": {
            "initial_portfolio_value": _round_metric(initial_portfolio_value),
            "final_portfolio_value": _round_metric(final_portfolio_value),
            "profit_loss_egp": _round_metric(profit_loss_egp),
            "total_return_pct": _round_metric(total_return_pct),
            "maximum_drawdown_egp": _round_metric(max_drawdown_egp),
            "maximum_drawdown_pct": _round_metric(max_drawdown_pct),
            "buy_operations": buy_operations,
            "sell_operations": sell_operations,
            "total_operations": buy_operations + sell_operations,
            "completed_trades": completed_trades,
            "final_cash": _round_metric(cash),
            "final_shares": round(float(shares), 2),
            "current_position": "Invested" if shares > 0 else "Cash",
            "exposure_days": exposure_days,
            "exposure_pct": _round_metric(exposure_pct),
            "buy_hold_final_value": _round_metric(buy_hold_final_value),
            "buy_hold_return_pct": _round_metric(buy_hold_return_pct),
            "excess_return_pct_points": _round_metric(excess_return_pct_points),
        },
    }
