import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? 0;
}

class ArApPartyRow {
  ArApPartyRow({
    required this.partyCode,
    required this.partyName,
    required this.locationCode,
    required this.glAccount,
    required this.balance,
    this.balanceSource = '',
    this.partyInGl = false,
  });

  final String partyCode;
  final String partyName;
  final String locationCode;
  final String glAccount;
  final double balance;
  final String balanceSource;
  final bool partyInGl;

  String get displayName => partyName.isNotEmpty ? partyName : partyCode;

  factory ArApPartyRow.fromJson(Map<String, dynamic> json) => ArApPartyRow(
        partyCode: '${json['party_code'] ?? ''}'.trim(),
        partyName: '${json['party_name'] ?? ''}'.trim(),
        locationCode: '${json['location_code'] ?? ''}'.trim(),
        glAccount: '${json['gl_account'] ?? ''}'.trim(),
        balance: _num(json['balance']),
        balanceSource: '${json['balance_source'] ?? ''}'.trim(),
        partyInGl: json['party_in_gl'] == true,
      );
}

class ArApTotals {
  const ArApTotals({
    this.count = 0,
    this.outstanding = 0,
    this.positiveCount = 0,
  });

  final int count;
  final double outstanding;
  final int positiveCount;

  factory ArApTotals.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const ArApTotals();
    return ArApTotals(
      count: (json['count'] as num?)?.toInt() ?? 0,
      outstanding: _num(json['outstanding']),
      positiveCount: (json['positive_count'] as num?)?.toInt() ?? 0,
    );
  }
}

class ArApListResult {
  ArApListResult({required this.rows, required this.totals});

  final List<ArApPartyRow> rows;
  final ArApTotals totals;
}

class ArApOpenDoc {
  ArApOpenDoc({
    required this.voucherNo,
    required this.voucherDate,
    required this.orderNo,
    required this.referenceNo,
    required this.narration,
    required this.source,
    required this.invoiceAmount,
    required this.allocatedAmount,
    required this.openAmount,
    required this.isPayable,
    required this.isCredit,
    this.balanceHint = '',
  });

  final String voucherNo;
  final String voucherDate;
  final String orderNo;
  final String referenceNo;
  final String narration;
  final String source;
  final double invoiceAmount;
  final double allocatedAmount;
  final double openAmount;
  final bool isPayable;
  final bool isCredit;
  final String balanceHint;

  factory ArApOpenDoc.fromJson(Map<String, dynamic> json) => ArApOpenDoc(
        voucherNo: '${json['voucher_no'] ?? ''}'.trim(),
        voucherDate: '${json['voucher_date'] ?? ''}'.trim(),
        orderNo: '${json['orderno'] ?? ''}'.trim(),
        referenceNo: '${json['reference_no'] ?? ''}'.trim(),
        narration: '${json['narration'] ?? ''}'.trim(),
        source: '${json['source'] ?? ''}'.trim(),
        invoiceAmount: _num(json['invoice_amount']),
        allocatedAmount: _num(json['allocated_amount']),
        openAmount: _num(json['open_amount']),
        isPayable: json['is_payable'] == true,
        isCredit: json['is_credit'] == true,
        balanceHint: '${json['balance_hint'] ?? ''}'.trim(),
      );
}

class ArApPartyDetail {
  ArApPartyDetail({
    required this.partyType,
    required this.partyCode,
    required this.partyName,
    required this.locationCode,
    required this.glAccount,
    required this.balance,
    required this.openPayableTotal,
    required this.openCreditTotal,
    required this.openDocuments,
    this.balanceSource = '',
  });

  final String partyType;
  final String partyCode;
  final String partyName;
  final String locationCode;
  final String glAccount;
  final double balance;
  final double openPayableTotal;
  final double openCreditTotal;
  final List<ArApOpenDoc> openDocuments;
  final String balanceSource;

