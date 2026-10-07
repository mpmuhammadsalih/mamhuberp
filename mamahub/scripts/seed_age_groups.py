"""Create MH_AGE_GROUP and seed default age bands for Shop by age."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / '.env')

from db import _get_connection, _table_exists  # noqa: E402
from storefront_backend.services.schema_bootstrap import ensure_age_group_schema  # noqa: E402

if __name__ == '__main__':
    print('before exists', _table_exists('MH_AGE_GROUP'))
    ensure_age_group_schema()
    print('after exists', _table_exists('MH_AGE_GROUP'))

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT AGE_GROUP_NAME, SLUG, SORT_ORDER
                FROM MH_AGE_GROUP
                WHERE IS_ACTIVE = 1
                ORDER BY SORT_ORDER
                """
            )
            for row in cur.fetchall():
                print(row)
