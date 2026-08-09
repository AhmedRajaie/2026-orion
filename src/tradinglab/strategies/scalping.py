"""
scalping.py — many small, fast trades instead of one long holding.

SMA crossover (sma.py) and RSI mean-reversion (mean_reversion.py) both hold a
position until a NEW signal tells them to change their mind. A scalp doesn't
wait for the story to change: it defines success and failure in advance (a
profit target and a stop-loss) and exits the moment either is hit. Because that
exit depends on what price a trade was opened at — not just today's
observation — this strategy is a stateful class instead of a plain function.
`run_backtest` still calls it once per day, in order, exactly like any other
strategy; it just happens to remember things between calls.

Built and graduated from `week1/06-scalping-strategy/notebook.ipynb`.
"""
from __future__ import annotations
import numpy as np


class ScalpingStrategy:
    """Enter on a short-term dip below the fast average; exit on a fixed
    profit target, stop-loss, or time limit — never on the entry signal
    reversing.

    Entry (per stock, independently): not currently in a trade, and today's
    price is `entry_dip` below its fast SMA (feature 1, `p/sma_fast`, already
    computed in features.py).

    Exit (per stock, independently), whichever comes first:
        - profit_target reached -> take the win
        - stop_loss reached     -> cut the loss
        - max_hold_days reached -> flatten anyway

    Position sizing: only stocks CURRENTLY in a trade get capital — the same
    "genuine cash, not a forced bet" principle as sma_crossover_weights. Among
    open trades, weight is inversely proportional to volatility (feature 4,
    already computed) and capped at `max_weight_per_asset`.
    """

    def __init__(self, entry_dip=0.015, profit_target=0.02, stop_loss=0.01,
                 max_hold_days=5, max_weight_per_asset=0.5):
        self.entry_dip = entry_dip
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.max_hold_days = max_hold_days
        self.max_weight_per_asset = max_weight_per_asset
        self.trade_log = []          # one entry per CLOSED trade

        self._price = None           # running scale-free price per asset
        self._in_position = None
        self._entry_price = None
        self._days_held = None

    def __call__(self, observation: np.ndarray) -> np.ndarray:
        n_assets = observation.shape[0]
        if self._price is None:                      # first call: set up state
            self._price = np.ones(n_assets)
            self._in_position = np.zeros(n_assets, dtype=bool)
            self._entry_price = np.zeros(n_assets)
            self._days_held = np.zeros(n_assets, dtype=int)

        today_return = observation[:, -1, 0]
        deviation = observation[:, -1, 1]             # p/sma_fast
        vol = observation[:, -1, 4]

        self._price *= (1.0 + today_return)           # roll the price path forward one day

        for asset in range(n_assets):
            if self._in_position[asset]:
                self._days_held[asset] += 1
                trade_return = self._price[asset] / self._entry_price[asset] - 1.0
                hit_target = trade_return >= self.profit_target
                hit_stop = trade_return <= -self.stop_loss
                timed_out = self._days_held[asset] >= self.max_hold_days
                if hit_target or hit_stop or timed_out:
                    reason = "target" if hit_target else "stop" if hit_stop else "timeout"
                    self.trade_log.append({
                        "asset": asset, "return": trade_return,
                        "days_held": int(self._days_held[asset]), "reason": reason,
                    })
                    self._in_position[asset] = False
            elif deviation[asset] <= -self.entry_dip:
                self._in_position[asset] = True
                self._entry_price[asset] = self._price[asset]
                self._days_held[asset] = 0

        if not self._in_position.any():
            return np.zeros(n_assets)                 # nothing open -- genuine cash

        inv_vol = np.where(self._in_position, 1.0 / np.maximum(vol, 1e-4), 0.0)
        weights = inv_vol / inv_vol.sum()
        weights = np.minimum(weights, self.max_weight_per_asset)
        weights = weights / weights.sum()              # re-normalize after capping
        return weights
