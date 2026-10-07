# DO NOT RUN

This folder is retained only as a historical reference.

**Policy:** Never drop or delete existing Oracle objects in the shared `mamahub` / Dynamics database.

Use `scripts/apply_schema.py` which:
- creates only missing objects
- skips existing objects
- blocks `DROP` / `TRUNCATE` / `DELETE` statements
