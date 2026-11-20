import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/item_master_service.dart';
import '../../widgets/api_error_banner.dart';
import 'item_detail_screen.dart';
import 'item_form_screen.dart';
import '../../core/theme/app_theme.dart';

class ItemListScreen extends StatefulWidget {
  const ItemListScreen({super.key});

  @override
  State<ItemListScreen> createState() => _ItemListScreenState();
}

class _ItemListScreenState extends State<ItemListScreen> {
  static const _accent = Color(0xFF5E35B1);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<ItemMasterRow> _rows = [];
  ItemListFilters _filters = const ItemListFilters();
  ItemOpenContext? _meta;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadMeta();
      _reload();
    });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _loadMeta() async {
    try {
      final meta = await context.read<ItemMasterService>().getOpenContext();
      if (mounted) setState(() => _meta = meta);
    } catch (_) {}
  }

  void _scheduleSearch() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), _reload);
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final rows = await context.read<ItemMasterService>().listItems(
            q: _search.text.trim(),
            filters: _filters,
          );
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _loading = false;
      });
    }
  }

  Future<void> _openNew() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const ItemFormScreen()),
    );
    if (saved == true && mounted) _reload();
  }

  Future<void> _openDetail(ItemMasterRow row) async {
    if (row.itemCode <= 0) return;
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => ItemDetailScreen(itemCode: row.itemCode),
      ),
    );
    if (changed == true && mounted) _reload();
  }

  Future<void> _openFilters() async {
    if (_meta == null) {
      await _loadMeta();
    }
    if (!mounted) return;
    final next = await showModalBottomSheet<ItemListFilters>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _ItemFilterSheet(
        initial: _filters,
        meta: _meta,
      ),
    );
    if (next == null || !mounted) return;
    setState(() => _filters = next);
    _reload();
  }

  String _money(double v) => v.toStringAsFixed(2);

  String _stock(double v) {
    if (v == v.roundToDouble()) return v.toStringAsFixed(0);
    return v.toStringAsFixed(3);
  }

  Widget _stockPill({required bool inStock, required bool lowStock}) {
    late final String label;
    late final Color bg;
    late final Color fg;
    if (!inStock) {
      label = 'Out of stock';
      bg = const Color(0xFFFFEBEE);
      fg = const Color(0xFFC62828);
    } else if (lowStock) {
      label = 'Low stock';
      bg = const Color(0xFFFFF3E0);
      fg = const Color(0xFFE65100);
    } else {
      label = 'In stock';
      bg = const Color(0xFFE8F5E9);
      fg = const Color(0xFF2E7D32);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(5)),
      child: Text(label, style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.w700, color: fg)),
    );
  }

  String _lookupLabel(String? code, List<ItemLookupOption> options) {
    if (code == null || code.isEmpty) return '';
    for (final o in options) {
      if (o.code == code) return o.name.isNotEmpty ? o.name : o.code;
    }
    return code;
  }

  List<Widget> _activeFilterChips() {
    final chips = <Widget>[];
    void add(String label, VoidCallback onClear) {
      chips.add(
        InputChip(
          label: Text(label, style: const TextStyle(fontSize: 12)),
          onDeleted: () {
            onClear();
            _reload();
          },
          deleteIconColor: _accent,
          side: BorderSide(color: _accent.withValues(alpha: 0.35)),
          backgroundColor: _accent.withValues(alpha: 0.08),
          visualDensity: VisualDensity.compact,
        ),
      );
    }

    if ((_filters.categoryCode ?? '').isNotEmpty) {
      final name = _lookupLabel(_filters.categoryCode, _meta?.categories ?? const []);
      add('Cat: $name', () => setState(() => _filters = _filters.copyWith(clearCategory: true)));
    }
    if ((_filters.brandCode ?? '').isNotEmpty) {
      final name = _lookupLabel(_filters.brandCode, _meta?.brands ?? const []);
      add('Brand: $name', () => setState(() => _filters = _filters.copyWith(clearBrand: true)));
    }
    if ((_filters.supplierCode ?? '').isNotEmpty) {
      final name = _lookupLabel(_filters.supplierCode, _meta?.suppliers ?? const []);
      add('Sup: $name', () => setState(() => _filters = _filters.copyWith(clearSupplier: true)));
    }
    if (_filters.stockFilter.isNotEmpty) {
      final labels = {
        'instock': 'In stock',
        'low': 'Low',
        'out': 'Out',
        'zero': 'Out',
        'notzero': 'Stock ≠ 0',
        'greater': 'Stock > 0',
        'less': 'Stock < 0',
      };
      add(
        labels[_filters.stockFilter] ?? _filters.stockFilter,
        () => setState(() => _filters = _filters.copyWith(stockFilter: '')),
      );
    }
    return chips;
  }

  @override
  Widget build(BuildContext context) {
    final filterChips = _activeFilterChips();
    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('Items', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Filters',
            onPressed: _openFilters,
            icon: Badge(
              isLabelVisible: _filters.hasActive,
              smallSize: 8,
              child: const Icon(Icons.filter_list_rounded),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNew,
        backgroundColor: _accent,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_box_outlined),
        label: const Text('New Item'),
      ),
      body: Column(
        children: [
          Material(
            color: Colors.white,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _search,
                    onChanged: (_) => _scheduleSearch(),
                    textInputAction: TextInputAction.search,
                    decoration: InputDecoration(
                      hintText: 'Search name, code, barcode…',
                      prefixIcon: const Icon(Icons.search_rounded, size: 20),
                      isDense: true,
                      filled: true,
                      fillColor: const Color(0xFFF0F2FA),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: BorderSide.none,
                      ),
                    ),
                  ),
                  if (filterChips.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Wrap(spacing: 6, runSpacing: 4, children: filterChips),
                  ],
                ],
              ),
            ),
          ),
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
          Expanded(
            child: RefreshIndicator(
              color: _accent,
              onRefresh: _reload,
              child: _loading && _rows.isEmpty
                  ? ListView(
                      children: const [
                        SizedBox(height: 120),
                        Center(child: CircularProgressIndicator()),
                      ],
                    )
                  : _rows.isEmpty
                      ? ListView(
                          children: [
                            const SizedBox(height: 80),
                            Icon(Icons.widgets_outlined, size: 42, color: Colors.grey.shade400),
                            const SizedBox(height: 12),
                            Text(
                              _search.text.trim().isEmpty && !_filters.hasActive
                                  ? 'No items yet.\nTap New Item to create one.'
                                  : 'No items match your search/filters.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.grey.shade600, height: 1.35),
                            ),
                          ],
                        )
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(12, 8, 12, 100),
                          itemCount: _rows.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 8),
                          itemBuilder: (context, i) {
                            final row = _rows[i];
                            final name = (row.itemName.isNotEmpty ? row.itemName : 'Item ${row.itemCode}').toUpperCase();
                            final uom = row.baseUom.isNotEmpty ? row.baseUom : 'PCS';
                            final stock = row.currentStock;
                            final inStock = stock > 0;
                            final lowStock = inStock && stock <= 10;
                            return Material(
                              color: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(14),
                                side: const BorderSide(color: Color(0xFFE8EBF3)),
                              ),
                              clipBehavior: Clip.antiAlias,
                              child: InkWell(
                                onTap: () => _openDetail(row),
                                child: Padding(
                                  padding: const EdgeInsets.fromLTRB(12, 12, 10, 12),
                                  child: Row(
                                    crossAxisAlignment: CrossAxisAlignment.center,
                                    children: [
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              name,
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                              style: const TextStyle(
                                                fontWeight: FontWeight.w800,
                                                fontSize: 14,
                                                height: 1.2,
                                                color: Color(0xFF262C50),
                                              ),
                                            ),
                                            const SizedBox(height: 3),
                                            Row(
                                              children: [
                                                Expanded(
                                                  child: Text(
                                                    [
                                                      if (row.itemCode > 0) 'SKU: ${row.itemCode}',
                                                      if (row.barcode.isNotEmpty) row.barcode,
                                                    ].join(' · '),
                                                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                                    maxLines: 1,
                                                    overflow: TextOverflow.ellipsis,
                                                  ),
                                                ),
                                                const SizedBox(width: 8),
                                                _stockPill(inStock: inStock, lowStock: lowStock),
                                              ],
                                            ),
                                            const SizedBox(height: 6),
                                            Text.rich(
                                              TextSpan(
                                                children: [
                                                  TextSpan(
                                                    text: '${_stock(stock)} $uom',
                                                    style: TextStyle(
                                                      fontWeight: FontWeight.w700,
                                                      fontSize: 13,
                                                      color: inStock
                                                          ? (lowStock
                                                              ? const Color(0xFFE65100)
                                                              : const Color(0xFF2E7D32))
                                                          : const Color(0xFFC62828),
                                                    ),
                                                  ),
                                                  TextSpan(
                                                    text: '  ·  Avg ',
                                                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                                  ),
                                                  TextSpan(
                                                    text: _money(row.averageCost),
                                                    style: const TextStyle(
                                                      fontWeight: FontWeight.w800,
                                                      fontSize: 16,
                                                      color: Color(0xFF262C50),
                                                    ),
                                                  ),
                                                  TextSpan(
                                                    text: '  ·  Cost ${_money(row.costPrice)}',
                                                    style: TextStyle(
                                                      fontWeight: FontWeight.w600,
                                                      fontSize: 12,
                                                      color: Colors.grey.shade600,
                                                    ),
                                                  ),
                                                  TextSpan(
                                                    text: '  ·  Retail ${_money(row.retailPrice)}',
                                                    style: TextStyle(
                                                      fontWeight: FontWeight.w600,
                                                      fontSize: 12,
                                                      color: Colors.grey.shade600,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                          ],
                                        ),
                                      ),
                                      Icon(Icons.chevron_right_rounded, color: Colors.grey.shade500),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ItemFilterSheet extends StatefulWidget {
  const _ItemFilterSheet({required this.initial, required this.meta});

  final ItemListFilters initial;
  final ItemOpenContext? meta;

  @override
  State<_ItemFilterSheet> createState() => _ItemFilterSheetState();
}

class _ItemFilterSheetState extends State<_ItemFilterSheet> {
  static const _accent = Color(0xFF5E35B1);

  late String? _categoryCode;
  late String? _brandCode;
  late String? _supplierCode;
  late String _stockFilter;

  @override
  void initState() {
    super.initState();
    _categoryCode = widget.initial.categoryCode;
    _brandCode = widget.initial.brandCode;
    _supplierCode = widget.initial.supplierCode;
    _stockFilter = widget.initial.stockFilter;
  }

  String _label(String? code, List<ItemLookupOption> options, String empty) {
    if (code == null || code.isEmpty) return empty;
    for (final o in options) {
      if (o.code == code) return o.label;
    }
    return code;
  }

  Future<void> _pick({
    required String title,
    required List<ItemLookupOption> options,
    required String? selected,
    required ValueChanged<String?> onPicked,
  }) async {
    final picked = await showModalBottomSheet<ItemLookupOption>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (ctx) {
        final search = TextEditingController();
        var filtered = options;
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            final bottom = MediaQuery.of(ctx).viewInsets.bottom;
            return Padding(
              padding: EdgeInsets.fromLTRB(16, 12, 16, 16 + bottom),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                  const SizedBox(height: 10),
                  TextField(
                    controller: search,
                    autofocus: true,
                    decoration: const InputDecoration(
                      hintText: 'Search…',
                      prefixIcon: Icon(Icons.search, size: 20),
                      isDense: true,
                    ),
                    onChanged: (q) {
                      final qq = q.trim().toLowerCase();
                      setLocal(() {
                        filtered = qq.isEmpty
                            ? options
                            : options
                                .where((o) =>
                                    o.code.toLowerCase().contains(qq) || o.name.toLowerCase().contains(qq))
                                .toList();
                      });
                    },
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(ctx, ItemLookupOption(code: '', name: '')),
                    child: const Text('Clear'),
                  ),
                  ConstrainedBox(
                    constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.45),
                    child: ListView.builder(
                      shrinkWrap: true,
                      itemCount: filtered.length,
                      itemBuilder: (_, i) {
                        final o = filtered[i];
                        return ListTile(
                          dense: true,
                          selected: o.code == selected,
                          title: Text(o.name.isNotEmpty ? o.name : o.code),
                          subtitle: Text(o.code),
                          onTap: () => Navigator.pop(ctx, o),
                        );
                      },
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
    if (picked == null) return;
    onPicked(picked.code.isEmpty ? null : picked.code);
  }

  @override
  Widget build(BuildContext context) {
    final meta = widget.meta;
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
          const Text('Filter items', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 14),
          _filterTile(
            label: 'Category',
            value: _label(_categoryCode, meta?.categories ?? const [], 'Any'),
            onTap: () => _pick(
              title: 'Category',
              options: meta?.categories ?? const [],
              selected: _categoryCode,
              onPicked: (v) => setState(() => _categoryCode = v),
            ),
          ),
          _filterTile(
            label: 'Brand',
            value: _label(_brandCode, meta?.brands ?? const [], 'Any'),
            onTap: () => _pick(
              title: 'Brand',
              options: meta?.brands ?? const [],
              selected: _brandCode,
              onPicked: (v) => setState(() => _brandCode = v),
            ),
          ),
          _filterTile(
            label: 'Supplier',
            value: _label(_supplierCode, meta?.suppliers ?? const [], 'Any'),
            onTap: () => _pick(
              title: 'Supplier',
              options: meta?.suppliers ?? const [],
              selected: _supplierCode,
              onPicked: (v) => setState(() => _supplierCode = v),
            ),
          ),
          const SizedBox(height: 8),
          Text('Stock', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: Colors.grey.shade700)),
          const SizedBox(height: 10),
          Row(
            children: [
              for (final e in const [
                (Icons.apps_rounded, '', 'All'),
                (Icons.check_circle_outline_rounded, 'instock', 'In stock'),
                (Icons.warning_amber_rounded, 'low', 'Low'),
                (Icons.remove_shopping_cart_outlined, 'out', 'Out'),
              ])
                Expanded(
                  child: InkWell(
                    onTap: () => setState(() => _stockFilter = e.$2),
                    borderRadius: BorderRadius.circular(12),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 2),
                      child: Column(
                        children: [
                          Container(
                            width: 52,
                            height: 52,
                            decoration: BoxDecoration(
                              color: _stockFilter == e.$2
                                  ? _accent.withValues(alpha: 0.12)
                                  : const Color(0xFFF0F2F8),
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: _stockFilter == e.$2
                                    ? _accent.withValues(alpha: 0.35)
                                    : Colors.grey.shade200,
                              ),
                            ),
                            child: Icon(
                              e.$1,
                              size: 22,
                              color: _stockFilter == e.$2 ? _accent : Colors.grey.shade600,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            e.$3,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: _stockFilter == e.$2 ? _accent : Colors.grey.shade700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(
                    context,
                    const ItemListFilters(),
                  ),
                  child: const Text('Clear all'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: _accent),
                  onPressed: () => Navigator.pop(
                    context,
                    ItemListFilters(
                      categoryCode: _categoryCode,
                      brandCode: _brandCode,
                      supplierCode: _supplierCode,
                      stockFilter: _stockFilter,
                    ),
                  ),
                  child: const Text('Apply'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _filterTile({
    required String label,
    required String value,
    required VoidCallback onTap,
  }) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(label, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
      subtitle: Text(value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
      trailing: const Icon(Icons.search_rounded, size: 20),
      onTap: onTap,
    );
  }
}
