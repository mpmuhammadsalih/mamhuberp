"""Lazy DDL bootstrap for MamaHub storefront tables missing from tenant DBs."""
from __future__ import annotations

import re

import oracledb

from db import _TABLE_EXISTS_CACHE, _get_connection, _schema_cache_key, _table_exists


_CART_TABLES = ('MH_CART', 'MH_CART_ITEM', 'MH_CART_COUPON')

_DEFAULT_AGE_GROUPS = (
    ('0_12M', '0-12 months', '0-12-months', 0, 12, 1),
    ('1_2Y', '1-2 years', '1-2-years', 13, 24, 2),
    ('3_5Y', '3-5 years', '3-5-years', 25, 60, 3),
    ('6_8Y', '6-8 years', '6-8-years', 61, 96, 4),
    ('9_12Y', '9-12 years', '9-12-years', 97, 144, 5),
    ('13_PLUS', '13+ years', '13-plus-years', 145, None, 6),
)

_CART_SCHEMA_READY = False
_AGE_GROUP_SCHEMA_READY = False
_APP_USER_SCHEMA_READY = False
_ADDRESS_SCHEMA_READY = False
_ORDER_SCHEMA_READY = False
_PASSWORD_RESET_SCHEMA_READY = False
_PROMOTION_SCHEMA_READY = False


def _invalidate_cart_table_cache() -> None:
    for key in _CART_TABLES:
        _TABLE_EXISTS_CACHE.pop(key, None)


def _mark_cart_tables_ready() -> None:
    for key in ('MH_CART', 'MH_CART_ITEM'):
        _TABLE_EXISTS_CACHE[key] = True


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
        if code in {955, 2260, 2261, 2264, 1408, 1430}:
            return
        raise


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) FROM user_tab_columns
        WHERE table_name = :table_name AND column_name = :column_name
        """,
        {'table_name': table.upper(), 'column_name': column.upper()},
    )
    return int((cur.fetchone() or [0])[0]) > 0


def ensure_cart_schema() -> None:
    """Create MH_CART / MH_CART_ITEM sequences and tables when absent."""
    global _CART_SCHEMA_READY
    if _CART_SCHEMA_READY:
        return
    if _table_exists('MH_CART') and _table_exists('MH_CART_ITEM'):
        _mark_cart_tables_ready()
        _CART_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for seq in (
                'SEQ_MH_CART_ID',
                'SEQ_MH_CART_ITEM_ID',
                'SEQ_MH_CART_COUPON_ID',
            ):
                if not _sequence_exists(cur, seq):
                    _exec_ddl(
                        cur,
                        f'CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                    )

            if not _table_exists('MH_CART'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_CART (
                        CART_ID                 NUMBER          NOT NULL,
                        USER_ID                 NUMBER,
                        GUEST_TOKEN             VARCHAR2(64),
                        LOCATION_CODE           NUMBER          NOT NULL,
                        CART_STATUS             VARCHAR2(30)    DEFAULT 'ACTIVE' NOT NULL,
                        CURRENCY_CODE           VARCHAR2(3)     DEFAULT 'QAR' NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_BY              NUMBER,
                        MODIFIED_AT             TIMESTAMP,
                        MODIFIED_BY             NUMBER,
                        CONSTRAINT PK_MH_CART PRIMARY KEY (CART_ID),
                        CONSTRAINT CK_MH_CART_OWNER CHECK (USER_ID IS NOT NULL OR GUEST_TOKEN IS NOT NULL),
                        CONSTRAINT CK_MH_CART_STATUS CHECK (CART_STATUS IN ('ACTIVE', 'MERGED', 'CHECKOUT', 'ABANDONED'))
                    )
                    """,
                )

            if not _table_exists('MH_CART_ITEM'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_CART_ITEM (
                        CART_ITEM_ID            NUMBER          NOT NULL,
                        CART_ID                 NUMBER          NOT NULL,
                        LOCATION_CODE           NUMBER          NOT NULL,
                        ITEM_CODE               NUMBER          NOT NULL,
                        QUANTITY                NUMBER(12,3)    DEFAULT 1 NOT NULL,
                        UNIT_PRICE              NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        LINE_STATUS             VARCHAR2(30)    DEFAULT 'ACTIVE' NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_BY              NUMBER,
                        MODIFIED_AT             TIMESTAMP,
                        MODIFIED_BY             NUMBER,
                        CONSTRAINT PK_MH_CART_ITEM PRIMARY KEY (CART_ITEM_ID),
                        CONSTRAINT FK_MH_CART_ITEM_CART FOREIGN KEY (CART_ID) REFERENCES MH_CART (CART_ID),
                        CONSTRAINT CK_MH_CART_ITEM_QTY CHECK (QUANTITY > 0),
                        CONSTRAINT CK_MH_CART_ITEM_STATUS CHECK (LINE_STATUS IN ('ACTIVE', 'SAVED'))
                    )
                    """,
                )

            if not _table_exists('MH_CART_COUPON'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_CART_COUPON (
                        CART_COUPON_ID          NUMBER          NOT NULL,
                        CART_ID                 NUMBER          NOT NULL,
                        COUPON_CODE             VARCHAR2(50)    NOT NULL,
                        DISCOUNT_AMOUNT         NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        APPLIED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_CART_COUPON PRIMARY KEY (CART_COUPON_ID),
                        CONSTRAINT FK_MH_CART_COUPON_CART FOREIGN KEY (CART_ID) REFERENCES MH_CART (CART_ID),
                        CONSTRAINT UQ_MH_CART_COUPON UNIQUE (CART_ID, COUPON_CODE)
                    )
                    """,
                )

            for index_name, ddl in (
                (
                    'IX_MH_CART_USER',
                    'CREATE INDEX IX_MH_CART_USER ON MH_CART (USER_ID, CART_STATUS)',
                ),
                (
                    'IX_MH_CART_GUEST',
                    'CREATE INDEX IX_MH_CART_GUEST ON MH_CART (GUEST_TOKEN, CART_STATUS)',
                ),
                (
                    'IX_MH_CART_ITEM_CART',
                    'CREATE INDEX IX_MH_CART_ITEM_CART ON MH_CART_ITEM (CART_ID, LINE_STATUS)',
                ),
            ):
                if not _index_exists(cur, index_name):
                    _exec_ddl(cur, ddl)

        conn.commit()

    _mark_cart_tables_ready()
    _CART_SCHEMA_READY = True