  factory ArApPartyDetail.fromJson(Map<String, dynamic> json) => ArApPartyDetail(
        partyType: '${json['party_type'] ?? ''}'.trim().toUpperCase(),
        partyCode: '${json['party_code'] ?? ''}'.trim(),
        partyName: '${json['party_name'] ?? ''}'.trim(),
        locationCode: '${json['location_code'] ?? ''}'.trim(),
        glAccount: '${json['gl_account'] ?? ''}'.trim(),
        balance: _num(json['balance']),
        openPayableTotal: _num(json['open_payable_total']),
        openCreditTotal: _num(json['open_credit_total']),
        balanceSource: '${json['balance_source'] ?? ''}'.trim(),
        openDocuments: (json['open_documents'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => ArApOpenDoc.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );
}

class ArApService {
  ArApService(this._apiClient);

  final ApiClient _apiClient;

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    final data = root['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return root;
  }

  Future<ArApListResult> listReceivables({
    String q = '',
    String balance = 'positive',
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/receivables',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'balance': balance.trim().isEmpty ? 'positive' : balance.trim(),
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    final rows = (data['rows'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => ArApPartyRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return ArApListResult(
      rows: rows,
      totals: ArApTotals.fromJson(
        data['totals'] is Map ? Map<String, dynamic>.from(data['totals'] as Map) : null,
      ),
    );
  }

  Future<ArApListResult> listPayables({
    String q = '',
    String balance = 'positive',
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/payables',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'balance': balance.trim().isEmpty ? 'positive' : balance.trim(),
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    final rows = (data['rows'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => ArApPartyRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return ArApListResult(
      rows: rows,
      totals: ArApTotals.fromJson(
        data['totals'] is Map ? Map<String, dynamic>.from(data['totals'] as Map) : null,
      ),
    );
  }

  Future<ArApPartyDetail> getReceivableDetail(String customerCode) async {
    final encoded = Uri.encodeComponent(customerCode.trim());
    final response = await _apiClient.dio.get('/api/v1/accounts/receivables/$encoded');
    return ArApPartyDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ArApPartyDetail> getPayableDetail(String supplierCode) async {
    final encoded = Uri.encodeComponent(supplierCode.trim());
    final response = await _apiClient.dio.get('/api/v1/accounts/payables/$encoded');
    return ArApPartyDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ArApPostOpenContext> getReceiptOpen(String customerCode) async {
    final encoded = Uri.encodeComponent(customerCode.trim());
    final response = await _apiClient.dio.get('/api/v1/accounts/receivables/$encoded/receipt-open');
    return ArApPostOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ArApPostOpenContext> getPaymentOpen(String supplierCode) async {
    final encoded = Uri.encodeComponent(supplierCode.trim());
    final response = await _apiClient.dio.get('/api/v1/accounts/payables/$encoded/payment-open');
    return ArApPostOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ArApPostResult> postReceivableReceipt({
    required String customerCode,
    required Map<String, dynamic> body,
  }) async {
    final encoded = Uri.encodeComponent(customerCode.trim());
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/receivables/$encoded/receipts',
      data: body,
    );
    return ArApPostResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ArApPostResult> postPayablePayment({
    required String supplierCode,
    required Map<String, dynamic> body,
  }) async {
    final encoded = Uri.encodeComponent(supplierCode.trim());
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/payables/$encoded/payments',
      data: body,
    );
    return ArApPostResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadReceivableReceiptPdf(String voucherNo) async {
    final encoded = Uri.encodeComponent(voucherNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/receivables/vouchers/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<List<int>> downloadPayablePaymentPdf(String voucherNo) async {
    final encoded = Uri.encodeComponent(voucherNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/payables/vouchers/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}

class ArApCashBankAccount {
  ArApCashBankAccount({required this.code, required this.name, required this.label});

  final String code;
  final String name;
  final String label;

  factory ArApCashBankAccount.fromJson(Map<String, dynamic> json) => ArApCashBankAccount(
        code: '${json['code'] ?? ''}'.trim(),
        name: '${json['name'] ?? ''}'.trim(),
        label: '${json['label'] ?? json['code'] ?? ''}'.trim(),
      );
}

class ArApPostOpenContext {
  ArApPostOpenContext({
    required this.detail,
    required this.cashBankAccounts,
    required this.paymentDate,
  });

  final ArApPartyDetail detail;
  final List<ArApCashBankAccount> cashBankAccounts;
  final String paymentDate;

  factory ArApPostOpenContext.fromJson(Map<String, dynamic> json) => ArApPostOpenContext(
        detail: ArApPartyDetail.fromJson(json),
        cashBankAccounts: (json['cash_bank_accounts'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => ArApCashBankAccount.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        paymentDate: '${json['payment_date'] ?? ''}'.trim(),
      );
}

class ArApPostResult {
  ArApPostResult({
    required this.voucherNo,
    required this.netCash,
    this.message = '',
  });

  final String voucherNo;
  final double netCash;
  final String message;

  factory ArApPostResult.fromJson(Map<String, dynamic> json) => ArApPostResult(
        voucherNo: '${json['voucher_no'] ?? ''}'.trim(),
        netCash: _num(json['net_cash']),
        message: '${json['message'] ?? ''}'.trim(),
      );
}
