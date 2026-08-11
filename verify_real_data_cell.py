import re
from pathlib import Path
import pandas as pd

text = Path('model_comparison_notebook.ipynb').read_text(encoding='utf-8')
pattern = r'<VSCode\.Cell[^>]*id="#VSC-7c67c6bb"[^>]*language="python"[^>]*>(.*?)</VSCode\.Cell>'
match = re.search(pattern, text, re.S)
if not match:
    raise SystemExit('Data-preparation cell not found')
code = match.group(1)
ns = {'pd': pd, 'Path': Path}
exec(code, ns)
print(ns['comparison_df'].head())
print('rows=', len(ns['comparison_df']))
print('columns=', list(ns['comparison_df'].columns))
