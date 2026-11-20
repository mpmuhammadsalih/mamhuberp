import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../core/network/api_client.dart';

String _str(dynamic v) => '${v ?? ''}'.trim();

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
}

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is int) return v;
  if (v is num) return v.round();
  return int.tryParse('$v'.trim()) ?? 0;
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class ItemLookupOption {
  ItemLookupOption({required this.code, required this.name, this.parentId = ''});

  final String code;
  final String name;
  final String parentId;

  String get label => name.isNotEmpty ? '$code — $name' : code;

  factory ItemLookupOption.fromJson(Map<String, dynamic> json) => ItemLookupOption(
        code: _str(json['code']),
        name: _str(json['name']),
        parentId: _str(json['parent_id'] ?? json['id']),
      );
}

class ItemAltUom {
  ItemAltUom({
    required this.uomCode,
    required this.conversionFactor,
    required this.barcode,
    required this.retailPrice,
    this.costPrice = 0,
    this.slno = '',
  });

  final String uomCode;
  final double conversionFactor;
  final String barcode;
  final double retailPrice;
  final double costPrice;
  final String slno;

  factory ItemAltUom.fromJson(Map<String, dynamic> json) => ItemAltUom(
        uomCode: _str(json['alternate_uom_code'] ?? json['uom']),
        conversionFactor: _num(json['conversion_factor'] ?? json['factor']),
        barcode: _str(json['manufacturer_id'] ?? json['barcode']),
        retailPrice: _num(json['retail_price'] ?? json['retailprice']),
        costPrice: _num(json['cost_price'] ?? json['costprice']),
        slno: _str(json['slno']),
      );
}

class ItemMasterRow {
  ItemMasterRow({
    required this.itemCode,
    required this.itemName,
    required this.barcode,
    required this.baseUom,
    required this.costPrice,
    this.averageCost = 0,
    required this.retailPrice,
    required this.currentStock,
    this.categoryName = '',
    this.brandName = '',
    this.supplierName = '',
  });

  final int itemCode;
  final String itemName;
  final String barcode;
  final String baseUom;
  final double costPrice;
  final double averageCost;
  final double retailPrice;
  final double currentStock;
  final String categoryName;
  final String brandName;
  final String supplierName;

  factory ItemMasterRow.fromJson(Map<String, dynamic> json) {
    final cost = _num(json['cost_price'] ?? json['costprice']);
    final avg = _num(json['average_cost'] ?? json['averagecost']);
    return ItemMasterRow(
      itemCode: _int(json['item_code'] ?? json['itemcode']),
      itemName: _str(json['item_name'] ?? json['itemname']),
      barcode: _str(json['barcode'] ?? json['manufacturer_id']),
      baseUom: _str(json['base_uom'] ?? json['baseuom']),
      costPrice: cost,
      averageCost: avg > 0 ? avg : cost,
      retailPrice: _num(json['retail_price'] ?? json['retailprice']),
      currentStock: _num(json['current_stock'] ?? json['currentstock']),
      categoryName: _str(json['category_name'] ?? json['categoryname']),
      brandName: _str(json['brand_name'] ?? json['brandname']),
      supplierName: _str(json['supplier_name'] ?? json['suppliername']),
    );
  }
}

class ItemDetail {
  ItemDetail({
    required this.itemCode,
    required this.itemName,
    required this.barcode,
    required this.baseUom,
    required this.categoryCode,
    required this.brandCode,
    required this.mainCategory,
    required this.departmentCode,
    required this.supCode,
    required this.costPrice,
    required this.retailPrice,
    required this.vatPercent,
    required this.currentStock,
    required this.categoryName,
    required this.brandName,
    required this.mainCategoryName,
    required this.departmentName,
    required this.salesAccount,
    required this.purchaseAccount,
    required this.inventoryAccount,
    required this.cogsAccount,
    required this.alternateUoms,
    this.supplierName = '',
    this.averageCost = 0,
    this.hasImage = false,
    this.imageUrl = '',
  });

  final int itemCode;
  final String itemName;
  final String barcode;
  final String baseUom;
  final int categoryCode;
  final int brandCode;
  final int mainCategory;
  final int departmentCode;
  final int supCode;
  final String supplierName;
  final double costPrice;
  final double averageCost;
  final double retailPrice;
  final double vatPercent;
  final double currentStock;
  final String categoryName;
  final String brandName;
  final String mainCategoryName;
  final String departmentName;
  final String salesAccount;
  final String purchaseAccount;
  final String inventoryAccount;
  final String cogsAccount;
  final List<ItemAltUom> alternateUoms;
  final bool hasImage;
  final String imageUrl;

