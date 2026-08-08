"""Addon manifest — Fixed Assets (tenant DB)."""
MANIFEST = {
    'technical_name': 'fixed_assets',
    'name': 'Fixed Assets',
    'version': '1.0.0',
    'category': 'Finance / Accounts',
    'summary': 'Asset categories, register, acquisition, depreciation, disposal, and transfer',
    'depends': ['accounts'],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/accounts/fixed-assets'},
    'flask': {
        'blueprint': 'fixed_assets',
        'blueprint_ref': 'addons.fixed_assets.controllers.routes:bp',
        'routes_module': 'addons.fixed_assets.controllers.routes',
    },
}
