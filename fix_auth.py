path = 'blueprints/auth.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
start = None
end = None
for i, line in enumerate(lines):
    if '# User is verified (counter check removed)' in line:
        start = i
    if start is not None and '# User is verified, proceed with login setup' in line and (i > start):
        end = i
        break
if start is not None and end is not None:
    new_lines = lines[:start] + [lines[end]] + lines[end + 1:]
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print('Removed lines', start, 'to', end - 1, 'inclusive. Kept line', end)
else:
    print('Markers not found. start=', start, 'end=', end)