  factory ItemDetail.fromJson(Map<String, dynamic> json) {
    final cost = _num(json['cost_price'] ?? json['costprice']);
    final avg = _num(json['average_cost'] ?? json['averagecost']);
    return ItemDetail(
      itemCode: _int(json['item_code'] ?? json['itemcode']),
      itemName: _str(json['item_name'] ?? json['itemname']),
      barcode: _str(json['barcode'] ?? json['manufacturer_id']),
      baseUom: _str(json['base_uom'] ?? json['baseuom']),
      categoryCode: _int(json['category_code'] ?? json['categorycode']),
      brandCode: _int(json['brand_code'] ?? json['brandcode']),
      mainCategory: _int(json['main_category'] ?? json['maincategory']),
      departmentCode: _int(json['department_code'] ?? json['departmentcode']),
      supCode: _int(json['sup_code'] ?? json['supplier_code']),
      supplierName: _str(json['supplier_name'] ?? json['suppliername']),
      costPrice: cost,
      averageCost: avg > 0 ? avg : cost,
      retailPrice: _num(json['retail_price'] ?? json['retailprice']),
      vatPercent: _num(json['vat_percent'] ?? json['vatpercent']),
      currentStock: _num(json['current_stock'] ?? json['currentstock']),
      categoryName: _str(json['category_name']),
      brandName: _str(json['brand_name']),
      mainCategoryName: _str(json['main_category_name']),
      departmentName: _str(json['department_name']),
      salesAccount: _str(json['sales_account']),
      purchaseAccount: _str(json['purchase_account']),
      inventoryAccount: _str(json['inventory_account']),
      cogsAccount: _str(json['cogs_account']),
      alternateUoms: (json['alternate_uoms'] as List<dynamic>? ?? const [])
          .whereType<Map>()
          .map((e) => ItemAltUom.fromJson(Map<String, dynamic>.from(e)))
          .where((e) => e.uomCode.isNotEmpty)
          .toList(),
      hasImage: json['has_image'] == true ||
          json['has_image'] == 1 ||
          _str(json['image_path']).isNotEmpty,
      imageUrl: _str(json['image_url']).isNotEmpty
          ? _str(json['image_url'])
          : '/api/v1/item/masters/${_int(json['item_code'] ?? json['itemcode'])}/image',
    );
  }
}

class ItemOpenContext {
  ItemOpenContext({
    required this.nextItemCode,
    required this.suggestedBarcode,
    required this.uoms,
    required this.categories,
    required this.brands,
    required this.mainCategories,
    required this.departments,
    required this.suppliers,
    required this.salesAccount,
    required this.purchaseAccount,
    required this.inventoryAccount,
    required this.cogsAccount,
  });

  final int nextItemCode;
  final String suggestedBarcode;
  final List<ItemLookupOption> uoms;
  final List<ItemLookupOption> categories;
  final List<ItemLookupOption> brands;
  final List<ItemLookupOption> mainCategories;
  final List<ItemLookupOption> departments;
  final List<ItemLookupOption> suppliers;
  final String salesAccount;
  final String purchaseAccount;
  final String inventoryAccount;
  final String cogsAccount;

  factory ItemOpenContext.fromJson(Map<String, dynamic> json) {
    List<ItemLookupOption> opts(String key) => (json[key] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => ItemLookupOption.fromJson(Map<String, dynamic>.from(e)))
        .where((e) => e.code.isNotEmpty)
        .toList();
    final defs = json['default_accounts'];
    final map = defs is Map ? Map<String, dynamic>.from(defs) : <String, dynamic>{};
    return ItemOpenContext(
      nextItemCode: _int(json['next_item_code']),
      suggestedBarcode: _str(json['suggested_barcode']),
      uoms: opts('uoms'),
      categories: opts('categories'),
      brands: opts('brands'),
      mainCategories: opts('main_categories'),
      departments: opts('departments'),
      suppliers: opts('suppliers'),
      salesAccount: _str(map['sales_account'] ?? '4100'),
      purchaseAccount: _str(map['purchase_account'] ?? '5001'),
      inventoryAccount: _str(map['inventory_account'] ?? '1300'),
      cogsAccount: _str(map['cogs_account'] ?? '5100'),
    );
  }
}

class ItemSaveResult {
  ItemSaveResult({
    required this.itemCode,
    required this.itemName,
    required this.barcode,
    required this.message,
  });

