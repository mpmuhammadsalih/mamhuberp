import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

double _factorFromJson(Map<String, dynamic> json) {
  final f = _num(json['factor'] ?? json['conversionfactor']);
  return f > 0 ? f : 1.0;
}

String _str(dynamic v) => '${v ?? ''}'.trim();

class StockReturnSummary {
  StockReturnSummary({
    required this.returnNo,
    required this.returnDate,
    required this.supplierCode,
    required this.supplierName,
    required this.amount,
    required this.approvalStatus,
    this.rowKind = 'request',
    this.canEdit = false,
  });

  final String returnNo;
  final String returnDate;
  final String supplierCode;
  final String supplierName;
  final double amount;
  final String approvalStatus;
  final String rowKind;
  final bool canEdit;

  String get supplierLabel {
    if (supplierName.isNotEmpty) return supplierName;
    if (supplierCode.isNotEmpty) return 'Supplier $supplierCode';
    return 'Supplier';
  }

  bool get isPosted =>
      rowKind == 'posted' || approvalStatus == 'POSTED' || approvalStatus == 'APPROVED';

  factory StockReturnSummary.fromJson(Map<String, dynamic> json) => StockReturnSummary(
        returnNo: _str(json['return_no'] ?? json['goodsreturnno']),
        returnDate: _str(json['return_date'] ?? json['returndate']),
        supplierCode: _str(json['supplier_code'] ?? json['suppliercode']),
        supplierName: _str(json['supplier_name'] ?? json['suppliername']),
        amount: _num(json['amount'] ?? json['returnamount']),
        approvalStatus: _str(json['approval_status']).toUpperCase(),
        rowKind: _str(json['row_kind']).isEmpty ? 'request' : _str(json['row_kind']).toLowerCase(),
        canEdit: json['can_edit'] == true,
      );
}

class StockReturnLine {
  StockReturnLine({
    required this.lineNo,
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    this.discount = 0,
    this.amount = 0,
    this.barcode = '',
    this.factor = 1,
    this.warehouseId,
    this.warehouseCode,
  });

  final int lineNo;
  final String itemCode;
  final String itemName;
  final String uom;
  final double qty;
  final double rate;
  final double discount;
  final double amount;
  final String barcode;
  final double factor;
  final String? warehouseId;
  final String? warehouseCode;

  factory StockReturnLine.fromJson(Map<String, dynamic> json) => StockReturnLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        itemCode: _str(json['item_code'] ?? json['itemcode']),
        itemName: _str(json['item_name'] ?? json['itemname']),
        uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
        qty: _num(json['qty'] ?? json['quantity']),
        rate: _num(json['rate']),
        discount: _num(json['discount']),
        amount: _num(json['amount']),
        barcode: _str(json['barcode']),
        factor: _factorFromJson(json),
        warehouseId: json['warehouse_id'] == null || _str(json['warehouse_id']).isEmpty
            ? null
            : _str(json['warehouse_id']),
        warehouseCode: _str(json['warehouse_code']).isEmpty ? null : _str(json['warehouse_code']),
      );
}

class StockReturnDetail {
  StockReturnDetail({
    required this.summary,
    required this.lines,
    this.discount = 0,
    this.remarks = '',
    this.receiptNo = '',
    this.postedStockNo = '',
    this.documentType = 'return_request',
    this.canEdit = false,
    this.canCancel = false,
    this.canApprove = false,
  });

  final StockReturnSummary summary;
  final List<StockReturnLine> lines;
  final double discount;
  final String remarks;
  final String receiptNo;
  final String postedStockNo;
  final String documentType;
  final bool canEdit;
  final bool canCancel;
  final bool canApprove;

  bool get isDraft =>
      summary.approvalStatus == 'DRAFT' || summary.approvalStatus.isEmpty;
  bool get isCanceled =>
      summary.approvalStatus == 'CANCELLED' || summary.approvalStatus == 'CANCELED';
  bool get isPosted =>
      documentType == 'posted_return' ||
      summary.approvalStatus == 'POSTED' ||
      summary.approvalStatus == 'APPROVED' ||
      postedStockNo.isNotEmpty;

  factory StockReturnDetail.fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockReturnLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return StockReturnDetail(
      summary: StockReturnSummary.fromJson(json),
      lines: lines,
      discount: _num(json['discount']),
      remarks: _str(json['remarks']),
      receiptNo: _str(json['receipt_no']),
      postedStockNo: _str(json['posted_stock_no']),
      documentType: _str(json['document_type']).isEmpty
          ? 'return_request'
          : _str(json['document_type']),
      canEdit: json['can_edit'] == true,
      canCancel: json['can_cancel'] == true,
      canApprove: json['can_approve'] == true,
    );
  }
}

