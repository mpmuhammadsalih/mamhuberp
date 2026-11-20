import 'package:shared_preferences/shared_preferences.dart';

/// Persists last GR / PO receipt key when the wizard is left mid-flow (`Continue PO …`).
class GrnResumeStorage {
  GrnResumeStorage._();

  static const _keyReceipt = 'nexa.grn.resume_receipt_no';

  static Future<void> remember(String receiptNoRaw) async {
    final key = receiptNoRaw.trim();
    if (key.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyReceipt, key);
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyReceipt);
  }

  static Future<String?> peek() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_keyReceipt);
    final t = v?.trim();
    return t == null || t.isEmpty ? null : t;
  }
}
