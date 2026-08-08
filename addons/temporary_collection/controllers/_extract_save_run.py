PATH = Path(__file__).resolve().parent / 'routes.py'
from pathlib import Path
txt = PATH.read_text(encoding='utf-8')
lines = txt.splitlines(True)
start = None
end = None
for i, L in enumerate(lines):
    if L.strip().startswith('def api_save'):
        ai = i + 1
        while ai < len(lines) and 'current_user' not in lines[ai]:
            ai += 1
        while ai < len(lines) and 'current_user =' not in lines[ai]:
            ai += 1
        start = ai + 1
        break
if start is None:
    raise SystemExit('start not found')
while start < len(lines) and 'try:' not in lines[start]:
    start += 1
end = start
brace = 0
exc_idx = None
for j in range(start, len(lines)):
    if lines[j].startswith('    except Exception as e:') and exc_idx is None:
        exc_idx = j
        break
if exc_idx is None:
    raise SystemExit('except not found')
end = exc_idx
while end < len(lines):
    line = lines[end]
    end += 1
    if end < len(lines) and lines[end].strip().startswith('@bp.route'):
        break
print('start_line', start + 1, 'slice end', end)
