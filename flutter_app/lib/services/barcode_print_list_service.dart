import '../core/network/api_client.dart';
import '../models/barcode_print_list.dart';

class BarcodePrintListService {
  BarcodePrintListService(this._apiClient);

  final ApiClient _apiClient;

  Future<List<BarcodePrintListSummary>> listDocuments({
    String listType = 'PRODUCT',
    int limit = 50,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/barcode-print-lists',
      queryParameters: {
        if (listType.trim().isNotEmpty) 'list_type': listType.trim().toUpperCase(),
        'limit': limit,
      },
    );
    final root = response.data as Map<String, dynamic>;
    if (root['success'] == false) {
      throw Exception('${root['message'] ?? 'Failed to load print lists'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    final rows = (data['rows'] as List<dynamic>? ?? [])
        .whereType<Map>()
        .map((e) => BarcodePrintListSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return rows;
  }

  Future<BarcodePrintListDocument> getDocument(int printNo) async {
    final response = await _apiClient.dio.get('/api/v1/barcode-print-lists/$printNo');
    final root = response.data as Map<String, dynamic>;
    if (root['success'] != true) {
      throw Exception('${root['message'] ?? 'Print list not found'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    final doc = data['document'];
    if (doc is! Map) {
      throw Exception('Print list not found');
    }
    return BarcodePrintListDocument.fromJson(Map<String, dynamic>.from(doc));
  }

  Future<BarcodePrintListDocument> saveDocument({
    int? printNo,
    required String listType,
    String remarks = '',
    required List<BarcodePrintListLine> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/barcode-print-lists',
      data: {
        if (printNo != null && printNo > 0) 'print_no': printNo,
        'list_type': listType.toUpperCase(),
        'status': 'READY',
        'remarks': remarks,
        'source': 'MOBILE',
        'lines': lines.map((e) => e.toJson()).toList(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    if (root['success'] != true) {
      throw Exception('${root['message'] ?? 'Failed to save print list'}');
    }
    final data = root['data'] as Map<String, dynamic>? ?? {};
    final doc = data['document'];
    if (doc is! Map) {
      throw Exception('Save succeeded but document missing in response');
    }
    return BarcodePrintListDocument.fromJson(Map<String, dynamic>.from(doc));
  }
}
