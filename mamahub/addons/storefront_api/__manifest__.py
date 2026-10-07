"""Addon manifest — MamaHub storefront API (/api/v1/* for customer app)."""
MANIFEST = {
    'technical_name': 'storefront_api',
    'name': 'Storefront API',
    'version': '1.0.0',
    'category': 'Integration',
    'summary': 'MamaHub customer-facing REST API — code in storefront_backend/',
    'depends': ['ecommerce'],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'flask': {
        'blueprint': 'storefront_api',
        'blueprint_ref': 'storefront_backend:bp',
    },
}
