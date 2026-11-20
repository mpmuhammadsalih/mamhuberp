import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_client.dart';
import '../../core/utils/barcode_utils.dart';
import '../../core/network/access_denied_alert.dart';
import '../../core/network/api_error_handler.dart';
import '../../core/storage/stock_count_last_scan_storage.dart';
import '../../models/inventory_item.dart';
import '../../models/stock_count_session.dart';
import '../../providers/auth_provider.dart';
import '../../repositories/inventory_repository.dart';
import '../../repositories/stock_count_repository.dart';
import '../../services/inventory_service.dart';
import '../../services/stock_count_service.dart';
import '../barcode_scanner_screen.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/hardware_barcode_capture.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

/// Resolves [StockCountRepository] from Provider; builds one if missing after hot-reload.
StockCountRepository stockCountRepo(BuildContext context) {
  try {
    return context.read<StockCountRepository>();
  } on ProviderNotFoundException {
    return StockCountRepository(StockCountService(context.read<ApiClient>()));
  }
}

abstract class _QtyDialogResult {}

enum _ItemCountStatus { pending, counted, variance }

class _QtyDialogSaved extends _QtyDialogResult {
  _QtyDialogSaved(this.qty);

  final double qty;
}

class _ItemDbSnapshot {
  const _ItemDbSnapshot({
    required this.item,
    required this.systemQty,
    required this.countedQty,
    this.lineNo,
    required this.session,
  });

  final InventoryItem item;
  final double systemQty;
  final double? countedQty;
  final int? lineNo;
  final StockCountSession session;
}

/// Cycle count: reads ITEMMASTER, saves lines to STOCK_COUNT_HDR / STOCK_COUNT_DTL.
class StockCountScreen extends StatefulWidget {
  const StockCountScreen({
    super.key,
    required this.locationcode,
    required this.countNo,
    this.warehouseId,
  });

  final int locationcode;
  final int countNo;
  /// From list/session header; used when saving lines if session load omits it.
  final int? warehouseId;

  @override
  State<StockCountScreen> createState() => _StockCountScreenState();
}

