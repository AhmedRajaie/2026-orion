"""
indicators.py — technical indicators. YOURS to write in week 1.

Pure functions: series in, series out. Same length as input; positions without
enough history are NaN. The provided observation.py uses these same ideas to
build the agent's state in week 3.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def sma(prices: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average over `window` days."""
    # ---8<--- solution
    prices = np.asarray(prices, dtype=float)
    out = np.full_like(prices, np.nan)
    for i in range(window - 1, len(prices)):
        out[i] = prices[i - window + 1 : i + 1].mean()
    return out
    # ---8<--- end


def ema(prices: np.ndarray, window: int) -> np.ndarray:
    """Exponential moving average. Weights recent prices more heavily."""
    # ---8<--- solution
    prices = np.asarray(prices, dtype=float)
    out = np.full_like(prices, np.nan)
    alpha = 2.0 / (window + 1.0)
    out[window - 1] = prices[:window].mean()
    for i in range(window, len(prices)):
        out[i] = alpha * prices[i] + (1 - alpha) * out[i - 1]
    return out
    # ---8<--- end


def rsi(prices: np.ndarray, window: int = 14) -> np.ndarray:
    """Relative Strength Index in [0, 100]."""
    # ---8<--- solution
    prices = np.asarray(prices, dtype=float)
    out = np.full_like(prices, np.nan)
    delta = np.diff(prices)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    for i in range(window, len(prices)):
        avg_gain = gains[i - window : i].mean()
        avg_loss = losses[i - window : i].mean()
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out
    # ---8<--- end


def rolling_volatility(returns: np.ndarray, window: int = 20) -> np.ndarray:
    """Rolling standard deviation of returns — a simple risk measure."""
    # ---8<--- solution
    returns = np.asarray(returns, dtype=float)
    out = np.full_like(returns, np.nan)
    for i in range(window - 1, len(returns)):
        out[i] = returns[i - window + 1 : i + 1].std()
    return out
    # ---8<--- end


# ---- dashboard indicators panel: MACD and Bollinger Bands ----

def macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, and histogram. Positions without enough
    history for the slow EMA are NaN."""
    prices = pd.Series(np.asarray(prices, dtype=float))
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_line[: slow - 1] = np.nan
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.to_numpy(), signal_line.to_numpy(), histogram.to_numpy()


def bollinger_bands(prices: np.ndarray, window: int = 20, num_std: float = 2.0):
    """Rolling mean with +/- num_std standard-deviation bands."""
    prices = pd.Series(np.asarray(prices, dtype=float))
    mid = prices.rolling(window).mean()
    std = prices.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid.to_numpy(), upper.to_numpy(), lower.to_numpy()


# ---- dashboard indicators panel: full OHLCV set ----
# These operate on their own fixed OHLC(V) columns, not the dashboard's
# price-field selector — that's standard: an ATR or Stochastic is always
# defined off actual high/low/close, the way TradingView itself only offers
# a "Source" override on single-line indicators (SMA/EMA/RSI/MACD/Bollinger).

def stochastic_oscillator(high: np.ndarray, low: np.ndarray, close: np.ndarray, k_window: int = 14, d_window: int = 3):
    """%K (position of close within the recent high-low range) and its
    %D signal line (%K's own SMA)."""
    high = pd.Series(np.asarray(high, dtype=float))
    low = pd.Series(np.asarray(low, dtype=float))
    close = pd.Series(np.asarray(close, dtype=float))
    lowest_low = low.rolling(k_window).min()
    highest_high = high.rolling(k_window).max()
    percent_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    percent_d = percent_k.rolling(d_window).mean()
    return percent_k.to_numpy(), percent_d.to_numpy()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> np.ndarray:
    """Average True Range — Wilder's smoothed average of the true range."""
    high = pd.Series(np.asarray(high, dtype=float))
    low = pd.Series(np.asarray(low, dtype=float))
    close = pd.Series(np.asarray(close, dtype=float))
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean().to_numpy()


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14):
    """Average Directional Index (trend strength) plus its +DI/-DI inputs
    (trend direction), Wilder's original smoothing."""
    high = pd.Series(np.asarray(high, dtype=float))
    low = pd.Series(np.asarray(low, dtype=float))
    close = pd.Series(np.asarray(close, dtype=float))
    prev_high, prev_low = high.shift(1), low.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0))
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0))

    smoothed_atr = _true_range(high, low, close).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / smoothed_atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / smoothed_atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_line = dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    return adx_line.to_numpy(), plus_di.to_numpy(), minus_di.to_numpy()


def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, window: int = 20) -> np.ndarray:
    """Volume-weighted average price over a rolling `window`.

    A 'true' VWAP anchors to a trading session, which needs intraday bars;
    these are daily bars, so this is the standard adaptation for daily
    data — a rolling window of typical price weighted by volume.
    """
    high = pd.Series(np.asarray(high, dtype=float))
    low = pd.Series(np.asarray(low, dtype=float))
    close = pd.Series(np.asarray(close, dtype=float))
    volume = pd.Series(np.asarray(volume, dtype=float))
    typical_price = (high + low + close) / 3.0
    pv = typical_price * volume
    return (pv.rolling(window).sum() / volume.rolling(window).sum()).to_numpy()


def ichimoku(high: np.ndarray, low: np.ndarray, close: np.ndarray, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    """Ichimoku Cloud: tenkan-sen, kijun-sen, the two senkou spans (the
    'cloud', projected `kijun` bars forward), and the chikou span (close
    shifted `kijun` bars back)."""
    high = pd.Series(np.asarray(high, dtype=float))
    low = pd.Series(np.asarray(low, dtype=float))
    close = pd.Series(np.asarray(close, dtype=float))

    def midpoint(window):
        return (high.rolling(window).max() + low.rolling(window).min()) / 2.0

    tenkan_sen = midpoint(tenkan)
    kijun_sen = midpoint(kijun)
    senkou_span_a = ((tenkan_sen + kijun_sen) / 2.0).shift(kijun)
    senkou_span_b = midpoint(senkou_b).shift(kijun)
    chikou_span = close.shift(-kijun)
    return (
        tenkan_sen.to_numpy(),
        kijun_sen.to_numpy(),
        senkou_span_a.to_numpy(),
        senkou_span_b.to_numpy(),
        chikou_span.to_numpy(),
    )


def parabolic_sar(high: np.ndarray, low: np.ndarray, step: float = 0.02, max_step: float = 0.2) -> np.ndarray:
    """Parabolic SAR (stop-and-reverse) trend-following dots. Inherently
    iterative — each bar's value depends on the trend state carried from
    the previous one, so unlike the rest of this module it can't be a
    vectorized rolling formula."""
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(high)
    sar = np.full(n, np.nan)
    if n < 2:
        return sar

    uptrend = True
    af = step
    ep = high[0]
    sar[0] = low[0]

    for i in range(1, n):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1])

        if uptrend:
            sar[i] = min(sar[i], low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if low[i] < sar[i]:
                uptrend, sar[i], ep, af = False, ep, low[i], step
            elif high[i] > ep:
                ep, af = high[i], min(af + step, max_step)
        else:
            sar[i] = max(sar[i], high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if high[i] > sar[i]:
                uptrend, sar[i], ep, af = True, ep, high[i], step
            elif low[i] < ep:
                ep, af = low[i], min(af + step, max_step)

    return sar


def obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """On-Balance Volume — running total of volume signed by the day's
    close-to-close direction."""
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    direction = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(direction * volume)
