import '../core/storage/local_cache.dart';
import '../models/business_summary.dart';
import '../services/reports_service.dart';

class BusinessSummaryRepository {
  BusinessSummaryRepository(this._service, this._cache);

  final ReportsService _service;
  final LocalCache _cache;

  String _cacheKey(String from, String to) => 'business_summary_${from}_$to';

  static const _cacheMaxAge = Duration(minutes: 5);

  Future<BusinessSummaryData?> readCache(String dateFrom, String dateTo) async {
    final cached = await _cache.getJsonMap(_cacheKey(dateFrom, dateTo));
    if (cached == null) return null;
    return BusinessSummaryData.fromJson(cached);
  }

  Future<bool> isCacheFresh(String dateFrom, String dateTo) async {
    final updated = await _cache.getUpdatedAt(_cacheKey(dateFrom, dateTo));
    if (updated == null) return false;
    return DateTime.now().difference(updated) < _cacheMaxAge;
  }

  Future<BusinessSummaryData> getSummary({
    required String dateFrom,
    required String dateTo,
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh && await isCacheFresh(dateFrom, dateTo)) {
      final cached = await readCache(dateFrom, dateTo);
      if (cached != null) return cached;
    }
    try {
      final data = await _service.getBusinessSummary(dateFrom: dateFrom, dateTo: dateTo);
      await _cache.saveJson(_cacheKey(dateFrom, dateTo), _toCacheMap(data));
      return data;
    } catch (_) {
      final cached = await readCache(dateFrom, dateTo);
      if (cached != null) return cached;
      rethrow;
    }
  }

  Map<String, dynamic> _toCacheMap(BusinessSummaryData d) => {
        'generated_at': d.generatedAt,
        'filters': {'date_from': d.dateFrom, 'date_to': d.dateTo},
        'warnings': d.warnings,
        'kpis': d.kpis
            .map((k) => {'id': k.id, 'label': k.label, 'value': k.value, 'format': k.format})
            .toList(),
        'charts': {
          'sales_vs_purchase_trend': {
            'labels': d.charts.trendLabels,
            'sales': d.charts.trendSales,
            'purchase': d.charts.trendPurchase,
          },
          'sales_vs_gross_profit': {
            'labels': d.charts.salesVsProfitLabels,
            'values': d.charts.salesVsProfitValues,
          },
          'daily_sales_trend':
              d.charts.dailySales.map((p) => {'date': p.date, 'amount': p.amount}).toList(),
          'top_customers': d.charts.topCustomers
              .map((e) => {'code': e.code, 'name': e.name, 'amount': e.amount})
              .toList(),
          'top_items':
              d.charts.topItems.map((e) => {'code': e.code, 'name': e.name, 'amount': e.amount}).toList(),
          'category_sales': d.charts.categorySales
              .map((e) => {'code': e.code, 'name': e.name, 'amount': e.amount})
              .toList(),
          'payment_methods': d.charts.paymentMethods
              .map((e) => {'code': e.code, 'name': e.name, 'amount': e.amount})
              .toList(),
        },
        'transaction_summary': d.transactions
            .map((t) => {
                  'transaction': t.transaction,
                  'count': t.count,
                  'amount': t.amount,
                  'percentage': t.percentage,
                })
            .toList(),
        'financial': {
          'net_sales': d.financial.netSales,
          'gross_profit': d.financial.grossProfit,
          'gross_profit_pct': d.financial.grossProfitPct,
          'net_purchases': d.financial.netPurchases,
          'expense_total': d.financial.expenseTotal,
          'net_profit': d.financial.netProfit,
        },
      };
}
