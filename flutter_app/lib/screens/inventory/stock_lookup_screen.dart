import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_client.dart';
import '../../core/network/api_error_handler.dart';
import '../../widgets/api_error_banner.dart';
import '../../models/inventory_item.dart';
import '../../core/storage/local_cache.dart';
import '../../repositories/inventory_repository.dart';
import '../../services/inventory_service.dart';
import '../barcode_scanner_screen.dart';
import '../../core/theme/app_theme.dart';

InventoryRepository _inventoryRepo(BuildContext context) {
  try {
    return context.read<InventoryRepository>();
  } on ProviderNotFoundException {
    return InventoryRepository(
      InventoryService(context.read<ApiClient>()),
      context.read<LocalCache>(),
    );
  }
}

class StockLookupScreen extends StatefulWidget {
  const StockLookupScreen({super.key});

  @override
  State<StockLookupScreen> createState() => _StockLookupScreenState();
}

class _StockLookupScreenState extends State<StockLookupScreen> {
  static const _pageSize = 40;

  final _searchCtrl = TextEditingController();

  bool _loading = false;
  String? _error;
  Object? _errorCause;
  List<InventoryItem> _items = [];

  @override
  void initState() {
    super.initState();
    _searchCtrl.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _search({String? query}) async {
    final q = (query ?? _searchCtrl.text).trim();
    if (q.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter item code, name, or barcode')),
      );
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _items = [];
    });

