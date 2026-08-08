"""
PDT (handheld) users and roles — dedicated auth DB tables.

Tables: pdt_roles, pdt_role_permissions, pdt_role_quick_access, pdt_users
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

PDT_ROLE_ID_PREFIX = 'PDT_'


def ensure_pdt_tables() -> None:
    """Create PDT auth tables if missing (auth DB only)."""
    from db import _get_connection_auth

    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'PDT_ROLES'")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    """
                    CREATE TABLE pdt_roles (
                        role_id VARCHAR2(50) PRIMARY KEY,
                        role_name VARCHAR2(100) NOT NULL,
                        description VARCHAR2(500),
                        created_at DATE DEFAULT SYSDATE,
                        updated_at DATE DEFAULT SYSDATE
                    )
                    """
                )
                conn.commit()
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'PDT_ROLE_PERMISSIONS'")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    """
                    CREATE TABLE pdt_role_permissions (
                        role_id VARCHAR2(50),
                        menu_path VARCHAR2(200),
                        permission VARCHAR2(50) DEFAULT 'Y',
                        PRIMARY KEY (role_id, menu_path),
                        FOREIGN KEY (role_id) REFERENCES pdt_roles(role_id) ON DELETE CASCADE
                    )
                    """
                )
                conn.commit()
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'PDT_ROLE_QUICK_ACCESS'")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    """
                    CREATE TABLE pdt_role_quick_access (
                        role_id VARCHAR2(50),
                        menu_path VARCHAR2(200),
                        sort_order NUMBER DEFAULT 0,
                        PRIMARY KEY (role_id, menu_path),
                        FOREIGN KEY (role_id) REFERENCES pdt_roles(role_id) ON DELETE CASCADE
                    )
                    """
                )
                conn.commit()
            cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'PDT_USERS'")
            if cur.fetchone()[0] == 0:
                cur.execute(
                    """
                    CREATE TABLE pdt_users (
                        username VARCHAR2(100) PRIMARY KEY,
                        password_hash VARCHAR2(255) NOT NULL,
                        employeecode VARCHAR2(50) NOT NULL,
                        role_id VARCHAR2(50),
                        tenant_id VARCHAR2(100),
                        active_flag VARCHAR2(1) DEFAULT 'Y',
                        created_at DATE DEFAULT SYSDATE,
                        updated_at DATE DEFAULT SYSDATE,
                        FOREIGN KEY (role_id) REFERENCES pdt_roles(role_id)
                    )
                    """
                )
                conn.commit()


def _rows(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    from db import _safe_rows_auth

    return _safe_rows_auth(query, params or {})


def is_pdt_user_account(username: str) -> bool:
    if not (username or '').strip():
        return False
    ensure_pdt_tables()
    rows = _rows(
        "SELECT 1 FROM pdt_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u)) AND NVL(active_flag, 'Y') = 'Y'",
        {'u': username.strip()},
    )
    return bool(rows)


def pdt_user_exists(username: str) -> bool:
    ensure_pdt_tables()
    rows = _rows(
        'SELECT 1 FROM pdt_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u))',
        {'u': (username or '').strip()},
    )
    return bool(rows)


def pdt_employee_code_exists(employeecode: str) -> bool:
    ensure_pdt_tables()
    rows = _rows(
        'SELECT 1 FROM pdt_users WHERE UPPER(TRIM(employeecode)) = UPPER(TRIM(:ec))',
        {'ec': (employeecode or '').strip()},
    )
    return bool(rows)


def verify_pdt_user(username: str, password: str) -> bool:
    ensure_pdt_tables()
    from db import _get_connection_auth

    query = """
        SELECT password_hash
        FROM pdt_users
        WHERE UPPER(TRIM(username)) = UPPER(TRIM(:username))
          AND NVL(active_flag, 'Y') = 'Y'
    """
    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {'username': username})
            row = cur.fetchone()
            if not row:
                return False
            try:
                return check_password_hash(row[0], password)
            except ValueError:
                return False


def get_pdt_user_employeecode(username: str) -> Optional[str]:
    ensure_pdt_tables()
    rows = _rows(
        'SELECT employeecode FROM pdt_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u))',
        {'u': (username or '').strip()},
    )
    if not rows or not rows[0].get('employeecode'):
        return None
    ec = rows[0]['employeecode']
    return ec.strip() if isinstance(ec, str) else str(ec).strip()


def get_pdt_username_by_employeecode(employeecode: str) -> Optional[str]:
    if not (employeecode or '').strip():
        return None
    ensure_pdt_tables()
    rows = _rows(
        """
        SELECT username FROM pdt_users
        WHERE UPPER(TRIM(employeecode)) = UPPER(TRIM(:ec))
          AND NVL(active_flag, 'Y') = 'Y'
        """,
        {'ec': employeecode.strip()},
    )
    if not rows:
        return None
    return rows[0].get('username')


def get_pdt_user_tenant_id(username: str) -> Optional[str]:
    ensure_pdt_tables()
    rows = _rows(
        'SELECT tenant_id FROM pdt_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u))',
        {'u': (username or '').strip()},
    )
    if not rows:
        return None
    tid = rows[0].get('tenant_id')
    if tid is None:
        return None
    s = (tid.strip() if isinstance(tid, str) else str(tid).strip()) or None
    return s


def get_pdt_user_role_id(username: str) -> Optional[str]:
    ensure_pdt_tables()
    rows = _rows(
        'SELECT role_id FROM pdt_users WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u))',
        {'u': (username or '').strip()},
    )
    if not rows or not rows[0].get('role_id'):
        return None
    rid = rows[0]['role_id']
    return rid.strip() if isinstance(rid, str) else str(rid).strip()


def update_pdt_user_password(username: str, old_password: str, new_password: str) -> bool:
    if not verify_pdt_user(username, old_password):
        return False
    from db import _get_connection_auth

    password_hash = generate_password_hash(new_password)
    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pdt_users
                SET password_hash = :ph, updated_at = SYSDATE
                WHERE UPPER(TRIM(username)) = UPPER(TRIM(:u))
                  AND NVL(active_flag, 'Y') = 'Y'
                """,
                {'ph': password_hash, 'u': username},
            )
            conn.commit()
    return True