class _StockCountScreenState extends State<StockCountScreen> with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  static const int _pageSize = 100;
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF6F7FC);
  static const _titleColor = Color(0xFF262C50);
  static const _autoRefreshInterval = Duration(seconds: 30);

  final TextEditingController _searchCtrl = TextEditingController();
  final TextEditingController _hardwareScanCtrl = TextEditingController();
  late final TabController _tabController;
  final FocusNode _scanFocusNode = FocusNode();

  final Map<String, double> _counts = {};
  final Map<String, double> _systemQty = {};
  final Map<String, int> _lineNos = {};

  StockCountSession? _session;
  bool _loading = true;
  bool _sessionLoading = true;
  bool _savingLine = false;
  String? _error;
  Object? _errorCause;

  List<InventoryItem> _items = [];
  final List<InventoryItem> _recentItems = [];

  int _catalogPage = 0;
  bool _catalogHasMore = true;
  bool _loadingMoreCatalog = false;
  Timer? _searchDebounce;

  InventoryItem? _lastScannedItem;
  String _lastScannedBarcode = '';
  double? _lastScanAddedQty;
  double? _lastScanTotalQty;

  final Map<String, InventoryItem> _lookupCache = {};
  bool _barcodeLookupInProgress = false;

  Timer? _autoRefreshTimer;
  bool _pauseAutoRefresh = false;

  bool get _isDraft =>
      _session == null || _session!.status.toUpperCase() != 'POSTED';

  int? get _effectiveWarehouseId => _session?.warehouseId ?? widget.warehouseId;

  int get _effectiveLocationcode => _session?.locationcode ?? widget.locationcode;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _autoRefreshTimer = Timer.periodic(_autoRefreshInterval, (_) => unawaited(_autoRefresh()));
    _tabController = TabController(length: 4, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging && mounted) setState(() {});
    });
    _searchCtrl.addListener(_onSearchChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    _autoRefreshTimer?.cancel();
    _searchDebounce?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    _tabController.dispose();
    _scanFocusNode.dispose();
    _searchCtrl.dispose();
    _hardwareScanCtrl.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_autoRefresh());
    }
  }

  void _applySessionLines(StockCountSession session) {
    _counts.clear();
    _systemQty.clear();
    _lineNos.clear();
    _recentItems.clear();
    for (final line in session.lines) {
      final key = line.itemcodeDisplay;
      _counts[key] = line.countedQty;
      _systemQty[key] = line.systemQty;
      if (line.lineNo > 0) _lineNos[key] = line.lineNo;
    }
    for (final line in session.lines.reversed) {
      _recentItems.add(
        InventoryItem(
          itemCode: line.itemcodeDisplay,
          itemName: '',
          unit: line.uom,
          qtyOnHand: line.systemQty,
          barcode: line.barcode,
        ),
      );
    }
  }

  /// Merge server session lines without clearing recent / last-scan UI state.
  void _mergeSessionLines(StockCountSession session) {
    _session = session;
    for (final line in session.lines) {
      final key = line.itemcodeDisplay;
      _counts[key] = line.countedQty;
      _systemQty[key] = line.systemQty;
      if (line.lineNo > 0) _lineNos[key] = line.lineNo;
    }
    _syncLastScanCountFromSession();
  }

  void _updateCatalogItem(InventoryItem fresh) {
    final idx = _items.indexWhere((e) => e.itemCode == fresh.itemCode);
    if (idx >= 0) {
      _items[idx] = fresh;
    } else {
      _items = [..._items, fresh];
    }
  }

  Future<T?> _withDbCheckLoader<T>(Future<T> Function() action) async {
    if (!mounted) return null;
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => PopScope(
        canPop: false,
        child: Center(
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(color: _accent),
                  const SizedBox(height: 14),
                  Text(
                    'Checking latest stock…',
                    style: TextStyle(fontWeight: FontWeight.w600, color: Colors.grey.shade800),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
    try {
      return await action();
    } finally {
      if (mounted) {
        Navigator.of(context, rootNavigator: true).pop();
      }
    }
  }

  Future<_ItemDbSnapshot?> _fetchItemDbSnapshot(InventoryItem item) async {
    final session = _session;
    if (session == null) return null;

    final scRepo = stockCountRepo(context);
    final invRepo = context.read<InventoryRepository>();

    final results = await Future.wait([
      scRepo.loadSession(session.locationcode, session.countNo),
      invRepo.getInventory(
        page: 1,
        pageSize: 10,
        search: item.itemCode,
        includeZero: true,
      ),
    ]);
    final freshSession = results[0] as StockCountSession;
    final invRows = results[1] as List<InventoryItem>;

    StockCountLine? line;
    for (final l in freshSession.lines) {
      if (l.itemcodeDisplay == item.itemCode) {
        line = l;
        break;
      }
    }

    InventoryItem freshItem = item;
    for (final row in invRows) {
      if (row.itemCode == item.itemCode) {
        freshItem = InventoryItem(
          itemCode: row.itemCode,
          itemName: row.itemName.isNotEmpty ? row.itemName : item.itemName,
          unit: row.unit.isNotEmpty ? row.unit : item.unit,
          qtyOnHand: row.qtyOnHand,
          barcode: row.barcode.isNotEmpty ? row.barcode : item.barcode,
        );
        break;
      }
    }

    final systemQty = freshItem.qtyOnHand;
    final countedQty = line?.countedQty;

    if (mounted) {
      setState(() {
        _mergeSessionLines(freshSession);
        _updateCatalogItem(freshItem);
        if (countedQty != null) {
          _counts[item.itemCode] = countedQty;
        }
        _systemQty[item.itemCode] = systemQty;
        if (line != null && line.lineNo > 0) {
          _lineNos[item.itemCode] = line.lineNo;
        }
      });
    }

    return _ItemDbSnapshot(
      item: freshItem,
      systemQty: systemQty,
      countedQty: countedQty,
      lineNo: line?.lineNo,
      session: freshSession,
    );
  }

  Future<void> _autoRefresh() async {
    if (!mounted || _pauseAutoRefresh || _savingLine || !_isDraft || _session == null) return;
    await _loadSession(silent: true);
  }

  /// Full item catalog (paginated) + session lines + recent scans.
  List<InventoryItem> get _catalogItems {
    final seen = <String>{};
    final ordered = <InventoryItem>[];
    for (final it in _items) {
      if (seen.add(it.itemCode)) ordered.add(it);
    }
    for (final line in _session?.lines ?? const <StockCountLine>[]) {
      final key = line.itemcodeDisplay;
      if (!seen.add(key)) continue;
      ordered.add(
        InventoryItem(
          itemCode: key,
          itemName: '',
          unit: line.uom,
          qtyOnHand: line.systemQty,
          barcode: line.barcode,
        ),
      );
    }
    for (final recent in _recentItems) {
      if (seen.add(recent.itemCode)) ordered.add(recent);
    }
    return ordered;
  }

  _ItemCountStatus _itemStatus(InventoryItem item) {
    final c = _counts[item.itemCode];
    if (c == null) return _ItemCountStatus.pending;
    final diff = c - _systemQtyFor(item);
    if (diff.abs() >= 0.0001) return _ItemCountStatus.variance;
    return _ItemCountStatus.counted;
  }

  int get _statTotal => _catalogItems.length;
  int get _statCounted =>
      _catalogItems.where((it) => _itemStatus(it) == _ItemCountStatus.counted).length;
  int get _statPending =>
      _catalogItems.where((it) => _itemStatus(it) == _ItemCountStatus.pending).length;
  int get _statVariance =>
      _catalogItems.where((it) => _itemStatus(it) == _ItemCountStatus.variance).length;

  List<InventoryItem> _itemsForTab(int tabIndex) {
    var list = _catalogItems;
    switch (tabIndex) {
      case 1:
        return list.where((it) => _itemStatus(it) == _ItemCountStatus.counted).toList();
      case 2:
        return list.where((it) => _itemStatus(it) == _ItemCountStatus.pending).toList();
      case 3:
        return list.where((it) => _itemStatus(it) == _ItemCountStatus.variance).toList();
      default:
        return list;
    }
  }

  String get _locationLabel {
    final loc = _effectiveLocationcode;
    final wh = _effectiveWarehouseId;
    if (wh != null) return 'Warehouse: $wh · Loc $loc';
    return 'Location: $loc';
  }

  void _showFilterSheet() {
    final session = _session;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.fromLTRB(20, 12, 20, 24 + MediaQuery.of(ctx).viewInsets.bottom),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Count session',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: _titleColor),
              ),
              const SizedBox(height: 14),
              _filterRow('Count #', session == null ? '…' : '${session.countNo}'),
              _filterRow('Status', session?.status ?? '…'),
              _filterRow('Location', '$_effectiveLocationcode'),
              if (_effectiveWarehouseId != null)
                _filterRow('Warehouse', '$_effectiveWarehouseId'),
              if (session?.countDate.isNotEmpty == true)
                _filterRow('Date', session!.countDate),
              Builder(
                builder: (ctx) {
                  final user = ctx.read<AuthProvider>().user?.username ?? '';
                  if (user.isEmpty) return const SizedBox.shrink();
                  return _filterRow('Counting as', user);
                },
              ),
              const SizedBox(height: 8),
              const Divider(height: 24),
              _buildSummarySection(forSheet: true),
              const SizedBox(height: 16),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: _accent,
                  minimumSize: const Size(double.infinity, 46),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                onPressed: _sessionLoading
                    ? null
                    : () async {
                        Navigator.pop(ctx);
                        await _loadSession();
                        await _loadFullCatalog();
                      },
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Reload count'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _filterRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          SizedBox(
            width: 90,
            child: Text(label, style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14, color: _titleColor),
            ),
          ),
        ],
      ),
    );
  }

  void _markRecent(InventoryItem item) {
    _recentItems.removeWhere((e) => e.itemCode == item.itemCode);
    _recentItems.insert(0, item);
    if (_recentItems.length > 25) {
      _recentItems.removeRange(25, _recentItems.length);
    }
  }

  void _recordLastScan({
    required InventoryItem item,
    required String barcode,
    required double addedQty,
    required double totalCounted,
  }) {
    _lastScannedItem = item;
    _lastScannedBarcode = barcode;
    _lastScanAddedQty = addedQty;
    _lastScanTotalQty = totalCounted;
    unawaited(_persistLastScan(
      item: item,
      barcode: barcode,
      addedQty: addedQty,
      totalCounted: totalCounted,
    ));
  }

  ({String tenantId, String username})? _userScope() {
    final user = context.read<AuthProvider>().user;
    if (user == null) return null;
    return (tenantId: user.tenantId ?? '', username: user.username);
  }

  Future<void> _persistLastScan({
    required InventoryItem item,
    required String barcode,
    required double addedQty,
    required double totalCounted,
  }) async {
    final scope = _userScope();
    if (scope == null) return;
    await StockCountLastScanStorage.save(
      tenantId: scope.tenantId,
      username: scope.username,
      record: StockCountLastScanRecord(
        itemCode: item.itemCode,
        itemName: item.itemName,
        unit: item.unit,
        qtyOnHand: _systemQtyFor(item),
        barcode: item.barcode,
        scannedBarcode: barcode,
        addedQty: addedQty,
        totalCounted: totalCounted,
      ),
    );
  }

  void _syncLastScanCountFromSession() {
    final item = _lastScannedItem;
    if (item == null) return;
    final sessionTotal = _counts[item.itemCode];
    if (sessionTotal != null) {
      _lastScanTotalQty = sessionTotal;
    }
  }

  Future<void> _loadLastScannedForUser() async {
    final scope = _userScope();
    if (scope == null || !mounted) return;

    final record = await StockCountLastScanStorage.read(
      tenantId: scope.tenantId,
      username: scope.username,
    );
    if (!mounted || record == null) return;

    var item = InventoryItem(
      itemCode: record.itemCode,
      itemName: record.itemName,
      unit: record.unit,
      qtyOnHand: record.qtyOnHand,
      barcode: record.barcode.isNotEmpty ? record.barcode : record.scannedBarcode,
    );

    for (final it in _catalogItems) {
      if (it.itemCode == record.itemCode) {
        item = InventoryItem(
          itemCode: it.itemCode,
          itemName: it.itemName.isNotEmpty ? it.itemName : record.itemName,
          unit: it.unit.isNotEmpty ? it.unit : record.unit,
          qtyOnHand: it.qtyOnHand,
          barcode: it.barcode.isNotEmpty ? it.barcode : item.barcode,
        );
        break;
      }
    }

    final sessionTotal = _counts[record.itemCode];
    setState(() {
      _lastScannedItem = item;
      _lastScannedBarcode = record.scannedBarcode;
      _lastScanAddedQty = record.addedQty;
      _lastScanTotalQty = sessionTotal ?? record.totalCounted;
    });
  }

  Future<void> _clearSearchArea() async {
    _searchCtrl.clear();
    FocusScope.of(context).unfocus();
    if (mounted) setState(() {});
  }

  double _systemQtyFor(InventoryItem item) =>
      _systemQty[item.itemCode] ?? item.qtyOnHand;

  Future<void> _bootstrap() async {
    await _loadSession();
    await _loadFullCatalog();
    await _loadLastScannedForUser();
  }

  Future<void> _loadSession({bool silent = false}) async {
    if (!mounted) return;
    if (!silent) {
      setState(() {
        _sessionLoading = true;
        _error = null;
        _errorCause = null;
      });
    }
    try {
      final repo = stockCountRepo(context);
      final session = await repo.loadSession(widget.locationcode, widget.countNo);
      if (!mounted) return;
      setState(() {
        _session = session;
        if (silent) {
          _mergeSessionLines(session);
        } else {
          _applySessionLines(session);
          _syncLastScanCountFromSession();
        }
        if (!silent) _sessionLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      if (!silent) {
        setState(() {
          _errorCause = e;
          _error = handleApiError(context, e, authenticatedContext: true);
          _sessionLoading = false;
        });
      }
    }
  }

  void _onSearchChanged() {
    if (!mounted) return;
    setState(() {});
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 400), () {
      if (mounted) unawaited(_loadFullCatalog());
    });
  }

  void _appendCatalogItems(List<InventoryItem> rows) {
    if (rows.isEmpty) return;
    final seen = _items.map((e) => e.itemCode).toSet();
    final merged = [..._items];
    for (final row in rows) {
      if (seen.add(row.itemCode)) merged.add(row);
    }
    _items = merged;
  }

  Future<void> _loadCatalogPage({required bool reset}) async {
    if (!mounted) return;
    if (reset) {
      setState(() {
        _loading = true;
        _loadingMoreCatalog = false;
        _catalogPage = 0;
        _catalogHasMore = true;
        _items = [];
        _error = null;
        _errorCause = null;
      });
    } else {
      if (!_catalogHasMore || _loadingMoreCatalog || _loading) return;
      setState(() => _loadingMoreCatalog = true);
    }

    final nextPage = reset ? 1 : _catalogPage + 1;
    try {
      final repo = context.read<InventoryRepository>();
      final rows = await repo.getInventory(
        page: nextPage,
        pageSize: _pageSize,
        search: _searchCtrl.text.trim(),
        includeZero: true,
      );
      if (!mounted) return;
      setState(() {
        if (reset) {
          _items = rows;
        } else {
          _appendCatalogItems(rows);
        }
        _catalogPage = nextPage;
        _catalogHasMore = rows.length >= _pageSize;
        _loading = false;
        _loadingMoreCatalog = false;
        if (_items.isEmpty) {
          _error = _searchCtrl.text.trim().isEmpty
              ? 'No items found in item master.'
              : 'No items match your search.';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
        _loadingMoreCatalog = false;
      });
    }
  }

  Future<void> _loadFullCatalog() => _loadCatalogPage(reset: true);

  Future<void> _loadMoreCatalog() => _loadCatalogPage(reset: false);

  void _rememberLookup(String scanned, InventoryItem item) {
    for (final q in barcodeLookupQueries(scanned)) {
      _lookupCache[q.toUpperCase()] = item;
    }
    while (_lookupCache.length > 200) {
      _lookupCache.remove(_lookupCache.keys.first);
    }
  }

  InventoryItem? _cachedLookup(String code) {
    for (final q in barcodeLookupQueries(code)) {
      final hit = _lookupCache[q.toUpperCase()];
      if (hit != null) return hit;
    }
    return null;
  }

  Future<InventoryItem?> _lookupItemFromApi(String code) async {
    final svc = context.read<InventoryService>();
    final repo = context.read<InventoryRepository>();
    final loc = _effectiveLocationcode;
    final locParam = loc > 0 ? loc : null;
    final queries = barcodeLookupQueries(code);
    if (queries.isEmpty) return null;

    final cached = _cachedLookup(code);
    if (cached != null) return cached;

    // POS lookup — run top queries in parallel for speed.
    final posQueries = queries.take(4).toList();
    final posHits = await Future.wait(
      posQueries.map((q) async {
        try {
          return await svc.lookupItem(query: q, locationcode: locParam);
        } catch (_) {
          return null;
        }
      }),
    );
    for (final item in posHits) {
      if (item != null) {
        _rememberLookup(code, item);
        return item;
      }
    }

    // Catalog fallback — try remaining query variants.
    for (final q in queries) {
      try {
        final rows = await repo.getInventory(
          page: 1,
          pageSize: 20,
          search: q,
          locationcode: locParam,
          includeZero: true,
        );
        final match = _matchItemForBarcode(code, rows);
        if (match != null) {
          _rememberLookup(code, match);
          return match;
        }
      } catch (_) {}
    }
    return null;
  }

  void _ensureCatalogItem(InventoryItem item) {
    if (_items.any((e) => e.itemCode == item.itemCode)) return;
    _items = [..._items, item];
  }

  InventoryItem? _matchItemForBarcode(String scanned, List<InventoryItem> items) {
    final raw = scanned.trim();
    if (raw.isEmpty || items.isEmpty) return null;

    for (final it in items) {
      if (inventoryItemMatchesScan(
        itemCode: it.itemCode,
        itemBarcode: it.barcode,
        scanned: raw,
      )) {
        return it;
      }
    }
    return null;
  }

  Future<void> _scanBarcode() async {
    if (!_isDraft || _session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('This count is not editable (already posted).')),
      );
      return;
    }

    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => BarcodeScannerScreen(
          title: 'Scan item barcode',
          locationcode: _effectiveLocationcode > 0 ? _effectiveLocationcode : null,
        ),
      ),
    );
    if (!mounted || code == null || code.trim().isEmpty) return;
    await _resolveScannedBarcode(code.trim());
  }

  Future<void> _resolveScannedBarcode(String code) async {
    if (!mounted) return;

    final raw = code.trim();
    final scanned = canonicalizeRetailBarcode(code) ?? normalizeBarcode(code);
    if (raw.isEmpty && scanned.isEmpty) return;

    var item = _matchItemForBarcode(raw, _catalogItems);
    item ??= scanned.isNotEmpty ? _matchItemForBarcode(scanned, _catalogItems) : null;
    item ??= _cachedLookup(raw);
    item ??= scanned.isNotEmpty ? _cachedLookup(scanned) : null;

    if (item == null) {
      setState(() => _barcodeLookupInProgress = true);
      try {
        item = await _lookupItemFromApi(raw.isNotEmpty ? raw : scanned);
      } finally {
        if (mounted) setState(() => _barcodeLookupInProgress = false);
      }
    }
    if (!mounted) return;

    if (item == null) {
      final shown = scanned.isNotEmpty ? scanned : raw;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'No item found for barcode "$shown". Check item master BARCODE in ERP.',
          ),
        ),
      );
      await _clearSearchArea();
      return;
    }

    setState(() => _ensureCatalogItem(item!));
    await _openCountDialog(item, barcodeHint: scanned.isNotEmpty ? scanned : raw);
    if (mounted) await _clearSearchArea();
  }

  String _barcodeForSave(InventoryItem item, {String? barcodeHint}) {
    final hint = canonicalizeRetailBarcode(barcodeHint ?? '') ??
        normalizeBarcode(barcodeHint ?? '');
    if (hint.isNotEmpty) return hint;
    final fromItem = canonicalizeRetailBarcode(item.barcode) ?? normalizeBarcode(item.barcode);
    if (fromItem.isNotEmpty) return fromItem;
    final session = _session;
    if (session != null) {
      for (final line in session.lines) {
        if (line.itemcodeDisplay == item.itemCode) {
          final saved = line.barcode.trim();
          if (saved.isNotEmpty) return saved;
        }
      }
    }
    final search = _searchCtrl.text.trim();
    if (search.isNotEmpty && search != item.itemCode.trim()) return search;
    return '';
  }

  Future<void> _openCountDialog(InventoryItem item, {String? barcodeHint}) async {
    if (_savingLine) return;
    if (!_isDraft || _session == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('This count is not editable (already posted).')),
      );
      return;
    }

    _pauseAutoRefresh = true;
    final snapshot = await _withDbCheckLoader(() => _fetchItemDbSnapshot(item));
    if (!mounted) {
      _pauseAutoRefresh = false;
      return;
    }
    if (snapshot == null) {
      _pauseAutoRefresh = false;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not load latest stock from server.')),
      );
      return;
    }

    final dialogItem = snapshot.item;
    final currentCounted = snapshot.countedQty;
    final hadCount = currentCounted != null;
    final localPrior = _counts[item.itemCode];

    final result = await showDialog<_QtyDialogResult>(
      context: context,
      builder: (ctx) => _CountQtyDialog(
        item: dialogItem,
        currentCounted: currentCounted,
        hadCount: hadCount,
        formatQty: _formatQty,
        systemQty: snapshot.systemQty,
      ),
    );

    _pauseAutoRefresh = false;
    if (!mounted || result == null) return;

    final session = _session!;
    final repo = stockCountRepo(context);

    if (result is _QtyDialogSaved) {
      if (_savingLine) return;
      final localBeforeSave = _counts[dialogItem.itemCode];
      setState(() => _savingLine = true);
      _pauseAutoRefresh = true;
      try {
        final freshSnapshot = await _fetchItemDbSnapshot(dialogItem);
        if (!mounted) return;
        if (freshSnapshot == null) {
          throw StateError('Could not verify latest count from server.');
        }

        final prior = freshSnapshot.countedQty;
        final effectiveBase = prior ?? freshSnapshot.systemQty;
        final newCounted = effectiveBase + result.qty;
        if (newCounted < -0.0001) {
          throw StateError('Counted qty cannot be below zero.');
        }
        final syncedFromServer = localPrior != null &&
            freshSnapshot.countedQty != null &&
            (localPrior - freshSnapshot.countedQty!).abs() >= 0.0001;

        final line = await repo.saveLine(
          locationcode: session.locationcode,
          countNo: session.countNo,
          itemcode: dialogItem.itemCode,
          countedQty: newCounted,
          systemQty: freshSnapshot.systemQty,
          uom: dialogItem.unit,
          barcode: _barcodeForSave(dialogItem, barcodeHint: barcodeHint),
          warehouseId: session.warehouseId ?? widget.warehouseId,
        );
        if (!mounted) return;
        setState(() {
          _counts[dialogItem.itemCode] = newCounted;
          _systemQty[dialogItem.itemCode] = freshSnapshot.systemQty;
          _lineNos[dialogItem.itemCode] = line.lineNo;
          _markRecent(dialogItem);
          final savedBarcode = _barcodeForSave(dialogItem, barcodeHint: barcodeHint);
          _recordLastScan(
            item: dialogItem,
            barcode: savedBarcode.isNotEmpty ? savedBarcode : dialogItem.itemCode,
            addedQty: result.qty,
            totalCounted: newCounted,
          );
          _savingLine = false;
        });
        if (!mounted) return;
        await _clearSearchArea();
        if (!mounted) return;
        final totalLabel = _formatQty(newCounted);
        final deltaLabel = _formatQty(result.qty.abs());
        final changeVerb = result.qty < 0
            ? 'Reduced by'
            : (result.qty > 0 ? (hadCount ? 'Added' : 'Adjusted by') : 'No change');
        final syncNote = syncedFromServer || (localBeforeSave != null && prior != null && (localBeforeSave - prior).abs() >= 0.0001)
            ? ' (synced from server before save)'
            : '';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              result.qty == 0
                  ? 'Count unchanged$syncNote'
                  : '$changeVerb $deltaLabel → total $totalLabel$syncNote',
            ),
          ),
        );
      } catch (e) {
        if (!mounted) return;
        setState(() => _savingLine = false);
        if (!maybeShowAccessDeniedAlert(context, e)) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(handleApiError(context, e, authenticatedContext: true, showAccessDialog: false))),
          );
        }
      } finally {
        _pauseAutoRefresh = false;
      }
    }
  }

  String _formatQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  void _runSearch() {
    FocusScope.of(context).unfocus();
    unawaited(_loadFullCatalog());
  }

  void _onSearchSubmitted(String _) {
    final q = _searchCtrl.text.trim();
    if (q.isEmpty) return;
    if (looksLikeBarcodeScan(q)) {
      unawaited(_resolveScannedBarcode(q));
      return;
    }
    _runSearch();
  }

  void _onHardwareScan(String code) {
    if (!_isDraft || _savingLine || _sessionLoading) return;
    unawaited(_resolveScannedBarcode(code));
  }

  bool get _listLoading => _loading || _sessionLoading;

  Widget _summaryCard({
    required IconData icon,
    required Color color,
    required Color bg,
    required int count,
    required String label,
  }) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 6),
            Text(
              '$count',
              style: TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: 18,
                color: color,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color.withValues(alpha: 0.85)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummarySection({bool forSheet = false}) {
    return Padding(
      padding: forSheet ? EdgeInsets.zero : const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Summary',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: _titleColor),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _summaryCard(
                icon: Icons.inventory_2_outlined,
                color: _accent,
                bg: const Color(0xFFE3F2FD),
                count: _statTotal,
                label: 'Total Items',
              ),
              const SizedBox(width: 8),
              _summaryCard(
                icon: Icons.check_circle_outline_rounded,
                color: const Color(0xFF2E7D32),
                bg: const Color(0xFFE8F5E9),
                count: _statCounted,
                label: 'Counted',
              ),
              const SizedBox(width: 8),
              _summaryCard(
                icon: Icons.schedule_rounded,
                color: const Color(0xFFE65100),
                bg: const Color(0xFFFFF3E0),
                count: _statPending,
                label: 'Pending',
              ),
              const SizedBox(width: 8),
              _summaryCard(
                icon: Icons.warning_amber_rounded,
                color: const Color(0xFFC62828),
                bg: const Color(0xFFFFEBEE),
                count: _statVariance,
                label: 'Variance',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSearchBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: TextField(
        controller: _searchCtrl,
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: 'Search items by name or SKU',
          hintStyle: TextStyle(color: Colors.grey.shade500, fontSize: 14),
          prefixIcon: Icon(Icons.search_rounded, color: Colors.grey.shade500),
          suffixIcon: IconButton(
            icon: Icon(Icons.qr_code_scanner_rounded, color: Colors.grey.shade700),
            tooltip: 'Scan barcode',
            onPressed: _sessionLoading || _savingLine || _loading ? null : _scanBarcode,
          ),
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
        onSubmitted: _onSearchSubmitted,
      ),
    );
  }

  Widget _buildLastScannedSection() {
    final item = _lastScannedItem;
    final hasScan = item != null && _lastScanTotalQty != null;

    if (!hasScan) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
        decoration: BoxDecoration(
          color: const Color(0xFFF6F7FC),
          border: Border(bottom: BorderSide(color: Colors.grey.shade200)),
        ),
        child: Row(
          children: [
            Icon(Icons.qr_code_scanner_rounded, size: 18, color: Colors.grey.shade500),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'No last scan yet — tap Scan Item to use phone camera',
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      );
    }

    final displayName = item.itemName.isNotEmpty ? item.itemName : item.itemCode;
    final systemQ = _systemQtyFor(item);
    final totalQ = _lastScanTotalQty!;
    final addedQ = _lastScanAddedQty ?? totalQ;
    final status = _itemStatus(item);
    final barcode = _lastScannedBarcode.isNotEmpty ? _lastScannedBarcode : item.barcode;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFFF6F7FC),
        border: Border(bottom: BorderSide(color: Colors.grey.shade200)),
      ),
      child: InkWell(
        onTap: _isDraft && !_savingLine ? () => _openCountDialog(item, barcodeHint: barcode) : null,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE3F2FD),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.qr_code_scanner_rounded, size: 14, color: _accent),
                        SizedBox(width: 4),
                        Text(
                          'Last scanned',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: _accent),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  _statusBadge(status),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                displayName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                  color: _titleColor,
                ),
              ),
              const SizedBox(height: 4),
              _itemCodeBarcodeLines(item, barcodeOverride: barcode),
              if (item.unit.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  item.unit,
                  style: TextStyle(fontSize: 11.5, color: Colors.grey.shade500),
                ),
              ],
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: _lastScanStat(
                      label: 'System',
                      value: _formatQty(systemQ),
                      color: const Color(0xFF5A6275),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _lastScanStat(
                      label: 'Last scan',
                      value: '${addedQ >= 0 ? '+' : ''}${_formatQty(addedQ)}',
                      color: const Color(0xFFEF6C00),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _lastScanStat(
                      label: 'Counted',
                      value: _formatQty(totalQ),
                      color: _accent,
                      highlight: true,
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

  Widget _lastScanStat({
    required String label,
    required String value,
    required Color color,
    bool highlight = false,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      decoration: BoxDecoration(
        color: highlight ? const Color(0xFFE3F2FD) : Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: highlight ? const Color(0xFFBBDEFB) : const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: Colors.grey.shade600)),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: color),
          ),
        ],
      ),
    );
  }

  Widget _statusBadge(_ItemCountStatus status) {
    late final IconData icon;
    late final String label;
    late final Color color;
    switch (status) {
      case _ItemCountStatus.counted:
        icon = Icons.check_circle_rounded;
        label = 'Counted';
        color = const Color(0xFF2E7D32);
      case _ItemCountStatus.pending:
        icon = Icons.schedule_rounded;
        label = 'Pending';
        color = const Color(0xFFE65100);
      case _ItemCountStatus.variance:
        icon = Icons.warning_amber_rounded;
        label = 'Variance';
        color = const Color(0xFFC62828);
    }
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 4),
        Text(
          label,
          style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: color),
        ),
      ],
    );
  }

  Widget _itemCodeBarcodeLines(InventoryItem item, {String? barcodeOverride}) {
    final barcode = (barcodeOverride ?? item.barcode).trim();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'SKU: ${item.itemCode}',
          style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
        ),
        if (barcode.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(
            'Barcode: $barcode',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 11.5, color: Colors.grey.shade500),
          ),
        ],
      ],
    );
  }

  Widget _itemThumb(InventoryItem item) {
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        color: const Color(0xFFF0F2F8),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Icon(
        Icons.inventory_2_outlined,
        color: Colors.grey.shade500,
        size: 28,
      ),
    );
  }

  Widget _buildItemList({
    required List<InventoryItem> items,
    required int tabIndex,
  }) {
    final loading = _listLoading;
    if (loading && items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (items.isEmpty && !loading) {
      final emptyMessages = [
        'No items loaded.\nSearch or scan to find items.',
        'No counted items yet.',
        'No pending items.',
        'No variance items.',
      ];
      return Center(
        child: Text(
          emptyMessages[tabIndex.clamp(0, 3)],
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey.shade600, height: 1.4),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: () async {
        await _loadSession();
        await _loadFullCatalog();
        await _loadLastScannedForUser();
      },
      child: NotificationListener<ScrollNotification>(
        onNotification: (notification) {
          if (notification.metrics.pixels >= notification.metrics.maxScrollExtent - 240) {
            unawaited(_loadMoreCatalog());
          }
          return false;
        },
        child: ListView.separated(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          itemCount: items.length + (_loadingMoreCatalog ? 1 : 0),
          separatorBuilder: (_, __) => Divider(height: 1, color: Colors.grey.shade200),
          itemBuilder: (context, index) {
            if (index >= items.length) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 16),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              );
            }
            final item = items[index];
          final c = _counts[item.itemCode];
          final systemQ = _systemQtyFor(item);
          final status = _itemStatus(item);
          final countedDisplay = c ?? 0.0;
          final displayName = item.itemName.isNotEmpty ? item.itemName : item.itemCode;

          return Material(
            color: Colors.white,
            child: InkWell(
              onTap: _isDraft && !_savingLine ? () => _openCountDialog(item) : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    _itemThumb(item),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                              color: _titleColor,
                            ),
                          ),
                          const SizedBox(height: 3),
                          _itemCodeBarcodeLines(item),
                          const SizedBox(height: 2),
                          Text(
                            _locationLabel,
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        _statusBadge(status),
                        const SizedBox(height: 4),
                        Text(
                          '${_formatQty(countedDisplay)} / ${_formatQty(systemQ)}',
                          style: const TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 14,
                            color: _titleColor,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(width: 4),
                    Icon(Icons.chevron_right_rounded, color: Colors.grey.shade400, size: 22),
                  ],
                ),
              ),
            ),
          );
        },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('Stock Count', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline_rounded),
            tooltip: 'Count session',
            onPressed: _showFilterSheet,
          ),
        ],
      ),
      backgroundColor: _bg,
      body: Stack(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildSearchBar(),
              if (_barcodeLookupInProgress)
                const LinearProgressIndicator(minHeight: 2),
              if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
              Material(
                color: Colors.white,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildLastScannedSection(),
                    TabBar(
                      controller: _tabController,
                      isScrollable: true,
                      tabAlignment: TabAlignment.start,
                      labelColor: _accent,
                      unselectedLabelColor: Colors.grey.shade600,
                      indicatorColor: _accent,
                      labelStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                      unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.w500, fontSize: 13),
                      tabs: [
                        Tab(text: 'All ($_statTotal)'),
                        Tab(text: 'Counted ($_statCounted)'),
                        Tab(text: 'Pending ($_statPending)'),
                        Tab(text: 'Variance ($_statVariance)'),
                      ],
                    ),
                  ],
                ),
              ),
              Expanded(
                child: ColoredBox(
                  color: Colors.white,
                  child: TabBarView(
                    controller: _tabController,
                    children: List.generate(
                      4,
                      (i) => _buildItemList(items: _itemsForTab(i), tabIndex: i),
                    ),
                  ),
                ),
              ),
            ],
          ),
          HardwareBarcodeCapture(
            focusNode: _scanFocusNode,
            controller: _hardwareScanCtrl,
            enabled: _isDraft && !_savingLine && !_sessionLoading,
            onScan: _onHardwareScan,
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: _accent,
              minimumSize: const Size(double.infinity, 52),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
            onPressed: _sessionLoading || _savingLine || !_isDraft ? null : _scanBarcode,
            icon: const Icon(Icons.photo_camera_outlined),
            label: const Text('Scan Item', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          ),
        ),
      ),
    );
  }
}

