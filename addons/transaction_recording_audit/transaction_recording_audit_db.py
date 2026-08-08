"""Transaction screen-recording audit — tenant DB tables and helpers."""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _get_connection,
    _safe_rows,
    _table_exists,
    create_role,
    get_role_by_id,
    get_role_permissions,
    get_user_role_id,
    role_exists,
    update_role,
)

HDR_TABLE = 'TRANSACTION_AUDIT_HDR'
DTL_TABLE = 'TRANSACTION_AUDIT_DTL'
HDR_SEQ = 'TRANSACTION_AUDIT_HDR_SEQ'
DTL_SEQ = 'TRANSACTION_AUDIT_DTL_SEQ'

TRANSACTION_TYPE_FOLDERS: Dict[str, str] = {
    'Purchase': 'Purchase',
    'Sales': 'Sales',
    'StockAdjustment': 'StockAdjustment',
    'Receipt': 'Receipt',
    'Payment': 'Payment',
}

TRANSACTION_TYPE_LABELS: Dict[str, str] = {
    'Purchase': 'Purchase Invoice',
    'GRN': 'Goods Receipt (GRN)',
    'PO': 'Purchase Order',
    'PurchaseReturn': 'Purchase Return',
    'Sales': 'Sales Invoice',
    'SalesReturn': 'Sales Return',
    'StockAdjustment': 'Stock Adjustment',
    'StockTransfer': 'Stock Transfer',
    'Repacking': 'Repacking',
    'Receipt': 'Receipt',
    'Payment': 'Payment',
    'JournalEntry': 'Journal Entry',
}

_STATUS_OPEN = 'OPEN'
_STATUS_SAVED = 'SAVED'
_STATUS_FAILED = 'FAILED'


def _folder_for_tx_type(tx_type: str) -> str:
    """Map logical transaction type to AuditFiles folder."""
    folder_aliases = {
        'GRN': 'Purchase',
        'PO': 'Purchase',
        'PurchaseReturn': 'Purchase',
        'SalesReturn': 'Sales',
        'StockTransfer': 'StockAdjustment',
        'Repacking': 'StockAdjustment',
        'JournalEntry': 'Payment',
    }
    return folder_aliases.get(tx_type, tx_type if tx_type in TRANSACTION_TYPE_FOLDERS else 'Purchase')


def _safe_tx_type(raw: str) -> str:
    key = (raw or '').strip()
    if key in TRANSACTION_TYPE_FOLDERS or key in TRANSACTION_TYPE_LABELS:
        return key
    upper = key.upper()
    aliases = {
        'PO': 'PO',
        'PURCHASE ORDER': 'PO',
        'LPO': 'PO',
        'PURCHASE': 'Purchase',
        'PI': 'Purchase',
        'GRN': 'GRN',
        'GOODS RECEIPT': 'GRN',
        'PURCHASERETURN': 'PurchaseReturn',
        'PURCHASE RETURN': 'PurchaseReturn',
        'PURCHASE_RETURN': 'PurchaseReturn',
        'SI': 'Sales',
        'SALES': 'Sales',
        'SO': 'Sales',
        'SALESRETURN': 'SalesReturn',
        'SALES RETURN': 'SalesReturn',
        'SALES_RETURN': 'SalesReturn',
        'STK_TRF': 'StockTransfer',
        'STOCKTRANSFER': 'StockTransfer',
        'STOCK TRANSFER': 'StockTransfer',
        'REPACKING': 'Repacking',
        'REPACK': 'Repacking',
        'JOURNAL': 'JournalEntry',
        'JOURNALENTRY': 'JournalEntry',
        'JOURNAL ENTRY': 'JournalEntry',
        'GL': 'JournalEntry',
        'STK_ADJ': 'StockAdjustment',
        'STOCKADJUSTMENT': 'StockAdjustment',
        'STOCK_ADJUSTMENT': 'StockAdjustment',
        'RCPT': 'Receipt',
        'RECEIPT': 'Receipt',
        'CASH_RECEIPT': 'Receipt',
        'PAY': 'Payment',
        'PAYMENT': 'Payment',
        'CPV': 'Payment',
    }
    return aliases.get(upper, 'Purchase')