# --- Roles ---

def get_all_pdt_roles() -> List[Dict[str, Any]]:
    ensure_pdt_tables()
    return _rows('SELECT role_id, role_name, description FROM pdt_roles ORDER BY role_name', {})


def get_pdt_role_by_id(role_id: str) -> Optional[Dict[str, Any]]:
    ensure_pdt_tables()
    rows = _rows(
        'SELECT role_id, role_name, description FROM pdt_roles WHERE role_id = :id',
        {'id': role_id},
    )
    return rows[0] if rows else None


def pdt_role_exists(role_id: str) -> bool:
    ensure_pdt_tables()
    rows = _rows('SELECT 1 FROM pdt_roles WHERE role_id = :id', {'id': role_id})
    return bool(rows)


def get_pdt_role_permissions(role_id: str) -> List[str]:
    ensure_pdt_tables()
    rows = _rows(
        "SELECT menu_path FROM pdt_role_permissions WHERE role_id = :id AND permission = 'Y'",
        {'id': role_id},
    )
    return [r['menu_path'] for r in rows if r.get('menu_path')]


def get_pdt_role_quick_access(role_id: str) -> List[str]:
    ensure_pdt_tables()
    rows = _rows(
        """
        SELECT menu_path FROM pdt_role_quick_access
        WHERE role_id = :id
        ORDER BY sort_order, menu_path
        """,
        {'id': role_id},
    )
    return [r['menu_path'] for r in rows if r.get('menu_path')]


def _replace_pdt_quick_access(cur, role_id: str, quick_access_paths: Optional[List[str]]) -> None:
    if quick_access_paths is None:
        return
    cur.execute('DELETE FROM pdt_role_quick_access WHERE role_id = :id', {'id': role_id})
    for idx, menu_path in enumerate(quick_access_paths):
        path = (menu_path or '').strip()
        if not path:
            continue
        cur.execute(
            """
            INSERT INTO pdt_role_quick_access (role_id, menu_path, sort_order)
            VALUES (:id, :path, :ord)
            """,
            {'id': role_id, 'path': path, 'ord': idx},
        )


def get_next_pdt_role_id() -> str:
    ensure_pdt_tables()
    max_n = 0
    pattern = re.compile(r'(\d+)$')
    for row in get_all_pdt_roles():
        rid = str(row.get('role_id') or '').strip().upper()
        if not rid.startswith(PDT_ROLE_ID_PREFIX):
            continue
        suffix = rid[len(PDT_ROLE_ID_PREFIX):]
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return f'{PDT_ROLE_ID_PREFIX}{max_n + 1:03d}'


