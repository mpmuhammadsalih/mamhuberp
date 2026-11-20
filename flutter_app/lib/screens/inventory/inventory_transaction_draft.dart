/// Shared helpers for inventory transaction draft banners / payloads.
class InventoryTransactionDraft {
  InventoryTransactionDraft._();

  static double numOf(Object? v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse('$v') ?? 0;
  }

  static int intOf(Object? v) {
    if (v == null) return 0;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('$v') ?? 0;
  }

  static Map<String, dynamic>? mapOf(Object? raw) {
    if (raw is! Map) return null;
    return Map<String, dynamic>.from(raw);
  }

  static Map<String, dynamic>? lineAt(List<dynamic> lines, int index) {
    if (index < 0 || index >= lines.length) return null;
    return mapOf(lines[index]);
  }

  static String summaryLabel(Map<String, dynamic> draft, {String fallback = 'Draft'}) {
    final party = '${draft['party_name'] ?? draft['supplier_name'] ?? ''}'.trim();
    final lines = (draft['lines'] as List?)?.length ?? 0;
    final who = party.isNotEmpty ? party : fallback;
    if (lines <= 0) return who;
    return '$who · $lines item${lines == 1 ? '' : 's'}';
  }

  static bool isMeaningful({
    String? partyCode,
    String? partyName,
    String? remarks,
    required List<dynamic> lines,
    bool other = false,
  }) {
    if (other) return true;
    if ((partyCode ?? '').trim().isNotEmpty) return true;
    if ((partyName ?? '').trim().isNotEmpty) return true;
    if ((remarks ?? '').trim().isNotEmpty) return true;
    if (lines.isNotEmpty) return true;
    return false;
  }

  static Map<String, dynamic> encodeParty({String? code, String? name}) {
    return {
      'code': (code ?? '').trim(),
      'name': (name ?? '').trim(),
    };
  }

  static Map<String, dynamic> encodeWarehouse({
    String? id,
    String? code,
    String? name,
    String? label,
  }) {
    return {
      if ((id ?? '').trim().isNotEmpty) 'id': id!.trim(),
      if ((id ?? '').trim().isNotEmpty) 'warehouse_id': id!.trim(),
      'code': (code ?? '').trim(),
      'warehouse_code': (code ?? '').trim(),
      'name': (name ?? '').trim(),
      'warehouse_name': (name ?? '').trim(),
      if ((label ?? '').trim().isNotEmpty) 'label': label!.trim(),
    };
  }

  static Map<String, dynamic> encodeStore({String? code, String? name, String? id}) {
    return {
      if ((id ?? '').trim().isNotEmpty) 'id': id!.trim(),
      'code': (code ?? '').trim(),
      'name': (name ?? '').trim(),
    };
  }

  static String? storeCodeOf(Object? raw) {
    if (raw == null) return null;
    if (raw is String) {
      final s = raw.trim();
      return s.isEmpty ? null : s;
    }
    final m = mapOf(raw);
    if (m == null) return null;
    final code = '${m['code'] ?? m['warehouse_code'] ?? ''}'.trim();
    return code.isEmpty ? null : code;
  }
}
