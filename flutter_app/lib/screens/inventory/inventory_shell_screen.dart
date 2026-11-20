import 'package:flutter/material.dart';

import '../../core/storage/last_nav_storage.dart';
import 'grn_screen.dart';
import 'purchase_order_screen.dart';
import 'stock_return_screen.dart';
import 'stock_count_choose_screen.dart';
import 'barcode_scanning_hub_screen.dart';
import 'item_ledger_screen.dart';
import 'stock_lookup_screen.dart';
import 'stock_transfer_list_screen.dart';
import 'stock_adjustment_screen.dart';
import '../masters/brand_master_screen.dart';
import '../masters/category_master_screen.dart';
import '../masters/customer_list_screen.dart';
import '../masters/item_list_screen.dart';
import '../masters/supplier_list_screen.dart';
import '../masters/unit_master_screen.dart';
import '../purchase_screen.dart';
import '../../core/theme/app_theme.dart';

/// Bottom-tab root for Inventory: shows Quick Actions hub, nested routes for each flow.
class InventoryShellScreen extends StatefulWidget {
  const InventoryShellScreen({super.key, this.onOpenDrawer});

  final VoidCallback? onOpenDrawer;

  @override
  State<InventoryShellScreen> createState() => InventoryShellScreenState();
}

class InventoryShellScreenState extends State<InventoryShellScreen> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  /// Reset stack to hub, then optionally open a flow (drawer shortcuts).
  void syncFromShell(String menuLabel) {
    final nav = _navigatorKey.currentState;
    if (nav == null) return;

    nav.popUntil((route) => route.isFirst);

    if (menuLabel == 'Quick Actions') {
      return;
    }

    final page = inventoryPageForLabel(menuLabel);
    if (page != null) {
      nav.push<void>(MaterialPageRoute<void>(builder: (_) => page));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Navigator(
      key: _navigatorKey,
      onGenerateRoute: (RouteSettings settings) {
        final name = settings.name ?? '/';
        final isHub = name == '/' || name == '/hub';
        if (!isHub) {
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (_) => const Scaffold(body: Center(child: Text('Unknown route'))),
          );
        }

        return MaterialPageRoute<void>(
          settings: const RouteSettings(name: '/'),
          builder: (ctx) => InventoryQuickActionsScreen(
            onOpenDrawer: widget.onOpenDrawer,
            onActionSelected: (label) {
              LastNavStorage.saveMenu(label);
              final next = inventoryPageForLabel(label);
              if (next != null) {
                Navigator.of(ctx).push<void>(
                  MaterialPageRoute<void>(
                    builder: (_) => next,
                    settings: RouteSettings(name: '/${label.hashCode}'),
                  ),
                );
              }
            },
          ),
        );
      },
    );
  }
}

Widget? inventoryPageForLabel(String label) {
  switch (label) {
    case 'Purchase Order':
      return const PurchaseOrderScreen();
    case 'Goods Receiving':
      return const PurchaseScreen();
    case 'GRN':
      return const GrnScreen();
    case 'Stock Transfer':
      return const StockTransferListScreen();
    case 'Stock Return':
    case 'Purchase Return':
      return const StockReturnScreen();
    case 'Stock Adjustment':
      return const StockAdjustmentScreen();
    case 'Stock Counting':
      return const StockCountChooseScreen();
    case 'Barcode Scanning':
      return const BarcodeScanningHubScreen();
    case 'Stock Lookup':
      return const StockLookupScreen();
    case 'Item Ledger':
    case 'Item ledger':
      return const ItemLedgerScreen();
    case 'Customers':
      return const CustomerListScreen();
    case 'Items':
    case 'Item':
      return const ItemListScreen();
    case 'Category Master':
      return const CategoryMasterScreen();
    case 'Brand Master':
      return const BrandMasterScreen();
    case 'Unit of measurement':
    case 'Unit of Measurement':
    case 'UOM Master':
      return const UnitMasterScreen();
    case 'Warehouses':
      return const InventoryPlaceholderScreen(
        title: 'Warehouses',
        subtitle: 'Warehouse master browse will be available here.',
      );
    case 'Suppliers':
      return const SupplierListScreen();
    default:
      return null;
  }
}

class InventoryQuickActionsScreen extends StatelessWidget {
  const InventoryQuickActionsScreen({
    super.key,
    this.onOpenDrawer,
    required this.onActionSelected,
  });

