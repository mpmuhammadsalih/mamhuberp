import '../../services/sales_service.dart';

/// Shared serialize/deserialize helpers for sales order / invoice / return drafts.
class SalesTransactionDraft {
  SalesTransactionDraft._();

  static Map<String, dynamic> encodeCustomer(SalesCustomerOption? c) {
    if (c == null) return {};
    return {
      'code': c.code,
      'name': c.name,
      'address': c.address,
      'phone': c.phone,
      'billing_type': c.billingType,
      'credit_limit': c.creditLimit,
      'current_credit': c.currentCredit,
      'outstanding': c.outstanding,
      'category_name': c.categoryName,
    };
  }

  static SalesCustomerOption? decodeCustomer(Object? raw) {
    if (raw is! Map) return null;
    final m = Map<String, dynamic>.from(raw);
    final code = '${m['code'] ?? ''}'.trim();
    if (code.isEmpty) return null;
    return SalesCustomerOption.fromJson(m);
  }

  static Map<String, dynamic> encodeWarehouse(SalesWarehouseOption? w) {
    if (w == null) return {};
    return {
      'warehouse_id': w.warehouseId,
      'warehouse_code': w.warehouseCode,
      'warehouse_name': w.warehouseName,
      'label': w.label,
    };
  }

  static SalesWarehouseOption? decodeWarehouse(Object? raw) {
    if (raw is! Map) return null;
    final m = Map<String, dynamic>.from(raw);
    if ('${m['warehouse_id'] ?? ''}'.trim().isEmpty &&
        '${m['warehouse_code'] ?? ''}'.trim().isEmpty) {
      return null;
    }
    return SalesWarehouseOption.fromJson(m);
  }

  static Map<String, dynamic> encodeUom(SalesUomOption u) => {
        'code': u.code,
        'name': u.name,
        'is_base': u.isBase,
        'conversion_factor': u.conversionFactor,
      };

  static SalesUomOption decodeUom(Map<String, dynamic> m) => SalesUomOption.fromJson(m);

  static Map<String, dynamic> encodeLine({
    required int slno,
    required String itemCode,
    required String itemName,
    required String uom,
    required double qty,
    required double rate,
    required double discount,
    required double cost,
    double averageCost = 0,
    required double conversionFactor,
    required List<SalesUomOption> availableUoms,
    String? warehouseId,
    String? warehouseCode,
    int? storageId,
    String? binCode,
    String? binName,
    String? lotId,
    String? lotLabel,
    bool batchTracked = false,
  }) =>
      {
        'slno': slno,
        'item_code': itemCode,
        'item_name': itemName,
        'uom': uom,
        'qty': qty,
        'rate': rate,
        'discount': discount,
        'cost': cost,
        'average_cost': averageCost,
        'conversion_factor': conversionFactor,
        'available_uoms': availableUoms.map(encodeUom).toList(),
        'warehouse_id': warehouseId,
        'warehouse_code': warehouseCode,
        'storage_id': storageId,
        'bin_code': binCode,
        'bin_name': binName,
        'lot_id': lotId,
        'lot_label': lotLabel,
        'batch_tracked': batchTracked,
      };

  static Map<String, dynamic>? lineAt(List<dynamic> lines, int index) {
    if (index < 0 || index >= lines.length) return null;
    final raw = lines[index];
    if (raw is! Map) return null;
    return Map<String, dynamic>.from(raw);
  }

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

  static String summaryLabel(Map<String, dynamic> draft) {
    final walkIn = draft['walk_in'] == true;
    final customer = decodeCustomer(draft['customer']);
    final lines = (draft['lines'] as List?)?.length ?? 0;
    final who = walkIn
        ? 'Walk-in'
        : (customer?.name.isNotEmpty == true ? customer!.name : 'Draft');
    if (lines <= 0) return who;
    return '$who · $lines item${lines == 1 ? '' : 's'}';
  }

  /// True when the draft has enough user input to be worth keeping.
  static bool isMeaningful({
    required bool walkIn,
    required SalesCustomerOption? customer,
    required String orderNo,
    required String remarks,
    required String address,
    required List<dynamic> lines,
    Map<String, double>? paymentAmounts,
  }) {
    if (walkIn) return true;
    if (customer != null) return true;
    if (orderNo.trim().isNotEmpty) return true;
    if (remarks.trim().isNotEmpty) return true;
    if (address.trim().isNotEmpty) return true;
    if (lines.isNotEmpty) return true;
    if (paymentAmounts != null && paymentAmounts.values.any((v) => v > 0)) return true;
    return false;
  }
}
