import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/ui/app_snackbar.dart';
import '../../core/ui/confirm_save.dart';
import '../../core/storage/printer_storage.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../providers/auth_provider.dart';
import '../../services/sales_service.dart';
import 'sales_customer_picker_sheet.dart';
import '../barcode_scanner_screen.dart';
import 'sales_invoice_cart_screen.dart';
import 'sales_invoice_catalog_step.dart';
import 'sales_invoice_item_detail_screen.dart';
import 'sales_invoice_payment_panel.dart';
import 'sales_invoice_quick_qty_sheet.dart';
import 'sales_transaction_draft.dart';
import '../../core/theme/app_theme.dart';

class _InvoiceLine {
  _InvoiceLine({
    required this.slno,
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    this.discount = 0,
    this.cost = 0,
    this.averageCost = 0,
    this.conversionFactor = 1,
    this.availableUoms = const [],
    this.warehouseId,
    this.warehouseCode,
    this.storageId,
    this.binCode,
    this.binName,
    this.lotId,
    this.lotLabel,
    this.batchTracked = false,
  });

  final int slno;
  final String itemCode;
  final String itemName;
  String uom;
  double qty;
  double rate;
  /// Discount **per unit** (ERP ITDISC = this × qty).
  double discount;
  double cost;
  /// Base-UOM inventory unit cost for COGS (not alt pack cost).
  double averageCost;
  double conversionFactor;
  List<SalesUomOption> availableUoms;
  String? warehouseId;
  String? warehouseCode;
  int? storageId;
  String? binCode;
  String? binName;
  String? lotId;
  String? lotLabel;
  bool batchTracked;

  double get baseQty => qty * conversionFactor;
  double get discountTotal => qty * discount;
  double get amount => (qty * rate) - discountTotal;

  _InvoiceLine copyWithSlno(int newSlno) => _InvoiceLine(
        slno: newSlno,
        itemCode: itemCode,
        itemName: itemName,
        uom: uom,
        qty: qty,
        rate: rate,
        discount: discount,
        cost: cost,
        averageCost: averageCost,
        conversionFactor: conversionFactor,
        availableUoms: availableUoms,
        warehouseId: warehouseId,
        warehouseCode: warehouseCode,
        storageId: storageId,
        binCode: binCode,
        binName: binName,
        lotId: lotId,
        lotLabel: lotLabel,
        batchTracked: batchTracked,
      );
}

class SalesInvoiceFormScreen extends StatefulWidget {
  const SalesInvoiceFormScreen({
    super.key,
    this.restoreDraft = false,
    this.seedAiCart = const [],
    this.seedBillingType,
    this.seedWalkIn,
    this.seedCustomer,
    this.seedWarehouse,
    this.seedAddress,
    this.seedOrderNo,
    this.seedRemarks,
  });

  /// When true, restores the in-session draft after open context loads.
  final bool restoreDraft;

  /// Optional AI Sales Mode cart lines to seed after open context loads.
  /// Each map: item_code, qty, unit?, rate?
  final List<Map<String, dynamic>> seedAiCart;

  /// Header fields seeded from AI Sales setup (applied after open context).
  final String? seedBillingType;
  final bool? seedWalkIn;
  final SalesCustomerOption? seedCustomer;
  final SalesWarehouseOption? seedWarehouse;
  final String? seedAddress;
  final String? seedOrderNo;
  final String? seedRemarks;

  @override
  State<SalesInvoiceFormScreen> createState() => _SalesInvoiceFormScreenState();
}

class _SalesInvoiceFormScreenState extends State<SalesInvoiceFormScreen> with WidgetsBindingObserver {
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  int _step = 0;
  bool _loading = true;
  bool _submitting = false;
  String? _loadError;

  String _billno = '';
  String _billDate = '';
  String _billTime = '';
  String _locationName = '';
  SalesInvoiceFeatures _features = const SalesInvoiceFeatures();

  SalesCustomerOption? _customer;
  SalesWarehouseOption? _headerWarehouse;
  final _orderNo = TextEditingController();
  final _remarks = TextEditingController();
  final _address = TextEditingController();
  String _billingType = 'CASH';
  bool _walkIn = false;

  List<SalesPaymentTender> _paymentTenders = const [];
  Map<String, double> _paymentAmounts = {};

