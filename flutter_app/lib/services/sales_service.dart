import 'package:dio/dio.dart';

import '../core/network/api_client.dart';
import '../models/sales_reports.dart';

double _num(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? 0;
}

class SalesInvoiceSummary {
  SalesInvoiceSummary({
    required this.billno,
    required this.billDate,
    required this.customerCode,
    required this.customerName,
    required this.orderNo,
    required this.netAmount,
    required this.billType,
    required this.billingType,
  });

  final String billno;
  final String billDate;
  final String customerCode;
  final String customerName;
  final String orderNo;
  final double netAmount;
  final String billType;
  final String billingType;

  String get customerLabel {
    if (customerName.isNotEmpty) return customerName;
    if (customerCode.isNotEmpty) return customerCode;
    return 'Walk-in / cash';
  }

  factory SalesInvoiceSummary.fromJson(Map<String, dynamic> json) => SalesInvoiceSummary(
        billno: _billno(json['billno']),
        billDate: '${json['billdate'] ?? ''}'.trim(),
        customerCode: '${json['customer_code'] ?? ''}'.trim(),
        customerName: '${json['customer_name'] ?? ''}'.trim(),
        orderNo: '${json['orderno'] ?? ''}'.trim(),
        netAmount: _num(json['net_amount']),
        billType: '${json['billtype'] ?? 'C'}'.trim().toUpperCase(),
        billingType: '${json['billing_type'] ?? 'CASH'}'.trim().toUpperCase(),
      );
}

class SalesInvoiceDetailLine {
  SalesInvoiceDetailLine({
    required this.lineNo,
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    required this.discount,
    required this.amount,
    this.cost = 0,
    this.warehouseId,
    this.warehouseCode,
  });

  final int lineNo;
  final String itemCode;
  final String itemName;
  final String uom;
  final double qty;
  final double rate;
  final double discount;
  final double amount;
  final double cost;
  final String? warehouseId;
  final String? warehouseCode;

  factory SalesInvoiceDetailLine.fromJson(Map<String, dynamic> json) => SalesInvoiceDetailLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        itemCode: '${json['item_code'] ?? ''}'.trim(),
        itemName: '${json['item_name'] ?? ''}'.trim(),
        uom: '${json['uom'] ?? ''}'.trim(),
        qty: _num(json['qty']),
        rate: _num(json['rate']),
        discount: _num(json['discount']),
        amount: _num(json['amount']),
        cost: _num(json['cost']),
        warehouseId: json['warehouse_id'] == null || '${json['warehouse_id']}'.trim().isEmpty
            ? null
            : '${json['warehouse_id']}'.trim(),
        warehouseCode: () {
          final c = '${json['warehouse_code'] ?? json['store'] ?? ''}'.trim();
          return c.isEmpty ? null : c;
        }(),
      );
}

class SalesInvoiceDetail {
  SalesInvoiceDetail({
    required this.summary,
    required this.lines,
    this.billStatus = 'P',
    this.billTime = '',
    this.remarks = '',
    this.address = '',
    this.warehouseId,
    this.warehouseCode,
    this.warehouseName,
  });

  final SalesInvoiceSummary summary;
  final List<SalesInvoiceDetailLine> lines;
  /// P=pending, I=invoiced, V=cancelled (sales orders).
  final String billStatus;
  final String billTime;
  final String remarks;
  final String address;
  final String? warehouseId;
  final String? warehouseCode;
  final String? warehouseName;

  bool get isPendingOrder => billStatus == 'P' || billStatus.isEmpty;
  bool get isInvoicedOrder => billStatus == 'I';
  bool get isCancelledOrder => billStatus == 'V';