  final int itemCode;
  final String itemName;
  final String barcode;
  final String message;

  factory ItemSaveResult.fromJson(Map<String, dynamic> json) => ItemSaveResult(
        itemCode: _int(json['item_code'] ?? json['itemcode']),
        itemName: _str(json['item_name'] ?? json['itemname']),
        barcode: _str(json['barcode'] ?? json['manufacturer_id']),
        message: _str(json['message']),
      );
}

class ItemListFilters {
  const ItemListFilters({
    this.categoryCode,
    this.brandCode,
    this.supplierCode,
    this.stockFilter = '',
  });

  final String? categoryCode;
  final String? brandCode;
  final String? supplierCode;
  final String stockFilter;

  bool get hasActive =>
      (categoryCode ?? '').isNotEmpty ||
      (brandCode ?? '').isNotEmpty ||
      (supplierCode ?? '').isNotEmpty ||
      stockFilter.isNotEmpty;

  ItemListFilters copyWith({
    String? categoryCode,
    String? brandCode,
    String? supplierCode,
    String? stockFilter,
    bool clearCategory = false,
    bool clearBrand = false,
    bool clearSupplier = false,
  }) =>
      ItemListFilters(
        categoryCode: clearCategory ? null : (categoryCode ?? this.categoryCode),
        brandCode: clearBrand ? null : (brandCode ?? this.brandCode),
        supplierCode: clearSupplier ? null : (supplierCode ?? this.supplierCode),
        stockFilter: stockFilter ?? this.stockFilter,
      );
}

class ItemLedgerRow {
  ItemLedgerRow({
    required this.docNo,
    required this.docDate,
    required this.partyCode,
    required this.partyName,
    required this.qty,
    required this.uom,
    required this.rate,
    required this.bonus,
    required this.discount,
    required this.amount,
    this.foc,
  });

  final String docNo;
  final String docDate;
  final String partyCode;
  final String partyName;
  final double qty;
  final String uom;
  final double rate;
  final double bonus;
  final double discount;
  final double amount;
  final dynamic foc;

  factory ItemLedgerRow.fromJson(Map<String, dynamic> json) => ItemLedgerRow(
        docNo: _str(json['doc_no'] ?? json['docno']),
        docDate: _str(json['doc_date'] ?? json['docdate']),
        partyCode: _str(json['party_code'] ?? json['partycode']),
        partyName: _str(json['party_name'] ?? json['partyname']),
        qty: _num(json['qty'] ?? json['quantity']),
        uom: _str(json['uom']),
        rate: _num(json['rate']),
        bonus: _num(json['bonus']),
        discount: _num(json['discount']),
        amount: _num(json['amount']),
        foc: json['foc'],
      );
}

class ItemLedgerPayload {
  ItemLedgerPayload({
    required this.tab,
    required this.itemCode,
    required this.itemName,
    required this.barcode,
    required this.rows,
  });

  final String tab;
  final int itemCode;
  final String itemName;
  final String barcode;
  final List<ItemLedgerRow> rows;

