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

class StockAdjustmentSummary {
  StockAdjustmentSummary({
    required this.adjNo,
    required this.adjDate,
    required this.remarks,
    required this.status,
    required this.stockValue,
    this.canReverse = false,
  });

  final String adjNo;
  final String adjDate;
  final String remarks;
  final String status;
  final double stockValue;
  final bool canReverse;

  bool get isPosted => status == 'POSTED';
  bool get isReversed => status == 'REVERSED';
  bool get isReversal => status == 'REVERSAL';

  factory StockAdjustmentSummary.fromJson(Map<String, dynamic> json) => StockAdjustmentSummary(
        adjNo: _str(json['adj_no'] ?? json['adjno']),
        adjDate: _str(json['adj_date'] ?? json['adjdate']),
        remarks: _str(json['remarks']),
        status: _str(json['status']).toUpperCase(),
        stockValue: _num(json['stock_value'] ?? json['stockvalue']),
        canReverse: json['can_reverse'] == true,
      );
}

class StockAdjustmentLine {
  StockAdjustmentLine({
    required this.lineNo,
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.store,
    required this.currentQty,
    required this.adjustQty,
    required this.newQty,
    required this.baseQty,
    required this.cost,
    this.factor = 1,
  });

  final int lineNo;
  final String itemCode;
  final String itemName;
  final String uom;
  final String store;
  final double currentQty;
  final double adjustQty;
  final double newQty;
  final double baseQty;
  final double cost;
  final double factor;

  double get lineValue => adjustQty.abs() * cost;

  factory StockAdjustmentLine.fromJson(Map<String, dynamic> json) => StockAdjustmentLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        itemCode: _str(json['item_code'] ?? json['itemcode']),
        itemName: _str(json['item_name'] ?? json['itemname']),
        uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
        store: _str(json['store']),
        currentQty: _num(json['current_qty'] ?? json['currentqty']),
        adjustQty: _num(json['adjust_qty'] ?? json['adjustqty']),
        newQty: _num(json['new_qty'] ?? json['newqty']),
        baseQty: _num(json['base_qty'] ?? json['baseqty']),
        cost: _num(json['cost'] ?? json['rate']),
        factor: _factorFromJson(json),
      );
}

class StockAdjustmentDetail {
  StockAdjustmentDetail({
    required this.summary,
    required this.lines,
    this.remarks = '',
    this.store = '',
    this.openingStock = false,
    this.canReverse = false,
    this.reversedAdjNo = '',
    this.reversalOfAdjNo = '',
  });

  final StockAdjustmentSummary summary;
  final List<StockAdjustmentLine> lines;
  final String remarks;
  final String store;
  final bool openingStock;
  final bool canReverse;
  final String reversedAdjNo;
  final String reversalOfAdjNo;

  factory StockAdjustmentDetail.fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockAdjustmentLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return StockAdjustmentDetail(
      summary: StockAdjustmentSummary.fromJson(json),
      lines: lines,
      remarks: _str(json['remarks']),
      store: _str(json['store'] ?? json['default_store']),
      openingStock: json['opening_stock'] == true,
      canReverse: json['can_reverse'] == true,
      reversedAdjNo: _str(json['reversed_adj_no']),
      reversalOfAdjNo: _str(json['reversal_of_adj_no']),
    );
  }
}

class StockAdjustmentOpenContext {
  StockAdjustmentOpenContext({
    required this.adjNo,
    required this.adjDate,
    this.defaultStore = '',
    this.openingStockMode = false,
  });

  final String adjNo;
  final String adjDate;
  final String defaultStore;
  final bool openingStockMode;

  factory StockAdjustmentOpenContext.fromJson(Map<String, dynamic> json) => StockAdjustmentOpenContext(
        adjNo: _str(json['adj_no']),
        adjDate: _str(json['adj_date']),
        defaultStore: _str(json['default_store']),
        openingStockMode: json['opening_stock_mode'] == true,
      );
}

class StockAdjustmentWarehouse {
  StockAdjustmentWarehouse({
    required this.code,
    required this.name,
    this.allowNegativeStock = false,
  });

  final String code;
  final String name;
  final bool allowNegativeStock;

  String get label => name.isNotEmpty ? name : code;

  factory StockAdjustmentWarehouse.fromJson(Map<String, dynamic> json) => StockAdjustmentWarehouse(
        code: _str(json['code']),
        name: _str(json['name']),
        allowNegativeStock: json['allow_negative_stock'] == true,
      );
}

class StockAdjustmentCatalogItem {
  StockAdjustmentCatalogItem({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.barcode,
    required this.cost,
    required this.currentStock,
    this.bestStore = '',
  });

  final String itemCode;
  final String itemName;
  final String uom;
  final String barcode;
  final double cost;
  final double currentStock;
  final String bestStore;