_CART_PARENT_COL_READY = False


def ensure_cart_item_parent_column() -> None:
    """Link add-on cart lines to the product they were chosen for."""
    global _CART_PARENT_COL_READY
    if _CART_PARENT_COL_READY:
        return
    if not _table_exists('MH_CART_ITEM'):
        return
    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _column_exists(cur, 'MH_CART_ITEM', 'PARENT_ITEM_CODE'):
                _exec_ddl(cur, 'ALTER TABLE MH_CART_ITEM ADD (PARENT_ITEM_CODE NUMBER)')
        conn.commit()
    _CART_PARENT_COL_READY = True


def _invalidate_age_group_cache() -> None:
    _TABLE_EXISTS_CACHE.pop('MH_AGE_GROUP', None)


def _mark_age_group_ready() -> None:
    _TABLE_EXISTS_CACHE['MH_AGE_GROUP'] = True


def _seed_age_groups(cur) -> None:
    cur.execute('SELECT COUNT(*) FROM MH_AGE_GROUP')
    if int((cur.fetchone() or [0])[0]) > 0:
        return
    for code, name, slug, min_m, max_m, sort_order in _DEFAULT_AGE_GROUPS:
        cur.execute(
            """
            INSERT INTO MH_AGE_GROUP (
                AGE_GROUP_ID, AGE_GROUP_CODE, AGE_GROUP_NAME, SLUG,
                MIN_AGE_MONTHS, MAX_AGE_MONTHS, SORT_ORDER, IS_ACTIVE
            ) VALUES (
                SEQ_AGE_GROUP_ID.NEXTVAL, :code, :name, :slug,
                :min_m, :max_m, :sort_order, 1
            )
            """,
            {
                'code': code,
                'name': name,
                'slug': slug,
                'min_m': min_m,
                'max_m': max_m,
                'sort_order': sort_order,
            },
        )


def ensure_age_group_schema() -> None:
    """Create MH_AGE_GROUP and seed default rows when absent."""
    global _AGE_GROUP_SCHEMA_READY
    if _AGE_GROUP_SCHEMA_READY:
        return
    if _table_exists('MH_AGE_GROUP'):
        with _get_connection() as conn:
            with conn.cursor() as cur:
                _seed_age_groups(cur)
            conn.commit()
        _mark_age_group_ready()
        _AGE_GROUP_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_AGE_GROUP_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_AGE_GROUP_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )

            _exec_ddl(
                cur,
                """
                CREATE TABLE MH_AGE_GROUP (
                    AGE_GROUP_ID            NUMBER          NOT NULL,
                    AGE_GROUP_CODE          VARCHAR2(50)    NOT NULL,
                    AGE_GROUP_NAME          VARCHAR2(100)   NOT NULL,
                    SLUG                    VARCHAR2(120)   NOT NULL,
                    MIN_AGE_MONTHS          NUMBER          DEFAULT 0 NOT NULL,
                    MAX_AGE_MONTHS          NUMBER,
                    DESCRIPTION             VARCHAR2(500),
                    SORT_ORDER              NUMBER          DEFAULT 0 NOT NULL,
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_MH_AGE_GROUP PRIMARY KEY (AGE_GROUP_ID),
                    CONSTRAINT UQ_MH_AGE_GROUP_CODE UNIQUE (AGE_GROUP_CODE),
                    CONSTRAINT UQ_MH_AGE_GROUP_SLUG UNIQUE (SLUG),
                    CONSTRAINT CK_MH_AGE_GROUP_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                )
                """,
            )
            _seed_age_groups(cur)
        conn.commit()

    _mark_age_group_ready()
    _AGE_GROUP_SCHEMA_READY = True


_ITEM_AGE_GROUP_SCHEMA_READY = False


def ensure_item_age_group_schema() -> None:
    """Create MH_ITEM_AGE_GROUP so ERP can assign products to Shop by age."""
    global _ITEM_AGE_GROUP_SCHEMA_READY
    if _ITEM_AGE_GROUP_SCHEMA_READY:
        return
    ensure_age_group_schema()
    if _table_exists('MH_ITEM_AGE_GROUP'):
        _TABLE_EXISTS_CACHE['MH_ITEM_AGE_GROUP'] = True
        key = _schema_cache_key('MH_ITEM_AGE_GROUP')
        if key:
            _TABLE_EXISTS_CACHE[key] = True
        _ITEM_AGE_GROUP_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            _exec_ddl(
                cur,
                """
                CREATE TABLE MH_ITEM_AGE_GROUP (
                    ITEM_CODE               NUMBER          NOT NULL,
                    AGE_GROUP_ID            NUMBER          NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CONSTRAINT PK_MH_ITEM_AGE_GROUP PRIMARY KEY (ITEM_CODE, AGE_GROUP_ID)
                )
                """,
            )
            _exec_ddl(cur, 'CREATE INDEX IX_MH_ITEM_AGE_GROUP_AGE ON MH_ITEM_AGE_GROUP (AGE_GROUP_ID)')
        conn.commit()

    _TABLE_EXISTS_CACHE['MH_ITEM_AGE_GROUP'] = True
    key = _schema_cache_key('MH_ITEM_AGE_GROUP')
    if key:
        _TABLE_EXISTS_CACHE[key] = True
    _ITEM_AGE_GROUP_SCHEMA_READY = True


_APP_USER_TABLES = ('APP_USER', 'ROLE', 'PERMISSION', 'USER_ROLE', 'ROLE_PERMISSION')

_SUPERADMIN_HASH = '$2b$12$mNB22NB0et3sb9cif0Mt9uEZZ0KrKbL.aBfLz8/km./g.2e1Wf8LC'

_DEFAULT_ROLES = (
    ('SUPER_ADMIN', 'Super Administrator', 'Full system access'),
    ('ADMIN', 'Administrator', 'Store admin portal access'),
    ('CUSTOMER', 'Customer', 'Online shopper'),
)

_DEFAULT_PERMISSIONS = (
    ('admin.dashboard', 'View admin dashboard', 'ADMIN'),
    ('admin.orders', 'Manage orders', 'ADMIN'),
    ('admin.products', 'View products', 'ADMIN'),
    ('admin.promotions', 'Manage promotions', 'ADMIN'),
    ('admin.customers', 'View customers', 'ADMIN'),
)


def _invalidate_app_user_cache() -> None:
    for key in _APP_USER_TABLES:
        _TABLE_EXISTS_CACHE.pop(key, None)


