"""Sales AI — premium ERP sales intelligence dashboard."""
MANIFEST = {
    'technical_name': 'sales_ai',
    'name': 'Sales AI Dashboard',
    'version': '1.0.0',
    'category': 'Sales',
    'summary': 'Power BI–style sales KPIs, forecasting, comparisons, and AI insights.',
    'depends': ['ai_forecast'],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/sales-ai'},
    'flask': {
        'blueprint': 'sales_ai',
        'blueprint_ref': 'addons.sales_ai:bp',
        'routes_module': 'addons.sales_ai.controllers.routes',
    },
}
