import logging

from db.oracle_driver import cx_Oracle
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from mobile_backend.deps_auth import require_access_claims, require_any_permission
from mobile_backend.services import business_summary_service
from mobile_backend.services import customer_wise_sales_report_service as cws_reports
from mobile_backend.services import inventory_reports_service as inv_reports
from mobile_backend.services import pos_x_report_service as x_reports
from mobile_backend.services import sales_details_report_service as sales_details_reports
from mobile_backend.services import transaction_reports_service as tx_reports
from mobile_backend.utils.response import failure, success

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["reports"],
    dependencies=[Depends(require_access_claims)],
)

_BUSINESS_SUMMARY_PERMS = (
    "business_summary.dashboard",
    "business_summary.api_dashboard",
)

_INV_REPORT_PERMS = (
    "reports.stock_report",
    "reports.stock_report_datewise",
    "reports.stock_aging_report",
    "reports.warehouse_summary_report",
    "reports.supplier_balance_report",
    "purchase.item_journal_list",
    "purchase.inventory_valuation",
    "mobile.stock_ledger",
    "mobile.stock_summary",
    "mobile.inventory_history",
    "mobile.inventory_aging",
    "mobile.warehouse_summary",
    "mobile.supplier_balance",
    "mobile.reports",
)

_TX_REPORT_PERMS = (
    "mobile.transaction_summary",
    "mobile.transaction_details",
    "mobile.reports",
    "business_summary.dashboard",
    "business_summary.api_dashboard",
    "reports.sales_details",
    "reports.last_transactions_report",
    "sales_summary.sales_summary",
)

_X_REPORT_PERMS = (
    "pos_billing.pos_counter_operations_page",
    "pos_billing.pos_sales_list_page",
    "pos_billing.pos_sales_list_summary_api",
    "pos_billing.pos_counter_operations_preclose_report",
    "reports.sales_details",
    "mobile.sales_reports",
    "mobile.reports",
    "sales_summary.sales_summary",
    "mobile.transaction_summary",
)

_CWS_REPORT_PERMS = (
    "reports.customer_wise_sales_report",
    "reports.sales_details",
    "mobile.sales_reports",
    "mobile.reports",
    "sales_summary.sales_summary",
    "mobile.transaction_summary",
)


def _inv_ok(fn, *, error_code: str):
    try:
        return success(fn())
    except (cx_Oracle.Error, RuntimeError) as exc:
        logger.exception(error_code)
        return failure(str(exc)[:500], status_code=503, error_code=error_code)
    except ValueError as exc:
        return failure(str(exc)[:500], status_code=400, error_code=error_code)
    except Exception as exc:
        logger.exception(error_code)
        return failure(str(exc)[:500], status_code=500, error_code=error_code)


@router.get(
    "/business-summary",
    dependencies=[Depends(require_any_permission(*_BUSINESS_SUMMARY_PERMS))],
)
def business_summary_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    branch: str = Query(""),
):
    try:
        data = business_summary_service.get_business_summary(
            date_from=date_from,
            date_to=date_to,
            branch=branch,
        )
        return success(data)
    except (cx_Oracle.Error, RuntimeError) as exc:
        logger.exception("Business summary error")
        return failure(str(exc)[:500], status_code=503, error_code="BUSINESS_SUMMARY_ERROR")
    except Exception as exc:
        logger.exception("Business summary error")
        return failure(str(exc)[:500], status_code=500, error_code="BUSINESS_SUMMARY_ERROR")


@router.get(
    "/warehouse-summary",
    dependencies=[Depends(require_any_permission(*_INV_REPORT_PERMS))],
)
def warehouse_summary_route(q: str = Query("")):
    return _inv_ok(
        lambda: inv_reports.warehouse_summary(search=q),
        error_code="WAREHOUSE_SUMMARY_ERROR",
    )


@router.get(
    "/supplier-balance",
    dependencies=[Depends(require_any_permission(*_INV_REPORT_PERMS))],
)
def supplier_balance_route(
    q: str = Query(""),
    min_balance: float = Query(0),
):
    return _inv_ok(
        lambda: inv_reports.supplier_balance(search=q, min_balance=min_balance),
        error_code="SUPPLIER_BALANCE_ERROR",
    )


