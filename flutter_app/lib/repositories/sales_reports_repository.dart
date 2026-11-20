import '../core/storage/local_cache.dart';
import '../models/sales_reports.dart';
import '../services/sales_service.dart';

class SalesReportsRepository {
  SalesReportsRepository(this._service, this._cache);

  final SalesService _service;
  final LocalCache _cache;

  static const _cacheMaxAge = Duration(minutes: 5);

  String _cacheKey(String from, String to) => 'sales_reports_${from}_$to';

  Future<SalesReportsData?> readCache(String dateFrom, String dateTo) async {
    final cached = await _cache.getJsonMap(_cacheKey(dateFrom, dateTo));
    if (cached == null) return null;
    return SalesReportsData.fromJson(cached);
  }

  Future<bool> isCacheFresh(String dateFrom, String dateTo) async {
    final updated = await _cache.getUpdatedAt(_cacheKey(dateFrom, dateTo));
    if (updated == null) return false;
    return DateTime.now().difference(updated) < _cacheMaxAge;
  }

  Future<SalesReportsData> getReports({
    required String dateFrom,
    required String dateTo,
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh && await isCacheFresh(dateFrom, dateTo)) {
      final cached = await readCache(dateFrom, dateTo);
      if (cached != null) return cached;
    }
    try {
      final data = await _service.getReports(dateFrom: dateFrom, dateTo: dateTo);
      await _cache.saveJson(_cacheKey(dateFrom, dateTo), _toCacheMap(data));
      return data;
    } catch (_) {
      final cached = await readCache(dateFrom, dateTo);
      if (cached != null) return cached;
      rethrow;
    }
  }

  Map<String, dynamic> _toCacheMap(SalesReportsData d) => {
        'period_days': d.periodDays,
        'date_from': d.dateFrom,
        'date_to': d.dateTo,
        'error': d.error,
        'summary': {
          'total_sales': d.summary.totalSales,
          'invoice_count': d.summary.invoiceCount,
          'return_amount': d.summary.returnAmount,
          'avg_ticket': d.summary.avgTicket,
          'today_sales': d.summary.todaySales,
          'today_invoices': d.summary.todayInvoices,
          'prev_period_sales': d.summary.prevPeriodSales,
          'prev_invoice_count': d.summary.prevInvoiceCount,
          'sales_change_pct': d.summary.salesChangePct,
          'invoice_change_pct': d.summary.invoiceChangePct,
        },
        'daily_trend': d.dailyTrend
            .map((p) => {'date': p.date, 'amount': p.amount, 'invoices': p.invoices})
            .toList(),
        'week_comparison': d.weekComparison
            .map((p) => {
                  'day': p.day,
                  'date': p.date,
                  'current': p.current,
                  'previous': p.previous,
                })
            .toList(),
        'top_customers': d.topCustomers
            .map((c) => {'name': c.name, 'amount': c.amount, 'invoices': c.invoices})
            .toList(),
        'top_items': d.topItems.map((i) => {'name': i.name, 'qty': i.qty, 'amount': i.amount}).toList(),
      };
}
