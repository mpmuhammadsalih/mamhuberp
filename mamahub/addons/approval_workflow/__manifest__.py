"""Addon manifest — Approval workflow setup (tenant DB)."""
MANIFEST = {
    'technical_name': 'approval_workflow',
    'name': 'Approval Workflow',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'Configure multi-level approval rules by transaction type and amount',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/setup/approval-workflow'},
    'flask': {
        'blueprint': 'approval_workflow',
        'blueprint_ref': 'addons.approval_workflow.controllers.routes:bp',
        'routes_module': 'addons.approval_workflow.controllers.routes',
    },
}