  factory StockAdjustmentCatalogItem.fromJson(Map<String, dynamic> json) => StockAdjustmentCatalogItem(
        itemCode: _str(json['item_code'] ?? json['itemcode']),
        itemName: _str(json['item_name'] ?? json['itemname']),
        uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
        barcode: _str(json['barcode']),
        cost: _num(json['cost'] ?? json['rate']),
        currentStock: _num(json['current_stock'] ?? json['currentstock']),
        bestStore: _str(json['best_store']),
      );
}

class StockAdjustmentUom {
  StockAdjustmentUom({
    required this.uom,
    required this.rate,
    this.barcode = '',
    this.factor = 1,
  });

  final String uom;
  final double rate;
  final String barcode;
  final double factor;

  factory StockAdjustmentUom.fromJson(Map<String, dynamic> json) => StockAdjustmentUom(
        uom: _str(json['uom']).isEmpty ? 'NOS' : _str(json['uom']),
        rate: _num(json['rate'] ?? json['cost']),
        barcode: _str(json['barcode']),
        factor: _factorFromJson(json),
      );
}

class StockAdjustmentItemStock {
  StockAdjustmentItemStock({
    required this.currentQty,
    required this.store,
    this.stores = const [],
  });

  final double currentQty;
  final String store;
  final List<Map<String, dynamic>> stores;

  factory StockAdjustmentItemStock.fromJson(Map<String, dynamic> json) => StockAdjustmentItemStock(
        currentQty: _num(json['current_qty'] ?? json['currentqty']),
        store: _str(json['store']),
        stores: (json['stores'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList(),
      );
}

class StockAdjustmentSaveResult {
  StockAdjustmentSaveResult({
    required this.adjNo,
    this.status = 'POSTED',
    this.message = '',
    this.stockValue = 0,
  });

  final String adjNo;
  final String status;
  final String message;
  final double stockValue;

  factory StockAdjustmentSaveResult.fromJson(Map<String, dynamic> json) => StockAdjustmentSaveResult(
        adjNo: _str(json['adj_no']),
        status: _str(json['status']).toUpperCase(),
        message: _str(json['message']),
        stockValue: _num(json['stock_value'] ?? json['stockvalue']),
      );
}

class StockAdjustmentService {
  StockAdjustmentService(this._apiClient);
  final ApiClient _apiClient;

  static const _base = '/api/v1/stock-adjustment';

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    final data = root['data'];
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return root;
  }

  Future<List<StockAdjustmentSummary>> listAdjustments({
    String q = '',
    int page = 1,
    int pageSize = 50,
  }) async {
    final response = await _apiClient.dio.get(
      '$_base/adjustments',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'page': page,
        'page_size': pageSize,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['adjustments'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockAdjustmentSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<StockAdjustmentOpenContext> getOpen() async {
    final response = await _apiClient.dio.get('$_base/open');
    return StockAdjustmentOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<StockAdjustmentWarehouse>> listWarehouses() async {
    final response = await _apiClient.dio.get('$_base/warehouses');
    final data = _data(response.data as Map<String, dynamic>);
    return (data['warehouses'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockAdjustmentWarehouse.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<StockAdjustmentCatalogItem>> searchCatalog({
    String q = '',
    int limit = 50,
  }) async {
    final response = await _apiClient.dio.get(
      '$_base/catalog',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['items'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockAdjustmentCatalogItem.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<StockAdjustmentUom>> getItemUoms(String itemCode) async {
    final response = await _apiClient.dio.get(
      '$_base/item-uoms',
      queryParameters: {'item_code': itemCode.trim()},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['uoms'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => StockAdjustmentUom.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<StockAdjustmentItemStock> getItemStock({
    required String itemCode,
    required String store,
  }) async {
    final response = await _apiClient.dio.get(
      '$_base/item-stock',
      queryParameters: {
        'item_code': itemCode.trim(),
        'store': store.trim(),
      },
    );
    return StockAdjustmentItemStock.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<StockAdjustmentDetail> getAdjustmentDetail(String adjNo) async {
    final encoded = Uri.encodeComponent(adjNo.trim());
    final response = await _apiClient.dio.get('$_base/adjustments/$encoded');
    return StockAdjustmentDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<StockAdjustmentSaveResult> saveAdjustment({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '$_base/adjustments',
      data: {'header': header, 'lines': lines},
    );
    return StockAdjustmentSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<Map<String, dynamic>> reverseAdjustment(String adjNo) async {
    final encoded = Uri.encodeComponent(adjNo.trim());
    final response = await _apiClient.dio.post('$_base/adjustments/$encoded/reverse');
    return _data(response.data as Map<String, dynamic>);
  }

  Future<List<int>> downloadPdf(String adjNo) async {
    final encoded = Uri.encodeComponent(adjNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '$_base/adjustments/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}
