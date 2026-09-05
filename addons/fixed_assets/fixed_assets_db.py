"""Fixed assets — categories, register, acquisition & depreciation GL."""
from __future__ import annotations

import calendar
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import (
    _get_connection,
    _get_table_columns,
    _norm_gl_account_code,
    _safe_rows,
    create_gl_journal_entry,
    ensure_gl_tables,
    get_all_chart_of_accounts,
    get_location_master_name_by_code,
    get_supplier_list,
)

CATEGORY_TABLE = 'FA_CATEGORY'
ASSET_TABLE = 'FA_ASSET'
DEP_RUN_TABLE = 'FA_DEP_RUN'
DEP_LINE_TABLE = 'FA_DEP_LINE'
CATEGORY_SEQ = 'FA_CATEGORY_SEQ'
ASSET_SEQ = 'FA_ASSET_SEQ'
DEP_RUN_SEQ = 'FA_DEP_RUN_SEQ'
DEP_LINE_SEQ = 'FA_DEP_LINE_SEQ'
DISPOSAL_TABLE = 'FA_DISPOSAL'
TRANSFER_TABLE = 'FA_TRANSFER'
SALE_HDR_TABLE = 'FA_SALE_HDR'
SALE_LINE_TABLE = 'FA_SALE_LINE'
DISPOSAL_SEQ = 'FA_DISPOSAL_SEQ'
TRANSFER_SEQ = 'FA_TRANSFER_SEQ'
SALE_HDR_SEQ = 'FA_SALE_HDR_SEQ'
SALE_LINE_SEQ = 'FA_SALE_LINE_SEQ'

STATUS_ACTIVE = 'ACTIVE'
STATUS_FULLY_DEP = 'FULLY_DEP'
STATUS_DISPOSED = 'DISPOSED'
RUN_DRAFT = 'DRAFT'
RUN_POSTED = 'POSTED'
DISPOSAL_DRAFT = 'DRAFT'
DISPOSAL_POSTED = 'POSTED'
TRANSFER_POSTED = 'POSTED'
SALE_DRAFT = 'DRAFT'
SALE_POSTED = 'POSTED'
DISPOSAL_TYPE_SALE = 'SALE'
DISPOSAL_TYPE_SCRAP = 'SCRAP'

DEFAULT_CATEGORIES = (
    ('MACH', 'Machinery & Equipment', '1510', '1600', '5500', 60),
    ('FURN', 'Furniture & Fixtures', '1520', '1600', '5500', 84),
    ('VEH', 'Vehicles', '1530', '1600', '5500', 48),
)


def _table_exists_cur(cur: Any, name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) = UPPER(:t)",
        {'t': name},
    )
    row = cur.fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _ensure_seq(cur: Any, seq_name: str) -> None:
    try:
        cur.execute('SELECT 1 FROM user_sequences WHERE sequence_name = :n', {'n': seq_name})
        if cur.fetchone() is None:
            cur.execute(f'CREATE SEQUENCE {seq_name} START WITH 1 INCREMENT BY 1 NOCACHE')
    except Exception:
        pass


def _row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return {}
    return {str(k).lower(): v for k, v in row.items()}


def _period_last_day(period_yyyymm: str) -> str:
    s = str(period_yyyymm or '').strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError('Period must be YYYYMM.')
    year = int(s[:4])
    month = int(s[4:6])
    if month < 1 or month > 12:
        raise ValueError('Invalid month in period.')
    last = calendar.monthrange(year, month)[1]
    return f'{year:04d}-{month:02d}-{last:02d}'


def _period_first_day(period_yyyymm: str) -> str:
    s = str(period_yyyymm or '').strip()
    return f'{s[:4]}-{s[4:6]}-01'


def _monthly_depreciation(cost: float, salvage: float, life_months: int) -> float:
    if life_months <= 0:
        return 0.0
    base = max(float(cost or 0) - float(salvage or 0), 0.0)
    return round(base / life_months, 2)


def _coa_postable_codes() -> set:
    codes = set()
    for r in get_all_chart_of_accounts() or []:
        code = str(r.get('code') or '').strip()
        if not code:
            continue
        postable = str(r.get('is_postable') or r.get('IS_POSTABLE') or 'Y').strip().upper()
        status = str(r.get('status') or r.get('STATUS') or 'ACTIVE').strip().upper()
        if postable in ('Y', '1', 'TRUE') and status == 'ACTIVE':
            codes.add(code)
    return codes


def _validate_account(code: str, label: str, *, require_postable: bool = True) -> Optional[str]:
    ac = _norm_gl_account_code(code)
    if not ac:
        return f'{label} is required.'
    coa_codes = _coa_postable_codes()
    all_codes = {str(r.get('code') or '').strip() for r in get_all_chart_of_accounts() or []}
    if ac not in all_codes:
        return f'{label} "{ac}" not found in Chart of Accounts.'
    if require_postable and ac not in coa_codes:
        return f'{label} "{ac}" is not a postable active account.'
    return None


