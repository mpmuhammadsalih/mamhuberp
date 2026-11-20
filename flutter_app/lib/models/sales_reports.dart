class SalesReportsSummary {
  SalesReportsSummary({
    required this.totalSales,
    required this.invoiceCount,
    required this.returnAmount,
    required this.avgTicket,
    required this.todaySales,
    required this.todayInvoices,
    required this.prevPeriodSales,
    required this.prevInvoiceCount,
    this.salesChangePct,
    this.invoiceChangePct,
  });

  final double totalSales;
  final int invoiceCount;
  final double returnAmount;
  final double avgTicket;
  final double todaySales;
  final int todayInvoices;
  final double prevPeriodSales;
  final int prevInvoiceCount;
  final double? salesChangePct;
  final double? invoiceChangePct;

  factory SalesReportsSummary.fromJson(Map<String, dynamic>? json) {
    final m = json ?? const {};
    return SalesReportsSummary(
      totalSales: _num(m['total_sales']),
      invoiceCount: _int(m['invoice_count']),
      returnAmount: _num(m['return_amount']),
      avgTicket: _num(m['avg_ticket']),
      todaySales: _num(m['today_sales']),
      todayInvoices: _int(m['today_invoices']),
      prevPeriodSales: _num(m['prev_period_sales']),
      prevInvoiceCount: _int(m['prev_invoice_count']),
      salesChangePct: _numOrNull(m['sales_change_pct']),
      invoiceChangePct: _numOrNull(m['invoice_change_pct']),
    );
  }
}

class SalesDailyPoint {
  SalesDailyPoint({required this.date, required this.amount, required this.invoices});

  final String date;
  final double amount;
  final int invoices;

  factory SalesDailyPoint.fromJson(Map<String, dynamic> json) => SalesDailyPoint(
        date: '${json['date'] ?? ''}',
        amount: _num(json['amount']),
        invoices: _int(json['invoices']),
      );
}

class SalesWeekComparePoint {
  SalesWeekComparePoint({
    required this.day,
    required this.date,
    required this.current,
    required this.previous,
  });

  final String day;
  final String date;
  final double current;
  final double previous;

  factory SalesWeekComparePoint.fromJson(Map<String, dynamic> json) => SalesWeekComparePoint(
        day: '${json['day'] ?? ''}',
        date: '${json['date'] ?? ''}',
        current: _num(json['current']),
        previous: _num(json['previous']),
      );
}

class SalesTopCustomer {
  SalesTopCustomer({required this.name, required this.amount, required this.invoices});

  final String name;
  final double amount;
  final int invoices;

  factory SalesTopCustomer.fromJson(Map<String, dynamic> json) => SalesTopCustomer(
        name: '${json['name'] ?? '—'}',
        amount: _num(json['amount']),
        invoices: _int(json['invoices']),
      );
}

class SalesTopItem {
  SalesTopItem({required this.name, required this.qty, required this.amount});

  final String name;
  final double qty;
  final double amount;

  factory SalesTopItem.fromJson(Map<String, dynamic> json) => SalesTopItem(
        name: '${json['name'] ?? '—'}',
        qty: _num(json['qty']),
        amount: _num(json['amount']),
      );
}

class SalesReportsData {
  SalesReportsData({
    required this.periodDays,
    required this.dateFrom,
    required this.dateTo,
    required this.summary,
    required this.dailyTrend,
    required this.weekComparison,
    required this.topCustomers,
    required this.topItems,
    this.error,
  });

  final int periodDays;
  final String dateFrom;
  final String dateTo;
  final SalesReportsSummary summary;
  final List<SalesDailyPoint> dailyTrend;
  final List<SalesWeekComparePoint> weekComparison;
  final List<SalesTopCustomer> topCustomers;
  final List<SalesTopItem> topItems;
  final String? error;

  factory SalesReportsData.fromJson(Map<String, dynamic> json) => SalesReportsData(
        periodDays: _int(json['period_days']),
        dateFrom: '${json['date_from'] ?? ''}',
        dateTo: '${json['date_to'] ?? ''}',
        summary: SalesReportsSummary.fromJson(json['summary'] as Map<String, dynamic>?),
        dailyTrend: (json['daily_trend'] as List<dynamic>?)
                ?.map((e) => SalesDailyPoint.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        weekComparison: (json['week_comparison'] as List<dynamic>?)
                ?.map((e) => SalesWeekComparePoint.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        topCustomers: (json['top_customers'] as List<dynamic>?)
                ?.map((e) => SalesTopCustomer.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        topItems: (json['top_items'] as List<dynamic>?)
                ?.map((e) => SalesTopItem.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        error: json['error'] as String?,
      );
}

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? 0;
}

double? _numOrNull(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse('$v');
}

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? 0;
}
