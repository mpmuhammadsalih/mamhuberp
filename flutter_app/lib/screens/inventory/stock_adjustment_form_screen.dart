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
import '../../services/stock_adjustment_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/hardware_barcode_capture.dart';
import '../../widgets/numeric_text_field.dart';
import '../barcode_scanner_screen.dart';
import 'inventory_transaction_draft.dart';
import '../../core/theme/app_theme.dart';

class _SaLine {
  _SaLine({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.store,
    required this.currentQty,
    required this.adjustQty,
    required this.cost,
    this.factor = 1,
  });

  final String itemCode;
  final String itemName;
  String uom;
  final String store;
  double currentQty;
  double adjustQty;
  double cost;
  double factor;

  double get newQty => currentQty + adjustQty;
  double get baseQty => adjustQty * factor;
  double get lineValue => adjustQty.abs() * cost;
}

class _SaLineEditResult {
  const _SaLineEditResult({
    required this.adjustQty,
    required this.cost,
    required this.uom,
    required this.currentQty,
    this.factor = 1,
    this.isIncrease = true,
  });

  final double adjustQty;
  final double cost;
  final String uom;
  final double currentQty;
  final double factor;
  final bool isIncrease;
}

class StockAdjustmentFormScreen extends StatefulWidget {
  const StockAdjustmentFormScreen({super.key, this.restoreDraft = false});

  /// When true, restores the in-session draft after open context loads.
  final bool restoreDraft;

  @override
  State<StockAdjustmentFormScreen> createState() => _StockAdjustmentFormScreenState();
}

