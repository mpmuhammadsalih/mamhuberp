import 'package:dio/dio.dart';

import '../core/network/api_client.dart';
import '../core/storage/app_config_storage.dart';
import '../models/app_config.dart';

class ConfigService {
  ConfigService(this._apiClient);

  final ApiClient _apiClient;

  Future<AppConfig> fetchAppConfig() async {
    final response = await _apiClient.dio.get('/api/v1/config/app');
    return _parseConfigResponse(response);
  }

  Future<void> testTenantConnection({
    required String host,
    required int port,
    required String serviceName,
    required String username,
    required String password,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/config/test-connection',
      data: {
        'host': host.trim(),
        'port': port,
        'service_name': serviceName.trim(),
        'username': username.trim(),
        'password': password,
      },
    );
    _ensureSuccess(response, fallback: 'Connection test failed');
  }

  Future<AppTenantOption> saveTenantDatabase({
    required String tenantId,
    String? displayName,
    required String host,
    required int port,
    required String serviceName,
    required String username,
    String? password,
    bool active = true,
    String? setupKey,
  }) async {
    final key = setupKey?.trim().isNotEmpty == true
        ? setupKey!.trim()
        : await AppConfigStorage.readSetupKey();
    final headers = <String, String>{};
    if (key != null && key.isNotEmpty) {
      headers['X-Config-Setup-Key'] = key;
    }
    final response = await _apiClient.dio.post(
      '/api/v1/config/tenant',
      data: {
        'tenant_id': tenantId.trim(),
        if (displayName != null && displayName.trim().isNotEmpty)
          'display_name': displayName.trim(),
        'host': host.trim(),
        'port': port,
        'service_name': serviceName.trim(),
        'username': username.trim(),
        if (password != null) 'password': password,
        'active': active,
      },
      options: Options(headers: headers),
    );
    final root = _rootMap(response);
    final data = root['data'];
    if (data is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Save tenant response missing data',
      );
    }
    return AppTenantOption.fromJson(Map<String, dynamic>.from(data));
  }

  AppConfig _parseConfigResponse(Response<dynamic> response) {
    final map = _rootMap(response);
    if (map['success'] != true) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: (map['message'] ?? 'Failed to load configuration').toString(),
      );
    }
    final data = map['data'];
    if (data is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Configuration response missing data',
      );
    }
    return AppConfig.fromJson(Map<String, dynamic>.from(data));
  }

  Map<String, dynamic> _rootMap(Response<dynamic> response) {
    final root = response.data;
    if (root is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Invalid API response',
      );
    }
    return Map<String, dynamic>.from(root);
  }

  void _ensureSuccess(Response<dynamic> response, {required String fallback}) {
    final map = _rootMap(response);
    if (map['success'] != true) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: (map['message'] ?? fallback).toString(),
      );
    }
  }
}
