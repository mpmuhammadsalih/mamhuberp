import '../core/network/api_client.dart';
import '../models/inventory_item.dart';
import '../models/label_scan_result.dart';
import '../models/storage_location.dart';

class InventoryService {
  InventoryService(this._apiClient);

  final ApiClient _apiClient;

  Future<List<InventoryItem>> getInventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    int? warehouseId,
    int? locationcode,
    bool includeZero = true,
  }) async {
    final Map<String, dynamic> q = {
      'page': page,
      'page_size': pageSize,
      'include_zero': includeZero,
    };
    final s = search.trim();
    if (s.isNotEmpty) q['search'] = s;
    if (warehouseId != null && warehouseId > 0) q['warehouse_id'] = warehouseId;
    if (locationcode != null && locationcode > 0) q['locationcode'] = locationcode;

    final response = await _apiClient.dio.get(
      '/api/v1/inventory',
      queryParameters: q,
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map(InventoryItem.fromJson).toList();
  }

  /// POS-style barcode lookup (MANUFACTURERID + alternate UOM barcodes).
  Future<InventoryItem> lookupItem({
    required String query,
    int? locationcode,
  }) async {
    final Map<String, dynamic> q = {'query': query.trim()};
    if (locationcode != null && locationcode > 0) {
      q['locationcode'] = locationcode;
    }
    final response = await _apiClient.dio.get(
      '/api/v1/inventory/lookup',
      queryParameters: q,
    );
    final root = response.data as Map<String, dynamic>;
    if (root['success'] != true) {
      throw Exception('${root['message'] ?? 'Item not found'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    final item = data['item'];
    if (item is! Map) {
      throw Exception('Item not found');
    }
    return InventoryItem.fromJson(Map<String, dynamic>.from(item));
  }

  /// Shelf / bin / rack lookup by STORAGE_BARCODE or CODE.
  Future<StorageLocation> lookupStorage({
    required String query,
    int? locationcode,
  }) async {
    final Map<String, dynamic> q = {'query': query.trim()};
    if (locationcode != null && locationcode > 0) {
      q['locationcode'] = locationcode;
    }
    final response = await _apiClient.dio.get(
      '/api/v1/inventory/storage-lookup',
      queryParameters: q,
    );
    final root = response.data as Map<String, dynamic>;
    if (root['success'] != true) {
      throw Exception('${root['message'] ?? 'Shelf / bin not found'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    final storage = data['storage'];
    if (storage is! Map) {
      throw Exception('Shelf / bin not found');
    }
    return StorageLocation.fromJson(Map<String, dynamic>.from(storage));
  }

  Future<bool> isLabelAiAvailable() async {
    try {
      final response = await _apiClient.dio.get('/api/v1/inventory/label-scan/status');
      final root = response.data as Map<String, dynamic>;
      if (root['success'] != true) return false;
      final data = root['data'] as Map<String, dynamic>? ?? {};
      return data['openai_configured'] == true;
    } catch (_) {
      return false;
    }
  }

  /// AI reads printed barcode text from a label photo (ERP OpenAI key).
  Future<LabelScanResult> labelScan({
    required String imageBase64,
    int? locationcode,
    String mime = 'image/jpeg',
  }) async {
    final payload = <String, dynamic>{
      'image_base64': imageBase64,
      'mime': mime,
    };
    if (locationcode != null && locationcode > 0) {
      payload['locationcode'] = locationcode;
    }
    final response = await _apiClient.dio.post(
      '/api/v1/inventory/label-scan',
      data: payload,
    );
    final root = response.data as Map<String, dynamic>;
    if (root['success'] != true) {
      throw Exception('${root['message'] ?? 'Label scan failed'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    return LabelScanResult.fromJson(data);
  }

  Future<List<ItemStoreStock>> getItemStoreStock(int itemCode) async {
    final response = await _apiClient.dio.get('/api/v1/inventory/$itemCode/stores');
    final root = response.data as Map<String, dynamic>;
    if (root['success'] == false) {
      throw Exception('${root['message'] ?? 'Request failed'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    return ((data['stores'] ?? []) as List<dynamic>)
        .whereType<Map>()
        .map((e) => ItemStoreStock.fromJson(Map<String, dynamic>.from(e)))
        .where((s) => s.store.isNotEmpty)
        .toList();
  }
}

