"""Addon manifest — Document numbering setup (tenant DB)."""
MANIFEST = {
    'technical_name': 'document_numbering',
    'name': 'Document Numbering',
    'version': '1.0.0',
    'category': 'Setup',
    'summary': 'Configure number series for sales, purchase, inventory, and accounts documents',
    'depends': [],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
    'urls': {'prefix': '/setup/document-numbering'},
    'flask': {
        'blueprint': 'document_numbering',
        'blueprint_ref': 'addons.document_numbering.controllers.routes:bp',
        'routes_module': 'addons.document_numbering.controllers.routes',
    },
}
