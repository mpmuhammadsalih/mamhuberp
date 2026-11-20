import 'package:flutter/material.dart';

import '../../services/sales_service.dart';

/// Standard ERP line-entry step: search items, cart lines, totals.
class SalesInvoiceLineView {
  const SalesInvoiceLineView({
    required this.slno,
    required this.itemCode,
    required this.itemName,
    required this.subtitle,
    required this.qty,
    required this.rate,
    required this.amount,
    this.discount = 0,
  });

  final int slno;
  final String itemCode;
  final String itemName;
  final String subtitle;
  final double qty;
  final double rate;
  final double amount;
  /// Discount **per unit** (total discount = this × qty).
  final double discount;

  double get gross => qty * rate;
  double get discountTotal => qty * discount;
}

enum _CatalogSort { name, priceLow, priceHigh, stockHigh }

enum _StockFilter { all, inStock, lowStock, outOfStock }

class SalesInvoiceLinesStep extends StatefulWidget {
  const SalesInvoiceLinesStep({
    super.key,
    required this.searchController,
    required this.items,
    required this.lines,
    required this.loading,
    required this.warehouseLabel,
    required this.showWarehouseHint,
    required this.netTotal,
    required this.onSearch,
    required this.onScan,
    required this.onRefresh,
    required this.onItemTap,
    required this.onQuickAdd,
    required this.onOpenCart,
    this.errorMessage,
    this.creditBanner,
    this.allowAddWithoutStock = false,
    this.showCustomerItemsTab = false,
    this.customerItems = const [],
    this.customerItemsLoading = false,
    this.customerItemsError,
    this.onRefreshCustomerItems,
  });

  final TextEditingController searchController;
  final List<SalesCatalogItem> items;
  final List<SalesInvoiceLineView> lines;
  final bool loading;
  final String? errorMessage;
  final String warehouseLabel;
  final bool showWarehouseHint;
  final double netTotal;
  final VoidCallback onSearch;
  final VoidCallback onScan;
  final Future<void> Function() onRefresh;
  final void Function(SalesCatalogItem item) onItemTap;
  final void Function(SalesCatalogItem item) onQuickAdd;
  final VoidCallback onOpenCart;
  final Widget? creditBanner;
  /// When true (ERP minus billing / sales return), show Add even if stock is 0.
  final bool allowAddWithoutStock;

  /// Second tab: items previously sold/ordered for the selected customer.
  final bool showCustomerItemsTab;
  final List<SalesCatalogItem> customerItems;
  final bool customerItemsLoading;
  final String? customerItemsError;
  final Future<void> Function()? onRefreshCustomerItems;

  @override
  State<SalesInvoiceLinesStep> createState() => _SalesInvoiceLinesStepState();
}

