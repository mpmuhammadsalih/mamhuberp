import 'package:dio/dio.dart';

import '../core/network/api_client.dart';
import '../models/business_summary.dart';

class InventoryReportPayload {
  const InventoryReportPayload({
    required this.rows,
    this.summary,
    this.meta = const {},
  });

  final List<Map<String, dynamic>> rows;
  final Map<String, dynamic>? summary;
  final Map<String, dynamic> meta;

  factory InventoryReportPayload.fromData(Map<String, dynamic> data) {
    final rawRows = data['rows'];
    final rows = <Map<String, dynamic>>[];
    if (rawRows is List) {
      for (final r in rawRows) {
        if (r is Map) {
          rows.add(Map<String, dynamic>.from(r));
        }
      }
    }
    Map<String, dynamic>? summary;
    final s = data['summary'];
    if (s is Map) {
      summary = Map<String, dynamic>.from(s);
    }
    final meta = Map<String, dynamic>.from(data)
      ..remove('rows')
      ..remove('summary');
    return InventoryReportPayload(rows: rows, summary: summary, meta: meta);
  }
}

class ReportsService {
  ReportsService(this._apiClient);

  final ApiClient _apiClient;

  Options get _reportTimeout => Options(
        receiveTimeout: const Duration(seconds: 90),
        sendTimeout: const Duration(seconds: 30),
      );

  Map<String, dynamic> _data(Map<String, dynamic> root) =>
      root['data'] as Map<String, dynamic>;

  Future<InventoryReportPayload> _getReport(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    final response = await _apiClient.dio.get(
      path,
      queryParameters: queryParameters,
      options: _reportTimeout,
    );
    return InventoryReportPayload.fromData(_data(response.data as Map<String, dynamic>));
  }

  Future<BusinessSummaryData> getBusinessSummary({
    required String dateFrom,
    required String dateTo,
    String branch = '',
  }) async {
    // ERP business summary runs many Oracle queries; allow extra time vs default 20s.
    final response = await _apiClient.dio.get(
      '/api/v1/reports/business-summary',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (branch.isNotEmpty) 'branch': branch,
      },
      options: Options(
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    return BusinessSummaryData.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<InventoryReportPayload> getWarehouseSummary({String q = ''}) {
    return _getReport(
      '/api/v1/reports/warehouse-summary',
      queryParameters: {
        if (q.isNotEmpty) 'q': q,
      },
    );
  }

  Future<InventoryReportPayload> getSupplierBalance({
    String q = '',
    double minBalance = 0,
  }) {
    return _getReport(
      '/api/v1/reports/supplier-balance',
      queryParameters: {
        if (q.isNotEmpty) 'q': q,
        if (minBalance > 0) 'min_balance': minBalance,
      },
    );
  }

  Future<InventoryReportPayload> getInventoryAging({
    String asOnDate = '',
    String q = '',
    String warehouseId = '',
  }) {
    return _getReport(
      '/api/v1/reports/inventory-aging',
      queryParameters: {
        if (asOnDate.isNotEmpty) 'as_on_date': asOnDate,
        if (q.isNotEmpty) 'q': q,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
      },
    );
  }

  Future<InventoryReportPayload> getStockSummary({
    String q = '',
    String warehouseId = '',
    bool includeZero = false,
    int limit = 200,
  }) {
    return _getReport(
      '/api/v1/reports/stock-summary',
      queryParameters: {
        if (q.isNotEmpty) 'q': q,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        'include_zero': includeZero,
        'limit': limit,
      },
    );
  }

  Future<InventoryReportPayload> getStockLedger({
    String dateFrom = '',
    String dateTo = '',
    String q = '',
    String itemCode = '',
    String reportMode = 'detail',
    int limit = 500,
  }) {
    return _getReport(
      '/api/v1/reports/stock-ledger',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (q.isNotEmpty) 'q': q,
        if (itemCode.isNotEmpty) 'item_code': itemCode,
        'report_mode': reportMode,
        'limit': limit,
      },
    );
  }

  Future<InventoryReportPayload> getInventoryHistory({
    String dateFrom = '',
    String dateTo = '',
    String q = '',
    String itemCode = '',
    int limit = 500,
  }) {
    return _getReport(
      '/api/v1/reports/inventory-history',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (q.isNotEmpty) 'q': q,
        if (itemCode.isNotEmpty) 'item_code': itemCode,
        'limit': limit,
      },
    );
  }