def _sanitize_tx_no(raw: str) -> str:
    s = re.sub(r'[^\w\-./]', '_', (raw or '').strip())
    return s[:80] or 'NEW'


def audit_files_root(app_root: Optional[str] = None) -> Path:
    base = Path(app_root or os.getcwd())
    root = base / 'AuditFiles'
    root.mkdir(parents=True, exist_ok=True)
    for folder in TRANSACTION_TYPE_FOLDERS.values():
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root


def ensure_transaction_recording_audit_tables() -> bool:
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if not _table_exists(HDR_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {HDR_TABLE} (
                            AUDIT_ID            NUMBER NOT NULL,
                            LOCATIONCODE        NUMBER DEFAULT 1 NOT NULL,
                            TRANSACTION_TYPE    VARCHAR2(40) NOT NULL,
                            TRANSACTION_NO      VARCHAR2(80),
                            USERNAME            VARCHAR2(100),
                            START_TIME          TIMESTAMP DEFAULT SYSTIMESTAMP,
                            END_TIME            TIMESTAMP,
                            VIDEO_PATH          VARCHAR2(500),
                            BEFORE_IMAGE_PATH   VARCHAR2(500),
                            AFTER_IMAGE_PATH    VARCHAR2(500),
                            IP_ADDRESS          VARCHAR2(64),
                            MACHINE_NAME        VARCHAR2(200),
                            STATUS              VARCHAR2(20) DEFAULT 'OPEN',
                            CONSTRAINT PK_TX_AUDIT_HDR PRIMARY KEY (AUDIT_ID)
                        )
                        """
                    )
                    cur.execute(
                        f"CREATE SEQUENCE {HDR_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                    )
                if not _table_exists(DTL_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {DTL_TABLE} (
                            DETAIL_ID     NUMBER NOT NULL,
                            AUDIT_ID      NUMBER NOT NULL,
                            FIELD_NAME    VARCHAR2(200) NOT NULL,
                            OLD_VALUE     VARCHAR2(4000),
                            NEW_VALUE     VARCHAR2(4000),
                            CHANGE_TIME   TIMESTAMP DEFAULT SYSTIMESTAMP,
                            CONSTRAINT PK_TX_AUDIT_DTL PRIMARY KEY (DETAIL_ID),
                            CONSTRAINT FK_TX_AUDIT_DTL_HDR FOREIGN KEY (AUDIT_ID)
                                REFERENCES {HDR_TABLE} (AUDIT_ID)
                        )
                        """
                    )
                    cur.execute(
                        f"CREATE SEQUENCE {DTL_SEQ} START WITH 1 INCREMENT BY 1 NOCACHE"
                    )
            conn.commit()
        return True
    except Exception:
        return False


def ensure_auditor_seed_role() -> None:
    """Seed AUDITOR role with transaction recording audit menu paths (auth DB)."""
    rid = 'AUDITOR'
    menus = ['transaction_recording_audit.viewer']
    if role_exists(rid):
        try:
            from permissions import expand_role_permission_paths, get_role_editor_menu_paths
            current = get_role_permissions(rid) or []
            editor_paths = get_role_editor_menu_paths()
            normalized = sorted({
                p for p in expand_role_permission_paths(current)
                if p in editor_paths
            })
            if not normalized:
                normalized = list(menus)
            if set(normalized) != set(current):
                update_role(rid, menu_permissions=normalized)
        except Exception:
            pass
        return
    create_role(rid, 'Auditor', 'Read-only access to transaction screen recording audit logs', menus)


def user_can_view_recording_audit(username: Optional[str]) -> bool:
    u = (username or '').strip().lower()
    if u in ('admin', 'super'):
        return True
    rid = get_user_role_id(username or '')
    if not rid:
        return False
    role = get_role_by_id(rid) or {}
    rname = (role.get('role_name') or '').upper()
    rid_upper = (rid or '').upper()
    if 'ADMIN' in rname or 'AUDITOR' in rname or rid_upper in ('ADMIN', 'AUDITOR', 'HO_FULL'):
        return True
    perms = get_role_permissions(rid) or []
    return any(str(p).startswith('transaction_recording_audit.') for p in perms)


def _next_hdr_id(cur) -> int:
    cur.execute(f'SELECT {HDR_SEQ}.NEXTVAL FROM DUAL')
    row = cur.fetchone()
    return int(row[0])


