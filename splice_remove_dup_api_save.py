"""Remove duplicated api_save body; delegate to _temporary_collection_save_run."""
from pathlib import Path
path = Path('d:\\webapps\\RGC_Dynamics - All\\addons\\temporary_collection\\controllers\\routes.py')
lines = path.read_text(encoding='utf-8').splitlines()
start = None
end = None
for i, L in enumerate(lines):
    if L.strip() == 'voucherno = data.get("voucherno", "").strip()' and i > 5100:
        start = i
        break
if start is None:
    raise SystemExit('start not found')
for j in range(start, len(lines)):
    if lines[j].strip().startswith('@bp.route("/accounts/temporary-collection/api/query"'):
        end = j
        break
if end is None:
    raise SystemExit('end not found')
new_block = ['    return _temporary_collection_save_response(*_temporary_collection_save_run(data))']
out = lines[:start] + new_block + lines[end:]
path.write_text('\n'.join(out) + '\n', encoding='utf-8')
print('removed lines', start, 'to', end - 1, 'kept', len(new_block), 'line(s)')
