"""Migrate all blueprints/*.py (except __init__) into addons/<name>/. Run from repo root: python tools/migrate_blueprints_to_addons.py"""
from __future__ import annotations
import ast
import re
import shutil
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS = ROOT / 'blueprints'
TEMPLATES = ROOT / 'templates'
MODULES: list[tuple[str, str, str]] = [('auth', 'auth_bp', 'auth'), ('dashboard', 'dashboard_bp', 'dashboard'), ('itemmaster', 'itemmaster_bp', 'itemmaster'), ('users', 'users_bp', 'users'), ('api', 'api_bp', 'api'), ('system_config', 'system_config_bp', 'system_config'), ('company_profile', 'company_profile_bp', 'company_profile'), ('reports', 'reports_bp', 'reports'), ('sms', 'sms_bp', 'sms'), ('sales_summary', 'sales_summary_bp', 'sales_summary'), ('roles', 'roles_bp', 'roles'), ('customer', 'customer_bp', 'customer'), ('employee', 'employee_bp', 'employee'), ('supplier', 'supplier_bp', 'supplier'), ('pos_billing', 'pos_billing_bp', 'pos_billing'), ('promotions', 'promotions_bp', 'promotions'), ('notifications', 'notifications_bp', 'notifications'), ('salesman_summary', 'salesman_summary_bp', 'salesman_summary'), ('tenants', 'tenants_bp', 'tenants'), ('ho', 'ho_bp', 'ho')]

def _insert_pathlib(text: str) -> str:
    if 'from pathlib import Path' in text:
        return text
    m = re.match('(^"""[\\s\\S]*?"""\\s*\\n)', text)
    if m:
        return m.group(0) + 'from pathlib import Path\n\n' + text[m.end():]
    return 'from pathlib import Path\n\n' + text

def _template_names(py_text: str) -> list[str]:
    tree = ast.parse(py_text)

    class V(ast.NodeVisitor):

        def __init__(self) -> None:
            self.names: list[str] = []

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == 'render_template':
                if node.args:
                    a = node.args[0]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        self.names.append(a.value)
                    elif isinstance(a, ast.Str):
                        self.names.append(a.s)
            self.generic_visit(node)
    v = V()
    v.visit(tree)
    seen: set[str] = set()
    out: list[str] = []
    for n in v.names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

def _replace_blueprint_line(text: str, bp_old: str, flask_name: str, tech: str) -> str:
    block = f'_ADDON_ROOT = Path(__file__).resolve().parents[1]\n\nbp = Blueprint(\n    "{flask_name}",\n    __name__,\n    template_folder=str(_ADDON_ROOT / "views" / "templates"),\n)\n'
    line_pat = re.compile('^' + re.escape(bp_old) + '\\s*=\\s*Blueprint\\(\\s*[\'\\"]' + re.escape(flask_name) + '[\'\\"]\\s*,\\s*__name__\\s*\\)\\s*$', re.MULTILINE)
    m = line_pat.search(text)
    if not m:
        print(f'[ERROR] No blueprint line for {tech}: {bp_old} = Blueprint(...)', file=sys.stderr)
        sys.exit(1)
    return line_pat.sub(block.rstrip('\n'), text, count=1)

def _prefix_templates(text: str, prefix: str) -> str:

    def rr(mm: re.Match[str]) -> str:
        name = mm.group(1)
        if '/' in name:
            return mm.group(0)
        return f'render_template("{prefix}/{name}"'
    out = re.sub('render_template\\(\\s*"([^"]+\\.html)"', rr, text)
    return out

def _write_addon_meta(tech: str, flask_name: str) -> None:
    title = flask_name.replace('_', ' ').title()
    mf = ROOT / 'addons' / tech / '__manifest__.py'
    mf.write_text(f'''"""Addon manifest — {title}."""\n\n\nMANIFEST = {{\n    "technical_name": "{tech}",\n    "name": "{title}",\n    "version": "1.0.0",\n    "category": "Legacy",\n    "summary": "Migrated from blueprints/{tech}.py",\n    "depends": [],\n    "application": False,\n    "installable": True,\n    "license": "LGPL-3",\n    "urls": {{"prefix": "/{tech.replace('_', '-')}"}},\n    "flask": {{\n        "blueprint": "{flask_name}",\n        "blueprint_ref": "addons.{tech}:bp",\n        "routes_module": "addons.{tech}.controllers.routes",\n    }},\n}}\n''', encoding='utf-8')
    init = ROOT / 'addons' / tech / '__init__.py'
    init.write_text(f'"""Addon `{tech}` (migrated from blueprints)."""\n\nfrom addons.{tech}.controllers.routes import bp\n\n__all__ = ["bp"]\n', encoding='utf-8')
    ci = ROOT / 'addons' / tech / 'controllers' / '__init__.py'
    ci.parent.mkdir(parents=True, exist_ok=True)
    ci.write_text('"""Routes."""\n', encoding='utf-8')

def main() -> None:
    for tech, bp_old, flask_name in MODULES:
        src_py = BLUEPRINTS / f'{tech}.py'
        if not src_py.is_file():
            print(f'Skip (missing): {src_py}')
            continue
        raw = src_py.read_text(encoding='utf-8')
        tmpls = _template_names(raw)
        text = _insert_pathlib(raw)
        text = _replace_blueprint_line(text, bp_old, flask_name, tech)
        text = text.replace(bp_old, 'bp')
        text = _prefix_templates(text, tech)
        if tech == 'ho':
            text = text.replace('from blueprints.customer import (', 'from addons.customer.controllers.routes import (', 1)
        dest = ROOT / 'addons' / tech / 'controllers' / 'routes.py'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
        td = ROOT / 'addons' / tech / 'views' / 'templates' / tech
        td.mkdir(parents=True, exist_ok=True)
        for html in tmpls:
            if '/' in html:
                raise SystemExit(f'{tech}: path template not supported yet: {html}')
            sf = TEMPLATES / html
            if not sf.is_file():
                raise FileNotFoundError(f'Missing template: {sf}')
            shutil.copy2(sf, td / html)
        _write_addon_meta(tech, flask_name)
        print(f'OK {tech}: {len(tmpls)} templates')
    print('Done. Remove blueprints/*.py (except __init__) and simplify app.py.')
if __name__ == '__main__':
    main()
