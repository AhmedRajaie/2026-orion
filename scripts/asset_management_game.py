"""
asset_management_game.py — replays "An Asset Management Game!" (slide 57).

The rules from the slide:
    - A mini stock market of 8 EGX names.
    - The player must always hold exactly 2 stocks (50/50).
    - Playtime: 06 Jul - 04 Aug. One reshuffle allowed, on 16 Jul.
    - Goal: maximize profit.

The 8 names come from the TradingView grid on the slide: EFG Holding (HRHO),
Beltone Holding (BTFH), Ibnsina Pharma (ISPH), QALA For Financial Investments
(QALA), Raya Holding (RAYA), Palm Hills Development (PHDC), Fawry (FWRY),
Commercial International Bank (COMI).

QALA isn't in the committed data/egx universe (scripts/fetch_egx_data.py never
pulled it), so the 06 Jul pick "QALA, BTFH" can't be replayed exactly — we fall
back to 100% BTFH for that leg and print a loud warning. Add QALA to SYMBOLS in
fetch_egx_data.py and re-run it to close that gap.

Reuses the same engine as the rest of the program (DataFeed + PortfolioSimulator
+ charting) — this is a fixed-scenario backtest, not a new simulator.

    uv run python scripts/asset_management_game.py
"""
from __future__ import annotations

import itertools
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from tradinglab.data_feed import DataFeed
from tradinglab.simulator import PortfolioSimulator
from tradinglab.metrics import total_return
from tradinglab.charting import plot_equity
import matplotlib.pyplot as plt

UNIVERSE = ["HRHO", "BTFH", "ISPH", "QALA", "RAYA", "PHDC", "FWRY", "COMI"]
DATA_DIR = "data/egx"

GAME_START = "2026-07-06"
CHECKPOINT = "2026-07-16"   # the one reshuffle the slide shows
GAME_END = "2026-08-04"

# The picks actually shown on the slide, per leg.
AS_PLAYED = {
    "leg1": ["QALA", "BTFH"],   # 06 Jul -> 16 Jul
    "leg2": ["PHDC", "BTFH"],   # 16 Jul -> 04 Aug
}


def pair_weights(feed: DataFeed, pair: list[str]) -> np.ndarray:
    """50/50 weight vector over `pair`, zero elsewhere. Drops any symbol not
    in the feed (so a missing ticker just gets the leftover weight zeroed,
    not an IndexError) and renormalizes over what's left."""
    w = np.zeros(feed.n_assets)
    idx = [feed.symbols.index(s) for s in pair if s in feed.symbols]
    missing = [s for s in pair if s not in feed.symbols]
    if missing:
        print(f"  [!] {missing} not in committed data -> reweighting {pair} onto {[feed.symbols[i] for i in idx]}")
    w[idx] = 1.0 / len(idx)
    return w


def day_index(feed: DataFeed, date_str: str) -> int:
    """First feed day on/after `date_str` (data ends 2026-07-30 in this repo's
    committed CSVs, so GAME_END clips to the last available day)."""
    idx = feed.dates.searchsorted(date_str)
    return int(min(idx, feed.n_days - 1))


def leg_return(feed: DataFeed, pair: list[str], start: int, end: int) -> float:
    """Compounded return of a 50/50 buy-and-hold pair from day `start` to `end`."""
    if start >= end:
        return 0.0
    weights = pair_weights(feed, pair)
    weights_by_day = np.tile(weights, (feed.n_days, 1))
    sim = PortfolioSimulator(feed)
    result = sim.run(weights_by_day, start, end)
    return total_return(result["portfolio_returns"])


def best_and_worst_pair(feed: DataFeed, start: int, end: int):
    """Brute-force every 2-of-N combo over one leg -- the 🎉 / ☠️ bounds a
    player could actually have hit, echoing the 'efficient frontier: best
    possible outcome' framing from the MPT day (slide 55)."""
    best = (-np.inf, None)
    worst = (np.inf, None)
    for pair in itertools.combinations(feed.symbols, 2):
        r = leg_return(feed, list(pair), start, end)
        if r > best[0]:
            best = (r, pair)
        if r < worst[0]:
            worst = (r, pair)
    return best, worst


def main():
    feed = DataFeed.from_dir(DATA_DIR, symbols=[s for s in UNIVERSE if s != "QALA"])
    print(f"Universe ({feed.n_assets}/8 stocks — QALA missing from committed data): {feed.symbols}")
    print(f"Data covers {feed.dates.min().date()} -> {feed.dates.max().date()}\n")

    t_start = day_index(feed, GAME_START)
    t_mid = day_index(feed, CHECKPOINT)
    t_end = day_index(feed, GAME_END)
    print(f"Game window: {feed.dates[t_start].date()} -> {feed.dates[t_mid].date()} -> {feed.dates[t_end].date()}\n")

    # --- as-played: the exact picks from the slide ---
    r1 = leg_return(feed, AS_PLAYED["leg1"], t_start, t_mid)
    r2 = leg_return(feed, AS_PLAYED["leg2"], t_mid, t_end)
    as_played_total = (1 + r1) * (1 + r2) - 1

    # --- best/worst possible, leg by leg ---
    (best1, pair_best1), (worst1, pair_worst1) = best_and_worst_pair(feed, t_start, t_mid)
    (best2, pair_best2), (worst2, pair_worst2) = best_and_worst_pair(feed, t_mid, t_end)
    best_total = (1 + best1) * (1 + best2) - 1
    worst_total = (1 + worst1) * (1 + worst2) - 1

    # --- equal-weight-of-universe benchmark, held the whole game ---
    sim = PortfolioSimulator(feed, benchmark="equal_weight")
    bench_total = total_return(sim.benchmark_returns[t_start + 1 : t_end + 1])

    print("=" * 60)
    print("AN ASSET MANAGEMENT GAME! — results")
    print("=" * 60)
    print(f"As played   {AS_PLAYED['leg1']} -> {AS_PLAYED['leg2']}: {as_played_total:+.2%}")
    print(f"Best possible pair each leg  ({pair_best1} -> {pair_best2}): {best_total:+.2%}  🎉🎉🎉")
    print(f"Worst possible pair each leg ({pair_worst1} -> {pair_worst2}): {worst_total:+.2%}  ☠️☠️☠️")
    print(f"Equal-weight benchmark (all {feed.n_assets} stocks, held flat): {bench_total:+.2%}")

    # --- equity curve: as-played vs benchmark ---
    weights_by_day = np.zeros((feed.n_days, feed.n_assets))
    weights_by_day[t_start:t_mid] = pair_weights(feed, AS_PLAYED["leg1"])
    weights_by_day[t_mid:t_end] = pair_weights(feed, AS_PLAYED["leg2"])
    full_sim = PortfolioSimulator(feed)
    curve = full_sim.run(weights_by_day, t_start, t_end)

    plot_equity(curve["portfolio"], curve["benchmark"], dates=curve["dates"],
                title="As played vs. equal-weight benchmark")
    out_path = os.path.join(os.path.dirname(__file__), "asset_management_game_result.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nSaved equity curve -> {out_path}")


if __name__ == "__main__":
    main()
