import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Document types that can hold an in-progress transaction draft in session.
abstract final class TransactionDraftType {
  static const salesOrder = 'sales_order';
  static const salesInvoice = 'sales_invoice';
  static const salesReturn = 'sales_return';
  static const purchaseOrder = 'purchase_order';
  static const purchaseReturn = 'purchase_return';
  static const grn = 'grn';
  static const goodsReceiving = 'goods_receiving';
  static const stockTransfer = 'stock_transfer';
  static const stockAdjustment = 'stock_adjustment';
  static const cashPaymentVoucher = 'cash_payment_voucher';
  static const journalEntry = 'journal_entry';

  static const all = <String>[
    salesOrder,
    salesInvoice,
    salesReturn,
    purchaseOrder,
    purchaseReturn,
    grn,
    goodsReceiving,
    stockTransfer,
    stockAdjustment,
    cashPaymentVoucher,
    journalEntry,
  ];
}

/// Persists unfinished transaction JSON until save succeeds or user dismisses / logs out.
class TransactionDraftStorage {
  TransactionDraftStorage._();

  static const _prefix = 'nexa.txn.draft';

  static String _key(String docType, String tenantId, String username) {
    final tenant = tenantId.trim().isEmpty ? 'default' : tenantId.trim();
    final user = username.trim().isEmpty ? 'anonymous' : username.trim();
    final type = docType.trim().isEmpty ? 'unknown' : docType.trim();
    return '$_prefix.$type.$tenant.$user';
  }

  static Future<Map<String, dynamic>?> read({
    required String docType,
    required String tenantId,
    required String username,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key(docType, tenantId, username));
    if (raw == null || raw.trim().isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;
      return Map<String, dynamic>.from(decoded);
    } catch (_) {
      return null;
    }
  }

  static Future<bool> hasDraft({
    required String docType,
    required String tenantId,
    required String username,
  }) async {
    final draft = await read(docType: docType, tenantId: tenantId, username: username);
    return draft != null && draft.isNotEmpty;
  }

  static Future<void> save({
    required String docType,
    required String tenantId,
    required String username,
    required Map<String, dynamic> draft,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final payload = Map<String, dynamic>.from(draft)
      ..['saved_at_ms'] = DateTime.now().millisecondsSinceEpoch
      ..['doc_type'] = docType;
    await prefs.setString(_key(docType, tenantId, username), jsonEncode(payload));
  }

  static Future<void> clear({
    required String docType,
    required String tenantId,
    required String username,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key(docType, tenantId, username));
  }

  /// Clears every known transaction draft for this user (logout).
  static Future<void> clearAllForUser({
    required String tenantId,
    required String username,
  }) async {
    for (final type in TransactionDraftType.all) {
      await clear(docType: type, tenantId: tenantId, username: username);
    }
  }

  /// Best-effort clear of all draft keys (logout when user already cleared).
  static Future<void> clearAll() async {
    final prefs = await SharedPreferences.getInstance();
    final keys = prefs.getKeys().where((k) => k.startsWith('$_prefix.')).toList();
    for (final k in keys) {
      await prefs.remove(k);
    }
  }
}
