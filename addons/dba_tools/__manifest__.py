"""Addon manifest — DBA tools (table list, lock status, unlock)."""
MANIFEST = {
    'technical_name': 'dba_tools',
    'name': 'DBA Tools',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'List database tables, show lock status, and release table locks.',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/setup/dba'},
    'flask': {
        'blueprint': 'dba_tools',
        'blueprint_ref': 'addons.dba_tools:bp',
        'routes_module': 'addons.dba_tools.controllers.routes',
    },
}
