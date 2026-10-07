"""AI Forecasting addon manifest."""
MANIFEST = {
    'technical_name': 'ai_forecast',
    'name': 'AI Forecasting',
    'version': '1.0.0',
    'category': 'Analytics',
    'summary': 'Sales & purchase forecasting, reorder, product/supplier/customer analytics.',
    'depends': [],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/ai'},
    'flask': {
        'blueprint': 'ai_forecast',
        'blueprint_ref': 'addons.ai_forecast:bp',
        'models_package': 'addons.ai_forecast.models',
        'routes_module': 'addons.ai_forecast.controllers.routes',
    },
}