def create_pdt_role(
    role_id: str,
    role_name: str,
    description: str = '',
    menu_permissions: Optional[List[str]] = None,
    quick_access_paths: Optional[List[str]] = None,
) -> None:
    if not role_id or not role_name:
        raise ValueError('Role ID and Role Name are required.')
    ensure_pdt_tables()
    from db import _get_connection_auth

    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM pdt_roles WHERE role_id = :id', {'id': role_id})
            if cur.fetchone():
                raise ValueError('PDT role ID already exists.')
            cur.execute(
                'INSERT INTO pdt_roles (role_id, role_name, description) VALUES (:id, :name, :role_desc)',
                {'id': role_id, 'name': role_name, 'role_desc': description or ''},
            )
            if menu_permissions:
                for menu_path in menu_permissions:
                    cur.execute(
                        """
                        INSERT INTO pdt_role_permissions (role_id, menu_path, permission)
                        VALUES (:id, :path, 'Y')
                        """,
                        {'id': role_id, 'path': menu_path},
                    )
            _replace_pdt_quick_access(cur, role_id, quick_access_paths)
            conn.commit()


def update_pdt_role(
    role_id: str,
    role_name: Optional[str] = None,
    description: Optional[str] = None,
    menu_permissions: Optional[List[str]] = None,
    quick_access_paths: Optional[List[str]] = None,
) -> None:
    ensure_pdt_tables()
    from db import _get_connection_auth

    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            updates = []
            params: Dict[str, Any] = {'id': role_id}
            if role_name is not None:
                updates.append('role_name = :name')
                params['name'] = role_name
            if description is not None:
                updates.append('description = :role_desc')
                params['role_desc'] = description
            if updates:
                updates.append('updated_at = SYSDATE')
                cur.execute(f"UPDATE pdt_roles SET {', '.join(updates)} WHERE role_id = :id", params)
            if menu_permissions is not None:
                cur.execute('DELETE FROM pdt_role_permissions WHERE role_id = :id', {'id': role_id})
                for menu_path in menu_permissions:
                    cur.execute(
                        """
                        INSERT INTO pdt_role_permissions (role_id, menu_path, permission)
                        VALUES (:id, :path, 'Y')
                        """,
                        {'id': role_id, 'path': menu_path},
                    )
            _replace_pdt_quick_access(cur, role_id, quick_access_paths)
            conn.commit()


def delete_pdt_role(role_id: str) -> None:
    ensure_pdt_tables()
    from db import _get_connection_auth

    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM pdt_roles WHERE role_id = :id', {'id': role_id})
            conn.commit()


def get_pdt_users_with_roles() -> List[Dict[str, Any]]:
    """List PDT users with role name and tenant location (auth DB)."""
    from db import ensure_tenant_databases_table

    ensure_pdt_tables()
    ensure_tenant_databases_table()
    return _rows(
        """
        SELECT
            u.username,
            u.employeecode,
            TRIM(TO_CHAR(td.locationcode)) AS location,
            u.tenant_id,
            u.role_id,
            r.role_name,
            u.active_flag
        FROM pdt_users u
        LEFT JOIN pdt_roles r ON u.role_id = r.role_id
        LEFT JOIN tenant_databases td
          ON UPPER(TRIM(u.tenant_id)) = UPPER(TRIM(td.tenant_id))
        ORDER BY u.username
        """,
        {},
    )


def create_pdt_user(
    username: str,
    password: str,
    employeecode: str,
    role_id: str,
    tenant_id: Optional[str] = None,
) -> None:
    if not username or not password:
        raise ValueError('Username and password are required.')
    if not employeecode:
        raise ValueError('Employee Code is required.')
    if not employeecode.isdigit():
        raise ValueError('Employee Code must be numeric.')
    if not role_id or not pdt_role_exists(role_id):
        raise ValueError('Select a valid PDT role.')
    ensure_pdt_tables()
    from db import user_exists

    if pdt_user_exists(username) or user_exists(username):
        raise ValueError('Username already exists.')
    if pdt_employee_code_exists(employeecode):
        raise ValueError('Employee Code already exists on a PDT user.')
    from db import employee_code_exists

    if employee_code_exists(employeecode):
        raise ValueError('Employee Code already exists on an ERP user.')

    password_hash = generate_password_hash(password)
    tenant_val = (tenant_id or '').strip() or None
    from db import _get_connection_auth

    with _get_connection_auth() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pdt_users (
                    username, password_hash, employeecode, role_id, tenant_id, active_flag
                ) VALUES (:u, :p, :e, :r, :t, 'Y')
                """,
                {'u': username.strip(), 'p': password_hash, 'e': employeecode, 'r': role_id, 't': tenant_val},
            )
            conn.commit()


def ensure_default_pdt_operator_role() -> None:
    """Seed PDT_OPERATOR in pdt_roles if missing."""
    rid = 'PDT_OPERATOR'
    if pdt_role_exists(rid):
        return
    perms = [
        'warehouse.warehouse_stock_counting',
        'auth.change_password',
    ]
    try:
        create_pdt_role(
            rid,
            'PDT Operator',
            'Default handheld stock counting access',
            perms,
            ['warehouse.warehouse_stock_counting'],
        )
    except ValueError:
        pass