def _next_dtl_id(cur) -> int:
    cur.execute(f'SELECT {DTL_SEQ}.NEXTVAL FROM DUAL')
    row = cur.fetchone()
    return int(row[0])


def start_audit_record(
    *,
    transaction_type: str,
    transaction_no: str,
    username: str,
    ip_address: str,
    machine_name: str,
    location_code: int = 1,
) -> int:
    ensure_transaction_recording_audit_tables()
    tx_type = _safe_tx_type(transaction_type)
    tx_no = _sanitize_tx_no(transaction_no)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            audit_id = _next_hdr_id(cur)
            cur.execute(
                f"""
                INSERT INTO {HDR_TABLE}
                    (AUDIT_ID, LOCATIONCODE, TRANSACTION_TYPE, TRANSACTION_NO,
                     USERNAME, START_TIME, IP_ADDRESS, MACHINE_NAME, STATUS)
                VALUES
                    (:id, :loc, :tt, :tn, :uname, SYSTIMESTAMP, :ip, :machine, :st)
                """,
                {
                    'id': audit_id,
                    'loc': location_code,
                    'tt': tx_type,
                    'tn': tx_no,
                    'uname': (username or '')[:100],
                    'ip': (ip_address or '')[:64],
                    'machine': (machine_name or '')[:200],
                    'st': _STATUS_OPEN,
                },
            )
        conn.commit()
    return audit_id


def append_field_change(
    audit_id: int,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
) -> None:
    ensure_transaction_recording_audit_tables()
    fname = (field_name or '').strip()[:200]
    if not fname or not audit_id:
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            detail_id = _next_dtl_id(cur)
            cur.execute(
                f"""
                INSERT INTO {DTL_TABLE}
                    (DETAIL_ID, AUDIT_ID, FIELD_NAME, OLD_VALUE, NEW_VALUE, CHANGE_TIME)
                VALUES
                    (:did, :aid, :fn, :ov, :nv, SYSTIMESTAMP)
                """,
                {
                    'did': detail_id,
                    'aid': int(audit_id),
                    'fn': fname,
                    'ov': (old_value or '')[:4000] if old_value is not None else None,
                    'nv': (new_value or '')[:4000] if new_value is not None else None,
                },
            )
        conn.commit()


def _relative_path(full_path: Path, root: Path) -> str:
    try:
        return str(full_path.relative_to(root)).replace('\\', '/')
    except ValueError:
        return str(full_path).replace('\\', '/')


def save_audit_image(
    *,
    app_root: str,
    transaction_type: str,
    transaction_no: str,
    image_bytes: bytes,
    phase: str,
) -> str:
    root = audit_files_root(app_root)
    tx_type = _safe_tx_type(transaction_type)
    folder = _folder_for_tx_type(tx_type)
    tx_no = _sanitize_tx_no(transaction_no)
    phase_key = 'before' if phase == 'before' else 'after'
    filename = f'{tx_type}_{tx_no}_{phase_key}.png'
    dest = root / folder / filename
    dest.write_bytes(image_bytes)
    return _relative_path(dest, root)


def save_audit_video(
    *,
    app_root: str,
    transaction_type: str,
    transaction_no: str,
    video_bytes: bytes,
    ext: str = 'webm',
    audit_id: Optional[int] = None,
) -> str:
    root = audit_files_root(app_root)
    tx_type = _safe_tx_type(transaction_type)
    folder = _folder_for_tx_type(tx_type)
    tx_no = _sanitize_tx_no(transaction_no)
    ext_clean = re.sub(r'[^a-z0-9]', '', (ext or 'webm').lower()) or 'webm'
    if audit_id:
        filename = f'{tx_type}_{tx_no}_audit{int(audit_id)}.{ext_clean}'
    else:
        filename = f'{tx_no}.{ext_clean}'
    dest = root / folder / filename
    dest.write_bytes(video_bytes)
    return _relative_path(dest, root)


