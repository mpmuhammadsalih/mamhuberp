import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

String _str(dynamic v) => '${v ?? ''}'.trim();

class JeAccountOption {
  JeAccountOption({required this.code, this.name = '', this.type = ''});

  final String code;
  final String name;
  final String type;

  String get label => name.isNotEmpty ? '$code — $name' : code;

  factory JeAccountOption.fromJson(Map<String, dynamic> json) => JeAccountOption(
        code: _str(json['code']),
        name: _str(json['name']),
        type: _str(json['type']),
      );
}

class JePartyOption {
  JePartyOption({
    required this.partyCode,
    required this.partyName,
    required this.partyType,
    this.glAccount = '',
  });

  final String partyCode;
  final String partyName;
  final String partyType;
  final String glAccount;

  String get label => partyName.isNotEmpty ? '$partyCode — $partyName' : partyCode;

  factory JePartyOption.fromJson(Map<String, dynamic> json) => JePartyOption(
        partyCode: _str(json['party_code']),
        partyName: _str(json['party_name']),
        partyType: _str(json['party_type']).toUpperCase(),
        glAccount: _str(json['gl_account']),
      );
}

class JeOpenContext {
  JeOpenContext({
    required this.voucherDate,
    this.defaultCustomerReceivable = '',
    this.defaultSupplierPayable = '',
  });

  final String voucherDate;
  final String defaultCustomerReceivable;
  final String defaultSupplierPayable;

  factory JeOpenContext.fromJson(Map<String, dynamic> json) => JeOpenContext(
        voucherDate: _str(json['voucher_date']),
        defaultCustomerReceivable: _str(json['default_customer_receivable']),
        defaultSupplierPayable: _str(json['default_supplier_payable']),
      );
}

class JeSummary {
  JeSummary({
    required this.voucherNo,
    required this.voucherDate,
    required this.referenceNo,
    required this.narration,
    required this.source,
    required this.status,
    required this.totalDebit,
    required this.totalCredit,
    this.draftId = '',
    this.lineCount = 0,
    this.canEdit = false,
    this.canPost = false,
    this.canReverse = false,
  });

  final String voucherNo;
  final String draftId;
  final String voucherDate;
  final String referenceNo;
  final String narration;
  final String source;
  final String status;
  final double totalDebit;
  final double totalCredit;
  final int lineCount;
  final bool canEdit;
  final bool canPost;
  final bool canReverse;

  bool get isDraft => status == 'DRAFT';
  bool get isPosted => status == 'POSTED';

  String get docKey => isDraft && draftId.isNotEmpty ? draftId : voucherNo;

  factory JeSummary.fromJson(Map<String, dynamic> json) => JeSummary(
        voucherNo: _str(json['voucher_no']),
        draftId: _str(json['draft_id']),
        voucherDate: _str(json['voucher_date']),
        referenceNo: _str(json['reference_no']),
        narration: _str(json['narration']),
        source: _str(json['source']).toUpperCase(),
        status: _str(json['status']).toUpperCase(),
        totalDebit: _num(json['total_debit']),
        totalCredit: _num(json['total_credit']),
        lineCount: (json['line_count'] as num?)?.toInt() ?? 0,
        canEdit: json['can_edit'] == true,
        canPost: json['can_post'] == true,
        canReverse: json['can_reverse'] == true,
      );
}

class JeLine {
  JeLine({
    required this.lineNo,
    required this.accountCode,
    required this.accountName,
    required this.debit,
    required this.credit,
    this.remarks = '',
    this.partyType = '',
    this.partyCode = '',
    this.partyName = '',
    this.costCenter = '',
    this.department = '',
    this.project = '',
  });

  final int lineNo;
  final String accountCode;
  final String accountName;
  final double debit;
  final double credit;
  final String remarks;
  final String partyType;
  final String partyCode;
  final String partyName;
  final String costCenter;
  final String department;
  final String project;

  factory JeLine.fromJson(Map<String, dynamic> json) => JeLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        accountCode: _str(json['account_code']),
        accountName: _str(json['account_name']),
        debit: _num(json['debit']),
        credit: _num(json['credit']),
        remarks: _str(json['remarks']),
        partyType: _str(json['party_type']).toUpperCase(),
        partyCode: _str(json['party_code']),
        partyName: _str(json['party_name']),
        costCenter: _str(json['cost_center']),
        department: _str(json['department']),
        project: _str(json['project']),
      );
}