  factory SalesInvoiceDetail.fromJson(Map<String, dynamic> json) {
    final lines = (json['lines'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => SalesInvoiceDetailLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    final whId = json['warehouse_id'] == null || '${json['warehouse_id']}'.trim().isEmpty
        ? null
        : '${json['warehouse_id']}'.trim();
    final whCode = '${json['warehouse_code'] ?? ''}'.trim();
    final whName = '${json['warehouse_name'] ?? ''}'.trim();
    return SalesInvoiceDetail(
      summary: SalesInvoiceSummary.fromJson(json),
      lines: lines,
      billStatus: '${json['billstatus'] ?? 'P'}'.trim().toUpperCase(),
      billTime: '${json['billtime'] ?? ''}'.trim(),
      remarks: '${json['remarks'] ?? ''}'.trim(),
      address: '${json['address'] ?? ''}'.trim(),
      warehouseId: whId,
      warehouseCode: whCode.isEmpty ? null : whCode,
      warehouseName: whName.isEmpty ? null : whName,
    );
  }
}

class SalesOrderConvertResult {
  SalesOrderConvertResult({
    required this.orderBillno,
    required this.invoiceBillno,
    this.alreadyInvoiced = false,
    this.message = '',
  });

  final String orderBillno;
  final String invoiceBillno;
  final bool alreadyInvoiced;
  final String message;

  factory SalesOrderConvertResult.fromJson(Map<String, dynamic> json) => SalesOrderConvertResult(
        orderBillno: '${json['order_billno'] ?? ''}'.trim(),
        invoiceBillno: _billno(json['invoice_billno'] ?? json['billno']),
        alreadyInvoiced: json['already_invoiced'] == true,
        message: '${json['message'] ?? ''}'.trim(),
      );
}

class SalesInvoiceFeatures {
  const SalesInvoiceFeatures({
    this.warehouseEnabled = false,
    this.binTrackingEnabled = false,
    this.batchTrackingEnabled = false,
    this.orderNoMandatory = true,
    this.minusBillingEnabled = false,
  });

  final bool warehouseEnabled;
  final bool binTrackingEnabled;
  final bool batchTrackingEnabled;
  /// From ERP Sales Accounts Configuration (invoice Order No mandatory).
  final bool orderNoMandatory;
  /// From ERP Sales Accounts Configuration — allow selling / ordering below stock.
  final bool minusBillingEnabled;

  static bool _flag(dynamic v) {
    if (v == true || v == 1) return true;
    final s = '$v'.trim().toUpperCase();
    return s == 'Y' || s == 'YES' || s == 'TRUE' || s == '1' || s == 'ON';
  }

  SalesInvoiceFeatures copyWith({
    bool? warehouseEnabled,
    bool? binTrackingEnabled,
    bool? batchTrackingEnabled,
    bool? orderNoMandatory,
    bool? minusBillingEnabled,
  }) =>
      SalesInvoiceFeatures(
        warehouseEnabled: warehouseEnabled ?? this.warehouseEnabled,
        binTrackingEnabled: binTrackingEnabled ?? this.binTrackingEnabled,
        batchTrackingEnabled: batchTrackingEnabled ?? this.batchTrackingEnabled,
        orderNoMandatory: orderNoMandatory ?? this.orderNoMandatory,
        minusBillingEnabled: minusBillingEnabled ?? this.minusBillingEnabled,
      );

  factory SalesInvoiceFeatures.fromJson(Map<String, dynamic>? json) {
    final m = json == null ? const <String, dynamic>{} : Map<String, dynamic>.from(json);
    return SalesInvoiceFeatures(
      warehouseEnabled: _flag(m['warehouse_enabled']),
      binTrackingEnabled: _flag(m['bin_tracking_enabled']),
      batchTrackingEnabled: _flag(m['batch_tracking_enabled']),
      // Default true to match ERP LOCATIONMASTER default when flag is absent.
      orderNoMandatory: m['orderno_mandatory'] == null ? true : _flag(m['orderno_mandatory']),
      minusBillingEnabled: _flag(m['minus_billing_enabled']),
    );
  }
}

class SalesCatalogResult {
  const SalesCatalogResult({
    required this.items,
    this.minusBillingEnabled = false,
  });

  final List<SalesCatalogItem> items;
  final bool minusBillingEnabled;
}

class SalesCustomerOption {
  SalesCustomerOption({
    required this.code,
    required this.name,
    this.address = '',
    this.phone = '',
    this.billingType = 'CASH',
    this.creditLimit = 0,
    this.currentCredit = 0,
    this.outstanding = 0,
    this.categoryName = '',
  });

  final String code;
  final String name;
  final String address;
  final String phone;
  final String billingType;
  final double creditLimit;
  final double currentCredit;
  final double outstanding;
  final String categoryName;

  double get displayOutstanding => billingType == 'CREDIT' ? currentCredit : outstanding;

  bool get isCredit => billingType == 'CREDIT';

  /// ERP treats credit_limit <= 0 as no cap when validating credit sales.
  String get creditLimitLabel {
    if (!isCredit) return 'Cash customer';
    if (creditLimit <= 0) return 'Unlimited credit';
    return 'Credit limit ${creditLimit.toStringAsFixed(0)}';
  }

  SalesCustomerOption copyWith({
    String? code,
    String? name,
    String? address,
    String? phone,
    String? billingType,
    double? creditLimit,
    double? currentCredit,
    double? outstanding,
    String? categoryName,
  }) =>
      SalesCustomerOption(
        code: code ?? this.code,
        name: name ?? this.name,
        address: address ?? this.address,
        phone: phone ?? this.phone,
        billingType: billingType ?? this.billingType,
        creditLimit: creditLimit ?? this.creditLimit,
        currentCredit: currentCredit ?? this.currentCredit,
        outstanding: outstanding ?? this.outstanding,
        categoryName: categoryName ?? this.categoryName,
      );

  factory SalesCustomerOption.fromJson(Map<String, dynamic> json) => SalesCustomerOption(
        code: '${json['code'] ?? ''}'.trim(),
        name: '${json['name'] ?? ''}'.trim(),
        address: '${json['address'] ?? ''}'.trim(),
        phone: '${json['phone'] ?? ''}'.trim(),
        billingType: '${json['billing_type'] ?? 'CASH'}'.trim().toUpperCase(),
        creditLimit: _num(json['credit_limit']),
        currentCredit: _num(json['current_credit']),
        outstanding: _num(json['outstanding']),
        categoryName: '${json['category_name'] ?? ''}'.trim(),
      );
}

class SalesWarehouseOption {
  SalesWarehouseOption({
    required this.warehouseId,
    this.warehouseCode = '',
    this.warehouseName = '',
    this.label = '',
  });

  final String warehouseId;
  final String warehouseCode;
  final String warehouseName;
  final String label;

  factory SalesWarehouseOption.fromJson(Map<String, dynamic> json) => SalesWarehouseOption(
        warehouseId: '${json['warehouse_id'] ?? ''}'.trim(),
        warehouseCode: '${json['warehouse_code'] ?? ''}'.trim(),
        warehouseName: '${json['warehouse_name'] ?? ''}'.trim(),
        label: '${json['label'] ?? ''}'.trim(),
      );
}

class SalesBinOption {
  SalesBinOption({
    required this.storageId,
    required this.code,
    this.name = '',
    this.stock = 0,
  });

  final int storageId;
  final String code;
  final String name;
  final double stock;

  factory SalesBinOption.fromJson(Map<String, dynamic> json) => SalesBinOption(
        storageId: _int(json['storage_id']),
        code: '${json['code'] ?? ''}'.trim(),
        name: '${json['name'] ?? ''}'.trim(),
        stock: _num(json['stock']),
      );
}

class SalesLotOption {
  SalesLotOption({
    required this.lotId,
    this.batchNo = '',
    this.expiryDate = '',
    this.qty = 0,
  });

  final String lotId;
  final String batchNo;
  final String expiryDate;
  final double qty;

  String get label {
    final parts = <String>[if (batchNo.isNotEmpty) batchNo, if (expiryDate.isNotEmpty) 'Exp $expiryDate'];
    return parts.isEmpty ? 'Lot $lotId' : parts.join(' • ');
  }

  factory SalesLotOption.fromJson(Map<String, dynamic> json) => SalesLotOption(
        lotId: '${json['lot_id'] ?? ''}'.trim(),
        batchNo: '${json['batch_no'] ?? ''}'.trim(),
        expiryDate: '${json['expiry_date'] ?? ''}'.trim(),
        qty: _num(json['qty']),
      );
}

class SalesItemLastSale {
  SalesItemLastSale({
    required this.billno,
    required this.billDate,
    required this.customerCode,
    required this.customerName,
    required this.qty,
    required this.uom,
    required this.rate,
    required this.discount,
    required this.netRate,
    required this.forSelectedCustomer,
  });

  final String billno;
  final String billDate;
  final String customerCode;
  final String customerName;
  final double qty;
  final String uom;
  final double rate;
  final double discount;
  final double netRate;
  final bool forSelectedCustomer;

  String get customerLabel {
    if (customerName.isNotEmpty) return customerName;
    if (customerCode.isNotEmpty) return customerCode;
    return 'Customer';
  }

  factory SalesItemLastSale.fromJson(Map<String, dynamic> json) => SalesItemLastSale(
        billno: '${json['billno'] ?? ''}'.trim(),
        billDate: '${json['billdate'] ?? ''}'.trim(),
        customerCode: '${json['customer_code'] ?? ''}'.trim(),
        customerName: '${json['customer_name'] ?? ''}'.trim(),
        qty: _num(json['qty']),
        uom: '${json['uom'] ?? ''}'.trim(),
        rate: _num(json['rate']),
        discount: _num(json['discount']),
        netRate: _num(json['net_rate']),
        forSelectedCustomer: json['for_selected_customer'] == true,
      );
}

class SalesItemInfo {
  SalesItemInfo({
    required this.itemCode,
    required this.itemName,
    required this.baseUom,
    required this.retailPrice,
    required this.costPrice,
    required this.currentStock,
    this.averageCost = 0,
    this.batchTracked = false,
    this.defaultWarehouseId,
    this.defaultBinStorageId,
  });

  final String itemCode;
  final String itemName;
  final String baseUom;
  final double retailPrice;
  final double costPrice;
  final double currentStock;
  /// Base-UOM inventory unit cost (ITEMMASTER.AVERAGECOST).
  final double averageCost;
  final bool batchTracked;
  final int? defaultWarehouseId;
  final int? defaultBinStorageId;

  factory SalesItemInfo.fromJson(Map<String, dynamic> json) => SalesItemInfo(
        itemCode: '${json['item_code'] ?? ''}'.trim(),
        itemName: '${json['item_name'] ?? ''}'.trim(),
        baseUom: '${json['base_uom'] ?? ''}'.trim(),
        retailPrice: _num(json['retail_price']),
        costPrice: _num(json['cost_price']),
        currentStock: _num(json['current_stock']),
        averageCost: _num(json['average_cost'] ?? json['averagecost']),
        batchTracked: json['batch_tracked'] == true,
        defaultWarehouseId: json['default_warehouse_id'] == null ? null : _int(json['default_warehouse_id']),
        defaultBinStorageId: json['default_bin_storage_id'] == null ? null : _int(json['default_bin_storage_id']),
      );
}

class SalesUomOption {
  SalesUomOption({
    required this.code,
    required this.name,
    this.isBase = false,
    this.conversionFactor = 1,
  });

  final String code;
  final String name;
  final bool isBase;
  final double conversionFactor;

  factory SalesUomOption.fromJson(Map<String, dynamic> json) => SalesUomOption(
        code: '${json['code'] ?? ''}'.trim(),
        name: '${json['name'] ?? ''}'.trim(),
        isBase: json['is_base'] == true,
        conversionFactor: _num(json['conversion_factor'] ?? 1),
      );
}

class SalesCatalogItem {
  SalesCatalogItem({
    required this.itemCode,
    required this.itemName,
    required this.unit,
    required this.rate,
    required this.stock,
    this.brand = '',
    this.barcode = '',
    this.costPrice = 0,
    this.averageCost = 0,
    this.lastQty = 0,
    this.lastRate = 0,
    this.lastBillDate = '',
    this.lastBillNo = '',
    this.timesOrdered = 0,
  });

  final String itemCode;
  final String itemName;
  final String unit;
  final double rate;
  final double stock;
  final String brand;
  final String barcode;
  final double costPrice;
  final double averageCost;
  /// From customer previous-sales tab (optional).
  final double lastQty;
  final double lastRate;
  final String lastBillDate;
  final String lastBillNo;
  final int timesOrdered;

  double get displayAvgCost => averageCost > 0 ? averageCost : costPrice;
  double get displayCostPrice => costPrice > 0 ? costPrice : averageCost;

  factory SalesCatalogItem.fromJson(Map<String, dynamic> json) => SalesCatalogItem(
        itemCode: '${json['item_code'] ?? ''}'.trim(),
        itemName: '${json['item_name'] ?? ''}'.trim(),
        unit: '${json['unit'] ?? 'PCS'}'.trim(),
        rate: _num(json['rate']),
        stock: _num(json['stock']),
        brand: '${json['brand'] ?? ''}'.trim(),
        barcode: '${json['barcode'] ?? ''}'.trim(),
        costPrice: _num(json['cost_price'] ?? json['costprice']),
        averageCost: _num(json['average_cost'] ?? json['averagecost']),
        lastQty: _num(json['last_qty']),
        lastRate: _num(json['last_rate']),
        lastBillDate: '${json['last_billdate'] ?? json['last_bill_date'] ?? ''}'.trim(),
        lastBillNo: '${json['last_billno'] ?? json['last_bill_no'] ?? ''}'.trim(),
        timesOrdered: int.tryParse('${json['times_ordered'] ?? 0}') ?? 0,
      );
}

class SalesUomPricing {
  SalesUomPricing({
    required this.uomCode,
    required this.rate,
    this.conversionFactor = 1,
    this.costPrice = 0,
    this.averageCost = 0,
  });

  final String uomCode;
  final double rate;
  final double conversionFactor;
  final double costPrice;
  /// Base-UOM inventory unit cost (ITEMMASTER.AVERAGECOST). Never alt pack cost.
  final double averageCost;

  factory SalesUomPricing.fromJson(Map<String, dynamic> json) => SalesUomPricing(
        uomCode: '${json['uom_code'] ?? ''}'.trim(),
        rate: _num(json['rate']),
        conversionFactor: _num(json['conversion_factor'] ?? 1),
        costPrice: _num(json['cost_price']),
        averageCost: _num(json['average_cost'] ?? json['averagecost']),
      );
}

class SalesPaymentTender {
  SalesPaymentTender({
    required this.tenderCode,
    required this.tenderName,
    this.category = '',
    this.sortOrder = 0,
    this.iconKey = '',
  });

  final String tenderCode;
  final String tenderName;
  final String category;
  final int sortOrder;
  final String iconKey;

  factory SalesPaymentTender.fromJson(Map<String, dynamic> json) => SalesPaymentTender(
        tenderCode: '${json['tender_code'] ?? ''}'.trim().toUpperCase(),
        tenderName: '${json['tender_name'] ?? json['tender_code'] ?? ''}'.trim(),
        category: '${json['category'] ?? ''}'.trim().toUpperCase(),
        sortOrder: int.tryParse('${json['sort_order'] ?? 0}') ?? 0,
        iconKey: '${json['icon_key'] ?? ''}'.trim(),
      );

  /// POS checkout fallback when tenant tender API is empty (same as ``DEFAULT_CHECKOUT_TENDERS``).
  static final List<SalesPaymentTender> posDefaults = [
    SalesPaymentTender(tenderCode: 'CASH', tenderName: 'Cash', category: 'CASH', sortOrder: 10, iconKey: 'cash'),
    SalesPaymentTender(tenderCode: 'CARD', tenderName: 'Card', category: 'CARD', sortOrder: 20, iconKey: 'card'),
    SalesPaymentTender(tenderCode: 'LOYALTY', tenderName: 'Loyalty points', category: 'WALLET', sortOrder: 60, iconKey: 'loyalty'),
    SalesPaymentTender(tenderCode: 'POINTS', tenderName: 'Points amount', category: 'WALLET', sortOrder: 61, iconKey: 'points'),
  ];
}

class SalesOpenContext {
  SalesOpenContext({
    required this.billno,
    required this.billDate,
    required this.billTime,
    required this.locationCode,
    this.locationName = '',
    this.features = const SalesInvoiceFeatures(),
    this.defaultWarehouseId,
    this.defaultWarehouseCode = '',
    this.defaultWarehouseName = '',
    this.defaultWarehouseLabel = '',
  });

  final String billno;
  final String billDate;
  final String billTime;
  final int locationCode;
  final String locationName;
  final SalesInvoiceFeatures features;
  final int? defaultWarehouseId;
  final String defaultWarehouseCode;
  final String defaultWarehouseName;
  final String defaultWarehouseLabel;

  factory SalesOpenContext.fromJson(Map<String, dynamic> json) => SalesOpenContext(
        billno: _billno(json['billno']),
        billDate: '${json['bill_date'] ?? ''}'.trim(),
        billTime: '${json['bill_time'] ?? ''}'.trim(),
        locationCode: _int(json['location_code']),
        locationName: '${json['location_name'] ?? ''}'.trim(),
        features: SalesInvoiceFeatures.fromJson(
          json['features'] is Map ? Map<String, dynamic>.from(json['features'] as Map) : null,
        ),
        defaultWarehouseId: json['default_warehouse_id'] == null ? null : _int(json['default_warehouse_id']),
        defaultWarehouseCode: '${json['default_warehouse_code'] ?? ''}'.trim(),
        defaultWarehouseName: '${json['default_warehouse_name'] ?? ''}'.trim(),
        defaultWarehouseLabel: '${json['default_warehouse_label'] ?? ''}'.trim(),
      );
}

class SalesCreditCheckResult {
  SalesCreditCheckResult({required this.ok, this.error, this.billingType = 'CREDIT'});

  final bool ok;
  final String? error;
  final String billingType;

  factory SalesCreditCheckResult.fromJson(Map<String, dynamic> json) => SalesCreditCheckResult(
        ok: json['ok'] == true,
        error: json['error'] as String?,
        billingType: '${json['billing_type'] ?? 'CREDIT'}',
      );
}

class SalesSaveResult {
  SalesSaveResult({
    required this.billno,
    this.message,
    this.billnoReassigned = false,
    this.glPosted = false,
    this.glVoucherNo,
    this.accountsPosted = false,
  });

  final String billno;
  final String? message;
  final bool billnoReassigned;
  final bool glPosted;
  final String? glVoucherNo;
  final bool accountsPosted;

  factory SalesSaveResult.fromJson(Map<String, dynamic> json) => SalesSaveResult(
        billno: _billno(json['billno']),
        message: json['message'] as String?,
        billnoReassigned: json['billno_reassigned'] == true,
        glPosted: json['gl_posted'] == true,
        glVoucherNo: json['gl_voucher_no'] as String?,
        accountsPosted: json['accounts_posted'] == true,
      );
}

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? 0;
}

String _billno(dynamic v) {
  if (v == null) return '';
  return '$v'.trim();
}

class SalesService {
  SalesService(this._apiClient);

