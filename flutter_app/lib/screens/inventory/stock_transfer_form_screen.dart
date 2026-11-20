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
import '../../core/utils/barcode_utils.dart';
import '../../models/stock_transfer.dart';
import '../../providers/auth_provider.dart';
import '../../services/stock_transfer_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/numeric_text_field.dart';
import '../barcode_scanner_screen.dart';
import 'inventory_transaction_draft.dart';
import '../../core/theme/app_theme.dart';

class StockTransferFormScreen extends StatefulWidget {
  const StockTransferFormScreen({super.key, this.transferNo, this.restoreDraft = false});

  final String? transferNo;

  /// When true, restores the in-session draft after open context loads (create only).
  final bool restoreDraft;

  @override
  State<StockTransferFormScreen> createState() => _StockTransferFormScreenState();
}

class _StockTransferFormScreenState extends State<StockTransferFormScreen>
    with WidgetsBindingObserver {
  static const _accent = Color(0xFF1565C0);

  final _remarksCtrl = TextEditingController();
  final _searchCtrl = TextEditingController();

  bool _loading = true;
  bool _busy = false;
  bool _pdfBusy = false;
  bool _itemSearchLoading = false;
  String? _error;
  Object? _errorCause;

  String _transferNo = '';
  String _transferDate = '';
  String _status = 'C';
  String _statusLabel = 'Created';
  bool _canEdit = true;
  bool _savedOnServer = false;

  List<StockTransferStore> _stores = [];
  String? _fromStore;
  String? _toStore;
  final List<StockTransferLine> _lines = [];
  List<StockTransferItemOption> _searchResults = [];

  Timer? _searchDebounce;
  int _searchRequestGen = 0;
  Timer? _draftDebounce;
  String _draftTenantId = '';
  String _draftUsername = '';
  bool _draftCleared = false;

  StockTransferService get _svc => context.read<StockTransferService>();

  bool get _isEditingExisting => (widget.transferNo ?? '').trim().isNotEmpty;

  bool get _searchActive => _searchCtrl.text.trim().isNotEmpty;

  bool get _storesLocked => !_canEdit || _lines.isNotEmpty;

  bool get _canPickFromStore => _canEdit && !_storesLocked && _toStore == null;

  bool get _canPickToStore => _canEdit && !_storesLocked && _fromStore != null && _toStore == null;

  bool get _canChangeStores => _canEdit && _lines.isEmpty;

  bool get _updateExistingOnSave => _isEditingExisting || _savedOnServer;

  String _storeShort(String? code) {
    if (code == null || code.isEmpty) return '—';
    for (final s in _stores) {
      if (s.code == code) {
        if (s.description.isNotEmpty && s.description.length <= 18) {
          return '${s.code} · ${s.description}';
        }
        return s.code;
      }
    }
    return code;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _transferDate = '';
    _searchCtrl.addListener(_onSearchChanged);
    _remarksCtrl.addListener(_scheduleDraftSave);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = context.read<AuthProvider>().user;
      _draftTenantId = user?.tenantId ?? '';
      _draftUsername = user?.username ?? '';
      _bootstrap();
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
    _remarksCtrl.removeListener(_scheduleDraftSave);
    _searchDebounce?.cancel();
    _draftDebounce?.cancel();
    _remarksCtrl.dispose();
    _searchCtrl.dispose();
    super.dispose();
  }

  void _scheduleDraftSave() {
    if (_isEditingExisting || _savedOnServer || _draftCleared || _loading || _busy) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), _persistDraft);
  }

  Map<String, dynamic> _encodeStoreCode(String? code) {
    if (code == null || code.trim().isEmpty) return {};
    String name = '';
    for (final s in _stores) {
      if (s.code == code) {
        name = s.description;
        break;
      }
    }
    return InventoryTransactionDraft.encodeStore(code: code, name: name);
  }

  bool get _hasMeaningfulDraft {
    final fromSet = (_fromStore ?? '').trim().isNotEmpty;
    final toSet = (_toStore ?? '').trim().isNotEmpty;
    return InventoryTransactionDraft.isMeaningful(
      remarks: _remarksCtrl.text,
      lines: _lines,
      other: fromSet || toSet,
    );
  }

  Future<void> _persistDraft() async {
    if (_isEditingExisting || _savedOnServer || _draftCleared || _busy) return;
    if (!_hasMeaningfulDraft) return;
    if (_draftUsername.isEmpty) return;
    final draft = <String, dynamic>{
      'from_store': _encodeStoreCode(_fromStore),
      'to_store': _encodeStoreCode(_toStore),
      'remarks': _remarksCtrl.text,
      'party_name': [
        if ((_fromStore ?? '').trim().isNotEmpty) _fromStore!.trim(),
        if ((_toStore ?? '').trim().isNotEmpty) _toStore!.trim(),
      ].join(' → '),
      'lines': _lines
          .map(
            (l) => <String, dynamic>{
              'sl_no': l.slNo,
              'item_code': l.itemCode,
              'item_name': l.itemName,
              'uom': l.uom,
              'available_qty': l.availableQty,
              'transfer_qty': l.transferQty,
              'remarks': l.remarks,
            },
          )
          .toList(),
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.stockTransfer,
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
      docType: TransactionDraftType.stockTransfer,
      tenantId: _draftTenantId,
      username: _draftUsername,
    );
  }

  void _applyDraft(Map<String, dynamic> draft) {
    _fromStore = InventoryTransactionDraft.storeCodeOf(draft['from_store']);
    _toStore = InventoryTransactionDraft.storeCodeOf(draft['to_store']);
    _remarksCtrl.text = '${draft['remarks'] ?? ''}';
    final linesRaw = (draft['lines'] as List?) ?? const [];
    final lines = <StockTransferLine>[];
    for (var i = 0; i < linesRaw.length; i++) {
      final m = InventoryTransactionDraft.lineAt(linesRaw, i);
      if (m == null) continue;
      final itemCode = InventoryTransactionDraft.intOf(m['item_code']);
      if (itemCode <= 0) continue;
      final slNo = InventoryTransactionDraft.intOf(m['sl_no']);
      lines.add(
        StockTransferLine(
          slNo: slNo > 0 ? slNo : i + 1,
          itemCode: itemCode,
          itemName: '${m['item_name'] ?? ''}'.trim(),
          uom: '${m['uom'] ?? 'NOS'}'.trim().isEmpty ? 'NOS' : '${m['uom']}'.trim(),
          availableQty: InventoryTransactionDraft.numOf(m['available_qty']),
          transferQty: InventoryTransactionDraft.numOf(m['transfer_qty']),
          remarks: '${m['remarks'] ?? ''}'.trim(),
        ),
      );
    }
    _lines
      ..clear()
      ..addAll(lines);
  }

  void _onSearchChanged() {
    if (!mounted) return;
    setState(() {});
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 400), () {
      if (mounted) unawaited(_fetchSearchResults());
    });
  }

  bool _ensureStoresSelected({bool notify = false}) {
    final from = _fromStore;
    if (from == null || from.isEmpty) {
      if (notify) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Select From store first')),
        );
      }
      return false;
    }
    if (_toStore == null || _toStore!.isEmpty) {
      if (notify) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Select To store first')),
        );
      }
      return false;
    }
    return true;
  }

  Future<List<StockTransferItemOption>> _querySearchItems({
    required String fromStore,
    required String query,
  }) async {
    var items = await _svc.searchItems(fromStore: fromStore, search: query);
    if (items.isEmpty && query.isNotEmpty) {
      final numericOnly = RegExp(r'^\d+$').hasMatch(query);
      if (numericOnly) {
        final ic = int.tryParse(query);
        if (ic != null && ic > 0) {
          items = await _svc.searchItems(fromStore: fromStore, exactItemCode: ic);
        }
      }
      if (items.isEmpty) {
        items = await _svc.searchItems(fromStore: fromStore, exactBarcode: query);
      }
    }
    return items;
  }

  Future<void> _bootstrap() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      _stores = await _svc.listStores();
      if ((widget.transferNo ?? '').trim().isNotEmpty) {
        final detail = await _svc.getTransfer(widget.transferNo!);
        if (detail == null) throw Exception('Transfer not found');
        _transferNo = detail.transferNo;
        _transferDate = detail.transferDate.length >= 10 ? detail.transferDate.substring(0, 10) : detail.transferDate;
        _status = detail.status;
        _statusLabel = detail.statusLabel;
        _canEdit = detail.canEdit;
        _fromStore = detail.fromStore.isNotEmpty ? detail.fromStore : null;
        _toStore = detail.toStore.isNotEmpty ? detail.toStore : null;
        _remarksCtrl.text = detail.remarks;
        _lines
          ..clear()
          ..addAll(detail.lines);
        _savedOnServer = true;
      } else {
        final open = await _svc.getOpenContext();
        _transferNo = open.transferNo;
        if (open.transferDate.isNotEmpty) {
          _transferDate = open.transferDate;
        }
        if (widget.restoreDraft && _draftUsername.isNotEmpty) {
          final draft = await TransactionDraftStorage.read(
            docType: TransactionDraftType.stockTransfer,
            tenantId: _draftTenantId,
            username: _draftUsername,
          );
          if (!mounted) return;
          if (draft != null) {
            _applyDraft(draft);
          }
        }
      }
      if (!mounted) return;
      setState(() => _loading = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _clearSearchArea() async {
    _searchRequestGen++;
    _searchCtrl.clear();
    if (!mounted) return;
    setState(() {
      _searchResults = [];
      _itemSearchLoading = false;
    });
    FocusScope.of(context).unfocus();
  }

  Future<void> _fetchSearchResults({
    bool fromSubmit = false,
    bool fromScan = false,
    String? scannedForMatch,
  }) async {
    final query = _searchCtrl.text.trim();
    if (query.isEmpty) {
      if (!mounted) return;
      setState(() {
        _searchResults = [];
        _itemSearchLoading = false;
      });
      return;
    }

    if (!_ensureStoresSelected(notify: fromSubmit || fromScan)) {
      if (!mounted) return;
      setState(() {
        _searchResults = [];
        _itemSearchLoading = false;
      });
      return;
    }

    final from = _fromStore!;
    final gen = ++_searchRequestGen;
    setState(() {
      _itemSearchLoading = true;
      _searchResults = [];
    });

    try {
      final items = await _querySearchItems(fromStore: from, query: query);
      if (!mounted || gen != _searchRequestGen) return;
      setState(() {
        _searchResults = items;
        _itemSearchLoading = false;
      });

      if (items.isEmpty) {
        if (fromSubmit || fromScan) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                fromScan
                    ? 'No item with stock in $from matches barcode "$query".'
                    : 'No items with stock in $from match your search',
              ),
            ),
          );
        }
        return;
      }

      if (fromScan) {
        final match = scannedForMatch != null ? _matchItemForBarcode(scannedForMatch, items) : null;
        if (match != null) {
          await _openTransferQtyDialog(match);
          return;
        }
        if (items.length == 1) {
          await _openTransferQtyDialog(items.first);
        }
        return;
      }

      if (fromSubmit && items.length == 1) {
        await _openTransferQtyDialog(items.first);
      }
    } catch (e) {
      if (!mounted || gen != _searchRequestGen) return;
      setState(() => _itemSearchLoading = false);
      if (fromSubmit || fromScan) {
        showApiErrorSnackBar(context, e, authenticatedContext: true);
      }
    }
  }

  Future<void> _runSearch() => _fetchSearchResults(fromSubmit: true);

  StockTransferItemOption? _matchItemForBarcode(String scanned, List<StockTransferItemOption> items) {
    final raw = scanned.trim();
    if (raw.isEmpty || items.isEmpty) return null;

    for (final it in items) {
      if (inventoryItemMatchesScan(
        itemCode: '${it.itemCode}',
        itemBarcode: it.barcode,
        scanned: raw,
      )) {
        return it;
      }
    }
    return null;
  }

  Future<void> _scanBarcode() async {
    if (!_canEdit || _busy) return;
    if (!_ensureStoresSelected(notify: true)) return;

    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => const BarcodeScannerScreen(title: 'Scan item barcode'),
      ),
    );
    if (!mounted || code == null || code.trim().isEmpty) return;

    final trimmed = code.trim();
    _searchCtrl.text = trimmed;
    await _fetchSearchResults(fromScan: true, scannedForMatch: trimmed);
  }

  Future<void> _openTransferQtyDialog(StockTransferItemOption item) async {
    if (!_canEdit || _busy) return;

    final from = _fromStore;
    if (from == null || from.isEmpty) return;

    final existingIdx = _lines.indexWhere((ln) => ln.itemCode == item.itemCode);
    final existingQty = existingIdx >= 0 ? _lines[existingIdx].transferQty : null;

    var effectiveItem = item;
    try {
      final stock = await _svc.getItemStock(itemCode: item.itemCode, store: from);
      effectiveItem = StockTransferItemOption(
        itemCode: item.itemCode,
        itemName: item.itemName,
        uom: item.uom,
        availableQty: stock.currentQty,
        barcode: item.barcode,
        actualQty: stock.actualQty > 0 ? stock.actualQty : stock.currentQty,
        pendingQty: stock.pendingQty,
      );
    } catch (_) {
      // Fall back to search payload when live stock lookup fails.
    }

    if (!mounted) return;

    final qty = await showDialog<double>(
      context: context,
      builder: (ctx) => _TransferQtyDialog(
        item: effectiveItem,
        existingQty: existingQty,
        formatQty: _formatQty,
      ),
    );

    if (!mounted || qty == null) return;
    _addLine(effectiveItem, qty);
    await _clearSearchArea();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Added ${_formatQty(qty)} ${item.uom} · ${item.itemCode}')),
    );
  }

  void _addLine(StockTransferItemOption item, double qty) {
    final existingIdx = _lines.indexWhere((ln) => ln.itemCode == item.itemCode);
    setState(() {
      if (existingIdx >= 0) {
        final prev = _lines[existingIdx];
        _lines[existingIdx] = StockTransferLine(
          slNo: prev.slNo,
          itemCode: prev.itemCode,
          itemName: prev.itemName,
          uom: prev.uom,
          availableQty: item.availableQty,
          transferQty: prev.transferQty + qty,
          remarks: prev.remarks,
        );
      } else {
        _lines.add(
          StockTransferLine(
            slNo: _lines.length + 1,
            itemCode: item.itemCode,
            itemName: item.itemName,
            uom: item.uom,
            availableQty: item.availableQty,
            transferQty: qty,
          ),
        );
      }
    });
    _scheduleDraftSave();
  }

  String _formatQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  Future<void> _clearStores() async {
    if (!_canChangeStores) return;
    _searchDebounce?.cancel();
    _searchRequestGen++;
    _searchCtrl.clear();
    if (!mounted) return;
    setState(() {
      _fromStore = null;
      _toStore = null;
      _searchResults = [];
      _itemSearchLoading = false;
    });
    _scheduleDraftSave();
    FocusScope.of(context).unfocus();
  }

  Future<void> _pickStore({required bool forFrom, bool changing = false}) async {
    if (changing) {
      if (!_canChangeStores) return;
      if (!forFrom && (_fromStore == null || _fromStore!.isEmpty)) return;
    } else {
      if (forFrom ? !_canPickFromStore : !_canPickToStore) return;
    }
    final blocked = forFrom ? _toStore : _fromStore;
    final options = _stores.where((s) {
      if (blocked != null && s.code == blocked) return false;
      return s.code.isNotEmpty;
    }).toList();

    if (options.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No stores available')),
      );
      return;
    }

    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _StorePickerSheet(
        title: forFrom ? 'From store' : 'To store',
        stores: options,
      ),
    );

    if (!mounted || picked == null || picked.isEmpty) return;
    _searchDebounce?.cancel();
    _searchRequestGen++;
    _searchCtrl.clear();
    setState(() {
      if (forFrom) {
        _fromStore = picked;
        if (_toStore == picked) _toStore = null;
      } else {
        _toStore = picked;
      }
      _searchResults = [];
      _itemSearchLoading = false;
    });
    _scheduleDraftSave();
  }

  Future<void> _editRemarks() async {
    final ctrl = TextEditingController(text: _remarksCtrl.text);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remarks'),
        content: TextField(
          controller: ctrl,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'Optional notes',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok == true && mounted) {
      setState(() => _remarksCtrl.text = ctrl.text.trim());
      _scheduleDraftSave();
    }
    ctrl.dispose();
  }

  Future<void> _save() async {
    if (_busy) return;
    if (_fromStore == null || _toStore == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select From store and To store')),
      );
      return;
    }
    if (_lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add at least one line')),
      );
      return;
    }
    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save stock transfer?',
      message: _transferNo.isNotEmpty
          ? 'Save transfer $_transferNo with ${_lines.length} line(s)?'
          : 'Save new transfer with ${_lines.length} line(s)?',
      confirmLabel: 'Save',
    );
    if (!confirmed || !mounted) return;
    final previousNo = _transferNo;
    setState(() => _busy = true);
    try {
      final result = await _svc.saveTransfer(
        transferNo: _transferNo,
        transferDate: _transferDate,
        fromStore: _fromStore!,
        toStore: _toStore!,
        remarks: _remarksCtrl.text.trim(),
        lines: _lines,
        updateExisting: _updateExistingOnSave,
      );
      if (!mounted) return;
      setState(() {
        _transferNo = result.transferNo;
        _status = 'C';
        _statusLabel = 'Created';
        _canEdit = true;
        _savedOnServer = true;
        _busy = false;
      });
      await _clearDraft();
      final no = result.transferNo;
      final message = result.wasReassigned && previousNo.isNotEmpty
          ? 'Transfer $previousNo already exists — saved as $no'
          : 'Saved transfer $no';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  Future<void> _postTransfer() async {
    if (_transferNo.isEmpty) return;
    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Send to transit?',
      message: 'Transfer $_transferNo to transit?',
      confirmLabel: 'Transfer',
    );
    if (!confirmed || !mounted) return;
    setState(() => _busy = true);
    try {
      await _svc.postTransfer(_transferNo);
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      await _bootstrap();
      if (!mounted) return;
      setState(() => _busy = false);
      messenger.showSnackBar(
        SnackBar(content: Text('Transfer $_transferNo sent to transit')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  Future<void> _approve() async {
    if (_transferNo.isEmpty) return;
    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Approve transfer?',
      message: 'Approve transfer $_transferNo and receive into destination?',
      confirmLabel: 'Approve',
      confirmColor: const Color(0xFF2E7D32),
    );
    if (!confirmed || !mounted) return;
    setState(() => _busy = true);
    try {
      await _svc.approveTransfer(_transferNo);
      if (!mounted) return;
      final messenger = ScaffoldMessenger.of(context);
      await _bootstrap();
      if (!mounted) return;
      setState(() => _busy = false);
      messenger.showSnackBar(
        SnackBar(content: Text('Transfer $_transferNo approved')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  Future<File> _writeTransferPdfFile() async {
    final bytes = await _svc.downloadTransferPdf(_transferNo);
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/store_transfer_$_transferNo.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy || _transferNo.isEmpty) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writeTransferPdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'Stock Transfer $_transferNo',
        text: 'Stock Transfer $_transferNo',
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _printCopy() async {
    if (_pdfBusy || _transferNo.isEmpty) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writeTransferPdfFile();
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(opened.message.isNotEmpty ? opened.message : 'Could not open PDF.')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final subtitle = [
      _statusLabel,
      if (_transferDate.isNotEmpty) _transferDate,
      if (_transferNo.isNotEmpty) _transferNo,
      '${_lines.length} line(s)',
    ].join(' · ');

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              _transferNo.isNotEmpty ? 'Transfer $_transferNo' : 'New transfer',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
            ),
            Text(
              subtitle,
              style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
            ),
          ],
        ),
        centerTitle: true,
        actions: [
          if (_transferNo.isNotEmpty)
            IconButton(
              tooltip: 'Share PDF',
              onPressed: (_busy || _pdfBusy || _loading) ? null : _sharePdf,
              icon: _pdfBusy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.share_outlined),
            ),
          if (_transferNo.isNotEmpty)
            IconButton(
              tooltip: 'Print copy',
              onPressed: (_busy || _pdfBusy || _loading) ? null : _printCopy,
              icon: const Icon(Icons.picture_as_pdf_outlined),
            ),
          if (_canEdit)
            IconButton(
              tooltip: 'Remarks',
              onPressed: _busy ? null : _editRemarks,
              icon: Badge(
                isLabelVisible: _remarksCtrl.text.trim().isNotEmpty,
                smallSize: 8,
                child: const Icon(Icons.notes_rounded, size: 22),
              ),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ApiErrorCenter(message: _error!, error: _errorCause)
              : Stack(
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _buildCompactRouteBar(),
                        if (_canEdit) _buildSearchBar(),
                        if (_itemSearchLoading)
                          const LinearProgressIndicator(minHeight: 2),
                        Expanded(child: _buildMainList()),
                      ],
                    ),
                    if (_busy)
                      const ColoredBox(
                        color: Color(0x44FFFFFF),
                        child: Center(child: CircularProgressIndicator()),
                      ),
                  ],
                ),
      bottomNavigationBar: _loading || _error != null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_canEdit)
                      FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: _accent,
                          minimumSize: const Size(double.infinity, 52),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                        ),
                        onPressed: _busy || _itemSearchLoading ? null : _scanBarcode,
                        icon: const Icon(Icons.photo_camera_outlined),
                        label: const Text('Scan Item', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                      ),
                    if (_canEdit) const SizedBox(height: 8),
                    Row(
                      children: [
                        if (_canEdit)
                          Expanded(
                            child: FilledButton(
                              onPressed: _busy ? null : _save,
                              style: FilledButton.styleFrom(
                                backgroundColor: _accent,
                                minimumSize: const Size(0, 44),
                              ),
                              child: const Text('Save'),
                            ),
                          ),
                        if (_canEdit && _status == 'C' && _transferNo.isNotEmpty) const SizedBox(width: 8),
                        if (_status == 'C' && _transferNo.isNotEmpty)
                          Expanded(
                            child: FilledButton.tonal(
                              onPressed: _busy ? null : _postTransfer,
                              style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
                              child: const Text('Transfer'),
                            ),
                          ),
                        if ((_status == 'T' || _status == 'P') && _transferNo.isNotEmpty)
                          Expanded(
                            child: FilledButton.tonal(
                              onPressed: _busy ? null : _approve,
                              style: FilledButton.styleFrom(
                                backgroundColor: const Color(0xFF2E7D32),
                                foregroundColor: Colors.white,
                                minimumSize: const Size(0, 44),
                              ),
                              child: const Text('Approve'),
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
    );
  }

  Widget _buildCompactRouteBar() {
    return Material(
      color: Colors.white,
      child: InkWell(
        onTap: _canEdit && !_storesLocked
            ? () {
                if (_fromStore == null) {
                  _pickStore(forFrom: true);
                } else if (_toStore == null) {
                  _pickStore(forFrom: false);
                }
              }
            : null,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: Colors.grey.shade200)),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('FROM', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Colors.grey.shade500)),
                    const SizedBox(height: 2),
                    Text(
                      _storeShort(_fromStore),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: _fromStore != null ? const Color(0xFF262C50) : Colors.grey.shade500,
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Icon(Icons.arrow_forward_rounded, size: 18, color: Colors.grey.shade400),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('TO', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Colors.grey.shade500)),
                    const SizedBox(height: 2),
                    Text(
                      _storeShort(_toStore),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.end,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: _toStore != null ? const Color(0xFF262C50) : Colors.grey.shade500,
                      ),
                    ),
                  ],
                ),
              ),
              if (_canEdit) ...[
                const SizedBox(width: 6),
                IconButton(
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                  tooltip: 'Change stores',
                  onPressed: _busy
                      ? null
                      : () async {
                          if (!_canChangeStores) {
                            if (_lines.isNotEmpty) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Remove all lines to change stores')),
                              );
                            }
                            return;
                          }
                          final action = await showModalBottomSheet<String>(
                            context: context,
                            backgroundColor: Colors.transparent,
                            builder: (ctx) => SafeArea(
                              child: Container(
                                margin: const EdgeInsets.fromLTRB(12, 0, 12, 16),
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    ListTile(
                                      title: const Text('Change From store'),
                                      onTap: () => Navigator.pop(ctx, 'from'),
                                    ),
                                    ListTile(
                                      title: const Text('Change To store'),
                                      onTap: () => Navigator.pop(ctx, 'to'),
                                    ),
                                    const Divider(height: 1),
                                    ListTile(
                                      title: Text('Clear stores', style: TextStyle(color: Colors.red.shade700)),
                                      onTap: () => Navigator.pop(ctx, 'clear'),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          );
                          if (!mounted || action == null) return;
                          if (action == 'clear') {
                            await _clearStores();
                            return;
                          }
                          // Wait one frame so the menu sheet finishes closing before opening the picker.
                          await Future<void>.delayed(Duration.zero);
                          if (!mounted) return;
                          await _pickStore(
                            forFrom: action == 'from',
                            changing: true,
                          );
                        },
                  icon: Icon(Icons.edit_location_alt_outlined, size: 20, color: Colors.grey.shade600),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSearchBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: TextField(
        controller: _searchCtrl,
        textInputAction: TextInputAction.search,
        style: const TextStyle(fontSize: 14),
        decoration: InputDecoration(
          hintText: 'Search items by name or SKU',
          hintStyle: TextStyle(color: Colors.grey.shade500, fontSize: 14),
          prefixIcon: Icon(Icons.search_rounded, color: Colors.grey.shade500),
          suffixIcon: _searchCtrl.text.trim().isNotEmpty
              ? IconButton(
                  icon: Icon(Icons.clear_rounded, color: Colors.grey.shade700),
                  tooltip: 'Clear search',
                  onPressed: _busy || _itemSearchLoading ? null : _clearSearchArea,
                )
              : null,
          filled: true,
          fillColor: Colors.white,
          contentPadding: const EdgeInsets.symmetric(vertical: 12),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade200),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(color: Colors.grey.shade200),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: _accent, width: 1.5),
          ),
        ),
        onSubmitted: (_) => _runSearch(),
      ),
    );
  }

  Widget _buildMainList() {
    if (_searchActive || (_itemSearchLoading && _searchResults.isEmpty)) {
      return _buildSearchResultsList();
    }
    return _buildLinesList();
  }

  Widget _buildSearchResultsList() {
    if (_itemSearchLoading && _searchResults.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (!_itemSearchLoading && _searchResults.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.search_off_rounded, size: 48, color: Colors.grey.shade400),
              const SizedBox(height: 12),
              Text(
                'No items match "${_searchCtrl.text.trim()}"',
                textAlign: TextAlign.center,
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
              ),
              const SizedBox(height: 6),
              Text(
                'Try another name, SKU, or barcode.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: Text(
            '${_searchResults.length} item(s) — tap to add',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.grey.shade600),
          ),
        ),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
            itemCount: _searchResults.length,
            separatorBuilder: (_, __) => const SizedBox(height: 4),
            itemBuilder: (context, index) => _buildSearchResultRow(_searchResults[index]),
          ),
        ),
      ],
    );
  }

  Widget _buildSearchResultRow(StockTransferItemOption item) {
    final inLines = _lines.any((ln) => ln.itemCode == item.itemCode);
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: _canEdit && !_busy ? () => _openTransferQtyDialog(item) : null,
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade200),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${item.itemCode}',
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
                    ),
                    if (item.itemName.isNotEmpty)
                      Text(
                        item.itemName,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade700, height: 1.25),
                      ),
                    if (item.barcode.isNotEmpty)
                      Text(
                        item.barcode,
                        style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                      ),
                    if (item.pendingQty > 0)
                      Text(
                        'Pending approval: ${_formatQty(item.pendingQty)} ${item.uom}',
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFFE65100)),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${_formatQty(item.availableQty)} ${item.uom}',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: item.availableQty > 0 ? const Color(0xFF2E7D32) : Colors.grey.shade600,
                    ),
                  ),
                  if (inLines)
                    Text(
                      'on transfer',
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: Colors.grey.shade500),
                    ),
                ],
              ),
              const SizedBox(width: 4),
              Icon(Icons.add_circle_outline, size: 22, color: _accent.withValues(alpha: 0.9)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLinesList() {
    if (_lines.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.inventory_2_outlined, size: 48, color: Colors.grey.shade400),
              const SizedBox(height: 12),
              Text(
                _canEdit ? 'No lines yet' : 'No lines on this transfer',
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
              ),
              const SizedBox(height: 6),
              Text(
                _canEdit ? 'Use search or tap Scan Item to add items.' : '',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
              ),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
      itemCount: _lines.length,
      itemBuilder: (context, index) => _buildLineRow(_lines[index], index + 1),
    );
  }

  Widget _buildLineRow(StockTransferLine ln, int rowNo) {
    return Material(
      color: Colors.white,
      child: InkWell(
        onTap: _canEdit && !_busy
            ? () async {
                final item = StockTransferItemOption(
                  itemCode: ln.itemCode,
                  itemName: ln.itemName,
                  uom: ln.uom,
                  availableQty: ln.availableQty,
                  barcode: '',
                );
                await _openTransferQtyDialog(item);
              }
            : null,
        child: Container(
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: Colors.grey.shade200)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Row(
            children: [
              SizedBox(
                width: 28,
                child: Text(
                  '$rowNo',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.grey.shade500),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${ln.itemCode}',
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                    ),
                    if (ln.itemName.isNotEmpty)
                      Text(
                        ln.itemName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                      ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${_formatQty(ln.transferQty)} ${ln.uom}',
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: _accent),
                  ),
                  Text(
                    'avail ${_formatQty(ln.availableQty)}',
                    style: TextStyle(fontSize: 10.5, color: Colors.grey.shade500),
                  ),
                ],
              ),
              if (_canEdit)
                IconButton(
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.only(left: 4),
                  constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                  icon: Icon(Icons.close_rounded, size: 20, color: Colors.grey.shade500),
                  onPressed: _busy
                      ? null
                      : () {
                          setState(() => _lines.remove(ln));
                          _scheduleDraftSave();
                        },
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StorePickerSheet extends StatefulWidget {
  const _StorePickerSheet({required this.title, required this.stores});

  final String title;
  final List<StockTransferStore> stores;

  @override
  State<_StorePickerSheet> createState() => _StorePickerSheetState();
}

class _StorePickerSheetState extends State<_StorePickerSheet> {
  final _filterCtrl = TextEditingController();
  String _filter = '';

  @override
  void dispose() {
    _filterCtrl.dispose();
    super.dispose();
  }

  List<StockTransferStore> get _filtered {
    final q = _filter.trim().toUpperCase();
    if (q.isEmpty) return widget.stores;
    return widget.stores
        .where((s) => s.code.toUpperCase().contains(q) || s.description.toUpperCase().contains(q))
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: Container(
        margin: const EdgeInsets.fromLTRB(12, 0, 12, 16),
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.65),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 8, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                  ),
                  IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                controller: _filterCtrl,
                decoration: InputDecoration(
                  hintText: 'Search store…',
                  prefixIcon: const Icon(Icons.search_rounded),
                  filled: true,
                  fillColor: const Color(0xFFF6F7FC),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  isDense: true,
                ),
                onChanged: (v) => setState(() => _filter = v),
              ),
            ),
            const SizedBox(height: 8),
            Flexible(
              child: _filtered.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text('No stores match', style: TextStyle(color: Colors.grey.shade600)),
                    )
                  : ListView.separated(
                      shrinkWrap: true,
                      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
                      itemCount: _filtered.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 6),
                      itemBuilder: (context, index) {
                        final s = _filtered[index];
                        return ListTile(
                          dense: true,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                            side: const BorderSide(color: Color(0xFFE8EBF3)),
                          ),
                          title: Text(s.code, style: const TextStyle(fontWeight: FontWeight.w700)),
                          subtitle: s.description.isNotEmpty ? Text(s.description) : null,
                          onTap: () => Navigator.pop(context, s.code),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TransferQtyDialog extends StatefulWidget {
  const _TransferQtyDialog({
    required this.item,
    required this.existingQty,
    required this.formatQty,
  });

  final StockTransferItemOption item;
  final double? existingQty;
  final String Function(double) formatQty;

  @override
  State<_TransferQtyDialog> createState() => _TransferQtyDialogState();
}

class _TransferQtyDialogState extends State<_TransferQtyDialog> {
  final _qtyCtrl = TextEditingController(text: '1');
  bool _submitting = false;

  double get _existingOnLine => widget.existingQty ?? 0;

  double get _maxAddQty {
    final remaining = widget.item.availableQty - _existingOnLine;
    return remaining > 0 ? remaining : 0;
  }

  @override
  void dispose() {
    _qtyCtrl.dispose();
    super.dispose();
  }

  void _save() {
    if (_submitting) return;
    final v = double.tryParse(_qtyCtrl.text.trim().replaceAll(',', ''));
    if (v == null || v <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid transfer quantity')),
      );
      return;
    }

    final maxAdd = _maxAddQty;
    final newLineTotal = _existingOnLine + v;
    if (newLineTotal > widget.item.availableQty + 0.0001) {
      final item = widget.item;
      final parts = <String>[
        'Available: ${widget.formatQty(item.availableQty)} ${item.uom}',
      ];
      if (item.actualQty > item.availableQty || item.pendingQty > 0) {
        parts.add('On hand: ${widget.formatQty(item.actualQty > 0 ? item.actualQty : item.availableQty)} ${item.uom}');
      }
      if (item.pendingQty > 0) {
        parts.add('Pending approval: ${widget.formatQty(item.pendingQty)} ${item.uom}');
      }
      if (_existingOnLine > 0) {
        parts.add('Already on this transfer: ${widget.formatQty(_existingOnLine)} ${item.uom}');
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Qty exceeds available (${parts.join(' · ')}). Max add: ${widget.formatQty(maxAdd)} ${item.uom}.',
          ),
        ),
      );
      return;
    }

    setState(() => _submitting = true);
    Navigator.of(context).pop(v);
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final onHand = item.actualQty > 0 ? item.actualQty : item.availableQty;
    return AlertDialog(
      title: Text('${item.itemCode}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (item.itemName.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(item.itemName, style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
            ),
          if (item.pendingQty > 0 || onHand > item.availableQty) ...[
            Text(
              'On hand: ${widget.formatQty(onHand)} ${item.uom}',
              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
            ),
            if (item.pendingQty > 0) ...[
              const SizedBox(height: 4),
              Text(
                'Pending approval: ${widget.formatQty(item.pendingQty)} ${item.uom}',
                style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: Color(0xFFE65100)),
              ),
            ],
            const SizedBox(height: 4),
          ],
          Text(
            'Available to transfer: ${widget.formatQty(item.availableQty)} ${item.uom}',
            style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700),
          ),
          if (widget.existingQty != null) ...[
            const SizedBox(height: 4),
            Text(
              'Already on this transfer: ${widget.formatQty(widget.existingQty!)} ${item.uom}',
              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
            ),
            if (_maxAddQty > 0) ...[
              const SizedBox(height: 4),
              Text(
                'Max add now: ${widget.formatQty(_maxAddQty)} ${item.uom}',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
            ],
          ],
          const SizedBox(height: 14),
          NumericTextField(
            controller: _qtyCtrl,
            autofocus: true,
            labelText: 'Qty',
            decoration: const InputDecoration(border: OutlineInputBorder()),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _submitting ? null : _save,
          child: _submitting
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : Text(widget.existingQty != null ? 'Add' : 'Add line'),
        ),
      ],
    );
  }
}