  final _catalogSearch = TextEditingController();
  final List<_InvoiceLine> _lines = [];
  List<SalesCatalogItem> _catalogItems = [];
  List<SalesCatalogItem> _customerItems = [];
  bool _catalogLoading = false;
  bool _customerItemsLoading = false;
  String? _catalogError;
  String? _customerItemsError;
  Timer? _catalogDebounce;
  Timer? _draftDebounce;
  String _draftTenantId = '';
  String _draftUsername = '';
  bool _draftCleared = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _orderNo.addListener(_scheduleDraftSave);
    _remarks.addListener(_scheduleDraftSave);
    _address.addListener(_scheduleDraftSave);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = context.read<AuthProvider>().user;
      _draftTenantId = user?.tenantId ?? '';
      _draftUsername = user?.username ?? '';
      _load();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.inactive) {
      _persistDraft();
    }
  }

  @override
  void dispose() {
    _persistDraft();
    WidgetsBinding.instance.removeObserver(this);
    _orderNo.removeListener(_scheduleDraftSave);
    _remarks.removeListener(_scheduleDraftSave);
    _address.removeListener(_scheduleDraftSave);
    _orderNo.dispose();
    _remarks.dispose();
    _address.dispose();
    _catalogSearch.dispose();
    _catalogDebounce?.cancel();
    _draftDebounce?.cancel();
    super.dispose();
  }

  void _scheduleDraftSave() {
    if (_draftCleared || _loading || _submitting) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), _persistDraft);
  }

  bool get _hasMeaningfulDraft => SalesTransactionDraft.isMeaningful(
        walkIn: _walkIn,
        customer: _customer,
        orderNo: _orderNo.text,
        remarks: _remarks.text,
        address: _address.text,
        lines: _lines,
        paymentAmounts: _paymentAmounts,
      );

  Future<void> _persistDraft() async {
    if (_draftCleared || _submitting) return;
    if (!_hasMeaningfulDraft) return;
    if (_draftUsername.isEmpty) return;
    final draft = <String, dynamic>{
      'step': _step,
      'billing_type': _billingType,
      'walk_in': _walkIn,
      'order_no': _orderNo.text,
      'remarks': _remarks.text,
      'address': _address.text,
      'customer': SalesTransactionDraft.encodeCustomer(_customer),
      'warehouse': SalesTransactionDraft.encodeWarehouse(_headerWarehouse),
      'payment_amounts': _paymentAmounts.map((k, v) => MapEntry(k, v)),
      'lines': _lines
          .map(
            (l) => SalesTransactionDraft.encodeLine(
              slno: l.slno,
              itemCode: l.itemCode,
              itemName: l.itemName,
              uom: l.uom,
              qty: l.qty,
              rate: l.rate,
              discount: l.discount,
              cost: l.cost,
              averageCost: l.averageCost,
              conversionFactor: l.conversionFactor,
              availableUoms: l.availableUoms,
              warehouseId: l.warehouseId,
              warehouseCode: l.warehouseCode,
              storageId: l.storageId,
              binCode: l.binCode,
              binName: l.binName,
              lotId: l.lotId,
              lotLabel: l.lotLabel,
              batchTracked: l.batchTracked,
            ),
          )
          .toList(),
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.salesInvoice,
      tenantId: _draftTenantId,
      username: _draftUsername,
      draft: draft,
    );
  }

  Future<void> _clearDraft() async {
    _draftCleared = true;
    _draftDebounce?.cancel();
    if (_draftUsername.isEmpty) return;
    await TransactionDraftStorage.clear(
      docType: TransactionDraftType.salesInvoice,
      tenantId: _draftTenantId,
      username: _draftUsername,
    );
  }

  void _applyDraft(Map<String, dynamic> draft) {
    final linesRaw = (draft['lines'] as List?) ?? const [];
    final lines = <_InvoiceLine>[];
    for (var i = 0; i < linesRaw.length; i++) {
      final m = SalesTransactionDraft.lineAt(linesRaw, i);
      if (m == null) continue;
      final uoms = ((m['available_uoms'] as List?) ?? const [])
          .whereType<Map>()
          .map((e) => SalesTransactionDraft.decodeUom(Map<String, dynamic>.from(e)))
          .toList();
      lines.add(
        _InvoiceLine(
          slno: SalesTransactionDraft.intOf(m['slno']) > 0
              ? SalesTransactionDraft.intOf(m['slno'])
              : i + 1,
          itemCode: '${m['item_code'] ?? ''}'.trim(),
          itemName: '${m['item_name'] ?? ''}'.trim(),
          uom: '${m['uom'] ?? 'PCS'}'.trim(),
          qty: SalesTransactionDraft.numOf(m['qty']),
          rate: SalesTransactionDraft.numOf(m['rate']),
          discount: SalesTransactionDraft.numOf(m['discount']),
          cost: SalesTransactionDraft.numOf(m['cost']),
          averageCost: SalesTransactionDraft.numOf(m['average_cost']) > 0
              ? SalesTransactionDraft.numOf(m['average_cost'])
              : SalesTransactionDraft.numOf(m['cost']),
          conversionFactor: SalesTransactionDraft.numOf(m['conversion_factor']) > 0
              ? SalesTransactionDraft.numOf(m['conversion_factor'])
              : 1,
          availableUoms: uoms,
          warehouseId: '${m['warehouse_id'] ?? ''}'.trim().isEmpty ? null : '${m['warehouse_id']}'.trim(),
          warehouseCode: '${m['warehouse_code'] ?? ''}'.trim().isEmpty ? null : '${m['warehouse_code']}'.trim(),
          storageId: SalesTransactionDraft.intOf(m['storage_id']) > 0
              ? SalesTransactionDraft.intOf(m['storage_id'])
              : null,
          binCode: '${m['bin_code'] ?? ''}'.trim().isEmpty ? null : '${m['bin_code']}'.trim(),
          binName: '${m['bin_name'] ?? ''}'.trim().isEmpty ? null : '${m['bin_name']}'.trim(),
          lotId: '${m['lot_id'] ?? ''}'.trim().isEmpty ? null : '${m['lot_id']}'.trim(),
          lotLabel: '${m['lot_label'] ?? ''}'.trim().isEmpty ? null : '${m['lot_label']}'.trim(),
          batchTracked: m['batch_tracked'] == true,
        ),
      );
    }

    _orderNo.text = '${draft['order_no'] ?? ''}';
    _remarks.text = '${draft['remarks'] ?? ''}';
    _address.text = '${draft['address'] ?? ''}';
    _customer = SalesTransactionDraft.decodeCustomer(draft['customer']);
    _headerWarehouse = SalesTransactionDraft.decodeWarehouse(draft['warehouse']) ?? _headerWarehouse;
    _walkIn = draft['walk_in'] == true;
    _billingType = '${draft['billing_type'] ?? (_walkIn ? 'CASH' : 'CASH')}'.trim().toUpperCase();
    if (_billingType != 'CREDIT') _billingType = 'CASH';
    final payRaw = draft['payment_amounts'];
    if (payRaw is Map) {
      _paymentAmounts = {
        for (final e in payRaw.entries) '${e.key}': SalesTransactionDraft.numOf(e.value),
      };
    } else {
      _paymentAmounts = {};
    }
    _lines
      ..clear()
      ..addAll(lines);
    final step = SalesTransactionDraft.intOf(draft['step']);
    _step = step.clamp(0, 2);
  }

  double get _netTotal => _lines.fold(0.0, (s, l) => s + l.amount);

  double get _discountTotal => _lines.fold(0.0, (s, l) => s + l.discountTotal);

  double get _grossTotal => _lines.fold(0.0, (s, l) => s + (l.qty * l.rate));

  void _clampLineDiscount(int index) {
    if (index < 0 || index >= _lines.length) return;
    final l = _lines[index];
    // Per-unit discount cannot exceed rate.
    if (l.discount > l.rate) l.discount = l.rate;
    if (l.discount < 0) l.discount = 0;
  }

  List<SalesInvoiceLineView> get _lineViews => _lines.asMap().entries.map((e) {
        final l = e.value;
        final meta = <String>[
          l.uom,
          if (l.binCode != null && l.binCode!.isNotEmpty) 'Bin ${l.binCode}',
          if (l.lotLabel != null && l.lotLabel!.isNotEmpty) l.lotLabel!,
        ].join(' • ');
        return SalesInvoiceLineView(
          slno: e.key + 1,
          itemCode: l.itemCode,
          itemName: l.itemName,
          subtitle: meta,
          qty: l.qty,
          rate: l.rate,
          amount: l.amount,
          discount: l.discount,
        );
      }).toList();

  void _setBillingType(String type, {VoidCallback? sheetRefresh}) {
    final next = type.toUpperCase();
    if (next == 'CREDIT' && _walkIn) {
      showAppSnackBar(context, 'Credit sale requires a customer. Turn off walk-in first.');
      return;
    }
    setState(() {
      _billingType = next;
      if (next == 'CREDIT') {
        _walkIn = false;
        _paymentAmounts = {};
      }
      // Customer list is bill-type scoped — drop mismatch on switch.
      if (_customer != null && _customer!.billingType != next) {
        _customer = null;
      }
    });
    _scheduleDraftSave();
    sheetRefresh?.call();
  }

  void _setWalkIn(bool value, {VoidCallback? sheetRefresh}) {
    setState(() {
      _walkIn = value;
      if (value) {
        _customer = null;
        _billingType = 'CASH';
        _address.clear();
        _paymentAmounts = {};
        _customerItems = [];
        _customerItemsError = null;
      }
    });
    _scheduleDraftSave();
    sheetRefresh?.call();
  }

  String? _validateHeader() {
    if (_features.orderNoMandatory && !_walkIn && _orderNo.text.trim().isEmpty) {
      return 'Order No is required.';
    }
    if (_billingType == 'CREDIT' && _customer == null) {
      return 'Credit sale requires a customer.';
    }
    if (!_walkIn && _customer == null) {
      return 'Select a customer or choose walk-in cash sale.';
    }
    if (_features.warehouseEnabled && (_headerWarehouse == null || _headerWarehouse!.warehouseId.isEmpty)) {
      return 'Select a warehouse.';
    }
    return null;
  }

  void _removeLine(int index) {
    setState(() {
      _lines.removeAt(index);
      for (var j = 0; j < _lines.length; j++) {
        _lines[j] = _lines[j].copyWithSlno(j + 1);
      }
    });
    _scheduleDraftSave();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final svc = context.read<SalesService>();
      final ctx = await svc.getInvoiceOpen(peek: true);
      if (!mounted) return;
      setState(() {
        _billno = ctx.billno;
        _billDate = ctx.billDate;
        _billTime = ctx.billTime;
        _locationName = ctx.locationName;
        _features = ctx.features;
        if (ctx.defaultWarehouseId != null && ctx.defaultWarehouseId! > 0) {
          _headerWarehouse = SalesWarehouseOption(
            warehouseId: '${ctx.defaultWarehouseId}',
            warehouseCode: ctx.defaultWarehouseCode,
            warehouseName: ctx.defaultWarehouseName,
            label: ctx.defaultWarehouseLabel.isNotEmpty
                ? ctx.defaultWarehouseLabel
                : ctx.defaultWarehouseName,
          );
        }
      });

      if (widget.restoreDraft && _draftUsername.isNotEmpty) {
        final draft = await TransactionDraftStorage.read(
          docType: TransactionDraftType.salesInvoice,
          tenantId: _draftTenantId,
          username: _draftUsername,
        );
        if (!mounted) return;
        if (draft != null) {
          setState(() => _applyDraft(draft));
          if (_step >= 1) {
            // Catalog is not persisted in draft — reload so resume isn't an empty search screen.
            await _loadCatalog();
          }
          // Customer items tab (same as purchase supplier items on resume).
          await _loadCustomerPreviousItems();
          if (_step >= 2) {
            await _loadPaymentTendersIfNeeded();
          }
        }
      }

      if (widget.seedBillingType != null ||
          widget.seedWalkIn != null ||
          widget.seedCustomer != null ||
          widget.seedWarehouse != null ||
          (widget.seedAddress ?? '').isNotEmpty ||
          (widget.seedOrderNo ?? '').isNotEmpty ||
          (widget.seedRemarks ?? '').isNotEmpty) {
        setState(() {
          if (widget.seedBillingType != null && widget.seedBillingType!.trim().isNotEmpty) {
            _billingType = widget.seedBillingType!.trim().toUpperCase();
          }
          if (widget.seedWalkIn != null) {
            _walkIn = widget.seedWalkIn!;
          }
          if (widget.seedCustomer != null) {
            _customer = widget.seedCustomer;
            _walkIn = false;
          }
          if (widget.seedWarehouse != null) {
            _headerWarehouse = widget.seedWarehouse;
          }
          if ((widget.seedAddress ?? '').trim().isNotEmpty) {
            _address.text = widget.seedAddress!.trim();
          }
          if ((widget.seedOrderNo ?? '').trim().isNotEmpty) {
            _orderNo.text = widget.seedOrderNo!.trim();
          }
          if ((widget.seedRemarks ?? '').trim().isNotEmpty) {
            _remarks.text = widget.seedRemarks!.trim();
          }
          if (_walkIn) {
            _customer = null;
            _billingType = 'CASH';
          }
        });
      }

      if (widget.seedAiCart.isNotEmpty && _lines.isEmpty) {
        for (final raw in widget.seedAiCart) {
          final code = '${raw['item_code'] ?? raw['itemCode'] ?? ''}'.trim();
          final qty = double.tryParse('${raw['qty'] ?? raw['quantity'] ?? 0}'.replaceAll(',', '')) ?? 0;
          if (code.isEmpty || qty <= 0) continue;
          final unit = '${raw['unit'] ?? raw['uom'] ?? 'PCS'}'.trim();
          final rate = double.tryParse('${raw['rate'] ?? raw['price'] ?? 0}'.replaceAll(',', '')) ?? 0;
          final discount =
              double.tryParse('${raw['discount'] ?? 0}'.replaceAll(',', '')) ?? 0;
          await _addLineFromRequest(
            code,
            SalesInvoiceItemAddRequest(
              uom: unit.isEmpty ? 'PCS' : unit,
              qty: qty,
              rate: rate,
              discount: discount < 0 ? 0 : discount,
            ),
          );
        }
        if (mounted && _lines.isNotEmpty) {
          setState(() => _step = 1);
        }
      }

      if (_features.warehouseEnabled &&
          (_headerWarehouse == null || _headerWarehouse!.warehouseId.isEmpty)) {
        final sole = await svc.soleWarehouseIfOnlyOne();
        if (!mounted) return;
        if (sole != null) {
          setState(() => _headerWarehouse = sole);
        }
      }

      if (mounted) setState(() => _loading = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _pickCustomer({VoidCallback? sheetRefresh}) async {
    final svc = context.read<SalesService>();
    final picked = await SalesCustomerPickerSheet.open(
      context,
      service: svc,
      billingType: _billingType,
    );
    if (picked == null || !mounted) return;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    SalesCustomerOption customer = picked;
    try {
      customer = await svc.fetchCustomerOutstanding(picked.code);
    } catch (_) {
      // Keep picker values if GL refresh fails.
    }

    if (mounted) Navigator.of(context, rootNavigator: true).pop();

    if (!mounted) return;
    setState(() {
      _walkIn = false;
      _customer = customer;
      // Keep document bill type; picker already scoped to it.
      if (customer.address.isNotEmpty) _address.text = customer.address;
    });
    sheetRefresh?.call();
    _loadCustomerPreviousItems();
  }

  Future<void> _refreshCustomerGlOutstanding() async {
    final c = _customer;
    if (c == null || c.code.isEmpty) return;
    try {
      final fresh = await context.read<SalesService>().fetchCustomerOutstanding(c.code);
      if (!mounted) return;
      setState(() {
        _customer = c.copyWith(
          currentCredit: fresh.currentCredit,
          outstanding: fresh.outstanding,
          creditLimit: fresh.creditLimit,
          billingType: fresh.billingType,
        );
        _billingType = fresh.billingType;
      });
      _scheduleDraftSave();
    } catch (_) {}
  }

  Future<void> _pickWarehouse({VoidCallback? sheetRefresh}) async {
    final svc = context.read<SalesService>();
    final picked = await showModalBottomSheet<SalesWarehouseOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _WarehousePickerSheet(service: svc),
    );
    if (picked == null || !mounted) return;
    setState(() => _headerWarehouse = picked);
    _scheduleDraftSave();
    sheetRefresh?.call();
    _loadCatalog();
    _loadCustomerPreviousItems();
  }

  Future<void> _loadCatalog() async {
    setState(() {
      _catalogLoading = true;
      _catalogError = null;
    });
    try {
      final svc = context.read<SalesService>();
      final catalog = await svc.searchCatalog(
        q: _catalogSearch.text.trim(),
        warehouseId: _headerWarehouse?.warehouseId ?? '',
        customerCode: _customer?.code ?? '',
      );
      if (!mounted) return;
      setState(() {
        _catalogItems = catalog.items;
        // Catalog flag is authoritative (Sales Accounts Configuration).
        if (catalog.minusBillingEnabled) {
          _features = _features.copyWith(minusBillingEnabled: true);
        }
        _catalogLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _catalogItems = [];
        _catalogLoading = false;
        _catalogError = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  Future<void> _loadCustomerPreviousItems() async {
    final code = _walkIn ? '' : (_customer?.code ?? '').trim();
    if (code.isEmpty || code == '0') {
      if (mounted) {
        setState(() {
          _customerItems = [];
          _customerItemsLoading = false;
          _customerItemsError = null;
        });
      }
      return;
    }
    setState(() {
      _customerItemsLoading = true;
      _customerItemsError = null;
    });
    try {
      final svc = context.read<SalesService>();
      final rows = await svc.listCustomerPreviousItems(
        customerCode: code,
        warehouseId: _headerWarehouse?.warehouseId ?? '',
      );
      if (!mounted) return;
      setState(() {
        _customerItems = rows;
        _customerItemsLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _customerItems = [];
        _customerItemsLoading = false;
        _customerItemsError = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  void _onCatalogSearch() {
    _catalogDebounce?.cancel();
    _catalogDebounce = Timer(const Duration(milliseconds: 350), _loadCatalog);
  }

  Future<void> _scanBarcode() async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const BarcodeScannerScreen(title: 'Scan item barcode')),
    );
    if (code == null || code.trim().isEmpty || !mounted) return;
    _catalogSearch.text = code.trim();
    await _loadCatalog();
    await _openItemDetailByCode(code.trim());
  }

  Future<void> _quickAddItem(SalesCatalogItem item) async {
    // Catalog already respects minus billing; allow Add for listed zero-stock items.
    final qty = await showModalBottomSheet<double>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => SalesInvoiceQuickQtySheet(
        itemCode: item.itemCode,
        itemName: item.itemName,
      ),
    );
    if (qty == null || qty <= 0 || !mounted) return;
    final uom = item.unit.isNotEmpty ? item.unit : 'PCS';
    await _addLineFromRequest(
      item.itemCode,
      SalesInvoiceItemAddRequest(uom: uom, qty: qty, rate: item.rate),
    );
  }

  Future<void> _openItemDetail(SalesCatalogItem item) async {
    final svc = context.read<SalesService>();
    final req = await Navigator.of(context).push<SalesInvoiceItemAddRequest>(
      MaterialPageRoute(
        builder: (_) => SalesInvoiceItemDetailScreen(
          catalogItem: item,
          service: svc,
          customerCode: _walkIn ? '' : (_customer?.code ?? ''),
          customerName: _walkIn ? '' : (_customer?.name ?? ''),
          allowAddWithoutStock: true,
        ),
      ),
    );
    if (req == null || !mounted) return;
    await _addLineFromRequest(item.itemCode, req);
  }

  Future<void> _openItemDetailByCode(String code) async {
    if (code.trim().isEmpty) return;
    SalesCatalogItem? catalogItem;
    for (final row in _catalogItems) {
      if (row.itemCode == code.trim()) {
        catalogItem = row;
        break;
      }
    }
    catalogItem ??= SalesCatalogItem(
      itemCode: code.trim(),
      itemName: '',
      unit: 'PCS',
      rate: 0,
      stock: 1,
    );
    await _openItemDetail(catalogItem);
  }

  Future<void> _addLineFromRequest(String itemCode, SalesInvoiceItemAddRequest req) async {
    final svc = context.read<SalesService>();
    try {
      final line = await _buildLineFromItem(
        svc,
        itemCode,
        uomOverride: req.uom,
        qty: req.qty,
        rateOverride: req.rate,
      );
      if (line == null || !mounted) return;
      line.discount = req.discount.clamp(0, line.rate).toDouble();
      setState(() {
        final idx = _lines.indexWhere(
          (l) =>
              l.itemCode == line.itemCode &&
              l.uom == line.uom &&
              l.warehouseId == line.warehouseId &&
              l.storageId == line.storageId &&
              l.lotId == line.lotId,
        );
        if (idx >= 0) {
          _lines[idx].qty += line.qty;
          if (line.discount > 0) {
            // Prefer the newly entered per-unit discount when re-adding.
            _lines[idx].discount = line.discount;
          }
          _clampLineDiscount(idx);
        } else {
          _lines.add(line.copyWithSlno(_lines.length + 1));
        }
      });
      _scheduleDraftSave();
      showAppSnackBar(
        context,
        'Added ${line.itemName.isNotEmpty ? line.itemName : line.itemCode}',
        duration: const Duration(milliseconds: 800),
      );
    } catch (e) {
      if (!mounted) return;
      showAppSnackBar(context, '$e');
    }
  }

  Future<_InvoiceLine?> _buildLineFromItem(
    SalesService svc,
    String query, {
    String? uomOverride,
    double qty = 1,
    double? rateOverride,
  }) async {
    final item = await svc.lookupItem(query);
    final uoms = await svc.getItemUoms(item.itemCode);
    final uom = uomOverride ??
        (uoms.isNotEmpty
            ? uoms.first.code
            : (item.baseUom.isNotEmpty ? item.baseUom : 'PCS'));
    final pricing = await svc.getUomPricing(item.itemCode, uom);
    var rate = rateOverride ?? (pricing.rate > 0 ? pricing.rate : item.retailPrice);
    var cost = pricing.costPrice > 0 ? pricing.costPrice : item.costPrice;
    var factor = pricing.conversionFactor > 0 ? pricing.conversionFactor : 1.0;
    var avgCost = pricing.averageCost > 0
        ? pricing.averageCost
        : (factor > 1.000001 && cost > 0 ? cost / factor : cost);

    String? whId;
    String? whCode;
    if (_features.warehouseEnabled) {
      final hw = _headerWarehouse;
      if (hw != null && hw.warehouseId.isNotEmpty) {
        whId = hw.warehouseId;
        whCode = hw.warehouseCode;
      } else if (item.defaultWarehouseId != null) {
        whId = '${item.defaultWarehouseId}';
      }
      if (whId == null || whId.isEmpty) {
        throw StateError('Select a warehouse on the header before adding items.');
      }
    }

    int? storageId;
    String? binCode;
    String? binName;
    if (_features.binTrackingEnabled && whId != null) {
      final bins = await svc.getItemBins(itemCode: item.itemCode, warehouseId: whId);
      SalesBinOption? pick;
      if (item.defaultBinStorageId != null) {
        for (final b in bins) {
          if (b.storageId == item.defaultBinStorageId) {
            pick = b;
            break;
          }
        }
      }
      pick ??= bins.isNotEmpty
          ? bins.reduce((a, b) => a.stock >= b.stock ? a : b)
          : null;
      if (pick == null && !_features.minusBillingEnabled) {
        throw StateError('No bin stock for item ${item.itemCode} at warehouse $whId.');
      }
      if (pick != null) {
        storageId = pick.storageId;
        binCode = pick.code;
        binName = pick.name;
      }
    }

    String? lotId;
    String? lotLabel;
    final needLot = _features.batchTrackingEnabled && item.batchTracked;
    if (needLot) {
      final lots = await svc.getBatchLots(item.itemCode);
      if (lots.isEmpty) {
        if (!_features.minusBillingEnabled) {
          throw StateError('No available batch/lot stock for item ${item.itemCode}.');
        }
      } else {
        if (!mounted) return null;
        final lot = await _pickLot(context, lots);
        if (lot == null) return null;
        lotId = lot.lotId;
        lotLabel = lot.label;
      }
    }

    return _InvoiceLine(
      slno: 0,
      itemCode: item.itemCode,
      itemName: item.itemName,
      uom: uom,
      qty: qty,
      rate: rate,
      cost: cost,
      averageCost: avgCost,
      conversionFactor: factor,
      availableUoms: uoms,
      warehouseId: whId,
      warehouseCode: whCode,
      storageId: storageId,
      binCode: binCode,
      binName: binName,
      lotId: lotId,
      lotLabel: lotLabel,
      batchTracked: item.batchTracked,
    );
  }

  Future<SalesLotOption?> _pickLot(BuildContext context, List<SalesLotOption> lots) {
    return showModalBottomSheet<SalesLotOption>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Select batch / lot', style: TextStyle(fontWeight: FontWeight.w700)),
              ),
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: lots.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final lot = lots[i];
                    return ListTile(
                      title: Text(lot.label),
                      subtitle: Text('Qty ${lot.qty.toStringAsFixed(2)}'),
                      onTap: () => Navigator.of(ctx).pop(lot),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _openLineOptions(int index) async {
    final line = _lines[index];
    final svc = context.read<SalesService>();
    final updated = await showModalBottomSheet<_InvoiceLine>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _LineOptionsSheet(
        line: line,
        service: svc,
        features: _features,
        headerWarehouseId: _headerWarehouse?.warehouseId,
      ),
    );
    if (updated == null || !mounted) return;
    setState(() => _lines[index] = updated.copyWithSlno(index + 1));
  }

  String? _validateLines() {
    if (_features.warehouseEnabled && (_headerWarehouse == null || _headerWarehouse!.warehouseId.isEmpty)) {
      return 'Select a warehouse (ERP requires warehouse when enabled).';
    }
    for (var i = 0; i < _lines.length; i++) {
      final l = _lines[i];
      final n = i + 1;
      if (_features.warehouseEnabled && (l.warehouseId == null || l.warehouseId!.isEmpty)) {
        return 'Line $n: warehouse is required.';
      }
      if (_features.binTrackingEnabled && (l.storageId == null || l.storageId! <= 0)) {
        return 'Line $n: bin is required.';
      }
      if (_features.batchTrackingEnabled && l.batchTracked && (l.lotId == null || l.lotId!.isEmpty)) {
        return 'Line $n: batch/lot is required.';
      }
    }
    return null;
  }

  Future<bool> _checkCreditBeforeSave() async {
    if (_billingType != 'CREDIT' || _customer == null) return true;
    final svc = context.read<SalesService>();
    final chk = await svc.checkCredit(
      customerCode: _customer!.code,
      netAmount: _netTotal,
      billingType: _billingType,
    );
    if (chk.ok) return true;
    if (!mounted) return false;
    final proceed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Credit limit exceeded'),
        content: Text(chk.error ?? 'This invoice exceeds the customer credit limit.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
        ],
      ),
    );
    return proceed == true;
  }

  void _ensurePaymentDefaults() {
    if (_billingType == 'CREDIT' || _paymentTenders.isEmpty) return;
    if (_paymentAmounts.isNotEmpty) return;
    setState(() {
      _paymentAmounts = {for (final t in _paymentTenders) t.tenderCode: 0.0};
    });
  }

  Future<void> _loadPaymentTendersIfNeeded() async {
    if (_billingType == 'CREDIT') return;
    if (_paymentTenders.isNotEmpty) {
      _ensurePaymentDefaults();
      return;
    }
    try {
      final rows = await context.read<SalesService>().listPaymentTenders();
      if (!mounted) return;
      setState(() => _paymentTenders = rows);
      _ensurePaymentDefaults();
    } catch (_) {
      if (!mounted) return;
      setState(() => _paymentTenders = List<SalesPaymentTender>.from(SalesPaymentTender.posDefaults));
      _ensurePaymentDefaults();
    }
  }

  Future<void> _submit() async {
    final headerErr = _validateHeader();
    if (headerErr != null) {
      showAppSnackBar(context, headerErr);
      setState(() => _step = 0);
      return;
    }
    if (_lines.isEmpty) {
      showAppSnackBar(context, 'Add at least one line item.');
      return;
    }
    final lineErr = _validateLines();
    if (lineErr != null) {
      showAppSnackBar(context, lineErr);
      return;
    }

    if (_billingType == 'CREDIT') {
      final ok = await _checkCreditBeforeSave();
      if (!ok) return;
    } else {
      final payErr = validateSalesPayment(amounts: _paymentAmounts, netTotal: _netTotal);
      if (payErr != null) {
        showAppSnackBar(context, payErr);
        return;
      }
    }

    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save sales invoice?',
      message: 'Save invoice $_billno for ${_netTotal.toStringAsFixed(2)}?',
      confirmLabel: 'Save invoice',
    );
    if (!confirmed || !mounted) return;

    setState(() => _submitting = true);
    try {
      final header = <String, dynamic>{
        'billno': _billno,
        'billdate': _billDate,
        'billtime': _billTime,
        'billtype': _billingType == 'CREDIT' ? 'R' : 'C',
        'customer_billing_type': _billingType,
        'walk_in': _walkIn,
        'customercode': _walkIn ? 0 : int.tryParse(_customer!.code) ?? _customer!.code,
        'customername': _walkIn ? 'Walk-in' : _customer!.name,
        'address': _address.text.trim(),
        'orderno': _orderNo.text.trim(),
        'remarks': _remarks.text.trim(),
        'sessioncode': 0,
      };
      if (_features.warehouseEnabled && _headerWarehouse != null) {
        header['warehouse_id'] = int.tryParse(_headerWarehouse!.warehouseId) ?? _headerWarehouse!.warehouseId;
        if (_headerWarehouse!.warehouseCode.isNotEmpty) {
          header['warehouse_code'] = _headerWarehouse!.warehouseCode;
        }
      }
      if (_billingType != 'CREDIT') {
        header.addAll(
          buildSalesPaymentHeaderFields(
            tenders: _paymentTenders,
            amounts: _paymentAmounts,
            netTotal: _netTotal,
          ),
        );
      }

      final lines = _lines.map((l) {
        final row = <String, dynamic>{
          'slno': l.slno,
          'item_code': l.itemCode,
          'item_name': l.itemName,
          'uom': l.uom,
          'quantity': l.qty,
          'rate': l.rate,
          'discount': l.discountTotal,
          'amount': l.amount,
          'base_qty': l.baseQty,
          'conversion_factor': l.conversionFactor,
          'conversionfactor': l.conversionFactor,
          'cost': l.cost,
          'costprice': l.cost,
          'average_cost': l.averageCost > 0 ? l.averageCost : l.cost,
          'averagecost': l.averageCost > 0 ? l.averageCost : l.cost,
        };
        if (l.lotId != null && l.lotId!.isNotEmpty) row['lot_id'] = l.lotId;
        final whId = int.tryParse(l.warehouseId ?? '') ?? 0;
        if (whId > 0) row['warehouse_id'] = whId;
        if (l.storageId != null && l.storageId! > 0) {
          row['storage_id'] = l.storageId;
          row['bin_storage_id'] = l.storageId;
          if (whId > 0) row['bin_loc_key'] = '$whId';
        }
        if (l.warehouseCode != null && l.warehouseCode!.isNotEmpty) row['store'] = l.warehouseCode;
        return row;
      }).toList();

      final result = await context.read<SalesService>().saveInvoice(header: header, lines: lines);
      if (!mounted) return;
      await _clearDraft();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => _InvoiceSavedDialog(
          result: result,
          orderNo: _orderNo.text.trim(),
          netTotal: _netTotal,
          customerName: _customer?.name ?? '',
        ),
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(),
        body: const Center(child: CircularProgressIndicator(color: _accent)),
      );
    }
    if (_loadError != null) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_loadError!, textAlign: TextAlign.center),
                const SizedBox(height: 16),
                FilledButton(onPressed: _load, child: const Text('Retry')),
              ],
            ),
          ),
        ),
      );
    }

    final isLast = _step >= 2;
    final rightLabel = isLast ? 'Save invoice' : 'Next';

    return Scaffold(
      backgroundColor: _bg,
      appBar: _appBar(),
      body: PopScope(
        canPop: _step <= 0,
        onPopInvokedWithResult: (didPop, result) {
          if (didPop) return;
          _handleWizardBack();
        },
        child: Column(
        children: [
          Expanded(
            child: switch (_step) {
              0 => SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                  child: _invoiceHeaderForm(),
                ),
              1 => _itemsSection(),
              _ => SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                  child: _stepReview(),
                ),
            },
          ),
          Container(
            color: Colors.white,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Divider(height: 1, color: Color(0xFFE8EBF3)),
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
                    child: Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: _submitting ? null : _handleWizardBack,
                            child: Text(_step == 0 ? 'Cancel' : 'Back'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          flex: 2,
                          child: FilledButton.icon(
                            style: FilledButton.styleFrom(backgroundColor: _accent),
                            onPressed: _submitting
                                ? null
                                : () async {
                                    if (_step == 0) {
                                      final err = _validateHeader();
                                      if (err != null) {
                                        showAppSnackBar(context, err);
                                        return;
                                      }
                                      setState(() => _step = 1);
                                      _scheduleDraftSave();
                                      _loadCatalog();
                                      _loadCustomerPreviousItems();
                                      if (!_walkIn && _customer != null) {
                                        _refreshCustomerGlOutstanding();
                                      }
                                      return;
                                    }
                                    if (_step == 1) {
                                      await _goToCheckoutStep();
                                      return;
                                    }
                                    await _submit();
                                  },
                            icon: _submitting
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : Icon(isLast ? Icons.check_circle_outline : Icons.arrow_forward_rounded),
                            label: Text(_submitting && isLast ? 'Saving…' : rightLabel),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
        ),
      ),
    );
  }

  PreferredSizeWidget _appBar() => AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: _submitting ? null : _handleWizardBack,
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Sales Invoice', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            if (_billno.isNotEmpty)
              Text(
                'Bill No. $_billno • ${_billDate.isEmpty ? '—' : _billDate}',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
              ),
          ],
        ),
      );

  Widget _readonlyRow(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 110, child: Text(label, style: TextStyle(fontSize: 13, color: Colors.grey.shade700))),
            Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
          ],
        ),
      );

  Widget _stepReview() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _docHeader(),
        const SizedBox(height: 12),
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _readonlyRow('Customer', _walkIn ? 'Walk-in (cash)' : (_customer?.name ?? '—')),
              _readonlyRow('Customer code', _walkIn ? '0' : (_customer?.code ?? '—')),
              _readonlyRow('Billing type', _billingType),
              if (_headerWarehouse != null) _readonlyRow('Warehouse', _headerWarehouse!.label),
              _readonlyRow('Order No.', _orderNo.text.trim().isEmpty ? '—' : _orderNo.text.trim()),
              if (_remarks.text.trim().isNotEmpty) _readonlyRow('Remarks', _remarks.text.trim()),
            ],
          ),
        ),
        const SizedBox(height: 12),
        if (_lineViews.isNotEmpty)
          _card(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  color: const Color(0xFFF0F2F7),
                  child: const Text('Line summary', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                ),
                for (var i = 0; i < _lineViews.length; i++) ...[
                  if (i > 0) const Divider(height: 1),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: 20,
                          child: Text('${_lineViews[i].slno}', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                        ),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(_lineViews[i].itemName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                              Text(
                                '${_lineViews[i].itemCode} • ${_lineViews[i].subtitle}',
                                style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                              ),
                            ],
                          ),
                        ),
                        Text(
                          _lineViews[i].discount > 0
                              ? '${_lineViews[i].qty.toStringAsFixed(_lineViews[i].qty == _lineViews[i].qty.roundToDouble() ? 0 : 2)} × ${_lineViews[i].rate.toStringAsFixed(2)} − ${_lineViews[i].discountTotal.toStringAsFixed(2)}'
                              : '${_lineViews[i].qty.toStringAsFixed(_lineViews[i].qty == _lineViews[i].qty.roundToDouble() ? 0 : 2)} × ${_lineViews[i].rate.toStringAsFixed(2)}',
                          style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
                        ),
                        const SizedBox(width: 8),
                        SizedBox(
                          width: 72,
                          child: Text(
                            _lineViews[i].amount.toStringAsFixed(2),
                            textAlign: TextAlign.right,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
                  child: Row(
                    children: [
                      Text('Subtotal', style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
                      const Spacer(),
                      Text(_grossTotal.toStringAsFixed(2), style: const TextStyle(fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
                if (_discountTotal > 0)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
                    child: Row(
                      children: [
                        Text('Discount', style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
                        const Spacer(),
                        Text(
                          '−${_discountTotal.toStringAsFixed(2)}',
                          style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFFC62828)),
                        ),
                      ],
                    ),
                  ),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    children: [
                      Text('${_lines.length} line(s)', style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
                      const Spacer(),
                      const Text('Net total', style: TextStyle(fontWeight: FontWeight.w600)),
                      const SizedBox(width: 12),
                      Text(
                        _netTotal.toStringAsFixed(2),
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        if (_billingType == 'CREDIT' && _customer != null) ...[
          const SizedBox(height: 10),
          _creditBanner(),
        ] else ...[
          const SizedBox(height: 12),
          _card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Payment',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
                const SizedBox(height: 10),
                SalesInvoicePaymentPanel(
                  netTotal: _netTotal,
                  tenders: _paymentTenders,
                  amounts: _paymentAmounts,
                  onChanged: (next) {
                    setState(() => _paymentAmounts = next);
                    _scheduleDraftSave();
                  },
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _card({required Widget child, EdgeInsetsGeometry? padding}) => Container(
        width: double.infinity,
        padding: padding ?? const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: _border),
        ),
        child: child,
      );

  Widget _docHeader() => _card(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _locationName.isNotEmpty ? _locationName : 'Sales Invoice',
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _walkIn
                        ? 'Walk-in cash sale'
                        : (_billingType == 'CREDIT' ? 'Credit sale' : 'Cash sale'),
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('Bill No.', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                Text('$_billno', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                const SizedBox(height: 6),
                Text(
                  _billDate.isEmpty ? '—' : '$_billDate  ${_billTime.isNotEmpty ? _billTime : ''}'.trim(),
                  style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
                ),
              ],
            ),
          ],
        ),
      );

  Widget _pickerField({
    required String label,
    required String value,
    required String hint,
    required IconData icon,
    required VoidCallback onTap,
    String? subtitle,
    Color iconColor = const Color(0xFF1565C0),
  }) =>
      InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(10),
                  color: Color.lerp(iconColor, Colors.white, 0.88)!,
                ),
                child: Icon(icon, size: 22, color: iconColor),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: TextStyle(fontSize: 11, color: iconColor.withValues(alpha: 0.75))),
                    const SizedBox(height: 2),
                    Text(
                      value.isNotEmpty ? value : hint,
                      style: TextStyle(
                        fontWeight: value.isNotEmpty ? FontWeight.w600 : FontWeight.w400,
                        color: value.isNotEmpty ? iconColor : Colors.grey.shade500,
                      ),
                    ),
                    if (subtitle != null && subtitle.isNotEmpty)
                      Text(subtitle, style: TextStyle(fontSize: 11, color: iconColor.withValues(alpha: 0.65))),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, size: 20, color: iconColor.withValues(alpha: 0.45)),
            ],
          ),
        ),
      );

  InputDecoration _fieldDec(String label, {String? hint}) => InputDecoration(
        labelText: label,
        hintText: hint,
        border: const OutlineInputBorder(),
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      );

  Widget _creditBanner() {
    if (_customer == null) return const SizedBox.shrink();
    final c = _customer!;
    final isCredit = c.billingType == 'CREDIT';
    final projected = isCredit ? c.currentCredit + _netTotal : 0.0;
    final over = isCredit && c.creditLimit > 0 && projected > c.creditLimit;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: over ? const Color(0xFFFFF5F6) : const Color(0xFFF0F7FF),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: over ? const Color(0xFFE63946) : const Color(0xFFBBDEFB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            isCredit ? 'Credit customer' : 'Cash customer',
            style: TextStyle(fontWeight: FontWeight.w700, color: over ? const Color(0xFFE63946) : const Color(0xFF1565C0)),
          ),
          const SizedBox(height: 4),
          Text(
            isCredit
                ? '${c.creditLimitLabel} • GL outstanding ${c.currentCredit.toStringAsFixed(2)}'
                : 'GL outstanding ${c.displayOutstanding.toStringAsFixed(2)}',
            style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
          ),
          if (isCredit && _netTotal > 0)
            Text(
              'After this bill: ${projected.toStringAsFixed(2)}${over ? ' — over limit' : ''}',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: over ? const Color(0xFFE63946) : null),
            ),
        ],
      ),
    );
  }

  Widget _billingTypeSelector({VoidCallback? sheetRefresh}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Billing type', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'CASH', label: Text('Cash'), icon: Icon(Icons.payments_outlined, size: 18)),
            ButtonSegment(value: 'CREDIT', label: Text('Credit'), icon: Icon(Icons.credit_score_outlined, size: 18)),
          ],
          selected: {_billingType},
          onSelectionChanged: (s) => _setBillingType(s.first, sheetRefresh: sheetRefresh),
        ),
        const SizedBox(height: 10),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _walkIn,
          onChanged: _billingType == 'CREDIT'
              ? null
              : (v) => _setWalkIn(v, sheetRefresh: sheetRefresh),
          title: const Text('Walk-in cash sale', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
          subtitle: Text(
            _walkIn
                ? 'No customer — same as POS walk-in (customer code 0, bill type C).'
                : 'Enable for counter / walk-in customers without a customer master record.',
            style: TextStyle(fontSize: 12, color: Colors.grey.shade600, height: 1.3),
          ),
        ),
      ],
    );
  }

  Widget _invoiceHeaderForm({VoidCallback? sheetRefresh}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _docHeader(),
        const SizedBox(height: 12),
        _card(child: _billingTypeSelector(sheetRefresh: sheetRefresh)),
        const SizedBox(height: 12),
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (!_walkIn)
                _pickerField(
                  label: _billingType == 'CREDIT' ? 'Customer *' : 'Customer',
                  value: _customer?.name ?? '',
                  hint: _billingType == 'CREDIT' ? 'Select credit customer' : 'Select customer (optional for cash)',
                  subtitle: _customer == null
                      ? null
                      : 'Code ${_customer!.code} • Master: ${_customer!.billingType}',
                  icon: Icons.person_search_outlined,
                  iconColor: const Color(0xFF1565C0),
                  onTap: () => _pickCustomer(sheetRefresh: sheetRefresh),
                )
              else
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const CircleAvatar(
                    backgroundColor: Color(0xFFE8F5E9),
                    child: Icon(Icons.storefront_outlined, color: Color(0xFF2E7D32)),
                  ),
                  title: const Text('Walk-in customer', style: TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: const Text('Customer code 0 • Cash invoice'),
                  trailing: TextButton(
                    onPressed: () => _setWalkIn(false, sheetRefresh: sheetRefresh),
                    child: const Text('Change'),
                  ),
                ),
              if (_customer != null && !_walkIn) ...[
                const Divider(height: 1),
                Padding(padding: const EdgeInsets.only(top: 10), child: _creditBanner()),
              ],
              if (!_walkIn) ...[
                const Divider(height: 24),
                TextField(controller: _address, decoration: _fieldDec('Delivery address'), maxLines: 2),
              ],
            ],
          ),
        ),
        if (_features.warehouseEnabled) ...[
          const SizedBox(height: 12),
          _card(
            child: _pickerField(
              label: 'Warehouse *',
              value: _headerWarehouse?.label.isNotEmpty == true
                  ? _headerWarehouse!.label
                  : (_headerWarehouse?.warehouseName ?? ''),
              hint: 'Select warehouse',
              subtitle: _headerWarehouse == null ? 'Required for stock allocation' : 'ID ${_headerWarehouse!.warehouseId}',
              icon: Icons.warehouse_outlined,
              iconColor: const Color(0xFFE65100),
              onTap: () => _pickWarehouse(sheetRefresh: sheetRefresh),
            ),
          ),
        ],
        const SizedBox(height: 12),
        _card(
          child: Column(
            children: [
              TextField(
                controller: _orderNo,
                decoration: _fieldDec(
                  (_features.orderNoMandatory && !_walkIn) ? 'Order No. *' : 'Order No. (optional)',
                  hint: _walkIn
                      ? 'Leave blank for walk-in'
                      : (_features.orderNoMandatory ? 'Customer PO / reference' : 'Optional PO / reference'),
                ),
              ),
              const SizedBox(height: 12),
              TextField(controller: _remarks, decoration: _fieldDec('Remarks'), maxLines: 2),
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _handleWizardBack() async {
    if (_submitting) return;
    if (_step <= 0) {
      await _persistDraft();
      if (mounted) Navigator.of(context).pop();
      return;
    }
    if (_step == 2) {
      setState(() => _step = 1);
      _scheduleDraftSave();
      return;
    }
    setState(() => _step -= 1);
    _scheduleDraftSave();
  }

  Future<bool> _goToCheckoutStep() async {
    if (_lines.isEmpty) {
      showAppSnackBar(context, 'Add at least one item.');
      return false;
    }
    final err = _validateLines();
    if (err != null) {
      showAppSnackBar(context, err);
      return false;
    }
    if (_billingType == 'CREDIT' && _customer != null) {
      final svc = context.read<SalesService>();
      final chk = await svc.checkCredit(
        customerCode: _customer!.code,
        netAmount: _netTotal,
        billingType: _billingType,
      );
      if (!chk.ok && mounted) {
        showAppSnackBar(context, chk.error ?? 'Credit limit exceeded');
        return false;
      }
    }
    await _loadPaymentTendersIfNeeded();
    if (!mounted) return false;
    setState(() => _step = 2);
    _scheduleDraftSave();
    return true;
  }

  Future<void> _openCart() async {
    final proceedToCheckout = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (context) => SalesInvoiceCartScreen(
          getLines: () => _lineViews,
          getNetTotal: () => _netTotal,
          onLineEdit: _openLineOptions,
          onLineDelete: _removeLine,
          onQtyChanged: (index, qty) => setState(() {
            _lines[index].qty = qty;
            _clampLineDiscount(index);
          }),
          onRateChanged: (index, rate) => setState(() {
            _lines[index].rate = rate;
            _clampLineDiscount(index);
          }),
          onDiscountChanged: (index, discount) => setState(() {
            _lines[index].discount = discount;
            _clampLineDiscount(index);
          }),
          billNo: _billno,
          billDate: _billDate,
        ),
      ),
    );
    if (!mounted) return;
    setState(() {});
    if (proceedToCheckout == true) {
      await _goToCheckoutStep();
    }
  }

  Widget _itemsSection() {
    final whLabel = _headerWarehouse != null
        ? 'Stock from: ${_headerWarehouse!.label.isNotEmpty ? _headerWarehouse!.label : _headerWarehouse!.warehouseName}'
        : (_features.warehouseEnabled ? '' : 'All sellable items');
    return SalesInvoiceLinesStep(
      searchController: _catalogSearch,
      items: _catalogItems,
      lines: _lineViews,
      loading: _catalogLoading,
      errorMessage: _catalogError,
      warehouseLabel: whLabel,
      showWarehouseHint: _features.warehouseEnabled &&
          (_headerWarehouse == null || _headerWarehouse!.warehouseId.isEmpty),
      netTotal: _netTotal,
      onSearch: _onCatalogSearch,
      onScan: _scanBarcode,
      onRefresh: _loadCatalog,
      onItemTap: _openItemDetail,
      onQuickAdd: _quickAddItem,
      onOpenCart: _openCart,
      // Catalog only returns sellable rows for current minus-billing setting.
      allowAddWithoutStock: true,
      creditBanner: _billingType == 'CREDIT' && _customer != null ? _creditBanner() : null,
      showCustomerItemsTab: !_walkIn && (_customer?.code.isNotEmpty ?? false),
      customerItems: _customerItems,
      customerItemsLoading: _customerItemsLoading,
      customerItemsError: _customerItemsError,
      onRefreshCustomerItems: _loadCustomerPreviousItems,
    );
  }
}

