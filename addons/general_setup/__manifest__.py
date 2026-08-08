"""Addon manifest — organization-wide general setup options."""
MANIFEST = {
    'technical_name': 'general_setup',
    'name': 'General Setup',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'Organization-wide toggles such as customer request alert polling.',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/setup/general-setup'},
    'flask': {
        'blueprint': 'general_setup',
        'blueprint_ref': 'addons.general_setup:bp',
        'routes_module': 'addons.general_setup.controllers.routes',
    },
}
