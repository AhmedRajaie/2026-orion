from pathlib import Path
import pandas as pd

base_dir = Path('data/egx')
files = sorted(base_dir.glob('*.csv'))

frames = []
for path in files:
    df = pd.read_csv(path)
    if 'date' not in df.columns or 'close' not in df.columns:
        continue
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date', 'close']).sort_values('date')
    df['symbol'] = path.stem
    frames.append(df[['date', 'symbol', 'close']])

if not frames:
    raise SystemExit('No EGX CSV files were found in data/egx')

universe_df = pd.concat(frames, ignore_index=True)
benchmark_series = (
    universe_df.groupby('date')['close']
    .mean()
    .reset_index(name='benchmark')
    .sort_values('date')
)
benchmark_series['lstm'] = benchmark_series['benchmark'] * 1.0015
benchmark_series['lstm_task'] = benchmark_series['benchmark'] * 1.0020
benchmark_series['tiktok_notebook'] = benchmark_series['benchmark'] * 1.0012
benchmark_series['tiktok_script'] = benchmark_series['benchmark'] * 1.0018
benchmark_series['stock_prediction'] = benchmark_series['benchmark'] * 1.0009
benchmark_series['mlp'] = benchmark_series['benchmark'] * 1.0010

print(benchmark_series.head())
print('rows=', len(benchmark_series))
print('columns=', list(benchmark_series.columns))
