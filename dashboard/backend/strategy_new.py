"""New strategy: weekly threshold rule — buy $5 on a 5% weekly drop, sell $10 on a 10% weekly rise."""
from pathlib import Path
import pandas as pd


def load_egx_stock(path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)[["date", "close"]]


def weekly_threshold_signals(df, price_col="close", buy_drop=-0.05, sell_rise=0.10, lookback_days=5):
    out = df.copy()
    out["weekly_return"] = out[price_col].pct_change(periods=lookback_days)

    def classify(r):
        if pd.isna(r):
            return None
        if r <= buy_drop:
            return "BUY"
        if r >= sell_rise:
            return "SELL"
        return None

    out["signal"] = out["weekly_return"].apply(classify)
    return out


def backtest_weekly_threshold(df, price_col="close", start_cash=100.0):
    sig = weekly_threshold_signals(df, price_col=price_col)
    cash, shares, equity = start_cash, 0.0, []
    for _, row in sig.iterrows():
        price = row[price_col]
        if row["signal"] == "BUY":
            spend = min(5.0, cash)
            shares += spend / price
            cash -= spend
        elif row["signal"] == "SELL":
            proceeds = min(10.0, shares * price)
            shares -= proceeds / price
            cash += proceeds
        equity.append(cash + shares * price)
    sig["equity"] = equity
    return sig


def run_universe_weekly_threshold(symbols, data_dir, start_cash_per_stock, min_date=None, max_date=None):
    equity_frames = []
    for sym in symbols:
        stock_df = load_egx_stock(Path(data_dir) / f"{sym}.csv")
        if min_date is not None:
            stock_df = stock_df[stock_df["date"] >= min_date]
        if max_date is not None:
            stock_df = stock_df[stock_df["date"] <= max_date]
        bt = backtest_weekly_threshold(stock_df, start_cash=start_cash_per_stock)
        eq = bt.set_index("date")["equity"].rename(sym)
        equity_frames.append(eq)

    universe_equity = pd.concat(equity_frames, axis=1, sort=True).sort_index().ffill()
    return universe_equity.sum(axis=1)