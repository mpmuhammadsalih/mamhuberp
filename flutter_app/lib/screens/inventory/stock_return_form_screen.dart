import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../core/ui/confirm_save.dart';
import '../../providers/auth_provider.dart';
import '../../services/purchase_order_service.dart';
import '../../services/stock_return_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/hardware_barcode_capture.dart';
import '../../widgets/numeric_text_field.dart';
import '../barcode_scanner_screen.dart';
import 'inventory_transaction_draft.dart';
import 'purchase_catalog_tabs.dart';
import 'purchase_order_cart_screen.dart';
import '../../core/theme/app_theme.dart';

class _RtLine {
  _RtLine({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    this.discount = 0,
    this.barcode = '',
    this.factor = 1,
    this.warehouseId,
    this.warehouseCode,
  });

  final String itemCode;
  final String itemName;
  String uom;
  double qty;
  double rate;
  double discount;
  String barcode;
  double factor;
  final String? warehouseId;
  String? warehouseCode;

  double get amount => (qty * rate) - discount;
}

class _RtLineEditResult {
  const _RtLineEditResult({
    required this.qty,
    required this.rate,
    required this.uom,
    this.barcode = '',
    this.factor = 1,
  });
  final double qty;
  final double rate;
  final String uom;
  final String barcode;
  final double factor;
}

class StockReturnFormScreen extends StatefulWidget {
  const StockReturnFormScreen({super.key, this.editReturnNo, this.restoreDraft = false});

  /// When set, loads that draft return for editing.
  final String? editReturnNo;

  /// When true, restores the in-session draft after open context loads.
  final bool restoreDraft;

  @override
  State<StockReturnFormScreen> createState() => _StockReturnFormScreenState();
}

class _StockReturnFormScreenState extends State<StockReturnFormScreen> with WidgetsBindingObserver {
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  int _step = 0;
  bool _loading = true;
  bool _submitting = false;
  String? _loadError;
  Object? _loadErrorCause;

  /// Same 3 options as GRN: `pr_draft` | `pr_only` | `pr_posting`
  String _saveMode = 'pr_draft';

  bool get _isEditing => (widget.editReturnNo ?? '').trim().isNotEmpty;

  String _returnNo = '';
  String _returnDate = '';
  bool _warehouseEnabled = false;

  PurchaseSupplierOption? _supplier;
  PurchaseWarehouseOption? _warehouse;
  final _remarks = TextEditingController();

