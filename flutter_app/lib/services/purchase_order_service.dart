import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

String _str(dynamic v) => '${v ?? ''}'.trim();

class PurchaseOrderSummary {
  PurchaseOrderSummary({
    required this.lpono,
    required this.lpoDate,
    required this.supplierCode,
    required this.supplierName,
    required this.amount,
    required this.approvalStatus,
  });

  final String lpono;
  final String lpoDate;
  final String supplierCode;
  final String supplierName;
  final double amount;
  final String approvalStatus;

  String get supplierLabel {
    if (supplierName.isNotEmpty) return supplierName;
    if (supplierCode.isNotEmpty) return 'Supplier $supplierCode';
    return 'Supplier';
  }

  factory PurchaseOrderSummary.fromJson(Map<String, dynamic> json) => PurchaseOrderSummary(
        lpono: _str(json['lpono']),
        lpoDate: _str(json['lpo_date'] ?? json['lpodate']),
        supplierCode: _str(json['supplier_code'] ?? json['suppliercode']),
        supplierName: _str(json['supplier_name'] ?? json['suppliername']),
        amount: _num(json['amount']),
        approvalStatus: _str(json['approval_status']).toUpperCase(),
      );
}

class PurchaseOrderLine {
  PurchaseOrderLine({
    required this.lineNo,
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    this.discount = 0,
    this.amount = 0,
    this.barcode = '',
    this.warehouseId,
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
  final String? warehouseId;

  factory PurchaseOrderLine.fromJson(Map<String, dynamic> json) => PurchaseOrderLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        itemCode: _str(json['item_code'] ?? json['itemcode']),
        itemName: _str(json['item_name'] ?? json['itemname']),
        uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
        qty: _num(json['qty'] ?? json['quantity']),
        rate: _num(json['rate']),
        discount: _num(json['discount']),
        amount: _num(json['amount']),
        barcode: _str(json['barcode']),
        warehouseId: json['warehouse_id'] == null || _str(json['warehouse_id']).isEmpty
            ? null
            : _str(json['warehouse_id']),
      );
}

class PurchaseOrderDetail {
  PurchaseOrderDetail({
    required this.summary,
    required this.lines,
    this.discount = 0,
    this.otherCharge = 0,
    this.remarks = '',
    this.warehouseId,
    this.hasGrn = false,
  });

  final PurchaseOrderSummary summary;
  final List<PurchaseOrderLine> lines;
  final double discount;
  final double otherCharge;
  final String remarks;
  final String? warehouseId;
  final bool hasGrn;

  bool get isDraft => summary.approvalStatus == 'DRAFT' || summary.approvalStatus.isEmpty;
  bool get isApproved => summary.approvalStatus == 'APPROVED';
  bool get isCanceled => summary.approvalStatus == 'CANCELLED' || summary.approvalStatus == 'CANCELED';
  /// Draft or approved POs can be edited until a GRN exists.
  bool get canEdit => !isCanceled && !hasGrn;

  factory PurchaseOrderDetail.fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseOrderLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return PurchaseOrderDetail(
      summary: PurchaseOrderSummary.fromJson(json),
      lines: lines,
      discount: _num(json['discount']),
      otherCharge: _num(json['other_charge'] ?? json['othercharge']),
      remarks: _str(json['remarks']),
      warehouseId: json['warehouse_id'] == null || _str(json['warehouse_id']).isEmpty
          ? null
          : _str(json['warehouse_id']),
      hasGrn: json['has_grn'] == true,
    );
  }
}

class PurchaseOrderOpenContext {
  PurchaseOrderOpenContext({
    required this.lpono,
    required this.lpoDate,
    this.warehouseEnabled = false,
    this.defaultWarehouseId,
    this.defaultWarehouseCode = '',
    this.defaultWarehouseName = '',
    this.defaultWarehouseLabel = '',
  });

  final String lpono;
  final String lpoDate;
  final bool warehouseEnabled;
  final String? defaultWarehouseId;
  final String defaultWarehouseCode;
  final String defaultWarehouseName;
  final String defaultWarehouseLabel;

