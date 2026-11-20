import 'package:shared_preferences/shared_preferences.dart';

/// One-time save token from the mobile API (replay protection for POST/PUT/PATCH/DELETE).
class SaveNonceStorage {
  static const _key = 'save_nonce';

  static Future<void> save(String nonce) async {
    final trimmed = nonce.trim();
    if (trimmed.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, trimmed);
  }

  static Future<String?> read() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key);
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }

  /// Pull ``save_nonce`` from a successful API JSON body (root or nested ``data``).
  static Future<void> applyFromResponseBody(Object? raw) async {
    if (raw is! Map) return;
    final root = Map<String, dynamic>.from(raw);
    final direct = root['save_nonce'];
    if (direct is String && direct.isNotEmpty) {
      await save(direct);
      return;
    }
    final data = root['data'];
    if (data is Map) {
      final nested = data['save_nonce'];
      if (nested is String && nested.isNotEmpty) {
        await save(nested);
      }
    }
  }
}
