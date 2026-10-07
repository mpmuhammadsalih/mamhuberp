from __future__ import annotations

import logging
from typing import Any

from db.oracle_driver import cx_Oracle

from mobile_backend.config import Config

logger = logging.getLogger(__name__)


def _mobile_ext_table_exists(cur: Any) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
          FROM user_tables
         WHERE table_name = :t
        """,
        {"t": "GRN_MOBILE_LINE_EXT"},
    )
    return int(cur.fetchone()[0] or 0) > 0


_DDLS = (
    """CREATE TABLE GRN_MOBILE_LINE_EXT (
           LPO_NO            VARCHAR2(64 CHAR)  NOT NULL,
           LOCATIONCODE      NUMBER(18)         DEFAULT 0 NOT NULL,
           LINE_SEQ          NUMBER(10)         NOT NULL,
           ITEM_CODE         VARCHAR2(128 CHAR) NOT NULL,
           RECEIVED_QTY      NUMBER(18, 4),
           BONUS_QTY         NUMBER(18, 4),
           FOC_FLAG          CHAR(1 CHAR),
           BONUS_BASE_UNIT   NUMBER(18, 4),
           BATCH_NO          VARCHAR2(128 CHAR),
           EXPIRY_DATE       DATE,
           STORE_CODE        VARCHAR2(64 CHAR),
           BIN_CODE          VARCHAR2(64 CHAR),
           UPDATED_BY        VARCHAR2(128 CHAR),
           UPDATED_AT        DATE DEFAULT SYSDATE NOT NULL,
           CONSTRAINT PK_GRN_MOBILE_LINE_EXT PRIMARY KEY (LPO_NO, LINE_SEQ, LOCATIONCODE)
         )""",
    "CREATE INDEX IDX_GRN_MOBILE_LINE_EXT_LPO ON GRN_MOBILE_LINE_EXT (LPO_NO)",
    "CREATE INDEX IDX_GRN_MOBILE_LINE_EXT_LPO_LOC ON GRN_MOBILE_LINE_EXT (LPO_NO, LOCATIONCODE)",
)

_COMMENT_DDLS = (
    """COMMENT ON TABLE GRN_MOBILE_LINE_EXT IS
       'Nexa mobile GRN wizard: supplemental line fields keyed by PO + LINE_SEQ + LOCATIONCODE.'""",
    """COMMENT ON COLUMN GRN_MOBILE_LINE_EXT.LOCATIONCODE IS
       'Numeric ERP branch/location id (JWT loc or LPO header); 0 = no specific location.'""",
)


def maybe_create_grn_mobile_line_ext(cur: Any, conn: Any) -> None:
    """
    If ``AUTO_CREATE_GRN_MOBILE_EXT=true`` (env / Config), creates ``GRN_MOBILE_LINE_EXT`` in the connected
    schema when missing. Disabled by default; requires CREATE TABLE / CREATE INDEX on that user.
    """
    if not Config.AUTO_CREATE_GRN_MOBILE_EXT:
        return
    if _mobile_ext_table_exists(cur):
        return
    logger.warning(
        "AUTO_CREATE_GRN_MOBILE_EXT enabled: provisioning GRN_MOBILE_LINE_EXT in current Oracle schema"
    )
    try:
        for stmt in _DDLS:
            cur.execute(stmt)
        for stmt in _COMMENT_DDLS:
            try:
                cur.execute(stmt)
            except cx_Oracle.DatabaseError as exc_inner:
                logger.debug("COMMENT DDL skipped (non-fatal): %s", exc_inner)
        conn.commit()
        logger.warning("AUTO_CREATE_GRN_MOBILE_EXT: GRN_MOBILE_LINE_EXT provisioned.")
    except cx_Oracle.DatabaseError as exc:
        conn.rollback()
        logger.exception(
            "AUTO_CREATE_GRN_MOBILE_EXT: could not provision GRN_MOBILE_LINE_EXT; run "
            "erp_api/sql/install_grn_mobile_line_ext_oracle_complete.sql manually. Reason: %s",
            exc,
        )