def complete_audit_record(
    audit_id: int,
    *,
    status: str,
    transaction_no: Optional[str] = None,
    before_image_path: Optional[str] = None,
    after_image_path: Optional[str] = None,
    video_path: Optional[str] = None,
) -> None:
    ensure_transaction_recording_audit_tables()
    st = (status or _STATUS_SAVED).upper()
    if st not in (_STATUS_SAVED, _STATUS_FAILED, _STATUS_OPEN):
        st = _STATUS_SAVED
    sets = ['END_TIME = SYSTIMESTAMP', 'STATUS = :st']
    params: Dict[str, Any] = {'id': int(audit_id), 'st': st}
    if transaction_no is not None:
        sets.append('TRANSACTION_NO = :tn')
        params['tn'] = _sanitize_tx_no(transaction_no)
    if before_image_path is not None:
        sets.append('BEFORE_IMAGE_PATH = :bp')
        params['bp'] = (before_image_path or '')[:500]
    if after_image_path is not None:
        sets.append('AFTER_IMAGE_PATH = :ap')
        params['ap'] = (after_image_path or '')[:500]
    if video_path is not None:
        sets.append('VIDEO_PATH = :vp')
        params['vp'] = (video_path or '')[:500]
    sql = f"UPDATE {HDR_TABLE} SET {', '.join(sets)} WHERE AUDIT_ID = :id"
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    start = row.get('start_time') or row.get('START_TIME')
    end = row.get('end_time') or row.get('END_TIME')
    duration_sec = None
    if start and end:
        try:
            duration_sec = int((end - start).total_seconds())
        except Exception:
            duration_sec = None
    tx_type = row.get('transaction_type') or row.get('TRANSACTION_TYPE') or ''
    return {
        'audit_id': row.get('audit_id') or row.get('AUDIT_ID'),
        'transaction_type': tx_type,
        'transaction_type_label': TRANSACTION_TYPE_LABELS.get(tx_type, tx_type),
        'transaction_no': row.get('transaction_no') or row.get('TRANSACTION_NO') or '',
        'username': row.get('username') or row.get('USERNAME') or '',
        'start_time': start.isoformat() if hasattr(start, 'isoformat') else (str(start) if start else ''),
        'end_time': end.isoformat() if hasattr(end, 'isoformat') else (str(end) if end else ''),
        'date': start.strftime('%Y-%m-%d') if hasattr(start, 'strftime') else '',
        'duration_sec': duration_sec,
        'duration_label': _format_duration(duration_sec),
        'video_path': row.get('video_path') or row.get('VIDEO_PATH') or '',
        'before_image_path': row.get('before_image_path') or row.get('BEFORE_IMAGE_PATH') or '',
        'after_image_path': row.get('after_image_path') or row.get('AFTER_IMAGE_PATH') or '',
        'ip_address': row.get('ip_address') or row.get('IP_ADDRESS') or '',
        'machine_name': row.get('machine_name') or row.get('MACHINE_NAME') or '',
        'status': row.get('status') or row.get('STATUS') or '',
    }


def _format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return '—'
    if seconds < 60:
        return f'{seconds}s'
    mins, secs = divmod(seconds, 60)
    if mins < 60:
        return f'{mins}m {secs}s'
    hrs, mins = divmod(mins, 60)
    return f'{hrs}h {mins}m'


