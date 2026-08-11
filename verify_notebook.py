import re
import traceback
from pathlib import Path

path = Path('model_comparison_notebook.ipynb')
text = path.read_text(encoding='utf-8')
pattern = re.compile(r'<VSCode\.Cell([^>]*)language="([^"]+)"[^>]*>(.*?)</VSCode\.Cell>', re.S)

for idx, match in enumerate(pattern.finditer(text), 1):
    lang = match.group(2)
    body = match.group(3).strip()
    if lang != 'python' or not body:
        continue
    print(f'--- Executing cell {idx} ---')
    try:
        ns = {}
        exec(body, ns)
        print('OK')
    except Exception as e:
        print('ERROR:', type(e).__name__, e)
        traceback.print_exc()
        break
else:
    print('All Python cells executed successfully.')
