import 'dart:async';

import '../core/storage/local_cache.dart';
import '../models/dashboard_summary.dart';
import '../services/dashboard_service.dart';

class DashboardRepository {
  DashboardRepository(this._service, this._cache);

  final DashboardService _service;
  final LocalCache _cache;

  static const _cacheKeyPrefix = 'dashboard_summary';

  String _cacheKey(String dateFrom, String dateTo) {
    final df = dateFrom.trim();
    final dt = dateTo.trim();
    if (df.isEmpty && dt.isEmpty) return _cacheKeyPrefix;
    return '${_cacheKeyPrefix}_${df}_$dt';
  }

  Map<String, dynamic> _toCacheMap(DashboardSummary summary) => {
        'total_items': summary.totalItems,
        'today_sales': summary.todaySales,
        'customer_count': summary.customerCount,
        'active_customers': summary.customerCount,
        'total_stock_qty': summary.totalStockQty,
        'out_of_stock_items': summary.outOfStockItems,
        'low_stock_items': summary.lowStockItems,
        'stock_value': summary.stockValue,
        'billhdr_rows_today': summary.billHdrRowsToday,
        'branch_name': summary.branchName,
        'period_label': summary.periodLabel,
        'date_from': summary.dateFrom,
        'date_to': summary.dateTo,
        'yesterday_sales': summary.yesterdaySales,
        'sales_trend_pct': summary.salesTrendPct,
        'invoice_count': summary.invoiceCount,
        'invoice_trend_pct': summary.invoiceTrendPct,
        'cash_sales': summary.cashSales,
        'credit_sales': summary.creditSales,
        'amount_collected': summary.amountCollected,
        'outstanding_amount': summary.outstandingAmount,
        'collection_pct': summary.collectionPct,
        'sales_return': summary.salesReturn,
        'sales_orders_today': summary.salesOrdersToday,
        'new_customers_today': summary.newCustomersToday,
        'purchases': summary.purchases,
        'expenses': summary.expenses,
        'gross_profit': summary.grossProfit,
        'net_profit': summary.netProfit,
        'purchases_trend_pct': summary.purchasesTrendPct,
        'expenses_trend_pct': summary.expensesTrendPct,
        'gross_profit_trend_pct': summary.grossProfitTrendPct,
        'net_profit_trend_pct': summary.netProfitTrendPct,
        'inventory_value': summary.inventoryValue,
        'items_in_stock': summary.itemsInStock,
        'receivables_overdue': summary.receivablesOverdue,
        'receivables_not_due': summary.receivablesNotDue,
        'payables_total': summary.payablesTotal,
        'payables_overdue': summary.payablesOverdue,
        'payables_not_due': summary.payablesNotDue,
        'cash_balance': summary.cashBalance,
        'bank_balance': summary.bankBalance,
        'cash_bank_total': summary.cashBankTotal,
        'return_count': summary.returnCount,
        'visits_today': summary.visitsToday,
        'top_customers': summary.topCustomers
            .map((c) => {
                  'code': c.code,
                  'name': c.name,
                  'sales': c.sales,
                  'invoices': c.invoices,
                })
            .toList(),
        'recent_activity': summary.recentActivity
            .map((a) => {
                  'type': a.type,
                  'title': a.title,
                  'subtitle': a.subtitle,
                  'ref': a.ref,
                  'time': a.time,
                  'amount': a.amount,
                  'signed': a.signed,
                })
            .toList(),
        'alerts': summary.alerts
            .map((a) => {
                  'severity': a.severity,
                  'title': a.title,
                  'subtitle': a.subtitle,
                })
            .toList(),
        'recent_receipts': summary.recentReceipts
            .map((r) => {
                  'receipt_no': r.receiptNo,
                  'po_no': r.poNo,
                  'supplier': r.supplier,
                  'invoice_no': r.invoiceNo,
                  'receipt_date': r.receiptDate,
                  'amount': r.amount,
                  'status': r.status,
                })
            .toList(),
      };

  Future<DashboardSummary?> readSummaryCache({
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final cached = await _cache.getJsonMap(_cacheKey(dateFrom, dateTo));
    if (cached == null) return null;
    return DashboardSummary.fromJson(cached);
  }

  Future<DashboardSummary> getSummary({
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final key = _cacheKey(dateFrom, dateTo);
    try {
      final summary = await _service.getSummary(
        dateFrom: dateFrom.isEmpty ? null : dateFrom,
        dateTo: dateTo.isEmpty ? null : dateTo,
      );
      unawaited(_cache.saveJson(key, _toCacheMap(summary)));
      return summary;
    } catch (_) {
      final cached = await _cache.getJsonMap(key);
      if (cached == null) rethrow;
      return DashboardSummary.fromJson(cached);
    }
  }
}