def ensure_fixed_assets_tables() -> bool:
    ensure_gl_tables()
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for seq in (
                    CATEGORY_SEQ, ASSET_SEQ, DEP_RUN_SEQ, DEP_LINE_SEQ,
                    DISPOSAL_SEQ, TRANSFER_SEQ, SALE_HDR_SEQ, SALE_LINE_SEQ,
                ):
                    _ensure_seq(cur, seq)
                if not _table_exists_cur(cur, CATEGORY_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {CATEGORY_TABLE} (
                            CATEGORY_ID NUMBER NOT NULL,
                            CODE VARCHAR2(20) NOT NULL,
                            NAME VARCHAR2(100) NOT NULL,
                            ASSET_ACCOUNT VARCHAR2(20) NOT NULL,
                            ACCUM_DEP_ACCOUNT VARCHAR2(20) NOT NULL,
                            DEP_EXPENSE_ACCOUNT VARCHAR2(20) NOT NULL,
                            USEFUL_LIFE_MONTHS NUMBER(6) DEFAULT 60 NOT NULL,
                            DEP_METHOD VARCHAR2(10) DEFAULT 'SL',
                            ACTIVE VARCHAR2(1) DEFAULT 'Y',
                            CREATED_BY VARCHAR2(50),
                            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            UPDATED_BY VARCHAR2(50),
                            UPDATED_AT TIMESTAMP,
                            CONSTRAINT PK_{CATEGORY_TABLE} PRIMARY KEY (CATEGORY_ID),
                            CONSTRAINT UK_{CATEGORY_TABLE}_CODE UNIQUE (CODE)
                        )
                        """
                    )
                if not _table_exists_cur(cur, ASSET_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {ASSET_TABLE} (
                            ASSET_ID NUMBER NOT NULL,
                            ASSET_NO VARCHAR2(30) NOT NULL,
                            NAME VARCHAR2(200) NOT NULL,
                            CATEGORY_ID NUMBER NOT NULL,
                            ACQUISITION_DATE DATE NOT NULL,
                            ACQUISITION_COST NUMBER(18,2) NOT NULL,
                            SALVAGE_VALUE NUMBER(18,2) DEFAULT 0,
                            ACCUM_DEP NUMBER(18,2) DEFAULT 0,
                            LOCATION_CODE NUMBER(10),
                            CUSTODIAN VARCHAR2(100),
                            SERIAL_NO VARCHAR2(100),
                            REMARKS VARCHAR2(500),
                            STATUS VARCHAR2(20) DEFAULT 'ACTIVE',
                            CREDIT_ACCOUNT VARCHAR2(20),
                            CREDIT_PARTY_TYPE VARCHAR2(20),
                            CREDIT_PARTY_CODE VARCHAR2(50),
                            GL_ACQ_VOUCHER VARCHAR2(30),
                            POSTED_ACQ VARCHAR2(1) DEFAULT 'N',
                            LAST_DEP_YYYYMM VARCHAR2(6),
                            CREATED_BY VARCHAR2(50),
                            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            UPDATED_BY VARCHAR2(50),
                            UPDATED_AT TIMESTAMP,
                            CONSTRAINT PK_{ASSET_TABLE} PRIMARY KEY (ASSET_ID),
                            CONSTRAINT UK_{ASSET_TABLE}_NO UNIQUE (ASSET_NO)
                        )
                        """
                    )
                _ensure_fa_asset_party_columns(cur)
                _ensure_fa_category_disposal_columns(cur)
                _ensure_fa_asset_disposal_columns(cur)
                if not _table_exists_cur(cur, DEP_RUN_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {DEP_RUN_TABLE} (
                            RUN_ID NUMBER NOT NULL,
                            RUN_NO VARCHAR2(30) NOT NULL,
                            PERIOD_YYYYMM VARCHAR2(6) NOT NULL,
                            RUN_DATE DATE,
                            STATUS VARCHAR2(20) DEFAULT 'DRAFT',
                            GL_VOUCHER_NO VARCHAR2(30),
                            TOTAL_DEP NUMBER(18,2) DEFAULT 0,
                            CREATED_BY VARCHAR2(50),
                            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            POSTED_BY VARCHAR2(50),
                            POSTED_AT TIMESTAMP,
                            CONSTRAINT PK_{DEP_RUN_TABLE} PRIMARY KEY (RUN_ID),
                            CONSTRAINT UK_{DEP_RUN_TABLE}_NO UNIQUE (RUN_NO)
                        )
                        """
                    )
                if not _table_exists_cur(cur, DEP_LINE_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {DEP_LINE_TABLE} (
                            LINE_ID NUMBER NOT NULL,
                            RUN_ID NUMBER NOT NULL,
                            ASSET_ID NUMBER NOT NULL,
                            DEP_AMOUNT NUMBER(18,2) NOT NULL,
                            ACCUM_BEFORE NUMBER(18,2) NOT NULL,
                            ACCUM_AFTER NUMBER(18,2) NOT NULL,
                            CONSTRAINT PK_{DEP_LINE_TABLE} PRIMARY KEY (LINE_ID)
                        )
                        """
                    )
                if not _table_exists_cur(cur, DISPOSAL_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {DISPOSAL_TABLE} (
                            DISPOSAL_ID NUMBER NOT NULL,
                            DISPOSAL_NO VARCHAR2(30) NOT NULL,
                            ASSET_ID NUMBER NOT NULL,
                            DISPOSAL_DATE DATE NOT NULL,
                            DISPOSAL_TYPE VARCHAR2(10) DEFAULT 'SALE' NOT NULL,
                            PROCEEDS_AMOUNT NUMBER(18,2) DEFAULT 0,
                            PROCEEDS_ACCOUNT VARCHAR2(20),
                            PROCEEDS_PARTY_TYPE VARCHAR2(20),
                            PROCEEDS_PARTY_CODE VARCHAR2(50),
                            ACQUISITION_COST NUMBER(18,2) NOT NULL,
                            ACCUM_DEP NUMBER(18,2) DEFAULT 0,
                            NBV NUMBER(18,2) NOT NULL,
                            GAIN_LOSS_AMOUNT NUMBER(18,2) DEFAULT 0,
                            STATUS VARCHAR2(20) DEFAULT 'DRAFT',
                            GL_VOUCHER_NO VARCHAR2(30),
                            REMARKS VARCHAR2(500),
                            CREATED_BY VARCHAR2(50),
                            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            POSTED_BY VARCHAR2(50),
                            POSTED_AT TIMESTAMP,
                            CONSTRAINT PK_{DISPOSAL_TABLE} PRIMARY KEY (DISPOSAL_ID),
                            CONSTRAINT UK_{DISPOSAL_TABLE}_NO UNIQUE (DISPOSAL_NO)
                        )
                        """
                    )
                if not _table_exists_cur(cur, TRANSFER_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {TRANSFER_TABLE} (
                            TRANSFER_ID NUMBER NOT NULL,
                            TRANSFER_NO VARCHAR2(30) NOT NULL,
                            ASSET_ID NUMBER NOT NULL,
                            TRANSFER_DATE DATE NOT NULL,
                            FROM_LOCATION_CODE NUMBER(10),
                            TO_LOCATION_CODE NUMBER(10),
                            FROM_CUSTODIAN VARCHAR2(100),
                            TO_CUSTODIAN VARCHAR2(100),
                            REMARKS VARCHAR2(500),
                            STATUS VARCHAR2(20) DEFAULT 'POSTED',
                            CREATED_BY VARCHAR2(50),
                            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            CONSTRAINT PK_{TRANSFER_TABLE} PRIMARY KEY (TRANSFER_ID),
                            CONSTRAINT UK_{TRANSFER_TABLE}_NO UNIQUE (TRANSFER_NO)
                        )
                        """
                    )
                if not _table_exists_cur(cur, SALE_HDR_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {SALE_HDR_TABLE} (
                            SALE_ID NUMBER NOT NULL,
                            SALE_NO VARCHAR2(30) NOT NULL,
                            SALE_DATE DATE NOT NULL,
                            PROCEEDS_ACCOUNT VARCHAR2(20),
                            PROCEEDS_PARTY_TYPE VARCHAR2(20),
                            PROCEEDS_PARTY_CODE VARCHAR2(50),
                            TOTAL_PROCEEDS NUMBER(18,2) DEFAULT 0,
                            TOTAL_COST NUMBER(18,2) DEFAULT 0,
                            TOTAL_ACCUM NUMBER(18,2) DEFAULT 0,
                            TOTAL_NBV NUMBER(18,2) DEFAULT 0,
                            TOTAL_GAIN_LOSS NUMBER(18,2) DEFAULT 0,
                            STATUS VARCHAR2(20) DEFAULT 'DRAFT',
                            GL_VOUCHER_NO VARCHAR2(30),
                            REMARKS VARCHAR2(500),
                            CREATED_BY VARCHAR2(50),
                            CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP,
                            POSTED_BY VARCHAR2(50),
                            POSTED_AT TIMESTAMP,
                            CONSTRAINT PK_{SALE_HDR_TABLE} PRIMARY KEY (SALE_ID),
                            CONSTRAINT UK_{SALE_HDR_TABLE}_NO UNIQUE (SALE_NO)
                        )
                        """
                    )
                if not _table_exists_cur(cur, SALE_LINE_TABLE):
                    cur.execute(
                        f"""
                        CREATE TABLE {SALE_LINE_TABLE} (
                            LINE_ID NUMBER NOT NULL,
                            SALE_ID NUMBER NOT NULL,
                            LINE_NO NUMBER(6) NOT NULL,
                            ASSET_ID NUMBER NOT NULL,
                            PROCEEDS_AMOUNT NUMBER(18,2) DEFAULT 0 NOT NULL,
                            ACQUISITION_COST NUMBER(18,2) NOT NULL,
                            ACCUM_DEP NUMBER(18,2) DEFAULT 0,
                            NBV NUMBER(18,2) NOT NULL,
                            GAIN_LOSS_AMOUNT NUMBER(18,2) DEFAULT 0,
                            CONSTRAINT PK_{SALE_LINE_TABLE} PRIMARY KEY (LINE_ID)
                        )
                        """
                    )
                _ensure_fa_asset_disposal_columns(cur)
            conn.commit()
        _seed_default_categories()
        return True
    except Exception:
        return False


def _ensure_fa_asset_party_columns(cur: Any) -> None:
    if not _table_exists_cur(cur, ASSET_TABLE):
        return
    cols = {c.upper() for c in (_get_table_columns(ASSET_TABLE) or [])}
    if 'CREDIT_PARTY_TYPE' not in cols:
        cur.execute(f'ALTER TABLE {ASSET_TABLE} ADD (CREDIT_PARTY_TYPE VARCHAR2(20))')
    if 'CREDIT_PARTY_CODE' not in cols:
        cur.execute(f'ALTER TABLE {ASSET_TABLE} ADD (CREDIT_PARTY_CODE VARCHAR2(50))')


def _ensure_fa_category_disposal_columns(cur: Any) -> None:
    if not _table_exists_cur(cur, CATEGORY_TABLE):
        return
    cols = {c.upper() for c in (_get_table_columns(CATEGORY_TABLE) or [])}
    if 'GAIN_ON_DISPOSAL_ACCOUNT' not in cols:
        cur.execute(f'ALTER TABLE {CATEGORY_TABLE} ADD (GAIN_ON_DISPOSAL_ACCOUNT VARCHAR2(20))')
    if 'LOSS_ON_DISPOSAL_ACCOUNT' not in cols:
        cur.execute(f'ALTER TABLE {CATEGORY_TABLE} ADD (LOSS_ON_DISPOSAL_ACCOUNT VARCHAR2(20))')


def _ensure_fa_asset_disposal_columns(cur: Any) -> None:
    if not _table_exists_cur(cur, ASSET_TABLE):
        return
    cols = {c.upper() for c in (_get_table_columns(ASSET_TABLE) or [])}
    if 'DISPOSAL_ID' not in cols:
        cur.execute(f'ALTER TABLE {ASSET_TABLE} ADD (DISPOSAL_ID NUMBER)')
    if 'DISPOSED_DATE' not in cols:
        cur.execute(f'ALTER TABLE {ASSET_TABLE} ADD (DISPOSED_DATE DATE)')
    if 'SALE_ID' not in cols:
        cur.execute(f'ALTER TABLE {ASSET_TABLE} ADD (SALE_ID NUMBER)')


def format_credit_lookup_label(
    account_code: Optional[str],
    party_type: Optional[str] = None,
    party_code: Optional[str] = None,
) -> str:
    ac = _norm_gl_account_code(account_code) if account_code else ''
    if not ac:
        return ''
    pt = str(party_type or '').strip().upper()
    pc = str(party_code or '').strip()
    if pt == 'SUPPLIER' and pc:
        for s in get_supplier_list(search=pc, limit=20) or []:
            if str(s.get('suppliercode') or '').strip() == pc:
                nm = str(s.get('suppliername') or '').strip()
                return f'SUP: {pc} — {nm} (A/c {ac})' if nm else f'SUP: {pc} (A/c {ac})'
        return f'SUP: {pc} (A/c {ac})'
    if pt == 'CUSTOMER' and pc:
        return f'CUST: {pc} (A/c {ac})'
    for r in get_all_chart_of_accounts() or []:
        if str(r.get('code') or '').strip() == ac:
            nm = str(r.get('name') or '').strip()
            return f'{ac} — {nm}' if nm else ac
    return ac


def _normalize_credit_party(party_type: Optional[str], party_code: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    pt = str(party_type or '').strip().upper()[:20] or None
    pc = str(party_code or '').strip()[:50] or None
    if pt not in ('SUPPLIER', 'CUSTOMER'):
        return None, None
    if not pc:
        return None, None
    return pt, pc


def _seed_default_categories() -> None:
    existing = _safe_rows(f'SELECT COUNT(*) AS cnt FROM {CATEGORY_TABLE}', {})
    if existing and int(existing[0].get('cnt') or existing[0].get('CNT') or 0) > 0:
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for code, name, asset_ac, accum_ac, exp_ac, life in DEFAULT_CATEGORIES:
                cur.execute(f'SELECT {CATEGORY_SEQ}.NEXTVAL FROM DUAL')
                cid = cur.fetchone()[0]
                cur.execute(
                    f"""
                    INSERT INTO {CATEGORY_TABLE}
                        (CATEGORY_ID, CODE, NAME, ASSET_ACCOUNT, ACCUM_DEP_ACCOUNT,
                         DEP_EXPENSE_ACCOUNT, USEFUL_LIFE_MONTHS, DEP_METHOD, ACTIVE, CREATED_BY)
                    VALUES
                        (:id, :code, :name, :aa, :ad, :de, :life, 'SL', 'Y', 'system')
                    """,
                    {'id': cid, 'code': code, 'name': name, 'aa': asset_ac, 'ad': accum_ac, 'de': exp_ac, 'life': life},
                )
        conn.commit()


def list_fa_categories(*, include_inactive: bool = False) -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    where = '' if include_inactive else " WHERE NVL(ACTIVE, 'Y') = 'Y'"
    rows = _safe_rows(
        f"""
        SELECT CATEGORY_ID, CODE, NAME, ASSET_ACCOUNT, ACCUM_DEP_ACCOUNT, DEP_EXPENSE_ACCOUNT,
               GAIN_ON_DISPOSAL_ACCOUNT, LOSS_ON_DISPOSAL_ACCOUNT,
               USEFUL_LIFE_MONTHS, DEP_METHOD, ACTIVE, CREATED_BY, CREATED_AT
        FROM {CATEGORY_TABLE}
        {where}
        ORDER BY CODE
        """,
        {},
    )
    return [_row_keys(r) for r in rows or []]


def get_fa_category(category_id: int) -> Optional[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT CATEGORY_ID, CODE, NAME, ASSET_ACCOUNT, ACCUM_DEP_ACCOUNT, DEP_EXPENSE_ACCOUNT,
               GAIN_ON_DISPOSAL_ACCOUNT, LOSS_ON_DISPOSAL_ACCOUNT,
               USEFUL_LIFE_MONTHS, DEP_METHOD, ACTIVE
        FROM {CATEGORY_TABLE}
        WHERE CATEGORY_ID = :id
        """,
        {'id': int(category_id)},
    )
    return _row_keys(rows[0]) if rows else None


def upsert_fa_category(
    *,
    category_id: Optional[int],
    code: str,
    name: str,
    asset_account: str,
    accum_dep_account: str,
    dep_expense_account: str,
    useful_life_months: int,
    gain_on_disposal_account: Optional[str] = None,
    loss_on_disposal_account: Optional[str] = None,
    active: str = 'Y',
    user: str = 'web',
) -> Tuple[bool, str]:
    ensure_fixed_assets_tables()
    code = str(code or '').strip().upper()[:20]
    name = str(name or '').strip()[:100]
    asset_account = _norm_gl_account_code(asset_account)
    accum_dep_account = _norm_gl_account_code(accum_dep_account)
    dep_expense_account = _norm_gl_account_code(dep_expense_account)
    gain_on_disposal_account = _norm_gl_account_code(gain_on_disposal_account) if gain_on_disposal_account else None
    loss_on_disposal_account = _norm_gl_account_code(loss_on_disposal_account) if loss_on_disposal_account else None
    active = 'Y' if str(active or 'Y').strip().upper() == 'Y' else 'N'
    if not code:
        return False, 'Category code is required.'
    if not name:
        return False, 'Category name is required.'
    try:
        life = int(useful_life_months)
    except (TypeError, ValueError):
        return False, 'Useful life (months) must be a number.'
    if life <= 0:
        return False, 'Useful life must be greater than zero.'
    for ac, lbl, postable in (
        (asset_account, 'Asset account', True),
        (accum_dep_account, 'Accumulated depreciation account', False),
        (dep_expense_account, 'Depreciation expense account', True),
    ):
        err = _validate_account(ac, lbl, require_postable=postable)
        if err:
            return False, err
    for ac, lbl in (
        (gain_on_disposal_account, 'Gain on disposal account'),
        (loss_on_disposal_account, 'Loss on disposal account'),
    ):
        if ac:
            err = _validate_account(ac, lbl, require_postable=True)
            if err:
                return False, err
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if category_id:
                    cur.execute(
                        f"""
                        UPDATE {CATEGORY_TABLE}
                        SET CODE = :code, NAME = :name,
                            ASSET_ACCOUNT = :aa, ACCUM_DEP_ACCOUNT = :ad, DEP_EXPENSE_ACCOUNT = :de,
                            GAIN_ON_DISPOSAL_ACCOUNT = :ga, LOSS_ON_DISPOSAL_ACCOUNT = :la,
                            USEFUL_LIFE_MONTHS = :life, ACTIVE = :act,
                            UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
                        WHERE CATEGORY_ID = :id
                        """,
                        {
                            'id': int(category_id),
                            'code': code,
                            'name': name,
                            'aa': asset_account,
                            'ad': accum_dep_account,
                            'de': dep_expense_account,
                            'ga': gain_on_disposal_account,
                            'la': loss_on_disposal_account,
                            'life': life,
                            'act': active,
                            'usr': (user or 'web')[:50],
                        },
                    )
                else:
                    cur.execute(f'SELECT {CATEGORY_SEQ}.NEXTVAL FROM DUAL')
                    cid = cur.fetchone()[0]
                    cur.execute(
                        f"""
                        INSERT INTO {CATEGORY_TABLE}
                            (CATEGORY_ID, CODE, NAME, ASSET_ACCOUNT, ACCUM_DEP_ACCOUNT,
                             DEP_EXPENSE_ACCOUNT, GAIN_ON_DISPOSAL_ACCOUNT, LOSS_ON_DISPOSAL_ACCOUNT,
                             USEFUL_LIFE_MONTHS, DEP_METHOD, ACTIVE, CREATED_BY)
                        VALUES
                            (:id, :code, :name, :aa, :ad, :de, :ga, :la, :life, 'SL', :act, :usr)
                        """,
                        {
                            'id': cid,
                            'code': code,
                            'name': name,
                            'aa': asset_account,
                            'ad': accum_dep_account,
                            'de': dep_expense_account,
                            'ga': gain_on_disposal_account,
                            'la': loss_on_disposal_account,
                            'life': life,
                            'act': active,
                            'usr': (user or 'web')[:50],
                        },
                    )
            conn.commit()
        return True, ''
    except Exception as e:
        low = str(e).lower()
        if 'ora-00001' in low and 'code' in low:
            return False, f'Category code "{code}" already exists.'
        return False, str(e)