@router.get(
    "/inventory-aging",
    dependencies=[Depends(require_any_permission(*_INV_REPORT_PERMS))],
)
def inventory_aging_route(
    as_on_date: str = Query(""),
    q: str = Query(""),
    warehouse_id: str = Query(""),
):
    return _inv_ok(
        lambda: inv_reports.inventory_aging(
            as_on_date=as_on_date,
            search=q,
            warehouse_id=warehouse_id,
        ),
        error_code="INVENTORY_AGING_ERROR",
    )


@router.get(
    "/stock-summary",
    dependencies=[Depends(require_any_permission(*_INV_REPORT_PERMS))],
)
def stock_summary_route(
    q: str = Query(""),
    warehouse_id: str = Query(""),
    include_zero: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
):
    return _inv_ok(
        lambda: inv_reports.stock_summary(
            search=q,
            warehouse_id=warehouse_id,
            include_zero=include_zero,
            limit=limit,
        ),
        error_code="STOCK_SUMMARY_ERROR",
    )


@router.get(
    "/stock-ledger",
    dependencies=[Depends(require_any_permission(*_INV_REPORT_PERMS))],
)
def stock_ledger_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    q: str = Query(""),
    item_code: str = Query(""),
    report_mode: str = Query("detail"),
    limit: int = Query(500, ge=1, le=2000),
):
    return _inv_ok(
        lambda: inv_reports.stock_ledger(
            date_from=date_from,
            date_to=date_to,
            search=q,
            item_code=item_code,
            report_mode=report_mode,
            limit=limit,
        ),
        error_code="STOCK_LEDGER_ERROR",
    )


@router.get(
    "/inventory-history",
    dependencies=[Depends(require_any_permission(*_INV_REPORT_PERMS))],
)
def inventory_history_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    q: str = Query(""),
    item_code: str = Query(""),
    limit: int = Query(500, ge=1, le=2000),
):
    return _inv_ok(
        lambda: inv_reports.inventory_history(
            date_from=date_from,
            date_to=date_to,
            search=q,
            item_code=item_code,
            limit=limit,
        ),
        error_code="INVENTORY_HISTORY_ERROR",
    )


@router.get(
    "/sales-details",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def sales_details_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    bill_no: str = Query(""),
    order_no: str = Query(""),
    customer_code: str = Query(""),
    bill_type: str = Query(""),
    txn_kind: str = Query("all"),
    item_code: str = Query(""),
    limit: int = Query(500, ge=1, le=2000),
):
    return _inv_ok(
        lambda: sales_details_reports.get_sales_details(
            date_from=date_from,
            date_to=date_to,
            bill_no=bill_no,
            order_no=order_no,
            customer_code=customer_code,
            bill_type=bill_type,
            txn_kind=txn_kind,
            item_code=item_code,
            limit=limit,
        ),
        error_code="SALES_DETAILS_ERROR",
    )


@router.get(
    "/sales-details/customers",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def sales_details_customers_route(q: str = Query(""), limit: int = Query(300, ge=1, le=800)):
    return _inv_ok(
        lambda: {"customers": sales_details_reports.list_sales_detail_customers(search=q, limit=limit)},
        error_code="SALES_DETAILS_CUSTOMERS_ERROR",
    )


@router.get(
    "/sales-details/items",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def sales_details_items_route(q: str = Query(""), limit: int = Query(300, ge=1, le=800)):
    return _inv_ok(
        lambda: {"items": sales_details_reports.list_sales_detail_items(search=q, limit=limit)},
        error_code="SALES_DETAILS_ITEMS_ERROR",
    )


@router.get(
    "/customer-wise-sales",
    dependencies=[Depends(require_any_permission(*_CWS_REPORT_PERMS))],
)
def customer_wise_sales_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    customer_code: str = Query(""),
    bill_type: str = Query(""),
):
    return _inv_ok(
        lambda: cws_reports.get_customer_wise_sales(
            date_from=date_from,
            date_to=date_to,
            customer_code=customer_code,
            bill_type=bill_type,
        ),
        error_code="CUSTOMER_WISE_SALES_ERROR",
    )


@router.get(
    "/sales-details/pdf",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def sales_details_pdf_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    bill_no: str = Query(""),
    order_no: str = Query(""),
    customer_code: str = Query(""),
    bill_type: str = Query(""),
    txn_kind: str = Query("all"),
    item_code: str = Query(""),
    limit: int = Query(800, ge=1, le=2000),
):
    try:
        pdf_bytes, filename = sales_details_reports.build_sales_details_pdf(
            date_from=date_from,
            date_to=date_to,
            bill_no=bill_no,
            order_no=order_no,
            customer_code=customer_code,
            bill_type=bill_type,
            txn_kind=txn_kind,
            item_code=item_code,
            limit=limit,
        )
    except ValueError as exc:
        return failure(str(exc)[:500], status_code=400, error_code="SALES_DETAILS_PDF_ERROR")
    except Exception as exc:
        logger.exception("Sales details PDF error")
        return failure(str(exc)[:500], status_code=500, error_code="SALES_DETAILS_PDF_ERROR")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/transactions/summary",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def transactions_summary_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    transaction_types: str = Query(""),
):
    return _inv_ok(
        lambda: tx_reports.get_transaction_summary(
            date_from=date_from,
            date_to=date_to,
            transaction_types=transaction_types,
        ),
        error_code="TX_SUMMARY_ERROR",
    )


