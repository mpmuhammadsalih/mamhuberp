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
  return int.tryParse('$v'.trim()) ?? 0;
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class CustomerMasterRow {
  CustomerMasterRow({
    required this.customerCode,
    required this.customerName,
    required this.mobile,
    required this.telephone,
    required this.billingType,
    required this.creditLimit,
    required this.address,
  });

  final int customerCode;
  final String customerName;
  final String mobile;
  final String telephone;
  final String billingType;
  final double creditLimit;
  final String address;

  String get phone => mobile.isNotEmpty ? mobile : telephone;

  factory CustomerMasterRow.fromJson(Map<String, dynamic> json) => CustomerMasterRow(
        customerCode: _int(json['customer_code'] ?? json['customercode']),
        customerName: _str(json['customer_name'] ?? json['customername']),
        mobile: _str(json['mobile']),
        telephone: _str(json['telephone']),
        billingType: _str(json['customer_billing_type']).toUpperCase(),
        creditLimit: _num(json['credit_limit'] ?? json['creditlimit']),
        address: _str(json['address']),
      );
}

class CustomerCategoryOption {
  CustomerCategoryOption({required this.code, required this.name});

  final String code;
  final String name;

  String get label => name.isNotEmpty ? '$code — $name' : code;

  factory CustomerCategoryOption.fromJson(Map<String, dynamic> json) => CustomerCategoryOption(
        code: _str(json['code']),
        name: _str(json['name']),
      );
}

class CustomerOpenContext {
  CustomerOpenContext({
    required this.nextCustomerCode,
    required this.defaultCreditTerm,
    required this.receivableAccount,
    required this.salesAccount,
    required this.vatOutputAccount,
    required this.advanceAccount,
    this.categories = const [],
  });

  final int nextCustomerCode;
  final double defaultCreditTerm;
  final int receivableAccount;
  final int salesAccount;
  final int vatOutputAccount;
  final int advanceAccount;
  final List<CustomerCategoryOption> categories;

  factory CustomerOpenContext.fromJson(Map<String, dynamic> json) {
    final defs = json['default_accounts'];
    final map = defs is Map ? Map<String, dynamic>.from(defs) : <String, dynamic>{};
    final cats = (json['categories'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => CustomerCategoryOption.fromJson(Map<String, dynamic>.from(e)))
        .where((e) => e.code.isNotEmpty)
        .toList();
    return CustomerOpenContext(
      nextCustomerCode: _int(json['next_customer_code']),
      defaultCreditTerm: _num(json['default_credit_term'] ?? 2),
      receivableAccount: _int(map['receivableaccount'] ?? 1200),
      salesAccount: _int(map['salesaccount'] ?? 4100),
      vatOutputAccount: _int(map['vatoutputaccount'] ?? 2200),
      advanceAccount: _int(map['advanceaccount'] ?? 2130),
      categories: cats,
    );
  }
}

class CustomerSaveResult {
  CustomerSaveResult({
    required this.customerCode,
    required this.customerName,
    required this.message,
  });

  final int customerCode;
  final String customerName;
  final String message;

  factory CustomerSaveResult.fromJson(Map<String, dynamic> json) => CustomerSaveResult(
        customerCode: _int(json['customer_code'] ?? json['customercode']),
        customerName: _str(json['customer_name'] ?? json['customername']),
        message: _str(json['message']),
      );
}

class CustomerDetail {
  CustomerDetail({
    required this.customerCode,
    required this.customerName,
    required this.billingType,
    required this.categoryCode,
    required this.categoryName,
    required this.mobile,
    required this.telephone,
    required this.whatsapp,
    required this.email,
    required this.address,
    required this.crno,
    required this.creditLimit,
    required this.creditTerm,
    required this.currentCredit,
    required this.ccode,
    required this.closed,
  });

  final int customerCode;
  final String customerName;
  final String billingType;
  final int categoryCode;
  final String categoryName;
  final String mobile;
  final String telephone;
  final String whatsapp;
  final String email;
  final String address;
  final String crno;
  final double creditLimit;
  final double creditTerm;
  final double currentCredit;
  final String ccode;
  final String closed;

  String get phone => mobile.isNotEmpty ? mobile : telephone;

  factory CustomerDetail.fromJson(Map<String, dynamic> json) => CustomerDetail(
        customerCode: _int(json['customer_code'] ?? json['customercode']),
        customerName: _str(json['customer_name'] ?? json['customername']),
        billingType: _str(json['customer_billing_type']).toUpperCase(),
        categoryCode: _int(json['customercategory'] ?? json['customer_category']),
        categoryName: _str(json['category_name']),
        mobile: _str(json['mobile']),
        telephone: _str(json['telephone']),
        whatsapp: _str(json['whatsapp']),
        email: _str(json['email']),
        address: _str(json['address']),
        crno: _str(json['crno']),
        creditLimit: _num(json['credit_limit'] ?? json['creditlimit']),
        creditTerm: _num(json['credit_term'] ?? json['creditterms'] ?? json['creditterm']),
        currentCredit: _num(json['current_credit'] ?? json['currentcredit']),
        ccode: _str(json['ccode']),
        closed: _str(json['closed']).toUpperCase(),
      );
}

class CustomerMasterService {
  CustomerMasterService(this._apiClient);

  final ApiClient _apiClient;

  Future<CustomerOpenContext> getOpenContext() async {
    final response = await _apiClient.dio.get('/api/v1/customer/masters/open');
    return CustomerOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<CustomerMasterRow>> listCustomers({String q = '', int limit = 100}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/customer/masters',
      queryParameters: {
        'q': q,
        'limit': limit,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['customers'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => CustomerMasterRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<CustomerSaveResult> createCustomer(Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.post(
      '/api/v1/customer/masters',
      data: payload,
    );
    return CustomerSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<CustomerDetail> getCustomer(int customerCode) async {
    final response = await _apiClient.dio.get('/api/v1/customer/masters/$customerCode');
    return CustomerDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<CustomerSaveResult> updateCustomer(int customerCode, Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.put(
      '/api/v1/customer/masters/$customerCode',
      data: payload,
    );
    return CustomerSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<CustomerSaveResult> deleteCustomer(int customerCode, {required String password}) async {
    final response = await _apiClient.dio.post(
      '/api/v1/customer/masters/$customerCode/delete',
      data: {'password': password},
    );
    return CustomerSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<CustomerCategoryOption>> listCategories({String q = ''}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/customer/categories',
      queryParameters: {'q': q},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['categories'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => CustomerCategoryOption.fromJson(Map<String, dynamic>.from(e)))
        .where((e) => e.code.isNotEmpty)
        .toList();
  }

  /// Creates ERP ``TBLCUSTOMERCATEGORY`` row (same as Customer Category master).
  Future<CustomerCategoryOption> createCategory({required String name}) async {
    final response = await _apiClient.dio.post(
      '/api/v1/customer/categories',
      data: {'categoryname': name.trim()},
    );
    return CustomerCategoryOption.fromJson(_data(response.data as Map<String, dynamic>));
  }
}