def delete_fa_category(category_id: int) -> Tuple[bool, str]:
    ensure_fixed_assets_tables()
    cnt = _safe_rows(
        f'SELECT COUNT(*) AS cnt FROM {ASSET_TABLE} WHERE CATEGORY_ID = :id',
        {'id': int(category_id)},
    )
    if cnt and int(cnt[0].get('cnt') or cnt[0].get('CNT') or 0) > 0:
        return False, 'Cannot delete — assets exist in this category.'
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {CATEGORY_TABLE} WHERE CATEGORY_ID = :id', {'id': int(category_id)})
            conn.commit()
        return True, ''
    except Exception as e:
        return False, str(e)


def _next_asset_no_cur(cur) -> str:
    year = datetime.now().strftime('%Y')
    prefix = f'FA-{year}-'
    cur.execute(
        f"""
        SELECT MAX(ASSET_NO) AS mx FROM {ASSET_TABLE}
        WHERE ASSET_NO LIKE :pfx || '%'
        """,
        {'pfx': prefix},
    )
    row = cur.fetchone()
    mx = str(row[0] if row and row[0] is not None else '').strip()
    seq = 1
    if mx.startswith(prefix):
        try:
            seq = int(mx[len(prefix):]) + 1
        except ValueError:
            seq = 1
    return f'{prefix}{seq:04d}'


def _next_asset_no() -> str:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            return _next_asset_no_cur(cur)


def list_fa_assets(*, status: Optional[str] = None, category_id: Optional[int] = None) -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    clauses = ['1=1']
    params: Dict[str, Any] = {}
    if status:
        clauses.append('a.STATUS = :st')
        params['st'] = str(status).strip().upper()
    if category_id:
        clauses.append('a.CATEGORY_ID = :cid')
        params['cid'] = int(category_id)
    rows = _safe_rows(
        f"""
        SELECT a.ASSET_ID, a.ASSET_NO, a.NAME, a.CATEGORY_ID, c.CODE AS CATEGORY_CODE, c.NAME AS CATEGORY_NAME,
               a.ACQUISITION_DATE, a.ACQUISITION_COST, a.SALVAGE_VALUE, a.ACCUM_DEP,
               (a.ACQUISITION_COST - NVL(a.ACCUM_DEP, 0)) AS NBV,
               a.LOCATION_CODE, a.CUSTODIAN, a.SERIAL_NO, a.STATUS,
               a.CREDIT_ACCOUNT, a.GL_ACQ_VOUCHER, a.POSTED_ACQ, a.LAST_DEP_YYYYMM
        FROM {ASSET_TABLE} a
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE {' AND '.join(clauses)}
        ORDER BY a.ASSET_NO DESC
        """,
        params,
    )
    return [_row_keys(r) for r in rows or []]


