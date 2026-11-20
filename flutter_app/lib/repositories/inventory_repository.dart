import '../core/storage/local_cache.dart';
import '../models/inventory_item.dart';
import '../services/inventory_service.dart';

/// Normalizes numeric item-code searches (leading zeros, e.g. 00123 → 123).
String normalizeInventorySearch(String raw) {
  final s = raw.trim();
  if (s.isEmpty) return s;
  if (RegExp(r'^\d+\.0+$').hasMatch(s)) {
    return s.split('.').first.replaceFirst(RegExp(r'^0+(?=\d)'), '').isEmpty
        ? '0'
        : s.split('.').first.replaceFirst(RegExp(r'^0+(?=\d)'), '');
  }
  if (RegExp(r'^\d+$').hasMatch(s)) {
    final stripped = s.replaceFirst(RegExp(r'^0+(?=\d)'), '');
    return stripped.isEmpty ? '0' : stripped;
  }
  return s;
}

class InventoryRepository {
  InventoryRepository(this._service, this._cache);

  final InventoryService _service;
  final LocalCache _cache;

  Future<List<InventoryItem>> getInventory({
    int page = 1,
    int pageSize = 20,
    String search = '',
    int? warehouseId,
    int? locationcode,
    bool includeZero = true,
  }) async {
    final q = normalizeInventorySearch(search);
    final wh = warehouseId ?? 0;
    final loc = locationcode ?? 0;
    final key = 'inventory_${page}_${pageSize}_${wh}_${loc}_${includeZero}_${q.hashCode.abs()}';
    try {
      final rows = await _service.getInventory(
        page: page,
        pageSize: pageSize,
        search: q,
        warehouseId: warehouseId,
        locationcode: locationcode,
        includeZero: includeZero,
      );
      await _cache.saveJson(
        key,
        rows
            .map((e) => {
                  'itemcode': e.itemCode,
                  'itemname': e.itemName,
                  'unit': e.unit,
                  'qty_on_hand': e.qtyOnHand,
                })
            .toList(),
      );
      return rows;
    } catch (_) {
      final cached = await _cache.getJsonList(key);
      if (cached == null) rethrow;
      return cached
          .cast<Map<String, dynamic>>()
          .map(InventoryItem.fromJson)
          .toList();
    }
  }
}

