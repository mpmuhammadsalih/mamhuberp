"""
Optional menu aggregation across addons.

The live sidebar still reads ``permissions.py`` → ``MENU_GROUPS`` (role-backed).
This module merges **addon manifest meta** into a plain structure suitable for:

- Admin tools / diagnostics
- Future codegen (generate ``base.html`` from data)
- API ``/api/menu-tree`` experiments

Keeping two sources briefly is intentional during migration from ``blueprints/`` → ``addons/``:
declare **permission paths** once in permissions.py menu_path, mirror labels in addon's
``security/menu_definitions.py`` if you want documentation parity.
"""
from __future__ import annotations
from typing import Any, Dict, List
from addons.core.manifest_loader import iter_installable_addons

def get_addon_menu_summary() -> List[Dict[str, Any]]:
    """
    Flat list describing each addon's declared URL prefix and Flask blueprint id.

    Not used for RBAC enforcement (see permissions.resolve_permission_targets).
    """
    out: List[Dict[str, Any]] = []
    for tech, path, mf in iter_installable_addons():
        urls = mf.get('urls') or {}
        flask_cfg = mf.get('flask') or {}
        row: Dict[str, Any] = {'technical_name': tech, 'path': str(path), 'name': mf.get('name') or tech, 'category': mf.get('category') or '', 'application': mf.get('application', False), 'url_prefix': urls.get('prefix') or '', 'blueprint': flask_cfg.get('blueprint') or '', 'blueprint_ref': flask_cfg.get('blueprint_ref') or ''}
        mp = flask_cfg.get('models_package')
        if mp:
            row['models_package'] = mp
        out.append(row)
    return out