    try {
      final rows = await _inventoryRepo(context).getInventory(
        page: 1,
        pageSize: _pageSize,
        search: q,
      );
      if (!mounted) return;
      setState(() {
        _items = rows;
        _loading = false;
      });
      if (rows.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No items match "$q"')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  void _clearSearch() {
    _searchCtrl.clear();
    setState(() {
      _items = [];
      _error = null;
      _loading = false;
    });
    FocusScope.of(context).unfocus();
  }

  InventoryItem? _matchBarcode(String scanned, List<InventoryItem> items) {
    final raw = scanned.trim();
    if (raw.isEmpty || items.isEmpty) return null;

    String norm(String s) {
      var t = s.trim();
      if (t.contains('.')) t = t.replaceAll(RegExp(r'\.0+$'), '');
      final stripped = t.replaceFirst(RegExp(r'^0+'), '');
      return stripped.isEmpty ? '0' : stripped;
    }

    final target = norm(raw);
    InventoryItem? numericMatch;

    for (final it in items) {
      if (it.itemCode.trim() == raw) return it;
      final bc = it.barcode.trim();
      if (bc.isNotEmpty && (bc == raw || norm(bc) == target)) return it;
      if (norm(it.itemCode) == target) numericMatch ??= it;
    }
    return numericMatch ?? (items.length == 1 ? items.first : null);
  }

  Future<void> _scanBarcode() async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => const BarcodeScannerScreen(title: 'Scan item barcode'),
      ),
    );
    if (!mounted || code == null || code.trim().isEmpty) return;

    _searchCtrl.text = code.trim();
    await _search(query: code.trim());
    if (!mounted) return;

    final item = _matchBarcode(code, _items);
    if (item != null) {
      await _openDetail(item);
      if (mounted) {
        _searchCtrl.clear();
        setState(() => _items = []);
      }
    }
  }

  Future<void> _openDetail(InventoryItem item) async {
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _StockLookupDetailSheet(item: item),
    );
  }

  String _formatQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('Stock Lookup', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _searchCtrl,
                    textInputAction: TextInputAction.search,
                    decoration: InputDecoration(
                      hintText: 'Search or scan barcode…',
                      filled: true,
                      fillColor: Colors.white,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                      isDense: true,
                      suffixIcon: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (_searchCtrl.text.isNotEmpty)
                            IconButton(
                              icon: const Icon(Icons.clear_rounded, size: 20),
                              tooltip: 'Clear',
                              onPressed: _loading ? null : _clearSearch,
                            ),
                          IconButton(
                            icon: const Icon(Icons.search_rounded),
                            onPressed: _loading
                                ? null
                                : () {
                                    FocusScope.of(context).unfocus();
                                    _search();
                                  },
                          ),
                        ],
                      ),
                    ),
                    onSubmitted: (_) => _search(),
                  ),
                ),
                const SizedBox(width: 8),
                Material(
                  color: const Color(0xFF00838F),
                  borderRadius: BorderRadius.circular(12),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: _loading ? null : _scanBarcode,
                    child: const Padding(
                      padding: EdgeInsets.all(12),
                      child: Icon(Icons.qr_code_scanner_rounded, color: Colors.white, size: 24),
                    ),
                  ),
                ),
                if (_loading) ...[
                  const SizedBox(width: 12),
                  const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2)),
                ],
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Chip(
              label: Text(
                _items.isEmpty
                    ? 'Search by item code, name, or barcode'
                    : '${_items.length} item(s) — tap for store stock',
              ),
              backgroundColor: Colors.white,
              side: const BorderSide(color: Color(0xFFE8EBF3)),
            ),
          ),
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause, padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4)),
          Expanded(
            child: _loading && _items.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : _items.isEmpty
                    ? Center(
                        child: Text(
                          _searchCtrl.text.trim().isEmpty ? 'Enter a search term to begin.' : 'No items match.',
                          style: TextStyle(color: Colors.grey.shade600),
                          textAlign: TextAlign.center,
                        ),
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                        itemCount: _items.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          final item = _items[index];
                          return Material(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                            child: InkWell(
                              borderRadius: BorderRadius.circular(12),
                              onTap: () => _openDetail(item),
                              child: Padding(
                                padding: const EdgeInsets.all(14),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            item.itemCode,
                                            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                                          ),
                                          if (item.itemName.isNotEmpty) ...[
                                            const SizedBox(height: 4),
                                            Text(
                                              item.itemName,
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
                                            ),
                                          ],
                                          const SizedBox(height: 6),
                                          Text(
                                            'On hand: ${_formatQty(item.qtyOnHand)} ${item.unit}'
                                            '${item.barcode.isNotEmpty ? ' · ${item.barcode}' : ''}',
                                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                                          ),
                                          if (item.retailPrice > 0) ...[
                                            const SizedBox(height: 4),
                                            Text(
                                              'Retail: ${item.retailPrice.toStringAsFixed(2)}',
                                              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                                            ),
                                          ],
                                        ],
                                      ),
                                    ),
                                    Icon(Icons.chevron_right_rounded, color: Colors.grey.shade400),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _StockLookupDetailSheet extends StatefulWidget {
  const _StockLookupDetailSheet({required this.item});

  final InventoryItem item;

  @override
  State<_StockLookupDetailSheet> createState() => _StockLookupDetailSheetState();
}

class _StockLookupDetailSheetState extends State<_StockLookupDetailSheet> {
  List<ItemStoreStock> _stores = [];
  bool _loading = true;
  String? _error;
  Object? _errorCause;

  @override
  void initState() {
    super.initState();
    _loadStores();
  }

  Future<void> _loadStores() async {
    final code = int.tryParse(widget.item.itemCode.trim()) ?? 0;
    if (code <= 0) {
      setState(() {
        _loading = false;
        _error = 'Invalid item code';
      });
      return;
    }
    try {
      final rows = await context.read<InventoryService>().getItemStoreStock(code);
      if (!mounted) return;
      setState(() {
        _stores = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  String _formatQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  Widget _infoChip(String label, String value) {
    return Chip(
      label: Text('$label: $value', style: const TextStyle(fontSize: 12)),
      backgroundColor: const Color(0xFFF6F7FC),
      side: const BorderSide(color: Color(0xFFE8EBF3)),
      visualDensity: VisualDensity.compact,
    );
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: Container(
        margin: const EdgeInsets.fromLTRB(12, 0, 12, 16),
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.75),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 8, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      item.itemCode,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (item.itemName.isNotEmpty)
                    Text(item.itemName, style: TextStyle(fontSize: 14, color: Colors.grey.shade700)),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _infoChip('On hand', '${_formatQty(item.qtyOnHand)} ${item.unit}'),
                      if (item.barcode.isNotEmpty) _infoChip('Barcode', item.barcode),
                      if (item.retailPrice > 0) _infoChip('Retail', item.retailPrice.toStringAsFixed(2)),
                    ],
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
              child: Text(
                'Stock by store',
                style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade800),
              ),
            ),
            Flexible(
              child: _loading
                  ? const Padding(
                      padding: EdgeInsets.all(24),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  : _error != null
                      ? ApiErrorCenter(message: _error!, error: _errorCause)
                      : _stores.isEmpty
                          ? Padding(
                              padding: const EdgeInsets.all(16),
                              child: Text(
                                'No store-level stock found.',
                                style: TextStyle(color: Colors.grey.shade600),
                              ),
                            )
                          : ListView.separated(
                              shrinkWrap: true,
                              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                              itemCount: _stores.length,
                              separatorBuilder: (_, __) => const SizedBox(height: 6),
                              itemBuilder: (context, index) {
                                final row = _stores[index];
                                return ListTile(
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(10),
                                    side: const BorderSide(color: Color(0xFFE8EBF3)),
                                  ),
                                  title: Text(row.store, style: const TextStyle(fontWeight: FontWeight.w600)),
                                  subtitle: row.description.isNotEmpty ? Text(row.description) : null,
                                  trailing: Text(
                                    _formatQty(row.qty),
                                    style: const TextStyle(fontWeight: FontWeight.w700),
                                  ),
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
