"""
Addon manifest (same idea as Odoo __manifest__.py).

Kept as importable MANIFEST dict for tooling (docs, codegen, CI checks).
Production menu entries still map via permissions.MENU_GROUPS and base.html sidebar.
"""
MANIFEST = {'technical_name': 'demo_sales', 'name': 'Demo Sales (architecture sample)', 'version': '1.0.0', 'category': 'Sales', 'summary': 'Example module: one main menu, multiple pages, layered code.', 'depends': [], 'application': True, 'installable': True, 'license': 'LGPL-3', 'urls': {'prefix': '/demo-sales'}, 'flask': {'blueprint': 'demo_sales', 'blueprint_ref': 'addons.demo_sales:bp', 'models_package': 'addons.demo_sales.models', 'routes_module': 'addons.demo_sales.controllers.routes'}}