class _LineOptionsSheet extends StatefulWidget {
  const _LineOptionsSheet({
    required this.line,
    required this.service,
    required this.features,
    this.headerWarehouseId,
  });

  final _InvoiceLine line;
  final SalesService service;
  final SalesInvoiceFeatures features;
  final String? headerWarehouseId;

  @override
  State<_LineOptionsSheet> createState() => _LineOptionsSheetState();
}

class _LineOptionsSheetState extends State<_LineOptionsSheet> {
  late String _uom;
  late List<SalesUomOption> _uoms;
  SalesBinOption? _bin;
  SalesLotOption? _lot;
  List<SalesBinOption> _bins = [];
  List<SalesLotOption> _lots = [];
  bool _loading = true;
  double _rate = 0;
  double _cost = 0;
  double _averageCost = 0;
  double _factor = 1;

  @override
  void initState() {
    super.initState();
    _uom = widget.line.uom;
    _uoms = widget.line.availableUoms;
    _rate = widget.line.rate;
    _cost = widget.line.cost;
    _averageCost = widget.line.averageCost;
    _factor = widget.line.conversionFactor;
    if (widget.line.storageId != null) {
      _bin = SalesBinOption(
        storageId: widget.line.storageId!,
        code: widget.line.binCode ?? '',
        name: widget.line.binName ?? '',
      );
    }
    if (widget.line.lotId != null) {
      _lot = SalesLotOption(lotId: widget.line.lotId!, batchNo: widget.line.lotLabel ?? '');
    }
    _load();
  }

