import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

String _str(dynamic v) => '${v ?? ''}'.trim();

enum PartyLedgerKind { customer, supplier }

class PartyLedgerParty {
  PartyLedgerParty({
    required this.partyCode,
    required this.partyName,
    this.glAccount = '',
  });

  final String partyCode;
  final String partyName;
  final String glAccount;

  String get displayName => partyName.isNotEmpty ? partyName : partyCode;

  factory PartyLedgerParty.fromJson(Map<String, dynamic> json) => PartyLedgerParty(
        partyCode: _str(json['party_code']),
        partyName: _str(json['party_name']),
        glAccount: _str(json['gl_account']),
      );
}

class PartyLedgerLine {
  PartyLedgerLine({
    required this.voucherDate,
    required this.voucherNo,
    required this.referenceNo,
    required this.narration,
    required this.source,
    required this.remarks,
    required this.accountCode,
    required this.debit,
    required this.credit,
    required this.runningBalance,
  });

  final String voucherDate;
  final String voucherNo;
  final String referenceNo;
  final String narration;
  final String source;
  final String remarks;
  final String accountCode;
  final double debit;
  final double credit;
  final double runningBalance;

  factory PartyLedgerLine.fromJson(Map<String, dynamic> json) => PartyLedgerLine(
        voucherDate: _str(json['voucher_date']),
        voucherNo: _str(json['voucher_no']),
        referenceNo: _str(json['reference_no']),
        narration: _str(json['narration']),
        source: _str(json['source']),
        remarks: _str(json['remarks']),
        accountCode: _str(json['account_code']),
        debit: _num(json['debit']),
        credit: _num(json['credit']),
        runningBalance: _num(json['running_balance']),
      );
}

class PartyLedgerStatement {
  PartyLedgerStatement({
    required this.partyType,
    required this.partyCode,
    required this.partyName,
    required this.glAccount,
    required this.dateFrom,
    required this.dateTo,
    required this.openingBalance,
    required this.totalDebit,
    required this.totalCredit,
    required this.closingBalance,
    required this.lines,
  });

  final String partyType;
  final String partyCode;
  final String partyName;
  final String glAccount;
  final String dateFrom;
  final String dateTo;
  final double openingBalance;
  final double totalDebit;
  final double totalCredit;
  final double closingBalance;
  final List<PartyLedgerLine> lines;

  String get displayName => partyName.isNotEmpty ? partyName : partyCode;

  factory PartyLedgerStatement.fromJson(Map<String, dynamic> json) => PartyLedgerStatement(
        partyType: _str(json['party_type']),
        partyCode: _str(json['party_code']),
        partyName: _str(json['party_name']),
        glAccount: _str(json['gl_account']),
        dateFrom: _str(json['date_from']),
        dateTo: _str(json['date_to']),
        openingBalance: _num(json['opening_balance']),
        totalDebit: _num(json['total_debit']),
        totalCredit: _num(json['total_credit']),
        closingBalance: _num(json['closing_balance']),
        lines: (json['lines'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => PartyLedgerLine.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );
}

class PartyLedgerService {
  PartyLedgerService(this._apiClient);

  final ApiClient _apiClient;

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    final data = root['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return root;
  }

  String _base(PartyLedgerKind kind) =>
      kind == PartyLedgerKind.customer ? '/api/v1/accounts/customer-ledger' : '/api/v1/accounts/supplier-ledger';

  Future<List<PartyLedgerParty>> listParties(
    PartyLedgerKind kind, {
    String q = '',
    int limit = 80,
  }) async {
    final response = await _apiClient.dio.get(
      '${_base(kind)}/parties',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['parties'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PartyLedgerParty.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<PartyLedgerStatement> getStatement(
    PartyLedgerKind kind,
    String partyCode, {
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final encoded = Uri.encodeComponent(partyCode.trim());
    final response = await _apiClient.dio.get(
      '${_base(kind)}/$encoded',
      queryParameters: {
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
      },
    );
    return PartyLedgerStatement.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadPdf(
    PartyLedgerKind kind,
    String partyCode, {
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final encoded = Uri.encodeComponent(partyCode.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '${_base(kind)}/$encoded/pdf',
      queryParameters: {
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
      },
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}
