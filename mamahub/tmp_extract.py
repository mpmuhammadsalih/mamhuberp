from pathlib import Path
path = Path('d:\\webapps\\RGC_Dynamics - All\\addons\\temporary_collection\\controllers\\routes.py')
lines = path.read_text(encoding='utf-8').splitlines()
inside = []
record = False
for i, ln in enumerate(lines):
    if not record and ln.strip() == 'try:' and (i > 4720):
        prev = ''.join(lines[i - 2:i]) if i >= 2 else ''
        if 'current_user' in prev:
            record = True
            inside.append(ln)
            continue
    if record:
        inside.append(ln)
        if ln.startswith('    except Exception as e:'):
            rest = lines[i + 1:i + 6]
            if any(('traceback.format_exc()' in x for x in rest)):
                break
out = Path('d:\\webapps\\RGC_Dynamics - All\\_snip_tc.txt')
out.write_text('\n'.join(inside) + '\n', encoding='utf-8')
print('lines', len(inside), 'chars', sum((len(x) for x in inside)))
