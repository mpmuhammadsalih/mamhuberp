"""Addon manifest — database backup utility."""
MANIFEST = {
    'technical_name': 'utilities_backup',
    'name': 'Database backup',
    'version': '1.0.0',
    'category': 'Technical',
    'summary': 'Export Oracle schema DDL and manage backup files from Utilities',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/utilities/backup'},
    'flask': {
        'blueprint': 'utilities_backup',
        'blueprint_ref': 'addons.utilities_backup.controllers.routes:bp',
        'routes_module': 'addons.utilities_backup.controllers.routes',
    },
}
