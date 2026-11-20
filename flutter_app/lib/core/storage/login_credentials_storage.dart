import 'package:shared_preferences/shared_preferences.dart';

class SavedLoginCredentials {
  const SavedLoginCredentials({
    this.username = '',
    this.password = '',
    this.rememberMe = false,
  });

  final String username;
  final String password;
  final bool rememberMe;
}

class LoginCredentialsStorage {
  LoginCredentialsStorage._();

  static const _rememberKey = 'login_remember_me';
  static const _usernameKey = 'login_username';
  static const _passwordKey = 'login_password';

  static Future<SavedLoginCredentials> read() async {
    final prefs = await SharedPreferences.getInstance();
    final remember = prefs.getBool(_rememberKey) ?? false;
    final username = prefs.getString(_usernameKey)?.trim() ?? '';
    final password = remember ? (prefs.getString(_passwordKey) ?? '') : '';
    return SavedLoginCredentials(
      username: username,
      password: password,
      rememberMe: remember,
    );
  }

  static Future<void> save({
    required String username,
    required String password,
    required bool rememberMe,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_rememberKey, rememberMe);
    await prefs.setString(_usernameKey, username.trim());
    if (rememberMe) {
      await prefs.setString(_passwordKey, password);
    } else {
      await prefs.remove(_passwordKey);
    }
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_rememberKey);
    await prefs.remove(_usernameKey);
    await prefs.remove(_passwordKey);
  }
}