  final VoidCallback? onOpenDrawer;
  final void Function(String label) onActionSelected;

  static const List<_QuickActionItem> _items = [
    _QuickActionItem('Items', 'Item master & barcodes', Icons.inventory_2_outlined, Color(0xFF00897B)),
    _QuickActionItem('Suppliers', 'Create & manage suppliers', Icons.storefront_outlined, Color(0xFF2E7D32)),
    _QuickActionItem('Category Master', 'Main / category / micro', Icons.account_tree_outlined, Color(0xFF00897B)),
    _QuickActionItem('Brand Master', 'Brand, shelf & color', Icons.sell_outlined, Color(0xFF6A1B9A)),
    _QuickActionItem('Unit of measurement', 'Create & manage UOMs', Icons.straighten_outlined, Color(0xFF455A64)),
    _QuickActionItem('Purchase Order', 'Create & manage LPOs', Icons.shopping_bag_outlined, Color(0xFF1565C0)),
    _QuickActionItem('Goods Receiving', 'Receive vs purchase orders', Icons.south_rounded, Color(0xFF2E7D32)),
    _QuickActionItem('GRN', 'Receipt notes & history', Icons.receipt_long_rounded, Color(0xFF0277BD)),
    _QuickActionItem('Stock Transfer', 'Transfer Stock', Icons.swap_horiz_rounded, Color(0xFF0277BD)),
    _QuickActionItem('Purchase Return', 'Return to supplier', Icons.compare_arrows_rounded, Color(0xFF6A1B9A)),
    _QuickActionItem('Stock Adjustment', 'Adjust Stock', Icons.rotate_left_rounded, Color(0xFFEF6C00)),
    _QuickActionItem('Stock Counting', 'Count Stock', Icons.fact_check_rounded, Color(0xFF5E35B1)),
    _QuickActionItem('Barcode Scanning', 'Scan Barcode', Icons.qr_code_scanner_rounded, Color(0xFF0277BD)),
    _QuickActionItem('Stock Lookup', 'Search Stock', Icons.search_rounded, Color(0xFF00838F)),
    _QuickActionItem('Item Ledger', 'Purchase / sale / adj history', Icons.menu_book_rounded, Color(0xFF00838F)),
  ];

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
          onPressed: () {
            final nav = Navigator.of(context);
            if (nav.canPop()) {
              nav.pop();
            } else {
              onOpenDrawer?.call();
            }
          },
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
        ),
        title: const Text('Quick Actions', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: GridView.builder(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 88),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.12,
                ),
                itemCount: _items.length,
                itemBuilder: (context, i) {
                  final item = _items[i];
                  return Material(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    child: InkWell(
                      onTap: () => onActionSelected(item.title),
                      borderRadius: BorderRadius.circular(14),
                      child: Ink(
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFFE8EBF3)),
                          boxShadow: const [BoxShadow(color: Color(0x08000000), blurRadius: 6, offset: Offset(0, 2))],
                        ),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Container(
                                width: 48,
                                height: 48,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(10),
                                  color: Color.lerp(item.color, Colors.white, 0.92)!,
                                ),
                                child: Icon(item.icon, color: item.color, size: 26),
                              ),
                              const SizedBox(height: 10),
                              Text(
                                item.title,
                                textAlign: TextAlign.center,
                                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                item.subtitle,
                                textAlign: TextAlign.center,
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade600, height: 1.25),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
    );
  }
}

class _QuickActionItem {
  const _QuickActionItem(this.title, this.subtitle, this.icon, this.color);

  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
}

class InventoryPlaceholderScreen extends StatelessWidget {
  const InventoryPlaceholderScreen({
    super.key,
    required this.title,
    required this.subtitle,
  });

  final String title;
  final String subtitle;

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
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      backgroundColor: const Color(0xFFF6F7FC),
      body: Padding(
        padding: const EdgeInsets.all(22),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE8EBF3)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.preview_outlined, size: 40, color: Colors.grey.shade400),
              const SizedBox(height: 16),
              Text(subtitle, style: TextStyle(fontSize: 15, color: Colors.grey.shade700, height: 1.35)),
              const SizedBox(height: 14),
              Text(
                'This flow will connect to the ERP module when ready.',
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade500),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