  final ApiClient _apiClient;

  Map<String, dynamic> _data(Map<String, dynamic> root) {
    if (root['success'] == false) {
      final msg = '${root['message'] ?? 'Request failed'}'.trim();
      throw Exception(msg.isEmpty ? 'Request failed' : msg);
    }
    final data = root['data'];
    if (data is Map) {
      return Map<String, dynamic>.from(data);
    }
    throw Exception(
      '${root['message'] ?? 'Unexpected API response (missing data)'}'.trim(),
    );
  }

  Future<SalesReportsData> getReports({
    int days = 30,
    String dateFrom = '',
    String dateTo = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/reports',
      queryParameters: {
        if (dateFrom.trim().isNotEmpty && dateTo.trim().isNotEmpty) ...{
          'date_from': dateFrom.trim(),
          'date_to': dateTo.trim(),
        } else
          'days': days,
      },
    );
    return SalesReportsData.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<SalesInvoiceSummary>> listInvoices({
    String q = '',
    int limit = 50,
    int days = 90,
    String dateFrom = '',
    String dateTo = '',
    String customerCode = '',
    String billingType = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoices',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
        'days': days,
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
        if (customerCode.trim().isNotEmpty) 'customer_code': customerCode.trim(),
        if (billingType.trim().isNotEmpty) 'billing_type': billingType.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['invoices'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => SalesInvoiceSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<SalesInvoiceDetail> getInvoiceDetail(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get('/api/v1/sales/invoices/$encoded');
    return SalesInvoiceDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  /// ERP cashbilldup invoice PDF bytes for [billno].
  Future<List<int>> downloadInvoicePdf(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/sales/invoices/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<SalesOpenContext> getInvoiceOpen({bool peek = true}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/open',
      queryParameters: {'peek': peek},
    );
    return SalesOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<SalesCustomerOption>> searchCustomers({
    String q = '',
    int limit = 50,
    String billingType = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/customers',
      queryParameters: {
        'q': q.trim(),
        'limit': limit,
        if (billingType.trim().isNotEmpty) 'billing_type': billingType.trim().toUpperCase(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['customers'] as List<dynamic>? ?? const [])
        .map((e) => SalesCustomerOption.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<SalesCustomerOption> fetchCustomerOutstanding(String customerCode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/customer-outstanding',
      queryParameters: {'customer_code': customerCode.trim()},
    );
    return SalesCustomerOption.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<SalesWarehouseOption>> searchWarehouses({String q = '', int limit = 100}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/warehouses',
      queryParameters: {'q': q.trim(), 'limit': limit},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['warehouses'] as List<dynamic>? ?? const [])
        .map((e) => SalesWarehouseOption.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// When the branch has exactly one warehouse, return it for auto-select.
  Future<SalesWarehouseOption?> soleWarehouseIfOnlyOne() async {
    final rows = await searchWarehouses(limit: 5);
    if (rows.length != 1) return null;
    final w = rows.first;
    if (w.warehouseId.trim().isEmpty) return null;
    return w;
  }

  Future<List<SalesBinOption>> getWarehouseBins(String warehouseId) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/warehouse-bins',
      queryParameters: {'warehouse_id': warehouseId},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['bins'] as List<dynamic>? ?? const [])
        .map((e) => SalesBinOption.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<SalesBinOption>> getItemBins({
    required String itemCode,
    required String warehouseId,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/item-bins',
      queryParameters: {'item_code': itemCode, 'warehouse_id': warehouseId},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['bins'] as List<dynamic>? ?? const [])
        .map((e) => SalesBinOption.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<SalesLotOption>> getBatchLots(String itemCode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/batch-lots',
      queryParameters: {'item_code': itemCode},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['lots'] as List<dynamic>? ?? const [])
        .map((e) => SalesLotOption.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<SalesCreditCheckResult> checkCredit({
    required String customerCode,
    required double netAmount,
    required String billingType,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/credit-check',
      queryParameters: {
        'customer_code': customerCode,
        'net_amount': netAmount,
        'billing_type': billingType,
      },
    );
    return SalesCreditCheckResult.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<SalesItemInfo> lookupItem(String query) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/item-info',
      queryParameters: {'query': query.trim()},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return SalesItemInfo.fromJson(data['item'] as Map<String, dynamic>);
  }

  Future<List<SalesUomOption>> getItemUoms(String itemCode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/item-uoms',
      queryParameters: {'item_code': itemCode},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['uoms'] as List<dynamic>? ?? const [])
        .map((e) => SalesUomOption.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<SalesUomPricing> getUomPricing(String itemCode, String uomCode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/uom-info',
      queryParameters: {'item_code': itemCode, 'uom_code': uomCode},
    );
    final data = _data(response.data as Map<String, dynamic>);
    return SalesUomPricing.fromJson(data['pricing'] as Map<String, dynamic>);
  }

  Future<SalesItemLastSale?> getItemLastSale({
    required String itemCode,
    String customerCode = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/item-last-sale',
      queryParameters: {
        'item_code': itemCode.trim(),
        if (customerCode.trim().isNotEmpty) 'customer_code': customerCode.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    final raw = data['last_sale'];
    if (raw is! Map) return null;
    return SalesItemLastSale.fromJson(Map<String, dynamic>.from(raw));
  }

  Future<SalesCatalogResult> searchCatalog({
    String q = '',
    String warehouseId = '',
    String customerCode = '',
    int limit = 60,
    /// Sales return: full item master including zero stock.
    bool forReturn = false,
    /// Sales order: use ERP MINUSBILLING_ORDER (list all items when enabled).
    bool forOrder = false,
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/catalog',
      queryParameters: {
        'q': q.trim(),
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        if (customerCode.isNotEmpty) 'customer_code': customerCode,
        'limit': forReturn ? (limit < 200 ? 400 : limit) : limit,
        if (forReturn) 'for_return': true,
        if (forOrder) 'for_order': true,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    final items = (data['items'] as List<dynamic>? ?? const [])
        .map((e) => SalesCatalogItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    // Returns / order-invoice minus flag from catalog (authoritative for Add button).
    final minus = forReturn || SalesInvoiceFeatures._flag(data['minus_billing_enabled']);
    return SalesCatalogResult(items: items, minusBillingEnabled: minus);
  }

  Future<List<SalesCatalogItem>> listCustomerPreviousItems({
    required String customerCode,
    String warehouseId = '',
    int limit = 80,
    int days = 365,
  }) async {
    final code = customerCode.trim();
    if (code.isEmpty || code == '0') return const [];
    final response = await _apiClient.dio.get(
      '/api/v1/sales/invoice/customer-previous-items',
      queryParameters: {
        'customer_code': code,
        if (warehouseId.isNotEmpty) 'warehouse_id': warehouseId,
        'limit': limit,
        'days': days,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['items'] as List<dynamic>? ?? const [])
        .map((e) => SalesCatalogItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .where((e) => e.itemCode.isNotEmpty)
        .toList();
  }

  Future<List<SalesPaymentTender>> listPaymentTenders() async {
    try {
      final response = await _apiClient.dio.get('/api/v1/sales/invoice/payment-tenders');
      final data = _data(response.data as Map<String, dynamic>);
      final rows = (data['tenders'] as List<dynamic>? ?? const [])
          .map((e) => SalesPaymentTender.fromJson(e as Map<String, dynamic>))
          .where((t) => t.tenderCode.isNotEmpty)
          .toList();
      if (rows.isNotEmpty) return rows;
    } catch (_) {
      // Endpoint missing or offline — use POS defaults below.
    }
    return List<SalesPaymentTender>.from(SalesPaymentTender.posDefaults);
  }

  Future<SalesSaveResult> saveInvoice({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/sales/invoice/save',
      data: {'header': header, 'lines': lines},
    );
    final raw = response.data;
    if (raw is! Map) {
      throw Exception('Unexpected save response from server.');
    }
    final result = SalesSaveResult.fromJson(_data(Map<String, dynamic>.from(raw)));
    if (result.billno.trim().isEmpty) {
      throw Exception('Save completed but no invoice number was returned. Check the invoice list.');
    }
    return result;
  }

  // ---- Sales Return (BILLHDR return / credit note style) ----

  Future<List<SalesInvoiceSummary>> listReturns({
    String q = '',
    int limit = 50,
    int days = 90,
    String dateFrom = '',
    String dateTo = '',
    String customerCode = '',
    String billingType = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/returns',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
        'days': days,
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
        if (customerCode.trim().isNotEmpty) 'customer_code': customerCode.trim(),
        if (billingType.trim().isNotEmpty) 'billing_type': billingType.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['returns'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => SalesInvoiceSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<SalesInvoiceDetail> getReturnDetail(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get('/api/v1/sales/returns/$encoded');
    return SalesInvoiceDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<List<int>> downloadReturnPdf(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/sales/returns/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<SalesOpenContext> getReturnOpen({bool peek = true}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/return/open',
      queryParameters: {'peek': peek},
    );
    return SalesOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<SalesSaveResult> saveReturn({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/sales/return/save',
      data: {'header': header, 'lines': lines},
    );
    final raw = response.data;
    if (raw is! Map) {
      throw Exception('Unexpected save response from server.');
    }
    final result = SalesSaveResult.fromJson(_data(Map<String, dynamic>.from(raw)));
    if (result.billno.trim().isEmpty) {
      throw Exception('Save completed but no return number was returned. Check the return list.');
    }
    return result;
  }

  /// Prefill return header + lines from a posted sales invoice.
  Future<Map<String, dynamic>> loadReturnFromInvoice(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get('/api/v1/sales/return/load-from-invoice/$encoded');
    return _data(response.data as Map<String, dynamic>);
  }

  // ---- Sales Order (mirrors invoice methods above, no payment panel) ----

  Future<List<SalesInvoiceSummary>> listOrders({
    String q = '',
    int limit = 50,
    int days = 90,
    String dateFrom = '',
    String dateTo = '',
    String customerCode = '',
    String billingType = '',
    /// `order` | `invoiced` | `cancelled` | `all`
    String statusTab = 'order',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/orders',
      queryParameters: {
        if (q.trim().isNotEmpty) 'q': q.trim(),
        'limit': limit,
        'days': days,
        if (dateFrom.trim().isNotEmpty) 'date_from': dateFrom.trim(),
        if (dateTo.trim().isNotEmpty) 'date_to': dateTo.trim(),
        if (customerCode.trim().isNotEmpty) 'customer_code': customerCode.trim(),
        if (billingType.trim().isNotEmpty) 'billing_type': billingType.trim(),
        'status_tab': statusTab.trim().isEmpty ? 'order' : statusTab.trim(),
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    return (data['orders'] as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) => SalesInvoiceSummary.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<SalesInvoiceDetail> getOrderDetail(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get('/api/v1/sales/orders/$encoded');
    return SalesInvoiceDetail.fromJson(_data(response.data as Map<String, dynamic>));
  }

  /// ERP cashbilldup sales-order PDF bytes for [billno].
  Future<List<int>> downloadOrderPdf(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/sales/orders/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }

  Future<SalesOpenContext> getOrderOpen({bool peek = true}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/sales/order/open',
      queryParameters: {'peek': peek},
    );
    return SalesOpenContext.fromJson(_data(response.data as Map<String, dynamic>));
  }

  Future<SalesSaveResult> saveOrder({
    required Map<String, dynamic> header,
    required List<Map<String, dynamic>> lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/sales/order/save',
      data: {'header': header, 'lines': lines},
    );
    final raw = response.data;
    if (raw is! Map) {
      throw Exception('Unexpected save response from server.');
    }
    final result = SalesSaveResult.fromJson(_data(Map<String, dynamic>.from(raw)));
    if (result.billno.trim().isEmpty) {
      throw Exception('Save completed but no order number was returned. Check the order list.');
    }
    return result;
  }

  Future<SalesOrderConvertResult> convertOrderToInvoice(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    final response = await _apiClient.dio.post('/api/v1/sales/orders/$encoded/convert');
    final root = response.data as Map<String, dynamic>;
    return SalesOrderConvertResult.fromJson(_data(root));
  }

  Future<void> cancelOrder(String billno) async {
    final encoded = Uri.encodeComponent(billno.trim());
    await _apiClient.dio.post('/api/v1/sales/orders/$encoded/cancel');
  }
}
