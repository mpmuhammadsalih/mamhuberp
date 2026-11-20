import 'package:shared_preferences/shared_preferences.dart';

/// Persists the last shell menu destination (e.g. Sales Order, Sales, Sales Return).
class LastNavStorage {
  LastNavStorage._();

  static const _menuKey = 'last_menu_nav';

  static Future<String?> readMenu() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(_menuKey)?.trim() ?? '';
    return value.isEmpty ? null : value;
  }

  static Future<void> saveMenu(String menuLabel) async {
    final trimmed = menuLabel.trim();
    if (trimmed.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_menuKey, trimmed);
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_menuKey);
  }
}
