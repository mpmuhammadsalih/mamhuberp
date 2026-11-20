class InventoryItem {
  InventoryItem({
    required this.itemCode,
    required this.itemName,
    required this.unit,
    required this.qtyOnHand,
    this.barcode = '',
    this.retailPrice = 0,
  });

  final String itemCode;
  final String itemName;
  final String unit;
  final double qtyOnHand;
  final String barcode;
  final double retailPrice;

  static String _asString(dynamic value) => value == null ? '' : value.toString();

  factory InventoryItem.fromJson(Map<String, dynamic> json) => InventoryItem(
        itemCode: _asString(json['itemcode']),
        itemName: _asString(json['itemname']),
        unit: _asString(json['unit']),
        qtyOnHand: ((json['qty_on_hand'] ?? 0) as num).toDouble(),
        barcode: _asString(json['barcode']),
        retailPrice: ((json['retail_price'] ?? 0) as num).toDouble(),
      );
}

class ItemStoreStock {
  ItemStoreStock({
    required this.store,
    required this.description,
    required this.qty,
  });

  final String store;
  final String description;
  final double qty;

  factory ItemStoreStock.fromJson(Map<String, dynamic> json) => ItemStoreStock(
        store: InventoryItem._asString(json['store']),
        description: InventoryItem._asString(json['description']),
        qty: ((json['qty'] ?? 0) as num).toDouble(),
      );

  String get label => description.isNotEmpty ? '$store — $description' : store;
}

