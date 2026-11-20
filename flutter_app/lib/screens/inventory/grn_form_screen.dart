import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../core/ui/confirm_save.dart';
import '../../providers/auth_provider.dart';
import '../../providers/purchase_provider.dart';
import '../../services/purchase_order_service.dart';
import '../../services/purchase_service.dart';
import '../../services/supplier_master_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/hardware_barcode_capture.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/numeric_text_field.dart';
import '../barcode_scanner_screen.dart';
import '../masters/supplier_form_screen.dart';
import 'inventory_transaction_draft.dart';
import 'purchase_catalog_tabs.dart';
import 'purchase_order_cart_screen.dart';
import '../../core/theme/app_theme.dart';

class _GrnFormLine {
  _GrnFormLine({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    this.barcode = '',
    this.conversionFactor = 1,
  });

  final String itemCode;
  final String itemName;
  String uom;
  double qty;
  double rate;
  String barcode;
  /// ITEMALTERNATEUOMMAP factor (base stock qty = qty × factor).
  double conversionFactor;

  double get amount => qty * rate;
  double get baseQty => qty * (conversionFactor > 0 ? conversionFactor : 1);
}

class _LineEditResult {
  const _LineEditResult({
    required this.qty,
    required this.rate,
    required this.uom,
    this.barcode = '',
    this.conversionFactor = 1,
  });
  final double qty;
  final double rate;
  final String uom;
  final String barcode;
  final double conversionFactor;
}

/// Direct Create GRN — same flow style as Purchase Order (details → items → review).
class GrnFormScreen extends StatefulWidget {
  const GrnFormScreen({super.key, this.restoreDraft = false});

  /// When true, restores the in-session draft after open context loads.
  final bool restoreDraft;

  @override
  State<GrnFormScreen> createState() => _GrnFormScreenState();
}

class _GrnFormScreenState extends State<GrnFormScreen> with WidgetsBindingObserver {
  static const _accent = Color(0xFF0277BD);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  int _step = 0;
  bool _loading = true;
  bool _submitting = false;
  String? _loadError;
  Object? _loadErrorCause;

  String _receiptNo = '';
  String _receiptDateIso = '';
  bool _warehouseEnabled = false;
  /// `grn_draft` | `grn_only` | `grn_invoice_posting`
  String _saveMode = 'grn_draft';

  PurchaseSupplierOption? _supplier;
  PurchaseWarehouseOption? _warehouse;
  final _invoiceNo = TextEditingController();
  final _poNo = TextEditingController();
  final _remarks = TextEditingController();
  final _confirmAmount = TextEditingController();
  late String _invoiceDateIso;

  final _catalogSearch = TextEditingController();
  final _catalogSearchFocus = FocusNode();
  final _hwBarcode = TextEditingController();
  final _hwBarcodeFocus = FocusNode();
  final List<_GrnFormLine> _lines = [];
  List<PurchaseCatalogItem> _catalogItems = [];
  bool _catalogLoading = false;
  String? _catalogError;
  Timer? _catalogDebounce;
  List<PurchaseCatalogItem> _supplierItems = [];
  bool _supplierItemsLoading = false;
  String? _supplierItemsError;
  String? _supplierItemsLoadedFor;
  bool _barcodeLookupBusy = false;
  Timer? _draftDebounce;
  String _draftTenantId = '';
  String _draftUsername = '';
  bool _draftCleared = false;

