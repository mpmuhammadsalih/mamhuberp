"""Lazy DDL bootstrap for MamaHub ecommerce tables missing from tenant DBs."""
from __future__ import annotations

import re

import oracledb

from db import _TABLE_EXISTS_CACHE, _get_connection, _table_exists

_MEDIA_TABLE = 'MH_MEDIA'
_MEDIA_SCHEMA_READY = False
_CMS_SCHEMA_READY = False


def _invalidate_media_table_cache() -> None:
    _TABLE_EXISTS_CACHE.pop(_MEDIA_TABLE, None)


def _mark_media_table_ready() -> None:
    _TABLE_EXISTS_CACHE[_MEDIA_TABLE] = True


def _sequence_exists(cur, name: str) -> bool:
    cur.execute(
        'SELECT COUNT(*) FROM user_sequences WHERE sequence_name = :name',
        {'name': name.upper()},
    )
    return int((cur.fetchone() or [0])[0]) > 0


def _index_exists(cur, name: str) -> bool:
    cur.execute(
        'SELECT COUNT(*) FROM user_indexes WHERE index_name = :name',
        {'name': name.upper()},
    )
    return int((cur.fetchone() or [0])[0]) > 0


def _exec_ddl(cur, sql: str) -> None:
    try:
        cur.execute(sql)
    except oracledb.DatabaseError as exc:
        code = None
        match = re.search(r'ORA-(\d+)', str(exc))
        if match:
            code = int(match.group(1))
        if code in {955, 2260, 2261, 2264, 1408, 1418}:
            return
        raise


_SINGLETON_MEDIA_PLACEMENTS = (
    'storefront_logo',
    'product_detail',
    'showcase_banner',
    'hero_bg',
    'age_group',
    'category',
    'brand',
    'explore_category',
)


