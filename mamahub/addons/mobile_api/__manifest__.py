"""Addon manifest — Nexa Mobile JWT API (/api/v1/*)."""
MANIFEST = {
    "technical_name": "mobile_api",
    "name": "Mobile API",
    "version": "1.0.0",
    "category": "Integration",
    "summary": "JWT REST API for Nexa Mobile — code in mobile_backend/",
    "depends": [],
    "application": False,
    "installable": True,
    "license": "LGPL-3",
    "flask": {
        "blueprint": "mobile_api",
        "blueprint_ref": "mobile_backend:bp",
    },
}