  factory ItemLedgerPayload.fromJson(Map<String, dynamic> json) => ItemLedgerPayload(
        tab: _str(json['tab']),
        itemCode: _int(json['item_code']),
        itemName: _str(json['item_name']),
        barcode: _str(json['barcode']),
        rows: (json['rows'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => ItemLedgerRow.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );
}

class ItemJournalRow {
  ItemJournalRow({
    required this.stockDate,
    required this.stockTime,
    required this.transtype,
    required this.sourceDoc,
    required this.sourceNo,
    required this.qtyIn,
    required this.qtyOut,
    required this.netQty,
    required this.uom,
    required this.rate,
    required this.amount,
    required this.warehouseCode,
  });

  final String stockDate;
  final String stockTime;
  final String transtype;
  final String sourceDoc;
  final String sourceNo;
  final double qtyIn;
  final double qtyOut;
  final double netQty;
  final String uom;
  final double rate;
  final double amount;
  final String warehouseCode;

  factory ItemJournalRow.fromJson(Map<String, dynamic> json) => ItemJournalRow(
        stockDate: _str(json['stock_date'] ?? json['date']),
        stockTime: _str(json['stock_time'] ?? json['time']),
        transtype: _str(json['transtype'] ?? json['trans_type'] ?? json['type']),
        sourceDoc: _str(json['source_doc'] ?? json['sourcedoc']),
        sourceNo: _str(json['source_no'] ?? json['sourceno']),
        qtyIn: _num(json['qty_in']),
        qtyOut: _num(json['qty_out']),
        netQty: _num(json['net_qty'] ?? json['qty'] ?? json['quantity']),
        uom: _str(json['uom']),
        rate: _num(json['rate'] ?? json['costprice']),
        amount: _num(json['amount'] ?? json['line_value']),
        warehouseCode: _str(json['warehouse_code'] ?? json['warehouse'] ?? json['warehouse_name']),
      );
}

class ItemJournalPayload {
  ItemJournalPayload({
    required this.itemCode,
    required this.itemName,
    required this.barcode,
    required this.rows,
    this.dateFrom = '',
    this.dateTo = '',
  });

  final int itemCode;
  final String itemName;
  final String barcode;
  final String dateFrom;
  final String dateTo;
  final List<ItemJournalRow> rows;

  factory ItemJournalPayload.fromJson(Map<String, dynamic> json) => ItemJournalPayload(
        itemCode: _int(json['item_code']),
        itemName: _str(json['item_name']),
        barcode: _str(json['barcode']),
        dateFrom: _str(json['date_from']),
        dateTo: _str(json['date_to']),
        rows: (json['rows'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => ItemJournalRow.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );
}

class ItemMasterService {
  ItemMasterService(this._apiClient);

  final ApiClient _apiClient;

  Future<ItemOpenContext> getOpenContext() async {
    final response = await _apiClient.dio.get('/api/v1/item/masters/open');
    return ItemOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<ItemMasterRow>> listItems({
    String q = '',
    int limit = 100,
    ItemListFilters filters = const ItemListFilters(),
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/item/masters',
      queryParameters: {
        'q': q,
        'limit': limit,
        if ((filters.categoryCode ?? '').isNotEmpty) 'category_code': filters.categoryCode,
        if ((filters.brandCode ?? '').isNotEmpty) 'brand_code': filters.brandCode,
        if ((filters.supplierCode ?? '').isNotEmpty) 'supplier_code': filters.supplierCode,
        if (filters.stockFilter.isNotEmpty) 'stock_filter': filters.stockFilter,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['items'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => ItemMasterRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<ItemDetail> getItem(int itemCode) async {
    final response = await _apiClient.dio.get('/api/v1/item/masters/$itemCode');
    return ItemDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  /// ERP Item Master ledger tabs.
  Future<ItemLedgerPayload> getItemLedger({
    int? itemCode,
    String barcode = '',
    String tab = 'purchase',
    int limit = 400,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/item/ledger',
      queryParameters: {
        if (itemCode != null && itemCode > 0) 'item_code': itemCode,
        if (barcode.trim().isNotEmpty) 'barcode': barcode.trim(),
        'tab': tab,
        'limit': limit,
      },
    );
    return ItemLedgerPayload.fromJson(_data(response.data as Map<String, dynamic>));
  }

  /// ITEMJOURNAL stock movements for one item.
  Future<ItemJournalPayload> getItemJournal({
    int? itemCode,
    String barcode = '',
    String dateFrom = '',
    String dateTo = '',
    int limit = 500,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/item/journal',
      queryParameters: {
        if (itemCode != null && itemCode > 0) 'item_code': itemCode,
        if (barcode.trim().isNotEmpty) 'barcode': barcode.trim(),
        if (dateFrom.isNotEmpty) 'date_from': dateFrom,
        if (dateTo.isNotEmpty) 'date_to': dateTo,
        'limit': limit,
      },
    );
    return ItemJournalPayload.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ItemSaveResult> createItem(Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.post(
      '/api/v1/item/masters',
      data: payload,
    );
    return ItemSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ItemSaveResult> updateItem(int itemCode, Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.put(
      '/api/v1/item/masters/$itemCode',
      data: payload,
    );
    return ItemSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<ItemSaveResult> deleteItem(int itemCode, {required String password}) async {
    final response = await _apiClient.dio.post(
      '/api/v1/item/masters/$itemCode/delete',
      data: {'password': password},
    );
    return ItemSaveResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<Uint8List?> fetchItemImageBytes(int itemCode) async {
    if (itemCode <= 0) return null;
    try {
      final response = await _apiClient.dio.get<List<int>>(
        '/api/v1/item/masters/$itemCode/image',
        options: Options(responseType: ResponseType.bytes),
      );
      final bytes = response.data;
      if (bytes == null || bytes.isEmpty) return null;
      return Uint8List.fromList(bytes);
    } catch (_) {
      return null;
    }
  }
}
