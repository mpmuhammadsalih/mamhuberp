#!/usr/bin/env python3
"""
Apply MamaHub Oracle SQL scripts using oracledb.

Policy:
- NEVER drop or delete existing database objects
- Create only objects that do not already exist
- Skip statements that conflict with existing objects
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import oracledb

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

from oracle_env import load_oracle_settings  # noqa: E402

SQL_ROOT = REPO_ROOT / 'sql'

INSTALL_SCRIPTS = [
    '01_sequences/01_create_sequences.sql',
    '01_sequences/02_mh_extension_sequences.sql',
    '01_sequences/03_mh_auth_sequences.sql',
    '01_sequences/04_mh_cart_sequences.sql',
    '01_sequences/05_mh_order_sequences.sql',
    '01_sequences/06_mh_content_sequences.sql',
    '01_sequences/07_mh_loyalty_sequences.sql',
    '02_tables/01_company_branch_warehouse.sql',
    '02_tables/02_user_role_permission.sql',
    '02_tables/06_mh_ecommerce_extensions.sql',
    '02_tables/07_mh_auth_support.sql',
    '02_tables/08_mh_cart_wishlist.sql',
    '02_tables/09_mh_customer_address.sql',
    '02_tables/10_mh_orders.sql',
    '02_tables/11_mh_delivery_pickup.sql',
    '02_tables/12_mh_inventory_reservation.sql',
    '02_tables/13_mh_promotions.sql',
    '02_tables/14_mh_reviews_cms_notifications.sql',
    '02_tables/15_mh_loyalty.sql',
    '02_tables/16_mh_media.sql',
    '05_seed/01_master_data.sql',
    '05_seed/02_sample_products.sql',
    '05_seed/03_order_delivery_promotions.sql',
    '05_seed/04_admin_rbac_seed.sql',
    '05_seed/05_currency_qar.sql',
    '05_seed/06_cms_pages.sql',
    '05_seed/07_loyalty_seed.sql',
]

IGNORABLE_ORACLE_ERRORS = {
    955,
    2260,
    2261,
    2264,
    2275,
    1408,
    1,
    54,
}


def _strip_line_comments(sql: str) -> str:
    lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith('PROMPT ') or stripped.startswith('WHENEVER '):
            continue
        if stripped.startswith('--'):
            continue
        if '--' in line and "'" not in line.split('--', 1)[0]:
            line = line.split('--', 1)[0]
        lines.append(line)
    return '\n'.join(lines)


def split_sql_statements(sql: str) -> list[str]:
    cleaned = _strip_line_comments(sql)
    statements: list[str] = []
    buffer: list[str] = []
    in_plsql = False

    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        upper = line.strip().upper()

        if not in_plsql and (upper.startswith('BEGIN') or upper.startswith('DECLARE')):
            in_plsql = True

        if in_plsql:
            if line.strip() == '/':
                block = '\n'.join(buffer).strip()
                if block:
                    statements.append(block)
                buffer = []
                in_plsql = False
            else:
                buffer.append(line)
            continue

        buffer.append(line)
        if line.rstrip().endswith(';'):
            stmt = '\n'.join(buffer).strip()
            stmt = stmt[:-1].strip()
            if stmt:
                statements.append(stmt)
            buffer = []

    trailing = '\n'.join(buffer).strip()
    if trailing:
        if trailing.endswith(';'):
            trailing = trailing[:-1].strip()
        if trailing:
            statements.append(trailing)

    filtered: list[str] = []
    for stmt in statements:
        normalized = re.sub(r'\s+', ' ', stmt).strip()
        if not normalized or normalized.upper() in {'EXIT', 'COMMIT'}:
            if normalized.upper() == 'COMMIT':
                filtered.append('COMMIT')
            continue
        if re.match(
            r'^\s*(DROP|TRUNCATE|DELETE\s+FROM)\b',
            normalized,
            flags=re.IGNORECASE,
        ):
            print(f'   blocked destructive statement: {normalized[:80]}...')
            continue
        filtered.append(stmt)
    return filtered


def _oracle_error_code(exc: BaseException) -> int | None:
    match = re.search(r'ORA-(\d+)', str(exc))
    return int(match.group(1)) if match else None


def execute_script(connection: oracledb.Connection, script_path: Path) -> None:
    print(f'-> {script_path.relative_to(SQL_ROOT)}')
    sql_text = script_path.read_text(encoding='utf-8')
    statements = split_sql_statements(sql_text)
    cursor = connection.cursor()
    try:
        for stmt in statements:
            if stmt.upper() == 'COMMIT':
                connection.commit()
                continue
            try:
                cursor.execute(stmt)
            except oracledb.DatabaseError as exc:
                code = _oracle_error_code(exc)
                if code in IGNORABLE_ORACLE_ERRORS:
                    preview = re.sub(r'\s+', ' ', stmt)[:90]
                    print(f'   skip existing ORA-{code:05d}: {preview}...')
                    continue
                raise
        connection.commit()
    finally:
        cursor.close()


def run_scripts(scripts: list[str]) -> None:
    settings = load_oracle_settings()
    print(
        f'Connecting to {settings.host}:{settings.port}/'
        f'{settings.service_name} as {settings.username}'
    )
    print('Mode: create-if-missing only (no drop/delete)')
    connection = oracledb.connect(
        user=settings.username,
        password=settings.password,
        dsn=settings.dsn,
    )
    try:
        for relative in scripts:
            path = SQL_ROOT / relative
            if not path.exists():
                raise FileNotFoundError(f'Missing SQL script: {path}')
            execute_script(connection, path)
        print('Done.')
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Apply MamaHub Oracle schema (create-if-missing only)'
    )
    parser.add_argument(
        '--seed-only',
        action='store_true',
        help='Run only seed scripts (inserts skipped if unique keys exist)',
    )
    args = parser.parse_args()

    if args.seed_only:
        run_scripts(
            [
                '05_seed/01_master_data.sql',
                '05_seed/02_sample_products.sql',
                '05_seed/03_order_delivery_promotions.sql',
                '05_seed/04_admin_rbac_seed.sql',
                '05_seed/05_currency_qar.sql',
            ]
        )
    else:
        run_scripts(INSTALL_SCRIPTS)


if __name__ == '__main__':
    main()
