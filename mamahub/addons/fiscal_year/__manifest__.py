"""Addon manifest — Fiscal year setup (tenant DB)."""
MANIFEST = {
    'technical_name': 'fiscal_year',
    'name': 'Fiscal Year Setup',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'Define accounting fiscal periods, current year, and closed flags',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/setup/fiscal-year'},
    'flask': {
        'blueprint': 'fiscal_year',
        'blueprint_ref': 'addons.fiscal_year.controllers.routes:bp',
        'routes_module': 'addons.fiscal_year.controllers.routes',
    },
}
