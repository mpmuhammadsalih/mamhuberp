import 'package:flutter/material.dart';

import '../../services/purchase_order_service.dart';

String purchaseCatalogFmtQty(double q) {
  if (q == q.roundToDouble()) return q.round().toString();
  return q.toStringAsFixed(2);
}

/// Avg cost line shown under item code.
Widget purchaseCatalogAvgCostLine(PurchaseCatalogItem item) {
  return Text(
    'Avg cost ${item.displayAvgCost.toStringAsFixed(2)}',
    style: const TextStyle(
      fontSize: 12,
      fontWeight: FontWeight.w600,
      color: Color(0xFF6B7280),
    ),
  );
}

/// Cost price on the right (used when adding).
Widget purchaseCatalogCostPriceColumn(PurchaseCatalogItem item) {
  return Column(
    crossAxisAlignment: CrossAxisAlignment.end,
    mainAxisSize: MainAxisSize.min,
    children: [
      Text(
        item.displayCostPrice.toStringAsFixed(2),
        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF1565C0)),
      ),
      const Text(
        'Cost price',
        style: TextStyle(fontSize: 10, color: Color(0xFF6B7280)),
      ),
    ],
  );
}

/// Last purchase line for Supplier items tab (qty · date).
String? purchaseSupplierHistoryLine(PurchaseCatalogItem item) {
  if (!item.hasSupplierHistory) return null;
  final parts = <String>[];
  if (item.lastQty > 0) {
    parts.add('Qty ${purchaseCatalogFmtQty(item.lastQty)} ${item.uom}');
  }
  if (item.lastReceiptDate.isNotEmpty) {
    parts.add(item.lastReceiptDate);
  }
  if (item.lastReceiptNo.isNotEmpty) {
    parts.add('GRN ${item.lastReceiptNo}');
  }
  return parts.isEmpty ? null : parts.join(' · ');
}

/// Items / Supplier items tabs — same pattern as Sales Customer items.
class PurchaseCatalogTabsBody extends StatefulWidget {
  const PurchaseCatalogTabsBody({
    super.key,
    required this.showSupplierTab,
    required this.items,
    required this.supplierItems,
    required this.itemsLoading,
    required this.supplierItemsLoading,
    required this.onRetryItems,
    required this.onRetrySupplierItems,
    required this.itemBuilder,
    this.itemsError,
    this.supplierItemsError,
    this.searchQuery = '',
    this.padding = const EdgeInsets.fromLTRB(14, 0, 14, 16),
  });

  final bool showSupplierTab;
  final List<PurchaseCatalogItem> items;
  final List<PurchaseCatalogItem> supplierItems;
  final bool itemsLoading;
  final bool supplierItemsLoading;
  final String? itemsError;
  final String? supplierItemsError;
  final VoidCallback onRetryItems;
  final VoidCallback onRetrySupplierItems;
  final Widget Function(BuildContext context, PurchaseCatalogItem item) itemBuilder;
  final String searchQuery;
  final EdgeInsetsGeometry padding;

  @override
  State<PurchaseCatalogTabsBody> createState() => _PurchaseCatalogTabsBodyState();
}

class _PurchaseCatalogTabsBodyState extends State<PurchaseCatalogTabsBody>
    with SingleTickerProviderStateMixin {
  static const _accent = Color(0xFF1565C0);

  TabController? _tabController;

  @override
  void initState() {
    super.initState();
    _syncTabController();
  }

  @override
  void didUpdateWidget(covariant PurchaseCatalogTabsBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.showSupplierTab != widget.showSupplierTab) {
      _syncTabController();
    }
  }

  @override
  void dispose() {
    _tabController?.dispose();
    super.dispose();
  }

  void _syncTabController() {
    if (widget.showSupplierTab) {
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

  bool get _onSupplierTab =>
      widget.showSupplierTab && (_tabController?.index ?? 0) == 1;

  List<PurchaseCatalogItem> get _sourceItems {
    if (!_onSupplierTab) return widget.items;
    final q = widget.searchQuery.trim().toLowerCase();
    if (q.isEmpty) return widget.supplierItems;
    return widget.supplierItems.where((it) {
      return it.itemName.toLowerCase().contains(q) ||
          it.itemCode.toLowerCase().contains(q) ||
          it.barcode.toLowerCase().contains(q);
    }).toList();
  }

  bool get _sourceLoading =>
      _onSupplierTab ? widget.supplierItemsLoading : widget.itemsLoading;

  String? get _sourceError =>
      _onSupplierTab ? widget.supplierItemsError : widget.itemsError;

  VoidCallback get _onRetry =>
      _onSupplierTab ? widget.onRetrySupplierItems : widget.onRetryItems;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.showSupplierTab && _tabController != null)
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
                  text: widget.supplierItems.isEmpty
                      ? 'Supplier items'
                      : 'Supplier items (${widget.supplierItems.length})',
                ),
              ],
            ),
          ),
        Expanded(child: _buildList()),
      ],
    );
  }

  Widget _buildList() {
    if (_sourceLoading && _sourceItems.isEmpty) {
      return const Center(child: CircularProgressIndicator(color: _accent));
    }
    if (_sourceError != null && _sourceItems.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _sourceError!,
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey.shade700),
              ),
              const SizedBox(height: 12),
              TextButton(onPressed: _onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_sourceItems.isEmpty) {
      final emptyMsg = _onSupplierTab
          ? (widget.searchQuery.trim().isEmpty
              ? 'No items purchased from this supplier yet.'
              : 'No supplier items match your search.')
          : (widget.searchQuery.trim().isEmpty
              ? 'No catalog items found.'
              : 'No items match your search.');
      return Center(
        child: Text(emptyMsg, style: TextStyle(color: Colors.grey.shade600)),
      );
    }
    return ListView.builder(
      padding: widget.padding,
      itemCount: _sourceItems.length,
      itemBuilder: (ctx, i) => widget.itemBuilder(ctx, _sourceItems[i]),
    );
  }
}