def _mark_app_user_ready() -> None:
    for key in _APP_USER_TABLES:
        _TABLE_EXISTS_CACHE[key] = True


def _row_count(cur, table: str) -> int:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    return int((cur.fetchone() or [0])[0])


def _seed_rbac(cur) -> None:
    if _row_count(cur, 'ROLE') == 0:
        for code, name, description in _DEFAULT_ROLES:
            cur.execute(
                """
                INSERT INTO ROLE (
                    ROLE_ID, ROLE_CODE, ROLE_NAME, DESCRIPTION,
                    IS_SYSTEM_ROLE, IS_ACTIVE, CREATED_AT
                ) VALUES (
                    SEQ_ROLE_ID.NEXTVAL, :code, :name, :description, 1, 1, SYSTIMESTAMP
                )
                """,
                {'code': code, 'name': name, 'description': description},
            )

    if _row_count(cur, 'PERMISSION') == 0:
        for code, name, module_name in _DEFAULT_PERMISSIONS:
            cur.execute(
                """
                INSERT INTO PERMISSION (
                    PERMISSION_ID, PERMISSION_CODE, PERMISSION_NAME,
                    MODULE_NAME, IS_ACTIVE, CREATED_AT
                ) VALUES (
                    SEQ_PERMISSION_ID.NEXTVAL, :code, :name, :module_name, 1, SYSTIMESTAMP
                )
                """,
                {'code': code, 'name': name, 'module_name': module_name},
            )

    cur.execute(
        """
        SELECT COUNT(*) FROM APP_USER WHERE LOWER(EMAIL) = 'admin@mamahub.store'
        """
    )
    if int((cur.fetchone() or [0])[0]) == 0:
        cur.execute('SELECT SEQ_USER_ID.NEXTVAL AS id FROM DUAL')
        user_id = int((cur.fetchone() or [0])[0])
        cur.execute(
            """
            INSERT INTO APP_USER (
                USER_ID, USERNAME, EMAIL, PASSWORD_HASH,
                FIRST_NAME, LAST_NAME, USER_TYPE, ACCOUNT_STATUS,
                EMAIL_VERIFIED, MOBILE_VERIFIED, FAILED_LOGIN_COUNT,
                PREFERRED_LANGUAGE, IS_ACTIVE, CREATED_AT
            ) VALUES (
                :user_id, 'superadmin', 'admin@mamahub.store', :password_hash,
                'Super', 'Admin', 'STAFF', 'ACTIVE',
                1, 0, 0, 'en', 1, SYSTIMESTAMP
            )
            """,
            {'user_id': user_id, 'password_hash': _SUPERADMIN_HASH},
        )
        cur.execute(
            """
            INSERT INTO USER_ROLE (USER_ROLE_ID, USER_ID, ROLE_ID, CREATED_AT)
            SELECT SEQ_USER_ROLE_ID.NEXTVAL, :user_id, r.ROLE_ID, SYSTIMESTAMP
            FROM ROLE r
            WHERE r.ROLE_CODE = 'SUPER_ADMIN'
            """,
            {'user_id': user_id},
        )


