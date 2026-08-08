"""Addon manifest — ERP transaction screen recording & field-change audit."""
MANIFEST = {
    'technical_name': 'transaction_recording_audit',
    'name': 'Transaction Recording Audit',
    'version': '1.0.0',
    'category': 'Reports',
    'summary': 'Screen capture, video, and field-change audit for ERP transactions',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/audit/recording'},
    'flask': {
        'blueprint': 'transaction_recording_audit',
        'blueprint_ref': 'addons.transaction_recording_audit.controllers.routes:bp',
        'routes_module': 'addons.transaction_recording_audit.controllers.routes',
    },
}
