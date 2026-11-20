import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

String _str(dynamic v) => '${v ?? ''}'.trim();

List<double> _numList(dynamic v) {
  if (v is! List) return const [0, 0, 0];
  final out = v.map(_num).toList();
  while (out.length < 3) {
    out.add(0);
  }
  return out.take(3).toList();
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class TrialBalanceRow {
  TrialBalanceRow({
    required this.code,
    required this.name,
    required this.type,
    required this.debit,
    required this.credit,
    required this.openingBalance,
    required this.balance,
  });

  final String code;
  final String name;
  final String type;
  final double debit;
  final double credit;
  final double openingBalance;
  final double balance;

  factory TrialBalanceRow.fromJson(Map<String, dynamic> json) => TrialBalanceRow(
        code: _str(json['code']),
        name: _str(json['name']),
        type: _str(json['type']),
        debit: _num(json['debit']),
        credit: _num(json['credit']),
        openingBalance: _num(json['opening_balance']),
        balance: _num(json['balance']),
      );
}

class TrialBalanceReport {
  TrialBalanceReport({
    required this.companyName,
    required this.periodDisplay,
    required this.dateFrom,
    required this.dateTo,
    required this.rows,
    required this.totalDebit,
    required this.totalCredit,
    required this.excludeClosing,
  });

  final String companyName;
  final String periodDisplay;
  final String dateFrom;
  final String dateTo;
  final List<TrialBalanceRow> rows;
  final double totalDebit;
  final double totalCredit;
  final bool excludeClosing;

  factory TrialBalanceReport.fromJson(Map<String, dynamic> json) => TrialBalanceReport(
        companyName: _str(json['company_name']),
        periodDisplay: _str(json['period_display']),
        dateFrom: _str(json['date_from']),
        dateTo: _str(json['date_to']),
        rows: (json['rows'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => TrialBalanceRow.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        totalDebit: _num(json['total_debit']),
        totalCredit: _num(json['total_credit']),
        excludeClosing: json['exclude_closing'] != false,
      );
}

class PlAccountRow {
  PlAccountRow({
    required this.code,
    required this.name,
    required this.amounts,
  });

  final String code;
  final String name;
  final List<double> amounts;

  double get current => amounts.isNotEmpty ? amounts.last : 0;

  factory PlAccountRow.fromJson(Map<String, dynamic> json) => PlAccountRow(
        code: _str(json['code']),
        name: _str(json['name']),
        amounts: _numList(json['amounts']),
      );
}

class ProfitLossReport {
  ProfitLossReport({
    required this.companyName,
    required this.periodLabels,
    required this.revenueRows,
    required this.costOfSalesRows,
    required this.operatingExpenseRows,
    required this.totalRevenue,
    required this.totalCostOfSales,
    required this.totalOperatingExpense,
    required this.grossProfit,
    required this.netProfit,
    required this.dateFrom,
    required this.dateTo,
    required this.dateFromDisplay,
    required this.dateToDisplay,
    required this.excludeClosing,
  });

  final String companyName;
  final List<String> periodLabels;
  final List<PlAccountRow> revenueRows;
  final List<PlAccountRow> costOfSalesRows;
  final List<PlAccountRow> operatingExpenseRows;
  final List<double> totalRevenue;
  final List<double> totalCostOfSales;
  final List<double> totalOperatingExpense;
  final List<double> grossProfit;
  final List<double> netProfit;
  final String dateFrom;
  final String dateTo;
  final String dateFromDisplay;
  final String dateToDisplay;
  final bool excludeClosing;

  factory ProfitLossReport.fromJson(Map<String, dynamic> json) {
    List<PlAccountRow> rows(dynamic key) => (json[key] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PlAccountRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();

    final labels = (json['period_labels'] as List<dynamic>? ?? const [])
        .map((e) => _str(e))
        .toList();
    while (labels.length < 3) {
      labels.add('');
    }

    return ProfitLossReport(
      companyName: _str(json['company_name']),
      periodLabels: labels,
      revenueRows: rows('revenue_rows'),
      costOfSalesRows: rows('cost_of_sales_rows'),
      operatingExpenseRows: rows('operating_expense_rows').isNotEmpty
          ? rows('operating_expense_rows')
          : rows('expense_rows'),
      totalRevenue: _numList(json['total_revenue']),
      totalCostOfSales: _numList(json['total_cost_of_sales']),
      totalOperatingExpense: _numList(json['total_operating_expense']),
      grossProfit: _numList(json['gross_profit']),
      netProfit: _numList(json['net_profit']),
      dateFrom: _str(json['date_from']),
      dateTo: _str(json['date_to']),
      dateFromDisplay: _str(json['date_from_display']),
      dateToDisplay: _str(json['date_to_display']),
      excludeClosing: json['exclude_closing'] != false,
    );
  }
}

class BalanceSheetRow {
  BalanceSheetRow({
    required this.code,
    required this.name,
    required this.amount,
    required this.depth,
    required this.isGroup,
  });

  final String code;
  final String name;
  final double amount;
  final int depth;
  final bool isGroup;

  factory BalanceSheetRow.fromJson(Map<String, dynamic> json) => BalanceSheetRow(
        code: _str(json['code']),
        name: _str(json['name']),
        amount: _num(json['amount'] ?? json['balance'] ?? json['closing']),
        depth: (_num(json['depth'])).round(),
        isGroup: json['is_group'] == true,
      );
}

class BalanceSheetReport {
  BalanceSheetReport({
    required this.companyName,
    required this.asOfDate,
    required this.asOfDateDisplay,
    required this.assetAccounts,
    required this.liabilityAccounts,
    required this.equityAccounts,
    required this.totalAssets,
    required this.totalLiabilities,
    required this.totalEquity,
    required this.liabilitiesPlusEquity,
    required this.difference,
  });

  final String companyName;
  final String asOfDate;
  final String asOfDateDisplay;
  final List<BalanceSheetRow> assetAccounts;
  final List<BalanceSheetRow> liabilityAccounts;
  final List<BalanceSheetRow> equityAccounts;
  final double totalAssets;
  final double totalLiabilities;
  final double totalEquity;
  final double liabilitiesPlusEquity;
  final double difference;

  factory BalanceSheetReport.fromJson(Map<String, dynamic> json) {
    List<BalanceSheetRow> section(String key) => (json[key] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => BalanceSheetRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();

    return BalanceSheetReport(
      companyName: _str(json['company_name']),
      asOfDate: _str(json['as_of_date']),
      asOfDateDisplay: _str(json['as_of_date_display']),
      assetAccounts: section('asset_accounts'),
      liabilityAccounts: section('liability_accounts'),
      equityAccounts: section('equity_accounts'),
      totalAssets: _num(json['total_assets']),
      totalLiabilities: _num(json['total_liabilities']),
      totalEquity: _num(json['total_equity']),
      liabilitiesPlusEquity: _num(json['liabilities_plus_equity']),
      difference: _num(json['difference']),
    );
  }
}

class AccountsReportsService {
  AccountsReportsService(this._apiClient);

  final ApiClient _apiClient;

  static Options get _reportOptions => Options(
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 30),
      );

  Future<TrialBalanceReport> getTrialBalance({
    required String dateFrom,
    required String dateTo,
    bool excludeClosing = true,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/trial-balance',
      queryParameters: {
        'date_from': dateFrom,
        'date_to': dateTo,
        'exclude_closing': excludeClosing,
      },
      options: _reportOptions,
    );
    return TrialBalanceReport.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadTrialBalancePdf({
    required String dateFrom,
    required String dateTo,
    bool excludeClosing = true,
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/trial-balance/pdf',
      queryParameters: {
        'date_from': dateFrom,
        'date_to': dateTo,
        'exclude_closing': excludeClosing,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) throw Exception('Empty PDF response.');
    return bytes;
  }

  Future<ProfitLossReport> getProfitLoss({
    required String dateFrom,
    required String dateTo,
    bool excludeClosing = true,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/profit-loss',
      queryParameters: {
        'date_from': dateFrom,
        'date_to': dateTo,
        'exclude_closing': excludeClosing,
      },
      options: _reportOptions,
    );
    return ProfitLossReport.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadProfitLossPdf({
    required String dateFrom,
    required String dateTo,
    bool excludeClosing = true,
    String pdfMode = 'single',
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/profit-loss/pdf',
      queryParameters: {
        'date_from': dateFrom,
        'date_to': dateTo,
        'exclude_closing': excludeClosing,
        'pdf_mode': pdfMode,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) throw Exception('Empty PDF response.');
    return bytes;
  }

  Future<BalanceSheetReport> getBalanceSheet({required String asOfDate}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/balance-sheet',
      queryParameters: {'as_of_date': asOfDate},
      options: _reportOptions,
    );
    return BalanceSheetReport.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadBalanceSheetPdf({
    required String asOfDate,
    String layout = 'single',
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/balance-sheet/pdf',
      queryParameters: {
        'as_of_date': asOfDate,
        'layout': layout,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) throw Exception('Empty PDF response.');
    return bytes;
  }
}