def ensure_app_user_schema() -> None:
    """Create APP_USER / RBAC tables and seed defaults when absent."""
    global _APP_USER_SCHEMA_READY
    if _APP_USER_SCHEMA_READY:
        return
    if _table_exists('APP_USER'):
        with _get_connection() as conn:
            with conn.cursor() as cur:
                if _table_exists('ROLE'):
                    _seed_rbac(cur)
            conn.commit()
        _mark_app_user_ready()
        _APP_USER_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for seq in (
                'SEQ_USER_ID',
                'SEQ_ROLE_ID',
                'SEQ_PERMISSION_ID',
                'SEQ_USER_ROLE_ID',
                'SEQ_ROLE_PERMISSION_ID',
            ):
                if not _sequence_exists(cur, seq):
                    _exec_ddl(
                        cur,
                        f'CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                    )

            _exec_ddl(
                cur,
                """
                CREATE TABLE APP_USER (
                    USER_ID                 NUMBER          NOT NULL,
                    USERNAME                VARCHAR2(100)   NOT NULL,
                    EMAIL                   VARCHAR2(255)   NOT NULL,
                    MOBILE                  VARCHAR2(30),
                    PASSWORD_HASH           VARCHAR2(255),
                    FIRST_NAME              VARCHAR2(100)   NOT NULL,
                    LAST_NAME               VARCHAR2(100)   NOT NULL,
                    USER_TYPE               VARCHAR2(30)    DEFAULT 'STAFF' NOT NULL,
                    ACCOUNT_STATUS          VARCHAR2(30)    DEFAULT 'ACTIVE' NOT NULL,
                    EMAIL_VERIFIED          NUMBER(1)       DEFAULT 0 NOT NULL,
                    MOBILE_VERIFIED         NUMBER(1)       DEFAULT 0 NOT NULL,
                    FAILED_LOGIN_COUNT      NUMBER          DEFAULT 0 NOT NULL,
                    LOCKED_UNTIL            TIMESTAMP,
                    LAST_LOGIN_AT           TIMESTAMP,
                    PREFERRED_LANGUAGE      VARCHAR2(10)    DEFAULT 'en' NOT NULL,
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_APP_USER PRIMARY KEY (USER_ID),
                    CONSTRAINT UQ_APP_USER_USERNAME UNIQUE (USERNAME),
                    CONSTRAINT UQ_APP_USER_EMAIL UNIQUE (EMAIL),
                    CONSTRAINT CK_APP_USER_ACTIVE CHECK (IS_ACTIVE IN (0, 1)),
                    CONSTRAINT CK_APP_USER_EMAIL_VER CHECK (EMAIL_VERIFIED IN (0, 1)),
                    CONSTRAINT CK_APP_USER_MOBILE_VER CHECK (MOBILE_VERIFIED IN (0, 1)),
                    CONSTRAINT CK_APP_USER_TYPE CHECK (
                        USER_TYPE IN ('CUSTOMER', 'STAFF', 'SYSTEM')
                    ),
                    CONSTRAINT CK_APP_USER_STATUS CHECK (
                        ACCOUNT_STATUS IN ('ACTIVE', 'INACTIVE', 'LOCKED', 'PENDING')
                    )
                )
                """,
            )

            _exec_ddl(
                cur,
                """
                CREATE TABLE ROLE (
                    ROLE_ID                 NUMBER          NOT NULL,
                    ROLE_CODE               VARCHAR2(50)    NOT NULL,
                    ROLE_NAME               VARCHAR2(100)   NOT NULL,
                    DESCRIPTION             VARCHAR2(500),
                    IS_SYSTEM_ROLE          NUMBER(1)       DEFAULT 1 NOT NULL,
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_ROLE PRIMARY KEY (ROLE_ID),
                    CONSTRAINT UQ_ROLE_CODE UNIQUE (ROLE_CODE),
                    CONSTRAINT CK_ROLE_ACTIVE CHECK (IS_ACTIVE IN (0, 1)),
                    CONSTRAINT CK_ROLE_SYSTEM CHECK (IS_SYSTEM_ROLE IN (0, 1))
                )
                """,
            )

            _exec_ddl(
                cur,
                """
                CREATE TABLE PERMISSION (
                    PERMISSION_ID           NUMBER          NOT NULL,
                    PERMISSION_CODE         VARCHAR2(100)   NOT NULL,
                    PERMISSION_NAME         VARCHAR2(150)   NOT NULL,
                    MODULE_NAME             VARCHAR2(100)   NOT NULL,
                    DESCRIPTION             VARCHAR2(500),
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_PERMISSION PRIMARY KEY (PERMISSION_ID),
                    CONSTRAINT UQ_PERMISSION_CODE UNIQUE (PERMISSION_CODE),
                    CONSTRAINT CK_PERMISSION_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                )
                """,
            )

            _exec_ddl(
                cur,
                """
                CREATE TABLE USER_ROLE (
                    USER_ROLE_ID            NUMBER          NOT NULL,
                    USER_ID                 NUMBER          NOT NULL,
                    ROLE_ID                 NUMBER          NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_USER_ROLE PRIMARY KEY (USER_ROLE_ID),
                    CONSTRAINT UQ_USER_ROLE UNIQUE (USER_ID, ROLE_ID),
                    CONSTRAINT FK_USER_ROLE_USER FOREIGN KEY (USER_ID) REFERENCES APP_USER (USER_ID),
                    CONSTRAINT FK_USER_ROLE_ROLE FOREIGN KEY (ROLE_ID) REFERENCES ROLE (ROLE_ID)
                )
                """,
            )

            _exec_ddl(
                cur,
                """
                CREATE TABLE ROLE_PERMISSION (
                    ROLE_PERMISSION_ID      NUMBER          NOT NULL,
                    ROLE_ID                 NUMBER          NOT NULL,
                    PERMISSION_ID           NUMBER          NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_ROLE_PERMISSION PRIMARY KEY (ROLE_PERMISSION_ID),
                    CONSTRAINT UQ_ROLE_PERMISSION UNIQUE (ROLE_ID, PERMISSION_ID),
                    CONSTRAINT FK_ROLE_PERM_ROLE FOREIGN KEY (ROLE_ID) REFERENCES ROLE (ROLE_ID),
                    CONSTRAINT FK_ROLE_PERM_PERM FOREIGN KEY (PERMISSION_ID) REFERENCES PERMISSION (PERMISSION_ID)
                )
                """,
            )

            if not _index_exists(cur, 'IDX_APP_USER_STATUS'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IDX_APP_USER_STATUS ON APP_USER (ACCOUNT_STATUS, IS_ACTIVE)',
                )

            _seed_rbac(cur)
        conn.commit()

    _mark_app_user_ready()
    _APP_USER_SCHEMA_READY = True


def _invalidate_address_cache() -> None:
    _TABLE_EXISTS_CACHE.pop('MH_CUSTOMER_ADDRESS', None)


def _mark_address_ready() -> None:
    _TABLE_EXISTS_CACHE['MH_CUSTOMER_ADDRESS'] = True


def ensure_address_schema() -> None:
    """Create MH_CUSTOMER_ADDRESS table and sequence when absent."""
    global _ADDRESS_SCHEMA_READY
    if _ADDRESS_SCHEMA_READY:
        return
    if _table_exists('MH_CUSTOMER_ADDRESS'):
        _mark_address_ready()
        _ADDRESS_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_ADDRESS_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_ADDRESS_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )

            _exec_ddl(
                cur,
                """
                CREATE TABLE MH_CUSTOMER_ADDRESS (
                    ADDRESS_ID              NUMBER          NOT NULL,
                    USER_ID                 NUMBER          NOT NULL,
                    ADDRESS_TITLE           VARCHAR2(100)   NOT NULL,
                    ADDRESS_TYPE            VARCHAR2(30)    DEFAULT 'HOME' NOT NULL,
                    BUILDING_NUMBER         VARCHAR2(50),
                    STREET                  VARCHAR2(200)   NOT NULL,
                    ZONE                    VARCHAR2(100),
                    AREA                    VARCHAR2(100),
                    CITY                    VARCHAR2(100)   NOT NULL,
                    COUNTRY                 VARCHAR2(100)   DEFAULT 'Qatar' NOT NULL,
                    LANDMARK                VARCHAR2(200),
                    LATITUDE                NUMBER(10,7),
                    LONGITUDE               NUMBER(10,7),
                    IS_DEFAULT              NUMBER(1)       DEFAULT 0 NOT NULL,
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CREATED_BY              NUMBER,
                    MODIFIED_AT             TIMESTAMP,
                    MODIFIED_BY             NUMBER,
                    CONSTRAINT PK_MH_CUSTOMER_ADDRESS PRIMARY KEY (ADDRESS_ID),
                    CONSTRAINT CK_MH_ADDRESS_TYPE CHECK (ADDRESS_TYPE IN ('HOME', 'OFFICE', 'OTHER')),
                    CONSTRAINT CK_MH_ADDRESS_DEFAULT CHECK (IS_DEFAULT IN (0, 1)),
                    CONSTRAINT CK_MH_ADDRESS_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                )
                """,
            )

            if not _index_exists(cur, 'IX_MH_ADDRESS_USER'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IX_MH_ADDRESS_USER ON MH_CUSTOMER_ADDRESS (USER_ID, IS_ACTIVE)',
                )

        conn.commit()

    _mark_address_ready()
    _ADDRESS_SCHEMA_READY = True


_ORDER_TABLES = ('MH_ORDER', 'MH_ORDER_ITEM', 'MH_ORDER_STATUS_HISTORY')


def _invalidate_order_cache() -> None:
    for key in _ORDER_TABLES:
        _TABLE_EXISTS_CACHE.pop(key, None)