  Future<InventoryReportPayload> getTransactionSummary({
    String dateFrom = '',
    String dateTo = '',
    String transactionTypes = '',
  }) {
    return _getReport(
      '/api/v1/reports/transactions/summary',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (transactionTypes.isNotEmpty) 'transaction_types': transactionTypes,
      },
    );
  }

  Future<InventoryReportPayload> getTransactionDetails({
    String dateFrom = '',
    String dateTo = '',
    String transactionTypes = '',
    String q = '',
    int limit = 400,
  }) {
    return _getReport(
      '/api/v1/reports/transactions/details',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (transactionTypes.isNotEmpty) 'transaction_types': transactionTypes,
        if (q.isNotEmpty) 'q': q,
        'limit': limit,
      },
    );
  }

  Future<List<int>> downloadTransactionSummaryPdf({
    String dateFrom = '',
    String dateTo = '',
    String transactionTypes = '',
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/reports/transactions/summary/pdf',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (transactionTypes.isNotEmpty) 'transaction_types': transactionTypes,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<List<int>> downloadTransactionDetailsPdf({
    String dateFrom = '',
    String dateTo = '',
    String transactionTypes = '',
    String q = '',
    int limit = 300,
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/reports/transactions/details/pdf',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (transactionTypes.isNotEmpty) 'transaction_types': transactionTypes,
        if (q.isNotEmpty) 'q': q,
        'limit': limit,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<InventoryReportPayload> getSalesDetails({
    String dateFrom = '',
    String dateTo = '',
    String billNo = '',
    String orderNo = '',
    String customerCode = '',
    String billType = '',
    String txnKind = 'all',
    String itemCode = '',
    int limit = 500,
  }) {
    return _getReport(
      '/api/v1/reports/sales-details',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (billNo.isNotEmpty) 'bill_no': billNo,
        if (orderNo.isNotEmpty) 'order_no': orderNo,
        if (customerCode.isNotEmpty) 'customer_code': customerCode,
        if (billType.isNotEmpty) 'bill_type': billType,
        if (txnKind.isNotEmpty) 'txn_kind': txnKind,
        if (itemCode.isNotEmpty) 'item_code': itemCode,
        'limit': limit,
      },
    );
  }

  Future<List<Map<String, dynamic>>> searchSalesDetailCustomers({
    String q = '',
    int limit = 300,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/reports/sales-details/customers',
      queryParameters: {
        if (q.isNotEmpty) 'q': q,
        'limit': limit,
      },
      options: _reportTimeout,
    );
    final data = _data(response.data as Map<String, dynamic>);
    final raw = data['customers'];
    final out = <Map<String, dynamic>>[];
    if (raw is List) {
      for (final r in raw) {
        if (r is Map) out.add(Map<String, dynamic>.from(r));
      }
    }
    return out;
  }

  Future<List<Map<String, dynamic>>> searchSalesDetailItems({
    String q = '',
    int limit = 300,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/reports/sales-details/items',
      queryParameters: {
        if (q.isNotEmpty) 'q': q,
        'limit': limit,
      },
      options: _reportTimeout,
    );
    final data = _data(response.data as Map<String, dynamic>);
    final raw = data['items'];
    final out = <Map<String, dynamic>>[];
    if (raw is List) {
      for (final r in raw) {
        if (r is Map) out.add(Map<String, dynamic>.from(r));
      }
    }
    return out;
  }

  Future<List<int>> downloadSalesDetailsPdf({
    String dateFrom = '',
    String dateTo = '',
    String billNo = '',
    String orderNo = '',
    String customerCode = '',
    String billType = '',
    String txnKind = 'all',
    String itemCode = '',
    int limit = 800,
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/reports/sales-details/pdf',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (billNo.isNotEmpty) 'bill_no': billNo,
        if (orderNo.isNotEmpty) 'order_no': orderNo,
        if (customerCode.isNotEmpty) 'customer_code': customerCode,
        if (billType.isNotEmpty) 'bill_type': billType,
        if (txnKind.isNotEmpty) 'txn_kind': txnKind,
        if (itemCode.isNotEmpty) 'item_code': itemCode,
        'limit': limit,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<Map<String, dynamic>> getXReportOpen() async {
    final response = await _apiClient.dio.get(
      '/api/v1/reports/x-report/open',
      options: _reportTimeout,
    );
    return _data(response.data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> getXReport({
    int counterCode = 0,
    String posDate = '',
    String dateFrom = '',
    String dateTo = '',
    bool isFinal = false,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/reports/x-report',
      queryParameters: {
        'counter_code': counterCode,
        if (posDate.isNotEmpty) 'pos_date': posDate,
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (isFinal) 'final': 1,
      },
      options: _reportTimeout,
    );
    return _data(response.data as Map<String, dynamic>);
  }

  Future<List<int>> downloadXReportPdf({
    int counterCode = 0,
    String posDate = '',
    String dateFrom = '',
    String dateTo = '',
    bool isFinal = false,
  }) async {
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/reports/x-report/pdf',
      queryParameters: {
        'counter_code': counterCode,
        if (posDate.isNotEmpty) 'pos_date': posDate,
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (isFinal) 'final': 1,
      },
      options: Options(
        responseType: ResponseType.bytes,
        receiveTimeout: const Duration(seconds: 120),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<Map<String, dynamic>> getCustomerWiseSales({
    String dateFrom = '',
    String dateTo = '',
    String customerCode = '',
    String billType = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/reports/customer-wise-sales',
      queryParameters: {
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        if (customerCode.isNotEmpty) 'customer_code': customerCode,
        if (billType.isNotEmpty) 'bill_type': billType,
      },
      options: _reportTimeout,
    );
    return _data(response.data as Map<String, dynamic>);
  }
}
