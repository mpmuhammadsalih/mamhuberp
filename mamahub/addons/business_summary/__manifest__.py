"""Daily Business Summary — executive ERP dashboard."""
MANIFEST = {
    'technical_name': 'business_summary',
    'name': 'Daily Business Summary',
    'version': '1.0.0',
    'category': 'Reports',
    'summary': 'Single-page executive dashboard: sales, purchases, inventory, profitability, and cash flow.',
    'depends': [],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/business-summary'},
    'flask': {
        'blueprint': 'business_summary',
        'blueprint_ref': 'addons.business_summary:bp',
        'routes_module': 'addons.business_summary.controllers.routes',
    },
}