def list_audit_records(
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    username: Optional[str] = None,
    transaction_type: Optional[str] = None,
    transaction_no: Optional[str] = None,
    location_code: Optional[int] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    ensure_transaction_recording_audit_tables()
    where = ['1=1']
    params: Dict[str, Any] = {'lim': max(1, min(limit, 500))}
    if location_code is not None:
        where.append('LOCATIONCODE = :loc')
        params['loc'] = int(location_code)
    if date_from:
        where.append('TRUNC(START_TIME) >= TO_DATE(:df, \'YYYY-MM-DD\')')
        params['df'] = date_from[:10]
    if date_to:
        where.append('TRUNC(START_TIME) <= TO_DATE(:dt, \'YYYY-MM-DD\')')
        params['dt'] = date_to[:10]
    if username:
        where.append('UPPER(USERNAME) LIKE UPPER(:uname)')
        params['uname'] = f'%{username.strip()}%'
    if transaction_type:
        where.append('TRANSACTION_TYPE = :tt')
        params['tt'] = _safe_tx_type(transaction_type)
    if transaction_no:
        where.append('UPPER(TRANSACTION_NO) LIKE UPPER(:tn)')
        params['tn'] = f'%{transaction_no.strip()}%'
    sql = f"""
        SELECT * FROM (
            SELECT
                AUDIT_ID AS audit_id,
                TRANSACTION_TYPE AS transaction_type,
                TRANSACTION_NO AS transaction_no,
                USERNAME AS username,
                START_TIME AS start_time,
                END_TIME AS end_time,
                VIDEO_PATH AS video_path,
                BEFORE_IMAGE_PATH AS before_image_path,
                AFTER_IMAGE_PATH AS after_image_path,
                IP_ADDRESS AS ip_address,
                MACHINE_NAME AS machine_name,
                STATUS AS status
            FROM {HDR_TABLE}
            WHERE {' AND '.join(where)}
            ORDER BY START_TIME DESC
        ) WHERE ROWNUM <= :lim
    """
    rows = _safe_rows(sql, params)
    return [_row_to_dict(r) for r in rows]


def get_audit_record(audit_id: int) -> Optional[Dict[str, Any]]:
    ensure_transaction_recording_audit_tables()
    rows = _safe_rows(
        f"""
        SELECT
            AUDIT_ID AS audit_id,
            TRANSACTION_TYPE AS transaction_type,
            TRANSACTION_NO AS transaction_no,
            USERNAME AS username,
            START_TIME AS start_time,
            END_TIME AS end_time,
            VIDEO_PATH AS video_path,
            BEFORE_IMAGE_PATH AS before_image_path,
            AFTER_IMAGE_PATH AS after_image_path,
            IP_ADDRESS AS ip_address,
            MACHINE_NAME AS machine_name,
            STATUS AS status
        FROM {HDR_TABLE}
        WHERE AUDIT_ID = :id
        """,
        {'id': int(audit_id)},
    )
    if not rows:
        return None
    hdr = _row_to_dict(rows[0])
    dtl = _safe_rows(
        f"""
        SELECT
            DETAIL_ID AS detail_id,
            FIELD_NAME AS field_name,
            OLD_VALUE AS old_value,
            NEW_VALUE AS new_value,
            CHANGE_TIME AS change_time
        FROM {DTL_TABLE}
        WHERE AUDIT_ID = :id
        ORDER BY CHANGE_TIME ASC, DETAIL_ID ASC
        """,
        {'id': int(audit_id)},
    )
    changes = []
    for d in dtl:
        ct = d.get('change_time')
        changes.append({
            'detail_id': d.get('detail_id'),
            'field_name': d.get('field_name') or '',
            'old_value': d.get('old_value') or '',
            'new_value': d.get('new_value') or '',
            'change_time': ct.isoformat() if hasattr(ct, 'isoformat') else (str(ct) if ct else ''),
        })
    hdr['changes'] = changes
    return hdr


def build_dashboard_stats(*, location_code: Optional[int] = None) -> Dict[str, Any]:
    ensure_transaction_recording_audit_tables()
    loc_clause = ''
    params: Dict[str, Any] = {}
    if location_code is not None:
        loc_clause = ' AND LOCATIONCODE = :loc'
        params['loc'] = int(location_code)

    today_rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {HDR_TABLE}
        WHERE TRUNC(START_TIME) = TRUNC(SYSDATE){loc_clause}
        """,
        params,
    )
    audited_rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {HDR_TABLE}
        WHERE STATUS = 'SAVED'{loc_clause}
        """,
        params,
    )
    failed_rows = _safe_rows(
        f"""
        SELECT COUNT(*) AS cnt FROM {HDR_TABLE}
        WHERE STATUS = 'FAILED'{loc_clause}
        """,
        params,
    )
    active_users = _safe_rows(
        f"""
        SELECT USERNAME AS username, COUNT(*) AS cnt
        FROM {HDR_TABLE}
        WHERE START_TIME >= SYSDATE - 30{loc_clause}
        GROUP BY USERNAME
        ORDER BY COUNT(*) DESC
        FETCH FIRST 8 ROWS ONLY
        """,
        params,
    )
    recent_adj = _safe_rows(
        f"""
        SELECT
            AUDIT_ID AS audit_id,
            TRANSACTION_NO AS transaction_no,
            USERNAME AS username,
            START_TIME AS start_time,
            STATUS AS status
        FROM {HDR_TABLE}
        WHERE TRANSACTION_TYPE = 'StockAdjustment'{loc_clause}
        ORDER BY START_TIME DESC
        FETCH FIRST 10 ROWS ONLY
        """,
        params,
    )
    return {
        'transactions_today': int((today_rows[0] if today_rows else {}).get('cnt') or 0),
        'audited_saved': int((audited_rows[0] if audited_rows else {}).get('cnt') or 0),
        'failed_saves': int((failed_rows[0] if failed_rows else {}).get('cnt') or 0),
        'most_active_users': [
            {'username': r.get('username') or '', 'count': int(r.get('cnt') or 0)}
            for r in active_users
        ],
        'recent_stock_adjustments': [
            {
                'audit_id': r.get('audit_id'),
                'transaction_no': r.get('transaction_no') or '',
                'username': r.get('username') or '',
                'start_time': (r.get('start_time').isoformat() if hasattr(r.get('start_time'), 'isoformat') else str(r.get('start_time') or '')),
                'status': r.get('status') or '',
            }
            for r in recent_adj
        ],
    }


