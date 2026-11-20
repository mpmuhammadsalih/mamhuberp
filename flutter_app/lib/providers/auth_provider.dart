import 'package:flutter/material.dart';

import '../core/network/api_error_message.dart';
import '../models/tenant_option.dart';
import '../models/user_model.dart';
import '../repositories/auth_repository.dart';

class AuthProvider extends ChangeNotifier {
  AuthProvider(this._repository);

  final AuthRepository _repository;

  bool isLoading = false;
  bool isRestoringSession = true;
  bool isTenantLoading = false;
  bool canSwitchTenant = false;
  String? error;
  UserModel? user;
  List<TenantOption> tenantOptions = [];

  bool get isAuthenticated => user != null;

  /// Reopen app with saved tokens + user until the user taps Logout.
  Future<void> restoreSession() async {
    isRestoringSession = true;
    error = null;
    notifyListeners();
    try {
      user = await _repository.restoreSession();
    } catch (_) {
      user = null;
    } finally {
      isRestoringSession = false;
      notifyListeners();
    }
  }

  Future<bool> login(String username, String password) async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      user = await _repository.login(username, password);
      return true;
    } catch (e) {
      error = 'Login failed: ${apiErrorMessage(e, authenticatedContext: false)}';
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    // Drop UI session first so Login appears even if the network logout hangs.
    user = null;
    tenantOptions = [];
    canSwitchTenant = false;
    error = null;
    notifyListeners();
    try {
      await _repository.logout();
    } catch (_) {
      // Local session already cleared; ignore remote logout failures.
    }
  }

  /// Clears local session only (no API call). Used when tokens are already invalid.
  Future<void> clearLocalSession() async {
    user = null;
    tenantOptions = [];
    canSwitchTenant = false;
    error = null;
    notifyListeners();
    try {
      await _repository.clearLocalSession();
    } catch (_) {}
  }

  Future<void> loadTenantOptions() async {
    isTenantLoading = true;
    error = null;
    notifyListeners();
    try {
      final (options, canSwitch, currentTenant) = await _repository.getTenantOptions();
      tenantOptions = options;
      canSwitchTenant = canSwitch;
      if (user != null && currentTenant != null && currentTenant.isNotEmpty) {
        user = user!.copyWith(tenantId: currentTenant);
      }
    } catch (e) {
      error = 'Unable to load tenants: ${apiErrorMessage(e, authenticatedContext: true)}';
    } finally {
      isTenantLoading = false;
      notifyListeners();
    }
  }

  Future<bool> switchTenant(String tenantId) async {
    isTenantLoading = true;
    error = null;
    notifyListeners();
    try {
      final newTenantId = await _repository.switchTenant(tenantId);
      if (user != null) {
        user = user!.copyWith(tenantId: newTenantId);
        await _repository.persistUser(user!);
      }
      return true;
    } catch (e) {
      error = 'Unable to switch tenant: ${apiErrorMessage(e, authenticatedContext: true)}';
      return false;
    } finally {
      isTenantLoading = false;
      notifyListeners();
    }
  }

  Future<bool> changePassword({
    required String oldPassword,
    required String newPassword,
    required String confirmPassword,
  }) async {
    isLoading = true;
    error = null;
    notifyListeners();
    try {
      await _repository.changePassword(
        oldPassword: oldPassword,
        newPassword: newPassword,
        confirmPassword: confirmPassword,
      );
      return true;
    } catch (e) {
      error = apiErrorMessage(e, authenticatedContext: true);
      return false;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }
}

