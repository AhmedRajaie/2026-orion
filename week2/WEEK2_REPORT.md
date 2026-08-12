# Week 2 Summary

## Objective
This report summarises the Week 2 notebooks created for MLP, LSTM, portfolio construction, dashboard-style AI components, and modern portfolio theory.

## Methods
- Reused the repository DataFeed, feature builders, and model utilities where possible.
- Used chronological splits and simple modular training loops.
- Backtested strategies through PortfolioSimulator.
- Added notebook-ready sentiment and chatbot helper functions.

## Experiments
- MLP: trained on one stock with a simple configurable deep MLP.
- LSTM: trained on sequences with a small LSTM architecture.
- Portfolio: converted predictions into long-only weights and evaluated them with PortfolioSimulator.
- AI dashboard: implemented modular sentiment analysis and a rule-based assistant.
- MPT: approximated the efficient frontier using random long-only portfolios.

## Best Hyperparameters
- MLP: 2 hidden layers, 32 hidden units, 60 epochs, batch size 32, learning rate 1e-3.
- LSTM: sequence length 5, hidden size 16, 1 layer, 60 epochs, batch size 32, learning rate 1e-3.

## Best Model
The LSTM provided the strongest sequence-based baseline in the example notebooks, although the final choice depends on the stock and dataset split.

## Best Portfolio
The portfolio notebook demonstrates a simple long-only prediction-based portfolio and can be extended to compare MLP, LSTM, and MPT allocations directly.

## Lessons Learned
- Chronological validation is essential for financial time series.
- Larger networks can overfit if they are not carefully evaluated.
- Portfolio construction is equally important as prediction quality.

## Future Improvements
- Add robust walk-forward validation.
- Compare more hyperparameter settings.
- Connect the notebooks to the dashboard strategy selector once a strategy registration hook exists.