@router.get(
    "/transactions/details",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def transactions_details_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    transaction_types: str = Query(""),
    q: str = Query(""),
    limit: int = Query(400, ge=1, le=2000),
):
    return _inv_ok(
        lambda: tx_reports.get_transaction_details(
            date_from=date_from,
            date_to=date_to,
            transaction_types=transaction_types,
            search=q,
            limit=limit,
        ),
        error_code="TX_DETAILS_ERROR",
    )


@router.get(
    "/transactions/summary/pdf",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def transactions_summary_pdf_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    transaction_types: str = Query(""),
):
    try:
        pdf_bytes, filename = tx_reports.build_transaction_summary_pdf(
            date_from=date_from,
            date_to=date_to,
            transaction_types=transaction_types,
        )
    except ValueError as exc:
        return failure(str(exc)[:500], status_code=400, error_code="TX_SUMMARY_PDF_ERROR")
    except Exception as exc:
        logger.exception("TX summary PDF error")
        return failure(str(exc)[:500], status_code=500, error_code="TX_SUMMARY_PDF_ERROR")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/transactions/details/pdf",
    dependencies=[Depends(require_any_permission(*_TX_REPORT_PERMS))],
)
def transactions_details_pdf_route(
    date_from: str = Query(""),
    date_to: str = Query(""),
    transaction_types: str = Query(""),
    q: str = Query(""),
    limit: int = Query(300, ge=1, le=500),
):
    try:
        pdf_bytes, filename = tx_reports.build_transaction_details_pdf(
            date_from=date_from,
            date_to=date_to,
            transaction_types=transaction_types,
            search=q,
            limit=limit,
        )
    except ValueError as exc:
        return failure(str(exc)[:500], status_code=400, error_code="TX_DETAILS_PDF_ERROR")
    except Exception as exc:
        logger.exception("TX details PDF error")
        return failure(str(exc)[:500], status_code=500, error_code="TX_DETAILS_PDF_ERROR")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/x-report/open",
    dependencies=[Depends(require_any_permission(*_X_REPORT_PERMS))],
)
def x_report_open_route():
    return _inv_ok(x_reports.get_open_context, error_code="X_REPORT_OPEN_ERROR")


@router.get(
    "/x-report",
    dependencies=[Depends(require_any_permission(*_X_REPORT_PERMS))],
)
def x_report_route(
    counter_code: int = Query(0, ge=0),
    pos_date: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    final: int = Query(0, ge=0, le=1),
):
    return _inv_ok(
        lambda: x_reports.get_x_report(
            counter_code=counter_code,
            pos_date=pos_date,
            date_from=date_from,
            date_to=date_to,
            is_final=bool(final),
        ),
        error_code="X_REPORT_ERROR",
    )


@router.get(
    "/x-report/pdf",
    dependencies=[Depends(require_any_permission(*_X_REPORT_PERMS))],
)
def x_report_pdf_route(
    counter_code: int = Query(0, ge=0),
    pos_date: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    final: int = Query(0, ge=0, le=1),
):
    try:
        pdf_bytes, filename = x_reports.build_x_report_pdf(
            counter_code=counter_code,
            pos_date=pos_date,
            date_from=date_from,
            date_to=date_to,
            is_final=bool(final),
        )
    except ValueError as exc:
        return failure(str(exc)[:500], status_code=400, error_code="X_REPORT_PDF_ERROR")
    except Exception as exc:
        logger.exception("X Report PDF error")
        return failure(str(exc)[:500], status_code=500, error_code="X_REPORT_PDF_ERROR")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
