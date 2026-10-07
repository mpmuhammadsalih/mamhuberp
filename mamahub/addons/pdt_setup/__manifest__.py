"""Addon manifest — PDT (handheld) roles and users."""
MANIFEST = {
    'technical_name': 'pdt_setup',
    'name': 'PDT Setup',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'PDT roles and handheld user creation',
    'depends': [],
    'application': False,
    'installable': False,
    'license': 'LGPL-3',
    'urls': {'prefix': '/pdt'},
    'flask': {
        'blueprint': 'pdt',
        'blueprint_ref': 'addons.pdt_setup:bp',
        'routes_module': 'addons.pdt_setup.controllers.routes',
    },
}
