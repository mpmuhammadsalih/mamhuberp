import 'package:dio/dio.dart';

import '../core/network/api_client.dart';
import '../core/storage/save_nonce_storage.dart';
import '../models/tenant_option.dart';
import '../models/user_model.dart';

class AuthService {
  AuthService(this._apiClient);

  final ApiClient _apiClient;

  Future<(String, String, UserModel)> login({
    required String username,
    required String password,
    String? tenantId,
  }) async {
    final payload = <String, dynamic>{
      'username': username,
      'password': password,
    };
    final tid = tenantId?.trim();
    if (tid != null && tid.isNotEmpty) {
      payload['tenant_id'] = tid;
    }
    final response = await _apiClient.dio.post(
      '/api/v1/auth/login',
      data: payload,
    );
    final raw = response.data;
    if (raw is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Invalid login response (expected JSON). Check API base URL.',
      );
    }
    final root = Map<String, dynamic>.from(raw);
    if (root['success'] != true) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: (root['message'] ?? 'Login failed').toString(),
      );
    }
    final dataRaw = root['data'];
    if (dataRaw is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Login response missing data. Check server matches this app.',
      );
    }
    final data = Map<String, dynamic>.from(dataRaw);
    final accessRaw = data['access_token'];
    final refreshRaw = data['refresh_token'];
    if (accessRaw is! String || refreshRaw is! String) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Login response missing tokens.',
      );
    }
    final userRaw = data['user'];
    if (userRaw is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Login response missing user.',
      );
    }
    final userMap = Map<String, dynamic>.from(userRaw);
    userMap['permissions'] = data['permissions'];
    userMap['mobile_menus'] = data['mobile_menus'];
    userMap['allow_all_permissions'] = data['allow_all_permissions'];
    final user = UserModel.fromJson(userMap);
    final saveNonce = data['save_nonce'];
    if (saveNonce is String && saveNonce.isNotEmpty) {
      await SaveNonceStorage.save(saveNonce);
    }
    return (accessRaw, refreshRaw, user);
  }

  Future<void> logout() async {
    try {
      await _apiClient.dio.post('/api/v1/auth/logout');
    } on DioException {
      // Local token clear is enough if backend logout is unavailable.
    }
  }

  Future<(List<TenantOption>, bool, String?)> getTenantOptions() async {
    final response = await _apiClient.dio.get('/api/v1/tenant/list');
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final canSwitch = data['can_switch'] == true;
    final ct = data['current_tenant_id'];
    final currentTenant =
        ct == null ? null : (ct is String ? ct : ct.toString());
    final tenants = ((data['tenants'] ?? []) as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .map(TenantOption.fromJson)
        .toList();
    return (tenants, canSwitch, currentTenant);
  }

  Future<(String, String, String)> switchTenant(String tenantId) async {
    final response = await _apiClient.dio.post(
      '/api/v1/tenant/switch',
      data: {'tenant_id': tenantId},
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final accessToken = data['access_token'] as String;
    final refreshToken = data['refresh_token'] as String;
    final rawTenant = data['tenant_id'];
    final newTenantId =
        rawTenant == null ? '' : (rawTenant is String ? rawTenant : rawTenant.toString());
    final saveNonce = data['save_nonce'];
    if (saveNonce is String && saveNonce.isNotEmpty) {
      await SaveNonceStorage.save(saveNonce);
    }
    return (accessToken, refreshToken, newTenantId);
  }

  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
    required String confirmPassword,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/auth/change-password',
      data: {
        'old_password': oldPassword,
        'new_password': newPassword,
        'confirm_password': confirmPassword,
      },
    );
    final raw = response.data;
    if (raw is! Map) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: 'Invalid change-password response.',
      );
    }
    final root = Map<String, dynamic>.from(raw);
    if (root['success'] != true) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        type: DioExceptionType.badResponse,
        message: (root['message'] ?? 'Password change failed').toString(),
      );
    }
  }
}