class _StockAdjustmentFormScreenState extends State<StockAdjustmentFormScreen>
    with WidgetsBindingObserver {
  static const _accent = Color(0xFFEF6C00);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  int _step = 0;
  bool _loading = true;
  bool _submitting = false;
  String? _loadError;
  Object? _loadErrorCause;

  String _adjNo = '';
  String _adjDate = '';
  bool _openingStockMode = false;

  StockAdjustmentWarehouse? _warehouse;
  List<StockAdjustmentWarehouse> _warehouses = [];
  final _remarks = TextEditingController();

  final _catalogSearch = TextEditingController();
  final _catalogSearchFocus = FocusNode();
  final _hwBarcode = TextEditingController();
  final _hwBarcodeFocus = FocusNode();
  final List<_SaLine> _lines = [];
  List<StockAdjustmentCatalogItem> _catalogItems = [];
  bool _catalogLoading = false;
  String? _catalogError;
  Timer? _catalogDebounce;
  bool _barcodeLookupBusy = false;
  Timer? _draftDebounce;
  String _draftTenantId = '';
  String _draftUsername = '';
  bool _draftCleared = false;

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
    if (_draftCleared || _loading || _submitting) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), _persistDraft);
  }

  bool get _hasMeaningfulDraft => InventoryTransactionDraft.isMeaningful(
        remarks: _remarks.text,
        lines: _lines,
        // Warehouse alone (often prefilled from open) is not enough to keep a draft.
        other: false,
      );

  Future<void> _persistDraft() async {
    if (_draftCleared || _submitting) return;
    if (!_hasMeaningfulDraft) return;
    if (_draftUsername.isEmpty) return;
    final draft = <String, dynamic>{
      'step': _step,
      'remarks': _remarks.text,
      'opening_stock_mode': _openingStockMode,
      'warehouse': InventoryTransactionDraft.encodeWarehouse(
        code: _warehouse?.code,
        name: _warehouse?.name,
      ),
      'party_name': (_warehouse?.name ?? '').trim().isNotEmpty
          ? _warehouse!.name.trim()
          : (_warehouse?.code ?? '').trim(),
      'lines': _lines
          .map(
            (l) => <String, dynamic>{
              'item_code': l.itemCode,
              'item_name': l.itemName,
              'uom': l.uom,
              'store': l.store,
              'current_qty': l.currentQty,
              'adjust_qty': l.adjustQty,
              'cost': l.cost,
              'factor': l.factor,
            },
          )
          .toList(),
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.stockAdjustment,
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
      docType: TransactionDraftType.stockAdjustment,
      tenantId: _draftTenantId,
      username: _draftUsername,
    );
  }

  void _applyDraft(Map<String, dynamic> draft) {
    final whMap = InventoryTransactionDraft.mapOf(draft['warehouse']);
    if (whMap != null) {
      final code = '${whMap['code'] ?? whMap['warehouse_code'] ?? ''}'.trim();
      if (code.isNotEmpty) {
        StockAdjustmentWarehouse? matched;
        for (final w in _warehouses) {
          if (w.code == code) {
            matched = w;
            break;
          }
        }
        final name = '${whMap['name'] ?? whMap['warehouse_name'] ?? code}'.trim();
        _warehouse = matched ?? StockAdjustmentWarehouse(code: code, name: name);
      }
    }
    _remarks.text = '${draft['remarks'] ?? ''}';
    if (draft.containsKey('opening_stock_mode')) {
      _openingStockMode = draft['opening_stock_mode'] == true;
    }
    final linesRaw = (draft['lines'] as List?) ?? const [];
    final lines = <_SaLine>[];
    for (var i = 0; i < linesRaw.length; i++) {
      final m = InventoryTransactionDraft.lineAt(linesRaw, i);
      if (m == null) continue;
      final itemCode = '${m['item_code'] ?? ''}'.trim();
      if (itemCode.isEmpty) continue;
      final factor = InventoryTransactionDraft.numOf(m['factor']);
      lines.add(
        _SaLine(
          itemCode: itemCode,
          itemName: '${m['item_name'] ?? itemCode}'.trim(),
          uom: '${m['uom'] ?? 'PCS'}'.trim().isEmpty ? 'PCS' : '${m['uom']}'.trim(),
          store: '${m['store'] ?? _warehouse?.code ?? ''}'.trim(),
          currentQty: InventoryTransactionDraft.numOf(m['current_qty']),
          adjustQty: InventoryTransactionDraft.numOf(m['adjust_qty']),
          cost: InventoryTransactionDraft.numOf(m['cost']),
          factor: factor > 0 ? factor : 1,
        ),
      );
    }
    _lines
      ..clear()
      ..addAll(lines);
    final step = InventoryTransactionDraft.intOf(draft['step']);
    _step = step.clamp(0, 2);
  }

  double get _stockValue => _lines.fold(0.0, (s, l) => s + l.lineValue);

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
      final svc = context.read<StockAdjustmentService>();
      final open = await svc.getOpen();
      final warehouses = await svc.listWarehouses();
      if (!mounted) return;

      StockAdjustmentWarehouse? defaultWh;
      if (open.defaultStore.isNotEmpty) {
        for (final w in warehouses) {
          if (w.code == open.defaultStore) {
            defaultWh = w;
            break;
          }
        }
        defaultWh ??= StockAdjustmentWarehouse(code: open.defaultStore, name: open.defaultStore);
      } else if (warehouses.length == 1) {
        defaultWh = warehouses.first;
      }

      setState(() {
        _adjNo = open.adjNo;
        _adjDate = open.adjDate;
        _openingStockMode = open.openingStockMode;
        _warehouses = warehouses;
        _warehouse = defaultWh;
      });

      if (widget.restoreDraft && _draftUsername.isNotEmpty) {
        final draft = await TransactionDraftStorage.read(
          docType: TransactionDraftType.stockAdjustment,
          tenantId: _draftTenantId,
          username: _draftUsername,
        );
        if (!mounted) return;
        if (draft != null) {
          // Keep adj no/date from open API; overlay draft header/lines.
          setState(() => _applyDraft(draft));
        }
      }

      if (mounted) setState(() => _loading = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadErrorCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  String? _validateHeader() {
    if (_warehouse == null || _warehouse!.code.trim().isEmpty) {
      return 'Select a warehouse / store.';
    }
    return null;
  }

  Future<void> _pickWarehouse() async {
    final picked = await showModalBottomSheet<StockAdjustmentWarehouse>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _WarehousePickerSheet(warehouses: _warehouses),
    );
    if (picked == null || !mounted) return;
    setState(() => _warehouse = picked);
    _scheduleDraftSave();
  }

  void _scheduleCatalogSearch() {
    _catalogDebounce?.cancel();
    _catalogDebounce = Timer(const Duration(milliseconds: 350), _loadCatalog);
  }

  Future<void> _loadCatalog() async {
    final q = _catalogSearch.text.trim();
    setState(() {
      _catalogLoading = true;
      _catalogError = null;
    });
    try {
      final items = await context.read<StockAdjustmentService>().searchCatalog(q: q);
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

  Future<_SaLineEditResult?> _showLineEditDialog({
    required StockAdjustmentService service,
    required String itemName,
    required String itemCode,
    required String uom,
    required double initialCost,
    required String store,
    required double catalogStock,
    _SaLine? existing,
  }) {
    return showDialog<_SaLineEditResult>(
      context: context,
      builder: (ctx) => _LineEditDialog(
        service: service,
        itemName: itemName,
        itemCode: itemCode,
        initialUom: existing?.uom ?? uom,
        initialCost: existing?.cost ?? initialCost,
        store: store,
        catalogStock: catalogStock,
        initialQty: existing != null ? existing.adjustQty.abs() : 1,
        initialIsIncrease: existing == null ? true : existing.adjustQty >= 0,
        confirmLabel: existing != null ? 'Update line' : 'Add line',
      ),
    );
  }

  Future<void> _addCatalogItem(StockAdjustmentCatalogItem item) async {
    final wh = _warehouse;
    if (wh == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select a warehouse first.')),
      );
      return;
    }

    _hwBarcodeFocus.unfocus();
    _catalogSearchFocus.unfocus();

    final svc = context.read<StockAdjustmentService>();
    final existingIdx = _lines.indexWhere(
      (l) => l.itemCode == item.itemCode && l.uom.toUpperCase() == item.uom.toUpperCase(),
    );
    final existing = existingIdx >= 0 ? _lines[existingIdx] : null;

    double storeStock = item.currentStock;
    try {
      final stock = await svc.getItemStock(itemCode: item.itemCode, store: wh.code);
      if (mounted) storeStock = stock.currentQty;
    } catch (_) {
      // Fall back to catalog stock.
    }

    final edited = await _showLineEditDialog(
      service: svc,
      itemName: item.itemName.isNotEmpty ? item.itemName : item.itemCode,
      itemCode: item.itemCode,
      uom: existing?.uom ?? item.uom,
      initialCost: existing?.cost ?? item.cost,
      store: wh.code,
      catalogStock: storeStock,
      existing: existing,
    );
    if (!mounted || edited == null || edited.adjustQty == 0) return;

    final matchIdx = _lines.indexWhere(
      (l) => l.itemCode == item.itemCode && l.uom.toUpperCase() == edited.uom.toUpperCase(),
    );

    setState(() {
      if (matchIdx >= 0) {
        final line = _lines[matchIdx];
        line.uom = edited.uom;
        line.currentQty = edited.currentQty;
        line.adjustQty = edited.adjustQty;
        line.cost = edited.cost;
        line.factor = edited.factor;
      } else if (existingIdx >= 0) {
        final line = _lines[existingIdx];
        line.uom = edited.uom;
        line.currentQty = edited.currentQty;
        line.adjustQty = edited.adjustQty;
        line.cost = edited.cost;
        line.factor = edited.factor;
      } else {
        _lines.add(
          _SaLine(
            itemCode: item.itemCode,
            itemName: item.itemName,
            uom: edited.uom,
            store: wh.code,
            currentQty: edited.currentQty,
            adjustQty: edited.adjustQty,
            cost: edited.cost,
            factor: edited.factor,
          ),
        );
      }
    });
    _scheduleDraftSave();

    final sign = edited.adjustQty >= 0 ? '+' : '';
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${matchIdx >= 0 || existingIdx >= 0 ? 'Updated' : 'Added'} '
          '$sign${_fmtQty(edited.adjustQty)} ${edited.uom} · ${item.itemCode}',
        ),
      ),
    );
    _requestHwBarcodeFocus();
  }

  Future<void> _editLine(int index) async {
    if (index < 0 || index >= _lines.length) return;
    final line = _lines[index];
    final wh = _warehouse;
    if (wh == null) return;

    final svc = context.read<StockAdjustmentService>();
    final edited = await _showLineEditDialog(
      service: svc,
      itemName: line.itemName.isNotEmpty ? line.itemName : line.itemCode,
      itemCode: line.itemCode,
      uom: line.uom,
      initialCost: line.cost,
      store: wh.code,
      catalogStock: line.currentQty,
      existing: line,
    );
    if (edited == null || !mounted) return;
    setState(() {
      line.uom = edited.uom;
      line.currentQty = edited.currentQty;
      line.adjustQty = edited.adjustQty;
      line.cost = edited.cost;
      line.factor = edited.factor;
    });
    _scheduleDraftSave();
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
      final items = await context.read<StockAdjustmentService>().searchCatalog(q: code, limit: 80);
      if (!mounted) return;
      setState(() {
        _catalogItems = items;
        _catalogLoading = false;
      });
      final upper = code.toUpperCase();
      StockAdjustmentCatalogItem? match;
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

  void _handleWizardBack() {
    if (_submitting) return;
    if (_step <= 0) {
      Navigator.of(context).maybePop();
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
      return;
    }
    if (_lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add at least one item.')),
      );
      setState(() => _step = 1);
      return;
    }

    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save stock adjustment?',
      message: 'Save adjustment $_adjNo with ${_lines.length} line(s)?',
      confirmLabel: 'Save adjustment',
    );
    if (!confirmed || !mounted) return;

    setState(() => _submitting = true);
    try {
      final header = <String, dynamic>{
        'adj_no': _adjNo,
        'adj_date': _adjDate,
        'remarks': _remarks.text.trim(),
        if (_openingStockMode) 'opening_stock': true,
      };
      final lines = _lines
          .map(
            (l) => <String, dynamic>{
              'item_code': l.itemCode,
              'item_name': l.itemName,
              'uom': l.uom,
              'store': l.store,
              'current_qty': l.currentQty,
              'adjust_qty': l.adjustQty,
              'new_qty': l.newQty,
              'base_qty': l.baseQty,
              'cost': l.cost,
              'factor': l.factor,
            },
          )
          .toList();

      final result = await context.read<StockAdjustmentService>().saveAdjustment(
            header: header,
            lines: lines,
          );
      if (!mounted) return;
      await _clearDraft();
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => _SaSavedDialog(result: result, stockValue: _stockValue),
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
    final rightLabel = isLast ? 'Save adjustment' : 'Next';

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
            const Text(
              'Stock Adjustment',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            if (_adjNo.isNotEmpty)
              Text(
                'SA-$_adjNo • ${_adjDate.isEmpty ? '—' : _adjDate}',
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

  Widget _detailsStep() {
    final whLabel = _warehouse == null
        ? ''
        : (_warehouse!.label.isNotEmpty ? _warehouse!.label : _warehouse!.code);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _readonlyRow('SA No.', _adjNo.isEmpty ? '—' : _adjNo),
              _readonlyRow('Date', _adjDate.isEmpty ? '—' : _adjDate),
              if (_openingStockMode)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline, size: 16, color: Colors.orange.shade800),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          'Opening stock mode — adjustments will be flagged as opening stock.',
                          style: TextStyle(fontSize: 12, color: Colors.orange.shade900),
                        ),
                      ),
                    ],
                  ),
                ),
              const Divider(height: 1),
              _pickerField(
                label: 'Warehouse / Store *',
                value: whLabel,
                hint: 'Select warehouse',
                icon: Icons.warehouse_outlined,
                onTap: _pickWarehouse,
                subtitle: _warehouse?.code.isNotEmpty == true ? 'Code ${_warehouse!.code}' : null,
              ),
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
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFFFFF3E0),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFFFCC80)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.tune_rounded, color: _accent, size: 22),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          '${_lines.length} line(s) · ${_stockValue.toStringAsFixed(2)}',
                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: Color(0xFFE65100)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  for (var i = 0; i < _lines.length; i++) ...[
                    if (i > 0) const Divider(height: 12),
                    InkWell(
                      onTap: () => _editLine(i),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              _lines[i].itemName.isNotEmpty ? _lines[i].itemName : _lines[i].itemCode,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                            ),
                          ),
                          Text(
                            '${_lines[i].adjustQty >= 0 ? '+' : ''}${_fmtQty(_lines[i].adjustQty)} ${_lines[i].uom}',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              color: _lines[i].adjustQty >= 0 ? const Color(0xFF2E7D32) : const Color(0xFFC62828),
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete_outline, size: 20, color: Color(0xFFC62828)),
                            onPressed: () {
                              setState(() => _lines.removeAt(i));
                              _scheduleDraftSave();
                            },
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        Expanded(
          child: _catalogLoading && _catalogItems.isEmpty
              ? const Center(child: CircularProgressIndicator(color: _accent))
              : _catalogError != null
                  ? ApiErrorCenter(message: _catalogError!, onRetry: _loadCatalog)
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 16),
                      children: [
                        Text('Catalog', style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade800)),
                        const SizedBox(height: 8),
                        if (_catalogItems.isEmpty)
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 24),
                            child: Center(
                              child: Text(
                                'No catalog items found.',
                                style: TextStyle(color: Colors.grey.shade600),
                              ),
                            ),
                          )
                        else
                          for (final item in _catalogItems) _catalogTile(item),
                      ],
                    ),
        ),
      ],
    );
  }

  Widget _catalogTile(StockAdjustmentCatalogItem item) {
    final name = item.itemName.isNotEmpty ? item.itemName : item.itemCode;
    final inCart = _lines.any((l) => l.itemCode == item.itemCode);
    final stockColor = item.currentStock > 0 ? const Color(0xFF16A34A) : const Color(0xFFDC2626);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: inCart ? const Color(0xFFFFCC80) : const Color(0xFFE8EAED)),
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
                      '${item.itemCode} · ${item.uom} · ${item.cost.toStringAsFixed(2)}',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Stock ${_fmtStock(item.currentStock)}'
                      '${item.barcode.isNotEmpty ? '  ·  Barcode ${item.barcode}' : ''}',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: stockColor),
                    ),
                  ],
                ),
              ),
              Icon(
                inCart ? Icons.check_circle : Icons.add_circle_outline,
                color: _accent,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _reviewStep() {
    final whLabel = _warehouse == null
        ? '—'
        : (_warehouse!.label.isNotEmpty ? _warehouse!.label : _warehouse!.code);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _readonlyRow('SA No.', _adjNo.isEmpty ? '—' : _adjNo),
              _readonlyRow('Date', _adjDate.isEmpty ? '—' : _adjDate),
              _readonlyRow('Warehouse', whLabel),
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
                color: const Color(0xFFFFF3E0),
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
                            Text(
                              'Current ${_fmtQty(_lines[i].currentQty)} → New ${_fmtQty(_lines[i].newQty)}',
                              style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        '${_lines[i].adjustQty >= 0 ? '+' : ''}${_fmtQty(_lines[i].adjustQty)}',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: _lines[i].adjustQty >= 0 ? const Color(0xFF2E7D32) : const Color(0xFFC62828),
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
                    const Text('Stock value', style: TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(width: 12),
                    Text(
                      _stockValue.toStringAsFixed(2),
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: Color(0xFFEF6C00)),
                    ),
                  ],
                ),
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
    required this.initialCost,
    required this.store,
    required this.catalogStock,
    required this.initialQty,
    required this.initialIsIncrease,
    required this.confirmLabel,
  });

  final StockAdjustmentService service;
  final String itemName;
  final String itemCode;
  final String initialUom;
  final double initialCost;
  final String store;
  final double catalogStock;
  final double initialQty;
  final bool initialIsIncrease;
  final String confirmLabel;

  @override
  State<_LineEditDialog> createState() => _LineEditDialogState();
}