def _mark_order_ready() -> None:
    for key in _ORDER_TABLES:
        _TABLE_EXISTS_CACHE[key] = True


def ensure_order_schema() -> None:
    """Create MH_ORDER tables and sequences when absent."""
    global _ORDER_SCHEMA_READY
    if _ORDER_SCHEMA_READY:
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for seq in (
                'SEQ_MH_ORDER_ID',
                'SEQ_MH_ORDER_ITEM_ID',
                'SEQ_MH_ORDER_STATUS_ID',
            ):
                if not _sequence_exists(cur, seq):
                    _exec_ddl(
                        cur,
                        f'CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                    )

            if not _table_exists('MH_ORDER'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_ORDER (
                        ORDER_ID                NUMBER          NOT NULL,
                        ORDER_NUMBER            VARCHAR2(30)    NOT NULL,
                        USER_ID                 NUMBER          NOT NULL,
                        CART_ID                 NUMBER,
                        LOCATION_CODE           NUMBER          NOT NULL,
                        ORDER_STATUS            VARCHAR2(40)    DEFAULT 'PENDING' NOT NULL,
                        FULFILLMENT_TYPE        VARCHAR2(20)    NOT NULL,
                        PAYMENT_STATUS          VARCHAR2(30)    DEFAULT 'PENDING' NOT NULL,
                        SUBTOTAL                NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        DISCOUNT_TOTAL          NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        TAX_TOTAL               NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        DELIVERY_FEE            NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        GRAND_TOTAL             NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        CURRENCY_CODE           VARCHAR2(3)     DEFAULT 'QAR' NOT NULL,
                        COUPON_CODE             VARCHAR2(50),
                        DELIVERY_ZONE_ID        NUMBER,
                        DELIVERY_SLOT_ID        NUMBER,
                        PICKUP_STORE_ID         NUMBER,
                        ADDRESS_ID              NUMBER,
                        ADDRESS_SNAPSHOT        CLOB,
                        CUSTOMER_NOTES          VARCHAR2(1000),
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_BY              NUMBER,
                        MODIFIED_AT             TIMESTAMP,
                        MODIFIED_BY             NUMBER,
                        CONSTRAINT PK_MH_ORDER PRIMARY KEY (ORDER_ID),
                        CONSTRAINT UQ_MH_ORDER_NUMBER UNIQUE (ORDER_NUMBER),
                        CONSTRAINT CK_MH_ORDER_FULFILLMENT CHECK (FULFILLMENT_TYPE IN ('DELIVERY', 'PICKUP'))
                    )
                    """,
                )

            if not _table_exists('MH_ORDER_ITEM'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_ORDER_ITEM (
                        ORDER_ITEM_ID           NUMBER          NOT NULL,
                        ORDER_ID                NUMBER          NOT NULL,
                        LOCATION_CODE           NUMBER          NOT NULL,
                        ITEM_CODE               NUMBER          NOT NULL,
                        ITEM_NAME               VARCHAR2(300),
                        QUANTITY                NUMBER(12,3)    NOT NULL,
                        UNIT_PRICE              NUMBER(18,4)    NOT NULL,
                        DISCOUNT_AMOUNT         NUMBER(18,4)    DEFAULT 0 NOT NULL,
                        LINE_TOTAL              NUMBER(18,4)    NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_ORDER_ITEM PRIMARY KEY (ORDER_ITEM_ID),
                        CONSTRAINT FK_MH_ORDER_ITEM_ORDER FOREIGN KEY (ORDER_ID) REFERENCES MH_ORDER (ORDER_ID)
                    )
                    """,
                )

            if not _table_exists('MH_ORDER_STATUS_HISTORY'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_ORDER_STATUS_HISTORY (
                        STATUS_HISTORY_ID       NUMBER          NOT NULL,
                        ORDER_ID                NUMBER          NOT NULL,
                        ORDER_STATUS            VARCHAR2(40)    NOT NULL,
                        STATUS_NOTES            VARCHAR2(500),
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_BY              NUMBER,
                        CONSTRAINT PK_MH_ORDER_STATUS_HISTORY PRIMARY KEY (STATUS_HISTORY_ID),
                        CONSTRAINT FK_MH_ORDER_STATUS_ORDER FOREIGN KEY (ORDER_ID) REFERENCES MH_ORDER (ORDER_ID)
                    )
                    """,
                )

            for index_name, ddl in (
                (
                    'IX_MH_ORDER_USER',
                    'CREATE INDEX IX_MH_ORDER_USER ON MH_ORDER (USER_ID, ORDER_STATUS)',
                ),
                (
                    'IX_MH_ORDER_ITEM_ORDER',
                    'CREATE INDEX IX_MH_ORDER_ITEM_ORDER ON MH_ORDER_ITEM (ORDER_ID)',
                ),
                (
                    'IX_MH_ORDER_STATUS_ORDER',
                    'CREATE INDEX IX_MH_ORDER_STATUS_ORDER ON MH_ORDER_STATUS_HISTORY (ORDER_ID, CREATED_AT)',
                ),
            ):
                if not _index_exists(cur, index_name):
                    _exec_ddl(cur, ddl)

        conn.commit()

    _mark_order_ready()
    _ORDER_SCHEMA_READY = True


def _mark_password_reset_ready() -> None:
    _TABLE_EXISTS_CACHE['MH_PASSWORD_RESET'] = True


def ensure_password_reset_schema() -> None:
    """Create MH_PASSWORD_RESET for email password reset tokens."""
    global _PASSWORD_RESET_SCHEMA_READY
    if _PASSWORD_RESET_SCHEMA_READY:
        return
    if _table_exists('MH_PASSWORD_RESET'):
        _mark_password_reset_ready()
        _PASSWORD_RESET_SCHEMA_READY = True
        return
    if not _table_exists('APP_USER'):
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_PASSWORD_RESET_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_PASSWORD_RESET_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )
            _exec_ddl(
                cur,
                """
                CREATE TABLE MH_PASSWORD_RESET (
                    RESET_ID                NUMBER          NOT NULL,
                    USER_ID                 NUMBER          NOT NULL,
                    TOKEN_HASH              VARCHAR2(64)    NOT NULL,
                    EXPIRES_AT              TIMESTAMP       NOT NULL,
                    USED_AT                 TIMESTAMP,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CONSTRAINT PK_MH_PASSWORD_RESET PRIMARY KEY (RESET_ID),
                    CONSTRAINT FK_MH_PASSWORD_RESET_USER FOREIGN KEY (USER_ID) REFERENCES APP_USER (USER_ID)
                )
                """,
            )
            if not _index_exists(cur, 'IX_MH_PASSWORD_RESET_HASH'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IX_MH_PASSWORD_RESET_HASH ON MH_PASSWORD_RESET (TOKEN_HASH)',
                )
            if not _index_exists(cur, 'IX_MH_PASSWORD_RESET_USER'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IX_MH_PASSWORD_RESET_USER ON MH_PASSWORD_RESET (USER_ID, USED_AT, EXPIRES_AT)',
                )
        conn.commit()

    _mark_password_reset_ready()
    _PASSWORD_RESET_SCHEMA_READY = True


_DELIVERY_SCHEMA_READY = False

_DEFAULT_DELIVERY_ZONES = (
    ('QATAR', 'Qatar', 'Doha', 0, 0, None, 1),
)

_DEFAULT_DELIVERY_SLOTS = (
    ('MORNING', 'Morning (9 AM – 1 PM)', 9, 13, 80),
    ('AFTERNOON', 'Afternoon (1 PM – 5 PM)', 13, 17, 80),
    ('EVENING', 'Evening (5 PM – 9 PM)', 17, 21, 80),
)


def _seed_delivery_defaults(cur) -> None:
    cur.execute('SELECT COUNT(*) FROM MH_DELIVERY_ZONE')
    if int((cur.fetchone() or [0])[0]) == 0:
        for zone_id, (code, name, city, fee, min_order, free_over, days) in enumerate(
            _DEFAULT_DELIVERY_ZONES, start=1
        ):
            cur.execute(
                """
                INSERT INTO MH_DELIVERY_ZONE (
                    DELIVERY_ZONE_ID, ZONE_CODE, ZONE_NAME, CITY,
                    DELIVERY_FEE, MIN_ORDER_AMOUNT, FREE_DELIVERY_THRESHOLD,
                    ESTIMATED_DAYS, IS_ACTIVE
                ) VALUES (
                    :zone_id, :zone_code, :zone_name, :city,
                    :delivery_fee, :min_order_amount, :free_delivery_threshold,
                    :estimated_days, 1
                )
                """,
                {
                    'zone_id': zone_id,
                    'zone_code': code,
                    'zone_name': name,
                    'city': city,
                    'delivery_fee': fee,
                    'min_order_amount': min_order,
                    'free_delivery_threshold': free_over,
                    'estimated_days': days,
                },
            )
    cur.execute('SELECT COUNT(*) FROM MH_DELIVERY_SLOT')
    if int((cur.fetchone() or [0])[0]) == 0:
        for slot_id, (code, label, start_hour, end_hour, max_orders) in enumerate(
            _DEFAULT_DELIVERY_SLOTS, start=1
        ):
            cur.execute(
                """
                INSERT INTO MH_DELIVERY_SLOT (
                    DELIVERY_SLOT_ID, SLOT_CODE, SLOT_LABEL,
                    START_HOUR, END_HOUR, MAX_ORDERS, IS_ACTIVE
                ) VALUES (
                    :slot_id, :slot_code, :slot_label,
                    :start_hour, :end_hour, :max_orders, 1
                )
                """,
                {
                    'slot_id': slot_id,
                    'slot_code': code,
                    'slot_label': label,
                    'start_hour': start_hour,
                    'end_hour': end_hour,
                    'max_orders': max_orders,
                },
            )


def ensure_delivery_schema() -> None:
    """Create delivery zone/slot tables and seed Qatar defaults when empty."""
    global _DELIVERY_SCHEMA_READY
    if _DELIVERY_SCHEMA_READY:
        return
    zone_ready = _table_exists('MH_DELIVERY_ZONE')
    slot_ready = _table_exists('MH_DELIVERY_SLOT')
    if zone_ready and slot_ready:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                _seed_delivery_defaults(cur)
            conn.commit()
        _TABLE_EXISTS_CACHE['MH_DELIVERY_ZONE'] = True
        _TABLE_EXISTS_CACHE['MH_DELIVERY_SLOT'] = True
        _DELIVERY_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_DELIVERY_ZONE_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_DELIVERY_ZONE_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )
            if not _sequence_exists(cur, 'SEQ_MH_DELIVERY_SLOT_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_DELIVERY_SLOT_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )
            _exec_ddl(
                cur,
                """
                CREATE TABLE MH_DELIVERY_ZONE (
                    DELIVERY_ZONE_ID        NUMBER          NOT NULL,
                    ZONE_CODE               VARCHAR2(40)    NOT NULL,
                    ZONE_NAME               VARCHAR2(120)   NOT NULL,
                    CITY                    VARCHAR2(80)    NOT NULL,
                    DELIVERY_FEE            NUMBER(12,3)    DEFAULT 0 NOT NULL,
                    MIN_ORDER_AMOUNT        NUMBER(12,3)    DEFAULT 0 NOT NULL,
                    FREE_DELIVERY_THRESHOLD NUMBER(12,3),
                    ESTIMATED_DAYS          NUMBER          DEFAULT 1 NOT NULL,
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CONSTRAINT PK_MH_DELIVERY_ZONE PRIMARY KEY (DELIVERY_ZONE_ID),
                    CONSTRAINT UQ_MH_DELIVERY_ZONE_CODE UNIQUE (ZONE_CODE),
                    CONSTRAINT CK_MH_DELIVERY_ZONE_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                )
                """,
            )
            _exec_ddl(
                cur,
                """
                CREATE TABLE MH_DELIVERY_SLOT (
                    DELIVERY_SLOT_ID        NUMBER          NOT NULL,
                    SLOT_CODE               VARCHAR2(40)    NOT NULL,
                    SLOT_LABEL              VARCHAR2(120)   NOT NULL,
                    START_HOUR              NUMBER          NOT NULL,
                    END_HOUR                NUMBER          NOT NULL,
                    MAX_ORDERS              NUMBER          DEFAULT 50 NOT NULL,
                    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                    CONSTRAINT PK_MH_DELIVERY_SLOT PRIMARY KEY (DELIVERY_SLOT_ID),
                    CONSTRAINT UQ_MH_DELIVERY_SLOT_CODE UNIQUE (SLOT_CODE),
                    CONSTRAINT CK_MH_DELIVERY_SLOT_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                )
                """,
            )
            _seed_delivery_defaults(cur)
        conn.commit()

    _TABLE_EXISTS_CACHE['MH_DELIVERY_ZONE'] = True
    _TABLE_EXISTS_CACHE['MH_DELIVERY_SLOT'] = True
    _DELIVERY_SCHEMA_READY = True


def _mark_promotion_ready() -> None:
    for key in ('MH_PROMOTION', 'MH_COUPON', 'MH_COUPON_USAGE'):
        _TABLE_EXISTS_CACHE.pop(key, None)
        _TABLE_EXISTS_CACHE.pop(_schema_cache_key(key), None)
        _TABLE_EXISTS_CACHE[key] = True
        _TABLE_EXISTS_CACHE[_schema_cache_key(key)] = True


def ensure_promotion_schema() -> None:
    """Create MH_PROMOTION, MH_COUPON, and MH_COUPON_USAGE when absent."""
    global _PROMOTION_SCHEMA_READY
    if _PROMOTION_SCHEMA_READY:
        return
    if (
        _table_exists('MH_PROMOTION')
        and _table_exists('MH_COUPON')
        and _table_exists('MH_COUPON_USAGE')
    ):
        _mark_promotion_ready()
        _PROMOTION_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for seq in (
                'SEQ_MH_PROMOTION_ID',
                'SEQ_MH_COUPON_ID',
                'SEQ_MH_COUPON_USAGE_ID',
            ):
                if not _sequence_exists(cur, seq):
                    _exec_ddl(
                        cur,
                        f'CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                    )

            if not _table_exists('MH_PROMOTION'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_PROMOTION (
                        PROMOTION_ID            NUMBER          NOT NULL,
                        PROMOTION_CODE          VARCHAR2(40)    NOT NULL,
                        PROMOTION_NAME          VARCHAR2(200)   NOT NULL,
                        PROMOTION_TYPE          VARCHAR2(20)    NOT NULL,
                        DISCOUNT_VALUE          NUMBER(12,3)    DEFAULT 0 NOT NULL,
                        MIN_ORDER_AMOUNT        NUMBER(12,3)    DEFAULT 0 NOT NULL,
                        MAX_DISCOUNT_AMOUNT     NUMBER(12,3),
                        START_DATE              TIMESTAMP       NOT NULL,
                        END_DATE                TIMESTAMP       NOT NULL,
                        USAGE_LIMIT             NUMBER,
                        USAGE_PER_CUSTOMER      NUMBER          DEFAULT 1 NOT NULL,
                        IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_PROMOTION PRIMARY KEY (PROMOTION_ID),
                        CONSTRAINT UQ_MH_PROMOTION_CODE UNIQUE (PROMOTION_CODE),
                        CONSTRAINT CK_MH_PROMOTION_TYPE CHECK (
                            PROMOTION_TYPE IN ('PERCENTAGE', 'FIXED', 'FREE_DELIVERY')
                        ),
                        CONSTRAINT CK_MH_PROMOTION_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                    )
                    """,
                )

            if not _table_exists('MH_COUPON'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_COUPON (
                        COUPON_ID               NUMBER          NOT NULL,
                        PROMOTION_ID            NUMBER          NOT NULL,
                        COUPON_CODE             VARCHAR2(50)    NOT NULL,
                        IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_COUPON PRIMARY KEY (COUPON_ID),
                        CONSTRAINT UQ_MH_COUPON_CODE UNIQUE (COUPON_CODE),
                        CONSTRAINT FK_MH_COUPON_PROMOTION FOREIGN KEY (PROMOTION_ID)
                            REFERENCES MH_PROMOTION (PROMOTION_ID),
                        CONSTRAINT CK_MH_COUPON_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
                    )
                    """,
                )

            if not _table_exists('MH_COUPON_USAGE'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_COUPON_USAGE (
                        USAGE_ID                NUMBER          NOT NULL,
                        COUPON_ID               NUMBER          NOT NULL,
                        USER_ID                 NUMBER,
                        ORDER_ID                NUMBER,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_COUPON_USAGE PRIMARY KEY (USAGE_ID),
                        CONSTRAINT FK_MH_COUPON_USAGE_COUPON FOREIGN KEY (COUPON_ID)
                            REFERENCES MH_COUPON (COUPON_ID)
                    )
                    """,
                )

            for index_name, ddl in (
                (
                    'IX_MH_PROMOTION_ACTIVE',
                    'CREATE INDEX IX_MH_PROMOTION_ACTIVE ON MH_PROMOTION (IS_ACTIVE, START_DATE, END_DATE)',
                ),
                (
                    'IX_MH_COUPON_PROMOTION',
                    'CREATE INDEX IX_MH_COUPON_PROMOTION ON MH_COUPON (PROMOTION_ID)',
                ),
                (
                    'IX_MH_COUPON_USAGE_COUPON',
                    'CREATE INDEX IX_MH_COUPON_USAGE_COUPON ON MH_COUPON_USAGE (COUPON_ID, USER_ID)',
                ),
            ):
                if not _index_exists(cur, index_name):
                    _exec_ddl(cur, ddl)

        conn.commit()

    _mark_promotion_ready()
    _PROMOTION_SCHEMA_READY = True


_SEARCH_EVENT_SCHEMA_READY = False


def ensure_search_event_schema() -> None:
    """Create MH_SEARCH_EVENT for zero-result / assist tracking."""
    global _SEARCH_EVENT_SCHEMA_READY
    if _SEARCH_EVENT_SCHEMA_READY:
        return
    if _table_exists('MH_SEARCH_EVENT'):
        _TABLE_EXISTS_CACHE['MH_SEARCH_EVENT'] = True
        _SEARCH_EVENT_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_SEARCH_EVENT_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_SEARCH_EVENT_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )
            if not _table_exists('MH_SEARCH_EVENT'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_SEARCH_EVENT (
                        EVENT_ID                NUMBER          NOT NULL,
                        USER_ID                 NUMBER,
                        QUERY_TEXT              VARCHAR2(200 CHAR) NOT NULL,
                        QUERY_NORM              VARCHAR2(200 CHAR) NOT NULL,
                        RESULT_COUNT            NUMBER          DEFAULT 0 NOT NULL,
                        CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CONSTRAINT PK_MH_SEARCH_EVENT PRIMARY KEY (EVENT_ID)
                    )
                    """,
                )
            if not _index_exists(cur, 'IX_MH_SEARCH_EVENT_USER'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IX_MH_SEARCH_EVENT_USER ON MH_SEARCH_EVENT (USER_ID, CREATED_AT)',
                )
            if not _index_exists(cur, 'IX_MH_SEARCH_EVENT_Q'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IX_MH_SEARCH_EVENT_Q ON MH_SEARCH_EVENT (QUERY_NORM, CREATED_AT)',
                )
        conn.commit()

    _TABLE_EXISTS_CACHE['MH_SEARCH_EVENT'] = True
    _SEARCH_EVENT_SCHEMA_READY = True


_NOTIFICATION_SCHEMA_READY = False


def ensure_notification_schema() -> None:
    """Create MH_NOTIFICATION for shop in-app alerts."""
    global _NOTIFICATION_SCHEMA_READY
    if _NOTIFICATION_SCHEMA_READY:
        return
    if _table_exists('MH_NOTIFICATION'):
        _TABLE_EXISTS_CACHE['MH_NOTIFICATION'] = True
        _NOTIFICATION_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            if not _sequence_exists(cur, 'SEQ_MH_NOTIFICATION_ID'):
                _exec_ddl(
                    cur,
                    'CREATE SEQUENCE SEQ_MH_NOTIFICATION_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                )
            if not _table_exists('MH_NOTIFICATION'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_NOTIFICATION (
                        NOTIFICATION_ID     NUMBER          NOT NULL,
                        USER_ID             NUMBER          NOT NULL,
                        CHANNEL             VARCHAR2(20)    DEFAULT 'IN_APP' NOT NULL,
                        NOTIFICATION_TYPE   VARCHAR2(50)    NOT NULL,
                        TITLE               VARCHAR2(200)   NOT NULL,
                        BODY                VARCHAR2(2000),
                        REF_ENTITY          VARCHAR2(50),
                        REF_ENTITY_ID       NUMBER,
                        IS_READ             NUMBER(1)       DEFAULT 0 NOT NULL,
                        CREATED_AT          TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        READ_AT             TIMESTAMP,
                        CONSTRAINT PK_MH_NOTIFICATION PRIMARY KEY (NOTIFICATION_ID),
                        CONSTRAINT CK_MH_NOTIF_READ CHECK (IS_READ IN (0, 1))
                    )
                    """,
                )
            if not _index_exists(cur, 'IX_MH_NOTIFICATION_USER'):
                _exec_ddl(
                    cur,
                    'CREATE INDEX IX_MH_NOTIFICATION_USER ON MH_NOTIFICATION (USER_ID, IS_READ, CREATED_AT)',
                )
        conn.commit()

    _TABLE_EXISTS_CACHE.pop(_schema_cache_key('MH_NOTIFICATION'), None)
    _TABLE_EXISTS_CACHE['MH_NOTIFICATION'] = True
    _NOTIFICATION_SCHEMA_READY = True


