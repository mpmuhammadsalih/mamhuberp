"""
Copy **all table/column definitions** from an RFIM Oracle schema into a generated Python model file.

This is a thin wrapper around ``oracle_introspect_models.py --profile rfim``. By default it writes:

* ``addons/core/schema/generated/oracle_rfim_tables/`` — one ``*.py`` per Oracle table (``*Cols`` classes).
* ``addons/core/schema/generated/oracle_schema_rfim.py`` — imports the package, re-exports column classes,
  and (unless ``--no-constraints``) holds ``PRIMARY_KEY_BY_TABLE``, ``FOREIGN_KEYS``, ``INDEXES``, etc.

Pass ``--no-split-tables`` through to the introspect script for a **single** large file instead of the
package. It does **not** connect the app to RFIM at runtime; it only snapshots metadata for use with
``from addons.core.schema.from_db import load_generated_schema``.

Prerequisites: ``oracledb`` (``pip install oracledb``), and network access to the DB.
For Autonomous DB, set ``ORACLE_WALLET_DIR`` and use a TNS alias as ``DB_DSN`` / ``RFIM_DSN``.

Examples::

    # Uses RFIM_USERNAME, RFIM_PASSWORD, RFIM_DSN from ``.env``
    python scripts/export_rfim_schema_to_models.py

    # Same as: rfim/rfim@192.168.1.225:1521/rgc
    python scripts/export_rfim_schema_to_models.py --user rfim --password rfim --dsn 192.168.1.225:1521/rgc

After a successful run, set in ``.env`` (so the app loads this module)::

    ORACLE_SCHEMA_MODULE=oracle_schema_rfim

Dry-run (list tables, no file write)::

    python scripts/export_rfim_schema_to_models.py --dry-run
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
INTROSPECT = ROOT / 'scripts' / 'oracle_introspect_models.py'

def main() -> int:
    cmd = [sys.executable, str(INTROSPECT), '--profile', 'rfim']
    cmd.extend(sys.argv[1:])
    return int(subprocess.call(cmd))
if __name__ == '__main__':
    raise SystemExit(main())