  factory PurchaseOrderOpenContext.fromJson(Map<String, dynamic> json) {
    final features = json['features'] as Map<String, dynamic>? ?? const {};
    return PurchaseOrderOpenContext(
      lpono: _str(json['lpono']),
      lpoDate: _str(json['lpo_date']),
      warehouseEnabled: features['warehouse_enabled'] == true,
      defaultWarehouseId: json['default_warehouse_id'] == null || _str(json['default_warehouse_id']).isEmpty
          ? null
          : _str(json['default_warehouse_id']),
      defaultWarehouseCode: _str(json['default_warehouse_code']),
      defaultWarehouseName: _str(json['default_warehouse_name']),
      defaultWarehouseLabel: _str(json['default_warehouse_label']),
    );
  }
}

class PurchaseSupplierOption {
  PurchaseSupplierOption({required this.code, required this.name});
  final String code;
  final String name;
  factory PurchaseSupplierOption.fromJson(Map<String, dynamic> json) => PurchaseSupplierOption(
        code: _str(json['code']),
        name: _str(json['name']),
      );
}

class PurchaseCatalogItem {
  PurchaseCatalogItem({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.rate,
    this.barcode = '',
    this.currentStock = 0,
    this.averageCost = 0,
    this.costPrice = 0,
    this.lastQty = 0,
    this.lastRate = 0,
    this.lastReceiptDate = '',
    this.lastReceiptNo = '',
  });
  final String itemCode;
  final String itemName;
  final String uom;
  /// Default add rate (average cost preferred).
  final double rate;
  final String barcode;
  final double currentStock;
  final double averageCost;
  final double costPrice;
  /// Last GRN qty for this supplier (Supplier items tab).
  final double lastQty;
  /// Last GRN rate for this supplier.
  final double lastRate;
  /// Last GRN date (YYYY-MM-DD).
  final String lastReceiptDate;
  final String lastReceiptNo;

  double get displayAvgCost => averageCost > 0 ? averageCost : rate;
  double get displayCostPrice => costPrice > 0 ? costPrice : (rate > 0 ? rate : averageCost);

  bool get hasSupplierHistory =>
      lastQty > 0 || lastReceiptDate.isNotEmpty || lastReceiptNo.isNotEmpty;

  factory PurchaseCatalogItem.fromJson(Map<String, dynamic> json) {
    final avg = _num(json['average_cost'] ?? json['averagecost']);
    final cprice = _num(json['cost_price'] ?? json['costprice']);
    final fallback = _num(json['rate']);
    final costPrice = cprice > 0 ? cprice : fallback;
    final averageCost = avg > 0 ? avg : fallback;
    return PurchaseCatalogItem(
      itemCode: _str(json['item_code']),
      itemName: _str(json['item_name']),
      uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
      // Default add rate = cost price.
      rate: costPrice > 0 ? costPrice : averageCost,
      barcode: _str(json['barcode']),
      currentStock: _num(json['current_stock'] ?? json['currentstock'] ?? json['stock']),
      averageCost: averageCost,
      costPrice: costPrice,
      lastQty: _num(json['last_qty']),
      lastRate: _num(json['last_rate']),
      lastReceiptDate: _str(
        json['last_receiptdate'] ?? json['last_receipt_date'] ?? json['receipt_date'],
      ),
      lastReceiptNo: _str(
        json['last_receiptno'] ?? json['last_receipt_no'] ?? json['receipt_no'],
      ),
    );
  }
}

class PurchaseUomOption {
  PurchaseUomOption({
    required this.uom,
    required this.rate,
    this.barcode = '',
    this.factor = 1,
  });
  final String uom;
  final double rate;
  final String barcode;
  /// ITEMMASTER base UOM is always 1; alternate UOMs use CONVERSIONFACTOR.
  final double factor;
  factory PurchaseUomOption.fromJson(Map<String, dynamic> json) {
    final factor = _num(json['factor'] ?? json['conversionfactor'] ?? json['conversion_factor']);
    return PurchaseUomOption(
      uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
      rate: _num(json['rate']),
      barcode: _str(json['barcode']),
      factor: factor > 0 ? factor : 1,
    );
  }
}

class PurchaseWarehouseOption {
  PurchaseWarehouseOption({
    required this.warehouseId,
    this.warehouseCode = '',
    this.warehouseName = '',
    this.label = '',
  });
  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String label;
  factory PurchaseWarehouseOption.fromJson(Map<String, dynamic> json) => PurchaseWarehouseOption(
        warehouseId: _str(json['warehouse_id']),
        warehouseCode: _str(json['warehouse_code']),
        warehouseName: _str(json['warehouse_name']),
        label: _str(json['label']),
      );
}