  Future<void> _load() async {
    try {
      if (_uoms.isEmpty) {
        _uoms = await widget.service.getItemUoms(widget.line.itemCode);
      }
      final wh = widget.line.warehouseId ?? widget.headerWarehouseId ?? '';
      if (widget.features.binTrackingEnabled && wh.isNotEmpty) {
        _bins = await widget.service.getItemBins(itemCode: widget.line.itemCode, warehouseId: wh);
      }
      if (widget.features.batchTrackingEnabled && widget.line.batchTracked) {
        _lots = await widget.service.getBatchLots(widget.line.itemCode);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _onUomChanged(String? v) async {
    if (v == null || v.isEmpty) return;
    final p = await widget.service.getUomPricing(widget.line.itemCode, v);
    setState(() {
      _uom = v;
      _rate = p.rate > 0 ? p.rate : _rate;
      _cost = p.costPrice > 0 ? p.costPrice : _cost;
      _factor = p.conversionFactor > 0 ? p.conversionFactor : 1.0;
      _averageCost = p.averageCost > 0
          ? p.averageCost
          : (_factor > 1.000001 && _cost > 0 ? _cost / _factor : _cost);
    });
  }

  void _apply() {
    final l = widget.line;
    Navigator.of(context).pop(
      _InvoiceLine(
        slno: l.slno,
        itemCode: l.itemCode,
        itemName: l.itemName,
        uom: _uom,
        qty: l.qty,
        rate: _rate,
        discount: l.discount,
        cost: _cost,
        averageCost: _averageCost,
        conversionFactor: _factor,
        availableUoms: _uoms,
        warehouseId: l.warehouseId,
        warehouseCode: l.warehouseCode,
        storageId: _bin?.storageId,
        binCode: _bin?.code,
        binName: _bin?.name,
        lotId: _lot?.lotId,
        lotLabel: _lot?.label,
        batchTracked: l.batchTracked,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.of(context).size.height * 0.55;
    return SizedBox(
      height: h,
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(widget.line.itemName, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                  Text('Code ${widget.line.itemCode}', style: TextStyle(color: Colors.grey.shade600)),
                  const SizedBox(height: 16),
                  if (_uoms.length > 1)
                    DropdownButtonFormField<String>(
                      value: _uom,
                      decoration: const InputDecoration(labelText: 'UOM', border: OutlineInputBorder()),
                      items: _uoms.map((u) => DropdownMenuItem(value: u.code, child: Text(u.code))).toList(),
                      onChanged: _onUomChanged,
                    )
                  else
                    _readonly('UOM', _uom),
                  if (widget.features.binTrackingEnabled && _bins.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<int>(
                      value: _bin?.storageId,
                      decoration: const InputDecoration(labelText: 'Bin', border: OutlineInputBorder()),
                      items: _bins
                          .map(
                            (b) => DropdownMenuItem(
                              value: b.storageId,
                              child: Text('${b.code} (${b.stock.toStringAsFixed(1)} qty)'),
                            ),
                          )
                          .toList(),
                      onChanged: (v) => setState(() {
                        _bin = _bins.firstWhere((b) => b.storageId == v);
                      }),
                    ),
                  ],
                  if (widget.features.batchTrackingEnabled && widget.line.batchTracked && _lots.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      value: _lot?.lotId,
                      decoration: const InputDecoration(labelText: 'Batch / Lot', border: OutlineInputBorder()),
                      items: _lots
                          .map((lot) => DropdownMenuItem(value: lot.lotId, child: Text(lot.label)))
                          .toList(),
                      onChanged: (v) => setState(() {
                        _lot = _lots.firstWhere((lot) => lot.lotId == v);
                      }),
                    ),
                  ],
                  const Spacer(),
                  FilledButton(onPressed: _apply, child: const Text('Apply')),
                ],
              ),
            ),
    );
  }

  Widget _readonly(String label, String value) => Row(
        children: [
          Text('$label: ', style: const TextStyle(fontWeight: FontWeight.w600)),
          Text(value),
        ],
      );
}

class _InvoiceSavedDialog extends StatefulWidget {
  const _InvoiceSavedDialog({
    required this.result,
    this.orderNo = '',
    this.netTotal = 0,
    this.customerName = '',
  });

  final SalesSaveResult result;
  final String orderNo;
  final double netTotal;
  final String customerName;

  @override
  State<_InvoiceSavedDialog> createState() => _InvoiceSavedDialogState();
}

class _InvoiceSavedDialogState extends State<_InvoiceSavedDialog> {
  static const _accent = Color(0xFF1565C0);
  static const _titleColor = Color(0xFF262C50);

  bool _pdfBusy = false;
  bool _hasPrinter = false;
  String? _pdfError;

  SalesSaveResult get result => widget.result;
  String get orderNo => widget.orderNo;
  double get netTotal => widget.netTotal;
  String get customerName => widget.customerName;

  @override
  void initState() {
    super.initState();
    _loadPrinter();
  }

  Future<void> _loadPrinter() async {
    final printer = await PrinterStorage.readSelected();
    if (!mounted) return;
    setState(() => _hasPrinter = printer != null && !printer.isEmpty);
  }

  String? get _reassignmentNote {
    if (result.billnoReassigned) {
      return 'Bill number was reassigned to #${result.billno}.';
    }
    final msg = result.message?.trim() ?? '';
    if (msg.isEmpty) return null;
    final savedAs = RegExp(r'Saved as bill\s+(\S+)', caseSensitive: false).firstMatch(msg);
    if (savedAs != null) {
      final assigned = (savedAs.group(1) ?? '').trim();
      if (assigned.isNotEmpty && assigned != result.billno) {
        return 'Bill number was reassigned to #$assigned.';
      }
    }
    if (msg.toLowerCase().contains('already taken') || msg.toLowerCase().contains('not reserved')) {
      return null;
    }
    return msg;
  }

  Future<void> _downloadPdf() async {
    if (_pdfBusy || result.billno.trim().isEmpty) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final bytes = await context.read<SalesService>().downloadInvoicePdf(result.billno);
      final dir = await getTemporaryDirectory();
      final safe = result.billno.replaceAll(RegExp(r'[^\w\-]+'), '_');
      final file = File('${dir.path}/invoice_$safe.pdf');
      await file.writeAsBytes(bytes, flush: true);
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        setState(() {
          _pdfError = opened.message.isNotEmpty
              ? opened.message
              : 'PDF saved. Open it from Files if it did not open automatically.';
        });
        showAppSnackBar(context, 'PDF saved to ${file.path}');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _pdfError = handleApiError(context, e, authenticatedContext: true));
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final posted = result.glPosted || result.accountsPosted;
    final voucher = result.glVoucherNo?.trim() ?? '';
    final note = _reassignmentNote;

    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 28),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(22, 28, 22, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: const Color(0xFFE8F5E9),
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF2E7D32).withValues(alpha: 0.12),
                    blurRadius: 16,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: const Icon(Icons.check_rounded, size: 40, color: Color(0xFF2E7D32)),
            ),
            const SizedBox(height: 18),
            const Text(
              'Invoice saved',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: _titleColor),
            ),
            const SizedBox(height: 6),
            Text(
              'Bill #${result.billno}',
              style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: _accent, height: 1.1),
            ),
            if (orderNo.isNotEmpty || customerName.isNotEmpty || netTotal > 0) ...[
              const SizedBox(height: 16),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFF6F7FC),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  children: [
                    if (orderNo.isNotEmpty) _summaryRow('Order', orderNo),
                    if (customerName.isNotEmpty) ...[
                      if (orderNo.isNotEmpty) const SizedBox(height: 8),
                      _summaryRow('Customer', customerName),
                    ],
                    if (netTotal > 0) ...[
                      if (orderNo.isNotEmpty || customerName.isNotEmpty) const SizedBox(height: 8),
                      _summaryRow('Total', netTotal.toStringAsFixed(2), bold: true),
                    ],
                  ],
                ),
              ),
            ],
            if (note != null) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF8E1),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFFFE082)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.info_outline_rounded, size: 18, color: Color(0xFFF57C00)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        note,
                        style: const TextStyle(fontSize: 12.5, color: Color(0xFF6D4C00), height: 1.35),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (posted) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFE3F2FD),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFFBBDEFB)),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.account_balance_wallet_outlined, size: 20, color: _accent),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Posted to accounts',
                            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: _titleColor),
                          ),
                          Text(
                            voucher.isNotEmpty ? 'GL voucher $voucher' : 'Receivable, sales & inventory updated',
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade700, height: 1.3),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (!_hasPrinter)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Text(
                  'No Bluetooth printer connected — download the invoice PDF instead.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade700, height: 1.3),
                ),
              ),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _pdfBusy ? null : _downloadPdf,
                icon: _pdfBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: _accent),
                      )
                    : const Icon(Icons.picture_as_pdf_outlined),
                label: Text(
                  _pdfBusy ? 'Preparing PDF…' : 'Download / view PDF',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: _accent,
                  side: const BorderSide(color: Color(0xFFBBDEFB)),
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            if (_pdfError != null) ...[
              const SizedBox(height: 8),
              Text(
                _pdfError!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12, color: Color(0xFFC62828), height: 1.3),
              ),
            ],
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _pdfBusy ? null : () => Navigator.of(context).pop(),
                style: FilledButton.styleFrom(
                  backgroundColor: _accent,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: const Text('Done', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _summaryRow(String label, String value, {bool bold = false}) {
    return Row(
      children: [
        Expanded(
          child: Text(label, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: 13,
            fontWeight: bold ? FontWeight.w800 : FontWeight.w600,
            color: _titleColor,
          ),
        ),
      ],
    );
  }
}

class _WarehousePickerSheet extends StatefulWidget {
  const _WarehousePickerSheet({required this.service});
  final SalesService service;

  @override
  State<_WarehousePickerSheet> createState() => _WarehousePickerSheetState();
}

class _WarehousePickerSheetState extends State<_WarehousePickerSheet> {
  final _search = TextEditingController();
  List<SalesWarehouseOption> _rows = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _fetch('');
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _fetch(String q) async {
    setState(() => _loading = true);
    try {
      final rows = await widget.service.searchWarehouses(q: q);
      if (mounted) setState(() => _rows = rows);
    } catch (_) {
      if (mounted) setState(() => _rows = []);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.of(context).size.height * 0.6;
    return SizedBox(
      height: h,
      child: Column(
        children: [
          const SizedBox(height: 8),
          Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2))),
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search warehouse',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              ),
              onSubmitted: _fetch,
              onChanged: (v) {
                if (v.length >= 1 || v.isEmpty) _fetch(v);
              },
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView.separated(
                    itemCount: _rows.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final w = _rows[i];
                      return ListTile(
                        title: Text(w.label.isNotEmpty ? w.label : w.warehouseName),
                        subtitle: Text('ID ${w.warehouseId}${w.warehouseCode.isNotEmpty ? ' • ${w.warehouseCode}' : ''}'),
                        onTap: () => Navigator.of(context).pop(w),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