class JeDetail {
  JeDetail({
    required this.voucherNo,
    required this.voucherDate,
    required this.referenceNo,
    required this.narration,
    required this.source,
    required this.status,
    required this.totalDebit,
    required this.totalCredit,
    required this.lines,
    this.draftId = '',
    this.editVoucherNo = '',
    this.createdBy = '',
    this.reversalVoucherNo = '',
    this.canEdit = false,
    this.canPost = false,
    this.canReverse = false,
  });

  final String voucherNo;
  final String draftId;
  final String editVoucherNo;
  final String voucherDate;
  final String referenceNo;
  final String narration;
  final String source;
  final String status;
  final String createdBy;
  final double totalDebit;
  final double totalCredit;
  final String reversalVoucherNo;
  final bool canEdit;
  final bool canPost;
  final bool canReverse;
  final List<JeLine> lines;

  bool get isDraft => status == 'DRAFT';
  bool get isPosted => status == 'POSTED';

  factory JeDetail.fromJson(Map<String, dynamic> json) => JeDetail(
        voucherNo: _str(json['voucher_no']),
        draftId: _str(json['draft_id']),
        editVoucherNo: _str(json['edit_voucher_no']),
        voucherDate: _str(json['voucher_date']),
        referenceNo: _str(json['reference_no']),
        narration: _str(json['narration']),
        source: _str(json['source']).toUpperCase(),
        status: _str(json['status']).toUpperCase(),
        createdBy: _str(json['created_by']),
        totalDebit: _num(json['total_debit']),
        totalCredit: _num(json['total_credit']),
        reversalVoucherNo: _str(json['reversal_voucher_no']),
        canEdit: json['can_edit'] == true,
        canPost: json['can_post'] == true,
        canReverse: json['can_reverse'] == true,
        lines: (json['lines'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => JeLine.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );
}

class JeSaveResult {
  JeSaveResult({
    required this.voucherNo,
    required this.status,
    this.draftId = '',
    this.message = '',
    this.totalDebit = 0,
    this.totalCredit = 0,
    this.reversalVoucherNo = '',
  });

  final String voucherNo;
  final String draftId;
  final String status;
  final String message;
  final double totalDebit;
  final double totalCredit;
  final String reversalVoucherNo;

  factory JeSaveResult.fromJson(Map<String, dynamic> json) => JeSaveResult(
        voucherNo: _str(json['voucher_no']),
        draftId: _str(json['draft_id']),
        status: _str(json['status']).toUpperCase(),
        message: _str(json['message']),
        totalDebit: _num(json['total_debit']),
        totalCredit: _num(json['total_credit']),
        reversalVoucherNo: _str(json['reversal_voucher_no']),
      );
}

class JournalEntryService {
  JournalEntryService(this._apiClient);

  final ApiClient _apiClient;

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    final data = root['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return root;
  }

  Future<JeOpenContext> getOpen() async {
    final response = await _apiClient.dio.get('/api/v1/accounts/journals/open');
    return JeOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<JeAccountOption>> listAccounts({String q = '', int limit = 200}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/journals/accounts',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['accounts'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => JeAccountOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<JePartyOption>> listCustomers({String q = ''}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/journals/parties/customers',
      queryParameters: {if (q.trim().isNotEmpty) 'q': q.trim()},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['parties'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => JePartyOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<JePartyOption>> listSuppliers({String q = ''}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/journals/parties/suppliers',
      queryParameters: {if (q.trim().isNotEmpty) 'q': q.trim()},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['parties'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => JePartyOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<JeSummary>> listJournals({
    String q = '',
    String status = 'all',
    String source = 'all',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/journals',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'status': status,
        if (source.trim().isNotEmpty && source != 'all') 'source': source,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['vouchers'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => JeSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<JeDetail> getDetail(String docId) async {
    final encoded = Uri.encodeComponent(docId.trim());
    final response = await _apiClient.dio.get('/api/v1/accounts/journals/$encoded');
    return JeDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<JeSaveResult> saveDraft(Map<String, dynamic> body) async {
    final response = await _apiClient.dio.post('/api/v1/accounts/journals/draft', data: body);
    return JeSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<JeSaveResult> postJournal(Map<String, dynamic> body) async {
    final response = await _apiClient.dio.post('/api/v1/accounts/journals/post', data: body);
    return JeSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<JeSaveResult> reverseJournal(String voucherNo, {String remarks = ''}) async {
    final encoded = Uri.encodeComponent(voucherNo.trim());
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/journals/$encoded/reverse',
      data: {if (remarks.trim().isNotEmpty) 'remarks': remarks.trim()},
    );
    return JeSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadPdf(String voucherNo) async {
    final encoded = Uri.encodeComponent(voucherNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/accounts/journals/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}
