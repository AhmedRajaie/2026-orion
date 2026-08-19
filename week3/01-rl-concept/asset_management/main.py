"""Run the Day 1 Asset Management Game assignment."""

from __future__ import annotations

import argparse
from pathlib import Path

from q_learning import QLearningAgent
from stock_env import StockTradingEnv
from train import evaluate, train
from utils import DEFAULT_TICKERS, generate_synthetic_prices, plot_portfolio, plot_training, trading_dates


def main() -> None:
    parser = argparse.ArgumentParser(description="Tabular Q-learning asset management game")
    parser.add_argument("--episodes", type=int, default=800, help="Number of training episodes")
    parser.add_argument("--seed", type=int, default=7, help="Synthetic-price random seed")
    parser.add_argument("--output-dir", default="outputs", help="Folder for PNG charts")
    parser.add_argument("--show", action="store_true", help="Display charts as well as saving them")
    args = parser.parse_args()

    dates = trading_dates()
    prices = generate_synthetic_prices(len(dates), len(DEFAULT_TICKERS), seed=args.seed)
    env = StockTradingEnv(prices, tickers=DEFAULT_TICKERS, transaction_cost=0.001)
    agent = QLearningAgent(n_actions=env.n_actions, alpha=0.1, gamma=0.95, seed=args.seed)

    history = train(env, agent, episodes=args.episodes)
    result = evaluate(env, agent)
    output_dir = Path(args.output_dir)
    plot_training(history, output_dir, show=args.show)
    plot_portfolio(result["portfolio_history"], dates, output_dir, show=args.show)

    print(f"Training episodes: {args.episodes}; learned states: {len(agent.q_table)}")
    print(f"Final profit:  {result['final_profit']:.2f}")
    print(f"Total reward:  {result['total_reward']:.2f}")
    print("\nPortfolio history:")
    for day, value in zip(dates, result["portfolio_history"]):
        print(f"  {day.isoformat()}: {value:.2f}")
    print("\nActions taken:")
    for day, action in zip(dates[:-1], result["actions"]):
        print(f"  {day.isoformat()}: {action}")
    print(f"\nCharts saved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
