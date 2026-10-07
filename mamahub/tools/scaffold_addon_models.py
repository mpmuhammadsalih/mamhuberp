"""Scaffold addons/<name>/models/__init__.py + <name>_models.py for each addon. Idempotent."""
from __future__ import annotations
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ADDONS = ROOT / 'addons'
SKIP_DIRS = {'core', '__pycache__'}
INIT_TEMPLATE = '"""\nData layer for ``{tech}`` — DTOs, repositories, and adapters into shared ``db`` helpers.\n\nKeep HTTP in ``controllers/routes.py``; move query logic here over time.\n"""\n\n__all__: list[str] = []\n\n'
STUB_TEMPLATE = '"""Domain scaffolding for ``{tech}`` — add dataclasses / repository functions here.\n\nDelegate SQL to shared ``db`` helpers (``_safe_rows``, ``_get_connection``, etc.).\n"""\n\nfrom __future__ import annotations\n\nfrom typing import Any, Dict, List\n\n__all__: list[str] = []\n\n# Example:\n# @dataclass(frozen=True)\n# class SomeRow:\n#     id: int\n#\n# def list_some_rows() -> List[Dict[str, Any]]:\n#     ...\n'

def slug(tech: str) -> str:
    s = re.sub('[^a-z0-9_]', '_', tech.lower()).strip('_')
    return s or 'domain'

def patch_manifest(manifest_path: Path, tech: str) -> None:
    text = manifest_path.read_text(encoding='utf-8')
    if 'models_package' in text:
        return
    key = f'"blueprint_ref": "addons.{tech}:bp"'
    if key not in text:
        print(f'[WARN] {tech}: manifest patch skipped (no blueprint_ref match)', file=sys.stderr)
        return
    insert = f'        "models_package": "addons.{tech}.models",\n'
    text = text.replace(key + ',\n', key + ',\n' + insert, 1)
    manifest_path.write_text(text, encoding='utf-8')
    print(f'[{tech}] manifest +models_package')

def main() -> None:
    for child in sorted(ADDONS.iterdir()):
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        if not (child / '__manifest__.py').is_file():
            continue
        tech = child.name
        stem = slug(tech)
        stub_name = f'{stem}_models.py'
        models_dir = child / 'models'
        models_dir.mkdir(exist_ok=True)
        init_py = models_dir / '__init__.py'
        if tech == 'demo_sales':
            patch_manifest(child / '__manifest__.py', tech)
            stub = models_dir / stub_name
            if not stub.is_file():
                stub.write_text(STUB_TEMPLATE.format(tech=tech), encoding='utf-8')
                print(f'[{tech}] created models/{stub_name} (stub)')
            continue
        if not init_py.is_file():
            init_py.write_text(INIT_TEMPLATE.format(tech=tech), encoding='utf-8')
            print(f'[{tech}] created models/__init__.py')
        stub = models_dir / stub_name
        if not stub.is_file():
            stub.write_text(STUB_TEMPLATE.format(tech=tech), encoding='utf-8')
            print(f'[{tech}] created models/{stub_name}')
        patch_manifest(child / '__manifest__.py', tech)
    print('Done scaffolding models/ + manifest models_package.')
if __name__ == '__main__':
    main()
