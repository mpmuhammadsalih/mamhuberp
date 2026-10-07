"""Discover addon packages and load their __manifest__.py as a dict."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Tuple
_addons_root = Path(__file__).resolve().parent.parent

def addons_root() -> Path:
    return _addons_root

def discover_addon_dirs() -> List[Path]:
    """Return sibling addon folders containing __manifest__.py (excludes ``core``, ``__pycache__``)."""
    skip = {'core', '__pycache__'}
    out: List[Path] = []
    if not _addons_root.is_dir():
        return out
    for child in sorted(_addons_root.iterdir()):
        if not child.is_dir() or child.name in skip:
            continue
        mf = child / '__manifest__.py'
        if mf.is_file():
            out.append(child)
    return out

def load_manifest_dict(addon_dir: Path) -> Tuple[str, Dict[str, Any]]:
    """
    Exec ``addon_dir/__manifest__.py`` and return ``(technical_name, MANIFEST)``.

    Raises if MANIFEST dict is missing or has no technical_name.
    """
    mf_path = addon_dir / '__manifest__.py'
    mod_name = f'_addon_manifest_{addon_dir.name}'
    spec = importlib.util.spec_from_file_location(mod_name, mf_path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load manifest: {mf_path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    manifest = getattr(mod, 'MANIFEST', None)
    if not isinstance(manifest, dict):
        raise ValueError(f'{mf_path}: MANIFEST must be a dict')
    tech = manifest.get('technical_name') or addon_dir.name
    return (str(tech), manifest)

def iter_installable_addons() -> List[Tuple[str, Path, Dict[str, Any]]]:
    """(technical_name, path, MANIFEST) for each addon where installable is truthy."""
    rows: List[Tuple[str, Path, Dict[str, Any]]] = []
    for d in discover_addon_dirs():
        try:
            tech, mf = load_manifest_dict(d)
        except Exception:
            continue
        if mf.get('installable', True):
            rows.append((tech, d, mf))
    return rows