def get_fa_asset(asset_id: int) -> Optional[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT a.ASSET_ID, a.ASSET_NO, a.NAME, a.CATEGORY_ID, c.CODE AS CATEGORY_CODE, c.NAME AS CATEGORY_NAME,
               a.ACQUISITION_DATE, a.ACQUISITION_COST, a.SALVAGE_VALUE, a.ACCUM_DEP,
               (a.ACQUISITION_COST - NVL(a.ACCUM_DEP, 0)) AS NBV,
               a.LOCATION_CODE,                a.CUSTODIAN, a.SERIAL_NO, a.REMARKS, a.STATUS,
               a.CREDIT_ACCOUNT, a.CREDIT_PARTY_TYPE, a.CREDIT_PARTY_CODE,
               a.GL_ACQ_VOUCHER, a.POSTED_ACQ, a.LAST_DEP_YYYYMM,
               c.GAIN_ON_DISPOSAL_ACCOUNT, c.LOSS_ON_DISPOSAL_ACCOUNT,
               c.ASSET_ACCOUNT, c.ACCUM_DEP_ACCOUNT, c.DEP_EXPENSE_ACCOUNT, c.USEFUL_LIFE_MONTHS
        FROM {ASSET_TABLE} a
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE a.ASSET_ID = :id
        """,
        {'id': int(asset_id)},
    )
    if not rows:
        return None
    row = _row_keys(rows[0])
    if row.get('location_code') is not None:
        row['location_name'] = get_location_master_name_by_code(row.get('location_code')) or ''
    return row


def save_fa_asset(
    *,
    asset_id: Optional[int],
    name: str,
    category_id: int,
    acquisition_date: str,
    acquisition_cost: float,
    salvage_value: float = 0.0,
    location_code: Optional[int] = None,
    custodian: Optional[str] = None,
    serial_no: Optional[str] = None,
    remarks: Optional[str] = None,
    credit_account: Optional[str] = None,
    credit_party_type: Optional[str] = None,
    credit_party_code: Optional[str] = None,
    user: str = 'web',
) -> Tuple[bool, str, Optional[int]]:
    ensure_fixed_assets_tables()
    name = str(name or '').strip()[:200]
    if not name:
        return False, 'Asset name is required.', None
    cat = get_fa_category(int(category_id))
    if not cat:
        return False, 'Category not found.', None
    try:
        cost = round(float(acquisition_cost or 0), 2)
    except (TypeError, ValueError):
        return False, 'Invalid acquisition cost.', None
    if cost <= 0:
        return False, 'Acquisition cost must be greater than zero.', None
    try:
        salvage = round(float(salvage_value or 0), 2)
    except (TypeError, ValueError):
        salvage = 0.0
    if salvage < 0 or salvage >= cost:
        return False, 'Salvage value must be zero or less than acquisition cost.', None
    acq_date = str(acquisition_date or '').strip()[:10]
    if len(acq_date) < 10:
        return False, 'Acquisition date is required.', None
    credit_account = _norm_gl_account_code(credit_account) if credit_account else None
    cpt, cpc = _normalize_credit_party(credit_party_type, credit_party_code)
    if asset_id:
        existing = get_fa_asset(int(asset_id))
        if not existing:
            return False, 'Asset not found.', None
        if str(existing.get('posted_acq') or 'N').upper() == 'Y':
            if credit_account and credit_account != _norm_gl_account_code(existing.get('credit_account')):
                return False, 'Credit account cannot change after acquisition is posted.', None
            if int(existing.get('category_id') or 0) != int(category_id):
                return False, 'Category cannot change after acquisition is posted.', None
            if round(float(existing.get('acquisition_cost') or 0), 2) != cost:
                return False, 'Acquisition cost cannot change after posting.', None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if asset_id:
                    cur.execute(
                        f"""
                        UPDATE {ASSET_TABLE}
                        SET NAME = :name, CATEGORY_ID = :cid,
                            ACQUISITION_DATE = TO_DATE(:ad, 'YYYY-MM-DD'),
                            ACQUISITION_COST = :cost, SALVAGE_VALUE = :salvage,
                            LOCATION_CODE = :loc, CUSTODIAN = :cust, SERIAL_NO = :sn,
                            REMARKS = :rm, CREDIT_ACCOUNT = :cr,
                            CREDIT_PARTY_TYPE = :cpt, CREDIT_PARTY_CODE = :cpc,
                            UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
                        WHERE ASSET_ID = :id
                        """,
                        {
                            'id': int(asset_id),
                            'name': name,
                            'cid': int(category_id),
                            'ad': acq_date,
                            'cost': cost,
                            'salvage': salvage,
                            'loc': location_code,
                            'cust': (custodian or '')[:100] or None,
                            'sn': (serial_no or '')[:100] or None,
                            'rm': (remarks or '')[:500] or None,
                            'cr': credit_account,
                            'cpt': cpt,
                            'cpc': cpc,
                            'usr': (user or 'web')[:50],
                        },
                    )
                    aid = int(asset_id)
                else:
                    asset_no = _next_asset_no()
                    cur.execute(f'SELECT {ASSET_SEQ}.NEXTVAL FROM DUAL')
                    aid = cur.fetchone()[0]
                    cur.execute(
                        f"""
                        INSERT INTO {ASSET_TABLE}
                            (ASSET_ID, ASSET_NO, NAME, CATEGORY_ID, ACQUISITION_DATE,
                             ACQUISITION_COST, SALVAGE_VALUE, LOCATION_CODE, CUSTODIAN,
                             SERIAL_NO, REMARKS, CREDIT_ACCOUNT, CREDIT_PARTY_TYPE, CREDIT_PARTY_CODE,
                             STATUS, POSTED_ACQ, CREATED_BY)
                        VALUES
                            (:id, :no, :name, :cid, TO_DATE(:ad, 'YYYY-MM-DD'),
                             :cost, :salvage, :loc, :cust, :sn, :rm, :cr, :cpt, :cpc, 'ACTIVE', 'N', :usr)
                        """,
                        {
                            'id': aid,
                            'no': asset_no,
                            'name': name,
                            'cid': int(category_id),
                            'ad': acq_date,
                            'cost': cost,
                            'salvage': salvage,
                            'loc': location_code,
                            'cust': (custodian or '')[:100] or None,
                            'sn': (serial_no or '')[:100] or None,
                            'rm': (remarks or '')[:500] or None,
                            'cr': credit_account,
                            'cpt': cpt,
                            'cpc': cpc,
                            'usr': (user or 'web')[:50],
                        },
                    )
            conn.commit()
        return True, '', aid
    except Exception as e:
        return False, str(e), None


def _post_fa_acquisition_tx(
    conn,
    cur,
    asset_id: int,
    asset: Dict[str, Any],
    *,
    user: str = 'web',
) -> str:
    if str(asset.get('posted_acq') or 'N').upper() == 'Y':
        raise ValueError('Acquisition already posted.')
    credit = _norm_gl_account_code(asset.get('credit_account'))
    if not credit:
        raise ValueError('Credit account is required to post acquisition.')
    err = _validate_account(credit, 'Credit account')
    if err:
        raise ValueError(err)
    asset_ac = _norm_gl_account_code(asset.get('asset_account'))
    err = _validate_account(asset_ac, 'Asset account')
    if err:
        raise ValueError(err)
    cost = round(float(asset.get('acquisition_cost') or 0), 2)
    acq_date = asset.get('acquisition_date')
    if hasattr(acq_date, 'strftime'):
        acq_date = acq_date.strftime('%Y-%m-%d')
    else:
        acq_date = str(acq_date or '')[:10]
    ref = str(asset.get('asset_no') or '')
    narration = f"FA acquisition — {asset.get('name') or ref}"
    cpt = str(asset.get('credit_party_type') or '').strip().upper() or None
    cpc = str(asset.get('credit_party_code') or '').strip() or None
    credit_line: Dict[str, Any] = {
        'account_code': credit,
        'debit': 0,
        'credit': cost,
        'remarks': ref,
    }
    if cpt in ('SUPPLIER', 'CUSTOMER') and cpc:
        credit_line['party_type'] = cpt
        credit_line['party_code'] = cpc
    lines = [
        {'account_code': asset_ac, 'debit': cost, 'credit': 0, 'remarks': ref},
        credit_line,
    ]
    vno = create_gl_journal_entry(
        acq_date,
        ref,
        narration,
        lines,
        created_by=(user or 'web')[:50],
        source='FA_ACQ',
        conn=conn,
        commit=False,
    )
    cur.execute(
        f"""
        UPDATE {ASSET_TABLE}
        SET POSTED_ACQ = 'Y', GL_ACQ_VOUCHER = :vno,
            UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
        WHERE ASSET_ID = :id
        """,
        {'vno': vno, 'usr': (user or 'web')[:50], 'id': int(asset_id)},
    )
    return vno


def post_fa_acquisition(asset_id: int, *, user: str = 'web') -> Tuple[bool, str, Optional[str]]:
    ensure_fixed_assets_tables()
    asset = get_fa_asset(int(asset_id))
    if not asset:
        return False, 'Asset not found.', None
    if str(asset.get('posted_acq') or 'N').upper() == 'Y':
        return False, 'Acquisition already posted.', asset.get('gl_acq_voucher')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                vno = _post_fa_acquisition_tx(conn, cur, int(asset_id), asset, user=user)
            conn.commit()
        return True, '', vno
    except Exception as e:
        return False, str(e), None


def save_fa_asset_register_batch(
    *,
    lines: List[Dict[str, Any]],
    acquisition_date: str,
    location_code: Optional[int] = None,
    remarks: Optional[str] = None,
    credit_account: Optional[str] = None,
    credit_party_type: Optional[str] = None,
    credit_party_code: Optional[str] = None,
    post_acq: bool = False,
    user: str = 'web',
) -> Tuple[bool, str, List[int]]:
    """Save multiple new assets in one transaction; optionally post all acquisitions."""
    ensure_fixed_assets_tables()
    if not lines:
        return False, 'Add at least one asset line.', []
    acq_date = str(acquisition_date or '').strip()[:10]
    if len(acq_date) < 10:
        return False, 'Acquisition date is required.', []
    credit_account = _norm_gl_account_code(credit_account) if credit_account else None
    cpt, cpc = _normalize_credit_party(credit_party_type, credit_party_code)
    if post_acq and not credit_account:
        return False, 'Credit account is required to post acquisition.', []
    if post_acq:
        err = _validate_account(credit_account, 'Credit account')
        if err:
            return False, err, []

    validated: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines, start=1):
        name = str(ln.get('name') or '').strip()[:200]
        if not name:
            return False, f'Line {idx}: asset name is required.', []
        try:
            category_id = int(ln.get('category_id') or 0)
        except (TypeError, ValueError):
            return False, f'Line {idx}: category is required.', []
        cat = get_fa_category(category_id)
        if not cat:
            return False, f'Line {idx}: category not found.', []
        try:
            cost = round(float(ln.get('acquisition_cost') or 0), 2)
        except (TypeError, ValueError):
            return False, f'Line {idx}: invalid acquisition cost.', []
        if cost <= 0:
            return False, f'Line {idx}: acquisition cost must be greater than zero.', []
        try:
            salvage = round(float(ln.get('salvage_value') or 0), 2)
        except (TypeError, ValueError):
            salvage = 0.0
        if salvage < 0 or salvage >= cost:
            return False, f'Line {idx}: salvage value must be zero or less than acquisition cost.', []
        if post_acq:
            asset_ac = _norm_gl_account_code(cat.get('asset_account'))
            err = _validate_account(asset_ac, f'Line {idx}: asset account')
            if err:
                return False, err, []
        validated.append({
            'name': name,
            'category_id': category_id,
            'acquisition_cost': cost,
            'salvage_value': salvage,
            'custodian': (ln.get('custodian') or '')[:100] or None,
            'serial_no': (ln.get('serial_no') or '')[:100] or None,
            'asset_account': _norm_gl_account_code(cat.get('asset_account')),
        })

    try:
        saved_ids: List[int] = []
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for vl in validated:
                    cur.execute(f'SELECT {ASSET_SEQ}.NEXTVAL FROM DUAL')
                    aid = int(cur.fetchone()[0])
                    asset_no = _next_asset_no_cur(cur)
                    cur.execute(
                        f"""
                        INSERT INTO {ASSET_TABLE}
                            (ASSET_ID, ASSET_NO, NAME, CATEGORY_ID, ACQUISITION_DATE,
                             ACQUISITION_COST, SALVAGE_VALUE, LOCATION_CODE, CUSTODIAN,
                             SERIAL_NO, REMARKS, CREDIT_ACCOUNT, CREDIT_PARTY_TYPE, CREDIT_PARTY_CODE,
                             STATUS, POSTED_ACQ, CREATED_BY)
                        VALUES
                            (:id, :no, :name, :cid, TO_DATE(:ad, 'YYYY-MM-DD'),
                             :cost, :salvage, :loc, :cust, :sn, :rm, :cr, :cpt, :cpc, 'ACTIVE', 'N', :usr)
                        """,
                        {
                            'id': aid,
                            'no': asset_no,
                            'name': vl['name'],
                            'cid': int(vl['category_id']),
                            'ad': acq_date,
                            'cost': vl['acquisition_cost'],
                            'salvage': vl['salvage_value'],
                            'loc': location_code,
                            'cust': vl['custodian'],
                            'sn': vl['serial_no'],
                            'rm': (remarks or '')[:500] or None,
                            'cr': credit_account,
                            'cpt': cpt,
                            'cpc': cpc,
                            'usr': (user or 'web')[:50],
                        },
                    )
                    saved_ids.append(aid)
                    if post_acq:
                        asset_row = {
                            'posted_acq': 'N',
                            'credit_account': credit_account,
                            'asset_account': vl['asset_account'],
                            'acquisition_cost': vl['acquisition_cost'],
                            'acquisition_date': acq_date,
                            'asset_no': asset_no,
                            'name': vl['name'],
                            'credit_party_type': cpt,
                            'credit_party_code': cpc,
                        }
                        _post_fa_acquisition_tx(conn, cur, aid, asset_row, user=user)
            conn.commit()
        return True, '', saved_ids
    except Exception as e:
        return False, str(e), []


def _asset_dep_line(asset: Dict[str, Any], period_yyyymm: str) -> Optional[Dict[str, Any]]:
    if str(asset.get('posted_acq') or 'N').upper() != 'Y':
        return None
    status = str(asset.get('status') or STATUS_ACTIVE).upper()
    if status in (STATUS_DISPOSED, STATUS_FULLY_DEP):
        return None
    last_dep = str(asset.get('last_dep_yyyymm') or '').strip()
    if last_dep and last_dep >= period_yyyymm:
        return None
    acq = asset.get('acquisition_date')
    if hasattr(acq, 'strftime'):
        acq_iso = acq.strftime('%Y-%m-%d')
    else:
        acq_iso = str(acq or '')[:10]
    period_end = _period_last_day(period_yyyymm)
    if acq_iso > period_end:
        return None
    life = int(asset.get('useful_life_months') or asset.get('USEFUL_LIFE_MONTHS') or 0)
    monthly = _monthly_depreciation(
        float(asset.get('acquisition_cost') or 0),
        float(asset.get('salvage_value') or 0),
        life,
    )
    accum = round(float(asset.get('accum_dep') or 0), 2)
    max_dep = round(float(asset.get('acquisition_cost') or 0) - float(asset.get('salvage_value') or 0), 2)
    remaining = round(max_dep - accum, 2)
    if remaining <= 0:
        return None
    dep_amt = min(monthly, remaining)
    if dep_amt <= 0:
        return None
    return {
        'asset_id': int(asset.get('asset_id') or 0),
        'asset_no': asset.get('asset_no'),
        'asset_name': asset.get('name'),
        'category_code': asset.get('category_code'),
        'dep_amount': dep_amt,
        'accum_before': accum,
        'accum_after': round(accum + dep_amt, 2),
        'dep_expense_account': _norm_gl_account_code(asset.get('dep_expense_account')),
        'accum_dep_account': _norm_gl_account_code(asset.get('accum_dep_account')),
    }


def preview_depreciation(period_yyyymm: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    ensure_fixed_assets_tables()
    try:
        _period_last_day(period_yyyymm)
    except ValueError as e:
        return False, str(e), []
    posted = _safe_rows(
        f"""
        SELECT RUN_ID FROM {DEP_RUN_TABLE}
        WHERE PERIOD_YYYYMM = :p AND STATUS = :st
        """,
        {'p': period_yyyymm, 'st': RUN_POSTED},
    )
    if posted:
        return False, f'Period {period_yyyymm} already has a posted depreciation run.', []
    assets = list_fa_assets(status=STATUS_ACTIVE)
    detailed = []
    for a in assets:
        full = get_fa_asset(int(a.get('asset_id') or 0))
        if not full:
            continue
        line = _asset_dep_line(full, period_yyyymm)
        if line:
            detailed.append(line)
    return True, '', detailed


def _next_dep_run_no(period_yyyymm: str) -> str:
    return f'FADEP-{period_yyyymm}-001'


def create_depreciation_run(period_yyyymm: str, *, user: str = 'web') -> Tuple[bool, str, Optional[int]]:
    ok, err, lines = preview_depreciation(period_yyyymm)
    if not ok:
        return False, err, None
    if not lines:
        return False, 'No assets eligible for depreciation in this period.', None
    total = round(sum(float(ln.get('dep_amount') or 0) for ln in lines), 2)
    run_date = _period_last_day(period_yyyymm)
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT RUN_ID, STATUS FROM {DEP_RUN_TABLE}
                    WHERE PERIOD_YYYYMM = :p
                    ORDER BY RUN_ID DESC
                    """,
                    {'p': period_yyyymm},
                )
                existing = cur.fetchone()
                if existing and str(existing[1] or '').upper() == RUN_POSTED:
                    return False, f'Period {period_yyyymm} is already posted.', None
                if existing:
                    run_id = int(existing[0])
                    cur.execute(f'DELETE FROM {DEP_LINE_TABLE} WHERE RUN_ID = :id', {'id': run_id})
                    cur.execute(
                        f"""
                        UPDATE {DEP_RUN_TABLE}
                        SET TOTAL_DEP = :tot, RUN_DATE = TO_DATE(:rd, 'YYYY-MM-DD'), STATUS = :st
                        WHERE RUN_ID = :id
                        """,
                        {'tot': total, 'rd': run_date, 'st': RUN_DRAFT, 'id': run_id},
                    )
                else:
                    cur.execute(f'SELECT {DEP_RUN_SEQ}.NEXTVAL FROM DUAL')
                    run_id = cur.fetchone()[0]
                    run_no = _next_dep_run_no(period_yyyymm)
                    cur.execute(
                        f"""
                        INSERT INTO {DEP_RUN_TABLE}
                            (RUN_ID, RUN_NO, PERIOD_YYYYMM, RUN_DATE, STATUS, TOTAL_DEP, CREATED_BY)
                        VALUES
                            (:id, :no, :p, TO_DATE(:rd, 'YYYY-MM-DD'), :st, :tot, :usr)
                        """,
                        {
                            'id': run_id,
                            'no': run_no,
                            'p': period_yyyymm,
                            'rd': run_date,
                            'st': RUN_DRAFT,
                            'tot': total,
                            'usr': (user or 'web')[:50],
                        },
                    )
                for ln in lines:
                    cur.execute(f'SELECT {DEP_LINE_SEQ}.NEXTVAL FROM DUAL')
                    lid = cur.fetchone()[0]
                    cur.execute(
                        f"""
                        INSERT INTO {DEP_LINE_TABLE}
                            (LINE_ID, RUN_ID, ASSET_ID, DEP_AMOUNT, ACCUM_BEFORE, ACCUM_AFTER)
                        VALUES
                            (:lid, :rid, :aid, :amt, :bef, :aft)
                        """,
                        {
                            'lid': lid,
                            'rid': run_id,
                            'aid': int(ln['asset_id']),
                            'amt': ln['dep_amount'],
                            'bef': ln['accum_before'],
                            'aft': ln['accum_after'],
                        },
                    )
            conn.commit()
        return True, '', run_id
    except Exception as e:
        return False, str(e), None


def list_depreciation_runs() -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT RUN_ID, RUN_NO, PERIOD_YYYYMM, RUN_DATE, STATUS, GL_VOUCHER_NO,
               TOTAL_DEP, CREATED_BY, CREATED_AT, POSTED_BY, POSTED_AT
        FROM {DEP_RUN_TABLE}
        ORDER BY PERIOD_YYYYMM DESC, RUN_ID DESC
        """,
        {},
    )
    return [_row_keys(r) for r in rows or []]


def get_depreciation_run(run_id: int) -> Optional[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT RUN_ID, RUN_NO, PERIOD_YYYYMM, RUN_DATE, STATUS, GL_VOUCHER_NO,
               TOTAL_DEP, CREATED_BY, CREATED_AT, POSTED_BY, POSTED_AT
        FROM {DEP_RUN_TABLE}
        WHERE RUN_ID = :id
        """,
        {'id': int(run_id)},
    )
    return _row_keys(rows[0]) if rows else None


