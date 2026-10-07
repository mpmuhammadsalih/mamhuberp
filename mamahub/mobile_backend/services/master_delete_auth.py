"""Password gate for master deletes (Item / Customer / Supplier)."""

from __future__ import annotations

# Same fixed password as ERP HO Itemmaster Central delete.
_MASTER_DELETE_PASSWORD = "123"


def require_master_delete_password(password: str, *, username: str) -> None:
    """
    Require a delete password.

    Accepts:
    - Fixed master password ``123`` (ERP HO item delete parity), or
    - The signed-in user's login password.
    """
    pwd = str(password or "").strip()
    if not pwd:
        raise ValueError("Delete password is required.")
    if pwd == _MASTER_DELETE_PASSWORD:
        return
    uname = str(username or "").strip()
    if not uname:
        raise ValueError("Invalid delete password.")
    try:
        from mobile_backend.services.auth_service import authenticate_user

        user = authenticate_user(uname, pwd)
    except Exception:
        user = None
    if not user:
        raise ValueError("Invalid delete password.")
