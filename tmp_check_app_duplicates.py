from collections import Counter
import re

def find_duplicates(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    funcs = re.findall(r'^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', text, flags=re.MULTILINE)
    counter = Counter(funcs)
    return {name: count for name, count in counter.items() if count > 1}

if __name__ == '__main__':
    dups = find_duplicates('app.py')
    if not dups:
        print('No duplicate function names found.')
    else:
        for name, count in sorted(dups.items()):
            print(f'{name}: {count}')
