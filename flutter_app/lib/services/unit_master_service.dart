import '../core/network/api_client.dart';

String _str(dynamic v) => '${v ?? ''}'.trim();

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class UnitMasterRow {
  UnitMasterRow({required this.code, required this.name});

  final String code;
  final String name;

  factory UnitMasterRow.fromJson(Map<String, dynamic> json) => UnitMasterRow(
        code: _str(json['code'] ?? json['unitcode']).toUpperCase(),
        name: _str(json['name'] ?? json['unitname']),
      );
}

class UnitMasterService {
  UnitMasterService(this._apiClient);

  final ApiClient _apiClient;

  Future<List<UnitMasterRow>> listUnits({String q = ''}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/unit-master',
      queryParameters: {if (q.isNotEmpty) 'q': q},
    );
    final data = _data(Map<String, dynamic>.from(response.data as Map? ?? const {}));
    final rows = <UnitMasterRow>[];
    final raw = data['rows'];
    if (raw is List) {
      for (final r in raw) {
        if (r is Map) {
          rows.add(UnitMasterRow.fromJson(Map<String, dynamic>.from(r)));
        }
      }
    }
    return rows;
  }

  Future<Map<String, dynamic>> createUnit({required String code, required String name}) async {
    final response = await _apiClient.dio.post(
      '/api/v1/unit-master',
      data: {'code': code.trim().toUpperCase(), 'name': name.trim()},
    );
    return _data(Map<String, dynamic>.from(response.data as Map? ?? const {}));
  }

  Future<Map<String, dynamic>> updateUnit({required String code, required String name}) async {
    final enc = Uri.encodeComponent(code.trim().toUpperCase());
    final response = await _apiClient.dio.put(
      '/api/v1/unit-master/$enc',
      data: {'name': name.trim()},
    );
    return _data(Map<String, dynamic>.from(response.data as Map? ?? const {}));
  }

  Future<Map<String, dynamic>> deleteUnit({required String code}) async {
    final enc = Uri.encodeComponent(code.trim().toUpperCase());
    final response = await _apiClient.dio.post('/api/v1/unit-master/$enc/delete');
    return _data(Map<String, dynamic>.from(response.data as Map? ?? const {}));
  }
}