class _SalesInvoiceLinesStepState extends State<SalesInvoiceLinesStep>
    with SingleTickerProviderStateMixin {
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF6F7FC);
  static const _titleColor = Color(0xFF262C50);
  static const _lowStockThreshold = 10.0;

  bool _gridView = false; // list view matches ERP sales item picker
  _CatalogSort _sort = _CatalogSort.name;
  _StockFilter _stockFilter = _StockFilter.all;
  TabController? _tabController;

  @override
  void initState() {
    super.initState();
    _syncTabController();
  }

  @override
  void didUpdateWidget(covariant SalesInvoiceLinesStep oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.showCustomerItemsTab != widget.showCustomerItemsTab) {
      _syncTabController();
    }
  }

  @override
  void dispose() {
    _tabController?.dispose();
    super.dispose();
  }

  void _syncTabController() {
    if (widget.showCustomerItemsTab) {
      if (_tabController == null || _tabController!.length != 2) {
        _tabController?.dispose();
        _tabController = TabController(length: 2, vsync: this);
        _tabController!.addListener(() {
          if (mounted) setState(() {});
        });
      }
    } else {
      _tabController?.dispose();
      _tabController = null;
    }
  }

  bool get _onCustomerTab =>
      widget.showCustomerItemsTab && (_tabController?.index ?? 0) == 1;

  List<SalesCatalogItem> get _sourceItems {
    if (!_onCustomerTab) return widget.items;
    final q = widget.searchController.text.trim().toLowerCase();
    if (q.isEmpty) return widget.customerItems;
    return widget.customerItems.where((it) {
      return it.itemName.toLowerCase().contains(q) ||
          it.itemCode.toLowerCase().contains(q) ||
          it.barcode.toLowerCase().contains(q) ||
          it.brand.toLowerCase().contains(q);
    }).toList();
  }

  bool get _sourceLoading => _onCustomerTab ? widget.customerItemsLoading : widget.loading;
  String? get _sourceError => _onCustomerTab ? widget.customerItemsError : widget.errorMessage;

  Future<void> _refreshActive() async {
    if (_onCustomerTab) {
      await widget.onRefreshCustomerItems?.call();
    } else {
      await widget.onRefresh();
    }
  }

  bool get _showSearchResults =>
      _sourceLoading ||
      _sourceError != null ||
      _sourceItems.isNotEmpty ||
      widget.searchController.text.trim().isNotEmpty ||
      _onCustomerTab;

  Set<String> get _cartCodes =>
      widget.lines.map((l) => l.itemCode.toUpperCase()).toSet();

  List<SalesCatalogItem> get _visibleItems {
    var list = List<SalesCatalogItem>.from(_sourceItems);
    switch (_stockFilter) {
      case _StockFilter.inStock:
        list = list.where((it) => it.stock > _lowStockThreshold).toList();
      case _StockFilter.lowStock:
        list = list.where((it) => it.stock > 0 && it.stock <= _lowStockThreshold).toList();
      case _StockFilter.outOfStock:
        list = list.where((it) => it.stock <= 0).toList();
      case _StockFilter.all:
        break;
    }
    switch (_sort) {
      case _CatalogSort.name:
        list.sort((a, b) {
          final an = a.itemName.isNotEmpty ? a.itemName : a.itemCode;
          final bn = b.itemName.isNotEmpty ? b.itemName : b.itemCode;
          return an.toLowerCase().compareTo(bn.toLowerCase());
        });
      case _CatalogSort.priceLow:
        list.sort((a, b) => a.rate.compareTo(b.rate));
      case _CatalogSort.priceHigh:
        list.sort((a, b) => b.rate.compareTo(a.rate));
      case _CatalogSort.stockHigh:
        list.sort((a, b) => b.stock.compareTo(a.stock));
    }
    return list;
  }

  int get _gridColumns => 3;

  double get _gridAspectRatio {
    final w = MediaQuery.sizeOf(context).width;
    final cellW = (w - 32 - 20) / 3;
    // Text-only cards (no image thumb) — shorter cells than before.
    if (cellW < 105) return 0.85;
    if (cellW < 120) return 0.95;
    return 1.05;
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: _bg,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _searchHeader(),
          if (widget.showCustomerItemsTab && _tabController != null)
            Material(
              color: Colors.white,
              child: TabBar(
                controller: _tabController,
                labelColor: _accent,
                unselectedLabelColor: Colors.grey.shade600,
                indicatorColor: _accent,
                labelStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5),
                tabs: [
                  const Tab(text: 'Items'),
                  Tab(
                    text: widget.customerItems.isEmpty
                        ? 'Customer items'
                        : 'Customer items (${widget.customerItems.length})',
                  ),
                ],
              ),
            ),
          Expanded(child: _buildResultsList()),
        ],
      ),
    );
  }

  Widget _searchHeader() {
    return Material(
      color: Colors.white,
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (widget.showWarehouseHint) ...[
              _warehouseHint(),
              const SizedBox(height: 10),
            ],
            Row(
              children: [
                Expanded(child: _searchField()),
                const SizedBox(width: 10),
                Badge(
                  isLabelVisible: _stockFilter != _StockFilter.all,
                  smallSize: 8,
                  child: Container(
                    decoration: BoxDecoration(
                      color: _bg,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.grey.shade200),
                    ),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: _showFilterSheet,
                      child: const SizedBox(
                        width: 48,
                        height: 48,
                        child: Icon(Icons.tune_rounded, color: _titleColor, size: 22),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            if (widget.lines.isNotEmpty) ...[
              const SizedBox(height: 10),
              _cartSummaryRow(),
            ],
            if (widget.creditBanner != null) ...[
              const SizedBox(height: 10),
              widget.creditBanner!,
            ],
          ],
        ),
      ),
    );
  }

  Widget _searchField() {
    return ValueListenableBuilder<TextEditingValue>(
      valueListenable: widget.searchController,
      builder: (context, value, _) {
        return TextField(
          controller: widget.searchController,
          decoration: InputDecoration(
            hintText: 'Search name, code or barcode…',
            hintStyle: TextStyle(color: Colors.grey.shade500, fontSize: 14),
            prefixIcon: Icon(Icons.search_rounded, size: 22, color: Colors.grey.shade500),
            suffixIcon: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (value.text.isNotEmpty)
                  IconButton(
                    icon: const Icon(Icons.close_rounded, size: 20),
                    onPressed: () {
                      widget.searchController.clear();
                      widget.onSearch();
                    },
                  ),
                IconButton(
                  icon: Icon(Icons.qr_code_scanner_rounded, color: Colors.grey.shade600),
                  tooltip: 'Scan barcode',
                  onPressed: widget.onScan,
                ),
              ],
            ),
            filled: true,
            fillColor: Colors.white,
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
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
          ),
          textInputAction: TextInputAction.search,
          onSubmitted: (_) => widget.onSearch(),
          onChanged: (_) => widget.onSearch(),
        );
      },
    );
  }

  Widget _listToolbar(int count) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
      child: Row(
        children: [
          Text(
            '$count Item${count == 1 ? '' : 's'}',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: _titleColor),
          ),
          const SizedBox(width: 10),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              side: BorderSide(color: Colors.grey.shade300),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
            onPressed: _showSortSheet,
            icon: Icon(Icons.swap_vert_rounded, size: 18, color: Colors.grey.shade700),
            label: Text('Sort', style: TextStyle(fontSize: 13, color: Colors.grey.shade800)),
          ),
          const Spacer(),
          _viewToggle(Icons.grid_view_rounded, _gridView, () => setState(() => _gridView = true)),
          const SizedBox(width: 6),
          _viewToggle(Icons.view_list_rounded, !_gridView, () => setState(() => _gridView = false)),
        ],
      ),
    );
  }

  Widget _viewToggle(IconData icon, bool active, VoidCallback onTap) {
    return Material(
      color: active ? _accent.withValues(alpha: 0.12) : Colors.transparent,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Icon(icon, size: 20, color: active ? _accent : Colors.grey.shade500),
        ),
      ),
    );
  }

  Widget _stockFilterChips({void Function(_StockFilter value)? onSelected}) {
    const filters = [
      (Icons.apps_rounded, 'All', _StockFilter.all),
      (Icons.check_circle_outline_rounded, 'In stock', _StockFilter.inStock),
      (Icons.warning_amber_rounded, 'Low', _StockFilter.lowStock),
      (Icons.remove_shopping_cart_outlined, 'Out', _StockFilter.outOfStock),
    ];
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        for (final (icon, label, value) in filters)
          Expanded(
            child: _categoryChip(
              icon: icon,
              label: label,
              value: value,
              onSelected: onSelected,
            ),
          ),
      ],
    );
  }

  Widget _categoryChip({
    required IconData icon,
    required String label,
    required _StockFilter value,
    void Function(_StockFilter value)? onSelected,
  }) {
    final active = _stockFilter == value;
    return InkWell(
      onTap: () {
        if (onSelected != null) {
          onSelected(value);
        } else {
          setState(() => _stockFilter = value);
        }
      },
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 2),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: active ? _accent.withValues(alpha: 0.12) : const Color(0xFFF0F2F8),
                shape: BoxShape.circle,
                border: Border.all(
                  color: active ? _accent.withValues(alpha: 0.35) : Colors.grey.shade200,
                ),
              ),
              child: Icon(icon, size: 22, color: active ? _accent : Colors.grey.shade600),
            ),
            const SizedBox(height: 6),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: active ? _accent : Colors.grey.shade700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildResultsList() {
    final visible = _visibleItems;
    return RefreshIndicator(
      color: _accent,
      onRefresh: _refreshActive,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (_sourceItems.isNotEmpty && !_sourceLoading)
            SliverToBoxAdapter(child: _listToolbar(visible.length)),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            sliver: _searchResultsSliver(visible),
          ),
        ],
      ),
    );
  }

  Widget _searchResultsSliver(List<SalesCatalogItem> visible) {
    if (_sourceLoading && _sourceItems.isEmpty) {
      return const SliverFillRemaining(
        hasScrollBody: false,
        child: Center(child: CircularProgressIndicator(color: _accent, strokeWidth: 2)),
      );
    }
    if (_sourceError != null && _sourceItems.isEmpty) {
      return SliverFillRemaining(
        hasScrollBody: false,
        child: _messageBox(
          icon: Icons.cloud_off_outlined,
          title: _onCustomerTab ? 'Could not load customer items' : 'Could not load items',
          body: _sourceError!,
          action: TextButton.icon(
            onPressed: _refreshActive,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
          ),
        ),
      );
    }
    if (_onCustomerTab && !_sourceLoading && widget.customerItems.isEmpty) {
      return SliverFillRemaining(
        hasScrollBody: false,
        child: _messageBox(
          icon: Icons.history_rounded,
          title: 'No previous items',
          body: 'This customer has no previous sales in the selected period.',
        ),
      );
    }
    if (!_showSearchResults || _sourceItems.isEmpty) {
      return SliverFillRemaining(
        hasScrollBody: false,
        child: _messageBox(
          icon: Icons.search_rounded,
          title: 'Search products',
          body: 'Type a name, code or barcode — or scan to add items.',
        ),
      );
    }
    if (visible.isEmpty) {
      return SliverFillRemaining(
        hasScrollBody: false,
        child: _messageBox(
          icon: Icons.filter_alt_off_outlined,
          title: 'No matching items',
          body: 'Try another search or clear filters.',
        ),
      );
    }
    if (_gridView) {
      return SliverGrid(
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: _gridColumns,
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: _gridAspectRatio,
        ),
        delegate: SliverChildBuilderDelegate(
          (_, i) => _gridCard(visible[i]),
          childCount: visible.length,
        ),
      );
    }
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (_, i) => Padding(
          padding: EdgeInsets.only(bottom: i == visible.length - 1 ? 0 : 10),
          child: _listCard(visible[i]),
        ),
        childCount: visible.length,
      ),
    );
  }

  bool _canAdd(SalesCatalogItem item) =>
      item.stock > 0 || widget.allowAddWithoutStock;

  void _showItemMenu(SalesCatalogItem item, {required bool canAdd}) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.add_rounded, color: _accent),
              title: const Text('Quick add qty'),
              enabled: canAdd,
              onTap: canAdd
                  ? () {
                      Navigator.pop(ctx);
                      widget.onQuickAdd(item);
                    }
                  : null,
            ),
            ListTile(
              leading: const Icon(Icons.info_outline_rounded, color: _accent),
              title: const Text('Item details'),
              onTap: () {
                Navigator.pop(ctx);
                widget.onItemTap(item);
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _gridCard(SalesCatalogItem item) {
    final inStock = item.stock > 0;
    final canAdd = _canAdd(item);
    final lowStock = inStock && item.stock <= _lowStockThreshold;
    final inCart = _cartCodes.contains(item.itemCode.toUpperCase());
    final displayName = (item.itemName.isNotEmpty ? item.itemName : item.itemCode).toUpperCase();
    final unit = item.unit.isNotEmpty ? item.unit : 'PCS';

    return Material(
      color: inCart ? const Color(0xFFE8F1FF) : Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: inCart ? _accent.withValues(alpha: 0.25) : Colors.grey.shade200),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => widget.onItemTap(item),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      displayName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 11,
                        height: 1.2,
                        color: _titleColor,
                      ),
                    ),
                  ),
                  InkWell(
                    onTap: () => _showItemMenu(item, canAdd: canAdd),
                    child: const Icon(Icons.more_vert_rounded, size: 18, color: _titleColor),
                  ),
                ],
              ),
              const SizedBox(height: 2),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      [
                        'SKU: ${item.itemCode}',
                        if (item.barcode.isNotEmpty) item.barcode,
                      ].join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 9.5, color: Colors.grey.shade600),
                    ),
                  ),
                  const SizedBox(width: 4),
                  _stockBadge(inStock: inStock, lowStock: lowStock, compact: true),
                ],
              ),
              const Spacer(),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      [
                        '${_fmtQty(item.stock)} $unit',
                        item.rate.toStringAsFixed(2),
                        if (item.displayAvgCost > 0) 'Avg ${item.displayAvgCost.toStringAsFixed(2)}',
                      ].join('  ·  '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 11.5, color: _titleColor),
                    ),
                  ),
                  if (canAdd)
                    Material(
                      color: _accent,
                      borderRadius: BorderRadius.circular(8),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(8),
                        onTap: () => widget.onQuickAdd(item),
                        child: const SizedBox(
                          width: 26,
                          height: 26,
                          child: Icon(Icons.add_rounded, color: Colors.white, size: 16),
                        ),
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

  Widget _listCard(SalesCatalogItem item) {
    final inStock = item.stock > 0;
    final canAdd = _canAdd(item);
    final lowStock = inStock && item.stock <= _lowStockThreshold;
    final inCart = _cartCodes.contains(item.itemCode.toUpperCase());
    final displayName = (item.itemName.isNotEmpty ? item.itemName : item.itemCode).toUpperCase();
    final unit = item.unit.isNotEmpty ? item.unit : 'PCS';

    return Material(
      color: inCart ? const Color(0xFFE8F1FF) : Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: inCart ? _accent.withValues(alpha: 0.25) : const Color(0xFFE8EBF3)),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => widget.onItemTap(item),
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
                      displayName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 14,
                        height: 1.2,
                        color: _titleColor,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            [
                              'SKU: ${item.itemCode}',
                              if (item.barcode.isNotEmpty) item.barcode,
                            ].join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          ),
                        ),
                        const SizedBox(width: 6),
                        _stockBadge(inStock: inStock, lowStock: lowStock, compact: true),
                      ],
                    ),
                    if (item.lastBillDate.isNotEmpty || item.lastQty > 0) ...[
                      const SizedBox(height: 3),
                      Text(
                        [
                          if (item.lastQty > 0)
                            'Qty ${_fmtQty(item.lastQty)} ${item.unit.isNotEmpty ? item.unit : 'PCS'}',
                          if (item.lastBillDate.isNotEmpty) item.lastBillDate,
                          if (item.lastBillNo.isNotEmpty) 'Bill ${item.lastBillNo}',
                          if (item.timesOrdered > 1) '×${item.timesOrdered}',
                        ].join(' · '),
                        style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
                      ),
                    ],
                    const SizedBox(height: 6),
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: '${_fmtQty(item.stock)} $unit',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                              color: inStock
                                  ? (lowStock ? const Color(0xFFE65100) : const Color(0xFF2E7D32))
                                  : const Color(0xFFC62828),
                            ),
                          ),
                          TextSpan(
                            text: '  ·  ',
                            style: TextStyle(fontSize: 13, color: Colors.grey.shade400),
                          ),
                          TextSpan(
                            text: item.rate.toStringAsFixed(2),
                            style: const TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 16,
                              color: _titleColor,
                            ),
                          ),
                          if (item.displayAvgCost > 0) ...[
                            TextSpan(
                              text: '  ·  ',
                              style: TextStyle(fontSize: 13, color: Colors.grey.shade400),
                            ),
                            TextSpan(
                              text: 'Avg ${item.displayAvgCost.toStringAsFixed(2)}',
                              style: TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 12.5,
                                color: Colors.grey.shade700,
                              ),
                            ),
                          ],
                          if (item.displayCostPrice > 0 &&
                              (item.displayAvgCost <= 0 ||
                                  (item.displayCostPrice - item.displayAvgCost).abs() > 0.009)) ...[
                            TextSpan(
                              text: '  ·  Cost ${item.displayCostPrice.toStringAsFixed(2)}',
                              style: TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 12,
                                color: Colors.grey.shade600,
                              ),
                            ),
                          ],
                        ],
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Material(
                color: canAdd ? _accent : Colors.grey.shade300,
                borderRadius: BorderRadius.circular(10),
                child: InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: canAdd
                      ? () {
                          widget.onQuickAdd(item);
                        }
                      : null,
                  child: const SizedBox(
                    width: 44,
                    height: 44,
                    child: Icon(Icons.add_rounded, color: Colors.white, size: 26),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _stockBadge({required bool inStock, required bool lowStock, bool compact = false}) {
    late final String label;
    late final Color bg;
    late final Color fg;
    if (!inStock) {
      label = compact ? 'Out' : 'Out of stock';
      bg = const Color(0xFFFFEBEE);
      fg = const Color(0xFFC62828);
    } else if (lowStock) {
      label = compact ? 'Low' : 'Low stock';
      bg = const Color(0xFFFFF3E0);
      fg = const Color(0xFFE65100);
    } else {
      label = compact ? 'In stock' : 'In stock';
      bg = const Color(0xFFE8F5E9);
      fg = const Color(0xFF2E7D32);
    }
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 4 : 6, vertical: compact ? 2 : 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(5)),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(fontSize: compact ? 8 : 9.5, fontWeight: FontWeight.w700, color: fg),
      ),
    );
  }

  void _showSortSheet() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 8),
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.shade300,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Sort by', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            ),
            _sortTile('Name (A–Z)', _CatalogSort.name),
            _sortTile('Price: low to high', _CatalogSort.priceLow),
            _sortTile('Price: high to low', _CatalogSort.priceHigh),
            _sortTile('Stock: high to low', _CatalogSort.stockHigh),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  Widget _sortTile(String label, _CatalogSort value) {
    return ListTile(
      title: Text(label),
      trailing: _sort == value ? const Icon(Icons.check_rounded, color: _accent) : null,
      onTap: () {
        setState(() => _sort = value);
        Navigator.pop(context);
      },
    );
  }

  void _showFilterSheet() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
          child: StatefulBuilder(
            builder: (ctx, setSheet) {
              return Column(
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
                  const Text('Filters', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                  const SizedBox(height: 6),
                  Text('Stock', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: Colors.grey.shade700)),
                  const SizedBox(height: 10),
                  _stockFilterChips(
                    onSelected: (v) {
                      setState(() => _stockFilter = v);
                      setSheet(() {});
                    },
                  ),
                  const SizedBox(height: 8),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.qr_code_scanner_rounded, color: _accent),
                    title: const Text('Scan barcode'),
                    onTap: () {
                      Navigator.pop(ctx);
                      widget.onScan();
                    },
                  ),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.swap_vert_rounded, color: _accent),
                    title: const Text('Sort items'),
                    onTap: () {
                      Navigator.pop(ctx);
                      _showSortSheet();
                    },
                  ),
                  if (widget.warehouseLabel.isNotEmpty)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.home_outlined, color: _accent),
                      title: Text(widget.warehouseLabel, maxLines: 2, overflow: TextOverflow.ellipsis),
                    ),
                  const SizedBox(height: 8),
                  FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: _accent, minimumSize: const Size(double.infinity, 46)),
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('Done', style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _cartSummaryRow() {
    final count = widget.lines.length;
    final total = widget.netTotal.toStringAsFixed(2);
    return InkWell(
      onTap: widget.onOpenCart,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            const Icon(Icons.shopping_cart_outlined, size: 20, color: _accent),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Cart $count · Total $total',
                style: const TextStyle(
                  color: _accent,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
            ),
            const Text(
              'Checkout',
              style: TextStyle(
                color: _accent,
                fontWeight: FontWeight.w700,
                fontSize: 14,
              ),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.open_in_new_rounded, size: 18, color: _accent),
          ],
        ),
      ),
    );
  }

  Widget _warehouseHint() => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF8E1),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color(0xFFFFE082)),
        ),
        child: Row(
          children: [
            const Icon(Icons.info_outline_rounded, size: 18, color: Color(0xFFF57C00)),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Select warehouse on the previous step to load stock by location.',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade800, height: 1.35),
              ),
            ),
          ],
        ),
      );

  Widget _messageBox({
    required IconData icon,
    required String title,
    required String body,
    Widget? action,
  }) =>
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 40, color: Colors.grey.shade400),
              const SizedBox(height: 10),
              Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              const SizedBox(height: 6),
              Text(
                body,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, height: 1.4, color: Colors.grey.shade600),
              ),
              if (action != null) ...[const SizedBox(height: 12), action],
            ],
          ),
        ),
      );

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(2);
  }
}

typedef SalesInvoiceCatalogStep = SalesInvoiceLinesStep;