class PurchaseOrderSaveResult {
  PurchaseOrderSaveResult({
    required this.lpono,
    this.approvalStatus = 'DRAFT',
    this.message = '',
    this.lponoReassigned = false,
  });
  final String lpono;
  final String approvalStatus;
  final String message;
  final bool lponoReassigned;
  factory PurchaseOrderSaveResult.fromJson(Map<String, dynamic> json) => PurchaseOrderSaveResult(
        lpono: _str(json['lpono']),
        approvalStatus: _str(json['approval_status']).toUpperCase(),
        message: _str(json['message']),
        lponoReassigned: json['lpono_reassigned'] == true,
      );
}

class PurchaseOrderService {
  PurchaseOrderService(this._apiClient);
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

  Future<List<PurchaseOrderSummary>> listOrders({
    String q = '',
    String tab = 'draft',
    int page = 1,
    int pageSize = 50,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/orders',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'tab': tab,
        'page': page,
        'page_size': pageSize,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['orders'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseOrderSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<PurchaseOrderDetail> getOrderDetail(String lpono) async {
    final encoded = Uri.encodeComponent(lpono.trim());
    final response = await _apiClient.dio.get('/api/v1/purchase/orders/$encoded');
    return PurchaseOrderDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<PurchaseOrderOpenContext> getOrderOpen() async {
    final response = await _apiClient.dio.get('/api/v1/purchase/order/open');
    return PurchaseOrderOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<PurchaseSupplierOption>> searchSuppliers({String q = '', int limit = 80}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/order/suppliers',
      queryParameters: {'q': q.trim(), 'limit': limit},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['suppliers'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseSupplierOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<PurchaseCatalogItem>> searchCatalog({
    String q = '',
    int limit = 80,
    String supplierCode = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/order/catalog',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
        if (supplierCode.trim().isNotEmpty) 'supplier_code': supplierCode.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['items'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseCatalogItem.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  /// Items previously purchased from [supplierCode] (+ master SUPCODE), like Sales customer items.
  Future<List<PurchaseCatalogItem>> listSupplierItems({
    required String supplierCode,
    String q = '',
    int limit = 80,
    int days = 365,
  }) async {
    final code = supplierCode.trim();
    if (code.isEmpty || code == '0') return const [];
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/order/supplier-items',
      queryParameters: {
        'supplier_code': code,
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
        'days': days,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['items'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseCatalogItem.fromJson(Map<String, dynamic>.from(e)))
        .where((e) => e.itemCode.isNotEmpty)
        .toList();
  }

  Future<List<PurchaseUomOption>> getItemUoms(String itemCode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/order/item-uoms',
      queryParameters: {'item_code': itemCode.trim()},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['uoms'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseUomOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<PurchaseWarehouseOption>> searchWarehouses({String q = '', int limit = 100}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/order/warehouses',
      queryParameters: {'q': q.trim(), 'limit': limit},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['warehouses'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => PurchaseWarehouseOption.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  /// When the branch has exactly one warehouse, return it for auto-select.
  Future<PurchaseWarehouseOption?> soleWarehouseIfOnlyOne() async {
    final rows = await searchWarehouses(limit: 5);
    if (rows.length != 1) return null;
    final w = rows.first;
    if (w.warehouseId.trim().isEmpty) return null;
    return w;
  }

  Future<PurchaseOrderSaveResult> saveOrder({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/order/save',
      data: {'header': header, 'lines': lines},
    );
    final raw = response.data;
    if (raw is! Map) {
      throw Exception('Unexpected save response from server.');
    }
    final result = PurchaseOrderSaveResult.fromJson(
      _data(Map<String, dynamic>.from(raw)),
    );
    if (result.lpono.trim().isEmpty) {
      throw Exception('Save completed but no PO number was returned. Check the PO list.');
    }
    return result;
  }

  /// ERP purchase-order PDF bytes for [lpono] (same layout as desktop PO print).
  Future<List<int>> downloadOrderPdf(String lpono) async {
    final encoded = Uri.encodeComponent(lpono.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/purchase/orders/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<void> cancelOrder(String lpono) async {
    final encoded = Uri.encodeComponent(lpono.trim());
    await _apiClient.dio.post('/api/v1/purchase/orders/$encoded/cancel');
  }
}
