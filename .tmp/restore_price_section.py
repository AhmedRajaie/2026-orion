from pathlib import Path
from textwrap import dedent

import nbformat as nbf


repo_root = Path(__file__).resolve().parents[1]
notebook_path = repo_root / "week2" / "02-lstm" / "day2_lstm_vs_mlp.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(dedent(text).strip() + "\n")


def code(text: str):
    return nbf.v4.new_code_cell(dedent(text).strip() + "\n")


nb = nbf.read(notebook_path, as_version=4)

marker = "# ABUK Price Prediction Comparison"
for i, cell in enumerate(nb.cells):
    if cell.cell_type == "markdown" and cell.source.strip().startswith(marker):
        nb.cells = nb.cells[:i]
        break


new_cells = [
    md(
        """
        # ABUK Price Prediction Comparison

        The MLP and LSTM in this notebook were trained to predict next-day ABUK returns rather than directly predict stock prices. To evaluate those same test predictions in price terms, we convert each predicted return into a one-step-ahead predicted closing price and compare it with the actual ABUK closing price over the same test period.

        Week 2 uses simple returns, so the price conversion here is:

        `predicted_price_t = actual_previous_close * (1 + predicted_return_t)`

        This stays a one-step-ahead experiment because every forecast starts from the actual previous close, not from the previous predicted close.
        """
    ),
    code(
        """
        from tradinglab.features import feature_columns


        def mean_absolute_error(actual, predicted) -> float:
            actual = np.asarray(actual, dtype=float)
            predicted = np.asarray(predicted, dtype=float)
            return float(np.mean(np.abs(predicted - actual)))


        def root_mean_squared_error(actual, predicted) -> float:
            actual = np.asarray(actual, dtype=float)
            predicted = np.asarray(predicted, dtype=float)
            return float(np.sqrt(np.mean((predicted - actual) ** 2)))


        def mean_absolute_percentage_error(actual, predicted) -> float:
            actual = np.asarray(actual, dtype=float)
            predicted = np.asarray(predicted, dtype=float)
            mask = actual != 0
            if not np.any(mask):
                return 0.0
            return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100.0)


        def tolerance_accuracy(actual, predicted, tolerance_pct: float) -> float:
            actual = np.asarray(actual, dtype=float)
            predicted = np.asarray(predicted, dtype=float)
            mask = actual != 0
            if not np.any(mask):
                return 0.0
            pct_error = np.abs(predicted[mask] - actual[mask]) / actual[mask] * 100.0
            return float(np.mean(pct_error <= tolerance_pct) * 100.0)


        def price_directional_accuracy(actual, predicted, previous_actual) -> float:
            actual = np.asarray(actual, dtype=float)
            predicted = np.asarray(predicted, dtype=float)
            previous_actual = np.asarray(previous_actual, dtype=float)
            actual_direction = np.sign(actual - previous_actual)
            predicted_direction = np.sign(predicted - previous_actual)
            return float(np.mean(actual_direction == predicted_direction) * 100.0)


        def price_metrics(actual, predicted, previous_actual) -> dict[str, float]:
            mape = mean_absolute_percentage_error(actual, predicted)
            return {
                "mae": mean_absolute_error(actual, predicted),
                "rmse": root_mean_squared_error(actual, predicted),
                "mape": mape,
                "price_accuracy": max(0.0, 100.0 - mape),
                "within_1pct": tolerance_accuracy(actual, predicted, 1.0),
                "within_2pct": tolerance_accuracy(actual, predicted, 2.0),
                "within_5pct": tolerance_accuracy(actual, predicted, 5.0),
                "directional_accuracy": price_directional_accuracy(actual, predicted, previous_actual),
            }


        abuk_close = feed.close[:, asset]
        abuk_features = feature_columns(feed, asset)
        abuk_target_returns = np.full(feed.n_days, np.nan)
        abuk_target_returns[:-1] = feed.returns[1:, asset]

        day_index = np.arange(feed.n_days)
        valid_rows = ~np.isnan(abuk_features).any(axis=1) & ~np.isnan(abuk_target_returns)
        full_test_feature_days = day_index[valid_rows & (day_index >= split_day)]
        aligned_test_feature_days = full_test_feature_days[seq_len:]

        previous_actual_test_prices = abuk_close[aligned_test_feature_days]
        actual_test_prices = abuk_close[aligned_test_feature_days + 1]
        test_price_dates = feed.dates[aligned_test_feature_days + 1]

        assert np.allclose(y_test, abuk_target_returns[aligned_test_feature_days])
        assert np.allclose(y_test, feed.returns[aligned_test_feature_days + 1, asset])
        assert np.allclose(actual_test_prices, previous_actual_test_prices * (1.0 + y_test))

        mlp_predicted_prices = previous_actual_test_prices * (1.0 + mlp_test_pred)
        lstm_predicted_prices = previous_actual_test_prices * (1.0 + lstm_test_pred)
        naive_predicted_prices = previous_actual_test_prices.copy()

        assert len(actual_test_prices) == len(previous_actual_test_prices)
        assert len(actual_test_prices) == len(mlp_predicted_prices)
        assert len(actual_test_prices) == len(lstm_predicted_prices)
        assert len(actual_test_prices) == len(naive_predicted_prices)
        assert len(actual_test_prices) == len(test_price_dates)
        assert np.isfinite(actual_test_prices).all()
        assert np.isfinite(previous_actual_test_prices).all()
        assert np.isfinite(mlp_predicted_prices).all()
        assert np.isfinite(lstm_predicted_prices).all()
        assert np.isfinite(naive_predicted_prices).all()

        mlp_price_results = price_metrics(actual_test_prices, mlp_predicted_prices, previous_actual_test_prices)
        lstm_price_results = price_metrics(actual_test_prices, lstm_predicted_prices, previous_actual_test_prices)
        naive_price_results = price_metrics(actual_test_prices, naive_predicted_prices, previous_actual_test_prices)

        mlp_price_accuracy = mlp_price_results["price_accuracy"]
        lstm_price_accuracy = lstm_price_results["price_accuracy"]
        naive_price_accuracy = naive_price_results["price_accuracy"]

        print(f"Price evaluation stock: {symbol}")
        print(f"Price evaluation dates: {test_price_dates[0]} -> {test_price_dates[-1]}")
        print(f"Aligned test observations: {len(actual_test_prices)}")
        print("Target scaling/normalization: none, so no inverse transform was needed.")
        print("Return definition confirmed from DataFeed: simple return = close[t] / close[t-1] - 1")
        """
    ),
    code(
        """
        plt.figure(figsize=(13, 5))
        plt.plot(test_price_dates, actual_test_prices, label="Actual ABUK close", linewidth=1.8)
        plt.plot(test_price_dates, mlp_predicted_prices, label="MLP predicted close", linewidth=1.2)
        plt.plot(test_price_dates, lstm_predicted_prices, label="LSTM predicted close", linewidth=1.2)
        plt.xlabel("Date")
        plt.ylabel("Price (EGP)")
        plt.title("ABUK - Actual vs Predicted Closing Price (Test Set)")
        plt.grid(alpha=0.3)
        plt.legend()
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.show()

        plt.figure(figsize=(13, 4))
        plt.plot(test_price_dates, np.abs(actual_test_prices - naive_predicted_prices), label="Naive absolute error", linewidth=1.2)
        plt.plot(test_price_dates, np.abs(actual_test_prices - mlp_predicted_prices), label="MLP absolute error", linewidth=1.2)
        plt.plot(test_price_dates, np.abs(actual_test_prices - lstm_predicted_prices), label="LSTM absolute error", linewidth=1.2)
        plt.xlabel("Date")
        plt.ylabel("Absolute Error (EGP)")
        plt.title("ABUK - Absolute Price Prediction Error")
        plt.grid(alpha=0.3)
        plt.legend()
        plt.xticks(rotation=30)
        plt.tight_layout()
        plt.show()
        """
    ),
    code(
        """
        price_summary_lines = [
            "## ABUK PRICE PREDICTION - TEST SET",
            "",
            "Price accuracy (100 - MAPE) is an intuitive percentage derived from MAPE, not a classification accuracy measure.",
            "",
            "| Metric | Naive | MLP | LSTM |",
            "|---|---:|---:|---:|",
            f"| MAE (EGP) | {naive_price_results['mae']:.3f} | {mlp_price_results['mae']:.3f} | {lstm_price_results['mae']:.3f} |",
            f"| RMSE (EGP) | {naive_price_results['rmse']:.3f} | {mlp_price_results['rmse']:.3f} | {lstm_price_results['rmse']:.3f} |",
            f"| MAPE (%) | {naive_price_results['mape']:.3f}% | {mlp_price_results['mape']:.3f}% | {lstm_price_results['mape']:.3f}% |",
            f"| Price accuracy (100 - MAPE) | {naive_price_results['price_accuracy']:.3f}% | {mlp_price_results['price_accuracy']:.3f}% | {lstm_price_results['price_accuracy']:.3f}% |",
            f"| Within +/-1% | {naive_price_results['within_1pct']:.2f}% | {mlp_price_results['within_1pct']:.2f}% | {lstm_price_results['within_1pct']:.2f}% |",
            f"| Within +/-2% | {naive_price_results['within_2pct']:.2f}% | {mlp_price_results['within_2pct']:.2f}% | {lstm_price_results['within_2pct']:.2f}% |",
            f"| Within +/-5% | {naive_price_results['within_5pct']:.2f}% | {mlp_price_results['within_5pct']:.2f}% | {lstm_price_results['within_5pct']:.2f}% |",
            f"| Directional accuracy | {naive_price_results['directional_accuracy']:.2f}% | {mlp_price_results['directional_accuracy']:.2f}% | {lstm_price_results['directional_accuracy']:.2f}% |",
        ]
        display(Markdown("\\n".join(price_summary_lines)))
        """
    ),
    code(
        """
        from textwrap import dedent


        def lower_is_better(metric_name: str) -> str:
            values = {
                "Naive": naive_price_results[metric_name],
                "MLP": mlp_price_results[metric_name],
                "LSTM": lstm_price_results[metric_name],
            }
            return min(values, key=values.get)


        def higher_is_better(metric_name: str) -> str:
            values = {
                "Naive": naive_price_results[metric_name],
                "MLP": mlp_price_results[metric_name],
                "LSTM": lstm_price_results[metric_name],
            }
            return max(values, key=values.get)


        best_mae = lower_is_better("mae")
        best_rmse = lower_is_better("rmse")
        best_mape = lower_is_better("mape")
        best_price_accuracy = higher_is_better("price_accuracy")
        best_within_1 = higher_is_better("within_1pct")
        best_within_2 = higher_is_better("within_2pct")
        best_within_5 = higher_is_better("within_5pct")
        best_direction = higher_is_better("directional_accuracy")

        if (
            lstm_price_results["mae"] < mlp_price_results["mae"]
            and lstm_price_results["rmse"] < mlp_price_results["rmse"]
            and lstm_price_results["mape"] < mlp_price_results["mape"]
        ):
            lstm_vs_mlp = (
                f"The LSTM improved on the MLP on the main price-error metrics "
                f"(MAE {mlp_price_results['mae']:.3f} -> {lstm_price_results['mae']:.3f}, "
                f"RMSE {mlp_price_results['rmse']:.3f} -> {lstm_price_results['rmse']:.3f}, "
                f"MAPE {mlp_price_results['mape']:.3f}% -> {lstm_price_results['mape']:.3f}%), "
                f"although the MLP kept a slightly higher directional accuracy."
            )
        else:
            lstm_vs_mlp = "The LSTM did not deliver a clean improvement over the MLP across the main price metrics."

        if (
            naive_price_results["mae"] <= min(mlp_price_results["mae"], lstm_price_results["mae"])
            and naive_price_results["rmse"] <= min(mlp_price_results["rmse"], lstm_price_results["rmse"])
            and naive_price_results["mape"] <= min(mlp_price_results["mape"], lstm_price_results["mape"])
            and naive_price_results["price_accuracy"] >= max(mlp_price_results["price_accuracy"], lstm_price_results["price_accuracy"])
        ):
            benchmark_sentence = (
                "Neither neural network beat the naive previous-close benchmark on the main price-level metrics, so neither added clear value over simply carrying forward yesterday's close."
            )
        else:
            benchmark_sentence = (
                "At least one neural network beat the naive previous-close benchmark on some main price-level metrics."
            )

        interpretation = f'''
        ## Which Model Predicted ABUK Price Best?

        The lowest MAE came from **{best_mae}**, the lowest RMSE came from **{best_rmse}**, and the lowest MAPE came from **{best_mape}**. The highest price accuracy (100 - MAPE) also came from **{best_price_accuracy}**.

        For tolerance accuracy, the best results were **{best_within_1}** within +/-1%, **{best_within_2}** within +/-2%, and **{best_within_5}** within +/-5%. The highest directional accuracy came from **{best_direction}**.

        The MLP stayed numerically close to the real ABUK close on many days, with a test MAPE of {mlp_price_results['mape']:.3f}% and price accuracy of {mlp_price_results['price_accuracy']:.3f}%. The LSTM was similarly close, with a test MAPE of {lstm_price_results['mape']:.3f}% and price accuracy of {lstm_price_results['price_accuracy']:.3f}%.

        **Was the MLP able to predict the ABUK price accurately?** In a narrow price-level sense, yes, it stayed close on average; but it did not beat the naive previous-close benchmark.

        **Was the LSTM able to predict the ABUK price accurately?** Also yes in a narrow price-level sense, and it slightly improved on the MLP's MAE, RMSE, MAPE, price accuracy, and +/-1% and +/-2% hit rates; but it still did not beat the naive previous-close benchmark.

        **Which model was better?** Among the two neural networks, the **LSTM** was slightly better on the main price-error metrics, while the **MLP** had a slightly better directional accuracy and +/-5% hit rate.

        **Did either neural network add value over simply using yesterday's closing price?** {benchmark_sentence}

        {lstm_vs_mlp}

        **Interpretation warning:** a high "price accuracy" percentage does not automatically mean strong forecasting skill. Consecutive stock prices are usually close to each other, so even the naive previous-close benchmark can score very highly. That is why the neural networks should be judged against the naive benchmark, not only by how close their price lines look on the chart.
        '''
        display(Markdown(dedent(interpretation).strip()))
        """
    ),
]

nb.cells.extend(new_cells)
nbf.write(nb, notebook_path)
print(notebook_path)
