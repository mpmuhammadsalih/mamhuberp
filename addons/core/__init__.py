"""
Shared utilities for Odoo-style addons (manifest loading, optional menu merging).

Imported by addons.register — keep this package free of Flask route code.
"""
from addons.core.manifest_loader import discover_addon_dirs, iter_installable_addons, load_manifest_dict
from addons.core.menu_registry import get_addon_menu_summary
__all__ = ['discover_addon_dirs', 'iter_installable_addons', 'load_manifest_dict', 'get_addon_menu_summary']
