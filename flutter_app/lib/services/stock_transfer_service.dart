import 'package:dio/dio.dart';

import '../core/network/api_client.dart';
import '../models/stock_transfer.dart';

class StockTransferSaveResult {
  const StockTransferSaveResult({
    required this.transferNo,
    this.wasReassigned = false,
    this.requestedTransferNo = '',
  });

  final String transferNo;
  final bool wasReassigned;
  final String requestedTransferNo;
}

class StockTransferOpenContext {
  const StockTransferOpenContext({
    required this.transferNo,
    required this.transferDate,
    this.openDateFrom = '',
    this.openDateTo = '',
    this.transactionDateBlocked = false,
  });

  final String transferNo;
  final String transferDate;
  final String openDateFrom;
  final String openDateTo;
  final bool transactionDateBlocked;

  factory StockTransferOpenContext.fromJson(Map<String, dynamic> json) {
    return StockTransferOpenContext(
      transferNo: _asDocNo(json['transfer_no']),
      transferDate: '${json['transfer_date'] ?? ''}'.trim(),
      openDateFrom: '${json['open_date_from'] ?? ''}'.trim(),
      openDateTo: '${json['open_date_to'] ?? ''}'.trim(),
      transactionDateBlocked: json['transaction_date_blocked'] == true,
    );
  }
}

class StockTransferService {
  StockTransferService(this._apiClient);

  final ApiClient _apiClient;

  Map<String, dynamic> _unwrapData(dynamic responseData) {
    if (responseData is! Map) {
      throw Exception('Unexpected API response');
    }
    final root = Map<String, dynamic>.from(responseData);
    if (root['success'] == false) {
      throw Exception('${root['message'] ?? 'Request failed'}');
    }
    final data = root['data'];
    if (data is Map) return Map<String, dynamic>.from(data);
    throw Exception('${root['message'] ?? 'Unexpected API response'}');
  }

  String _pathNo(String transferNo) => Uri.encodeComponent(transferNo.trim());

  Future<List<StockTransferStore>> listStores() async {
    final response = await _apiClient.dio.get('/api/v1/stock-transfer/stores');
    final data = _unwrapData(response.data);
    return ((data['stores'] ?? []) as List<dynamic>)
        .whereType<Map>()
        .map((e) => StockTransferStore.fromJson(Map<String, dynamic>.from(e)))
        .where((s) => s.code.isNotEmpty)
        .toList();
  }

  Future<List<StockTransferSummary>> listTransfers({
    String bucket = 'all',
    String fromStore = '',
    String toStore = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/stock-transfer/transfers',
      queryParameters: {
        'bucket': bucket,
        if (fromStore.isNotEmpty) 'from_store': fromStore,
        if (toStore.isNotEmpty) 'to_store': toStore,
      },
    );
    final data = _unwrapData(response.data);
    return ((data['rows'] ?? []) as List<dynamic>)
        .whereType<Map>()
        .map((e) => StockTransferSummary.fromJson(Map<String, dynamic>.from(e)))
        .where((r) => r.transferNo.isNotEmpty)
        .toList();
  }

  Future<String> nextTransferNo() async {
    final open = await getOpenContext();
    return open.transferNo;
  }

  Future<StockTransferOpenContext> getOpenContext() async {
    final response = await _apiClient.dio.get('/api/v1/stock-transfer/transfers/next-no');
    final data = _unwrapData(response.data);
    return StockTransferOpenContext.fromJson(data);
  }

  Future<StockTransferDetail?> getTransfer(String transferNo) async {
    final no = transferNo.trim();
    if (no.isEmpty) return null;
    final response = await _apiClient.dio.get('/api/v1/stock-transfer/transfers/${_pathNo(no)}');
    final raw = response.data;
    if (raw is! Map) return null;
    final root = Map<String, dynamic>.from(raw);
    if (root['success'] == false) return null;
    final data = root['data'];
    if (data is! Map || data.isEmpty) return null;
    return StockTransferDetail.fromJson(Map<String, dynamic>.from(data));
  }

  Future<List<StockTransferItemOption>> searchItems({
    required String fromStore,
    String search = '',
    String? exactBarcode,
    int? exactItemCode,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/stock-transfer/items',
      queryParameters: {
        'from_store': fromStore,
        if (search.isNotEmpty) 'search': search,
        if (exactBarcode != null && exactBarcode.trim().isNotEmpty)
          'exact_barcode': exactBarcode.trim(),
        if (exactItemCode != null && exactItemCode > 0) 'exact_item_code': exactItemCode,
      },
    );
    final data = _unwrapData(response.data);
    final seen = <int>{};
    return ((data['items'] ?? []) as List<dynamic>)
        .whereType<Map>()
        .map((e) => StockTransferItemOption.fromJson(Map<String, dynamic>.from(e)))
        .where((i) => i.itemCode > 0 && seen.add(i.itemCode))
        .toList();
  }

  Future<StockTransferItemStock> getItemStock({
    required int itemCode,
    required String store,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/stock-transfer/item-stock',
      queryParameters: {
        'item_code': itemCode,
        'store': store,
      },
    );
    final data = _unwrapData(response.data);
    return StockTransferItemStock.fromJson(data);
  }

  Future<StockTransferSaveResult> saveTransfer({
    required String transferNo,
    required String transferDate,
    required String fromStore,
    required String toStore,
    required String remarks,
    required List<StockTransferLine> lines,
    bool updateExisting = false,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/stock-transfer/transfers',
      data: {
        'transfer_no': transferNo,
        'transfer_date': transferDate,
        'from_store': fromStore,
        'to_store': toStore,
        'remarks': remarks,
        'update_existing': updateExisting,
        'lines': lines.map((l) => l.toSaveJson()).toList(),
      },
    );
    final data = _unwrapData(response.data);
    final savedNo = _asDocNo(data['transfer_no']);
    return StockTransferSaveResult(
      transferNo: savedNo.isNotEmpty ? savedNo : transferNo,
      wasReassigned: data['transfer_no_reassigned'] == true,
      requestedTransferNo: _asDocNo(data['requested_transfer_no']),
    );
  }

  Future<void> postTransfer(String transferNo) async {
    final no = transferNo.trim();
    await _apiClient.dio.post('/api/v1/stock-transfer/transfers/${_pathNo(no)}/transfer');
  }

  Future<void> approveTransfer(String transferNo) async {
    final no = transferNo.trim();
    await _apiClient.dio.post('/api/v1/stock-transfer/transfers/${_pathNo(no)}/approve');
  }

  /// ERP store-transfer PDF bytes.
  Future<List<int>> downloadTransferPdf(String transferNo, {bool duplicate = false}) async {
    final no = transferNo.trim();
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/stock-transfer/transfers/${_pathNo(no)}/pdf',
      queryParameters: {if (duplicate) 'copy': 1},
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}

String _asDocNo(dynamic value) {
  if (value == null) return '';
  final s = '$value'.trim();
  if (s.isEmpty || s == '0' || s == 'null') return '';
  return s;
}
