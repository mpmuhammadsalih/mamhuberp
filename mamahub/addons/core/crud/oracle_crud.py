"""Reusable Oracle CRUD base for app-owned tables (DDL via ``db.ensure_*``, data via this layer).

Subclass with ``TABLE_NAME``, ``PRIMARY_KEY``, ``FIELD_SPECS``, and ``USE_AUTH``. Then call
``YourModel.list_rows()``, ``get()``, ``create()``, ``upsert()``, ``delete()`` from routes or ``db.py``.

This is **not** an ORM: it builds bound SQL from an allowlisted column map. Add new tables by
subclassing — see ``company_profile_crud.CompanyProfile``.
"""
from __future__ import annotations
import re
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Sequence, Tuple
FieldSpec = Tuple[str, str, Optional[int]]

def _assert_sql_ident(name: str, kind: str='identifier') -> str:
    s = (name or '').strip()
    if not s or not re.match('^[A-Za-z_][A-Za-z0-9_]*$', s):
        raise ValueError(f'Invalid Oracle {kind}: {name!r}')
    return s.upper()

class OracleCrud:
    """Base class for table-scoped CRUD. Subclass and set class attributes."""
    TABLE_NAME: ClassVar[str] = ''
    PRIMARY_KEY: ClassVar[str] = 'ID'
    USE_AUTH: ClassVar[bool] = False
    FIELD_SPECS: ClassVar[Tuple[FieldSpec, ...]] = ()

    @classmethod
    def _table(cls) -> str:
        return _assert_sql_ident(cls.TABLE_NAME, 'table')

    @classmethod
    def _pk(cls) -> str:
        return _assert_sql_ident(cls.PRIMARY_KEY, 'column')

    @classmethod
    def _field_map(cls) -> Dict[str, Tuple[str, Optional[int]]]:
        m: Dict[str, Tuple[str, Optional[int]]] = {}
        for py, ora, ml in cls.FIELD_SPECS:
            m[py] = (_assert_sql_ident(ora, 'column'), ml)
        return m

    @classmethod
    def _binds_from_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        fm = cls._field_map()
        params: Dict[str, Any] = {}
        for py, (ora_u, ml) in fm.items():
            raw = data.get(py)
            if raw is None:
                s = ''
            else:
                s = str(raw).strip()
            if ml is not None:
                s = s[:int(ml)]
            params[py] = s
        return params

    @classmethod
    def _optional_blob(cls, data: Dict[str, Any], key: str, max_len: int) -> Optional[str]:
        raw = data.get(key)
        if raw is None:
            return None
        t = str(raw).strip()[:max_len]
        return t or None

    @classmethod
    def ensure_table(cls) -> None:
        """Override and call the matching ``db.ensure_*_table`` for this entity."""
        raise NotImplementedError(f'define ensure_table() on {cls.__name__}')

    @classmethod
    def _connection_cm(cls):
        if cls.USE_AUTH:
            from db import _get_connection_auth
            return _get_connection_auth()
        from db import _get_connection
        return _get_connection()

    @classmethod
    def normalize_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """Default: coerce NULL to '' for display (override if needed)."""
        out = dict(row)
        for k, v in out.items():
            if v is None and str(k).lower() != 'updated_at':
                out[k] = ''
        return out

    @classmethod
    def list_rows(cls, columns: str='*', order_by: Optional[str]=None, extra_where: str='', extra_binds: Optional[Dict[str, Any]]=None) -> List[Dict[str, Any]]:
        """SELECT rows. ``columns`` must be * or a verified fragment (subclasses can wrap safe lists)."""
        cls.ensure_table()
        if columns != '*':
            raise ValueError("Pass columns='*' or override list_rows for custom projections.")
        q = f'SELECT * FROM {cls._table()}'
        binds: Dict[str, Any] = dict(extra_binds or {})
        if extra_where.strip():
            q += f' WHERE {extra_where}'
        q += f' ORDER BY {order_by or cls._pk()}'
        from db import _fetch_rows
        try:
            _, rows = _fetch_rows(q, binds)
        except Exception:
            return []
        return [cls.normalize_row(dict(r)) for r in rows or []]

    @classmethod
    def get(cls, pk: Any) -> Dict[str, Any]:
        cls.ensure_table()
        pk_col = cls._pk().lower()
        q = f'SELECT * FROM {cls._table()} WHERE {cls._pk()} = :pk'
        from db import _fetch_rows
        try:
            _, rows = _fetch_rows(q, {'pk': pk})
        except Exception:
            return {}
        if not rows:
            return {}
        return cls.normalize_row(dict(rows[0]))

    @classmethod
    def upsert(cls, pk: Any, data: Dict[str, Any]) -> None:
        """UPDATE by PK; if no row updated, INSERT with that PK."""
        cls.ensure_table()
        params = cls._bind_payload(data)
        params['cid'] = pk
        from db import _get_connection, _get_connection_auth, _TABLE_EXISTS_CACHE
        upd = cls._update_sql()
        ins = cls._insert_sql()
        cm = _get_connection_auth if cls.USE_AUTH else _get_connection
        with cm() as conn:
            with conn.cursor() as cur:
                cur.execute(upd, params)
                if getattr(cur, 'rowcount', None) == 0:
                    cur.execute(ins, params)
            conn.commit()
        _TABLE_EXISTS_CACHE.pop(cls.TABLE_NAME.upper(), None)

    @classmethod
    def _bind_payload(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Override if some fields are non-string (e.g. logos). Default uses _binds_from_data + PK."""
        return cls._binds_from_data(data)

    @classmethod
    def _update_sql(cls) -> str:
        sets = ', '.join((f"{_assert_sql_ident(ora, 'column')} = :{py}" for py, ora, _ml in cls.FIELD_SPECS))
        extra = ''
        if getattr(cls, 'UPDATED_AT_SYSDATE', False):
            extra = ', UPDATED_AT = SYSDATE'
        return f'UPDATE {cls._table()} SET {sets}{extra} WHERE {cls._pk()} = :cid'

    @classmethod
    def _insert_sql(cls) -> str:
        cols = [cls._pk()] + [_assert_sql_ident(ora, 'column') for py, ora, _ml in cls.FIELD_SPECS]
        binds = [':cid'] + [f':{py}' for py, _ora, _ml in cls.FIELD_SPECS]
        extra_col = ''
        extra_val = ''
        if getattr(cls, 'UPDATED_AT_SYSDATE', False):
            extra_col = ', UPDATED_AT'
            extra_val = ', SYSDATE'
        csql = ', '.join(cols)
        bsql = ', '.join(binds)
        return f'INSERT INTO {cls._table()} ({csql}{extra_col}) VALUES ({bsql}{extra_val})'

class OracleCrudManualId(OracleCrud):
    """CRUD for tables that allocate ``PRIMARY_KEY`` via ``MAX(id)+1`` (no sequence)."""

    @classmethod
    def create(cls, data: Dict[str, Any]) -> Any:
        cls.ensure_table()
        params = cls._bind_payload(data)
        from db import _get_connection, _get_connection_auth, _TABLE_EXISTS_CACHE
        cm = _get_connection_auth if cls.USE_AUTH else _get_connection
        with cm() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT NVL(MAX({cls._pk()}), 0) + 1 FROM {cls._table()}')
                new_id = int((cur.fetchone() or [1])[0] or 1)
                params['cid'] = new_id
                cur.execute(cls._insert_sql(), params)
            conn.commit()
        _TABLE_EXISTS_CACHE.pop(cls.TABLE_NAME.upper(), None)
        return new_id

    @classmethod
    def delete(cls, pk: Any) -> int:
        """DELETE row. Returns rowcount (0 if none)."""
        cls.ensure_table()
        from db import _get_connection, _get_connection_auth, _TABLE_EXISTS_CACHE
        cm = _get_connection_auth if cls.USE_AUTH else _get_connection
        with cm() as conn:
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM {cls._table()} WHERE {cls._pk()} = :pk', {'pk': pk})
                n = int(cur.rowcount or 0)
            conn.commit()
        _TABLE_EXISTS_CACHE.pop(cls.TABLE_NAME.upper(), None)
        return n
