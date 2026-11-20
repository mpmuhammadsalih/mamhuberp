import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

String _str(dynamic v) => '${v ?? ''}'.trim();

class CpvAccountOption {
  CpvAccountOption({
    required this.code,
    this.name = '',
    this.type = '',
  });

  final String code;
  final String name;
  final String type;

  String get label => name.isNotEmpty ? '$code — $name' : code;

  factory CpvAccountOption.fromJson(Map<String, dynamic> json) => CpvAccountOption(
        code: _str(json['code']),
        name: _str(json['name']),
        type: _str(json['type']),
      );
}

class CpvOpenContext {
  CpvOpenContext({
    required this.voucherNo,
    required this.voucherDate,
    this.defaultPettyCash = '',
    this.defaultExpenseParent = '',
    this.pettyAccounts = const [],
    this.expenseParentAccounts = const [],
  });

  final String voucherNo;
  final String voucherDate;
  final String defaultPettyCash;
  final String defaultExpenseParent;
  final List<CpvAccountOption> pettyAccounts;
  final List<CpvAccountOption> expenseParentAccounts;

  factory CpvOpenContext.fromJson(Map<String, dynamic> json) => CpvOpenContext(
        voucherNo: _str(json['voucher_no']),
        voucherDate: _str(json['voucher_date']),
        defaultPettyCash: _str(json['default_petty_cash']),
        defaultExpenseParent: _str(json['default_expense_parent']),
        pettyAccounts: (json['petty_accounts'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => CpvAccountOption.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
        expenseParentAccounts: (json['expense_parent_accounts'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => CpvAccountOption.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );
}

class CpvSummary {
  CpvSummary({
    required this.voucherNo,
    required this.voucherDate,
    required this.pettyCashAccount,
    required this.referenceNo,
    required this.narration,
    required this.status,
    required this.totalAmount,
    this.glVoucherNo = '',
    this.lineCount = 0,
    this.canEdit = false,
    this.canPost = false,
  });

  final String voucherNo;
  final String voucherDate;
  final String pettyCashAccount;
  final String referenceNo;
  final String narration;
  final String status;
  final double totalAmount;
  final String glVoucherNo;
  final int lineCount;
  final bool canEdit;
  final bool canPost;

  bool get isDraft => status == 'DRAFT' || status.isEmpty;
  bool get isPosted => status == 'POSTED';

  String get subtitle {
    if (narration.isNotEmpty) return narration;
    if (referenceNo.isNotEmpty) return 'Ref $referenceNo';
    return pettyCashAccount.isNotEmpty ? 'Petty cash $pettyCashAccount' : '';
  }

  factory CpvSummary.fromJson(Map<String, dynamic> json) => CpvSummary(
        voucherNo: _str(json['voucher_no']),
        voucherDate: _str(json['voucher_date']),
        pettyCashAccount: _str(json['petty_cash_account']),
        referenceNo: _str(json['reference_no']),
        narration: _str(json['narration']),
        status: _str(json['status']).toUpperCase(),
        totalAmount: _num(json['total_amount']),
        glVoucherNo: _str(json['gl_voucher_no']),
        lineCount: (json['line_count'] as num?)?.toInt() ?? 0,
        canEdit: json['can_edit'] == true,
        canPost: json['can_post'] == true,
      );
}

class CpvLine {
  CpvLine({
    required this.lineNo,
    required this.accountCode,
    required this.accountName,
    required this.description,
    required this.amount,
  });

  final int lineNo;
  final String accountCode;
  final String accountName;
  final String description;
  final double amount;

  factory CpvLine.fromJson(Map<String, dynamic> json) => CpvLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        accountCode: _str(json['account_code']),
        accountName: _str(json['account_name']),
        description: _str(json['description']),
        amount: _num(json['amount']),
      );
}

class CpvDetail {
  CpvDetail({
    required this.voucherNo,
    required this.voucherDate,
    required this.pettyCashAccount,
    required this.pettyCashName,
    required this.expenseParentAccount,
    required this.expenseParentName,
    required this.referenceNo,
    required this.narration,
    required this.status,
    required this.totalAmount,
    required this.lines,
    this.glVoucherNo = '',
    this.canEdit = false,
    this.canPost = false,
  });

  final String voucherNo;
  final String voucherDate;
  final String pettyCashAccount;
  final String pettyCashName;
  final String expenseParentAccount;
  final String expenseParentName;
  final String referenceNo;
  final String narration;
  final String status;
  final double totalAmount;
  final String glVoucherNo;
  final bool canEdit;
  final bool canPost;
  final List<CpvLine> lines;

  bool get isDraft => status == 'DRAFT' || status.isEmpty;
  bool get isPosted => status == 'POSTED';

  factory CpvDetail.fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => CpvLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return CpvDetail(
      voucherNo: _str(json['voucher_no']),
      voucherDate: _str(json['voucher_date']),
      pettyCashAccount: _str(json['petty_cash_account']),
      pettyCashName: _str(json['petty_cash_name']),
      expenseParentAccount: _str(json['expense_parent_account']),
      expenseParentName: _str(json['expense_parent_name']),
      referenceNo: _str(json['reference_no']),
      narration: _str(json['narration']),
      status: _str(json['status']).toUpperCase(),
      totalAmount: _num(json['total_amount']),
      glVoucherNo: _str(json['gl_voucher_no']),
      canEdit: json['can_edit'] == true,
      canPost: json['can_post'] == true,
      lines: lines,
    );
  }
}

class CpvSaveResult {
  CpvSaveResult({
    required this.voucherNo,
    this.status = 'DRAFT',
    this.totalAmount = 0,
    this.message = '',
  });

  final String voucherNo;
  final String status;
  final double totalAmount;
  final String message;

  factory CpvSaveResult.fromJson(Map<String, dynamic> json) => CpvSaveResult(
        voucherNo: _str(json['voucher_no']),
        status: _str(json['status']).toUpperCase(),
        totalAmount: _num(json['total_amount']),
        message: _str(json['message']),
      );
}

class CpvPostResult {
  CpvPostResult({
    required this.voucherNo,
    this.status = 'POSTED',
    this.glVoucherNo = '',
    this.totalAmount = 0,
    this.message = '',
  });

  final String voucherNo;
  final String status;
  final String glVoucherNo;
  final double totalAmount;
  final String message;

  factory CpvPostResult.fromJson(Map<String, dynamic> json) => CpvPostResult(
        voucherNo: _str(json['voucher_no']),
        status: _str(json['status']).toUpperCase(),
        glVoucherNo: _str(json['gl_voucher_no']),
        totalAmount: _num(json['total_amount']),
        message: _str(json['message']),
      );
}

class CashPaymentVoucherService {
  CashPaymentVoucherService(this._apiClient);
  final ApiClient _apiClient;

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    final data = root['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return root;
  }

  Future<CpvOpenContext> getOpen() async {
    final response = await _apiClient.dio.get('/api/v1/accounts/cash-payment-vouchers/open');
    return CpvOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<CpvAccountOption>> listExpenseChildren(String parentCode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/cash-payment-vouchers/expense-children',
      queryParameters: {'parent_code': parentCode.trim()},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['accounts'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => CpvAccountOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  /// Create a postable expense sub-account under [parentCode] (ERP Chart of Accounts).
  Future<CpvAccountOption> createExpenseSubAccount({
    required String parentCode,
    required String name,
    String code = '',
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/cash-payment-vouchers/expense-sub-accounts',
      data: {
        'parent_code': parentCode.trim(),
        'name': name.trim(),
        if (code.trim().isNotEmpty) 'code': code.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    if (root['success'] == false) {
      throw Exception('${root['message'] ?? 'Failed to create sub-account'}');
    }
    final data = _data(root);
    final created = CpvAccountOption.fromJson(data);
    if (created.code.isEmpty) {
      throw Exception('Sub-account was created but code is missing.');
    }
    return created;
  }

  Future<List<CpvSummary>> listVouchers({
    String q = '',
    String status = 'all',
    int limit = 100,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/cash-payment-vouchers',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'status': status,
        'limit': limit,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['vouchers'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => CpvSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<CpvDetail> getDetail(String voucherNo) async {
    final encoded = Uri.encodeComponent(voucherNo.trim());
    final response = await _apiClient.dio.get('/api/v1/accounts/cash-payment-vouchers/$encoded');
    return CpvDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<CpvSaveResult> saveDraft({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/cash-payment-vouchers/save',
      data: {'header': header, 'lines': lines},
    );
    return CpvSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<CpvPostResult> postVoucher({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/cash-payment-vouchers/post',
      data: {'header': header, 'lines': lines},
    );
    return CpvPostResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadPdf(String voucherNo) async {
    final encoded = Uri.encodeComponent(voucherNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/cash-payment-vouchers/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}