  final _catalogSearch = TextEditingController();
  final _catalogSearchFocus = FocusNode();
  final _hwBarcode = TextEditingController();
  final _hwBarcodeFocus = FocusNode();
  final List<_RtLine> _lines = [];
  List<PurchaseCatalogItem> _catalogItems = [];
  bool _catalogLoading = false;
  String? _catalogError;
  Timer? _catalogDebounce;
  List<PurchaseCatalogItem> _supplierItems = [];
  bool _supplierItemsLoading = false;
  String? _supplierItemsError;
  String? _supplierItemsLoadedFor;
  Timer? _draftDebounce;
  String _draftTenantId = '';
  String _draftUsername = '';
  bool _draftCleared = false;
  bool _barcodeLookupBusy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _remarks.addListener(_scheduleDraftSave);
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
    _remarks.removeListener(_scheduleDraftSave);
    _catalogDebounce?.cancel();
    _draftDebounce?.cancel();
    _remarks.dispose();
    _catalogSearch.dispose();
    _catalogSearchFocus.dispose();
    _hwBarcode.dispose();
    _hwBarcodeFocus.dispose();
    super.dispose();
  }

  void _scheduleDraftSave() {
    if (_isEditing || _draftCleared || _loading || _submitting) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), _persistDraft);
  }

  bool get _hasMeaningfulDraft => InventoryTransactionDraft.isMeaningful(
        partyCode: _supplier?.code,
        partyName: _supplier?.name,
        remarks: _remarks.text,
        lines: _lines,
      );

  Future<void> _persistDraft() async {
    if (_isEditing || _draftCleared || _submitting) return;
    if (!_hasMeaningfulDraft) return;
    if (_draftUsername.isEmpty) return;
    final draft = <String, dynamic>{
      'step': _step,
      'save_mode': _saveMode,
      'remarks': _remarks.text,
      'supplier': _supplier == null
          ? null
          : {'code': _supplier!.code, 'name': _supplier!.name},
      'warehouse': _warehouse == null
          ? null
          : {
              'warehouse_id': _warehouse!.warehouseId,
              'warehouse_code': _warehouse!.warehouseCode,
              'warehouse_name': _warehouse!.warehouseName,
              'label': _warehouse!.label,
            },
      'party_name': (_supplier?.name.isNotEmpty == true ? _supplier!.name : _supplier?.code) ?? '',
      'lines': _lines
          .map(
            (l) => <String, dynamic>{
              'itemCode': l.itemCode,
              'itemName': l.itemName,
              'uom': l.uom,
              'qty': l.qty,
              'rate': l.rate,
              'discount': l.discount,
              'barcode': l.barcode,
              'factor': l.factor,
              'warehouseId': l.warehouseId,
              'warehouseCode': l.warehouseCode,
            },
          )
          .toList(),
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.purchaseReturn,
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
      docType: TransactionDraftType.purchaseReturn,
      tenantId: _draftTenantId,
      username: _draftUsername,
    );
  }

  void _applyDraft(Map<String, dynamic> draft) {
    final linesRaw = (draft['lines'] as List?) ?? const [];
    final lines = <_RtLine>[];
    for (var i = 0; i < linesRaw.length; i++) {
      final raw = linesRaw[i];
      if (raw is! Map) continue;
      final m = Map<String, dynamic>.from(raw);
      final itemCode = '${m['itemCode'] ?? m['item_code'] ?? ''}'.trim();
      if (itemCode.isEmpty) continue;
      final whId = '${m['warehouseId'] ?? m['warehouse_id'] ?? ''}'.trim();
      final whCode = '${m['warehouseCode'] ?? m['warehouse_code'] ?? ''}'.trim();
      final uom = '${m['uom'] ?? 'NOS'}'.trim();
      final factor = InventoryTransactionDraft.numOf(m['factor']);
      lines.add(
        _RtLine(
          itemCode: itemCode,
          itemName: '${m['itemName'] ?? m['item_name'] ?? ''}'.trim(),
          uom: uom.isEmpty ? 'NOS' : uom,
          qty: InventoryTransactionDraft.numOf(m['qty']),
          rate: InventoryTransactionDraft.numOf(m['rate']),
          discount: InventoryTransactionDraft.numOf(m['discount']),
          barcode: '${m['barcode'] ?? ''}'.trim(),
          factor: factor > 0 ? factor : 1,
          warehouseId: whId.isEmpty ? null : whId,
          warehouseCode: whCode.isEmpty ? null : whCode,
        ),
      );
    }

    _remarks.text = '${draft['remarks'] ?? ''}';

    final supRaw = draft['supplier'];
    if (supRaw is Map) {
      final code = '${supRaw['code'] ?? ''}'.trim();
      if (code.isNotEmpty) {
        _supplier = PurchaseSupplierOption(
          code: code,
          name: '${supRaw['name'] ?? ''}'.trim(),
        );
      }
    }

    final whRaw = draft['warehouse'];
    if (whRaw is Map) {
      final whId = '${whRaw['warehouse_id'] ?? ''}'.trim();
      if (whId.isNotEmpty) {
        _warehouse = PurchaseWarehouseOption(
          warehouseId: whId,
          warehouseCode: '${whRaw['warehouse_code'] ?? ''}'.trim(),
          warehouseName: '${whRaw['warehouse_name'] ?? ''}'.trim(),
          label: '${whRaw['label'] ?? ''}'.trim(),
        );
      }
    }

    _lines
      ..clear()
      ..addAll(lines);
    final step = InventoryTransactionDraft.intOf(draft['step']);
    _step = step.clamp(0, 2);
    final mode = '${draft['save_mode'] ?? ''}'.trim();
    if (mode == 'pr_draft' || mode == 'pr_only' || mode == 'pr_posting') {
      _saveMode = mode;
    } else if (mode == 'grn_draft') {
      _saveMode = 'pr_draft';
    } else if (mode == 'grn_only') {
      _saveMode = 'pr_only';
    } else if (mode == 'grn_invoice_posting') {
      _saveMode = 'pr_posting';
    }
  }

  String _saveModeLabel() {
    switch (_saveMode) {
      case 'pr_posting':
        return 'Post stock + accounts';
      case 'pr_only':
        return 'Post stock';
      default:
        return 'Save draft';
    }
  }

  double get _netTotal => _lines.fold(0.0, (s, l) => s + l.amount);

  List<PurchaseOrderCartLineView> get _cartLineViews => _lines
      .map(
        (l) => PurchaseOrderCartLineView(
          itemCode: l.itemCode,
          itemName: l.itemName,
          uom: l.uom,
          qty: l.qty,
          rate: l.rate,
          amount: l.amount,
          barcode: l.barcode,
        ),
      )
      .toList();

  String _fmtQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  String _fmtStock(double s) {
    if (s == s.roundToDouble()) return s.round().toString();
    return s.toStringAsFixed(2);
  }

  void _requestHwBarcodeFocus() {
    if (_step != 1 || !mounted) return;
    // Don't steal focus from the visible search field (causes IME / dispose races).
    if (_catalogSearchFocus.hasFocus) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _step != 1 || _catalogSearchFocus.hasFocus) return;
      if (!_hwBarcodeFocus.hasFocus) _hwBarcodeFocus.requestFocus();
    });
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _loadErrorCause = null;
    });
    try {
      final rtSvc = context.read<StockReturnService>();
      final poSvc = context.read<PurchaseOrderService>();
      final open = await rtSvc.getReturnOpen();
      if (!mounted) return;

      if (_isEditing) {
        final detail = await rtSvc.getReturnDetail(widget.editReturnNo!.trim());
        if (!mounted) return;
        if (!detail.canEdit) {
          setState(() {
            _loadError = detail.isCanceled
                ? 'This Purchase Return is canceled and cannot be edited.'
                : detail.isPosted
                    ? 'This Purchase Return is posted and cannot be edited.'
                    : 'This Purchase Return cannot be edited.';
            _loading = false;
          });
          return;
        }
        await _applyEditDetail(detail, open: open, poSvc: poSvc);
        return;
      }

      setState(() {
        _returnNo = open.returnNo;
        _returnDate = open.returnDate;
        _warehouseEnabled = open.warehouseEnabled;
        if (open.defaultWarehouseId != null && open.defaultWarehouseId!.isNotEmpty) {
          _warehouse = PurchaseWarehouseOption(
            warehouseId: open.defaultWarehouseId!,
            warehouseCode: open.defaultWarehouseCode,
            warehouseName: open.defaultWarehouseName,
            label: open.defaultWarehouseLabel.isNotEmpty
                ? open.defaultWarehouseLabel
                : open.defaultWarehouseName,
          );
        }
      });

      if (widget.restoreDraft && _draftUsername.isNotEmpty) {
        final draft = await TransactionDraftStorage.read(
          docType: TransactionDraftType.purchaseReturn,
          tenantId: _draftTenantId,
          username: _draftUsername,
        );
        if (!mounted) return;
        if (draft != null) {
          setState(() => _applyDraft(draft));
        }
      }

      if (_warehouseEnabled && (_warehouse == null || _warehouse!.warehouseId.isEmpty)) {
        final sole = await context.read<PurchaseOrderService>().soleWarehouseIfOnlyOne();
        if (!mounted) return;
        if (sole != null) {
          setState(() => _warehouse = sole);
        }
      }

      if (mounted) {
        setState(() => _loading = false);
        if (_step >= 1) {
          _loadCatalog();
          _loadSupplierItems();
          if (_step == 1) _requestHwBarcodeFocus();
        } else {
          _loadSupplierItems();
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadErrorCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _applyEditDetail(
    StockReturnDetail detail, {
    required StockReturnOpenContext open,
    required PurchaseOrderService poSvc,
  }) async {
    final s = detail.summary;
    PurchaseWarehouseOption? wh;
    String? lineWhId;
    for (final ln in detail.lines) {
      final id = ln.warehouseId;
      if (id != null && id.isNotEmpty) {
        lineWhId = id;
        break;
      }
    }
    final whId = lineWhId;
    if (whId != null && whId.isNotEmpty) {
      wh = PurchaseWarehouseOption(
        warehouseId: whId,
        label: whId,
      );
      try {
        final rows = await poSvc.searchWarehouses(q: whId, limit: 40);
        if (!mounted) return;
        for (final w in rows) {
          if (w.warehouseId == whId || w.warehouseCode == whId) {
            wh = w;
            break;
          }
        }
      } catch (_) {
        // Keep minimal warehouse from line.
      }
    } else if (open.defaultWarehouseId != null && open.defaultWarehouseId!.isNotEmpty) {
      wh = PurchaseWarehouseOption(
        warehouseId: open.defaultWarehouseId!,
        warehouseCode: open.defaultWarehouseCode,
        warehouseName: open.defaultWarehouseName,
        label: open.defaultWarehouseLabel.isNotEmpty
            ? open.defaultWarehouseLabel
            : open.defaultWarehouseName,
      );
    }

    final lines = detail.lines
        .map(
          (ln) => _RtLine(
            itemCode: ln.itemCode,
            itemName: ln.itemName,
            uom: ln.uom,
            qty: ln.qty,
            rate: ln.rate,
            discount: ln.discount,
            barcode: ln.barcode,
            factor: ln.factor,
            warehouseId: ln.warehouseId ?? wh?.warehouseId,
            warehouseCode: ln.warehouseCode ?? wh?.warehouseCode,
          ),
        )
        .toList();

    setState(() {
      _returnNo = s.returnNo.isNotEmpty ? s.returnNo : open.returnNo;
      _returnDate = open.returnDate.isNotEmpty ? open.returnDate : s.returnDate;
      _warehouseEnabled = open.warehouseEnabled;
      _supplier = PurchaseSupplierOption(
        code: s.supplierCode,
        name: s.supplierName.isNotEmpty ? s.supplierName : s.supplierCode,
      );
      _warehouse = wh;
      _remarks.text = detail.remarks;
      _lines
        ..clear()
        ..addAll(lines);
      _loading = false;
    });
    if (!mounted) return;
    _loadCatalog();
    _loadSupplierItems();
  }

  String? _validateHeader() {
    if (_supplier == null || _supplier!.code.trim().isEmpty) {
      return 'Select a supplier.';
    }
    if (_warehouseEnabled && (_warehouse == null || _warehouse!.warehouseId.isEmpty)) {
      return 'Select a warehouse.';
    }
    return null;
  }

  Future<void> _pickSupplier() async {
    final picked = await showModalBottomSheet<PurchaseSupplierOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _SupplierPickerSheet(service: context.read<PurchaseOrderService>()),
    );
    if (picked == null || !mounted) return;
    setState(() => _supplier = picked);
    _scheduleDraftSave();
    _loadSupplierItems(force: true);
  }

  Future<void> _pickWarehouse() async {
    final picked = await showModalBottomSheet<PurchaseWarehouseOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _WarehousePickerSheet(service: context.read<PurchaseOrderService>()),
    );
    if (picked == null || !mounted) return;
    setState(() => _warehouse = picked);
    _scheduleDraftSave();
  }

  void _scheduleCatalogSearch() {
    _catalogDebounce?.cancel();
    _catalogDebounce = Timer(const Duration(milliseconds: 350), _loadCatalog);
  }

  Future<void> _loadSupplierItems({bool force = false}) async {
    final code = (_supplier?.code ?? '').trim();
    if (code.isEmpty || code == '0') {
      if (mounted) {
        setState(() {
          _supplierItems = [];
          _supplierItemsLoading = false;
          _supplierItemsError = null;
          _supplierItemsLoadedFor = null;
        });
      }
      return;
    }
    if (!force && _supplierItemsLoadedFor == code && _supplierItems.isNotEmpty) {
      return;
    }
    setState(() {
      _supplierItemsLoading = true;
      _supplierItemsError = null;
    });
    try {
      final rows = await context.read<PurchaseOrderService>().listSupplierItems(
            supplierCode: code,
          );
      if (!mounted) return;
      setState(() {
        _supplierItems = rows;
        _supplierItemsLoading = false;
        _supplierItemsLoadedFor = code;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _supplierItems = [];
        _supplierItemsLoading = false;
        _supplierItemsError = handleApiError(context, e, authenticatedContext: true);
        _supplierItemsLoadedFor = code;
      });
    }
  }

  Future<void> _loadCatalog() async {
    final q = _catalogSearch.text.trim();
    setState(() {
      _catalogLoading = true;
      _catalogError = null;
    });
    try {
      // Full location catalog — do not filter by supplier (ITEMMASTER.SUPCODE is sparse).
      final items = await context.read<PurchaseOrderService>().searchCatalog(q: q);
      if (!mounted) return;
      setState(() {
        _catalogItems = items;
        _catalogLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _catalogLoading = false;
        _catalogError = handleApiError(context, e, authenticatedContext: true);
        _catalogItems = [];
      });
    }
  }

  Future<_RtLineEditResult?> _showLineEditDialog({
    required String itemName,
    required String itemCode,
    required String uom,
    required String barcode,
    required double currentStock,
    required double initialQty,
    required double initialRate,
    required String confirmLabel,
  }) {
    return showDialog<_RtLineEditResult>(
      context: context,
      builder: (ctx) => _LineEditDialog(
        service: context.read<PurchaseOrderService>(),
        itemName: itemName,
        itemCode: itemCode,
        initialUom: uom,
        initialBarcode: barcode,
        currentStock: currentStock,
        initialQty: initialQty,
        initialRate: initialRate,
        confirmLabel: confirmLabel,
      ),
    );
  }

  Future<void> _addCatalogItem(PurchaseCatalogItem item) async {
    _hwBarcodeFocus.unfocus();
    _catalogSearchFocus.unfocus();

    final seedUom = item.uom;
    final existingIdx = _lines.indexWhere(
      (l) => l.itemCode == item.itemCode && l.uom.toUpperCase() == seedUom.toUpperCase(),
    );
    final existing = existingIdx >= 0 ? _lines[existingIdx] : null;

    final edited = await _showLineEditDialog(
      itemName: item.itemName.isNotEmpty ? item.itemName : item.itemCode,
      itemCode: item.itemCode,
      uom: existing?.uom ?? item.uom,
      barcode: existing?.barcode ?? item.barcode,
      currentStock: item.currentStock,
      initialQty: existing?.qty ?? 1,
      initialRate: existing?.rate ?? item.displayCostPrice,
      confirmLabel: existing != null ? 'Update cart' : 'Add to cart',
    );
    if (!mounted || edited == null || edited.qty <= 0) return;

    final matchIdx = _lines.indexWhere(
      (l) => l.itemCode == item.itemCode && l.uom.toUpperCase() == edited.uom.toUpperCase(),
    );

    setState(() {
      if (matchIdx >= 0) {
        _lines[matchIdx].qty = edited.qty;
        _lines[matchIdx].rate = edited.rate;
        _lines[matchIdx].uom = edited.uom;
        _lines[matchIdx].barcode = edited.barcode;
        _lines[matchIdx].factor = edited.factor;
      } else if (existingIdx >= 0) {
        // UOM changed on an existing cart row — update that row in place.
        _lines[existingIdx].qty = edited.qty;
        _lines[existingIdx].rate = edited.rate;
        _lines[existingIdx].uom = edited.uom;
        _lines[existingIdx].barcode = edited.barcode;
        _lines[existingIdx].factor = edited.factor;
      } else {
        _lines.add(
          _RtLine(
            itemCode: item.itemCode,
            itemName: item.itemName,
            uom: edited.uom,
            qty: edited.qty,
            rate: edited.rate,
            barcode: edited.barcode,
            factor: edited.factor,
            warehouseId: _warehouse?.warehouseId,
            warehouseCode: _warehouse?.warehouseCode,
          ),
        );
      }
    });
    _scheduleDraftSave();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${matchIdx >= 0 || existingIdx >= 0 ? 'Updated' : 'Added'} '
          '${_fmtQty(edited.qty)} ${edited.uom} · ${item.itemCode}',
        ),
      ),
    );
    _requestHwBarcodeFocus();
  }

  Future<void> _editCartLine(int index) async {
    if (index < 0 || index >= _lines.length) return;
    final line = _lines[index];
    PurchaseCatalogItem? catalog;
    for (final it in _catalogItems) {
      if (it.itemCode == line.itemCode) {
        catalog = it;
        break;
      }
    }
    final edited = await _showLineEditDialog(
      itemName: line.itemName.isNotEmpty ? line.itemName : line.itemCode,
      itemCode: line.itemCode,
      uom: line.uom,
      barcode: line.barcode,
      currentStock: catalog?.currentStock ?? 0,
      initialQty: line.qty,
      initialRate: line.rate,
      confirmLabel: 'Update cart',
    );
    if (edited == null) return;
    line.qty = edited.qty;
    line.rate = edited.rate;
    line.uom = edited.uom;
    line.barcode = edited.barcode;
    line.factor = edited.factor;
    _scheduleDraftSave();
  }

  Future<void> _openCart() async {
    _hwBarcodeFocus.unfocus();
    _catalogSearchFocus.unfocus();
    final proceed = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => PurchaseOrderCartScreen(
          getLines: () => _cartLineViews,
          getNetTotal: () => _netTotal,
          // Mutate only — setState on this route while cart is open dirty-builds wrong scope.
          onLineDelete: (index) {
            if (index >= 0 && index < _lines.length) _lines.removeAt(index);
          },
          onQtyChanged: (index, qty) {
            if (index >= 0 && index < _lines.length) _lines[index].qty = qty;
          },
          onRateChanged: (index, rate) {
            if (index >= 0 && index < _lines.length) _lines[index].rate = rate;
          },
          onLineEdit: _editCartLine,
          lpono: _returnNo,
          lpoDate: _returnDate,
        ),
      ),
    );
    if (!mounted) return;
    setState(() {});
    _scheduleDraftSave();
    if (proceed == true) {
      await _goToReviewStep();
    } else {
      _requestHwBarcodeFocus();
    }
  }

  Future<void> _scanBarcode() async {
    _hwBarcodeFocus.unfocus();
    _catalogSearchFocus.unfocus();
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const BarcodeScannerScreen(title: 'Scan item barcode')),
    );
    if (code == null || code.trim().isEmpty || !mounted) return;
    await _handleBarcodeLookup(code.trim());
  }

  Future<void> _handleBarcodeLookup(String raw) async {
    final code = raw.trim();
    if (code.isEmpty || _barcodeLookupBusy || !mounted) return;
    _barcodeLookupBusy = true;
    if (_catalogSearch.text != code) {
      _catalogSearch.value = TextEditingValue(
        text: code,
        selection: TextSelection.collapsed(offset: code.length),
      );
    }
    setState(() {
      _catalogLoading = true;
      _catalogError = null;
    });
    try {
      final items = await context.read<PurchaseOrderService>().searchCatalog(q: code, limit: 80);
      if (!mounted) return;
      setState(() {
        _catalogItems = items;
        _catalogLoading = false;
      });
      final upper = code.toUpperCase();
      PurchaseCatalogItem? match;
      for (final it in items) {
        if (it.barcode.toUpperCase() == upper || it.itemCode.toUpperCase() == upper) {
          match = it;
          break;
        }
      }
      match ??= items.length == 1 ? items.first : null;
      if (match != null) {
        await _addCatalogItem(match);
      } else if (items.isEmpty && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No item found for barcode $code')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _catalogLoading = false;
        _catalogError = handleApiError(context, e, authenticatedContext: true);
        _catalogItems = [];
      });
    } finally {
      _barcodeLookupBusy = false;
      if (mounted) _requestHwBarcodeFocus();
    }
  }

  Future<void> _handleWizardBack() async {
    if (_submitting) return;
    if (_step <= 0) {
      await _persistDraft();
      if (mounted) Navigator.of(context).maybePop();
      return;
    }
    setState(() => _step -= 1);
    _scheduleDraftSave();
  }

  Future<void> _goToReviewStep() async {
    if (_lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add at least one item.')),
      );
      return;
    }
    setState(() => _step = 2);
    _scheduleDraftSave();
  }

  Future<void> _submit() async {
    final err = _validateHeader();
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
      setState(() => _step = 0);
      _scheduleDraftSave();
      return;
    }
    if (_lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add at least one item.')),
      );
      setState(() => _step = 1);
      _scheduleDraftSave();
      return;
    }

    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save purchase return?',
      message: '${_saveModeLabel()}: return $_returnNo with ${_lines.length} line(s)?',
      confirmLabel: _saveModeLabel(),
    );
    if (!confirmed || !mounted) return;

    setState(() => _submitting = true);
    try {
      final header = <String, dynamic>{
        'return_no': _returnNo,
        'return_date': _returnDate,
        'supplier_code': _supplier!.code,
        'remarks': _remarks.text.trim(),
        'warehouse_id': _warehouse?.warehouseId,
        'save_mode': _saveMode,
      };
      final lines = _lines
          .map(
            (l) => <String, dynamic>{
              'item_code': l.itemCode,
              'quantity': l.qty,
              'rate': l.rate,
              'discount': l.discount,
              'amount': l.amount,
              'uom': l.uom,
              'barcode': l.barcode,
              'factor': l.factor,
              'conversionfactor': l.factor,
              'warehouse_id': l.warehouseId ?? _warehouse?.warehouseId,
              if ((l.warehouseCode ?? _warehouse?.warehouseCode ?? '').isNotEmpty)
                'warehouse_code': l.warehouseCode ?? _warehouse?.warehouseCode,
              if ((l.warehouseCode ?? _warehouse?.warehouseCode ?? '').isNotEmpty)
                'store': l.warehouseCode ?? _warehouse?.warehouseCode,
            },
          )
          .toList();

      final result = await context.read<StockReturnService>().saveReturn(
            header: header,
            lines: lines,
            saveMode: _saveMode,
          );
      if (!mounted) return;
      await _clearDraft();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => _RtSavedDialog(
          result: result,
          supplierName: _supplier?.name ?? '',
          netTotal: _netTotal,
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
        body: ApiErrorCenter(message: _loadError!, error: _loadErrorCause, onRetry: _load),
      );
    }

    final isLast = _step >= 2;
    final rightLabel = isLast
        ? (_isEditing ? 'Update return' : _saveModeLabel())
        : 'Next';

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
            _stepHeader(),
            Expanded(
              child: switch (_step) {
                0 => SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                    child: _detailsStep(),
                  ),
                1 => _itemsStep(),
                _ => SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                    child: _reviewStep(),
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
                                          ScaffoldMessenger.of(context).showSnackBar(
                                            SnackBar(content: Text(err)),
                                          );
                                          return;
                                        }
                                        setState(() => _step = 1);
                                        _scheduleDraftSave();
                                        _loadCatalog();
                                        _loadSupplierItems();
                                        _requestHwBarcodeFocus();
                                        return;
                                      }
                                      if (_step == 1) {
                                        await _goToReviewStep();
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
            Text(
              _isEditing ? 'Edit Purchase Return' : 'Purchase Return',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            if (_returnNo.isNotEmpty)
              Text(
                'PR-$_returnNo • ${_returnDate.isEmpty ? '—' : _returnDate}',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
              ),
          ],
        ),
      );

  Widget _stepHeader() {
    const labels = ['Details', 'Items', 'Review'];
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
      child: Row(
        children: [
          for (var i = 0; i < labels.length; i++) ...[
            if (i > 0) Expanded(child: Divider(color: i <= _step ? _accent : Colors.grey.shade300)),
            Column(
              children: [
                CircleAvatar(
                  radius: 12,
                  backgroundColor: i <= _step ? _accent : Colors.grey.shade300,
                  child: Text(
                    '${i + 1}',
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  labels[i],
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: i == _step ? FontWeight.w700 : FontWeight.w500,
                    color: i == _step ? _accent : Colors.grey.shade600,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
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

  Widget _pickerField({
    required String label,
    required String value,
    required String hint,
    required IconData icon,
    required VoidCallback onTap,
    String? subtitle,
  }) =>
      InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                    const SizedBox(height: 2),
                    Text(
                      value.isNotEmpty ? value : hint,
                      style: TextStyle(
                        fontWeight: value.isNotEmpty ? FontWeight.w600 : FontWeight.w400,
                        color: value.isNotEmpty ? const Color(0xFF262C50) : Colors.grey.shade500,
                      ),
                    ),
                    if (subtitle != null && subtitle.isNotEmpty)
                      Text(subtitle, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                  ],
                ),
              ),
              Icon(icon, size: 20, color: Colors.grey.shade600),
            ],
          ),
        ),
      );

  Widget _detailsStep() {
    final supplierLabel = _supplier == null
        ? ''
        : (_supplier!.name.isNotEmpty ? _supplier!.name : _supplier!.code);
    final whLabel = _warehouse == null
        ? ''
        : (_warehouse!.label.isNotEmpty
            ? _warehouse!.label
            : (_warehouse!.warehouseName.isNotEmpty
                ? _warehouse!.warehouseName
                : _warehouse!.warehouseId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _pickerField(
                label: 'Supplier *',
                value: supplierLabel,
                hint: 'Select supplier',
                icon: Icons.storefront_outlined,
                onTap: _pickSupplier,
                subtitle: _supplier?.code.isNotEmpty == true ? 'Code ${_supplier!.code}' : null,
              ),
              if (_warehouseEnabled) ...[
                const Divider(height: 1),
                _pickerField(
                  label: 'Warehouse *',
                  value: whLabel,
                  hint: 'Select warehouse',
                  icon: Icons.warehouse_outlined,
                  onTap: _pickWarehouse,
                ),
              ],
              const Divider(height: 1),
              const SizedBox(height: 8),
              TextField(
                controller: _remarks,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: 'Remarks',
                  border: const OutlineInputBorder(),
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                  hintStyle: TextStyle(color: Colors.grey.shade500),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _itemsStep() {
    return Column(
      children: [
        HardwareBarcodeCapture(
          focusNode: _hwBarcodeFocus,
          controller: _hwBarcode,
          onScan: _handleBarcodeLookup,
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
          child: TextField(
            controller: _catalogSearch,
            focusNode: _catalogSearchFocus,
            decoration: InputDecoration(
              hintText: 'Search name, code or barcode…',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_catalogSearch.text.isNotEmpty)
                    IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: () {
                        _catalogSearch.clear();
                        setState(() {});
                        _loadCatalog();
                        _requestHwBarcodeFocus();
                      },
                    ),
                  IconButton(
                    icon: Icon(Icons.qr_code_scanner_rounded, color: Colors.grey.shade700),
                    tooltip: 'Scan barcode',
                    onPressed: _scanBarcode,
                  ),
                ],
              ),
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              isDense: true,
            ),
            onChanged: (_) {
              setState(() {});
              _scheduleCatalogSearch();
            },
            onSubmitted: (_) => _loadCatalog(),
          ),
        ),
        if (_lines.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Material(
              color: const Color(0xFFE3F2FD),
              borderRadius: BorderRadius.circular(12),
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: _openCart,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  child: Row(
                    children: [
                      const Icon(Icons.shopping_cart_outlined, color: _accent, size: 22),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          '${_lines.length} in cart · ${_netTotal.toStringAsFixed(2)}',
                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: Color(0xFF0D47A1)),
                        ),
                      ),
                      Text(
                        'Edit qty / price',
                        style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: Colors.grey.shade800),
                      ),
                      const Icon(Icons.chevron_right_rounded, color: _accent),
                    ],
                  ),
                ),
              ),
            ),
          ),
        Expanded(
          child: PurchaseCatalogTabsBody(
            showSupplierTab: (_supplier?.code.trim().isNotEmpty ?? false),
            items: _catalogItems,
            supplierItems: _supplierItems,
            itemsLoading: _catalogLoading,
            supplierItemsLoading: _supplierItemsLoading,
            itemsError: _catalogError,
            supplierItemsError: _supplierItemsError,
            onRetryItems: _loadCatalog,
            onRetrySupplierItems: () => _loadSupplierItems(force: true),
            searchQuery: _catalogSearch.text,
            itemBuilder: (_, item) => _catalogTile(item),
          ),
        ),
      ],
    );
  }

  Widget _catalogTile(PurchaseCatalogItem item) {
    final name = item.itemName.isNotEmpty ? item.itemName : item.itemCode;
    final inCart = _lines.any((l) => l.itemCode == item.itemCode);
    final stockColor = item.currentStock > 0 ? const Color(0xFF16A34A) : const Color(0xFFDC2626);
    final history = purchaseSupplierHistoryLine(item);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: inCart ? const Color(0xFF90CAF9) : const Color(0xFFE8EAED)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: () => _addCatalogItem(item),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      [
                        item.itemCode,
                        item.uom,
                        if (item.barcode.isNotEmpty) item.barcode,
                      ].join(' · '),
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                    const SizedBox(height: 4),
                    purchaseCatalogAvgCostLine(item),
                    if (history != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        history,
                        style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: Colors.grey.shade700,
                        ),
                      ),
                    ],
                    const SizedBox(height: 6),
                    Text(
                      'Stock ${_fmtStock(item.currentStock)}',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: stockColor),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  purchaseCatalogCostPriceColumn(item),
                  const SizedBox(height: 4),
                  Icon(
                    inCart ? Icons.shopping_cart : Icons.add_circle_outline,
                    color: _accent,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

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

  Widget _reviewStep() {
    final supplierLabel = _supplier == null
        ? '—'
        : (_supplier!.name.isNotEmpty ? _supplier!.name : _supplier!.code);
    final whLabel = _warehouse == null
        ? '—'
        : (_warehouse!.label.isNotEmpty
            ? _warehouse!.label
            : (_warehouse!.warehouseName.isNotEmpty
                ? _warehouse!.warehouseName
                : _warehouse!.warehouseId));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _readonlyRow('PR No.', _returnNo.isEmpty ? '—' : _returnNo),
              _readonlyRow('Date', _returnDate.isEmpty ? '—' : _returnDate),
              _readonlyRow('Supplier', supplierLabel),
              if (_supplier?.code.isNotEmpty == true) _readonlyRow('Supplier code', _supplier!.code),
              if (_warehouseEnabled) _readonlyRow('Warehouse', whLabel),
              if (_remarks.text.trim().isNotEmpty) _readonlyRow('Remarks', _remarks.text.trim()),
            ],
          ),
        ),
        const SizedBox(height: 12),
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
              for (var i = 0; i < _lines.length; i++) ...[
                if (i > 0) const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 20,
                        child: Text('${i + 1}', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _lines[i].itemName.isNotEmpty ? _lines[i].itemName : _lines[i].itemCode,
                              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                            ),
                            Text(
                              '${_lines[i].itemCode} • ${_lines[i].uom}',
                              style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        '${_fmtQty(_lines[i].qty)} × ${_lines[i].rate.toStringAsFixed(2)}',
                        style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 72,
                        child: Text(
                          _lines[i].amount.toStringAsFixed(2),
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
        const SizedBox(height: 12),
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Save as', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
              RadioListTile<String>(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Draft (no stock posting)'),
                subtitle: const Text('Save and post later'),
                value: 'pr_draft',
                groupValue: _saveMode,
                onChanged: (v) {
                  setState(() => _saveMode = v ?? 'pr_draft');
                  _scheduleDraftSave();
                },
              ),
              RadioListTile<String>(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Approve & post stock'),
                subtitle: const Text('Updates warehouse stock / item journal'),
                value: 'pr_only',
                groupValue: _saveMode,
                onChanged: (v) {
                  setState(() => _saveMode = v ?? 'pr_only');
                  _scheduleDraftSave();
                },
              ),
              RadioListTile<String>(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Post stock + accounts'),
                subtitle: const Text('Stock + purchase return / AP (ERP)'),
                value: 'pr_posting',
                groupValue: _saveMode,
                onChanged: (v) {
                  setState(() => _saveMode = v ?? 'pr_posting');
                  _scheduleDraftSave();
                },
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _LineEditDialog extends StatefulWidget {
  const _LineEditDialog({
    required this.service,
    required this.itemName,
    required this.itemCode,
    required this.initialUom,
    required this.initialBarcode,
    required this.currentStock,
    required this.initialQty,
    required this.initialRate,
    required this.confirmLabel,
  });

  final PurchaseOrderService service;
  final String itemName;
  final String itemCode;
  final String initialUom;
  final String initialBarcode;
  final double currentStock;
  final double initialQty;
  final double initialRate;
  final String confirmLabel;

  @override
  State<_LineEditDialog> createState() => _LineEditDialogState();
}

class _LineEditDialogState extends State<_LineEditDialog> {
  late final TextEditingController _qty;
  late final TextEditingController _rate;
  List<PurchaseUomOption> _uoms = [];
  late String _uom;
  late String _barcode;
  bool _loadingUoms = true;
  String? _uomError;

  @override
  void initState() {
    super.initState();
    final q = widget.initialQty;
    _qty = TextEditingController(
      text: q == q.roundToDouble() ? q.round().toString() : q.toStringAsFixed(2),
    );
    _rate = TextEditingController(text: widget.initialRate.toStringAsFixed(2));
    _uom = widget.initialUom.isNotEmpty ? widget.initialUom : 'NOS';
    _barcode = widget.initialBarcode;
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadUoms());
  }

  @override
  void dispose() {
    _qty.dispose();
    _rate.dispose();
    super.dispose();
  }

  String _fmtStock(double s) {
    if (s == s.roundToDouble()) return s.round().toString();
    return s.toStringAsFixed(2);
  }

  String _fmtFactor(double f) {
    final v = f > 0 ? f : 1;
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(3);
  }

  PurchaseUomOption? get _selectedUom {
    for (final u in _uoms) {
      if (u.uom.toUpperCase() == _uom.toUpperCase()) return u;
    }
    return _uoms.isNotEmpty ? _uoms.first : null;
  }

  Future<void> _loadUoms() async {
    setState(() {
      _loadingUoms = true;
      _uomError = null;
    });
    try {
      final rows = await widget.service.getItemUoms(widget.itemCode);
      if (!mounted) return;
      var list = rows;
      if (list.isEmpty) {
        list = [
          PurchaseUomOption(uom: _uom, rate: widget.initialRate, barcode: _barcode),
        ];
      }
      final match = list.where((u) => u.uom.toUpperCase() == _uom.toUpperCase());
      final selected = match.isNotEmpty ? match.first : list.first;
      setState(() {
        _uoms = list;
        _uom = selected.uom;
        _barcode = selected.barcode.isNotEmpty ? selected.barcode : _barcode;
        final editingCart = widget.confirmLabel.toLowerCase().contains('update');
        if (selected.rate > 0 && (!editingCart || widget.initialRate <= 0)) {
          _rate.text = selected.rate.toStringAsFixed(2);
        }
        _loadingUoms = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingUoms = false;
        _uomError = 'Could not load UOMs';
        _uoms = [
          PurchaseUomOption(uom: _uom, rate: widget.initialRate, barcode: _barcode),
        ];
      });
    }
  }

  void _applyUomCost(PurchaseUomOption opt) {
    final rateText = opt.rate.toStringAsFixed(2);
    _rate.value = TextEditingValue(
      text: rateText,
      selection: TextSelection.collapsed(offset: rateText.length),
    );
    if (opt.barcode.isNotEmpty) {
      _barcode = opt.barcode;
    }
  }

  void _onUomChanged(String? value) {
    if (value == null || value.isEmpty) return;
    PurchaseUomOption? opt;
    for (final u in _uoms) {
      if (u.uom.toUpperCase() == value.toUpperCase()) {
        opt = u;
        break;
      }
    }
    setState(() {
      _uom = value;
      if (opt != null) {
        _applyUomCost(opt);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.itemName, maxLines: 2, overflow: TextOverflow.ellipsis),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            widget.itemCode,
            style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
          ),
          const SizedBox(height: 4),
          Text(
            'Stock ${_fmtStock(widget.currentStock)}'
            '${_barcode.isNotEmpty ? '  ·  Barcode $_barcode' : ''}',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
          ),
          if (_uomError != null) ...[
            const SizedBox(height: 8),
            Text(_uomError!, style: const TextStyle(fontSize: 12, color: Color(0xFFC62828))),
          ],
          const SizedBox(height: 14),
          if (_loadingUoms)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))),
            )
          else ...[
            DropdownButtonFormField<String>(
              key: ValueKey('uom-$_uom-${_uoms.length}'),
              initialValue: _uoms.any((u) => u.uom == _uom)
                  ? _uom
                  : (_uoms.isNotEmpty ? _uoms.first.uom : _uom),
              decoration: const InputDecoration(
                labelText: 'UOM',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              items: _uoms
                  .map(
                    (u) => DropdownMenuItem(
                      value: u.uom,
                      child: Text(
                        '${u.uom} · ${u.rate.toStringAsFixed(2)} · ×${_fmtFactor(u.factor)}',
                      ),
                    ),
                  )
                  .toList(),
              onChanged: _uoms.isEmpty ? null : _onUomChanged,
            ),
            const SizedBox(height: 6),
            Text(
              'Conversion factor: ${_fmtFactor(_selectedUom?.factor ?? 1)}'
              '${(_selectedUom?.factor ?? 1) == 1 ? ' (ITEMMASTER base)' : ''}',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
            ),
          ],
          const SizedBox(height: 12),
          NumericTextField(
            controller: _qty,
            autofocus: true,
            selectAllOnFocus: true,
            labelText: 'Quantity',
            textInputAction: TextInputAction.next,
          ),
          const SizedBox(height: 12),
          NumericTextField(
            controller: _rate,
            selectAllOnFocus: true,
            labelText: 'Purchase rate',
            textInputAction: TextInputAction.done,
            helperText: 'Updates when UOM changes; you can override',
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1565C0)),
          onPressed: _loadingUoms
              ? null
              : () {
                  final q = double.tryParse(_qty.text.trim().replaceAll(',', '')) ?? 0;
                  final r = double.tryParse(_rate.text.trim().replaceAll(',', '')) ?? -1;
                  if (q <= 0) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Enter a quantity greater than zero.')),
                    );
                    return;
                  }
                  if (r < 0) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Enter a valid purchase rate.')),
                    );
                    return;
                  }
                  Navigator.pop(
                    context,
                    _RtLineEditResult(
                      qty: q,
                      rate: r,
                      uom: _uom,
                      barcode: _barcode,
                      factor: _selectedUom?.factor ?? 1,
                    ),
                  );
                },
          child: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}