class _CountQtyDialog extends StatefulWidget {
  const _CountQtyDialog({
    required this.item,
    required this.currentCounted,
    required this.hadCount,
    required this.formatQty,
    required this.systemQty,
  });

  final InventoryItem item;
  final double? currentCounted;
  final bool hadCount;
  final String Function(double) formatQty;
  final double systemQty;

  @override
  State<_CountQtyDialog> createState() => _CountQtyDialogState();
}

class _CountQtyDialogState extends State<_CountQtyDialog> {
  late final TextEditingController _qtyCtrl;
  double? _newTotalPreview;
  bool _submitting = false;

  double get _effectiveBase => widget.currentCounted ?? widget.systemQty;

  @override
  void initState() {
    super.initState();
    _qtyCtrl = TextEditingController();
    _qtyCtrl.addListener(_onQtyChanged);
  }

  void _onQtyChanged() {
    final raw = _qtyCtrl.text.trim();
    if (raw.isEmpty) {
      setState(() => _newTotalPreview = null);
      return;
    }
    final delta = double.tryParse(raw.replaceAll(',', ''));
    if (delta == null) {
      setState(() => _newTotalPreview = null);
      return;
    }
    setState(() => _newTotalPreview = _effectiveBase + delta);
  }

  double get _entryDelta {
    final raw = _qtyCtrl.text.trim();
    return double.tryParse(raw.replaceAll(',', '')) ?? 0;
  }

