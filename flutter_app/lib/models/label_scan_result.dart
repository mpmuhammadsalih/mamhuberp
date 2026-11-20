import '../models/inventory_item.dart';

class LabelScanResult {
  const LabelScanResult({
    required this.barcode,
    required this.matched,
    this.item,
    this.queryUsed,
    this.queriesTried = const [],
  });

  final String barcode;
  final bool matched;
  final InventoryItem? item;
  final String? queryUsed;
  final List<String> queriesTried;

  factory LabelScanResult.fromJson(Map<String, dynamic> json) {
    final itemRaw = json['item'];
    return LabelScanResult(
      barcode: '${json['barcode'] ?? ''}'.trim(),
      matched: json['matched'] == true,
      queryUsed: json['query_used']?.toString(),
      queriesTried: ((json['queries_tried'] ?? []) as List<dynamic>)
          .map((e) => e.toString())
          .where((e) => e.isNotEmpty)
          .toList(),
      item: itemRaw is Map ? InventoryItem.fromJson(Map<String, dynamic>.from(itemRaw)) : null,
    );
  }
}
