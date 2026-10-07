"""Audit user role display and orphan role_permissions."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass
from permissions import get_menu_groups
from db import get_users_with_roles, get_all_roles, get_role_permissions, _safe_rows_auth

visible = set()
for g in get_menu_groups():
    for it in g.get("items") or []:
        mp = (it.get("menu_path") or "").strip()
        if mp:
            visible.add(mp)

print("=== Users (all) ===")
for u in get_users_with_roles():
    rid = u.get("role_id")
    rn = u.get("role_name")
    disp = rn or rid or "Full access"
    print(f"  {u.get('username')}: role_id={rid!r} role_name={rn!r} -> {disp!r}")

print("\n=== Roles with orphan permissions (in DB but not in role editor) ===")
for r in get_all_roles():
    rid = r["role_id"]
    perms = set(get_role_permissions(rid))
    orphans = sorted(perms - visible)
    if orphans:
        extra = " ..." if len(orphans) > 8 else ""
        print(f"  {rid}: {orphans[:8]}{extra}")

rows = _safe_rows_auth(
    """
    SELECT u.username, u.role_id
    FROM login_users u
    LEFT JOIN roles r ON UPPER(TRIM(u.role_id)) = UPPER(TRIM(r.role_id))
    WHERE u.role_id IS NOT NULL AND r.role_id IS NULL
    """,
    {},
)
print("\n=== Users with role_id not matching any role ===")
for row in rows:
    print(f"  {row}")
