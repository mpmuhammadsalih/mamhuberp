import 'dart:async';

import '../core/storage/app_config_storage.dart';
import '../core/storage/last_nav_storage.dart';
import '../core/storage/login_credentials_storage.dart';
import '../core/storage/save_nonce_storage.dart';
import '../core/storage/token_storage.dart';
import '../core/storage/transaction_draft_storage.dart';
import '../core/storage/user_session_storage.dart';
import '../models/tenant_option.dart';
import '../models/user_model.dart';
import '../services/auth_service.dart';
import '../services/grn_resume_storage.dart';

class AuthRepository {
  AuthRepository(this._service, this._tokenStorage);

  final AuthService _service;
  final TokenStorage _tokenStorage;

  Future<UserModel> login(String username, String password) async {
    final preferredTenant = await AppConfigStorage.readDefaultTenantId();
    final (access, refresh, user) = await _service.login(
      username: username,
      password: password,
      tenantId: preferredTenant,
    );
    await _tokenStorage.saveTokens(access, refresh);
    await UserSessionStorage.save(user);
    return user;
  }

  Future<void> logout() async {
    try {
      // Don't block returning to Login if the API is slow/unreachable.
      await _service.logout().timeout(const Duration(seconds: 4));
    } catch (_) {
      // Local clear below is enough.
    } finally {
      await _clearAllSessionData();
    }
  }

  Future<void> clearLocalSession() async {
    await _clearAllSessionData();
  }

  /// Tokens, user, nonce, last screen, in-progress GRN / drafts — only called on logout / expired session.
  Future<void> _clearAllSessionData() async {
    await _tokenStorage.clear();
    await SaveNonceStorage.clear();
    await UserSessionStorage.clear();
    await LastNavStorage.clear();
    await GrnResumeStorage.clear();
    await TransactionDraftStorage.clearAll();
  }

  Future<bool> hasToken() async {
    final access = await _tokenStorage.getAccessToken();
    if (access != null && access.isNotEmpty) return true;
    final refresh = await _tokenStorage.getRefreshToken();
    return refresh != null && refresh.isNotEmpty;
  }

  /// Restore user from SharedPreferences when tokens are still present.
  Future<UserModel?> restoreSession() async {
    if (!await hasToken()) {
      await UserSessionStorage.clear();
      return null;
    }
    final user = await UserSessionStorage.read();
    if (user == null) {
      await _clearAllSessionData();
      return null;
    }
    return user;
  }

  Future<void> persistUser(UserModel user) async {
    await UserSessionStorage.save(user);
  }

  Future<(List<TenantOption>, bool, String?)> getTenantOptions() async {
    return _service.getTenantOptions();
  }

  Future<String> switchTenant(String tenantId) async {
    final (access, refresh, newTenantId) = await _service.switchTenant(tenantId);
    await _tokenStorage.saveTokens(access, refresh);
    return newTenantId;
  }

  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
    required String confirmPassword,
  }) async {
    await _service.changePassword(
      oldPassword: oldPassword,
      newPassword: newPassword,
      confirmPassword: confirmPassword,
    );
    final saved = await LoginCredentialsStorage.read();
    if (saved.rememberMe && saved.username.isNotEmpty) {
      await LoginCredentialsStorage.save(
        username: saved.username,
        password: newPassword,
        rememberMe: true,
      );
    }
  }
}