def list_depreciation_run_lines(run_id: int) -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT l.LINE_ID, l.RUN_ID, l.ASSET_ID, l.DEP_AMOUNT, l.ACCUM_BEFORE, l.ACCUM_AFTER,
               a.ASSET_NO, a.NAME AS ASSET_NAME, c.CODE AS CATEGORY_CODE,
               c.DEP_EXPENSE_ACCOUNT, c.ACCUM_DEP_ACCOUNT
        FROM {DEP_LINE_TABLE} l
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = l.ASSET_ID
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE l.RUN_ID = :id
        ORDER BY a.ASSET_NO
        """,
        {'id': int(run_id)},
    )
    return [_row_keys(r) for r in rows or []]


def post_depreciation_run(run_id: int, *, user: str = 'web') -> Tuple[bool, str, Optional[str]]:
    ensure_fixed_assets_tables()
    run = get_depreciation_run(int(run_id))
    if not run:
        return False, 'Depreciation run not found.', None
    if str(run.get('status') or '').upper() == RUN_POSTED:
        return False, 'Run already posted.', run.get('gl_voucher_no')
    lines = list_depreciation_run_lines(int(run_id))
    if not lines:
        return False, 'Run has no lines.', None
    period = str(run.get('period_yyyymm') or '')
    run_date = run.get('run_date')
    if hasattr(run_date, 'strftime'):
        vdate = run_date.strftime('%Y-%m-%d')
    else:
        vdate = _period_last_day(period)
    groups: Dict[Tuple[str, str], float] = {}
    for ln in lines:
        key = (
            _norm_gl_account_code(ln.get('dep_expense_account')),
            _norm_gl_account_code(ln.get('accum_dep_account')),
        )
        groups[key] = round(groups.get(key, 0.0) + float(ln.get('dep_amount') or 0), 2)
    gl_lines: List[Dict[str, Any]] = []
    for (exp_ac, accum_ac), amt in sorted(groups.items()):
        if amt <= 0:
            continue
        gl_lines.append({'account_code': exp_ac, 'debit': amt, 'credit': 0, 'remarks': period})
        gl_lines.append({'account_code': accum_ac, 'debit': 0, 'credit': amt, 'remarks': period})
    if len(gl_lines) < 2:
        return False, 'Nothing to post.', None
    ref = str(run.get('run_no') or f'FADEP-{period}')
    narration = f'Fixed asset depreciation — {period}'
    try:
        vno = create_gl_journal_entry(
            vdate,
            ref,
            narration,
            gl_lines,
            created_by=(user or 'web')[:50],
            source='FA_DEP',
        )
        with _get_connection() as conn:
            with conn.cursor() as cur:
                for ln in lines:
                    aid = int(ln.get('asset_id') or 0)
                    accum_after = round(float(ln.get('accum_after') or 0), 2)
                    cost = round(float(get_fa_asset(aid).get('acquisition_cost') or 0), 2)
                    salvage = round(float(get_fa_asset(aid).get('salvage_value') or 0), 2)
                    max_dep = round(cost - salvage, 2)
                    new_status = STATUS_FULLY_DEP if accum_after >= max_dep - 0.01 else STATUS_ACTIVE
                    cur.execute(
                        f"""
                        UPDATE {ASSET_TABLE}
                        SET ACCUM_DEP = :acc, LAST_DEP_YYYYMM = :p, STATUS = :st,
                            UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
                        WHERE ASSET_ID = :id
                        """,
                        {
                            'acc': accum_after,
                            'p': period,
                            'st': new_status,
                            'usr': (user or 'web')[:50],
                            'id': aid,
                        },
                    )
                cur.execute(
                    f"""
                    UPDATE {DEP_RUN_TABLE}
                    SET STATUS = :st, GL_VOUCHER_NO = :vno,
                        POSTED_BY = :usr, POSTED_AT = SYSTIMESTAMP
                    WHERE RUN_ID = :id
                    """,
                    {'st': RUN_POSTED, 'vno': vno, 'usr': (user or 'web')[:50], 'id': int(run_id)},
                )
            conn.commit()
        return True, '', vno
    except Exception as e:
        return False, str(e), None


def get_postable_accounts_for_select(*, include_codes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    extra = {str(c or '').strip() for c in (include_codes or []) if str(c or '').strip()}
    rows = []
    for r in get_all_chart_of_accounts() or []:
        code = str(r.get('code') or '').strip()
        if not code:
            continue
        postable = str(r.get('is_postable') or r.get('IS_POSTABLE') or 'Y').strip().upper()
        status = str(r.get('status') or r.get('STATUS') or 'ACTIVE').strip().upper()
        if code in extra or (postable in ('Y', '1', 'TRUE') and status == 'ACTIVE'):
            rows.append({'code': code, 'name': str(r.get('name') or '').strip()})
    rows.sort(key=lambda x: x['code'])
    return rows


def _next_doc_no(prefix: str, table: str, col: str) -> str:
    year = datetime.now().strftime('%Y')
    pfx = f'{prefix}-{year}-'
    rows = _safe_rows(
        f"SELECT MAX({col}) AS mx FROM {table} WHERE {col} LIKE :pfx || '%'",
        {'pfx': pfx},
    )
    mx = str((rows[0].get('mx') or rows[0].get('MX') or '') if rows else '').strip()
    seq = 1
    if mx.startswith(pfx):
        try:
            seq = int(mx[len(pfx):]) + 1
        except ValueError:
            seq = 1
    return f'{pfx}{seq:04d}'


def list_fa_assets_eligible(*, for_disposal: bool = False, for_transfer: bool = False) -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    clauses = ["NVL(a.POSTED_ACQ, 'N') = 'Y'", "NVL(a.STATUS, 'ACTIVE') <> :disp"]
    params: Dict[str, Any] = {'disp': STATUS_DISPOSED}
    if for_disposal:
        clauses.append(
            f"""NOT EXISTS (
                SELECT 1 FROM {DISPOSAL_TABLE} d
                WHERE d.ASSET_ID = a.ASSET_ID AND d.STATUS = :draft
            )"""
        )
        params['draft'] = DISPOSAL_DRAFT
        clauses.append(
            f"""NOT EXISTS (
                SELECT 1 FROM {SALE_LINE_TABLE} sl
                JOIN {SALE_HDR_TABLE} sh ON sh.SALE_ID = sl.SALE_ID
                WHERE sl.ASSET_ID = a.ASSET_ID AND sh.STATUS = :sale_draft
            )"""
        )
        params['sale_draft'] = SALE_DRAFT
    rows = _safe_rows(
        f"""
        SELECT a.ASSET_ID, a.ASSET_NO, a.NAME, a.CATEGORY_ID, c.CODE AS CATEGORY_CODE,
               c.GAIN_ON_DISPOSAL_ACCOUNT, c.LOSS_ON_DISPOSAL_ACCOUNT,
               a.ACQUISITION_COST, a.ACCUM_DEP,
               (a.ACQUISITION_COST - NVL(a.ACCUM_DEP, 0)) AS NBV,
               a.LOCATION_CODE, a.CUSTODIAN, a.STATUS
        FROM {ASSET_TABLE} a
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE {' AND '.join(clauses)}
        ORDER BY a.ASSET_NO
        """,
        params,
    )
    out = []
    for r in rows or []:
        row = _row_keys(r)
        loc = row.get('location_code')
        if loc is not None:
            row['location_name'] = get_location_master_name_by_code(loc) or ''
        out.append(row)
    return out


def _compute_disposal_gain_loss(nbv: float, proceeds: float) -> float:
    return round(float(proceeds or 0) - float(nbv or 0), 2)


def list_fa_disposals(disposal_type: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    where = ''
    params: Dict[str, Any] = {}
    dtype = str(disposal_type or '').strip().upper()
    if dtype in (DISPOSAL_TYPE_SALE, DISPOSAL_TYPE_SCRAP):
        where = 'WHERE UPPER(NVL(d.DISPOSAL_TYPE, \'\')) = :dtype'
        params['dtype'] = dtype
    rows = _safe_rows(
        f"""
        SELECT d.DISPOSAL_ID, d.DISPOSAL_NO, d.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               d.DISPOSAL_DATE, d.DISPOSAL_TYPE, d.PROCEEDS_AMOUNT, d.NBV, d.GAIN_LOSS_AMOUNT,
               d.STATUS, d.GL_VOUCHER_NO, d.CREATED_BY, d.CREATED_AT, d.POSTED_BY, d.POSTED_AT
        FROM {DISPOSAL_TABLE} d
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = d.ASSET_ID
        {where}
        ORDER BY d.DISPOSAL_ID DESC
        """,
        params,
    )
    return [_row_keys(r) for r in rows or []]


def get_fa_disposal(disposal_id: int) -> Optional[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT d.DISPOSAL_ID, d.DISPOSAL_NO, d.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               c.CODE AS CATEGORY_CODE, c.GAIN_ON_DISPOSAL_ACCOUNT, c.LOSS_ON_DISPOSAL_ACCOUNT,
               c.ASSET_ACCOUNT, c.ACCUM_DEP_ACCOUNT,
               d.DISPOSAL_DATE, d.DISPOSAL_TYPE, d.PROCEEDS_AMOUNT, d.PROCEEDS_ACCOUNT,
               d.PROCEEDS_PARTY_TYPE, d.PROCEEDS_PARTY_CODE,
               d.ACQUISITION_COST, d.ACCUM_DEP, d.NBV, d.GAIN_LOSS_AMOUNT,
               d.STATUS, d.GL_VOUCHER_NO, d.REMARKS,
               d.CREATED_BY, d.CREATED_AT, d.POSTED_BY, d.POSTED_AT
        FROM {DISPOSAL_TABLE} d
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = d.ASSET_ID
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE d.DISPOSAL_ID = :id
        """,
        {'id': int(disposal_id)},
    )
    return _row_keys(rows[0]) if rows else None


def _fetch_fa_disposal_cur(cur, disposal_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(
        f"""
        SELECT d.DISPOSAL_ID, d.DISPOSAL_NO, d.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               c.CODE AS CATEGORY_CODE, c.GAIN_ON_DISPOSAL_ACCOUNT, c.LOSS_ON_DISPOSAL_ACCOUNT,
               c.ASSET_ACCOUNT, c.ACCUM_DEP_ACCOUNT,
               d.DISPOSAL_DATE, d.DISPOSAL_TYPE, d.PROCEEDS_AMOUNT, d.PROCEEDS_ACCOUNT,
               d.PROCEEDS_PARTY_TYPE, d.PROCEEDS_PARTY_CODE,
               d.ACQUISITION_COST, d.ACCUM_DEP, d.NBV, d.GAIN_LOSS_AMOUNT,
               d.STATUS, d.GL_VOUCHER_NO, d.REMARKS,
               d.CREATED_BY, d.CREATED_AT, d.POSTED_BY, d.POSTED_AT
        FROM {DISPOSAL_TABLE} d
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = d.ASSET_ID
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE d.DISPOSAL_ID = :id
        """,
        {'id': int(disposal_id)},
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0].lower() for d in cur.description]
    return _row_keys(dict(zip(cols, row)))


def _post_fa_disposal_tx(conn, cur, disposal_id: int, *, user: str = 'web') -> str:
    disp = _fetch_fa_disposal_cur(cur, int(disposal_id))
    if not disp:
        raise ValueError('Disposal not found.')
    if str(disp.get('status') or '').upper() == DISPOSAL_POSTED:
        raise ValueError('Disposal already posted.')
    asset_id = int(disp.get('asset_id') or 0)
    cur.execute(
        f"SELECT STATUS FROM {ASSET_TABLE} WHERE ASSET_ID = :aid",
        {'aid': asset_id},
    )
    asset_row = cur.fetchone()
    if not asset_row or str(asset_row[0] or '').upper() == STATUS_DISPOSED:
        raise ValueError('Asset is not eligible for disposal.')
    cost = round(float(disp.get('acquisition_cost') or 0), 2)
    accum = round(float(disp.get('accum_dep') or 0), 2)
    gain_loss = round(float(disp.get('gain_loss_amount') or 0), 2)
    asset_ac = _norm_gl_account_code(disp.get('asset_account'))
    accum_ac = _norm_gl_account_code(disp.get('accum_dep_account'))
    gain_ac = _norm_gl_account_code(disp.get('gain_on_disposal_account'))
    loss_ac = _norm_gl_account_code(disp.get('loss_on_disposal_account'))
    proceeds = round(float(disp.get('proceeds_amount') or 0), 2)
    proceeds_ac = _norm_gl_account_code(disp.get('proceeds_account'))
    if gain_loss > 0.005 and not gain_ac:
        raise ValueError('Set gain on disposal account on the asset category before posting.')
    if gain_loss < -0.005 and not loss_ac:
        raise ValueError('Set loss on disposal account on the asset category before posting.')
    ref = str(disp.get('disposal_no') or '')
    asset_no = str(disp.get('asset_no') or '')
    disp_date = disp.get('disposal_date')
    if hasattr(disp_date, 'strftime'):
        vdate = disp_date.strftime('%Y-%m-%d')
    else:
        vdate = str(disp_date or '')[:10]
    gl_lines: List[Dict[str, Any]] = []
    if accum > 0:
        gl_lines.append({'account_code': accum_ac, 'debit': accum, 'credit': 0, 'remarks': asset_no})
    if proceeds > 0 and proceeds_ac:
        pline: Dict[str, Any] = {'account_code': proceeds_ac, 'debit': proceeds, 'credit': 0, 'remarks': asset_no}
        ppt = str(disp.get('proceeds_party_type') or '').strip().upper()
        ppc = str(disp.get('proceeds_party_code') or '').strip()
        if ppt in ('SUPPLIER', 'CUSTOMER') and ppc:
            pline['party_type'] = ppt
            pline['party_code'] = ppc
        gl_lines.append(pline)
    if gain_loss < -0.005 and loss_ac:
        loss_amt = round(abs(gain_loss), 2)
        gl_lines.append({'account_code': loss_ac, 'debit': loss_amt, 'credit': 0, 'remarks': asset_no})
    gl_lines.append({'account_code': asset_ac, 'debit': 0, 'credit': cost, 'remarks': asset_no})
    if gain_loss > 0.005 and gain_ac:
        gl_lines.append({'account_code': gain_ac, 'debit': 0, 'credit': gain_loss, 'remarks': asset_no})
    narration = f"FA disposal — {disp.get('asset_name') or asset_no}"
    vno = create_gl_journal_entry(
        vdate,
        ref,
        narration,
        gl_lines,
        created_by=(user or 'web')[:50],
        source='FA_DIS',
        conn=conn,
        commit=False,
    )
    cur.execute(
        f"""
        UPDATE {DISPOSAL_TABLE}
        SET STATUS = :st, GL_VOUCHER_NO = :vno,
            POSTED_BY = :usr, POSTED_AT = SYSTIMESTAMP
        WHERE DISPOSAL_ID = :id
        """,
        {'st': DISPOSAL_POSTED, 'vno': vno, 'usr': (user or 'web')[:50], 'id': int(disposal_id)},
    )
    cur.execute(
        f"""
        UPDATE {ASSET_TABLE}
        SET STATUS = :st, DISPOSAL_ID = :did, DISPOSED_DATE = TO_DATE(:dd, 'YYYY-MM-DD'),
            UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
        WHERE ASSET_ID = :aid
        """,
        {
            'st': STATUS_DISPOSED,
            'did': int(disposal_id),
            'dd': vdate,
            'usr': (user or 'web')[:50],
            'aid': asset_id,
        },
    )
    return vno


