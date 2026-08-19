"""A small, self-contained stock-picking environment for tabular Q-learning."""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np


class StockTradingEnv:
    """Trade eight stocks while always owning exactly one share of two of them.

    An action is a target pair of stock indices.  All ``n choose 2`` target pairs
    are generated automatically, so each action is valid from every state.  A
    trade happens at today's price; reward is the next day's marked-to-market
    portfolio change less transaction costs.
    """

    def __init__(
        self,
        prices: np.ndarray,
        tickers: tuple[str, ...] | list[str] | None = None,
        transaction_cost: float = 0.001,
        initial_portfolio: tuple[int, int] = (0, 1),
    ) -> None:
        prices = np.asarray(prices, dtype=float)
        if prices.ndim != 2 or prices.shape[0] < 2 or prices.shape[1] < 2:
            raise ValueError("prices must have shape (at least 2 days, at least 2 stocks)")
        if np.any(prices <= 0):
            raise ValueError("all prices must be positive")
        if not 0 <= transaction_cost < 1:
            raise ValueError("transaction_cost must be in [0, 1)")

        self.prices = prices
        self.n_days, self.n_stocks = prices.shape
        self.tickers = tuple(tickers or [f"STOCK_{i}" for i in range(self.n_stocks)])
        if len(self.tickers) != self.n_stocks:
            raise ValueError("tickers and price columns must have the same length")
        self.transaction_cost = transaction_cost
        self.actions = list(combinations(range(self.n_stocks), 2))
        self.n_actions = len(self.actions)
        self.initial_portfolio = self._validate_portfolio(initial_portfolio)
        self.reset()

    def _validate_portfolio(self, portfolio: tuple[int, int]) -> tuple[int, int]:
        portfolio = tuple(sorted(portfolio))
        if len(portfolio) != 2 or portfolio[0] == portfolio[1] or not all(0 <= i < self.n_stocks for i in portfolio):
            raise ValueError("a portfolio must contain exactly two different valid stock indices")
        return portfolio

    def _price_features(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Discretize normalized prices and daily returns for a finite Q-table."""
        normalized_prices = self.prices[self.day] / self.prices[0]
        # Far below start, below start, near start, above start, far above start.
        price_buckets = tuple(np.digitize(normalized_prices, bins=(0.90, 0.98, 1.02, 1.10)).tolist())
        if self.day == 0:
            return price_buckets, (1,) * self.n_stocks  # neutral movement on the first day
        returns = self.prices[self.day] / self.prices[self.day - 1] - 1.0
        movement_buckets = tuple(np.digitize(returns, bins=(-0.01, 0.01)).tolist())
        return price_buckets, movement_buckets  # down, flat, up

    def _state(self) -> tuple[int, tuple[int, int], tuple[tuple[int, ...], tuple[int, ...]]]:
        return (self.day, self.portfolio, self._price_features())

    def portfolio_value(self, day: int | None = None) -> float:
        """Value of two shares plus accumulated transaction-cost cash balance."""
        day = self.day if day is None else day
        return float(self.prices[day, list(self.portfolio)].sum() + self.cash)

    def reset(self) -> tuple[int, tuple[int, int], tuple[tuple[int, ...], tuple[int, ...]]]:
        self.day = 0
        self.portfolio = self.initial_portfolio
        self.cash = 0.0
        self.done = False
        self.portfolio_history = [self.portfolio_value()]
        return self._state()

    def action_description(self, action: int, previous: tuple[int, int] | None = None) -> str:
        """Describe a target-pair action as keep/replace-first/replace-second/both."""
        current = self.portfolio if previous is None else previous
        target = self.actions[action]
        removed = [self.tickers[i] for i in current if i not in target]
        added = [self.tickers[i] for i in target if i not in current]
        if not removed:
            return f"Keep {self.tickers[target[0]]}, {self.tickers[target[1]]}"
        if len(removed) == 1:
            return f"Replace {removed[0]} with {added[0]}"
        return f"Replace both with {self.tickers[target[0]]}, {self.tickers[target[1]]}"

    def step(self, action: int) -> tuple[tuple[int, tuple[int, int], tuple[tuple[int, ...], tuple[int, ...]]], float, bool, dict[str, Any]]:
        if self.done:
            raise RuntimeError("Episode is done. Call reset() before step().")
        if not 0 <= action < self.n_actions:
            raise ValueError(f"action must be between 0 and {self.n_actions - 1}")

        old_portfolio = self.portfolio
        old_value = self.portfolio_value()
        new_portfolio = self.actions[action]
        # Buy and sell one share for every changed holding; paying a proportional fee.
        traded_indices = set(old_portfolio).symmetric_difference(new_portfolio)
        trading_notional = float(self.prices[self.day, list(traded_indices)].sum())
        cost = self.transaction_cost * trading_notional
        self.cash -= cost
        self.portfolio = new_portfolio
        self.day += 1
        self.done = self.day == self.n_days - 1
        new_value = self.portfolio_value()
        reward = new_value - old_value
        self.portfolio_history.append(new_value)

        info = {
            "date_index": self.day,
            "portfolio": tuple(self.tickers[i] for i in self.portfolio),
            "portfolio_value": new_value,
            "transaction_cost": cost,
            "action_description": self.action_description(action, old_portfolio),
        }
        return self._state(), float(reward), self.done, info
