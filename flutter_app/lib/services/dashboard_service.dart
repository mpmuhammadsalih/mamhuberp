import '../core/network/api_client.dart';
import '../models/dashboard_summary.dart';

class DashboardKpiDetail {
  DashboardKpiDetail({
    required this.kpiId,
    required this.title,
    required this.description,
    required this.value,
    required this.asOf,
    required this.branchName,
    required this.rowKind,
    required this.rows,
    required this.related,
    this.periodLabel = '',
    this.dateFrom = '',
    this.dateTo = '',
    this.rowCount = 0,
  });

  final String kpiId;
  final String title;
  final String description;
  final dynamic value;
  final String asOf;
  final String branchName;
  final String rowKind;
  final List<Map<String, dynamic>> rows;
  final Map<String, dynamic> related;
  final String periodLabel;
  final String dateFrom;
  final String dateTo;
  final int rowCount;

  factory DashboardKpiDetail.fromJson(Map<String, dynamic> json) => DashboardKpiDetail(
        kpiId: '${json['kpi_id'] ?? ''}'.trim(),
        title: '${json['title'] ?? ''}'.trim(),
        description: '${json['description'] ?? ''}'.trim(),
        value: json['value'],
        asOf: '${json['as_of'] ?? ''}'.trim(),
        branchName: '${json['branch_name'] ?? ''}'.trim(),
        rowKind: '${json['row_kind'] ?? 'none'}'.trim(),
        periodLabel: '${json['period_label'] ?? ''}'.trim(),
        dateFrom: '${json['date_from'] ?? ''}'.trim(),
        dateTo: '${json['date_to'] ?? ''}'.trim(),
        rowCount: () {
          final v = json['row_count'];
          if (v is int) return v;
          if (v is num) return v.toInt();
          return int.tryParse('$v') ?? 0;
        }(),
        rows: (json['rows'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList(),
        related: json['related'] is Map
            ? Map<String, dynamic>.from(json['related'] as Map)
            : const {},
      );
}

class DashboardService {
  DashboardService(this._apiClient);

  final ApiClient _apiClient;

  Future<DashboardSummary> getSummary({String? dateFrom, String? dateTo}) async {
    final params = <String, dynamic>{};
    final df = (dateFrom ?? '').trim();
    final dt = (dateTo ?? '').trim();
    if (df.isNotEmpty) params['date_from'] = df;
    if (dt.isNotEmpty) params['date_to'] = dt;
    final response = await _apiClient.dio.get(
      '/api/v1/dashboard/summary',
      queryParameters: params.isEmpty ? null : params,
    );
    final root = response.data as Map<String, dynamic>;
    return DashboardSummary.fromJson(root['data'] as Map<String, dynamic>);
  }

  Future<DashboardKpiDetail> getKpiDetail(
    String kpiId, {
    int limit = 40,
    String? dateFrom,
    String? dateTo,
  }) async {
    final encoded = Uri.encodeComponent(kpiId.trim());
    final params = <String, dynamic>{'limit': limit};
    final df = (dateFrom ?? '').trim();
    final dt = (dateTo ?? '').trim();
    if (df.isNotEmpty) params['date_from'] = df;
    if (dt.isNotEmpty) params['date_to'] = dt;
    final response = await _apiClient.dio.get(
      '/api/v1/dashboard/kpi/$encoded',
      queryParameters: params,
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'];
    if (data is! Map) {
      throw Exception('Invalid KPI detail response.');
    }
    return DashboardKpiDetail.fromJson(Map<String, dynamic>.from(data));
  }
}
