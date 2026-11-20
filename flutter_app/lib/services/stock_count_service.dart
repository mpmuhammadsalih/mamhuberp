import '../core/network/api_client.dart';
import '../models/stock_count_session.dart';

class StockCountService {
  StockCountService(this._apiClient);

  final ApiClient _apiClient;

  Future<List<StockCountSummary>> listSessions({
    int? locationcode,
    int limit = 50,
    String status = 'OPEN',
    bool availableForUser = false,
  }) async {
    final q = <String, dynamic>{
      'limit': limit,
      'status': status,
      'available_for_user': availableForUser,
    };
    // Only send when user filters; omit = all locations (API default locationcode=0)
    if (locationcode != null && locationcode > 0) {
      q['locationcode'] = locationcode;
    }

    final response = await _apiClient.dio.get(
      '/api/v1/stock-count/sessions',
      queryParameters: q,
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map(StockCountSummary.fromJson).toList();
  }

  Future<StockCountSession> ensureDraftSession({
    required int locationcode,
    int? warehouseId,
    int? storageId,
    String remarks = '',
    bool forceNew = false,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/stock-count/sessions',
      queryParameters: {if (forceNew) 'force_new': true},
      data: {
        'locationcode': locationcode,
        if (warehouseId != null) 'warehouse_id': warehouseId,
        if (storageId != null) 'storage_id': storageId,
        'remarks': remarks,
      },
    );
    return _sessionFromResponse(response.data as Map<String, dynamic>);
  }

  Future<StockCountSession?> getCurrentDraft(int locationcode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/stock-count/sessions/current',
      queryParameters: {'locationcode': locationcode},
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'];
    if (data is! Map || data.isEmpty || data['count_no'] == null) {
      return null;
    }
    return StockCountSession.fromJson(Map<String, dynamic>.from(data));
  }

  Future<StockCountSession> getSession(int locationcode, int countNo) async {
    final response = await _apiClient.dio.get(
      '/api/v1/stock-count/sessions/$countNo',
      queryParameters: {'locationcode': locationcode},
    );
    return _sessionFromResponse(response.data as Map<String, dynamic>);
  }

  Future<StockCountLine> upsertLine({
    required int locationcode,
    required int countNo,
    required String itemcode,
    required double countedQty,
    required double systemQty,
    String uom = '',
    String barcode = '',
    int? warehouseId,
  }) async {
    final response = await _apiClient.dio.put(
      '/api/v1/stock-count/sessions/$countNo/lines',
      data: {
        'locationcode': locationcode,
        'itemcode': itemcode,
        'counted_qty': countedQty,
        'system_qty': systemQty,
        'uom': uom,
        'barcode': barcode,
        'warehouse_id': warehouseId,
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = Map<String, dynamic>.from(root['data'] as Map);
    return StockCountLine.fromJson(data);
  }

  Future<void> deleteLineByItem({
    required int locationcode,
    required int countNo,
    required String itemcode,
  }) async {
    await _apiClient.dio.delete(
      '/api/v1/stock-count/sessions/$countNo/lines',
      queryParameters: {
        'locationcode': locationcode,
        'itemcode': itemcode,
      },
    );
  }

  Future<StockCountSession> claimSession({
    required int locationcode,
    required int countNo,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/stock-count/sessions/$countNo/claim',
      data: {'locationcode': locationcode},
    );
    return _sessionFromResponse(response.data as Map<String, dynamic>);
  }

  Future<StockCountSession> postSession({
    required int locationcode,
    required int countNo,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/stock-count/sessions/$countNo/post',
      data: {'locationcode': locationcode},
    );
    return _sessionFromResponse(response.data as Map<String, dynamic>);
  }

  StockCountSession _sessionFromResponse(Map<String, dynamic> root) {
    final data = Map<String, dynamic>.from(root['data'] as Map);
    return StockCountSession.fromJson(data);
  }
}
