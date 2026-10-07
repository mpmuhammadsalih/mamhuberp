"""Public app configuration — auth catalog + tenant ERP connections."""

from __future__ import annotations

from typing import Any

from db.oracle_driver import oracle_connect

from mobile_backend.config import Config
from mobile_backend.database.oracle_pool import get_auth_connection, invalidate_tenant_pool
from mobile_backend.database.transaction import oracle_transaction
from mobile_backend.operation_lock import mobile_operation_lock
from mobile_backend.services.auth_service import PRIVILEGED_USERS


def _mask_dsn(dsn: str) -> str:
    s = (dsn or "").strip()
    if not s:
        return ""
    if "@" in s:
        return s.split("@", 1)[-1]
    return s


def list_active_tenants() -> list[dict[str, Any]]:
    conn = get_auth_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tenant_id, display_name, ip, port, service_name, username, active_flag
              FROM tenant_databases
             WHERE NVL(active_flag, 'Y') = 'Y'
             ORDER BY tenant_id
            """
        )
        rows = []
        for row in cur.fetchall() or []:
            host = str(row[2] or "").strip()
            port = int(row[3] or 1521)
            svc = str(row[4] or "").strip()
            erp_dsn = f"{host}:{port}/{svc}" if host and svc else ""
            rows.append(
                {
                    "tenant_id": str(row[0] or "").strip(),
                    "display_name": str(row[1] or row[0] or "").strip(),
                    "erp_dsn": erp_dsn,
                    "erp_username": str(row[5] or "").strip(),
                    "ip": host,
                    "port": port,
                    "service_name": svc,
                    "active": str(row[6] or "Y").strip().upper() != "N",
                }
            )
        return rows


def tenant_exists(tenant_id: str) -> bool:
    tid = (tenant_id or "").strip()
    if not tid:
        return False
    return any(t["tenant_id"].lower() == tid.lower() for t in list_active_tenants())


def get_app_config() -> dict[str, Any]:
    """Catalog DB status and tenant list (no passwords)."""
    auth_connected = False
    auth_error: str | None = None
    tenants: list[dict[str, Any]] = []

    try:
        tenants = list_active_tenants()
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM DUAL")
            auth_connected = True
    except Exception as exc:
        auth_error = str(exc)[:300]

    return {
        "auth_catalog": {
            "connected": auth_connected,
            "username": (Config.ORACLE_USER or "").strip(),
            "dsn": _mask_dsn(Config.ORACLE_DSN or ""),
            "error": auth_error,
        },
        "tenants": tenants,
    }


def _tenant_dsn(host: str, port: int, service_name: str) -> str:
    return f"{host.strip()}:{int(port)}/{service_name.strip()}"


def test_oracle_connection(
    *,
    host: str,
    port: int,
    service_name: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    host_s = (host or "").strip()
    svc = (service_name or "").strip()
    user = (username or "").strip()
    if not host_s or not svc or not user:
        raise ValueError("Host, service name, and username are required.")
    dsn = _tenant_dsn(host_s, port or 1521, svc)
    conn = oracle_connect(user=user, password=password or "", dsn=dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM DUAL")
            cur.fetchone()
    finally:
        conn.close()
    return {"connected": True, "dsn": dsn, "username": user}


def upsert_tenant_database(
    *,
    tenant_id: str,
    display_name: str | None,
    host: str,
    port: int,
    service_name: str,
    username: str,
    password: str | None,
    active: bool = True,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id is required.")
    host_s = (host or "").strip()
    svc = (service_name or "").strip()
    user = (username or "").strip()
    if not host_s or not svc or not user:
        raise ValueError("Host, service name, and username are required.")

    pwd = password if password is not None and str(password).strip() != "" else None
    flag = "Y" if active else "N"
    name = (display_name or tid).strip()

    with mobile_operation_lock(
        "tenant_upsert",
        tid.lower(),
        busy_message="Tenant configuration is already being saved. Please wait.",
    ):
        conn = get_auth_connection()
        with oracle_transaction(conn), conn.cursor() as cur:
            cur.execute(
                "SELECT password FROM tenant_databases WHERE tenant_id = :tid",
                {"tid": tid},
            )
            existing = cur.fetchone()
            if existing and pwd is None:
                pwd = str(existing[0] or "")

            if pwd is None:
                raise ValueError("Password is required for a new tenant.")

            cur.execute(
                """
                MERGE INTO tenant_databases t
                USING (SELECT :tid AS tenant_id FROM dual) s
                ON (t.tenant_id = s.tenant_id)
                WHEN MATCHED THEN
                  UPDATE SET display_name = :display_name,
                             ip = :ip,
                             port = :port,
                             service_name = :service_name,
                             username = :username,
                             password = :password,
                             active_flag = :active_flag
                WHEN NOT MATCHED THEN
                  INSERT (
                      tenant_id, display_name, active_flag,
                      ip, port, service_name, username, password
                  ) VALUES (
                      :tid, :display_name, :active_flag,
                      :ip, :port, :service_name, :username, :password
                  )
                """,
                {
                    "tid": tid,
                    "display_name": name,
                    "active_flag": flag,
                    "ip": host_s,
                    "port": int(port or 1521),
                    "service_name": svc,
                    "username": user,
                    "password": pwd,
                },
            )

    invalidate_tenant_pool(tid)
    erp_dsn = _tenant_dsn(host_s, port or 1521, svc)
    return {
        "tenant_id": tid,
        "display_name": name,
        "erp_dsn": erp_dsn,
        "erp_username": user,
        "ip": host_s,
        "port": int(port or 1521),
        "service_name": svc,
        "active": active,
    }


def resolve_login_tenant(user: dict[str, Any], requested_tenant_id: str | None) -> str | None:
    """Pick JWT tenant_id: user row default, or app-selected tenant when allowed."""
    base = user.get("tenant_id")
    base_s = str(base).strip() if base is not None else ""
    req = (requested_tenant_id or "").strip()
    if not req:
        return base_s or None
    if not tenant_exists(req):
        raise ValueError(f"Unknown tenant '{req}'. Refresh configuration and try again.")
    username = str(user.get("username") or "").strip().lower()
    if username in PRIVILEGED_USERS:
        return req
    if base_s and base_s.lower() == req.lower():
        return req
    if not base_s:
        return req
    raise ValueError(
        f"Tenant '{req}' is not assigned to this user. "
        "Use your assigned tenant or ask an administrator."
    )