def _persist_fa_disposal_cur(
    cur,
    *,
    disposal_id: Optional[int],
    asset_id: int,
    disp_date: str,
    disp_type: str,
    proceeds: float,
    proceeds_account: Optional[str],
    ppt: Optional[str],
    ppc: Optional[str],
    cost: float,
    accum: float,
    nbv: float,
    gain_loss: float,
    remarks: Optional[str],
    user: str,
) -> int:
    if disposal_id:
        cur.execute(
            f"""
            UPDATE {DISPOSAL_TABLE}
            SET DISPOSAL_DATE = TO_DATE(:dd, 'YYYY-MM-DD'),
                DISPOSAL_TYPE = :dt, PROCEEDS_AMOUNT = :pr,
                PROCEEDS_ACCOUNT = :pa, PROCEEDS_PARTY_TYPE = :ppt, PROCEEDS_PARTY_CODE = :ppc,
                ACQUISITION_COST = :cost, ACCUM_DEP = :acc, NBV = :nbv,
                GAIN_LOSS_AMOUNT = :gl, REMARKS = :rm
            WHERE DISPOSAL_ID = :id
            """,
            {
                'id': int(disposal_id),
                'dd': disp_date,
                'dt': disp_type,
                'pr': proceeds,
                'pa': proceeds_account,
                'ppt': ppt,
                'ppc': ppc,
                'cost': cost,
                'acc': accum,
                'nbv': nbv,
                'gl': gain_loss,
                'rm': (remarks or '')[:500] or None,
            },
        )
        return int(disposal_id)
    cur.execute(f'SELECT {DISPOSAL_SEQ}.NEXTVAL FROM DUAL')
    did = int(cur.fetchone()[0])
    disp_no = _next_doc_no('FADIS', DISPOSAL_TABLE, 'DISPOSAL_NO')
    cur.execute(
        f"""
        INSERT INTO {DISPOSAL_TABLE}
            (DISPOSAL_ID, DISPOSAL_NO, ASSET_ID, DISPOSAL_DATE, DISPOSAL_TYPE,
             PROCEEDS_AMOUNT, PROCEEDS_ACCOUNT, PROCEEDS_PARTY_TYPE, PROCEEDS_PARTY_CODE,
             ACQUISITION_COST, ACCUM_DEP, NBV, GAIN_LOSS_AMOUNT, STATUS, REMARKS, CREATED_BY)
        VALUES
            (:id, :no, :aid, TO_DATE(:dd, 'YYYY-MM-DD'), :dt,
             :pr, :pa, :ppt, :ppc, :cost, :acc, :nbv, :gl, :st, :rm, :usr)
        """,
        {
            'id': did,
            'no': disp_no,
            'aid': int(asset_id),
            'dd': disp_date,
            'dt': disp_type,
            'pr': proceeds,
            'pa': proceeds_account,
            'ppt': ppt,
            'ppc': ppc,
            'cost': cost,
            'acc': accum,
            'nbv': nbv,
            'gl': gain_loss,
            'st': DISPOSAL_DRAFT,
            'rm': (remarks or '')[:500] or None,
            'usr': (user or 'web')[:50],
        },
    )
    return did


def _validate_fa_disposal_inputs(
    *,
    disposal_id: Optional[int],
    asset_id: int,
    disposal_date: str,
    disposal_type: str,
    proceeds_amount: float,
    proceeds_account: Optional[str],
    proceeds_party_type: Optional[str] = None,
    proceeds_party_code: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    asset = get_fa_asset(int(asset_id))
    if not asset:
        return False, 'Asset not found.', None
    if str(asset.get('posted_acq') or 'N').upper() != 'Y':
        return False, 'Acquisition must be posted before disposal.', None
    if str(asset.get('status') or '').upper() == STATUS_DISPOSED:
        return False, 'Asset is already disposed.', None
    disp_type = str(disposal_type or DISPOSAL_TYPE_SALE).strip().upper()
    if disp_type not in (DISPOSAL_TYPE_SALE, DISPOSAL_TYPE_SCRAP):
        return False, 'Disposal type must be SALE or SCRAP.', None
    disp_date = str(disposal_date or '').strip()[:10]
    if len(disp_date) < 10:
        return False, 'Disposal date is required.', None
    try:
        proceeds = round(float(proceeds_amount or 0), 2)
    except (TypeError, ValueError):
        return False, 'Invalid proceeds amount.', None
    if proceeds < 0:
        return False, 'Proceeds cannot be negative.', None
    if disp_type == DISPOSAL_TYPE_SALE and proceeds <= 0:
        return False, 'Proceeds are required for a sale disposal.', None
    proceeds_account = _norm_gl_account_code(proceeds_account) if proceeds_account else None
    ppt, ppc = _normalize_credit_party(proceeds_party_type, proceeds_party_code)
    if proceeds > 0:
        if not proceeds_account:
            return False, 'Proceeds account is required when proceeds > 0.', None
        err = _validate_account(proceeds_account, 'Proceeds account')
        if err:
            return False, err, None
    cost = round(float(asset.get('acquisition_cost') or 0), 2)
    accum = round(float(asset.get('accum_dep') or 0), 2)
    nbv = round(cost - accum, 2)
    gain_loss = _compute_disposal_gain_loss(nbv, proceeds)
    if disposal_id:
        existing = get_fa_disposal(int(disposal_id))
        if not existing:
            return False, 'Disposal not found.', None
        if str(existing.get('status') or '').upper() == DISPOSAL_POSTED:
            return False, 'Posted disposal cannot be edited.', None
        if int(existing.get('asset_id') or 0) != int(asset_id):
            return False, 'Asset cannot be changed on an existing disposal.', None
    else:
        draft = _safe_rows(
            f"""
            SELECT DISPOSAL_ID FROM {DISPOSAL_TABLE}
            WHERE ASSET_ID = :aid AND STATUS = :st
            """,
            {'aid': int(asset_id), 'st': DISPOSAL_DRAFT},
        )
        if draft:
            return False, 'A draft disposal already exists for this asset.', None
    return True, '', {
        'asset_id': int(asset_id),
        'disp_date': disp_date,
        'disp_type': disp_type,
        'proceeds': proceeds,
        'proceeds_account': proceeds_account,
        'ppt': ppt,
        'ppc': ppc,
        'cost': cost,
        'accum': accum,
        'nbv': nbv,
        'gain_loss': gain_loss,
        'gain_ac': _norm_gl_account_code(asset.get('gain_on_disposal_account')),
        'loss_ac': _norm_gl_account_code(asset.get('loss_on_disposal_account')),
    }


def save_fa_disposal(
    *,
    disposal_id: Optional[int],
    asset_id: int,
    disposal_date: str,
    disposal_type: str,
    proceeds_amount: float,
    proceeds_account: Optional[str],
    proceeds_party_type: Optional[str] = None,
    proceeds_party_code: Optional[str] = None,
    remarks: Optional[str] = None,
    user: str = 'web',
) -> Tuple[bool, str, Optional[int]]:
    ensure_fixed_assets_tables()
    ok, err, fields = _validate_fa_disposal_inputs(
        disposal_id=disposal_id,
        asset_id=asset_id,
        disposal_date=disposal_date,
        disposal_type=disposal_type,
        proceeds_amount=proceeds_amount,
        proceeds_account=proceeds_account,
        proceeds_party_type=proceeds_party_type,
        proceeds_party_code=proceeds_party_code,
    )
    if not ok or not fields:
        return False, err, None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                did = _persist_fa_disposal_cur(
                    cur,
                    disposal_id=disposal_id,
                    asset_id=fields['asset_id'],
                    disp_date=fields['disp_date'],
                    disp_type=fields['disp_type'],
                    proceeds=fields['proceeds'],
                    proceeds_account=fields['proceeds_account'],
                    ppt=fields['ppt'],
                    ppc=fields['ppc'],
                    cost=fields['cost'],
                    accum=fields['accum'],
                    nbv=fields['nbv'],
                    gain_loss=fields['gain_loss'],
                    remarks=remarks,
                    user=user,
                )
            conn.commit()
        return True, '', did
    except Exception as e:
        return False, str(e), None


def save_fa_disposal_and_post(
    *,
    disposal_id: Optional[int],
    asset_id: int,
    disposal_date: str,
    disposal_type: str,
    proceeds_amount: float,
    proceeds_account: Optional[str],
    proceeds_party_type: Optional[str] = None,
    proceeds_party_code: Optional[str] = None,
    remarks: Optional[str] = None,
    user: str = 'web',
) -> Tuple[bool, str, Optional[int], Optional[str]]:
    ensure_fixed_assets_tables()
    ok, err, fields = _validate_fa_disposal_inputs(
        disposal_id=disposal_id,
        asset_id=asset_id,
        disposal_date=disposal_date,
        disposal_type=disposal_type,
        proceeds_amount=proceeds_amount,
        proceeds_account=proceeds_account,
        proceeds_party_type=proceeds_party_type,
        proceeds_party_code=proceeds_party_code,
    )
    if not ok or not fields:
        return False, err, None, None
    gain_loss = fields['gain_loss']
    if gain_loss > 0.005 and not fields['gain_ac']:
        return False, 'Set gain on disposal account on the asset category before posting.', None, None
    if gain_loss < -0.005 and not fields['loss_ac']:
        return False, 'Set loss on disposal account on the asset category before posting.', None, None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                did = _persist_fa_disposal_cur(
                    cur,
                    disposal_id=disposal_id,
                    asset_id=fields['asset_id'],
                    disp_date=fields['disp_date'],
                    disp_type=fields['disp_type'],
                    proceeds=fields['proceeds'],
                    proceeds_account=fields['proceeds_account'],
                    ppt=fields['ppt'],
                    ppc=fields['ppc'],
                    cost=fields['cost'],
                    accum=fields['accum'],
                    nbv=fields['nbv'],
                    gain_loss=fields['gain_loss'],
                    remarks=remarks,
                    user=user,
                )
                vno = _post_fa_disposal_tx(conn, cur, did, user=user)
            conn.commit()
        return True, '', did, vno
    except Exception as e:
        return False, str(e), None, None


def post_fa_disposal(disposal_id: int, *, user: str = 'web') -> Tuple[bool, str, Optional[str]]:
    ensure_fixed_assets_tables()
    disp = get_fa_disposal(int(disposal_id))
    if not disp:
        return False, 'Disposal not found.', None
    if str(disp.get('status') or '').upper() == DISPOSAL_POSTED:
        return False, 'Disposal already posted.', disp.get('gl_voucher_no')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                vno = _post_fa_disposal_tx(conn, cur, int(disposal_id), user=user)
            conn.commit()
        return True, '', vno
    except Exception as e:
        return False, str(e), None


def list_fa_sales() -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT h.SALE_ID, h.SALE_NO, h.SALE_DATE, h.TOTAL_PROCEEDS, h.TOTAL_NBV, h.TOTAL_GAIN_LOSS,
               h.STATUS, h.GL_VOUCHER_NO, h.CREATED_BY, h.CREATED_AT, h.POSTED_BY, h.POSTED_AT,
               (SELECT COUNT(*) FROM {SALE_LINE_TABLE} l WHERE l.SALE_ID = h.SALE_ID) AS LINE_COUNT
        FROM {SALE_HDR_TABLE} h
        ORDER BY h.SALE_ID DESC
        """,
        {},
    )
    return [_row_keys(r) for r in rows or []]


def get_fa_sale(sale_id: int) -> Optional[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT h.SALE_ID, h.SALE_NO, h.SALE_DATE, h.PROCEEDS_ACCOUNT,
               h.PROCEEDS_PARTY_TYPE, h.PROCEEDS_PARTY_CODE,
               h.TOTAL_PROCEEDS, h.TOTAL_COST, h.TOTAL_ACCUM, h.TOTAL_NBV, h.TOTAL_GAIN_LOSS,
               h.STATUS, h.GL_VOUCHER_NO, h.REMARKS,
               h.CREATED_BY, h.CREATED_AT, h.POSTED_BY, h.POSTED_AT
        FROM {SALE_HDR_TABLE} h
        WHERE h.SALE_ID = :id
        """,
        {'id': int(sale_id)},
    )
    if not rows:
        return None
    hdr = _row_keys(rows[0])
    lines = _safe_rows(
        f"""
        SELECT l.LINE_ID, l.SALE_ID, l.LINE_NO, l.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               c.CODE AS CATEGORY_CODE, c.ASSET_ACCOUNT, c.ACCUM_DEP_ACCOUNT,
               c.GAIN_ON_DISPOSAL_ACCOUNT, c.LOSS_ON_DISPOSAL_ACCOUNT,
               l.PROCEEDS_AMOUNT, l.ACQUISITION_COST, l.ACCUM_DEP, l.NBV, l.GAIN_LOSS_AMOUNT
        FROM {SALE_LINE_TABLE} l
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = l.ASSET_ID
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE l.SALE_ID = :id
        ORDER BY l.LINE_NO, l.LINE_ID
        """,
        {'id': int(sale_id)},
    )
    hdr['lines'] = [_row_keys(r) for r in lines or []]
    return hdr


