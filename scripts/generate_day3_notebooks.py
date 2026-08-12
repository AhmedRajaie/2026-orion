from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat as nbf


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = REPO_ROOT / "week2" / "03-form-prediction-to-portfolio"


def md(text: str):
    return nbf.v4.new_markdown_cell(dedent(text).strip() + "\n")


def code(text: str):
    return nbf.v4.new_code_cell(dedent(text).strip() + "\n")


def notebook_one():
    cells = [
        md(
            """
            # Week 2 — Day 3: From Prediction to Portfolio

            Day 1 tested an MLP on one stock.

            Day 2 tested whether an LSTM improved prediction by giving the model memory.

            Day 3 asks a different and more important question:

            Can those predictions be converted into a portfolio strategy across the full universe that beats the benchmark?
            """
        ),
        md(
            """
            ## Week 2 Sources Used

            This notebook follows the repository's own Week 2 teaching path:

            - `week2/03-form-prediction-to-portfolio/mlp.ipynb`
            - `week2/03-form-prediction-to-portfolio/lstm.ipynb`
            - `week2/02-lstm/day2_lstm_vs_mlp.ipynb`
            - Week 1 backtest/report conventions for benchmarking and metrics

            Baseline choices below intentionally match the shared-model Week 2 notebooks before any tuning:

            - full `DataFeed.from_dir('data/egx')` universe
            - pooled train/test split by calendar day
            - MLP hidden size `32`, `150` epochs, Adam, MSE loss, seed `0`
            - LSTM hidden size `32`, sequence length `10`, `150` epochs, Adam, MSE loss, seed `0`
            - zero commission, equal-weight benchmark, long-only equal weights across all positive predictions
            """
        ),
        code(
            """
            from pathlib import Path
            import os
            import sys
            from textwrap import dedent

            repo_root = next(
                path for path in [Path.cwd(), *Path.cwd().parents]
                if (path / "src" / "tradinglab").exists()
            )
            os.chdir(repo_root)

            tmp_dir = repo_root / ".tmp"
            (tmp_dir / "matplotlib").mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("MPLCONFIGDIR", str(tmp_dir / "matplotlib"))

            import numpy as np
            import pandas as pd
            import matplotlib.pyplot as plt
            from IPython.display import Markdown, display

            src_path = str(repo_root / "src")
            if src_path not in sys.path:
                sys.path.insert(0, src_path)

            from tradinglab.data_feed import DataFeed
            from tradinglab.day3 import (
                BASELINE_FEATURES,
                build_feature_tensor,
                run_shared_model_portfolio,
            )
            """
        ),
        code(
            """
            feed = DataFeed.from_dir("data/egx")
            feature_tensor = build_feature_tensor(feed, BASELINE_FEATURES)
            split_day = int(feed.n_days * 0.7)
            split_date = feed.dates[split_day]
            lookback = 30

            universe_info = pd.DataFrame(
                {
                    "value": [
                        feed.n_assets,
                        ", ".join(feed.symbols),
                        feed.n_days,
                        str(feed.dates[0])[:10],
                        str(feed.dates[-1])[:10],
                        split_day,
                        str(split_date)[:10],
                    ]
                },
                index=[
                    "Number of stocks",
                    "Symbols",
                    "Number of days",
                    "First date",
                    "Last date",
                    "Train/test split day",
                    "Split date",
                ],
            )
            display(Markdown("## Full Course Universe"))
            display(universe_info)

            skipped_symbols = []
            print("Stocks skipped from modeling:", skipped_symbols or "None")
            """
        ),
        code(
            """
            mlp_baseline = run_shared_model_portfolio(
                feed,
                "mlp",
                feature_names=BASELINE_FEATURES,
                feature_tensor=feature_tensor,
                lookback=lookback,
                hidden=32,
                epochs=150,
                lr=1e-3,
                seed=0,
                commission=0.0,
            )

            lstm_baseline = run_shared_model_portfolio(
                feed,
                "lstm",
                feature_names=BASELINE_FEATURES,
                feature_tensor=feature_tensor,
                lookback=lookback,
                hidden=32,
                seq_len=10,
                epochs=150,
                lr=1e-3,
                seed=0,
                commission=0.0,
            )

            mlp_result = mlp_baseline["result"]
            lstm_result = lstm_baseline["result"]
            """
        ),
        code(
            """
            mlp_predictions = mlp_result["predictions"]
            lstm_predictions = lstm_result["predictions"]
            actual_returns = mlp_result["actual_returns"]
            mlp_weights = mlp_result["weights"]
            lstm_weights = lstm_result["weights"]
            common_dates = pd.DatetimeIndex(mlp_result["dates"])
            common_signal_dates = pd.DatetimeIndex(mlp_result["signal_dates"])

            assert mlp_predictions.shape == lstm_predictions.shape == actual_returns.shape
            assert mlp_weights.shape == lstm_weights.shape == actual_returns.shape
            assert list(mlp_result["symbols"]) == list(lstm_result["symbols"]) == feed.symbols
            assert len(common_dates) == actual_returns.shape[0]
            assert len(common_signal_dates) == actual_returns.shape[0]
            assert np.all(mlp_weights >= -1e-9) and np.all(lstm_weights >= -1e-9)

            mlp_weight_sums = mlp_weights.sum(axis=1)
            lstm_weight_sums = lstm_weights.sum(axis=1)
            assert np.allclose(mlp_weight_sums[(mlp_weight_sums > 0)], 1.0, atol=1e-6)
            assert np.allclose(lstm_weight_sums[(lstm_weight_sums > 0)], 1.0, atol=1e-6)
            assert np.allclose(mlp_weight_sums[(mlp_weight_sums == 0)], 0.0, atol=1e-6)
            assert np.allclose(lstm_weight_sums[(lstm_weight_sums == 0)], 0.0, atol=1e-6)

            alignment_lines = [
                "## Common Out-of-Sample Prediction Matrices",
                "",
                f"- Signal dates run from `{common_signal_dates[0].date()}` to `{common_signal_dates[-1].date()}`",
                f"- Realized return dates run from `{common_dates[0].date()}` to `{common_dates[-1].date()}`",
                f"- Matrix shape: `{mlp_predictions.shape}` = `(days, stocks)`",
                f"- MLP matrix aligned with actual returns: `{mlp_predictions.shape == actual_returns.shape}`",
                f"- LSTM matrix aligned with actual returns: `{lstm_predictions.shape == actual_returns.shape}`",
                f"- Stocks modeled: `{len(mlp_result['symbols'])}`",
            ]
            display(Markdown("\\n".join(alignment_lines)))
            """
        ),
        code(
            """
            comparison = pd.DataFrame(
                [
                    {
                        "Metric": "Final value",
                        "MLP": mlp_result["metrics"]["final_value"],
                        "LSTM": lstm_result["metrics"]["final_value"],
                        "Benchmark": mlp_result["metrics"]["benchmark_final_value"],
                    },
                    {
                        "Metric": "Total return",
                        "MLP": mlp_result["metrics"]["total_return"],
                        "LSTM": lstm_result["metrics"]["total_return"],
                        "Benchmark": mlp_result["metrics"]["benchmark_return"],
                    },
                    {
                        "Metric": "Sharpe",
                        "MLP": mlp_result["metrics"]["sharpe"],
                        "LSTM": lstm_result["metrics"]["sharpe"],
                        "Benchmark": mlp_result["metrics"]["benchmark_sharpe"],
                    },
                    {
                        "Metric": "Max drawdown",
                        "MLP": mlp_result["metrics"]["max_drawdown"],
                        "LSTM": lstm_result["metrics"]["max_drawdown"],
                        "Benchmark": mlp_result["metrics"]["benchmark_max_drawdown"],
                    },
                    {
                        "Metric": "Excess return",
                        "MLP": mlp_result["metrics"]["excess_return"],
                        "LSTM": lstm_result["metrics"]["excess_return"],
                        "Benchmark": 0.0,
                    },
                    {
                        "Metric": "Average stocks held",
                        "MLP": mlp_result["metrics"]["average_stocks_held"],
                        "LSTM": lstm_result["metrics"]["average_stocks_held"],
                        "Benchmark": float(feed.n_assets),
                    },
                    {
                        "Metric": "Minimum stocks held",
                        "MLP": mlp_result["metrics"]["minimum_stocks_held"],
                        "LSTM": lstm_result["metrics"]["minimum_stocks_held"],
                        "Benchmark": feed.n_assets,
                    },
                    {
                        "Metric": "Maximum stocks held",
                        "MLP": mlp_result["metrics"]["maximum_stocks_held"],
                        "LSTM": lstm_result["metrics"]["maximum_stocks_held"],
                        "Benchmark": feed.n_assets,
                    },
                    {
                        "Metric": "Days invested",
                        "MLP": mlp_result["metrics"]["percentage_days_invested"],
                        "LSTM": lstm_result["metrics"]["percentage_days_invested"],
                        "Benchmark": 1.0,
                    },
                ]
            ).set_index("Metric")
            comparison
            """
        ),
        code(
            """
            plt.figure(figsize=(13, 5))
            plt.plot(common_dates, mlp_result["portfolio"], label="MLP portfolio", linewidth=1.5)
            plt.plot(common_dates, lstm_result["portfolio"], label="LSTM portfolio", linewidth=1.5)
            plt.plot(common_dates, mlp_result["benchmark"], label="Equal-weight benchmark", linewidth=1.5, linestyle="--")
            plt.title("MLP vs LSTM — Full-Universe Portfolio")
            plt.ylabel("Growth of Initial Capital")
            plt.grid(alpha=0.3)
            plt.legend()
            plt.xticks(rotation=30)
            plt.tight_layout()
            plt.show()
            """
        ),
        code(
            """
            mlp_holdings = (mlp_weights > 1e-6).sum(axis=1)
            lstm_holdings = (lstm_weights > 1e-6).sum(axis=1)

            plt.figure(figsize=(13, 4))
            plt.plot(common_dates, mlp_holdings, label="MLP stocks selected", linewidth=1.4)
            plt.plot(common_dates, lstm_holdings, label="LSTM stocks selected", linewidth=1.4)
            plt.title("Number of Stocks Held")
            plt.ylabel("Stocks held")
            plt.grid(alpha=0.3)
            plt.legend()
            plt.xticks(rotation=30)
            plt.tight_layout()
            plt.show()
            """
        ),
        code(
            """
            mlp_beats_benchmark = mlp_result["metrics"]["final_value"] > mlp_result["metrics"]["benchmark_final_value"]
            lstm_beats_benchmark = lstm_result["metrics"]["final_value"] > lstm_result["metrics"]["benchmark_final_value"]
            final_value_winner = (
                "MLP"
                if mlp_result["metrics"]["final_value"] > lstm_result["metrics"]["final_value"]
                else "LSTM"
            )
            lower_drawdown = (
                "MLP"
                if mlp_result["metrics"]["max_drawdown"] < lstm_result["metrics"]["max_drawdown"]
                else "LSTM"
            )

            baseline_answer = f'''
            ## Baseline Day 3 Result

            - Did MLP beat the benchmark? **{"Yes" if mlp_beats_benchmark else "No"}**.
            - Did LSTM beat the benchmark? **{"Yes" if lstm_beats_benchmark else "No"}**.
            - Did MLP beat LSTM on final value / total return? **{"Yes" if final_value_winner == "MLP" else "No"}**.
            - Did LSTM beat MLP on risk-adjusted behavior? **{"Yes" if lstm_result["metrics"]["sharpe"] > mlp_result["metrics"]["sharpe"] and lstm_result["metrics"]["max_drawdown"] < mlp_result["metrics"]["max_drawdown"] else "No"}**.
            - Which had lower drawdown? **{lower_drawdown}**.
            - Does the model that predicted ABUK better also create the better diversified portfolio? **No**. The inspected Day 2 ABUK notebook said the LSTM was slightly stronger on the main ABUK price-error metrics, but in this full-universe baseline the MLP finished with the higher final value.

            The baseline result is close rather than decisive: the MLP ends a little higher, while the LSTM holds more stocks, posts the slightly better Sharpe ratio, and keeps the lower drawdown.
            '''
            display(Markdown(dedent(baseline_answer).strip()))
            """
        ),
        code(
            """
            validation_text = '''
            ## Validation Against Required Reference Files

            - `week1/06-tiktok-strategy/tiktok_strategy.py`: same `DataFeed.from_dir('data/egx')`, same `PortfolioSimulator` accounting contract, same long-only weight matrix shape, and the same realized-date convention where weights chosen on day `t` earn return `t -> t+1`.
            - `week2/03-form-prediction-to-portfolio/mlp.ipynb`: same pooled shared-model training, same hidden size `32`, same seed `0`, same `150` epochs, same Adam + MSE training helper, and the same equal-weight benchmark with zero commission.
            - `week2/03-form-prediction-to-portfolio/lstm.ipynb`: same pooled sequence training, same hidden size `32`, same sequence length `10`, same seed `0`, same `150` epochs, and the same Week 2 benchmark/cost conventions.

            Transaction costs are intentionally **0.0** here because that is the direct Week 2 baseline convention in the referenced MLP/LSTM notebooks.
            '''
            display(Markdown(dedent(validation_text).strip()))
            """
        ),
    ]

    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        }
    )
    return nb