def ensure_media_schema() -> None:
    """Create MH_MEDIA table and sequence when absent."""
    global _MEDIA_SCHEMA_READY
    if _MEDIA_SCHEMA_READY:
        return
    if _table_exists(_MEDIA_TABLE):
        _mark_media_table_ready()
        _ensure_media_column_sizes()
        _ensure_media_indexes()
        _MEDIA_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_MEDIA_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_MEDIA_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )

            if not _table_exists(_MEDIA_TABLE):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_MEDIA (
                        MEDIA_ID                NUMBER          NOT NULL,
                        PLACEMENT               VARCHAR2(50)    NOT NULL,
                        REF_KEY                 VARCHAR2(120),
                        TITLE                   VARCHAR2(200),
                        SUBTITLE                VARCHAR2(2000 CHAR),
                        IMAGE_URL               VARCHAR2(500)   NOT NULL,
                        LINK_URL                VARCHAR2(500),
                        ALT_TEXT                VARCHAR2(500 CHAR),
                        SORT_ORDER              NUMBER          DEFAULT 0 NOT NULL,
                        META_JSON               VARCHAR2(4000 CHAR),
                        IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        MODIFIED_AT             TIMESTAMP,
                        CONSTRAINT PK_MH_MEDIA PRIMARY KEY (MEDIA_ID),
                        CONSTRAINT CK_MH_MEDIA_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                    )
                    """,
                )

        conn.commit()

    _ensure_media_column_sizes()
    _ensure_media_indexes()
    _mark_media_table_ready()
    _MEDIA_SCHEMA_READY = True


def _ensure_media_indexes() -> None:
    """Allow multiple gallery rows per product; keep singleton placements unique."""
    if not _table_exists(_MEDIA_TABLE):
        return
    singletons = ', '.join(f"'{name}'" for name in _SINGLETON_MEDIA_PLACEMENTS)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if _index_exists(cur, 'UQ_MH_MEDIA_PLACEMENT_REF'):
                _exec_ddl(cur, 'DROP INDEX UQ_MH_MEDIA_PLACEMENT_REF')
            if not _index_exists(cur, 'UQ_MH_MEDIA_SINGLE_SLOT'):
                _exec_ddl(
                    cur,
                    f"""
                    CREATE UNIQUE INDEX UQ_MH_MEDIA_SINGLE_SLOT ON MH_MEDIA (
                        CASE
                            WHEN PLACEMENT IN ({singletons})
                            THEN PLACEMENT || CHR(1) || NVL(REF_KEY, ' ')
                            ELSE NULL
                        END
                    )
                    """,
                )
        conn.commit()


def _ensure_media_column_sizes() -> None:
    """Widen MH_MEDIA text columns on existing tenant databases."""
    if not _table_exists(_MEDIA_TABLE):
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            _exec_ddl(cur, 'ALTER TABLE MH_MEDIA MODIFY (SUBTITLE VARCHAR2(2000 CHAR))')
            _exec_ddl(cur, 'ALTER TABLE MH_MEDIA MODIFY (ALT_TEXT VARCHAR2(500 CHAR))')
            _exec_ddl(cur, 'ALTER TABLE MH_MEDIA MODIFY (META_JSON VARCHAR2(4000 CHAR))')
            if not _column_exists(cur, _MEDIA_TABLE, 'TITLE_AR'):
                _exec_ddl(cur, 'ALTER TABLE MH_MEDIA ADD (TITLE_AR VARCHAR2(200 CHAR))')
            if not _column_exists(cur, _MEDIA_TABLE, 'SUBTITLE_AR'):
                _exec_ddl(cur, 'ALTER TABLE MH_MEDIA ADD (SUBTITLE_AR VARCHAR2(2000 CHAR))')
        conn.commit()


_CMS_TABLE = 'MH_CMS_PAGE'


def _invalidate_cms_table_cache() -> None:
    _TABLE_EXISTS_CACHE.pop(_CMS_TABLE, None)


def _mark_cms_table_ready() -> None:
    _TABLE_EXISTS_CACHE[_CMS_TABLE] = True


def ensure_cms_schema() -> None:
    """Create MH_CMS_PAGE table and sequence when absent."""
    global _CMS_SCHEMA_READY
    if _CMS_SCHEMA_READY:
        return
    if _table_exists(_CMS_TABLE):
        _mark_cms_table_ready()
        _ensure_cms_meta_json_column()
        _ensure_contact_inquiry_schema()
        _CMS_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_CMS_PAGE_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_CMS_PAGE_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )

            if not _table_exists(_CMS_TABLE):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_CMS_PAGE (
                        CMS_PAGE_ID             NUMBER          NOT NULL,
                        PAGE_CODE               VARCHAR2(80)    NOT NULL,
                        PAGE_TITLE              VARCHAR2(200)   NOT NULL,
                        SLUG                    VARCHAR2(120)   NOT NULL,
                        PAGE_TYPE               VARCHAR2(40)    DEFAULT 'STATIC' NOT NULL,
                        CONTENT_HTML            CLOB,
                        META_DESCRIPTION        VARCHAR2(500),
                        IS_PUBLISHED            NUMBER(1)       DEFAULT 1 NOT NULL,
                        SORT_ORDER              NUMBER          DEFAULT 0 NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        MODIFIED_AT             TIMESTAMP,
                        META_JSON               CLOB,
                        CONSTRAINT PK_MH_CMS_PAGE PRIMARY KEY (CMS_PAGE_ID),
                        CONSTRAINT UQ_MH_CMS_PAGE_CODE UNIQUE (PAGE_CODE),
                        CONSTRAINT UQ_MH_CMS_PAGE_SLUG UNIQUE (SLUG),
                        CONSTRAINT CK_MH_CMS_PUBLISHED CHECK (IS_PUBLISHED IN (0, 1))
                    )
                    """,
                )

        conn.commit()

    _mark_cms_table_ready()
    _ensure_cms_meta_json_column()
    _ensure_contact_inquiry_schema()
    _CMS_SCHEMA_READY = True


def _column_exists(cur, table: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) FROM user_tab_columns
        WHERE table_name = :table_name AND column_name = :column_name
        """,
        {'table_name': table.upper(), 'column_name': column_name.upper()},
    )
    return int((cur.fetchone() or [0])[0]) > 0


def _ensure_cms_meta_json_column() -> None:
    if not _table_exists(_CMS_TABLE):
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _column_exists(cur, _CMS_TABLE, 'META_JSON'):
                _exec_ddl(cur, 'ALTER TABLE MH_CMS_PAGE ADD (META_JSON CLOB)')
        conn.commit()


def _ensure_contact_inquiry_schema() -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_CONTACT_INQUIRY_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_CONTACT_INQUIRY_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )
            if not _table_exists('MH_CONTACT_INQUIRY'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_CONTACT_INQUIRY (
                        INQUIRY_ID              NUMBER          NOT NULL,
                        FULL_NAME               VARCHAR2(200)   NOT NULL,
                        EMAIL                   VARCHAR2(200)   NOT NULL,
                        SUBJECT                 VARCHAR2(200),
                        MESSAGE_BODY            VARCHAR2(4000)  NOT NULL,
                        STATUS                  VARCHAR2(20)    DEFAULT 'NEW' NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_CONTACT_INQUIRY PRIMARY KEY (INQUIRY_ID)
                    )
                    """,
                )
        conn.commit()
