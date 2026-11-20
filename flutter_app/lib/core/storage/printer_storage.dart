import 'package:shared_preferences/shared_preferences.dart';

class SavedPrinter {
  const SavedPrinter({required this.name, required this.address});

  final String name;
  final String address;

  bool get isEmpty => address.trim().isEmpty;

  String get label => name.trim().isNotEmpty ? name.trim() : address;

  Map<String, String> toMap() => {'name': name, 'address': address};

  factory SavedPrinter.fromMap(Map<String, String> map) => SavedPrinter(
        name: map['name'] ?? '',
        address: map['address'] ?? '',
      );
}

class PrinterStorage {
  static const _nameKey = 'selected_printer_name';
  static const _addressKey = 'selected_printer_address';

  static Future<SavedPrinter?> readSelected() async {
    final prefs = await SharedPreferences.getInstance();
    final address = prefs.getString(_addressKey)?.trim() ?? '';
    if (address.isEmpty) return null;
    return SavedPrinter(
      name: prefs.getString(_nameKey)?.trim() ?? '',
      address: address,
    );
  }

  static Future<void> saveSelected(SavedPrinter printer) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_nameKey, printer.name.trim());
    await prefs.setString(_addressKey, printer.address.trim());
  }

  static Future<void> clearSelected() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_nameKey);
    await prefs.remove(_addressKey);
  }
}
