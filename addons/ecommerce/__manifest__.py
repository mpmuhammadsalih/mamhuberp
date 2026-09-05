"""Addon manifest — MamaHub Ecommerce (ERP admin)."""
MANIFEST = {
    'technical_name': 'ecommerce',
    'name': 'Ecommerce',
    'version': '1.0.0',
    'category': 'Sales',
    'summary': 'Online store admin: dashboard, orders, catalog, promotions, media.',
    'depends': ['itemmaster'],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/ecommerce'},
    'flask': {
        'blueprint': 'ecommerce',
        'blueprint_ref': 'addons.ecommerce:bp',
        'models_package': 'addons.ecommerce.models',
        'routes_module': 'addons.ecommerce.controllers.routes',
    },
}