class _SupplierPickerSheet extends StatefulWidget {
  const _SupplierPickerSheet({required this.service});

  final PurchaseOrderService service;

  @override
  State<_SupplierPickerSheet> createState() => _SupplierPickerSheetState();
}

class _SupplierPickerSheetState extends State<_SupplierPickerSheet> {
  static const _accent = Color(0xFF1565C0);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  List<PurchaseSupplierOption> _rows = [];

  @override
  void initState() {
    super.initState();
    _fetch('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _schedule(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _fetch(q.trim()));
  }

  Future<void> _fetch(String q) async {
    setState(() => _loading = true);
    try {
      final rows = await widget.service.searchSuppliers(q: q);
      if (mounted) setState(() => _rows = rows);
    } catch (_) {
      if (mounted) setState(() => _rows = []);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 12),
          const Text('Select supplier', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 12),
          TextField(
            controller: _search,
            autofocus: true,
            decoration: InputDecoration(
              hintText: 'Search name or code',
              prefixIcon: const Icon(Icons.search, size: 20),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              isDense: true,
            ),
            onChanged: _schedule,
            onSubmitted: _fetch,
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: CircularProgressIndicator(color: _accent)),
            )
          else if (_rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(child: Text('No suppliers found.', style: TextStyle(color: Colors.grey.shade600))),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.45),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final s = _rows[i];
                  final name = s.name.isNotEmpty ? s.name : s.code;
                  return ListTile(
                    onTap: () => Navigator.pop(context, s),
                    title: Text(name, style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text('Code ${s.code}'),
                    trailing: const Icon(Icons.chevron_right_rounded),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _WarehousePickerSheet extends StatefulWidget {
  const _WarehousePickerSheet({required this.service});

  final PurchaseOrderService service;

  @override
  State<_WarehousePickerSheet> createState() => _WarehousePickerSheetState();
}

class _WarehousePickerSheetState extends State<_WarehousePickerSheet> {
  static const _accent = Color(0xFF1565C0);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  List<PurchaseWarehouseOption> _rows = [];

  @override
  void initState() {
    super.initState();
    _fetch('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _schedule(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _fetch(q.trim()));
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
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 12),
          const Text('Select warehouse', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 12),
          TextField(
            controller: _search,
            decoration: InputDecoration(
              hintText: 'Search warehouse',
              prefixIcon: const Icon(Icons.search, size: 20),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              isDense: true,
            ),
            onChanged: _schedule,
            onSubmitted: _fetch,
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: CircularProgressIndicator(color: _accent)),
            )
          else if (_rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(child: Text('No warehouses found.', style: TextStyle(color: Colors.grey.shade600))),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.45),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final w = _rows[i];
                  final label = w.label.isNotEmpty
                      ? w.label
                      : (w.warehouseName.isNotEmpty ? w.warehouseName : w.warehouseId);
                  return ListTile(
                    onTap: () => Navigator.pop(context, w),
                    title: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text(
                      [
                        if (w.warehouseCode.isNotEmpty) w.warehouseCode,
                        if (w.warehouseId.isNotEmpty) 'ID ${w.warehouseId}',
                      ].join(' · '),
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _RtSavedDialog extends StatefulWidget {
  const _RtSavedDialog({
    required this.result,
    this.supplierName = '',
    this.netTotal = 0,
  });

  final StockReturnSaveResult result;
  final String supplierName;
  final double netTotal;

  @override
  State<_RtSavedDialog> createState() => _RtSavedDialogState();
}

class _RtSavedDialogState extends State<_RtSavedDialog> {
  static const _accent = Color(0xFF1565C0);
  static const _titleColor = Color(0xFF262C50);

  bool _pdfBusy = false;
  String? _pdfError;

  Future<File> _writePdfFile() async {
    final bytes = await context.read<StockReturnService>().downloadReturnPdf(
          widget.result.returnNo,
          kind: widget.result.inventoryPosted ? 'posted' : 'request',
        );
    final dir = await getTemporaryDirectory();
    final safe = widget.result.returnNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/RT_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _viewPdf() async {
    if (_pdfBusy || widget.result.returnNo.trim().isEmpty) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final file = await _writePdfFile();
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        setState(() {
          _pdfError = opened.message.isNotEmpty
              ? opened.message
              : 'PDF saved. Open it from Files if it did not open automatically.';
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _pdfError = handleApiError(context, e, authenticatedContext: true));
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy || widget.result.returnNo.trim().isEmpty) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final file = await _writePdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'Purchase Return ${widget.result.returnNo}',
        text: 'Purchase Return ${widget.result.returnNo}',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _pdfError = handleApiError(context, e, authenticatedContext: true));
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    final note = result.message.trim().isNotEmpty ? result.message.trim() : null;

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
              decoration: const BoxDecoration(
                color: Color(0xFFE8F5E9),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.check_rounded, size: 40, color: Color(0xFF2E7D32)),
            ),
            const SizedBox(height: 18),
            Text(
              result.inventoryPosted
                  ? (result.accountsPosted
                      ? 'Purchase Return posted'
                      : 'Purchase Return stock posted')
                  : 'Purchase Return saved',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: _titleColor),
            ),
            const SizedBox(height: 6),
            Text(
              'PR-${result.returnNo}',
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: _accent, height: 1.1),
            ),
            const SizedBox(height: 6),
            Text(
              result.approvalStatus,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Colors.grey.shade700),
            ),
            if (widget.supplierName.isNotEmpty || widget.netTotal > 0) ...[
              const SizedBox(height: 14),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFF6F7FC),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  children: [
                    if (widget.supplierName.isNotEmpty)
                      Row(
                        children: [
                          Text('Supplier', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                          const Spacer(),
                          Flexible(
                            child: Text(
                              widget.supplierName,
                              textAlign: TextAlign.right,
                              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    if (widget.netTotal > 0) ...[
                      if (widget.supplierName.isNotEmpty) const SizedBox(height: 8),
                      Row(
                        children: [
                          Text('Total', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                          const Spacer(),
                          Text(
                            widget.netTotal.toStringAsFixed(2),
                            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ],
            if (note != null) ...[
              const SizedBox(height: 12),
              Text(
                note,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700, height: 1.35),
              ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _pdfBusy ? null : _sharePdf,
                icon: _pdfBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.share_outlined),
                label: Text(
                  _pdfBusy ? 'Preparing PDF…' : 'Share PDF',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
                style: FilledButton.styleFrom(
                  backgroundColor: _accent,
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _pdfBusy ? null : _viewPdf,
                icon: const Icon(Icons.picture_as_pdf_outlined),
                label: const Text(
                  'View PDF',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
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
              child: TextButton(
                onPressed: _pdfBusy ? null : () => Navigator.of(context).pop(),
                child: const Text('Done', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
