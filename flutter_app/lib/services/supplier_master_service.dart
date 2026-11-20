import '../core/network/api_client.dart';

String _str(dynamic v) => '${v ?? ''}'.trim();

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is int) return v;
  if (v is num) return v.round();
  return int.tryParse('$v'.trim()) ?? 0;
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class SupplierMasterRow {
  SupplierMasterRow({
    required this.supplierCode,
    required this.supplierName,
    required this.supplierType,
    required this.billingType,
    required this.mobile,
    required this.telephone,
    required this.contactPerson,
    required this.address,
    required this.email,
  });

  final int supplierCode;
  final String supplierName;
  final String supplierType;
  final String billingType;
  final String mobile;
  final String telephone;
  final String contactPerson;
  final String address;
  final String email;

  String get phone => mobile.isNotEmpty ? mobile : telephone;

  factory SupplierMasterRow.fromJson(Map<String, dynamic> json) => SupplierMasterRow(
        supplierCode: _int(json['supplier_code'] ?? json['suppliercode']),
        supplierName: _str(json['supplier_name'] ?? json['suppliername']),
        supplierType: _str(json['supplier_type'] ?? json['suppliertype']).toUpperCase(),
        billingType: _str(json['supplier_billing_type'] ?? json['billing_type']).toUpperCase(),
        mobile: _str(json['mobile']),
        telephone: _str(json['telephone']),
        contactPerson: _str(json['contact_person'] ?? json['contactperson']),
        address: _str(json['address']),
        email: _str(json['email'] ?? json['emailid']),
      );
}

class SupplierOpenContext {
  SupplierOpenContext({
    required this.nextSupplierCode,
    required this.cashAccount,
    required this.payableAccount,
    required this.purchaseAccount,
    required this.vatInputAccount,
    required this.advanceAccount,
    this.supplierTypes = const ['LOCAL', 'INTERNATIONAL'],
  });

  final int nextSupplierCode;
  final int cashAccount;
  final int payableAccount;
  final int purchaseAccount;
  final int vatInputAccount;
  final int advanceAccount;
  final List<String> supplierTypes;

  factory SupplierOpenContext.fromJson(Map<String, dynamic> json) {
    final defs = json['default_accounts'];
    final map = defs is Map ? Map<String, dynamic>.from(defs) : <String, dynamic>{};
    final types = (json['supplier_types'] as List<dynamic>? ?? const ['LOCAL', 'INTERNATIONAL'])
        .map((e) => _str(e).toUpperCase())
        .where((e) => e.isNotEmpty)
        .toList();
    return SupplierOpenContext(
      nextSupplierCode: _int(json['next_supplier_code']),
      cashAccount: _int(map['cashaccount'] ?? 1111),
      payableAccount: _int(map['payableaccount'] ?? 2110),
      purchaseAccount: _int(map['purchaseaccount'] ?? 5001),
      vatInputAccount: _int(map['vatinputaccount'] ?? 2200),
      advanceAccount: _int(map['advanceaccount'] ?? 1230),
      supplierTypes: types.isEmpty ? const ['LOCAL', 'INTERNATIONAL'] : types,
    );
  }
}

class SupplierSaveResult {
  SupplierSaveResult({
    required this.supplierCode,
    required this.supplierName,
    required this.message,
  });

  final int supplierCode;
  final String supplierName;
  final String message;

  factory SupplierSaveResult.fromJson(Map<String, dynamic> json) => SupplierSaveResult(
        supplierCode: _int(json['supplier_code'] ?? json['suppliercode']),
        supplierName: _str(json['supplier_name'] ?? json['suppliername']),
        message: _str(json['message']),
      );
}

class SupplierDetail {
  SupplierDetail({
    required this.supplierCode,
    required this.supplierName,
    required this.supplierType,
    required this.billingType,
    required this.mobile,
    required this.telephone,
    required this.email,
    required this.contactPerson,
    required this.address,
    required this.supplierRef,
    required this.supplierCr,
    required this.payableAccount,
    required this.cashAccount,
    required this.purchaseAccount,
    required this.vatInputAccount,
    required this.advanceAccount,
  });

  final int supplierCode;
  final String supplierName;
  final String supplierType;
  final String billingType;
  final String mobile;
  final String telephone;
  final String email;
  final String contactPerson;
  final String address;
  final String supplierRef;
  final String supplierCr;
  final int payableAccount;
  final int cashAccount;
  final int purchaseAccount;
  final int vatInputAccount;
  final int advanceAccount;

  String get phone => mobile.isNotEmpty ? mobile : telephone;

  factory SupplierDetail.fromJson(Map<String, dynamic> json) => SupplierDetail(
        supplierCode: _int(json['supplier_code'] ?? json['suppliercode']),
        supplierName: _str(json['supplier_name'] ?? json['suppliername']),
        supplierType: _str(json['supplier_type'] ?? json['suppliertype']).toUpperCase(),
        billingType: _str(json['supplier_billing_type'] ?? json['billing_type']).toUpperCase(),
        mobile: _str(json['mobile']),
        telephone: _str(json['telephone']),
        email: _str(json['email'] ?? json['emailid']),
        contactPerson: _str(json['contact_person'] ?? json['contactperson']),
        address: _str(json['address']),
        supplierRef: _str(json['supplier_ref'] ?? json['supref']),
        supplierCr: _str(json['supplier_cr'] ?? json['suppliercr']),
        payableAccount: _int(json['payableaccount']),
        cashAccount: _int(json['cashaccount'] ?? 1111),
        purchaseAccount: _int(json['purchaseaccount']),
        vatInputAccount: _int(json['vatinputaccount']),
        advanceAccount: _int(json['advanceaccount']),
      );
}

class SupplierMasterService {
  SupplierMasterService(this._apiClient);

  final ApiClient _apiClient;

  Future<SupplierOpenContext> getOpenContext() async {
    final response = await _apiClient.dio.get('/api/v1/supplier/masters/open');
    return SupplierOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<SupplierMasterRow>> listSuppliers({String q = '', int limit = 100}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/supplier/masters',
      queryParameters: {
        'q': q,
        'limit': limit,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['suppliers'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => SupplierMasterRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<SupplierDetail> getSupplier(int supplierCode) async {
    final response = await _apiClient.dio.get('/api/v1/supplier/masters/$supplierCode');
    return SupplierDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<SupplierSaveResult> createSupplier(Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.post(
      '/api/v1/supplier/masters',
      data: payload,
    );
    return SupplierSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<SupplierSaveResult> updateSupplier(int supplierCode, Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.put(
      '/api/v1/supplier/masters/$supplierCode',
      data: payload,
    );
    return SupplierSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<SupplierSaveResult> deleteSupplier(int supplierCode, {required String password}) async {
    final response = await _apiClient.dio.post(
      '/api/v1/supplier/masters/$supplierCode/delete',
      data: {'password': password},
    );
    return SupplierSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }
}