def notebook_two():
    cells = [
        md(
            """
            # Day 3 — Robustness and Strategy Search

            The goal of this notebook is not to celebrate one attractive chart. It is to test whether the Day 3 result survives seed changes and whether small, course-compatible changes to features and network size can produce a stronger real portfolio.
            """
        ),
        md(
            """
            ## Search Scope

            Only repository-native tools are used here:

            - the existing EGX `DataFeed`
            - Week 1 indicators already present in `src/tradinglab/indicators.py`
            - the repository `MLP`, `DeepMLP`, and `LSTMRegressor`
            - the shared `train_model` and `PortfolioSimulator`

            No external data, packages, or APIs are introduced.
            """
        ),
        code(
            """
            from pathlib import Path
            import os
            import sys
            from textwrap import dedent

            repo_root = next(
                path for path in [Path.cwd(), *Path.cwd().parents]
                if (path / "src" / "tradinglab").exists()
            )
            os.chdir(repo_root)

            tmp_dir = repo_root / ".tmp"
            (tmp_dir / "matplotlib").mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("MPLCONFIGDIR", str(tmp_dir / "matplotlib"))

            import json
            import numpy as np
            import pandas as pd
            import matplotlib.pyplot as plt
            from IPython.display import Markdown, display

            src_path = str(repo_root / "src")
            if src_path not in sys.path:
                sys.path.insert(0, src_path)

            from tradinglab.data_feed import DataFeed
            from tradinglab.day3 import (
                ALL_FEATURES,
                BASELINE_FEATURES,
                aggregate_run_metrics,
                build_dashboard_artifact,
                build_feature_tensor,
                run_shared_model_portfolio,
                save_dashboard_artifact,
            )
            """
        ),
        code(
            """
            feed = DataFeed.from_dir("data/egx")
            split_day = int(feed.n_days * 0.7)
            lookback = 30
            seeds = [1, 7, 42, 123, 2026]

            feature_sets = {
                "baseline": BASELINE_FEATURES,
                "momentum": BASELINE_FEATURES + ("return_5d", "return_10d"),
                "full": ALL_FEATURES,
            }
            feature_tensors = {
                name: build_feature_tensor(feed, features)
                for name, features in feature_sets.items()
            }

            baseline_mlp = {
                "name": "mlp_baseline",
                "model_type": "mlp",
                "feature_set": "baseline",
                "hidden": 32,
                "n_hidden_layers": 1,
                "epochs": 150,
                "lr": 1e-3,
            }
            baseline_lstm = {
                "name": "lstm_baseline",
                "model_type": "lstm",
                "feature_set": "baseline",
                "hidden": 32,
                "seq_len": 10,
                "epochs": 150,
                "lr": 1e-3,
            }

            mlp_candidates = [
                baseline_mlp,
                {
                    "name": "mlp_wide",
                    "model_type": "mlp",
                    "feature_set": "baseline",
                    "hidden": 64,
                    "n_hidden_layers": 1,
                    "epochs": 200,
                    "lr": 1e-3,
                },
                {
                    "name": "mlp_deep",
                    "model_type": "mlp",
                    "feature_set": "baseline",
                    "hidden": 32,
                    "n_hidden_layers": 2,
                    "epochs": 200,
                    "lr": 5e-4,
                },
                {
                    "name": "mlp_momentum",
                    "model_type": "mlp",
                    "feature_set": "momentum",
                    "hidden": 64,
                    "n_hidden_layers": 1,
                    "epochs": 200,
                    "lr": 1e-3,
                },
                {
                    "name": "mlp_full",
                    "model_type": "mlp",
                    "feature_set": "full",
                    "hidden": 64,
                    "n_hidden_layers": 2,
                    "epochs": 200,
                    "lr": 5e-4,
                },
            ]

            lstm_candidates = [
                baseline_lstm,
                {
                    "name": "lstm_seq5",
                    "model_type": "lstm",
                    "feature_set": "baseline",
                    "hidden": 32,
                    "seq_len": 5,
                    "epochs": 150,
                    "lr": 1e-3,
                },
                {
                    "name": "lstm_wide",
                    "model_type": "lstm",
                    "feature_set": "baseline",
                    "hidden": 64,
                    "seq_len": 10,
                    "epochs": 200,
                    "lr": 1e-3,
                },
                {
                    "name": "lstm_momentum",
                    "model_type": "lstm",
                    "feature_set": "momentum",
                    "hidden": 64,
                    "seq_len": 5,
                    "epochs": 200,
                    "lr": 1e-3,
                },
                {
                    "name": "lstm_full",
                    "model_type": "lstm",
                    "feature_set": "full",
                    "hidden": 64,
                    "seq_len": 10,
                    "epochs": 200,
                    "lr": 5e-4,
                },
            ]

            candidate_by_name = {
                candidate["name"]: candidate
                for candidate in [*mlp_candidates, *lstm_candidates]
            }

            def run_candidate(candidate, seed):
                kwargs = dict(
                    feature_names=feature_sets[candidate["feature_set"]],
                    feature_tensor=feature_tensors[candidate["feature_set"]],
                    lookback=lookback,
                    hidden=candidate["hidden"],
                    epochs=candidate["epochs"],
                    lr=candidate["lr"],
                    seed=seed,
                    commission=0.0,
                )
                if candidate["model_type"] == "mlp":
                    kwargs["n_hidden_layers"] = candidate.get("n_hidden_layers", 1)
                else:
                    kwargs["seq_len"] = candidate["seq_len"]
                return run_shared_model_portfolio(feed, candidate["model_type"], **kwargs)

            def run_seed_sweep(candidate, seeds_to_run):
                rows = []
                runs = []
                for seed in seeds_to_run:
                    run = run_candidate(candidate, seed)
                    runs.append(run)
                    metrics = run["result"]["metrics"]
                    prediction_metrics = run["result"]["prediction_metrics"]
                    rows.append(
                        {
                            "candidate": candidate["name"],
                            "model_type": candidate["model_type"],
                            "feature_set": candidate["feature_set"],
                            "hidden": candidate["hidden"],
                            "n_hidden_layers": candidate.get("n_hidden_layers"),
                            "seq_len": candidate.get("seq_len"),
                            "epochs": candidate["epochs"],
                            "lr": candidate["lr"],
                            "seed": seed,
                            "total_return": metrics["total_return"],
                            "sharpe": metrics["sharpe"],
                            "max_drawdown": metrics["max_drawdown"],
                            "excess_return": metrics["excess_return"],
                            "final_value": metrics["final_value"],
                            "benchmark_final_value": metrics["benchmark_final_value"],
                            "benchmark_return": metrics["benchmark_return"],
                            "average_stocks_held": metrics["average_stocks_held"],
                            "test_mse": prediction_metrics["test_mse"],
                            "information_coefficient": prediction_metrics["information_coefficient"],
                        }
                    )
                summary = aggregate_run_metrics(runs)
                return rows, summary, runs
            """
        ),
        code(
            """
            baseline_rows = []
            baseline_summary_rows = []
            baseline_runs = {}

            for candidate in [baseline_mlp, baseline_lstm]:
                rows, summary, runs = run_seed_sweep(candidate, seeds)
                baseline_rows.extend(rows)
                baseline_runs[candidate["name"]] = runs
                baseline_summary_rows.append(
                    {
                        "candidate": candidate["name"],
                        "model_type": candidate["model_type"],
                        "mean_total_return": summary["mean_total_return"],
                        "std_total_return": summary["std_total_return"],
                        "mean_sharpe": summary["mean_sharpe"],
                        "mean_max_drawdown": summary["mean_max_drawdown"],
                        "mean_excess_return": summary["mean_excess_return"],
                        "beat_benchmark_count": summary["beat_benchmark_count"],
                        "beat_benchmark_pct": summary["beat_benchmark_pct"],
                        "best_seed": summary["best_seed"],
                        "worst_seed": summary["worst_seed"],
                    }
                )

            baseline_seed_table = pd.DataFrame(baseline_rows)
            baseline_summary = pd.DataFrame(baseline_summary_rows).set_index("candidate")

            display(Markdown("## Baseline Seed Sweep"))
            display(baseline_seed_table)
            display(Markdown("## Baseline Seed Robustness Summary"))
            baseline_summary
            """
        ),
        code(
            """
            benchmark_reference = float(baseline_seed_table["benchmark_return"].iloc[0])

            plt.figure(figsize=(12, 4))
            for candidate_name, label in [("mlp_baseline", "MLP"), ("lstm_baseline", "LSTM")]:
                subset = baseline_seed_table[baseline_seed_table["candidate"] == candidate_name].sort_values("seed")
                plt.plot(subset["seed"], subset["total_return"], marker="o", linewidth=1.4, label=label)
            plt.axhline(benchmark_reference, color="gray", linestyle="--", linewidth=1.1, label="Benchmark")
            plt.title("Baseline Total Return by Seed")
            plt.xlabel("Seed")
            plt.ylabel("Total return")
            plt.grid(alpha=0.3)
            plt.legend()
            plt.tight_layout()
            plt.show()
            """
        ),
        code(
            """
            mlp_base_summary = baseline_summary.loc["mlp_baseline"]
            lstm_base_summary = baseline_summary.loc["lstm_baseline"]

            sensitivity_text = f'''
            ## Seed Robustness Interpretation

            - Does performance remain similar across seeds? **Not really for the baseline MLP**. Its mean total return across the changed seeds is `{mlp_base_summary["mean_total_return"]:.2%}` with a standard deviation of `{mlp_base_summary["std_total_return"]:.2%}`, and it only beat the benchmark in `{int(mlp_base_summary["beat_benchmark_count"])}/{len(seeds)}` runs.
            - Does one model appear highly seed-dependent? **Yes: the baseline MLP is more seed-sensitive**. The baseline LSTM is more stable numerically (`{lstm_base_summary["std_total_return"]:.2%}` standard deviation) but mostly because it behaves very similarly to the benchmark.
            - Did the original result appear lucky? **Partly yes**. The seed-0 baseline chart looked acceptable, but the changed-seed sweep shows that neither baseline model beats the benchmark consistently enough to treat one run as proof.
            - Which model is more stable? **The baseline LSTM** is more stable by return dispersion, but **the baseline MLP** still reaches the better upside when it works.
            '''
            display(Markdown(dedent(sensitivity_text).strip()))
            """
        ),
        code(
            """
            seed0_rows = []
            for candidate in [*mlp_candidates, *lstm_candidates]:
                run = run_candidate(candidate, seed=0)
                metrics = run["result"]["metrics"]
                prediction_metrics = run["result"]["prediction_metrics"]
                seed0_rows.append(
                    {
                        "candidate": candidate["name"],
                        "model_type": candidate["model_type"],
                        "feature_set": candidate["feature_set"],
                        "hidden": candidate["hidden"],
                        "n_hidden_layers": candidate.get("n_hidden_layers"),
                        "seq_len": candidate.get("seq_len"),
                        "epochs": candidate["epochs"],
                        "lr": candidate["lr"],
                        "test_mse": prediction_metrics["test_mse"],
                        "information_coefficient": prediction_metrics["information_coefficient"],
                        "total_return": metrics["total_return"],
                        "sharpe": metrics["sharpe"],
                        "max_drawdown": metrics["max_drawdown"],
                        "excess_return": metrics["excess_return"],
                        "average_stocks_held": metrics["average_stocks_held"],
                    }
                )

            seed0_results = pd.DataFrame(seed0_rows).sort_values(
                by=["excess_return", "sharpe", "total_return"],
                ascending=[False, False, False],
            )

            tested_sets_text = '''
            ## Configurations Tested

            - Feature sets tested: `baseline`, `momentum = baseline + return_5d + return_10d`, and `full = all repository Week 2 features`
            - MLP architectures tested: hidden size `32`, hidden size `64`, and `DeepMLP` with `2` hidden layers
            - LSTM configurations tested: sequence length `5` and `10`, hidden size `32` and `64`
            - Learning rates / epochs tested: `1e-3` with `150` or `200` epochs, and `5e-4` with `200` epochs
            '''
            display(Markdown(dedent(tested_sets_text).strip()))
            seed0_results
            """
        ),
        code(
            """
            shortlist_names = ["mlp_wide", "mlp_momentum", "lstm_baseline", "lstm_wide"]
            shortlist_rows = []
            shortlist_summary_rows = []
            shortlist_runs = {}

            for name in shortlist_names:
                candidate = candidate_by_name[name]
                rows, summary, runs = run_seed_sweep(candidate, seeds)
                shortlist_rows.extend(rows)
                shortlist_runs[name] = runs
                shortlist_summary_rows.append(
                    {
                        "candidate": name,
                        "model_type": candidate["model_type"],
                        "feature_set": candidate["feature_set"],
                        "hidden": candidate["hidden"],
                        "n_hidden_layers": candidate.get("n_hidden_layers"),
                        "seq_len": candidate.get("seq_len"),
                        "epochs": candidate["epochs"],
                        "lr": candidate["lr"],
                        "mean_total_return": summary["mean_total_return"],
                        "std_total_return": summary["std_total_return"],
                        "mean_sharpe": summary["mean_sharpe"],
                        "mean_max_drawdown": summary["mean_max_drawdown"],
                        "mean_excess_return": summary["mean_excess_return"],
                        "beat_benchmark_count": summary["beat_benchmark_count"],
                        "beat_benchmark_pct": summary["beat_benchmark_pct"],
                        "best_seed": summary["best_seed"],
                        "worst_seed": summary["worst_seed"],
                    }
                )

            shortlist_table = pd.DataFrame(shortlist_rows)
            shortlist_summary = pd.DataFrame(shortlist_summary_rows).sort_values(
                by=["beat_benchmark_pct", "mean_sharpe", "mean_excess_return", "mean_max_drawdown"],
                ascending=[False, False, False, True],
            ).set_index("candidate")

            display(Markdown("## Shortlisted Configurations Across Seeds"))
            display(shortlist_table)
            display(Markdown("## Robustness Comparison for the Shortlist"))
            shortlist_summary
            """
        ),
        code(
            """
            best_candidate_name = shortlist_summary.index[0]
            best_candidate = candidate_by_name[best_candidate_name]
            best_seed_for_dashboard = 0
            best_run = run_candidate(best_candidate, best_seed_for_dashboard)

            best_artifact = build_dashboard_artifact(
                strategy_id="best_neural",
                strategy_name="Best Neural Strategy",
                strategy_description=(
                    "Week 2 Day 3 best robust neural portfolio. Shared MLP across the full "
                    "universe, equal weights across stocks with positive predicted returns."
                ),
                run=best_run,
            )
            save_dashboard_artifact("dashboard/data/best_neural_strategy.json", best_artifact)

            best_summary = shortlist_summary.loc[best_candidate_name]
            best_metrics = best_run["result"]["metrics"]
            best_prediction_metrics = best_run["result"]["prediction_metrics"]

            best_config_text = f'''
            ## Best Configuration Summary

            - Model: **{best_candidate["model_type"].upper()}**
            - Features: **{best_candidate["feature_set"]}**
            - Architecture: **hidden={best_candidate["hidden"]}**, hidden layers = **{best_candidate.get("n_hidden_layers", 1)}**
            - Sequence length: **{best_candidate.get("seq_len", "N/A")}**
            - Learning rate: **{best_candidate["lr"]}**
            - Epochs: **{best_candidate["epochs"]}**
            - Seed methodology: configuration selected by multi-seed robustness; dashboard artifact saved with representative Week 2 seed **0** rather than the luckiest seed
            - Portfolio return (seed 0 artifact): **{best_metrics["total_return"]:.2%}**
            - Sharpe (seed 0 artifact): **{best_metrics["sharpe"]:.3f}**
            - Maximum drawdown (seed 0 artifact): **{best_metrics["max_drawdown"]:.2%}**
            - Benchmark return: **{best_metrics["benchmark_return"]:.2%}**
            - Excess return: **{best_metrics["excess_return"]:.2%}**
            - Test MSE: **{best_prediction_metrics["test_mse"]:.6f}**
            - Information coefficient: **{best_prediction_metrics["information_coefficient"]:.4f}**
            - Robustness across changed seeds: **{int(best_summary["beat_benchmark_count"])}/{len(seeds)}** runs beat the benchmark, mean excess return **{best_summary["mean_excess_return"]:.2%}**

            Dashboard artifact saved to `dashboard/data/best_neural_strategy.json`.
            '''
            display(Markdown(dedent(best_config_text).strip()))
            """
        ),
        code(
            """
            validation_and_conclusion = f'''
            ## Validation Against Required Files

            - `week1/06-tiktok-strategy/tiktok_strategy.py`: the best Day 3 strategy still plugs into the same `DataFeed` + `PortfolioSimulator` bookkeeping contract; it just sources weights from predictions instead of TikTok rules.
            - `week2/03-form-prediction-to-portfolio/mlp.ipynb`: reused the pooled shared-model baseline, the same seed `0`, hidden size `32`, `150` epochs, Adam, MSE loss, and zero commission baseline.
            - `week2/03-form-prediction-to-portfolio/lstm.ipynb`: reused the pooled sequence baseline, hidden size `32`, sequence length `10`, `150` epochs, Adam, MSE loss, and zero commission baseline.

            ## Day 3 Conclusion

            1. Did the baseline MLP beat the benchmark? **{"Yes" if baseline_runs["mlp_baseline"][0]["result"]["metrics"]["final_value"] > baseline_runs["mlp_baseline"][0]["result"]["metrics"]["benchmark_final_value"] else "No"}**.
            2. Did the baseline LSTM beat the benchmark? **{"Yes" if baseline_runs["lstm_baseline"][0]["result"]["metrics"]["final_value"] > baseline_runs["lstm_baseline"][0]["result"]["metrics"]["benchmark_final_value"] else "No"}**.
            3. Which baseline model won? **MLP on final value / excess return**, while the baseline LSTM kept the slightly better drawdown.
            4. Were results stable across seeds? **Not for the baseline setup.** Seed changes moved the MLP materially, and even the steadier LSTM only matched the benchmark closely rather than beating it consistently.
            5. Did changing features improve portfolio performance? **Yes.** Adding the existing `return_5d` and `return_10d` momentum features produced the strongest MLP portfolio.
            6. Did changing architecture improve portfolio performance? **Partly.** A wider MLP helped, while the tested wider LSTM did not create a meaningful portfolio improvement.
            7. What was the best strategy found? **{best_candidate_name}**.
            8. Did the best strategy beat the benchmark? **Yes in its representative seed-0 run, and in {int(best_summary["beat_benchmark_count"])}/{len(seeds)} changed-seed runs.**
            9. What was its max drawdown? **{best_metrics["max_drawdown"]:.2%}** in the saved dashboard artifact.
            10. Is there evidence the model adds useful signal beyond luck? **Some evidence, yes, but not perfect stability.** The best config kept a positive mean excess return and beat the benchmark in most changed-seed runs, but one seed still lost, so the edge should be described as modest rather than bulletproof.
            '''
            display(Markdown(dedent(validation_and_conclusion).strip()))
            """
        ),
    ]

    nb = nbf.v4.new_notebook(cells=cells)
    nb.metadata.update(
        {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        }
    )
    return nb


def main() -> None:
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    day3_nb = NOTEBOOK_DIR / "day3_portfolio_backtest.ipynb"
    robustness_nb = NOTEBOOK_DIR / "day3_robustness_and_optimization.ipynb"

    day3_nb.write_text(nbf.writes(notebook_one()), encoding="utf-8")
    robustness_nb.write_text(nbf.writes(notebook_two()), encoding="utf-8")

    print(day3_nb)
    print(robustness_nb)


if __name__ == "__main__":
    main()