  bool get _canStepDown {
    return _effectiveBase + _entryDelta - 1 >= -0.0001;
  }

  void _adjustQty(double delta) {
    var next = _entryDelta + delta;
    if (_effectiveBase + next < 0) next = -_effectiveBase;
    final text = next == next.roundToDouble() ? next.round().toString() : next.toStringAsFixed(2);
    _qtyCtrl.text = text;
    _qtyCtrl.selection = TextSelection.collapsed(offset: text.length);
  }

  Widget _stepButton({required bool isPlus, VoidCallback? onTap}) {
    const minusColor = Color(0xFFC62828);
    const plusColor = Color(0xFF1565C0);
    final enabled = onTap != null;
    final color = isPlus ? plusColor : minusColor;
    return Material(
      color: enabled ? color.withValues(alpha: 0.1) : Colors.grey.shade100,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(
          color: enabled ? color.withValues(alpha: 0.35) : Colors.grey.shade300,
          width: 1.5,
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        onLongPress: enabled ? () => _adjustQty(isPlus ? 10 : -10) : null,
        child: SizedBox(
          width: 52,
          height: 52,
          child: Icon(
            isPlus ? Icons.add_rounded : Icons.remove_rounded,
            size: 30,
            color: enabled ? color : Colors.grey.shade400,
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _qtyCtrl.removeListener(_onQtyChanged);
    _qtyCtrl.dispose();
    super.dispose();
  }

  void _save() {
    if (_submitting) return;
    final raw = _qtyCtrl.text.trim();
    if (raw.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a change amount')),
      );
      return;
    }
    final v = double.tryParse(raw.replaceAll(',', ''));
    if (v == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid number')),
      );
      return;
    }
    final newTotal = _effectiveBase + v;
    if (newTotal < -0.0001) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Cannot go below 0. Max reduction is ${widget.formatQty(_effectiveBase)}.',
          ),
        ),
      );
      return;
    }
    setState(() => _submitting = true);
    Navigator.of(context).pop(_QtyDialogSaved(v));
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final baseLabel = widget.hadCount && widget.currentCounted != null ? 'Counted' : 'Starting';
    return AlertDialog(
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(item.itemCode, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
          if (item.barcode.trim().isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Barcode: ${item.barcode.trim()}',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
            ),
          ],
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (item.itemName.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(item.itemName, style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
            ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.blueGrey.shade50,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'System: ${widget.formatQty(widget.systemQty)} ${item.unit}',
                  style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
                ),
                const SizedBox(height: 4),
                Text(
                  '$baseLabel: ${widget.formatQty(_effectiveBase)} ${item.unit}',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          Text(
            'Change (+ / −)',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
          ),
          const SizedBox(height: 6),
          Container(
            decoration: BoxDecoration(
              color: Colors.grey.shade50,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.grey.shade300),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                _stepButton(
                  isPlus: false,
                  onTap: _canStepDown ? () => _adjustQty(-1) : null,
                ),
                Expanded(
                  child: NumericTextField(
                    controller: _qtyCtrl,
                    autofocus: true,
                    signed: true,
                    labelText: 'Change',
                    textAlign: TextAlign.center,
                    decoration: const InputDecoration(
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 12),
                      isDense: true,
                    ),
                  ),
                ),
                _stepButton(
                  isPlus: true,
                  onTap: () => _adjustQty(1),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(top: 6, left: 4),
            child: Text(
              'Tap − / + for ±1 · long-press for ±10',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
            ),
          ),
          if (_newTotalPreview != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xFFE3F2FD),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'After save: ${widget.formatQty(_newTotalPreview!)} ${item.unit}',
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0277BD),
                ),
              ),
            ),
          ],
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
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Save'),
        ),
      ],
    );
  }
}
