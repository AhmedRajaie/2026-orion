"""Training and greedy evaluation loops for the tabular stock agent."""

from __future__ import annotations

from stock_env import StockTradingEnv
from q_learning import QLearningAgent


def train(
    env: StockTradingEnv,
    agent: QLearningAgent,
    episodes: int = 800,
    epsilon_start: float = 1.0,
    epsilon_decay: float = 0.995,
    epsilon_min: float = 0.05,
) -> dict[str, list[float]]:
    """Run the same reset -> act -> Bellman update loop used in GridWorld."""
    epsilon = epsilon_start
    history = {"episode_rewards": [], "epsilons": []}
    for _ in range(episodes):
        state = env.reset()
        done = False
        total_reward = 0.0
        while not done:
            action = agent.epsilon_greedy(state, epsilon)
            next_state, reward, done, _ = env.step(action)
            agent.q_update(state, action, reward, next_state, done)
            state = next_state
            total_reward += reward
        history["episode_rewards"].append(total_reward)
        history["epsilons"].append(epsilon)
        epsilon = max(epsilon_min, epsilon * epsilon_decay)
    return history


def evaluate(env: StockTradingEnv, agent: QLearningAgent) -> dict[str, object]:
    """Run one episode with greedy actions only and record every decision."""
    state = env.reset()
    done = False
    total_reward = 0.0
    actions: list[str] = []
    while not done:
        action = agent.epsilon_greedy(state, epsilon=0.0)
        state, reward, done, info = env.step(action)
        total_reward += reward
        actions.append(info["action_description"])
    return {
        "final_profit": env.portfolio_history[-1] - env.portfolio_history[0],
        "total_reward": total_reward,
        "portfolio_history": env.portfolio_history.copy(),
        "actions": actions,
    }
