import json, os, re, sys
from pathlib import Path

root = Path(r'c:\Users\Lenovo\2026-orion')

# Parse notebook outputs
notebooks = [
    ('LSTM_Task.ipynb', ['Final Test Loss:', 'MLP test loss', 'LSTM test loss', 'Mean return:', 'Sharpe ratio:']),
    ('stock_prediction.ipynb', ['final test loss:']),
    ('week2/01-mlp/notebook.ipynb', ['final test loss:', 'test loss is']),
    ('week2/02-lstm/notebook.ipynb', ['LSTM (5-step window) test loss:', 'MLP  (1-point) test loss:', 'error reduction:']),
    ('week1/05-tiktok-strategy/notebook.ipynb', ['Total Return:', 'Sharpe:', 'Max Drawdown:']),
]

for rel, needles in notebooks:
    path = root / rel
    nb = json.loads(path.read_text(encoding='utf-8'))
    print(f'\n=== {rel} ===')
    for i, cell in enumerate(nb['cells']):
        if cell.get('cell_type') != 'code':
            continue
        src = ''.join(cell.get('source', []))
        if not src.strip():
            continue
        if any(n.lower() in src.lower() for n in needles):
            print(f'-- cell {i} --')
            print(src[:2500])
            for out in cell.get('outputs', []):
                if 'text' in out:
                    txt = ''.join(out['text'])
                    if txt.strip():
                        print('OUTPUT:', txt[:1500])
                elif 'data' in out and 'text/plain' in out['data']:
                    print('OUTPUT:', out['data']['text/plain'][:1500])
            print('---')

# Try to run the TikTok Python strategy and print summary if possible
sys.path.insert(0, str(root))
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('tiktok_strategy', root / 'week1/06-tiktok-strategy/tiktok_strategy.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print('\n=== week1/06-tiktok-strategy/tiktok_strategy.py ===')
    print('Loaded strategy function:', mod.make_tiktok_guru_strategy)
    print('Script imports and backtest call are present.')
except Exception as e:
    print('\n=== week1/06-tiktok-strategy/tiktok_strategy.py ===')
    print('Could not execute directly:', repr(e))
