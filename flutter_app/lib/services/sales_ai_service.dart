import '../core/network/api_client.dart';

String _str(dynamic v) => '${v ?? ''}'.trim();

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class SalesAiUomOption {
  SalesAiUomOption({
    required this.unit,
    required this.rate,
    this.isBase = false,
    this.conversionFactor = 1,
  });

  final String unit;
  final double rate;
  final bool isBase;
  final double conversionFactor;

  factory SalesAiUomOption.fromJson(Map<String, dynamic> json) => SalesAiUomOption(
        unit: _str(json['unit'] ?? json['code'] ?? json['uom']).isEmpty
            ? 'PCS'
            : _str(json['unit'] ?? json['code'] ?? json['uom']),
        rate: _num(json['rate'] ?? json['price']),
        isBase: json['is_base'] == true || json['isBase'] == true,
        conversionFactor: _num(json['conversion_factor'] ?? json['conversionFactor'] ?? 1),
      );
}

class SalesAiProduct {
  SalesAiProduct({
    required this.itemCode,
    required this.itemName,
    required this.unit,
    required this.rate,
    this.stock = 0,
    this.brand = '',
    this.barcode = '',
    this.uoms = const [],
  });

  final String itemCode;
  final String itemName;
  final String unit;
  final double rate;
  final double stock;
  final String brand;
  final String barcode;
  final List<SalesAiUomOption> uoms;

  factory SalesAiProduct.fromJson(Map<String, dynamic> json) {
    final uomsRaw = json['uoms'];
    final uoms = (uomsRaw is List ? uomsRaw : const [])
        .whereType<Map>()
        .map((e) => SalesAiUomOption.fromJson(Map<String, dynamic>.from(e)))
        .where((e) => e.unit.isNotEmpty)
        .toList();
    return SalesAiProduct(
      itemCode: _str(json['item_code'] ?? json['itemCode']),
      itemName: _str(json['item_name'] ?? json['itemName']),
      unit: _str(json['unit'] ?? json['uom']).isEmpty ? 'PCS' : _str(json['unit'] ?? json['uom']),
      rate: _num(json['rate'] ?? json['price'] ?? json['retail_price']),
      stock: _num(json['stock'] ?? json['current_stock']),
      brand: _str(json['brand']),
      barcode: _str(json['barcode']),
      uoms: uoms,
    );
  }

  Map<String, dynamic> toJson() => {
        'item_code': itemCode,
        'item_name': itemName,
        'unit': unit,
        'rate': rate,
        'stock': stock,
        'brand': brand,
        'barcode': barcode,
        'uoms': [
          for (final u in uoms)
            {
              'unit': u.unit,
              'rate': u.rate,
              'is_base': u.isBase,
              'conversion_factor': u.conversionFactor,
            },
        ],
      };
}

class SalesAiCartLine {
  SalesAiCartLine({
    required this.itemCode,
    required this.itemName,
    required this.unit,
    required this.qty,
    required this.rate,
    this.discount = 0,
    this.stock = 0,
    this.brand = '',
  });

  final String itemCode;
  final String itemName;
  final String unit;
  final double qty;
  final double rate;
  /// Discount **per unit** (same as Sales Invoice cart).
  final double discount;
  final double stock;
  final String brand;

  double get discountTotal => qty * discount;
  double get amount => (qty * rate) - discountTotal;

  SalesAiCartLine copyWith({
    double? qty,
    double? rate,
    double? discount,
  }) {
    return SalesAiCartLine(
      itemCode: itemCode,
      itemName: itemName,
      unit: unit,
      qty: qty ?? this.qty,
      rate: rate ?? this.rate,
      discount: discount ?? this.discount,
      stock: stock,
      brand: brand,
    );
  }

  factory SalesAiCartLine.fromJson(Map<String, dynamic> json) => SalesAiCartLine(
        itemCode: _str(json['item_code'] ?? json['itemCode']),
        itemName: _str(json['item_name'] ?? json['itemName']),
        unit: _str(json['unit'] ?? json['uom']).isEmpty ? 'PCS' : _str(json['unit'] ?? json['uom']),
        qty: _num(json['qty'] ?? json['quantity']),
        rate: _num(json['rate'] ?? json['price']),
        discount: _num(json['discount']),
        stock: _num(json['stock']),
        brand: _str(json['brand']),
      );

  Map<String, dynamic> toJson() => {
        'item_code': itemCode,
        'item_name': itemName,
        'unit': unit,
        'qty': qty,
        'rate': rate,
        'discount': discount,
        'amount': amount,
        'stock': stock,
        'brand': brand,
      };
}

class SalesAiChatResult {
  SalesAiChatResult({
    required this.reply,
    required this.speak,
    required this.cart,
    required this.cartTotal,
    required this.suggestions,
    this.status = const [],
  });

  final String reply;
  final String speak;
  final List<SalesAiCartLine> cart;
  final double cartTotal;
  final List<SalesAiProduct> suggestions;
  final List<String> status;

  factory SalesAiChatResult.fromJson(Map<String, dynamic> json) => SalesAiChatResult(
        reply: _str(json['reply']),
        speak: _str(json['speak']).isEmpty ? _str(json['reply']) : _str(json['speak']),
        cart: (json['cart'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => SalesAiCartLine.fromJson(Map<String, dynamic>.from(e)))
            .where((e) => e.itemCode.isNotEmpty)
            .toList(),
        cartTotal: _num(json['cart_total']),
        suggestions: (json['suggestions'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => SalesAiProduct.fromJson(Map<String, dynamic>.from(e)))
            .where((e) => e.itemCode.isNotEmpty)
            .toList(),
        status: (json['status'] as List<dynamic>? ?? const []).map((e) => _str(e)).where((e) => e.isNotEmpty).toList(),
      );
}

class SalesAiChatMessage {
  SalesAiChatMessage({required this.role, required this.content});

  final String role; // user | assistant
  final String content;

  Map<String, dynamic> toJson() => {'role': role, 'content': content};
}

class SalesAiService {
  SalesAiService(this._apiClient);

  final ApiClient _apiClient;

  Future<bool> isConfigured() async {
    final response = await _apiClient.dio.get('/api/v1/sales/ai/status');
    final data = _data(response.data as Map<String, dynamic>);
    return data['openai_configured'] == true;
  }

  Future<SalesAiChatResult> chat({
    required String message,
    required List<SalesAiChatMessage> history,
    required List<SalesAiCartLine> cart,
    String language = 'en',
    String warehouseId = '',
    String customerCode = '',
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/sales/ai/chat',
      data: {
        'message': message,
        'history': history.map((e) => e.toJson()).toList(),
        'cart': cart.map((e) => e.toJson()).toList(),
        'language': language,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (customerCode.isNotEmpty) 'customer_code': customerCode,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return SalesAiChatResult.fromJson(data);
  }
}
