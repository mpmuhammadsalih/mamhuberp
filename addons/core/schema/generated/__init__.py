"""Generated Oracle modules live here.

Run from project root (copies RFIM user's table/column metadata into Python)::

    python scripts/export_rfim_schema_to_models.py

Same as ``python scripts/oracle_introspect_models.py --profile rfim``. Creates ``oracle_schema_rfim.py`` plus per-table modules under ``oracle_rfim_tables/`` (unless export
is run with ``--no-split-tables``).
Apps load via :mod:`addons.core.schema.from_db`; set ``ORACLE_SCHEMA_MODULE`` (e.g.
``oracle_schema_rfim``).
"""
__all__: list[str] = []