  double get _lineTotal => _lines.fold(0.0, (s, l) => s + l.amount);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final now = DateTime.now();
    _receiptDateIso =
        '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
    _invoiceDateIso = _receiptDateIso;
    _invoiceNo.addListener(_scheduleDraftSave);
    _poNo.addListener(_scheduleDraftSave);
    _remarks.addListener(_scheduleDraftSave);
    _confirmAmount.addListener(_scheduleDraftSave);
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
    _invoiceNo.removeListener(_scheduleDraftSave);
    _poNo.removeListener(_scheduleDraftSave);
    _remarks.removeListener(_scheduleDraftSave);
    _confirmAmount.removeListener(_scheduleDraftSave);
    _catalogDebounce?.cancel();
    _draftDebounce?.cancel();
    _invoiceNo.dispose();
    _poNo.dispose();
    _remarks.dispose();
    _confirmAmount.dispose();
    _catalogSearch.dispose();
    _catalogSearchFocus.dispose();
    _hwBarcode.dispose();
    _hwBarcodeFocus.dispose();
    super.dispose();
  }

  void _scheduleDraftSave() {
    if (_draftCleared || _loading || _submitting) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), _persistDraft);
  }

  bool get _hasMeaningfulDraft => InventoryTransactionDraft.isMeaningful(
        partyCode: _supplier?.code,
        partyName: _supplier?.name,
        remarks: _remarks.text,
        lines: _lines,
        other: _invoiceNo.text.trim().isNotEmpty || _poNo.text.trim().isNotEmpty,
      );

  Future<void> _persistDraft() async {
    if (_draftCleared || _submitting) return;
    if (!_hasMeaningfulDraft) return;
    if (_draftUsername.isEmpty) return;
    final draft = <String, dynamic>{
      'step': _step,
      'save_mode': _saveMode,
      'remarks': _remarks.text,
      'invoice_no': _invoiceNo.text,
      'po_no': _poNo.text,
      'confirm_amount': _confirmAmount.text,
      'invoice_date_iso': _invoiceDateIso,
      'supplier': InventoryTransactionDraft.encodeParty(
        code: _supplier?.code,
        name: _supplier?.name,
      ),
      'warehouse': InventoryTransactionDraft.encodeWarehouse(
        id: _warehouse?.warehouseId,
        code: _warehouse?.warehouseCode,
        name: _warehouse?.warehouseName,
        label: _warehouse?.label,
      ),
      'party_name': (_supplier?.name ?? '').trim().isNotEmpty
          ? _supplier!.name.trim()
          : (_supplier?.code ?? '').trim(),
      'lines': _lines
          .map(
            (l) => <String, dynamic>{
              'item_code': l.itemCode,
              'item_name': l.itemName,
              'uom': l.uom,
              'qty': l.qty,
              'rate': l.rate,
              'barcode': l.barcode,
            },
          )
          .toList(),
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.grn,
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
      docType: TransactionDraftType.grn,
      tenantId: _draftTenantId,
      username: _draftUsername,
    );
  }

  void _applyDraft(Map<String, dynamic> draft) {
    final supplierMap = InventoryTransactionDraft.mapOf(draft['supplier']);
    if (supplierMap != null) {
      final code = '${supplierMap['code'] ?? ''}'.trim();
      if (code.isNotEmpty) {
        _supplier = PurchaseSupplierOption(
          code: code,
          name: '${supplierMap['name'] ?? code}'.trim(),
        );
      }
    }
    final whMap = InventoryTransactionDraft.mapOf(draft['warehouse']);
    if (whMap != null) {
      final id = '${whMap['warehouse_id'] ?? whMap['id'] ?? ''}'.trim();
      final code = '${whMap['warehouse_code'] ?? whMap['code'] ?? ''}'.trim();
      if (id.isNotEmpty || code.isNotEmpty) {
        final name = '${whMap['warehouse_name'] ?? whMap['name'] ?? ''}'.trim();
        final label = '${whMap['label'] ?? ''}'.trim();
        _warehouse = PurchaseWarehouseOption(
          warehouseId: id.isNotEmpty ? id : code,
          warehouseCode: code,
          warehouseName: name,
          label: label.isNotEmpty ? label : (name.isNotEmpty ? name : code),
        );
      }
    }
    _invoiceNo.text = '${draft['invoice_no'] ?? ''}';
    _poNo.text = '${draft['po_no'] ?? ''}';
    _remarks.text = '${draft['remarks'] ?? ''}';
    _confirmAmount.text = '${draft['confirm_amount'] ?? ''}';
    final invDate = '${draft['invoice_date_iso'] ?? ''}'.trim();
    if (invDate.isNotEmpty) _invoiceDateIso = invDate;
    final mode = '${draft['save_mode'] ?? ''}'.trim();
    if (mode == 'grn_draft' || mode == 'grn_only' || mode == 'grn_invoice_posting') {
      _saveMode = mode;
    }
    final linesRaw = (draft['lines'] as List?) ?? const [];
    final lines = <_GrnFormLine>[];
    for (var i = 0; i < linesRaw.length; i++) {
      final m = InventoryTransactionDraft.lineAt(linesRaw, i);
      if (m == null) continue;
      final itemCode = '${m['item_code'] ?? ''}'.trim();
      if (itemCode.isEmpty) continue;
      lines.add(
        _GrnFormLine(
          itemCode: itemCode,
          itemName: '${m['item_name'] ?? itemCode}'.trim(),
          uom: '${m['uom'] ?? 'PCS'}'.trim().isEmpty ? 'PCS' : '${m['uom']}'.trim(),
          qty: InventoryTransactionDraft.numOf(m['qty']),
          rate: InventoryTransactionDraft.numOf(m['rate']),
          barcode: '${m['barcode'] ?? ''}'.trim(),
        ),
      );
    }
    _lines
      ..clear()
      ..addAll(lines);
    final step = InventoryTransactionDraft.intOf(draft['step']);
    _step = step.clamp(0, 2);
    if (_confirmAmount.text.trim().isEmpty && _lines.isNotEmpty) {
      _confirmAmount.text = _lineTotal.toStringAsFixed(2);
    }
  }

  String _fmtQty(double q) => q == q.roundToDouble() ? q.round().toString() : q.toStringAsFixed(2);

  String _displayDate(String iso) {
    if (iso.length < 10) return iso;
    const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final y = int.tryParse(iso.substring(0, 4)) ?? 0;
    final mo = int.tryParse(iso.substring(5, 7)) ?? 1;
    final d = int.tryParse(iso.substring(8, 10)) ?? 1;
    if (y <= 0) return iso;
    return '${m[mo - 1]} $d, $y';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _loadErrorCause = null;
    });
    try {
      final poSvc = context.read<PurchaseOrderService>();
      final purchaseSvc = context.read<PurchaseService>();
      final open = await poSvc.getOrderOpen();
      String nextNo = '';
      try {
        nextNo = await purchaseSvc.nextGrnNo();
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _receiptNo = nextNo;
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
          docType: TransactionDraftType.grn,
          tenantId: _draftTenantId,
          username: _draftUsername,
        );
        if (!mounted) return;
        if (draft != null) {
          setState(() => _applyDraft(draft));
        }
      }

      if (_warehouseEnabled && (_warehouse == null || _warehouse!.warehouseId.isEmpty)) {
        final sole = await poSvc.soleWarehouseIfOnlyOne();
        if (!mounted) return;
        if (sole != null) {
          setState(() => _warehouse = sole);
        }
      }

      if (mounted) setState(() => _loading = false);
      _loadCatalog();
      _loadSupplierItems();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadErrorCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _pickDate({required bool invoice}) async {
    final initial = DateTime.tryParse(invoice ? _invoiceDateIso : _receiptDateIso) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    final iso =
        '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
    setState(() {
      if (invoice) {
        _invoiceDateIso = iso;
      } else {
        _receiptDateIso = iso;
      }
    });
    if (invoice) _scheduleDraftSave();
  }

  Future<void> _pickSupplier() async {
    final picked = await showModalBottomSheet<PurchaseSupplierOption>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
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
      useSafeArea: true,
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

  Future<_LineEditResult?> _showLineEdit({
    required String itemName,
    required String itemCode,
    required String uom,
    required String barcode,
    required double initialQty,
    required double initialRate,
    required String confirmLabel,
  }) {
    return showDialog<_LineEditResult>(
      context: context,
      builder: (ctx) => _GrnFormLineEditDialog(
        service: context.read<PurchaseOrderService>(),
        itemName: itemName,
        itemCode: itemCode,
        initialUom: uom,
        initialBarcode: barcode,
        initialQty: initialQty,
        initialRate: initialRate,
        confirmLabel: confirmLabel,
      ),
    );
  }

  Future<void> _addCatalogItem(PurchaseCatalogItem item) async {
    final existingIdx = _lines.indexWhere(
      (l) => l.itemCode == item.itemCode && l.uom.toUpperCase() == item.uom.toUpperCase(),
    );
    final existing = existingIdx >= 0 ? _lines[existingIdx] : null;
    final edited = await _showLineEdit(
      itemName: item.itemName.isNotEmpty ? item.itemName : item.itemCode,
      itemCode: item.itemCode,
      uom: existing?.uom ?? item.uom,
      barcode: existing?.barcode ?? item.barcode,
      initialQty: existing?.qty ?? 1,
      initialRate: existing?.rate ?? (item.displayCostPrice > 0 ? item.displayCostPrice : 1),
      confirmLabel: existing != null ? 'Update line' : 'Add line',
    );
    if (!mounted || edited == null || edited.qty <= 0) return;
    setState(() {
      if (existingIdx >= 0) {
        _lines[existingIdx].qty = edited.qty;
        _lines[existingIdx].rate = edited.rate;
        _lines[existingIdx].uom = edited.uom;
        _lines[existingIdx].barcode = edited.barcode;
        _lines[existingIdx].conversionFactor = edited.conversionFactor;
      } else {
        _lines.add(
          _GrnFormLine(
            itemCode: item.itemCode,
            itemName: item.itemName.isNotEmpty ? item.itemName : item.itemCode,
            uom: edited.uom,
            qty: edited.qty,
            rate: edited.rate,
            barcode: edited.barcode,
            conversionFactor: edited.conversionFactor,
          ),
        );
      }
      _confirmAmount.text = _lineTotal.toStringAsFixed(2);
    });
    _scheduleDraftSave();
  }

  Future<void> _editLine(int index) async {
    if (index < 0 || index >= _lines.length) return;
    final line = _lines[index];
    final edited = await _showLineEdit(
      itemName: line.itemName,
      itemCode: line.itemCode,
      uom: line.uom,
      barcode: line.barcode,
      initialQty: line.qty,
      initialRate: line.rate,
      confirmLabel: 'Update line',
    );
    if (!mounted || edited == null) return;
    setState(() {
      if (edited.qty <= 0) {
        _lines.removeAt(index);
      } else {
        line.qty = edited.qty;
        line.rate = edited.rate;
        line.uom = edited.uom;
        line.barcode = edited.barcode;
        line.conversionFactor = edited.conversionFactor;
      }
      _confirmAmount.text = _lineTotal.toStringAsFixed(2);
    });
    _scheduleDraftSave();
  }

  Future<void> _scanBarcode() async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const BarcodeScannerScreen()),
    );
    if (code == null || code.trim().isEmpty || !mounted) return;
    await _handleBarcodeLookup(code.trim());
  }

  Future<void> _handleBarcodeLookup(String code) async {
    if (_barcodeLookupBusy || code.isEmpty) return;
    setState(() => _barcodeLookupBusy = true);
    try {
      final items = await context.read<PurchaseOrderService>().searchCatalog(q: code, limit: 80);
      if (!mounted) return;
      PurchaseCatalogItem? hit;
      for (final i in items) {
        if (i.barcode.toUpperCase() == code.toUpperCase() || i.itemCode == code) {
          hit = i;
          break;
        }
      }
      hit ??= items.isNotEmpty ? items.first : null;
      if (hit == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No item found for $code')),
        );
        return;
      }
      await _addCatalogItem(hit);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _barcodeLookupBusy = false);
    }
  }

  bool _validateDetails() {
    if (_supplier == null || _supplier!.code.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Supplier is required.')),
      );
      return false;
    }
    if (_warehouseEnabled && (_warehouse == null || _warehouse!.warehouseId.trim().isEmpty)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Warehouse is required.')),
      );
      return false;
    }
    if (_invoiceNo.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invoice number is required.')),
      );
      return false;
    }
    return true;
  }

  Future<void> _save() async {
    if (_submitting) return;
    if (!_validateDetails()) return;
    if (_lines.where((l) => l.qty > 0).isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add at least one item.')),
      );
      return;
    }
    final confirm = double.tryParse(_confirmAmount.text.trim().replaceAll(',', '')) ?? 0;
    if ((confirm - _lineTotal).abs() > 0.02) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Confirm amount must match line total (${_lineTotal.toStringAsFixed(2)}).')),
      );
      return;
    }

    final ok = await confirmSaveTransaction(
      context,
      title: 'Save GRN?',
      message: 'Save GRN ${_receiptNo.isEmpty ? '(new)' : _receiptNo} for ${_lineTotal.toStringAsFixed(2)}?',
      confirmLabel: 'Save GRN',
      confirmColor: const Color(0xFF0277BD),
    );
    if (!ok || !mounted) return;

    final whId = int.tryParse(_warehouse?.warehouseId ?? '');
    final lines = _lines
        .where((l) => l.qty > 0)
        .map(
          (l) {
            final factor = l.conversionFactor > 0 ? l.conversionFactor : 1.0;
            final baseQty = l.qty * factor;
            return {
              'item_code': l.itemCode,
              'itemcode': l.itemCode,
              'qty': l.qty,
              'quantity': l.qty,
              // ERP: receivedqty / baseqty are stock base units (qty × factor)
              'receivedqty': baseQty,
              'baseqty': baseQty,
              'conversionfactor': factor,
              'uomfactor': factor,
              'rate': l.rate,
              'amount': l.amount,
              'unit': l.uom.isEmpty ? 'PCS' : l.uom,
              'uom': l.uom.isEmpty ? 'PCS' : l.uom,
              if (whId != null) 'warehouse_id': whId,
              if ((_warehouse?.warehouseCode ?? '').isNotEmpty) 'warehouse_code': _warehouse!.warehouseCode,
            };
          },
        )
        .toList();

    // Set before any await so a second tap cannot start a parallel save (409 nonce race).
    _submitting = true;
    setState(() {});
    try {
      final result = await context.read<PurchaseProvider>().saveGrn(
            receiptNo: _receiptNo,
            receiptDate: _receiptDateIso,
            supplierCode: _supplier!.code,
            poNo: _poNo.text.trim(),
            invoiceNo: _invoiceNo.text.trim(),
            invoiceDate: _invoiceDateIso,
            invoiceAmount: _lineTotal,
            remarks: _remarks.text.trim(),
            lines: lines,
            saveMode: _saveMode,
            warehouseId: whId,
          );
      if (!mounted) return;
      await _clearDraft();
      final no = '${result['receipt_no'] ?? result['receiptno'] ?? _receiptNo}'.trim();
      final msg = '${result['message'] ?? ''}'.trim();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            msg.isNotEmpty
                ? msg
                : (_saveMode == 'grn_invoice_posting'
                    ? 'GRN ${no.isEmpty ? '' : no} posted to stock & accounts.'
                    : _saveMode == 'grn_only'
                        ? 'GRN ${no.isEmpty ? '' : no} posted to stock.'
                        : 'GRN ${no.isEmpty ? '' : no} saved as draft.'),
          ),
        ),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _next() async {
    if (_step == 0) {
      if (!_validateDetails()) return;
      setState(() {
        _step = 1;
        _confirmAmount.text = _lineTotal.toStringAsFixed(2);
      });
      _scheduleDraftSave();
      _loadCatalog();
      _loadSupplierItems();
      return;
    }
    if (_step == 1) {
      if (_lines.where((l) => l.qty > 0).isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Add at least one item.')),
        );
        return;
      }
      await _openCart(proceedToReview: true);
      return;
    }
    await _save();
  }

  @override
  Widget build(BuildContext context) {
    final purchase = context.watch<PurchaseProvider>();
    final busy = _submitting || purchase.isSubmitting;

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('New GRN', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: LoadingOverlay(
        loading: busy,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _loadError != null
                ? ApiErrorCenter(message: _loadError!, error: _loadErrorCause, onRetry: _load)
                : Column(
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
                        child: Row(
                          children: [
                            _dot(0),
                            Expanded(child: Container(height: 2, color: _step >= 1 ? _accent : const Color(0xFFE8EBF3))),
                            _dot(1),
                            Expanded(child: Container(height: 2, color: _step >= 2 ? _accent : const Color(0xFFE8EBF3))),
                            _dot(2),
                          ],
                        ),
                      ),
                      Expanded(
                        child: switch (_step) {
                          0 => _detailsStep(),
                          1 => _itemsStep(),
                          _ => _reviewStep(),
                        },
                      ),
                      SafeArea(
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
                          child: Row(
                            children: [
                              Expanded(
                                child: OutlinedButton(
                                  onPressed: busy
                                      ? null
                                      : () {
                                          if (_step <= 0) {
                                            Navigator.of(context).maybePop();
                                          } else {
                                            setState(() => _step -= 1);
                                            _scheduleDraftSave();
                                          }
                                        },
                                  child: Text(_step == 0 ? 'Cancel' : 'Back'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: FilledButton(
                                  style: FilledButton.styleFrom(backgroundColor: _accent),
                                  onPressed: busy ? null : _next,
                                  child: Text(
                                    _step == 0
                                        ? 'Next: Items'
                                        : _step == 1
                                            ? 'Next: Review'
                                            : (_saveMode == 'grn_invoice_posting'
                                                ? 'Post stock + accounts'
                                                : _saveMode == 'grn_only'
                                                    ? 'Post stock'
                                                    : 'Save draft'),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
      ),
    );
  }

  Future<void> _openCart({bool proceedToReview = false}) async {
    final goReview = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => PurchaseOrderCartScreen(
          title: 'GRN cart',
          emptyHint: 'Search or scan products to add lines to this GRN.',
          continueLabel: proceedToReview ? 'Checkout' : 'Done',
          lpono: _receiptNo.isEmpty ? 'New GRN' : _receiptNo,
          lpoDate: _displayDate(_receiptDateIso),
          getLines: () => _lines
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
              .toList(),
          getNetTotal: () => _lineTotal,
          onLineDelete: (i) {
            if (i < 0 || i >= _lines.length) return;
            setState(() {
              _lines.removeAt(i);
              _confirmAmount.text = _lineTotal.toStringAsFixed(2);
            });
            _scheduleDraftSave();
          },
          onQtyChanged: (i, qty) {
            if (i < 0 || i >= _lines.length) return;
            setState(() {
              _lines[i].qty = qty;
              _confirmAmount.text = _lineTotal.toStringAsFixed(2);
            });
            _scheduleDraftSave();
          },
          onRateChanged: (i, rate) {
            if (i < 0 || i >= _lines.length) return;
            setState(() {
              _lines[i].rate = rate;
              _confirmAmount.text = _lineTotal.toStringAsFixed(2);
            });
            _scheduleDraftSave();
          },
          onLineEdit: (i) async {
            await _editLine(i);
          },
        ),
      ),
    );
    if (!mounted) return;
    setState(() => _confirmAmount.text = _lineTotal.toStringAsFixed(2));
    if (proceedToReview && goReview == true && _lines.where((l) => l.qty > 0).isNotEmpty) {
      setState(() => _step = 2);
    }
    _scheduleDraftSave();
  }

  String _saveModeLabel() {
    switch (_saveMode) {
      case 'grn_invoice_posting':
        return 'Post stock + accounts';
      case 'grn_only':
        return 'Post stock';
      default:
        return 'Save draft';
    }
  }

  Widget _dot(int i) => Container(
        width: 22,
        height: 22,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: _step >= i ? _accent : Colors.white,
          border: Border.all(color: _step >= i ? _accent : const Color(0xFFD0D5E2)),
          shape: BoxShape.circle,
        ),
        child: Text(
          '${i + 1}',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            color: _step >= i ? Colors.white : const Color(0xFF8A90A5),
          ),
        ),
      );

  Widget _card({required Widget child}) => Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE8EBF3)),
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
            : (_warehouse!.warehouseName.isNotEmpty ? _warehouse!.warehouseName : _warehouse!.warehouseId));

    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 24),
      children: [
        if (_receiptNo.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text('Next GRN: $_receiptNo', style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
          ),
        _card(
          child: Column(
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
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('Receipt date *', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                subtitle: Text(_displayDate(_receiptDateIso), style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                trailing: const Icon(Icons.calendar_today_outlined, size: 18),
                onTap: () => _pickDate(invoice: false),
              ),
              const Divider(height: 1),
              const SizedBox(height: 8),
              TextField(
                controller: _invoiceNo,
                decoration: const InputDecoration(labelText: 'Invoice No *', isDense: true, border: OutlineInputBorder()),
              ),
              const SizedBox(height: 10),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('Invoice date *', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                subtitle: Text(_displayDate(_invoiceDateIso), style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                trailing: const Icon(Icons.calendar_today_outlined, size: 18),
                onTap: () => _pickDate(invoice: true),
              ),
              const Divider(height: 1),
              const SizedBox(height: 8),
              TextField(
                controller: _poNo,
                decoration: const InputDecoration(
                  labelText: 'PO No (optional)',
                  hintText: 'Leave blank for direct GRN',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _remarks,
                maxLines: 2,
                decoration: const InputDecoration(labelText: 'Remarks', isDense: true, border: OutlineInputBorder()),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Default save mode', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
              const SizedBox(height: 4),
              Text(_saveModeLabel(), style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(
                'You can change this on the Review step.',
                style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
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
          padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
          child: TextField(
            controller: _catalogSearch,
            focusNode: _catalogSearchFocus,
            onChanged: (_) {
              setState(() {});
              _scheduleCatalogSearch();
            },
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
                      },
                    ),
                  IconButton(
                    icon: Icon(Icons.qr_code_scanner_rounded, color: Colors.grey.shade700),
                    onPressed: _scanBarcode,
                  ),
                ],
              ),
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: _border)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: _border)),
              isDense: true,
            ),
          ),
        ),
        if (_lines.isNotEmpty)
          Material(
            color: Colors.white,
            child: InkWell(
              onTap: () => _openCart(),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
                child: Row(
                  children: [
                    const Icon(Icons.shopping_cart_outlined, color: _accent, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Cart ${_lines.length} · Total ${_lineTotal.toStringAsFixed(2)}',
                        style: const TextStyle(fontWeight: FontWeight.w700, color: _accent),
                      ),
                    ),
                    TextButton(
                      onPressed: () => _openCart(proceedToReview: true),
                      child: const Text('Checkout'),
                    ),
                    IconButton(
                      tooltip: 'Open cart',
                      onPressed: () => _openCart(),
                      icon: const Icon(Icons.open_in_new_rounded, color: _accent),
                    ),
                  ],
                ),
              ),
            ),
          ),
        if (_catalogError != null && _catalogItems.isEmpty && _supplierItems.isEmpty)
          ApiErrorBanner(message: _catalogError!),
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
            itemBuilder: (_, item) {
              final history = purchaseSupplierHistoryLine(item);
              return Container(
                margin: const EdgeInsets.only(bottom: 6),
                child: Material(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  child: ListTile(
                    onTap: () => _addCatalogItem(item),
                    title: Text(
                      item.itemName.isNotEmpty ? item.itemName : item.itemCode,
                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5),
                    ),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          [
                            if (item.itemCode.isNotEmpty) item.itemCode,
                            if (item.uom.isNotEmpty) item.uom,
                            if (item.barcode.isNotEmpty) item.barcode,
                          ].join(' · '),
                        ),
                        const SizedBox(height: 2),
                        purchaseCatalogAvgCostLine(item),
                        if (history != null) ...[
                          const SizedBox(height: 2),
                          Text(
                            history,
                            style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: FontWeight.w600,
                              color: Colors.grey.shade700,
                            ),
                          ),
                        ],
                      ],
                    ),
                    isThreeLine: true,
                    trailing: purchaseCatalogCostPriceColumn(item),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _reviewStep() {
    final activeLines = _lines.where((l) => l.qty > 0).toList();
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 24),
      children: [
        const Text('Review & save', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17, color: _accent)),
        const SizedBox(height: 12),
        _card(
          child: Column(
            children: [
              _kv('GRN', _receiptNo.isEmpty ? '(auto)' : _receiptNo),
              _kv('Supplier', _supplier?.name.isNotEmpty == true ? _supplier!.name : (_supplier?.code ?? '')),
              if (_warehouseEnabled) _kv('Warehouse', _warehouse?.label ?? ''),
              _kv('Receipt date', _displayDate(_receiptDateIso)),
              _kv('Invoice', _invoiceNo.text.trim()),
              _kv('Invoice date', _displayDate(_invoiceDateIso)),
              if (_poNo.text.trim().isNotEmpty) _kv('PO', _poNo.text.trim()),
              _kv('Lines', '${activeLines.length}'),
              _kv('Total', _lineTotal.toStringAsFixed(2)),
            ],
          ),
        ),
        const SizedBox(height: 12),
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text('Checkout items', style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                  TextButton.icon(
                    onPressed: () => _openCart(),
                    icon: const Icon(Icons.shopping_cart_outlined, size: 18),
                    label: const Text('Open cart'),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              if (activeLines.isEmpty)
                Text('No lines.', style: TextStyle(color: Colors.grey.shade600))
              else
                for (final l in activeLines) ...[
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                l.itemName.isNotEmpty ? l.itemName : l.itemCode,
                                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '${l.itemCode} · ${_fmtQty(l.qty)} ${l.uom} @ ${l.rate.toStringAsFixed(2)}',
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                              ),
                            ],
                          ),
                        ),
                        Text(l.amount.toStringAsFixed(2), style: const TextStyle(fontWeight: FontWeight.w800)),
                      ],
                    ),
                  ),
                  if (l != activeLines.last) Divider(height: 1, color: Colors.grey.shade200),
                ],
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
                value: 'grn_draft',
                groupValue: _saveMode,
                onChanged: (v) {
                  setState(() => _saveMode = v ?? 'grn_draft');
                  _scheduleDraftSave();
                },
              ),
              RadioListTile<String>(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Approve & post stock'),
                subtitle: const Text('Updates warehouse stock / item journal'),
                value: 'grn_only',
                groupValue: _saveMode,
                onChanged: (v) {
                  setState(() => _saveMode = v ?? 'grn_only');
                  _scheduleDraftSave();
                },
              ),
              RadioListTile<String>(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: const Text('Post stock + accounts'),
                subtitle: const Text('Stock + purchase invoice / AP (ERP)'),
                value: 'grn_invoice_posting',
                groupValue: _saveMode,
                onChanged: (v) {
                  setState(() => _saveMode = v ?? 'grn_invoice_posting');
                  _scheduleDraftSave();
                },
              ),
              const SizedBox(height: 8),
              NumericTextField(
                controller: _confirmAmount,
                decoration: const InputDecoration(
                  labelText: 'Confirm invoice amount *',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            SizedBox(width: 110, child: Text(k, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600))),
            Expanded(child: Text(v.isEmpty ? '—' : v, style: const TextStyle(fontWeight: FontWeight.w600))),
          ],
        ),
      );
}

