import 'package:shared_preferences/shared_preferences.dart';

/// Saved mobile app connection preferences (API URL is in [ApiEndpointStorage]).
class AppConfigStorage {
  static const _tenantKey = 'default_tenant_id';
  static const _setupKeyKey = 'config_setup_key';

  static Future<String?> readDefaultTenantId() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_tenantKey)?.trim();
    if (v == null || v.isEmpty) return null;
    return v;
  }

  static Future<String?> readSetupKey() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_setupKeyKey)?.trim();
    if (v == null || v.isEmpty) return null;
    return v;
  }

  static Future<void> saveSetupKey(String? key) async {
    final prefs = await SharedPreferences.getInstance();
    final v = key?.trim() ?? '';
    if (v.isEmpty) {
      await prefs.remove(_setupKeyKey);
    } else {
      await prefs.setString(_setupKeyKey, v);
    }
  }

  static Future<void> saveDefaultTenantId(String? tenantId) async {
    final prefs = await SharedPreferences.getInstance();
    final v = tenantId?.trim() ?? '';
    if (v.isEmpty) {
      await prefs.remove(_tenantKey);
    } else {
      await prefs.setString(_tenantKey, v);
    }
  }
}
