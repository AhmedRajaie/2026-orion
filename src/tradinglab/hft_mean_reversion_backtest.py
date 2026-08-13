"""
hft_mean_reversion_backtest.py — "HFT Mean-Reversion Rebound", a discrete,
fixed-notional multi-symbol strategy. Doesn't fit PortfolioSimulator (which
assumes continuous non-negative weights summing to 1); this is closer in
shape to single_asset_backtest.py's explicit cash/shares loop, just run
across every symbol in a universe at once against one shared cash pool.

Despite the name, this trades on DAILY bars (data/egx has no intraday data),
so the finest possible "drop within a lookback window" is a 1-day close-to-
close return. That's what's implemented — a daily, not intraday, strategy.

Rule set (see conversation for the decisions behind each):
  Entry:    symbol is flat, and today's 1-day return <= -drop_pct
            -> buy `notional` worth of shares. reference_price = yesterday's
            close (the pre-drop level the exit watches for).
  Scale-in: symbol holds exactly one tranche, and today's 1-day return is
            ANOTHER <= -drop_pct drop -> buy a second `notional` tranche
            (now ~2x notional invested, capped there). Same reference_price.
  Exit:     today's close >= reference_price -> sell the ENTIRE position
            (all tranches). Long-only — no short leg. Since exit only ever
            fires at or above the pre-drop reference price, and every tranche
            was bought below it, every CLOSED trade is a win by construction;
            the strategy's real risk lives entirely in positions that never
            recover (see below).
  Risk gap: no stop-loss and no max holding period, exactly as specified.
            A position can sit open indefinitely — including through the end
            of the backtest window, where it's marked to market as an open
            position rather than force-closed. This is a genuine, intentional
            gap: a stock that never recovers to its pre-drop price ties up
            capital forever and can carry an arbitrarily large unrealized
            loss. The equity curve (which marks open positions to market)
            reflects this risk even though closed-trade win rate cannot.
"""
from __future__ import annotations

import numpy as np

from .data_feed import DataFeed


def run_hft_mean_reversion_backtest(
    feed: DataFeed,
    capital: float = 1000.0,
    drop_pct: float = 0.05,
    notional: float = 5.0,
    lookback: int = 30,
) -> dict:
    """Walk the whole feed once, trading every symbol independently against
    one shared cash pool, then report the window from `lookback` onward —
    the same start index run_backtest()/PortfolioSimulator use for SMA/MPT —
    so all three strategies' curves line up on the same dates for charting.
    """
    dates = feed.dates
    close = feed.close                    # (T, n_assets)
    returns_1d = feed.returns             # (T, n_assets), row 0 = 0.0
    n_days, n_assets = close.shape

    cash = capital
    shares = np.zeros(n_assets)
    tranches = np.zeros(n_assets, dtype=int)          # 0 flat, 1 or 2 tranches held
    reference_price = np.full(n_assets, np.nan)
    entry_dates = [None] * n_assets

    raw_portfolio_value = np.full(n_days, capital)
    trades: list[dict] = []

    for t in range(1, n_days):
        for a in range(n_assets):
            price = close[t, a]

            if tranches[a] > 0 and price >= reference_price[a]:
                # Rebound: close the whole position, every tranche included.
                proceeds = float(shares[a] * price)
                invested = notional * tranches[a]
                trades.append({
                    "symbol": feed.symbols[a],
                    "entry_date": entry_dates[a],
                    "exit_date": dates[t],
                    "tranches": int(tranches[a]),
                    "invested": invested,
                    "proceeds": proceeds,
                    "return_pct": (proceeds / invested - 1.0) * 100.0,
                    "holding_days": (dates[t] - entry_dates[a]).days,
                    "win": proceeds >= invested,
                })
                cash += proceeds
                shares[a] = 0.0
                tranches[a] = 0
                reference_price[a] = np.nan
                entry_dates[a] = None
            elif tranches[a] == 0 and returns_1d[t, a] <= -drop_pct and cash >= notional:
                shares[a] += notional / price
                cash -= notional
                tranches[a] = 1
                reference_price[a] = close[t - 1, a]
                entry_dates[a] = dates[t]
            elif tranches[a] == 1 and returns_1d[t, a] <= -drop_pct and cash >= notional:
                shares[a] += notional / price
                cash -= notional
                tranches[a] = 2

        raw_portfolio_value[t] = cash + float(np.dot(shares, close[t]))

    start = min(lookback, n_days - 1)
    end = n_days - 1
    window_value = raw_portfolio_value[start:end + 1]
    normalized = window_value / window_value[0]

    port_rets = np.diff(normalized) / normalized[:-1]
    benchmark_rets = feed.returns[start + 1:end + 1].mean(axis=1)

    closed = [t for t in trades if t["exit_date"] is not None]
    still_open = int(np.sum(tranches > 0))

    return {
        "dates": dates[start + 1:end + 1],
        "portfolio": normalized[1:],
        "benchmark": np.cumprod(1.0 + benchmark_rets),
        "portfolio_returns": port_rets,
        "trades": trades,
        "kpis": {
            "num_trades_closed": len(closed),
            "num_positions_open_at_end": still_open,
            "win_rate_pct": float(np.mean([t["win"] for t in closed]) * 100.0) if closed else 0.0,
            "avg_holding_days": float(np.mean([t["holding_days"] for t in closed])) if closed else 0.0,
        },
    }
