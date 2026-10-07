"""Varchar document numbers for Store Transfer, Stock Adjustment, and Repacking."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_DOCNO_VARCHAR_LEN = 30


def _billno_varchar_requested() -> bool:
    from db import _billno_varchar_requested as _fn
    return _fn()


def _billno_numeric_part(val: Any) -> int:
    from db import billno_numeric_part as _fn
    return _fn(val)


@dataclass
class InventoryDocNoSpec:
    env_key: str
    doc_type: str
    default_prefix: str
    hdr_table_aliases: List[str]
    dtl_table_aliases: List[str]
    no_col_names: List[str]
    pk_specs: List[Tuple[str, str, str, List[str]]]
    _ensured: bool = field(default=False, repr=False)

    def varchar_requested(self) -> bool:
        raw = str(os.getenv(self.env_key, '') or '').strip().lower()
        if raw:
            return raw in ('1', 'true', 'yes', 'y', 'on')
        return _billno_varchar_requested()

    def _hdr_table(self) -> Optional[str]:
        from db import _detect_table
        return _detect_table(self.hdr_table_aliases)

    def _no_col(self, tbl: Optional[str] = None) -> Optional[str]:
        from db import _detect_column
        t = tbl or self._hdr_table()
        if not t:
            return None
        return _detect_column(t, self.no_col_names)

    def _column_type(self, tbl: str, col: str) -> str:
        from db import _get_table_column_types_with_key
        try:
            types = _get_table_column_types_with_key(tbl)
            return str(types.get(str(col).upper()) or '').upper()
        except Exception:
            return ''

    def uses_varchar_storage(self) -> bool:
        tbl = self._hdr_table()
        col = self._no_col(tbl)
        if not tbl or not col:
            return False
        dt = self._column_type(tbl, col)
        return dt in ('VARCHAR2', 'VARCHAR', 'CHAR', 'NVARCHAR2', 'NCHAR')

    def normalize(self, val: Any) -> str:
        return str(val or '').strip()[:_DOCNO_VARCHAR_LEN]

    def coerce(self, val: Any) -> Any:
        if self.uses_varchar_storage():
            s = self.normalize(val)
            return s if s else ''
        try:
            if val is None or str(val).strip() == '':
                return 0
            n = _billno_numeric_part(val)
            return int(n) if n > 0 else int(val)
        except (TypeError, ValueError):
            return 0

    def parse_from_request(self, val: Any) -> Any:
        if val is None or str(val).strip() == '':
            return self.coerce(0)
        return self.coerce(val)

    def is_valid(self, val: Any) -> bool:
        if self.uses_varchar_storage():
            s = self.normalize(val)
            if not s:
                return False
            if s.lstrip('-').isdigit():
                try:
                    return int(s) != 0
                except (TypeError, ValueError):
                    pass
            return True
        try:
            return int(val) > 0
        except (TypeError, ValueError):
            return _billno_numeric_part(val) > 0

    def format_display(self, val: Any, *, location_code: Optional[int] = None, reset_no: int = 1) -> str:
        s = self.normalize(val)
        if not s:
            return ''
        n = _billno_numeric_part(val)
        if s and not s.isdigit() and n > 0:
            return s[:_DOCNO_VARCHAR_LEN]
        if n <= 0:
            return s
        try:
            from addons.document_numbering.document_numbering_db import format_document_no, get_document_series_by_type
            series = get_document_series_by_type(
                self.doc_type,
                location_code=int(location_code) if location_code is not None else None,
                reset_no=int(reset_no or 1),
            )
            if series:
                return str(format_document_no(series, n) or '')[:_DOCNO_VARCHAR_LEN]
        except Exception:
            pass
        return f'{self.default_prefix}{str(n).zfill(6)}'

    def storage_from_series(self, numeric_no: int, formatted_no: str) -> Any:
        if self.uses_varchar_storage():
            fmt = str(formatted_no or '').strip()
            if fmt:
                return fmt[:_DOCNO_VARCHAR_LEN]
            return str(int(numeric_no))[:_DOCNO_VARCHAR_LEN]
        return int(numeric_no)

    def match_sql(self, col_sql: str, *, bind_prefix: str = 'doc') -> str:
        p_str = f'{bind_prefix}_str'
        p_num = f'{bind_prefix}_num'
        num_suffix = f"NVL(TO_NUMBER(REGEXP_SUBSTR(TO_CHAR({col_sql}), '[0-9]+$')), 0)"
        return (
            f"(TO_CHAR({col_sql}) = :{p_str} "
            f"OR (:{p_num} > 0 AND {num_suffix} = :{p_num}))"
        )

    def match_params(self, val: Any, *, bind_prefix: str = 'doc') -> Dict[str, Any]:
        s = self.normalize(val)
        n = _billno_numeric_part(val)
        p_str = f'{bind_prefix}_str'
        p_num = f'{bind_prefix}_num'
        if not s and n > 0:
            s = str(n)
        return {p_str: s, p_num: int(n) if n > 0 else -1}

    def numeric_ref(self, val: Any) -> int:
        return _billno_numeric_part(val)

    def _needs_migration(self, tbl: str) -> bool:
        from db import _detect_table, _table_exists
        if not _table_exists(tbl):
            return False
        col = self._no_col(tbl)
        if not col:
            return False
        dt = self._column_type(tbl, col)
        return dt not in ('VARCHAR2', 'VARCHAR', 'CHAR', 'NVARCHAR2', 'NCHAR')

    def ensure_varchar_columns(self) -> bool:
        if not self.varchar_requested():
            return self.uses_varchar_storage()
        if self._ensured and not any(self._needs_migration(tbl) for tbl, *_ in self.pk_specs):
            return self.uses_varchar_storage()
        self._ensured = True
        from db import _get_connection, _table_exists, _TABLE_COLUMNS_CACHE, _oracle_migrate_docno_column_to_varchar
        ok_any = self.uses_varchar_storage()
        try:
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    for tbl, col, pk, pk_cols in self.pk_specs:
                        if not _table_exists(tbl):
                            continue
                        try:
                            if _oracle_migrate_docno_column_to_varchar(
                                cur, tbl, col, pk_name=pk, pk_columns=pk_cols,
                                varchar_len=_DOCNO_VARCHAR_LEN,
                            ):
                                ok_any = True
                        except Exception as ex:
                            print(f'[WARN ensure_{self.env_key}] {tbl}.{col}: {ex}')
                conn.commit()
        except Exception as ex:
            print(f'[WARN ensure_{self.env_key}] {ex}')
        for tbl, *_ in self.pk_specs:
            _TABLE_COLUMNS_CACHE.pop(str(tbl).upper(), None)
        return self.uses_varchar_storage()

    def _max_existing_cur(self, cur: Any, location_code: Optional[int], reset_no: int = 1) -> int:
        from db import _detect_column
        tbl = self._hdr_table()
        if not tbl:
            return 0
        no_col = self._no_col(tbl)
        loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO', 'resetno'])
        if not no_col:
            return 0
        where = ['1=1']
        params: Dict[str, Any] = {}
        if loc_col and location_code is not None:
            where.append(f'{loc_col} = :loc')
            params['loc'] = int(location_code)
        if reset_col:
            where.append(f'{reset_col} = :rn')
            params['rn'] = int(reset_no or 1)
        try:
            cur.execute(f'SELECT {no_col} FROM {tbl} WHERE {" AND ".join(where)}', params)
            mx = 0
            for row in cur.fetchall() or []:
                mx = max(mx, _billno_numeric_part(row[0]))
            return mx
        except Exception:
            return 0

    def _series_enabled(self) -> bool:
        try:
            from addons.document_numbering.document_numbering_db import get_document_series_by_type
            row = get_document_series_by_type(self.doc_type, location_code=None, reset_no=1)
            return bool(row and str(row.get('is_active') or 'Y').strip().upper() == 'Y')
        except Exception:
            return False

    def get_next_no_cur(self, cur: Any, location_code: int, *, reset_no: int = 1, user: str = 'system') -> Any:
        self.ensure_varchar_columns()
        from addons.document_numbering.document_numbering_db import allocate_document_no_cur
        floor_no = self._max_existing_cur(cur, location_code, reset_no=int(reset_no or 1))
        next_no, formatted, err = allocate_document_no_cur(
            cur,
            self.doc_type,
            location_code=location_code,
            reset_no=int(reset_no or 1),
            user=user,
            floor_no=floor_no if floor_no else None,
        )
        if not next_no:
            raise RuntimeError(err or f'Could not allocate {self.doc_type} number from document series.')
        return self.storage_from_series(int(next_no), str(formatted or ''))

    def next_no(self, location_code: Optional[int] = None, *, reset_no: int = 1, user: str = 'system') -> Any:
        self.ensure_varchar_columns()
        loc = int(location_code if location_code is not None else 1)
        if self._series_enabled():
            from db import _get_connection
            with _get_connection() as conn:
                with conn.cursor() as cur:
                    return self.get_next_no_cur(cur, loc, reset_no=reset_no, user=user)
        tbl = self._hdr_table()
        if not tbl:
            return self.coerce(1)
        from db import _detect_column, _fetch_rows
        no_col = self._no_col(tbl) or self.no_col_names[0]
        loc_col = _detect_column(tbl, ['LOCATIONCODE', 'LOCATION_CODE', 'locationcode'])
        reset_col = _detect_column(tbl, ['RESETNO', 'RESET_NO', 'resetno'])
        where = '1=1'
        params: Dict[str, Any] = {}
        if loc_col:
            where += f' AND {loc_col} = :loc'
            params['loc'] = loc
        if reset_col:
            where += f' AND {reset_col} = :rn'
            params['rn'] = int(reset_no or 1)
        q = f'SELECT NVL(MAX({no_col}), 0) + 1 AS n FROM {tbl} WHERE {where}'
        try:
            _, rows = _fetch_rows(q, params)
            n = int(rows[0]['n']) if rows else 1
        except Exception:
            n = 1
        if self.uses_varchar_storage():
            return self.format_display(n, location_code=loc, reset_no=reset_no)
        return n

    def peek_next_no(self, location_code: int, *, reset_no: int = 1) -> Any:
        self.ensure_varchar_columns()
        if not self._series_enabled():
            return None
        try:
            from db import _get_connection
            from addons.document_numbering.document_numbering_db import (
                format_document_no,
                get_document_series_by_type,
                peek_document_no_int,
            )
            floor = 0
            try:
                with _get_connection() as conn:
                    with conn.cursor() as cur:
                        floor = self._max_existing_cur(cur, location_code, reset_no=int(reset_no or 1))
            except Exception:
                pass
            n = peek_document_no_int(
                self.doc_type,
                location_code=location_code,
                reset_no=int(reset_no or 1),
                floor_no=floor if floor else None,
            )
            if not n:
                return None
            series = get_document_series_by_type(self.doc_type, location_code=location_code, reset_no=int(reset_no or 1))
            if not series:
                return self.storage_from_series(int(n), str(n))
            formatted = format_document_no(series, int(n))
            return self.storage_from_series(int(n), formatted)
        except Exception:
            return None


TRANSFERNO_SPEC = InventoryDocNoSpec(
    env_key='TRANSFERNO_AS_VARCHAR',
    doc_type='STOCK_TRANSFER',
    default_prefix='ST-',
    hdr_table_aliases=['STKTRFHDR', 'stktrfhdr'],
    dtl_table_aliases=['STKTRFDTL', 'stktrfdtl'],
    no_col_names=['TRANSFERNO', 'transferno'],
    pk_specs=[
        ('STKTRFHDR', 'TRANSFERNO', 'PK_STKTRFHDR', ['LOCATIONCODE', 'RESETNO', 'TRANSFERNO']),
        ('STKTRFDTL', 'TRANSFERNO', 'PK_STKTRFDTL', ['LOCATIONCODE', 'RESETNO', 'TRANSFERNO', 'SLNO']),
    ],
)

ADJNO_SPEC = InventoryDocNoSpec(
    env_key='ADJNO_AS_VARCHAR',
    doc_type='STOCK_ADJUSTMENT',
    default_prefix='SA-',
    hdr_table_aliases=['STKADJHDR', 'stockadjustmenthdr', 'ADJUSTMENTHDR'],
    dtl_table_aliases=['STKADJDTL', 'stockadjustmentdtl', 'ADJUSTMENTDTL'],
    no_col_names=['ADJNO', 'ADJUSTNO', 'DOCNO'],
    pk_specs=[
        ('STKADJHDR', 'ADJNO', 'PK_STKADJHDR', ['LOCATIONCODE', 'ADJNO']),
        ('STKADJDTL', 'ADJNO', 'PK_STKADJDTL', ['LOCATIONCODE', 'ADJNO', 'SLNO']),
    ],
)

REPACKNO_SPEC = InventoryDocNoSpec(
    env_key='REPACKNO_AS_VARCHAR',
    doc_type='REPACK',
    default_prefix='RP-',
    hdr_table_aliases=['REPACKHDR', 'repackhdr'],
    dtl_table_aliases=['REPACKDTL', 'repackdtl'],
    no_col_names=['REPACKNO', 'repackno', 'DOCNO'],
    pk_specs=[
        ('REPACKHDR', 'REPACKNO', 'PK_REPACKHDR', ['LOCATIONCODE', 'REPACKNO']),
        ('REPACKDTL', 'REPACKNO', 'PK_REPACKDTL', ['LOCATIONCODE', 'REPACKNO', 'SLNO']),
    ],
)

# Convenience aliases
ensure_transferno_varchar_columns = TRANSFERNO_SPEC.ensure_varchar_columns
ensure_adjno_varchar_columns = ADJNO_SPEC.ensure_varchar_columns
ensure_repackno_varchar_columns = REPACKNO_SPEC.ensure_varchar_columns
coerce_transferno = TRANSFERNO_SPEC.coerce
coerce_adjno = ADJNO_SPEC.coerce
coerce_repackno = REPACKNO_SPEC.coerce
parse_transferno_from_request = TRANSFERNO_SPEC.parse_from_request
parse_adjno_from_request = ADJNO_SPEC.parse_from_request
parse_repackno_from_request = REPACKNO_SPEC.parse_from_request
transferno_is_valid = TRANSFERNO_SPEC.is_valid
adjno_is_valid = ADJNO_SPEC.is_valid
repackno_is_valid = REPACKNO_SPEC.is_valid
format_transferno_display = TRANSFERNO_SPEC.format_display
format_adjno_display = ADJNO_SPEC.format_display
format_repackno_display = REPACKNO_SPEC.format_display
transferno_match_sql = TRANSFERNO_SPEC.match_sql
adjno_match_sql = ADJNO_SPEC.match_sql
repackno_match_sql = REPACKNO_SPEC.match_sql
transferno_match_params = TRANSFERNO_SPEC.match_params
adjno_match_params = ADJNO_SPEC.match_params
repackno_match_params = REPACKNO_SPEC.match_params