_WISHLIST_TABLES = ('MH_WISHLIST', 'MH_WISHLIST_ITEM')
_WISHLIST_SCHEMA_READY = False


def ensure_wishlist_schema() -> None:
    """Create MH_WISHLIST / MH_WISHLIST_ITEM sequences and tables when absent."""
    global _WISHLIST_SCHEMA_READY
    if _WISHLIST_SCHEMA_READY:
        return
    if _table_exists('MH_WISHLIST') and _table_exists('MH_WISHLIST_ITEM'):
        for key in _WISHLIST_TABLES:
            _TABLE_EXISTS_CACHE[key] = True
        _WISHLIST_SCHEMA_READY = True
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for seq in ('SEQ_MH_WISHLIST_ID', 'SEQ_MH_WISHLIST_ITEM_ID'):
                if not _sequence_exists(cur, seq):
                    _exec_ddl(
                        cur,
                        f'CREATE SEQUENCE {seq} START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE',
                    )

            if not _table_exists('MH_WISHLIST'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_WISHLIST (
                        WISHLIST_ID     NUMBER          NOT NULL,
                        USER_ID         NUMBER          NOT NULL,
                        WISHLIST_NAME   VARCHAR2(80)    DEFAULT 'My Wishlist' NOT NULL,
                        IS_DEFAULT      NUMBER(1)       DEFAULT 1 NOT NULL,
                        CREATED_AT      TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_BY      NUMBER,
                        MODIFIED_AT     TIMESTAMP,
                        MODIFIED_BY     NUMBER,
                        CONSTRAINT PK_MH_WISHLIST PRIMARY KEY (WISHLIST_ID),
                        CONSTRAINT CK_MH_WISHLIST_DEFAULT CHECK (IS_DEFAULT IN (0, 1))
                    )
                    """,
                )

            if not _table_exists('MH_WISHLIST_ITEM'):
                _exec_ddl(
                    cur,
                    """
                    CREATE TABLE MH_WISHLIST_ITEM (
                        WISHLIST_ITEM_ID    NUMBER          NOT NULL,
                        WISHLIST_ID         NUMBER          NOT NULL,
                        LOCATION_CODE       NUMBER          NOT NULL,
                        ITEM_CODE           NUMBER          NOT NULL,
                        CREATED_AT          TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
                        CREATED_BY          NUMBER,
                        CONSTRAINT PK_MH_WISHLIST_ITEM PRIMARY KEY (WISHLIST_ITEM_ID),
                        CONSTRAINT FK_MH_WISHLIST_ITEM_HDR FOREIGN KEY (WISHLIST_ID)
                            REFERENCES MH_WISHLIST (WISHLIST_ID),
                        CONSTRAINT UQ_MH_WISHLIST_ITEM UNIQUE (WISHLIST_ID, LOCATION_CODE, ITEM_CODE)
                    )
                    """,
                )

            for index_name, ddl in (
                (
                    'IX_MH_WISHLIST_USER',
                    'CREATE INDEX IX_MH_WISHLIST_USER ON MH_WISHLIST (USER_ID, IS_DEFAULT)',
                ),
                (
                    'IX_MH_WISHLIST_ITEM_HDR',
                    'CREATE INDEX IX_MH_WISHLIST_ITEM_HDR ON MH_WISHLIST_ITEM (WISHLIST_ID)',
                ),
            ):
                if not _index_exists(cur, index_name):
                    _exec_ddl(cur, ddl)

        conn.commit()

    for key in _WISHLIST_TABLES:
        _TABLE_EXISTS_CACHE.pop(_schema_cache_key(key), None)
        _TABLE_EXISTS_CACHE[key] = True
    _WISHLIST_SCHEMA_READY = True
