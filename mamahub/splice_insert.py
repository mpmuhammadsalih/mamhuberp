from pathlib import Path
r = Path('d:\\webapps\\RGC_Dynamics - All\\addons\\temporary_collection\\controllers\\routes.py')
t = r.read_text(encoding='utf-8')
ins = Path('d:\\webapps\\RGC_Dynamics - All\\_tc_run_full.py').read_text(encoding='utf-8').lstrip('\n')
marker = '@bp.route("/accounts/temporary-collection/api/save", methods=["POST"])'
i = t.find(marker)
if i < 0:
    raise SystemExit('marker not found')
t2 = t[:i] + '\n\n' + ins + '\n\n' + t[i:]
r.write_text(t2, encoding='utf-8')
print('inserted at', i)
