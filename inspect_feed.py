from pathlib import Path
source = Path('app.py').read_text(encoding='utf-8')
for i, line in enumerate(source.splitlines(), 1):
    if 2680 <= i <= 2760:
        print(f'{i}: {line}')