class _LineEditDialogState extends State<_LineEditDialog> {
  static const _accent = Color(0xFFEF6C00);

  late final TextEditingController _qty;
  late final TextEditingController _cost;
  List<StockAdjustmentUom> _uoms = [];
  late String _uom;
  late bool _isIncrease;
  double _currentStock = 0;
  bool _loadingUoms = true;
  bool _loadingStock = true;
  String? _uomError;

  @override
  void initState() {
    super.initState();
    final q = widget.initialQty;
    _qty = TextEditingController(
      text: q == q.roundToDouble() ? q.round().toString() : q.toStringAsFixed(2),
    );
    _cost = TextEditingController(text: widget.initialCost.toStringAsFixed(2));
    _uom = widget.initialUom.isNotEmpty ? widget.initialUom : 'NOS';
    _isIncrease = widget.initialIsIncrease;
    _currentStock = widget.catalogStock;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadUoms();
      _loadStock();
    });
  }

  @override
  void dispose() {
    _qty.dispose();
    _cost.dispose();
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

  StockAdjustmentUom? get _selectedUom {
    for (final u in _uoms) {
      if (u.uom.toUpperCase() == _uom.toUpperCase()) return u;
    }
    return _uoms.isNotEmpty ? _uoms.first : null;
  }

  double get _signedAdjust {
    final q = double.tryParse(_qty.text.trim().replaceAll(',', '')) ?? 0;
    if (q <= 0) return 0;
    return _isIncrease ? q : -q;
  }

  double get _newQty => _currentStock + _signedAdjust;

  Future<void> _loadStock() async {
    setState(() => _loadingStock = true);
    try {
      final stock = await widget.service.getItemStock(
        itemCode: widget.itemCode,
        store: widget.store,
      );
      if (!mounted) return;
      setState(() {
        _currentStock = stock.currentQty;
        _loadingStock = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingStock = false);
    }
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
          StockAdjustmentUom(uom: _uom, rate: widget.initialCost),
        ];
      }
      final match = list.where((u) => u.uom.toUpperCase() == _uom.toUpperCase());
      final selected = match.isNotEmpty ? match.first : list.first;
      setState(() {
        _uoms = list;
        _uom = selected.uom;
        if (selected.rate > 0 && widget.initialCost <= 0) {
          _cost.text = selected.rate.toStringAsFixed(2);
        }
        _loadingUoms = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingUoms = false;
        _uomError = 'Could not load UOMs';
        _uoms = [
          StockAdjustmentUom(uom: _uom, rate: widget.initialCost),
        ];
      });
    }
  }

  void _onUomChanged(String? value) {
    if (value == null || value.isEmpty) return;
    StockAdjustmentUom? opt;
    for (final u in _uoms) {
      if (u.uom.toUpperCase() == value.toUpperCase()) {
        opt = u;
        break;
      }
    }
    setState(() {
      _uom = value;
      if (opt != null && opt.rate > 0) {
        _cost.text = opt.rate.toStringAsFixed(2);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final newQtyColor = _newQty < 0 ? const Color(0xFFC62828) : const Color(0xFF2E7D32);

    return AlertDialog(
      title: Text(widget.itemName, maxLines: 2, overflow: TextOverflow.ellipsis),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.itemCode,
              style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
            ),
            const SizedBox(height: 8),
            if (_loadingStock)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 4),
                child: LinearProgressIndicator(minHeight: 2),
              )
            else
              Text(
                'Current stock (store ${widget.store}): ${_fmtStock(_currentStock)}',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
              ),
            if (_uomError != null) ...[
              const SizedBox(height: 8),
              Text(_uomError!, style: const TextStyle(fontSize: 12, color: Color(0xFFC62828))),
            ],
            const SizedBox(height: 14),
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(
                  value: true,
                  label: Text('Increase'),
                  icon: Icon(Icons.arrow_upward_rounded, size: 16),
                ),
                ButtonSegment(
                  value: false,
                  label: Text('Decrease'),
                  icon: Icon(Icons.arrow_downward_rounded, size: 16),
                ),
              ],
              selected: {_isIncrease},
              onSelectionChanged: (s) => setState(() => _isIncrease = s.first),
            ),
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
                'Conversion factor: ${_fmtFactor(_selectedUom?.factor ?? 1)}',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
              ),
            ],
            const SizedBox(height: 12),
            NumericTextField(
              controller: _qty,
              autofocus: true,
              selectAllOnFocus: true,
              labelText: 'Adjust quantity',
              textInputAction: TextInputAction.next,
            ),
            const SizedBox(height: 12),
            NumericTextField(
              controller: _cost,
              selectAllOnFocus: true,
              labelText: 'Rate / cost',
              textInputAction: TextInputAction.done,
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: newQtyColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Text(
                    'New qty',
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
                  ),
                  const Spacer(),
                  Text(
                    _fmtStock(_newQty),
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: newQtyColor),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: _accent),
          onPressed: _loadingUoms
              ? null
              : () {
                  final q = double.tryParse(_qty.text.trim().replaceAll(',', '')) ?? 0;
                  final c = double.tryParse(_cost.text.trim().replaceAll(',', '')) ?? -1;
                  if (q <= 0) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Enter a quantity greater than zero.')),
                    );
                    return;
                  }
                  if (c < 0) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Enter a valid rate / cost.')),
                    );
                    return;
                  }
                  if (!_isIncrease && _newQty < 0) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('New quantity cannot be negative for this store.')),
                    );
                    return;
                  }
                  final signed = _isIncrease ? q : -q;
                  Navigator.pop(
                    context,
                    _SaLineEditResult(
                      adjustQty: signed,
                      cost: c,
                      uom: _uom,
                      currentQty: _currentStock,
                      factor: _selectedUom?.factor ?? 1,
                      isIncrease: _isIncrease,
                    ),
                  );
                },
          child: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}

