"""The GridWorld tabular Q-learning algorithm, generalized to any action count."""

from __future__ import annotations

from collections import defaultdict

import numpy as np


class QLearningAgent:
    def __init__(self, n_actions: int, alpha: float = 0.1, gamma: float = 0.95, seed: int = 0) -> None:
        self.n_actions = n_actions
        self.alpha = alpha
        self.gamma = gamma
        self.rng = np.random.default_rng(seed)
        self.q_table: defaultdict[tuple, np.ndarray] = defaultdict(lambda: np.zeros(self.n_actions, dtype=float))

    def epsilon_greedy(self, state: tuple, epsilon: float) -> int:
        """Same policy as GridWorld: explore randomly, otherwise choose argmax Q."""
        if self.rng.random() < epsilon:
            return int(self.rng.integers(self.n_actions))
        return int(np.argmax(self.q_table[state]))

    def q_update(self, state: tuple, action: int, reward: float, next_state: tuple, done: bool) -> None:
        """One-step Bellman update: Q(s,a) <- Q(s,a) + alpha * TD error."""
        best_next = 0.0 if done else float(np.max(self.q_table[next_state]))
        td_target = reward + self.gamma * best_next
        td_error = td_target - self.q_table[state][action]
        self.q_table[state][action] += self.alpha * td_error
