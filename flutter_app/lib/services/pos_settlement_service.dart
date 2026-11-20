import '../core/network/api_client.dart';

String _str(dynamic v) => '${v ?? ''}'.trim();

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is int) return v;
  if (v is num) return v.round();
  final s = '$v'.trim();
  if (s.isEmpty) return 0;
  return int.tryParse(s) ?? double.tryParse(s)?.round() ?? 0;
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class PosSettlementOpenContext {
  PosSettlementOpenContext({
    required this.locationCode,
    required this.defaultDate,
    required this.accounts,
    this.tenderTypes = const [],
  });

  final int locationCode;
  final String defaultDate;
  final Map<String, String> accounts;
  final List<PosTenderType> tenderTypes;

  factory PosSettlementOpenContext.fromJson(Map<String, dynamic> json) {
    final accRaw = json['accounts'];
    final accMap = accRaw is Map ? Map<String, dynamic>.from(accRaw) : <String, dynamic>{};
    return PosSettlementOpenContext(
      locationCode: _int(json['location_code']),
      defaultDate: _str(json['default_date']),
      accounts: {
        for (final e in accMap.entries) e.key: _str(e.value),
      },
      tenderTypes: (json['tender_types'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((e) => PosTenderType.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }
}

class PosTenderType {
  PosTenderType({required this.code, required this.name, this.sortOrder = 0});

  final String code;
  final String name;
  final int sortOrder;

  factory PosTenderType.fromJson(Map<String, dynamic> json) => PosTenderType(
        code: _str(json['code']).toUpperCase(),
        name: _str(json['name']),
        sortOrder: _int(json['sort_order']),
      );
}

class PosSettlementPendingDay {
  PosSettlementPendingDay({
    required this.billDate,
    required this.billCount,
    required this.netAmount,
  });

  final String billDate;
  final int billCount;
  final double netAmount;

  factory PosSettlementPendingDay.fromJson(Map<String, dynamic> json) => PosSettlementPendingDay(
        billDate: _str(json['bill_date']),
        billCount: _int(json['bill_count']),
        netAmount: _num(json['net_amount']),
      );
}

class PosSettlementDraftSummary {
  PosSettlementDraftSummary({
    required this.draftId,
    required this.status,
    required this.referenceNo,
    required this.billCount,
    this.voucherNo = '',
    this.voucherDate = '',
    this.createdAt = '',
    this.createdBy = '',
    this.narration = '',
  });

  final int draftId;
  final String status;
  final String referenceNo;
  final int billCount;
  final String voucherNo;
  final String voucherDate;
  final String createdAt;
  final String createdBy;
  final String narration;

  factory PosSettlementDraftSummary.fromJson(Map<String, dynamic> json) => PosSettlementDraftSummary(
        draftId: _int(json['draft_id']),
        status: _str(json['status']).toUpperCase(),
        referenceNo: _str(json['reference_no']),
        billCount: _int(json['bill_count']),
        voucherNo: _str(json['voucher_no']),
        voucherDate: _str(json['voucher_date']),
        createdAt: _str(json['created_at']),
        createdBy: _str(json['created_by']),
        narration: _str(json['narration']),
      );
}

class PosSettlementBill {
  PosSettlementBill({
    required this.billNo,
    required this.billDate,
    required this.netAmount,
    this.customerName = '',
    this.counterCode = 0,
    this.settlementStatus = 'PENDING',
    this.paymentMode = '',
  });

  /// Document bill number (numeric or formatted, e.g. SI-000001).
  final String billNo;
  final String billDate;
  final double netAmount;
  final String customerName;
  final int counterCode;
  final String settlementStatus;
  final String paymentMode;

  factory PosSettlementBill.fromJson(Map<String, dynamic> json) => PosSettlementBill(
        billNo: _str(json['billNo'] ?? json['bill_no'] ?? json['billno']),
        billDate: _str(json['billDate'] ?? json['bill_date'] ?? json['billdate']),
        netAmount: _num(json['netAmount'] ?? json['net'] ?? json['netbillamount']),
        customerName: _str(json['customer'] ?? json['customerName'] ?? json['customer_name']),
        counterCode: _int(json['counter'] ?? json['counterCode'] ?? json['counter_code']),
        settlementStatus: _str(
          json['settlementStatus'] ?? json['pos_settlement_status'] ?? 'Pending',
        ).toUpperCase(),
        paymentMode: _str(json['paymentType'] ?? json['paymentMode'] ?? json['payment_mode']),
      );
}

class PosPaymodeLine {
  PosPaymodeLine({required this.code, required this.label, required this.amount});

  final String code;
  final String label;
  final double amount;

  factory PosPaymodeLine.fromJson(Map<String, dynamic> json) => PosPaymodeLine(
        code: _str(json['code']).toUpperCase(),
        label: _str(json['label']),
        amount: _num(json['amount']),
      );
}

class PosSettlementDraftDetail {
  PosSettlementDraftDetail({
    required this.draftId,
    required this.status,
    required this.referenceNo,
    required this.billNos,
    this.voucherNo = '',
    this.voucherDate = '',
    this.narration = '',
    this.journalLines = const [],
    this.meta = const {},
  });

  final int draftId;
  final String status;
  final String referenceNo;
  final List<String> billNos;
  final String voucherNo;
  final String voucherDate;
  final String narration;
  final List<Map<String, dynamic>> journalLines;
  final Map<String, dynamic> meta;

  factory PosSettlementDraftDetail.fromJson(Map<String, dynamic> json) {
    final bills = <String>[];
    for (final x in json['bill_nos'] as List<dynamic>? ?? const []) {
      final n = _str(x);
      if (n.isNotEmpty) bills.add(n);
    }
    return PosSettlementDraftDetail(
      draftId: _int(json['draft_id']),
      status: _str(json['status']).toUpperCase(),
      referenceNo: _str(json['reference_no']),
      billNos: bills,
      voucherNo: _str(json['voucher_no']),
      voucherDate: _str(json['voucher_date']),
      narration: _str(json['narration']),
      journalLines: (json['journal_lines'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList(),
      meta: json['meta'] is Map ? Map<String, dynamic>.from(json['meta'] as Map) : const {},
    );
  }
}

class PosSettlementService {
  PosSettlementService(this._apiClient);

  final ApiClient _apiClient;

  Future<PosSettlementOpenContext> getOpenContext() async {
    final response = await _apiClient.dio.get('/api/v1/accounts/pos-settlements/open');
    return PosSettlementOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<PosSettlementPendingDay>> listPendingByDate({int limit = 90}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/pos-settlements/pending-by-date',
      queryParameters: {'limit': limit},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['days'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PosSettlementPendingDay.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<PosSettlementDraftSummary>> listDrafts({int limit = 40}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/pos-settlements/drafts',
      queryParameters: {'limit': limit},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['drafts'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PosSettlementDraftSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<PosSettlementBill>> listBills({
    String fromDate = '',
    String toDate = '',
    String settlementScope = 'pending',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/accounts/pos-settlements/bills',
      queryParameters: {
        'from': fromDate,
        'to': toDate,
        'settlement_scope': settlementScope,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['bills'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PosSettlementBill.fromJson(Map<String, dynamic>.from(e)))
        .where((e) => e.billNo.isNotEmpty)
        .toList();
  }

  Future<List<PosPaymodeLine>> paymentModeSummary(List<String> billNos) async {
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/pos-settlements/payment-mode-summary',
      data: {'bill_nos': billNos},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['lines'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PosPaymodeLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<({PosSettlementDraftDetail detail, List<PosSettlementBill> bills})> getDraft(int draftId) async {
    final response = await _apiClient.dio.get('/api/v1/accounts/pos-settlements/drafts/$draftId');
    final data = _data(response.data as Map<String, dynamic>);
    final detailRaw = data['detail'];
    final detail = PosSettlementDraftDetail.fromJson(
      detailRaw is Map ? Map<String, dynamic>.from(detailRaw) : <String, dynamic>{},
    );
    final bills = (data['bills'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PosSettlementBill.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return (detail: detail, bills: bills);
  }

  Future<PosSettlementDraftDetail> generateDraft({
    required List<String> billNos,
    required Map<String, String> accounts,
    required Map<String, dynamic> meta,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/pos-settlements/drafts/generate',
      data: {
        'bill_nos': billNos,
        'accounts': accounts,
        'meta': meta,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    final detailRaw = data['detail'];
    return PosSettlementDraftDetail.fromJson(
      detailRaw is Map ? Map<String, dynamic>.from(detailRaw) : <String, dynamic>{},
    );
  }

  Future<PosSettlementDraftDetail> verifyDraft(int draftId) async {
    final response = await _apiClient.dio.post('/api/v1/accounts/pos-settlements/drafts/$draftId/verify');
    final data = _data(response.data as Map<String, dynamic>);
    final detailRaw = data['detail'];
    return PosSettlementDraftDetail.fromJson(
      detailRaw is Map ? Map<String, dynamic>.from(detailRaw) : <String, dynamic>{},
    );
  }

  Future<PosSettlementDraftDetail> cancelDraft(int draftId) async {
    final response = await _apiClient.dio.post('/api/v1/accounts/pos-settlements/drafts/$draftId/cancel');
    final data = _data(response.data as Map<String, dynamic>);
    final detailRaw = data['detail'];
    return PosSettlementDraftDetail.fromJson(
      detailRaw is Map ? Map<String, dynamic>.from(detailRaw) : <String, dynamic>{},
    );
  }

  Future<({String voucherNo, PosSettlementDraftDetail detail})> postDraft(
    int draftId, {
    String voucherDate = '',
    String remarks = '',
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/accounts/pos-settlements/drafts/$draftId/post',
      data: {
        if (voucherDate.isNotEmpty) 'voucher_date': voucherDate,
        if (remarks.isNotEmpty) 'remarks': remarks,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    final detailRaw = data['detail'];
    return (
      voucherNo: _str(data['voucher_no']),
      detail: PosSettlementDraftDetail.fromJson(
        detailRaw is Map ? Map<String, dynamic>.from(detailRaw) : <String, dynamic>{},
      ),
    );
  }
}
