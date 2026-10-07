"""Addon manifest — branch transaction date setup (TBLTRANSACTIONDATE)."""
MANIFEST = {
    'technical_name': 'transaction_date_setup',
    'name': 'Transaction Date Setup',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'Open business dates per transaction type (sales, purchase, GRN, transfer, etc.).',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/setup/transaction-date'},
    'flask': {
        'blueprint': 'transaction_date_setup',
        'blueprint_ref': 'addons.transaction_date_setup:bp',
        'routes_module': 'addons.transaction_date_setup.controllers.routes',
    },
}
