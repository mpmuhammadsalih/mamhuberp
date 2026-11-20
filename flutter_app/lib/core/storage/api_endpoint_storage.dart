import 'package:shared_preferences/shared_preferences.dart';

/// Saved override for API base URL (scheme + host + port, no trailing path).
class ApiEndpointStorage {
  static const _key = 'api_base_url_override';

  static Future<String?> readOverride() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_key)?.trim();
    if (v == null || v.isEmpty) return null;
    return v;
  }

  static Future<void> saveOverride(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, url);
  }

  static Future<void> clearOverride() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }
}