class _GrnFormLineEditDialog extends StatefulWidget {
  const _GrnFormLineEditDialog({
    required this.service,
    required this.itemName,
    required this.itemCode,
    required this.initialUom,
    required this.initialBarcode,
    required this.initialQty,
    required this.initialRate,
    required this.confirmLabel,
  });

  final PurchaseOrderService service;
  final String itemName;
  final String itemCode;
  final String initialUom;
  final String initialBarcode;
  final double initialQty;
  final double initialRate;
  final String confirmLabel;

  @override
  State<_GrnFormLineEditDialog> createState() => _GrnFormLineEditDialogState();
}

class _GrnFormLineEditDialogState extends State<_GrnFormLineEditDialog> {
  late final TextEditingController _qty;
  late final TextEditingController _rate;
  List<PurchaseUomOption> _uoms = [];
  late String _uom;
  late String _barcode;
  bool _loadingUoms = true;

  @override
  void initState() {
    super.initState();
    final q = widget.initialQty;
    _qty = TextEditingController(
      text: q == q.roundToDouble() ? q.round().toString() : q.toStringAsFixed(2),
    );
    _rate = TextEditingController(text: widget.initialRate.toStringAsFixed(2));
    _uom = widget.initialUom.isNotEmpty ? widget.initialUom : 'PCS';
    _barcode = widget.initialBarcode;
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadUoms());
  }

  @override
  void dispose() {
    _qty.dispose();
    _rate.dispose();
    super.dispose();
  }

  Future<void> _loadUoms() async {
    try {
      var list = await widget.service.getItemUoms(widget.itemCode);
      if (!mounted) return;
      if (list.isEmpty) {
        list = [PurchaseUomOption(uom: _uom, rate: widget.initialRate, barcode: _barcode)];
      }
      final match = list.where((u) => u.uom.toUpperCase() == _uom.toUpperCase());
      final selected = match.isNotEmpty ? match.first : list.first;
      setState(() {
        _uoms = list;
        _uom = selected.uom;
        _barcode = selected.barcode.isNotEmpty ? selected.barcode : _barcode;
        _loadingUoms = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingUoms = false;
        _uoms = [PurchaseUomOption(uom: _uom, rate: widget.initialRate, barcode: _barcode)];
      });
    }
  }

  void _submit() {
    final qty = double.tryParse(_qty.text.trim().replaceAll(',', '')) ?? 0;
    final rate = double.tryParse(_rate.text.trim().replaceAll(',', '')) ?? 0;
    var factor = 1.0;
    for (final u in _uoms) {
      if (u.uom.toUpperCase() == _uom.toUpperCase()) {
        factor = u.factor > 0 ? u.factor : 1.0;
        break;
      }
    }
    Navigator.pop(
      context,
      _LineEditResult(
        qty: qty,
        rate: rate,
        uom: _uom,
        barcode: _barcode,
        conversionFactor: factor,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Line', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(widget.itemName, style: const TextStyle(fontWeight: FontWeight.w700)),
            Text('Code ${widget.itemCode}', style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
            const SizedBox(height: 12),
            TextField(
              controller: _qty,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Quantity', isDense: true),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _rate,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Rate', isDense: true),
            ),
            const SizedBox(height: 10),
            if (_loadingUoms)
              const LinearProgressIndicator()
            else
              DropdownButtonFormField<String>(
                value: _uoms.any((u) => u.uom == _uom) ? _uom : (_uoms.isNotEmpty ? _uoms.first.uom : _uom),
                decoration: const InputDecoration(labelText: 'UOM', isDense: true),
                items: [
                  for (final u in _uoms) DropdownMenuItem(value: u.uom, child: Text(u.uom)),
                ],
                onChanged: (v) {
                  if (v == null) return;
                  final opt = _uoms.firstWhere((u) => u.uom == v, orElse: () => _uoms.first);
                  setState(() {
                    _uom = opt.uom;
                    _barcode = opt.barcode.isNotEmpty ? opt.barcode : _barcode;
                    if (opt.rate > 0) _rate.text = opt.rate.toStringAsFixed(2);
                  });
                },
              ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0277BD)),
          onPressed: _submit,
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

  Future<void> _createSupplier() async {
    final prefill = _search.text.trim();
    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute(
        builder: (_) => SupplierFormScreen(prefillName: prefill),
      ),
    );
    if (!mounted || result == null) return;
    if (result is SupplierSaveResult && result.supplierCode > 0) {
      Navigator.pop(
        context,
        PurchaseSupplierOption(
          code: '${result.supplierCode}',
          name: result.supplierName.isNotEmpty ? result.supplierName : '${result.supplierCode}',
        ),
      );
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
          const SizedBox(height: 8),
          Row(
            children: [
              const Expanded(
                child: Text('Select supplier', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              TextButton.icon(
                onPressed: _createSupplier,
                icon: const Icon(Icons.person_add_alt_1_rounded, size: 18),
                label: const Text('New'),
              ),
            ],
          ),
          const SizedBox(height: 8),
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
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
            onPressed: _createSupplier,
            icon: const Icon(Icons.add_business_rounded, size: 18),
            label: const Text('Create new supplier'),
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
          else if (_rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 20),
              child: Center(
                child: Text(
                  'No suppliers found. Create a new one above.',
                  style: TextStyle(color: Colors.grey.shade600),
                  textAlign: TextAlign.center,
                ),
              ),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.4),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final s = _rows[i];
                  return ListTile(
                    onTap: () => Navigator.pop(context, s),
                    title: Text(s.name.isNotEmpty ? s.name : s.code, style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text('Code ${s.code}'),
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
          const SizedBox(height: 8),
          const Text('Select warehouse', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 12),
          TextField(
            controller: _search,
            autofocus: true,
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
            const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
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
                    subtitle: Text(w.warehouseId),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
