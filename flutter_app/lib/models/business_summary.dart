class BusinessSummaryKpi {
  BusinessSummaryKpi({
    required this.id,
    required this.label,
    required this.value,
    required this.format,
  });

  final String id;
  final String label;
  final double value;
  final String format;

  factory BusinessSummaryKpi.fromJson(Map<String, dynamic> json) => BusinessSummaryKpi(
        id: '${json['id'] ?? ''}',
        label: '${json['label'] ?? ''}',
        value: _num(json['value']),
        format: '${json['format'] ?? 'currency'}',
      );
}

class BusinessSummaryEntity {
  BusinessSummaryEntity({
    required this.code,
    required this.name,
    required this.amount,
  });

  final String code;
  final String name;
  final double amount;

  String get displayName {
    final n = name.trim();
    if (n.isNotEmpty) return n;
    return code.trim().isNotEmpty ? code : '—';
  }

  factory BusinessSummaryEntity.fromJson(Map<String, dynamic> json) => BusinessSummaryEntity(
        code: '${json['code'] ?? ''}',
        name: '${json['name'] ?? ''}',
        amount: _num(json['amount']),
      );
}

class BusinessSummaryDailyPoint {
  BusinessSummaryDailyPoint({required this.date, required this.amount});

  final String date;
  final double amount;

  factory BusinessSummaryDailyPoint.fromJson(Map<String, dynamic> json) => BusinessSummaryDailyPoint(
        date: '${json['date'] ?? ''}',
        amount: _num(json['amount']),
      );
}

class BusinessSummaryTransactionRow {
  BusinessSummaryTransactionRow({
    required this.transaction,
    required this.count,
    required this.amount,
    required this.percentage,
  });

  final String transaction;
  final int count;
  final double amount;
  final double percentage;

  factory BusinessSummaryTransactionRow.fromJson(Map<String, dynamic> json) =>
      BusinessSummaryTransactionRow(
        transaction: '${json['transaction'] ?? ''}',
        count: _int(json['count']),
        amount: _num(json['amount']),
        percentage: _num(json['percentage']),
      );
}

class BusinessSummaryFinancial {
  BusinessSummaryFinancial({
    required this.netSales,
    required this.grossProfit,
    required this.grossProfitPct,
    required this.netPurchases,
    required this.expenseTotal,
    required this.netProfit,
  });

  final double netSales;
  final double grossProfit;
  final double grossProfitPct;
  final double netPurchases;
  final double expenseTotal;
  final double netProfit;

  factory BusinessSummaryFinancial.fromJson(Map<String, dynamic>? json) {
    final m = json ?? const {};
    return BusinessSummaryFinancial(
      netSales: _num(m['net_sales']),
      grossProfit: _num(m['gross_profit']),
      grossProfitPct: _num(m['gross_profit_pct']),
      netPurchases: _num(m['net_purchases']),
      expenseTotal: _num(m['expense_total']),
      netProfit: _num(m['net_profit']),
    );
  }
}

class BusinessSummaryCharts {
  BusinessSummaryCharts({
    required this.trendLabels,
    required this.trendSales,
    required this.trendPurchase,
    required this.dailySales,
    required this.topCustomers,
    required this.topItems,
    required this.categorySales,
    required this.paymentMethods,
    required this.salesVsProfitLabels,
    required this.salesVsProfitValues,
  });

  final List<String> trendLabels;
  final List<double> trendSales;
  final List<double> trendPurchase;
  final List<BusinessSummaryDailyPoint> dailySales;
  final List<BusinessSummaryEntity> topCustomers;
  final List<BusinessSummaryEntity> topItems;
  final List<BusinessSummaryEntity> categorySales;
  final List<BusinessSummaryEntity> paymentMethods;
  final List<String> salesVsProfitLabels;
  final List<double> salesVsProfitValues;

  factory BusinessSummaryCharts.fromJson(Map<String, dynamic>? json) {
    final m = json ?? const {};
    final trend = m['sales_vs_purchase_trend'] as Map<String, dynamic>? ?? const {};
    final profit = m['sales_vs_gross_profit'] as Map<String, dynamic>? ?? const {};
    return BusinessSummaryCharts(
      trendLabels: (trend['labels'] as List<dynamic>?)?.map((e) => '$e').toList() ?? const [],
      trendSales: (trend['sales'] as List<dynamic>?)?.map(_num).toList() ?? const [],
      trendPurchase: (trend['purchase'] as List<dynamic>?)?.map(_num).toList() ?? const [],
      dailySales: (m['daily_sales_trend'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryDailyPoint.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      topCustomers: (m['top_customers'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryEntity.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      topItems: (m['top_items'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryEntity.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      categorySales: (m['category_sales'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryEntity.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      paymentMethods: (m['payment_methods'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryEntity.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      salesVsProfitLabels:
          (profit['labels'] as List<dynamic>?)?.map((e) => '$e').toList() ?? const [],
      salesVsProfitValues: (profit['values'] as List<dynamic>?)?.map(_num).toList() ?? const [],
    );
  }
}

class BusinessSummaryData {
  BusinessSummaryData({
    required this.generatedAt,
    required this.dateFrom,
    required this.dateTo,
    this.branch,
    required this.kpis,
    required this.charts,
    required this.transactions,
    required this.financial,
    required this.warnings,
  });

  final String generatedAt;
  final String dateFrom;
  final String dateTo;
  final int? branch;
  final List<BusinessSummaryKpi> kpis;
  final BusinessSummaryCharts charts;
  final List<BusinessSummaryTransactionRow> transactions;
  final BusinessSummaryFinancial financial;
  final List<String> warnings;

  double? kpiValue(String id) {
    for (final k in kpis) {
      if (k.id == id) return k.value;
    }
    return null;
  }

  BusinessSummaryKpi? kpi(String id) {
    for (final k in kpis) {
      if (k.id == id) return k;
    }
    return null;
  }

  factory BusinessSummaryData.fromJson(Map<String, dynamic> json) {
    final filters = json['filters'] as Map<String, dynamic>? ?? const {};
    final branchRaw = filters['branch'];
    int? branch;
    if (branchRaw is num) {
      branch = branchRaw.toInt();
    } else if (branchRaw != null) {
      branch = int.tryParse('$branchRaw');
    }
    return BusinessSummaryData(
      generatedAt: '${json['generated_at'] ?? ''}',
      dateFrom: '${filters['date_from'] ?? ''}',
      dateTo: '${filters['date_to'] ?? ''}',
      branch: branch,
      kpis: (json['kpis'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryKpi.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      charts: BusinessSummaryCharts.fromJson(json['charts'] as Map<String, dynamic>?),
      transactions: (json['transaction_summary'] as List<dynamic>?)
              ?.whereType<Map>()
              .map((e) => BusinessSummaryTransactionRow.fromJson(Map<String, dynamic>.from(e)))
              .toList() ??
          const [],
      financial: BusinessSummaryFinancial.fromJson(json['financial'] as Map<String, dynamic>?),
      warnings: (json['warnings'] as List<dynamic>?)?.map((e) => '$e').toList() ?? const [],
    );
  }
}

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? 0;
}

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? 0;
}