class _WarehousePickerSheet extends StatelessWidget {
  const _WarehousePickerSheet({required this.warehouses});

  final List<StockAdjustmentWarehouse> warehouses;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
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
          const Text('Select warehouse / store', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 12),
          if (warehouses.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(child: Text('No warehouses found.', style: TextStyle(color: Colors.grey.shade600))),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.45),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: warehouses.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final w = warehouses[i];
                  final label = w.label;
                  return ListTile(
                    onTap: () => Navigator.pop(context, w),
                    title: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
                    subtitle: Text(
                      [
                        if (w.code.isNotEmpty) w.code,
                        if (w.allowNegativeStock) 'Allows negative stock',
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

class _SaSavedDialog extends StatefulWidget {
  const _SaSavedDialog({
    required this.result,
    this.stockValue = 0,
  });

  final StockAdjustmentSaveResult result;
  final double stockValue;

  @override
  State<_SaSavedDialog> createState() => _SaSavedDialogState();
}

class _SaSavedDialogState extends State<_SaSavedDialog> {
  static const _accent = Color(0xFFEF6C00);
  static const _titleColor = Color(0xFF262C50);

  bool _pdfBusy = false;
  String? _pdfError;

  Future<File> _writePdfFile() async {
    final bytes = await context.read<StockAdjustmentService>().downloadPdf(widget.result.adjNo);
    final dir = await getTemporaryDirectory();
    final safe = widget.result.adjNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/SA_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _viewPdf() async {
    if (_pdfBusy || widget.result.adjNo.trim().isEmpty) return;
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
    if (_pdfBusy || widget.result.adjNo.trim().isEmpty) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final file = await _writePdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'Stock Adjustment ${widget.result.adjNo}',
        text: 'Stock Adjustment SA-${widget.result.adjNo}',
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
    final value = result.stockValue > 0 ? result.stockValue : widget.stockValue;

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
            const Text(
              'Stock Adjustment saved',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: _titleColor),
            ),
            const SizedBox(height: 6),
            Text(
              'SA-${result.adjNo}',
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: _accent, height: 1.1),
            ),
            const SizedBox(height: 6),
            Text(
              result.status,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Colors.grey.shade700),
            ),
            if (value > 0) ...[
              const SizedBox(height: 14),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFF6F7FC),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Text('Stock value', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                    const Spacer(),
                    Text(
                      value.toStringAsFixed(2),
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
                    ),
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
                  side: const BorderSide(color: Color(0xFFFFCC80)),
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