class StockReturnOpenContext {
  StockReturnOpenContext({
    required this.returnNo,
    required this.returnDate,
    this.warehouseEnabled = false,
    this.defaultWarehouseId,
    this.defaultWarehouseCode = '',
    this.defaultWarehouseName = '',
    this.defaultWarehouseLabel = '',
  });

  final String returnNo;
  final String returnDate;
  final bool warehouseEnabled;
  final String? defaultWarehouseId;
  final String defaultWarehouseCode;
  final String defaultWarehouseName;
  final String defaultWarehouseLabel;

  factory StockReturnOpenContext.fromJson(Map<String, dynamic> json) {
    final features = json['features'] as Map<String, dynamic>? ?? const {};
    return StockReturnOpenContext(
      returnNo: _str(json['return_no']),
      returnDate: _str(json['return_date']),
      warehouseEnabled: features['warehouse_enabled'] == true,
      defaultWarehouseId: json['default_warehouse_id'] == null ||
              _str(json['default_warehouse_id']).isEmpty
          ? null
          : _str(json['default_warehouse_id']),
      defaultWarehouseCode: _str(json['default_warehouse_code']),
      defaultWarehouseName: _str(json['default_warehouse_name']),
      defaultWarehouseLabel: _str(json['default_warehouse_label']),
    );
  }
}

class StockReturnSaveResult {
  StockReturnSaveResult({
    required this.returnNo,
    this.approvalStatus = 'DRAFT',
    this.message = '',
    this.saveMode = 'pr_draft',
    this.inventoryPosted = false,
    this.accountsPosted = false,
    this.postedStockNo = '',
  });

  final String returnNo;
  final String approvalStatus;
  final String message;
  final String saveMode;
  final bool inventoryPosted;
  final bool accountsPosted;
  final String postedStockNo;

  factory StockReturnSaveResult.fromJson(Map<String, dynamic> json) => StockReturnSaveResult(
        returnNo: _str(json['return_no']),
        approvalStatus: _str(json['approval_status']).toUpperCase(),
        message: _str(json['message']),
        saveMode: _str(json['save_mode']).isEmpty ? 'pr_draft' : _str(json['save_mode']),
        inventoryPosted: json['inventory_posted'] == true,
        accountsPosted: json['accounts_posted'] == true,
        postedStockNo: _str(json['posted_stock_no']),
      );
}

class StockReturnService {
  StockReturnService(this._apiClient);
  final ApiClient _apiClient;

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    if (root['success'] == false) {
      final msg = '${root['message'] ?? 'Request failed'}'.trim();
      throw Exception(msg.isEmpty ? 'Request failed' : msg);
    }
    final data = root['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    throw Exception(
      '${root['message'] ?? 'Unexpected API response (missing data)'}'.trim(),
    );
  }

  Future<List<StockReturnSummary>> listReturns({
    String q = '',
    String tab = 'draft',
    int page = 1,
    int pageSize = 50,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/returns',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'tab': tab,
        'page': page,
        'page_size': pageSize,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['returns'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockReturnSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<StockReturnDetail> getReturnDetail(String returnNo, {String kind = 'request'}) async {
    final encoded = Uri.encodeComponent(returnNo.trim());
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/returns/$encoded',
      queryParameters: {'kind': kind},
    );
    return StockReturnDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<StockReturnOpenContext> getReturnOpen() async {
    final response = await _apiClient.dio.get('/api/v1/purchase/return/open');
    return StockReturnOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<StockReturnSaveResult> saveReturn({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
    String saveMode = 'pr_draft',
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/return/save',
      data: {
        'header': header,
        'lines': lines,
        'save_mode': saveMode,
      },
    );
    final raw = response.data;
    if (raw is! Map) {
      throw Exception('Unexpected save response from server.');
    }
    final result = StockReturnSaveResult.fromJson(
      _data(Map<String, dynamic>.from(raw)),
    );
    if (result.returnNo.trim().isEmpty) {
      throw Exception('Save completed but no return number was returned. Check the return list.');
    }
    return result;
  }

  Future<void> cancelReturn(String returnNo) async {
    final encoded = Uri.encodeComponent(returnNo.trim());
    await _apiClient.dio.post('/api/v1/purchase/returns/$encoded/cancel');
  }

  Future<Map<String, dynamic>> approveReturn(String returnNo, {String remarks = ''}) async {
    final encoded = Uri.encodeComponent(returnNo.trim());
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/returns/$encoded/approve',
      data: {'remarks': remarks},
    );
    return _data(response.data as Map<String, dynamic>);
  }

  Future<List<int>> downloadReturnPdf(String returnNo, {String kind = 'request'}) async {
    final encoded = Uri.encodeComponent(returnNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/purchase/returns/$encoded/pdf',
      queryParameters: {'kind': kind},
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}