def transaction_view_url(transaction_type: str, transaction_no: str) -> Optional[str]:
    tx_type = _safe_tx_type(transaction_type)
    no = (transaction_no or '').strip()
    if not no or no.upper() == 'NEW':
        return None
    if tx_type == 'GRN':
        return f'/purchase/receipt/query/{no}'
    if tx_type == 'PO':
        return f'/purchase/order/edit/{no}'
    if tx_type == 'PurchaseReturn':
        return f'/purchase/return/query/{no}'
    if tx_type == 'StockAdjustment':
        return f'/purchase/stock-adjustment/{no}'
    if tx_type == 'StockTransfer':
        return f'/purchase/stock-transfer/query/{no}'
    if tx_type == 'Repacking':
        return f'/purchase/repacking/{no}'
    if tx_type == 'Purchase':
        return f'/purchase/invoice/{no}' if no else '/purchase/invoice'
    if tx_type == 'Sales':
        return f'/sales?billno={no}'
    if tx_type == 'SalesReturn':
        return f'/sales-return?billno={no}'
    if tx_type == 'Receipt':
        return f'/accounts/cash-receipt?receipt_no={no}'
    if tx_type == 'Payment':
        return f'/accounts/cash-payment-voucher?voucher_no={no}'
    if tx_type == 'JournalEntry':
        return f'/accounts/journal-entry/voucher/{no}' if no and no.upper() != 'NEW' else '/accounts/journal-entry?new=1'
    return None


def list_audit_usernames(limit: int = 100) -> List[str]:
    ensure_transaction_recording_audit_tables()
    rows = _safe_rows(
        f"""
        SELECT DISTINCT USERNAME AS username FROM {HDR_TABLE}
        WHERE USERNAME IS NOT NULL
        ORDER BY USERNAME
        FETCH FIRST :lim ROWS ONLY
        """,
        {'lim': max(1, min(limit, 500))},
    )
    return [str(r.get('username') or '').strip() for r in rows if str(r.get('username') or '').strip()]


def archive_old_audit_files(app_root: str, *, retention_days: int = 365) -> Tuple[int, int]:
    """Move audit files older than retention_days into AuditFiles/_archive/YYYY/."""
    root = audit_files_root(app_root)
    archive_root = root / '_archive'
    archive_root.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=max(1, retention_days))
    moved = 0
    scanned = 0
    for folder in TRANSACTION_TYPE_FOLDERS.values():
        folder_path = root / folder
        if not folder_path.is_dir():
            continue
        for fp in folder_path.iterdir():
            if not fp.is_file():
                continue
            scanned += 1
            try:
                mtime = datetime.fromtimestamp(fp.stat().st_mtime)
            except OSError:
                continue
            if mtime >= cutoff:
                continue
            year_dir = archive_root / str(mtime.year) / folder
            year_dir.mkdir(parents=True, exist_ok=True)
            dest = year_dir / fp.name
            if dest.exists():
                dest = year_dir / f'{fp.stem}_{int(mtime.timestamp())}{fp.suffix}'
            try:
                shutil.move(str(fp), str(dest))
                moved += 1
            except OSError:
                pass
    return moved, scanned