def _prepare_fa_sale_save(
    *,
    sale_id: Optional[int],
    sale_date: str,
    proceeds_account: Optional[str],
    proceeds_party_type: Optional[str] = None,
    proceeds_party_code: Optional[str] = None,
    lines: Optional[List[Dict[str, Any]]] = None,
    for_post: bool = False,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    sdate = str(sale_date or '').strip()[:10]
    if len(sdate) < 10:
        return False, 'Sale date is required.', None
    raw_lines = lines or []
    if not raw_lines:
        return False, 'Add at least one asset line.', None
    proceeds_account = _norm_gl_account_code(proceeds_account) if proceeds_account else None
    ppt, ppc = _normalize_credit_party(proceeds_party_type, proceeds_party_code)
    if not proceeds_account:
        return False, 'Proceeds account is required.', None
    err = _validate_account(proceeds_account, 'Proceeds account')
    if err:
        return False, err, None

    built: List[Dict[str, Any]] = []
    seen: set = set()
    total_proceeds = 0.0
    total_cost = 0.0
    total_accum = 0.0
    total_nbv = 0.0
    for idx, ln in enumerate(raw_lines, start=1):
        try:
            aid = int(ln.get('asset_id') or 0)
        except (TypeError, ValueError):
            return False, f'Line {idx}: invalid asset.', None
        if aid <= 0:
            return False, f'Line {idx}: select an asset.', None
        if aid in seen:
            return False, f'Line {idx}: duplicate asset on this sale.', None
        seen.add(aid)
        try:
            proceeds = round(float(ln.get('proceeds_amount') or 0), 2)
        except (TypeError, ValueError):
            return False, f'Line {idx}: invalid proceeds.', None
        if proceeds <= 0:
            return False, f'Line {idx}: proceeds must be greater than zero.', None
        asset = get_fa_asset(aid)
        if not asset:
            return False, f'Line {idx}: asset not found.', None
        if str(asset.get('posted_acq') or 'N').upper() != 'Y':
            return False, f'Line {idx}: acquisition must be posted ({asset.get("asset_no")}).', None
        if str(asset.get('status') or '').upper() == STATUS_DISPOSED:
            return False, f'Line {idx}: asset already disposed ({asset.get("asset_no")}).', None
        if sale_id:
            busy = _safe_rows(
                f"""
                SELECT sh.SALE_NO
                FROM {SALE_LINE_TABLE} sl
                JOIN {SALE_HDR_TABLE} sh ON sh.SALE_ID = sl.SALE_ID
                WHERE sl.ASSET_ID = :aid AND sh.STATUS = :st
                  AND sh.SALE_ID <> :sid
                  AND ROWNUM = 1
                """,
                {'aid': aid, 'st': SALE_DRAFT, 'sid': int(sale_id)},
            )
        else:
            busy = _safe_rows(
                f"""
                SELECT sh.SALE_NO
                FROM {SALE_LINE_TABLE} sl
                JOIN {SALE_HDR_TABLE} sh ON sh.SALE_ID = sl.SALE_ID
                WHERE sl.ASSET_ID = :aid AND sh.STATUS = :st
                  AND ROWNUM = 1
                """,
                {'aid': aid, 'st': SALE_DRAFT},
            )
        if busy:
            sno = (busy[0] or {}).get('sale_no') or (busy[0] or {}).get('SALE_NO') or ''
            return False, f'Line {idx}: asset already on draft sale {sno}.', None
        cost = round(float(asset.get('acquisition_cost') or 0), 2)
        accum = round(float(asset.get('accum_dep') or 0), 2)
        nbv = round(cost - accum, 2)
        gain_loss = _compute_disposal_gain_loss(nbv, proceeds)
        if for_post:
            asset_no = str(asset.get('asset_no') or '')
            gain_ac = _norm_gl_account_code(asset.get('gain_on_disposal_account'))
            loss_ac = _norm_gl_account_code(asset.get('loss_on_disposal_account'))
            asset_ac = _norm_gl_account_code(asset.get('asset_account'))
            accum_ac = _norm_gl_account_code(asset.get('accum_dep_account'))
            if gain_loss > 0.005 and not gain_ac:
                return False, f'Set gain account on category for {asset_no}.', None
            if gain_loss < -0.005 and not loss_ac:
                return False, f'Set loss account on category for {asset_no}.', None
            if not asset_ac:
                return False, f'Missing asset GL account for {asset_no}.', None
            if accum > 0 and not accum_ac:
                return False, f'Missing accum. dep. account for {asset_no}.', None
        built.append({
            'asset_id': aid,
            'proceeds_amount': proceeds,
            'acquisition_cost': cost,
            'accum_dep': accum,
            'nbv': nbv,
            'gain_loss_amount': gain_loss,
        })
        total_proceeds += proceeds
        total_cost += cost
        total_accum += accum
        total_nbv += nbv
    if sale_id:
        existing = get_fa_sale(int(sale_id))
        if not existing:
            return False, 'Sale not found.', None
        if str(existing.get('status') or '').upper() == SALE_POSTED:
            return False, 'Posted sale cannot be edited.', None
    return True, '', {
        'sdate': sdate,
        'proceeds_account': proceeds_account,
        'ppt': ppt,
        'ppc': ppc,
        'built': built,
        'total_proceeds': round(total_proceeds, 2),
        'total_cost': round(total_cost, 2),
        'total_accum': round(total_accum, 2),
        'total_nbv': round(total_nbv, 2),
        'total_gain_loss': round(total_proceeds - total_nbv, 2),
    }


def _persist_fa_sale_cur(
    cur,
    *,
    sale_id: Optional[int],
    prep: Dict[str, Any],
    remarks: Optional[str],
    user: str,
) -> int:
    if sale_id:
        sid = int(sale_id)
        cur.execute(
            f"""
            UPDATE {SALE_HDR_TABLE}
            SET SALE_DATE = TO_DATE(:sd, 'YYYY-MM-DD'),
                PROCEEDS_ACCOUNT = :pa, PROCEEDS_PARTY_TYPE = :ppt, PROCEEDS_PARTY_CODE = :ppc,
                TOTAL_PROCEEDS = :tp, TOTAL_COST = :tc, TOTAL_ACCUM = :ta,
                TOTAL_NBV = :tn, TOTAL_GAIN_LOSS = :tg, REMARKS = :rm
            WHERE SALE_ID = :id
            """,
            {
                'id': sid,
                'sd': prep['sdate'],
                'pa': prep['proceeds_account'],
                'ppt': prep['ppt'],
                'ppc': prep['ppc'],
                'tp': prep['total_proceeds'],
                'tc': prep['total_cost'],
                'ta': prep['total_accum'],
                'tn': prep['total_nbv'],
                'tg': prep['total_gain_loss'],
                'rm': (remarks or '')[:500] or None,
            },
        )
        cur.execute(f'DELETE FROM {SALE_LINE_TABLE} WHERE SALE_ID = :id', {'id': sid})
    else:
        cur.execute(f'SELECT {SALE_HDR_SEQ}.NEXTVAL FROM DUAL')
        sid = int(cur.fetchone()[0])
        sale_no = _next_doc_no('FASALE', SALE_HDR_TABLE, 'SALE_NO')
        cur.execute(
            f"""
            INSERT INTO {SALE_HDR_TABLE}
                (SALE_ID, SALE_NO, SALE_DATE, PROCEEDS_ACCOUNT, PROCEEDS_PARTY_TYPE, PROCEEDS_PARTY_CODE,
                 TOTAL_PROCEEDS, TOTAL_COST, TOTAL_ACCUM, TOTAL_NBV, TOTAL_GAIN_LOSS,
                 STATUS, REMARKS, CREATED_BY)
            VALUES
                (:id, :no, TO_DATE(:sd, 'YYYY-MM-DD'), :pa, :ppt, :ppc,
                 :tp, :tc, :ta, :tn, :tg, :st, :rm, :usr)
            """,
            {
                'id': sid,
                'no': sale_no,
                'sd': prep['sdate'],
                'pa': prep['proceeds_account'],
                'ppt': prep['ppt'],
                'ppc': prep['ppc'],
                'tp': prep['total_proceeds'],
                'tc': prep['total_cost'],
                'ta': prep['total_accum'],
                'tn': prep['total_nbv'],
                'tg': prep['total_gain_loss'],
                'st': SALE_DRAFT,
                'rm': (remarks or '')[:500] or None,
                'usr': (user or 'web')[:50],
            },
        )
    for i, ln in enumerate(prep['built'], start=1):
        cur.execute(f'SELECT {SALE_LINE_SEQ}.NEXTVAL FROM DUAL')
        lid = int(cur.fetchone()[0])
        cur.execute(
            f"""
            INSERT INTO {SALE_LINE_TABLE}
                (LINE_ID, SALE_ID, LINE_NO, ASSET_ID, PROCEEDS_AMOUNT,
                 ACQUISITION_COST, ACCUM_DEP, NBV, GAIN_LOSS_AMOUNT)
            VALUES
                (:lid, :sid, :lno, :aid, :pr, :cost, :acc, :nbv, :gl)
            """,
            {
                'lid': lid,
                'sid': sid,
                'lno': i,
                'aid': ln['asset_id'],
                'pr': ln['proceeds_amount'],
                'cost': ln['acquisition_cost'],
                'acc': ln['accum_dep'],
                'nbv': ln['nbv'],
                'gl': ln['gain_loss_amount'],
            },
        )
    return sid


def save_fa_sale(
    *,
    sale_id: Optional[int],
    sale_date: str,
    proceeds_account: Optional[str],
    proceeds_party_type: Optional[str] = None,
    proceeds_party_code: Optional[str] = None,
    remarks: Optional[str] = None,
    lines: Optional[List[Dict[str, Any]]] = None,
    user: str = 'web',
) -> Tuple[bool, str, Optional[int]]:
    """Save a multi-asset sale draft (header + lines)."""
    ensure_fixed_assets_tables()
    ok, err, prep = _prepare_fa_sale_save(
        sale_id=sale_id,
        sale_date=sale_date,
        proceeds_account=proceeds_account,
        proceeds_party_type=proceeds_party_type,
        proceeds_party_code=proceeds_party_code,
        lines=lines,
    )
    if not ok or not prep:
        return False, err, None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                sid = _persist_fa_sale_cur(
                    cur,
                    sale_id=sale_id,
                    prep=prep,
                    remarks=remarks,
                    user=user,
                )
            conn.commit()
        return True, '', sid
    except Exception as e:
        return False, str(e), None


def _fetch_fa_sale_cur(cur, sale_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(
        f"""
        SELECT h.SALE_ID, h.SALE_NO, h.SALE_DATE, h.PROCEEDS_ACCOUNT,
               h.PROCEEDS_PARTY_TYPE, h.PROCEEDS_PARTY_CODE,
               h.TOTAL_PROCEEDS, h.TOTAL_COST, h.TOTAL_ACCUM, h.TOTAL_NBV, h.TOTAL_GAIN_LOSS,
               h.STATUS, h.GL_VOUCHER_NO, h.REMARKS,
               h.CREATED_BY, h.CREATED_AT, h.POSTED_BY, h.POSTED_AT
        FROM {SALE_HDR_TABLE} h
        WHERE h.SALE_ID = :id
        """,
        {'id': int(sale_id)},
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0].lower() for d in cur.description]
    hdr = _row_keys(dict(zip(cols, row)))
    cur.execute(
        f"""
        SELECT l.LINE_ID, l.SALE_ID, l.LINE_NO, l.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               c.CODE AS CATEGORY_CODE, c.ASSET_ACCOUNT, c.ACCUM_DEP_ACCOUNT,
               c.GAIN_ON_DISPOSAL_ACCOUNT, c.LOSS_ON_DISPOSAL_ACCOUNT,
               l.PROCEEDS_AMOUNT, l.ACQUISITION_COST, l.ACCUM_DEP, l.NBV, l.GAIN_LOSS_AMOUNT
        FROM {SALE_LINE_TABLE} l
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = l.ASSET_ID
        JOIN {CATEGORY_TABLE} c ON c.CATEGORY_ID = a.CATEGORY_ID
        WHERE l.SALE_ID = :id
        ORDER BY l.LINE_NO, l.LINE_ID
        """,
        {'id': int(sale_id)},
    )
    line_rows = cur.fetchall()
    line_cols = [d[0].lower() for d in cur.description]
    hdr['lines'] = [_row_keys(dict(zip(line_cols, lr))) for lr in line_rows or []]
    return hdr


def _post_fa_sale_tx(conn, cur, sale_id: int, *, user: str = 'web') -> str:
    sale = _fetch_fa_sale_cur(cur, int(sale_id))
    if not sale:
        raise ValueError('Sale not found.')
    if str(sale.get('status') or '').upper() == SALE_POSTED:
        raise ValueError('Sale already posted.')
    lines = sale.get('lines') or []
    if not lines:
        raise ValueError('Sale has no asset lines.')
    proceeds_ac = _norm_gl_account_code(sale.get('proceeds_account'))
    if not proceeds_ac:
        raise ValueError('Proceeds account is required.')
    sdate = sale.get('sale_date')
    if hasattr(sdate, 'strftime'):
        vdate = sdate.strftime('%Y-%m-%d')
    else:
        vdate = str(sdate or '')[:10]
    ref = str(sale.get('sale_no') or '')
    gl_lines: List[Dict[str, Any]] = []
    for ln in lines:
        asset_id = int(ln.get('asset_id') or 0)
        cur.execute(
            f"SELECT STATUS FROM {ASSET_TABLE} WHERE ASSET_ID = :aid",
            {'aid': asset_id},
        )
        asset_row = cur.fetchone()
        if not asset_row or str(asset_row[0] or '').upper() == STATUS_DISPOSED:
            raise ValueError(f'Asset {ln.get("asset_no") or asset_id} is not eligible.')
        cost = round(float(ln.get('acquisition_cost') or 0), 2)
        accum = round(float(ln.get('accum_dep') or 0), 2)
        proceeds = round(float(ln.get('proceeds_amount') or 0), 2)
        gain_loss = round(float(ln.get('gain_loss_amount') or 0), 2)
        asset_ac = _norm_gl_account_code(ln.get('asset_account'))
        accum_ac = _norm_gl_account_code(ln.get('accum_dep_account'))
        gain_ac = _norm_gl_account_code(ln.get('gain_on_disposal_account'))
        loss_ac = _norm_gl_account_code(ln.get('loss_on_disposal_account'))
        asset_no = str(ln.get('asset_no') or '')
        if gain_loss > 0.005 and not gain_ac:
            raise ValueError(f'Set gain account on category for {asset_no}.')
        if gain_loss < -0.005 and not loss_ac:
            raise ValueError(f'Set loss account on category for {asset_no}.')
        if not asset_ac:
            raise ValueError(f'Missing asset GL account for {asset_no}.')
        if accum > 0 and not accum_ac:
            raise ValueError(f'Missing accum. dep. account for {asset_no}.')
        if accum > 0:
            gl_lines.append({'account_code': accum_ac, 'debit': accum, 'credit': 0, 'remarks': asset_no})
        if proceeds > 0:
            pline: Dict[str, Any] = {
                'account_code': proceeds_ac, 'debit': proceeds, 'credit': 0, 'remarks': asset_no,
            }
            ppt = str(sale.get('proceeds_party_type') or '').strip().upper()
            ppc = str(sale.get('proceeds_party_code') or '').strip()
            if ppt in ('SUPPLIER', 'CUSTOMER') and ppc:
                pline['party_type'] = ppt
                pline['party_code'] = ppc
            gl_lines.append(pline)
        if gain_loss < -0.005 and loss_ac:
            gl_lines.append({
                'account_code': loss_ac, 'debit': round(abs(gain_loss), 2), 'credit': 0, 'remarks': asset_no,
            })
        gl_lines.append({'account_code': asset_ac, 'debit': 0, 'credit': cost, 'remarks': asset_no})
        if gain_loss > 0.005 and gain_ac:
            gl_lines.append({
                'account_code': gain_ac, 'debit': 0, 'credit': gain_loss, 'remarks': asset_no,
            })
    narration = f"FA asset sale — {ref} ({len(lines)} asset(s))"
    vno = create_gl_journal_entry(
        vdate,
        ref,
        narration,
        gl_lines,
        created_by=(user or 'web')[:50],
        source='FA_SALE',
        conn=conn,
        commit=False,
    )
    cur.execute(
        f"""
        UPDATE {SALE_HDR_TABLE}
        SET STATUS = :st, GL_VOUCHER_NO = :vno,
            POSTED_BY = :usr, POSTED_AT = SYSTIMESTAMP
        WHERE SALE_ID = :id
        """,
        {'st': SALE_POSTED, 'vno': vno, 'usr': (user or 'web')[:50], 'id': int(sale_id)},
    )
    for ln in lines:
        cur.execute(
            f"""
            UPDATE {ASSET_TABLE}
            SET STATUS = :st, SALE_ID = :sid, DISPOSED_DATE = TO_DATE(:dd, 'YYYY-MM-DD'),
                UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
            WHERE ASSET_ID = :aid
            """,
            {
                'st': STATUS_DISPOSED,
                'sid': int(sale_id),
                'dd': vdate,
                'usr': (user or 'web')[:50],
                'aid': int(ln.get('asset_id') or 0),
            },
        )
    return vno


def save_fa_sale_and_post(
    *,
    sale_id: Optional[int],
    sale_date: str,
    proceeds_account: Optional[str],
    proceeds_party_type: Optional[str] = None,
    proceeds_party_code: Optional[str] = None,
    remarks: Optional[str] = None,
    lines: Optional[List[Dict[str, Any]]] = None,
    user: str = 'web',
) -> Tuple[bool, str, Optional[int], Optional[str]]:
    ensure_fixed_assets_tables()
    ok, err, prep = _prepare_fa_sale_save(
        sale_id=sale_id,
        sale_date=sale_date,
        proceeds_account=proceeds_account,
        proceeds_party_type=proceeds_party_type,
        proceeds_party_code=proceeds_party_code,
        lines=lines,
        for_post=True,
    )
    if not ok or not prep:
        return False, err, None, None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                sid = _persist_fa_sale_cur(
                    cur,
                    sale_id=sale_id,
                    prep=prep,
                    remarks=remarks,
                    user=user,
                )
                vno = _post_fa_sale_tx(conn, cur, sid, user=user)
            conn.commit()
        return True, '', sid, vno
    except Exception as e:
        return False, str(e), None, None


def post_fa_sale(sale_id: int, *, user: str = 'web') -> Tuple[bool, str, Optional[str]]:
    ensure_fixed_assets_tables()
    sale = get_fa_sale(int(sale_id))
    if not sale:
        return False, 'Sale not found.', None
    if str(sale.get('status') or '').upper() == SALE_POSTED:
        return False, 'Sale already posted.', sale.get('gl_voucher_no')
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                vno = _post_fa_sale_tx(conn, cur, int(sale_id), user=user)
            conn.commit()
        return True, '', vno
    except Exception as e:
        return False, str(e), None


def list_fa_transfers() -> List[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT t.TRANSFER_ID, t.TRANSFER_NO, t.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               t.TRANSFER_DATE, t.FROM_LOCATION_CODE, t.TO_LOCATION_CODE,
               t.FROM_CUSTODIAN, t.TO_CUSTODIAN, t.REMARKS, t.STATUS,
               t.CREATED_BY, t.CREATED_AT
        FROM {TRANSFER_TABLE} t
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = t.ASSET_ID
        ORDER BY t.TRANSFER_ID DESC
        """,
        {},
    )
    out = []
    for r in rows or []:
        row = _row_keys(r)
        for key in ('from_location_code', 'to_location_code'):
            code = row.get(key)
            if code is not None:
                row[key.replace('_code', '_name')] = get_location_master_name_by_code(code) or ''
        out.append(row)
    return out


def get_fa_transfer(transfer_id: int) -> Optional[Dict[str, Any]]:
    ensure_fixed_assets_tables()
    rows = _safe_rows(
        f"""
        SELECT t.TRANSFER_ID, t.TRANSFER_NO, t.ASSET_ID, a.ASSET_NO, a.NAME AS ASSET_NAME,
               t.TRANSFER_DATE, t.FROM_LOCATION_CODE, t.TO_LOCATION_CODE,
               t.FROM_CUSTODIAN, t.TO_CUSTODIAN, t.REMARKS, t.STATUS,
               t.CREATED_BY, t.CREATED_AT
        FROM {TRANSFER_TABLE} t
        JOIN {ASSET_TABLE} a ON a.ASSET_ID = t.ASSET_ID
        WHERE t.TRANSFER_ID = :id
        """,
        {'id': int(transfer_id)},
    )
    if not rows:
        return None
    row = _row_keys(rows[0])
    for key in ('from_location_code', 'to_location_code'):
        code = row.get(key)
        if code is not None:
            row[key.replace('_code', '_name')] = get_location_master_name_by_code(code) or ''
    return row


def create_fa_transfer(
    *,
    asset_id: int,
    transfer_date: str,
    to_location_code: Optional[int],
    to_custodian: Optional[str],
    remarks: Optional[str] = None,
    user: str = 'web',
) -> Tuple[bool, str, Optional[int]]:
    ensure_fixed_assets_tables()
    asset = get_fa_asset(int(asset_id))
    if not asset:
        return False, 'Asset not found.', None
    if str(asset.get('posted_acq') or 'N').upper() != 'Y':
        return False, 'Acquisition must be posted before transfer.', None
    if str(asset.get('status') or '').upper() == STATUS_DISPOSED:
        return False, 'Disposed assets cannot be transferred.', None
    trf_date = str(transfer_date or '').strip()[:10]
    if len(trf_date) < 10:
        return False, 'Transfer date is required.', None
    from_loc = asset.get('location_code')
    from_cust = str(asset.get('custodian') or '').strip() or None
    try:
        to_loc = int(to_location_code) if to_location_code not in (None, '', 0) else None
    except (TypeError, ValueError):
        to_loc = None
    to_cust = str(to_custodian or '').strip()[:100] or None
    if from_loc == to_loc and (from_cust or '') == (to_cust or ''):
        return False, 'Change location or custodian before transferring.', None
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT {TRANSFER_SEQ}.NEXTVAL FROM DUAL')
                tid = cur.fetchone()[0]
                trf_no = _next_doc_no('FATRF', TRANSFER_TABLE, 'TRANSFER_NO')
                cur.execute(
                    f"""
                    INSERT INTO {TRANSFER_TABLE}
                        (TRANSFER_ID, TRANSFER_NO, ASSET_ID, TRANSFER_DATE,
                         FROM_LOCATION_CODE, TO_LOCATION_CODE, FROM_CUSTODIAN, TO_CUSTODIAN,
                         REMARKS, STATUS, CREATED_BY)
                    VALUES
                        (:id, :no, :aid, TO_DATE(:td, 'YYYY-MM-DD'),
                         :fl, :tl, :fc, :tc, :rm, :st, :usr)
                    """,
                    {
                        'id': tid,
                        'no': trf_no,
                        'aid': int(asset_id),
                        'td': trf_date,
                        'fl': from_loc,
                        'tl': to_loc,
                        'fc': from_cust,
                        'tc': to_cust,
                        'rm': (remarks or '')[:500] or None,
                        'st': TRANSFER_POSTED,
                        'usr': (user or 'web')[:50],
                    },
                )
                cur.execute(
                    f"""
                    UPDATE {ASSET_TABLE}
                    SET LOCATION_CODE = :loc, CUSTODIAN = :cust,
                        UPDATED_BY = :usr, UPDATED_AT = SYSTIMESTAMP
                    WHERE ASSET_ID = :aid
                    """,
                    {
                        'loc': to_loc,
                        'cust': to_cust,
                        'usr': (user or 'web')[:50],
                        'aid': int(asset_id),
                    },
                )
            conn.commit()
        return True, '', tid
    except Exception as e:
        return False, str(e), None
