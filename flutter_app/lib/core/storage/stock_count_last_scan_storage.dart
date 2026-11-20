import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Last barcode scan on stock count, scoped to logged-in user + tenant.
class StockCountLastScanRecord {
  const StockCountLastScanRecord({
    required this.itemCode,
    required this.itemName,
    required this.unit,
    required this.qtyOnHand,
    required this.barcode,
    required this.scannedBarcode,
    required this.addedQty,
    required this.totalCounted,
    this.scannedAtMs,
  });

  final String itemCode;
  final String itemName;
  final String unit;
  final double qtyOnHand;
  final String barcode;
  final String scannedBarcode;
  final double addedQty;
  final double totalCounted;
  final int? scannedAtMs;

  Map<String, dynamic> toJson() => {
        'item_code': itemCode,
        'item_name': itemName,
        'unit': unit,
        'qty_on_hand': qtyOnHand,
        'barcode': barcode,
        'scanned_barcode': scannedBarcode,
        'added_qty': addedQty,
        'total_counted': totalCounted,
        'scanned_at_ms': scannedAtMs ?? DateTime.now().millisecondsSinceEpoch,
      };

  factory StockCountLastScanRecord.fromJson(Map<String, dynamic> json) => StockCountLastScanRecord(
        itemCode: '${json['item_code'] ?? ''}'.trim(),
        itemName: '${json['item_name'] ?? ''}'.trim(),
        unit: '${json['unit'] ?? ''}'.trim(),
        qtyOnHand: _num(json['qty_on_hand']),
        barcode: '${json['barcode'] ?? ''}'.trim(),
        scannedBarcode: '${json['scanned_barcode'] ?? ''}'.trim(),
        addedQty: _num(json['added_qty']),
        totalCounted: _num(json['total_counted']),
        scannedAtMs: json['scanned_at_ms'] is int ? json['scanned_at_ms'] as int : null,
      );

  static double _num(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse('$v') ?? 0;
  }
}

class StockCountLastScanStorage {
  StockCountLastScanStorage._();

  static const _prefix = 'nexa.stock_count.last_scan';

  static String _key(String tenantId, String username) {
    final tenant = tenantId.trim().isEmpty ? 'default' : tenantId.trim();
    final user = username.trim().isEmpty ? 'anonymous' : username.trim();
    return '$_prefix.$tenant.$user';
  }

  static Future<StockCountLastScanRecord?> read({
    required String tenantId,
    required String username,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key(tenantId, username));
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      final record = StockCountLastScanRecord.fromJson(decoded);
      if (record.itemCode.isEmpty) return null;
      return record;
    } catch (_) {
      return null;
    }
  }

  static Future<void> save({
    required String tenantId,
    required String username,
    required StockCountLastScanRecord record,
  }) async {
    if (record.itemCode.trim().isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key(tenantId, username), jsonEncode(record.toJson()));
  }

  static Future<void> clear({
    required String tenantId,
    required String username,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key(tenantId, username));
  }
}
