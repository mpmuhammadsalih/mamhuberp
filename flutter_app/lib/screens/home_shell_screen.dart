import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/mobile_menu_item.dart';
import '../core/network/access_denied_alert.dart';
import '../core/storage/last_nav_storage.dart';
import '../providers/auth_provider.dart';
import '../widgets/nexus_erp_logo.dart';
import 'accounts/accounts_shell_screen.dart';
import 'dashboard_screen.dart';
import 'inventory/inventory_shell_screen.dart';
import 'profile_settings_screen.dart';
import 'reports/business_summary_screen.dart';
import 'reports/inventory_aging_report_screen.dart';
import 'reports/inventory_history_report_screen.dart';
import 'reports/sales_details_report_screen.dart';
import 'reports/sales_reports_screen.dart';
import 'reports/stock_ledger_report_screen.dart';
import 'reports/stock_summary_report_screen.dart';
import 'reports/supplier_balance_report_screen.dart';
import 'reports/transaction_report_screen.dart';
import 'reports/warehouse_summary_report_screen.dart';
import 'reports/customer_wise_sales_report_screen.dart';
import 'reports_screen.dart';
import 'sales/sales_shell_screen.dart';
import 'sales/sales_x_report_screen.dart';
import 'setup/transaction_date_setup_screen.dart';

const _menuIcons = <String, IconData>{
  'dashboard': Icons.home_rounded,
  'purchase_order': Icons.shopping_bag_outlined,
  'goods_receiving': Icons.south_rounded,
  'grn': Icons.receipt_long_rounded,
  'stock_transfer': Icons.swap_horiz_rounded,
  'stock_return': Icons.assignment_return_rounded,
  'stock_adjustment': Icons.tune_rounded,
  'stock_counting': Icons.fact_check_outlined,
  'barcode_scanning': Icons.qr_code_scanner_rounded,
  'stock_lookup': Icons.manage_search_rounded,
  'item_ledger': Icons.menu_book_rounded,
  'customers': Icons.people_alt_outlined,
  'customer_category': Icons.category_outlined,
  'items': Icons.widgets_outlined,
  'category_master': Icons.account_tree_outlined,
  'brand_master': Icons.sell_outlined,
  'unit_master': Icons.straighten_outlined,
  'warehouses': Icons.warehouse_outlined,
  'suppliers': Icons.person_outline_rounded,
  'stock_ledger': Icons.receipt_long_rounded,
  'stock_summary': Icons.pie_chart_outline_rounded,
  'inventory_history': Icons.history_rounded,
  'inventory_aging': Icons.timelapse_rounded,
  'warehouse_summary': Icons.warehouse_outlined,
  'supplier_balance': Icons.people_alt_outlined,
  'sales_order': Icons.assignment_outlined,
  'sales': Icons.receipt_long_outlined,
  'sales_return': Icons.assignment_return_outlined,
  'sales_reports': Icons.bar_chart_rounded,
  'business_summary': Icons.insights_rounded,
  'transaction_summary': Icons.summarize_outlined,
  'transaction_details': Icons.list_alt_rounded,
  'sales_details': Icons.receipt_long_outlined,
  'x_report': Icons.assessment_outlined,
  'customer_wise_sales': Icons.people_outline_rounded,
  'cash_payment_voucher': Icons.payments_outlined,
  'pos_settlement': Icons.point_of_sale_outlined,
  'ai_sales_mode': Icons.record_voice_over_outlined,
  'trial_balance': Icons.account_balance_wallet_outlined,
  'profit_loss': Icons.trending_up_rounded,
  'balance_sheet': Icons.account_balance_outlined,
  'customer_ledger': Icons.people_outline_rounded,
  'supplier_ledger': Icons.storefront_outlined,
  'journal_entry': Icons.menu_book_outlined,
  'accounts_receivable': Icons.call_received_rounded,
  'accounts_payable': Icons.call_made_rounded,
  'transaction_date_setup': Icons.event_available_rounded,
  'settings': Icons.settings_outlined,
};

class HomeShellScreen extends StatefulWidget {
  const HomeShellScreen({super.key});

  @override
  State<HomeShellScreen> createState() => _HomeShellScreenState();
}

class _HomeShellScreenState extends State<HomeShellScreen> {
  int _index = 0;
  String _selectedMenu = 'Dashboard';

  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final GlobalKey<InventoryShellScreenState> _inventoryNavKey =
      GlobalKey<InventoryShellScreenState>();
  final GlobalKey<SalesShellScreenState> _salesNavKey =
      GlobalKey<SalesShellScreenState>();
  final GlobalKey<AccountsShellScreenState> _accountsNavKey =
      GlobalKey<AccountsShellScreenState>();

  late final List<Widget> _screens;

  @override
  void initState() {
    super.initState();
    _screens = <Widget>[
      DashboardScreen(
        onOpenMenu: (menuLabel) => _navigateTo(_shellIndexForNav(menuLabel), menuLabel),
      ),
      InventoryShellScreen(
        key: _inventoryNavKey,
        onOpenDrawer: () => _scaffoldKey.currentState?.openDrawer(),
      ),
      SalesShellScreen(
        key: _salesNavKey,
        onOpenDrawer: () => _scaffoldKey.currentState?.openDrawer(),
      ),
      AccountsShellScreen(
        key: _accountsNavKey,
        onOpenDrawer: () => _scaffoldKey.currentState?.openDrawer(),
      ),
      const ReportsScreen(),
    ];
    WidgetsBinding.instance.addPostFrameCallback((_) => _restoreLastNav());
  }

  Future<void> _restoreLastNav() async {
    final menuLabel = await LastNavStorage.readMenu();
    if (!mounted || menuLabel == null || menuLabel == 'Dashboard') return;

    // Don't auto-open pushed full-screen routes or settings on cold start.
    const skipRestore = {
      'Settings',
      'Transaction Date Setup',
      'Summary',
      'Details',
      'Sales Details',
      'X Report',
      'Customer Wise Sales',
      'Business Summary',
      'Sales Reports',
      'Stock Ledger',
      'Stock Summary',
      'Inventory History',
      'Inventory Aging',
      'Warehouse Summary',
      'Supplier Balance',
    };
    if (skipRestore.contains(menuLabel)) return;

    final auth = context.read<AuthProvider>();
    final user = auth.user;
    const shellHubLabels = {'Quick Actions', 'Sales Hub', 'Accounts Hub', 'Reports Hub'};
    if (user != null &&
        user.mobileMenus.isNotEmpty &&
        !shellHubLabels.contains(menuLabel) &&
        !user.canNavigate(menuLabel)) {
      return;
    }

    final index = _shellIndexForNav(menuLabel);
    if (!mounted) return;
    setState(() {
      _index = index;
      _selectedMenu = menuLabel;
    });

    if (index == 1) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _inventoryNavKey.currentState?.syncFromShell(menuLabel);
      });
    } else if (index == 2) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _salesNavKey.currentState?.syncFromShell(menuLabel);
      });
    } else if (index == 3) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _accountsNavKey.currentState?.syncFromShell(menuLabel);
      });
    }
  }

  static const _txnDateSetupItem = MobileMenuItem(
    id: 'transaction_date_setup',
    label: 'Transaction Date Setup',
    nav: 'Transaction Date Setup',
  );

  /// Ensure General Setup appears even when login JWT menus predate this feature.
  List<MobileMenuSection> _withGeneralSetup(
    List<MobileMenuSection> menus, {
    required bool forceShow,
  }) {
    if (!forceShow) return menus;
    final already = menus.any(
      (s) => s.items.any((i) => i.nav == 'Transaction Date Setup' || i.id == 'transaction_date_setup'),
    );
    if (already) return menus;

    final setupSection = MobileMenuSection(
      section: 'GENERAL SETUP',
      items: const [_txnDateSetupItem],
    );
    // Insert above Settings (last untitled section) when present.
    final out = List<MobileMenuSection>.from(menus);
    var settingsIdx = -1;
    for (var i = out.length - 1; i >= 0; i--) {
      if (out[i].section == null && out[i].items.any((e) => e.nav == 'Settings')) {
        settingsIdx = i;
        break;
      }
    }
    if (settingsIdx >= 0) {
      out.insert(settingsIdx, setupSection);
    } else {
      out.add(setupSection);
    }
    return out;
  }

  /// Put Items first in INVENTORY when missing (hub + drawer parity).
  List<MobileMenuSection> _withItemsBeforePurchaseOrder(List<MobileMenuSection> menus) {
    const itemsItem = MobileMenuItem(id: 'items', label: 'Items', nav: 'Items');
    return menus.map((section) {
      if (section.section != 'INVENTORY') return section;
      final already = section.items.any((i) => i.nav == 'Items' || i.id == 'items');
      if (already) {
        // Move Items before Purchase Order when both exist.
        final rest = section.items.where((i) => i.nav != 'Items' && i.id != 'items').toList();
        final items = section.items.where((i) => i.nav == 'Items' || i.id == 'items').toList();
        final poIdx = rest.indexWhere((i) => i.nav == 'Purchase Order' || i.id == 'purchase_order');
        if (poIdx < 0) {
          return MobileMenuSection(section: section.section, items: [...items, ...rest]);
        }
        final merged = [...rest.sublist(0, poIdx), ...items, ...rest.sublist(poIdx)];
        return MobileMenuSection(section: section.section, items: merged);
      }
      final poIdx = section.items.indexWhere((i) => i.nav == 'Purchase Order' || i.id == 'purchase_order');
      if (poIdx < 0) {
        return MobileMenuSection(section: section.section, items: [itemsItem, ...section.items]);
      }
      final items = [...section.items];
      items.insert(poIdx, itemsItem);
      return MobileMenuSection(section: section.section, items: items);
    }).toList();
  }

  List<MobileMenuSection> _menuSections(AuthProvider auth) {
    final menus = auth.user?.mobileMenus ?? const [];
    if (menus.isNotEmpty) {
      // Always surface General Setup (API still enforces permission on open/save).
      return _withGeneralSetup(_withItemsBeforePurchaseOrder(menus), forceShow: true);
    }
    // Legacy API: show full drawer until server returns ERP menus.
    return _withGeneralSetup([
      MobileMenuSection(items: const [
        MobileMenuItem(id: 'dashboard', label: 'Dashboard', nav: 'Dashboard'),
      ]),
      MobileMenuSection(section: 'INVENTORY', items: const [
        MobileMenuItem(id: 'items', label: 'Items', nav: 'Items'),
        MobileMenuItem(id: 'suppliers', label: 'Suppliers', nav: 'Suppliers'),
        MobileMenuItem(id: 'purchase_order', label: 'Purchase Order', nav: 'Purchase Order'),
        MobileMenuItem(id: 'goods_receiving', label: 'Goods Receiving', nav: 'Goods Receiving'),
        MobileMenuItem(id: 'grn', label: 'GRN', nav: 'GRN'),
        MobileMenuItem(id: 'stock_transfer', label: 'Stock Transfer', nav: 'Stock Transfer'),
        MobileMenuItem(id: 'stock_return', label: 'Purchase Return', nav: 'Purchase Return'),
        MobileMenuItem(id: 'stock_adjustment', label: 'Stock Adjustment', nav: 'Stock Adjustment'),
        MobileMenuItem(id: 'stock_counting', label: 'Stock Counting', nav: 'Stock Counting'),
        MobileMenuItem(id: 'barcode_scanning', label: 'Barcode Scanning', nav: 'Barcode Scanning'),
        MobileMenuItem(id: 'stock_lookup', label: 'Stock Lookup', nav: 'Stock Lookup'),
        MobileMenuItem(id: 'item_ledger', label: 'Item Ledger', nav: 'Item Ledger'),
      ]),
      MobileMenuSection(section: 'SALES', items: const [
        MobileMenuItem(id: 'sales_order', label: 'Sales Order', nav: 'Sales Order'),
        MobileMenuItem(id: 'sales', label: 'Sales', nav: 'Sales'),
        MobileMenuItem(id: 'sales_return', label: 'Sales Return', nav: 'Sales Return'),
        MobileMenuItem(id: 'x_report', label: 'X Report', nav: 'X Report'),
        MobileMenuItem(id: 'customer_wise_sales', label: 'Customer Wise Sales', nav: 'Customer Wise Sales'),
        MobileMenuItem(id: 'customers', label: 'Customers', nav: 'Customers'),
        MobileMenuItem(id: 'customer_category', label: 'Customer Category', nav: 'Customer Category'),
      ]),
      MobileMenuSection(section: 'ACCOUNTS', items: const [
        MobileMenuItem(id: 'cash_payment_voucher', label: 'Cash Payment Voucher', nav: 'Cash Payment Voucher'),
        MobileMenuItem(id: 'pos_settlement', label: 'POS Settlement', nav: 'POS Settlement'),
        MobileMenuItem(id: 'trial_balance', label: 'Trial Balance', nav: 'Trial Balance'),
        MobileMenuItem(id: 'profit_loss', label: 'Profit & Loss', nav: 'Profit & Loss'),
        MobileMenuItem(id: 'balance_sheet', label: 'Balance Sheet', nav: 'Balance Sheet'),
        MobileMenuItem(id: 'customer_ledger', label: 'Customer Ledger', nav: 'Customer Ledger'),
        MobileMenuItem(id: 'supplier_ledger', label: 'Supplier Ledger', nav: 'Supplier Ledger'),
        MobileMenuItem(id: 'journal_entry', label: 'Journal Entry', nav: 'Journal Entry'),
        MobileMenuItem(id: 'accounts_receivable', label: 'Accounts Receivable', nav: 'Accounts Receivable'),
        MobileMenuItem(id: 'accounts_payable', label: 'Accounts Payable', nav: 'Accounts Payable'),
      ]),
      MobileMenuSection(section: 'MASTERS', items: const [
        MobileMenuItem(id: 'customers', label: 'Customers', nav: 'Customers'),
        MobileMenuItem(id: 'items', label: 'Items', nav: 'Items'),
        MobileMenuItem(id: 'category_master', label: 'Category Master', nav: 'Category Master'),
        MobileMenuItem(id: 'brand_master', label: 'Brand Master', nav: 'Brand Master'),
        MobileMenuItem(id: 'unit_master', label: 'Unit of measurement', nav: 'Unit of measurement'),
        MobileMenuItem(id: 'warehouses', label: 'Warehouses', nav: 'Warehouses'),
        MobileMenuItem(id: 'suppliers', label: 'Suppliers', nav: 'Suppliers'),
      ]),
      MobileMenuSection(section: 'REPORTS', items: const [
        MobileMenuItem(id: 'transaction_summary', label: 'Summary', nav: 'Summary'),
        MobileMenuItem(id: 'transaction_details', label: 'Details', nav: 'Details'),
        MobileMenuItem(id: 'sales_details', label: 'Sales Details', nav: 'Sales Details'),
        MobileMenuItem(id: 'x_report', label: 'X Report', nav: 'X Report'),
        MobileMenuItem(id: 'customer_wise_sales', label: 'Customer Wise Sales', nav: 'Customer Wise Sales'),
        MobileMenuItem(id: 'business_summary', label: 'Business Summary', nav: 'Business Summary'),
        MobileMenuItem(id: 'sales_reports', label: 'Sales Reports', nav: 'Sales Reports'),
        MobileMenuItem(id: 'stock_ledger', label: 'Stock Ledger', nav: 'Stock Ledger'),
        MobileMenuItem(id: 'stock_summary', label: 'Stock Summary', nav: 'Stock Summary'),
        MobileMenuItem(id: 'inventory_history', label: 'Inventory History', nav: 'Inventory History'),
        MobileMenuItem(id: 'inventory_aging', label: 'Inventory Aging', nav: 'Inventory Aging'),
        MobileMenuItem(id: 'warehouse_summary', label: 'Warehouse Summary', nav: 'Warehouse Summary'),
        MobileMenuItem(id: 'supplier_balance', label: 'Supplier Balance', nav: 'Supplier Balance'),
      ]),
      MobileMenuSection(section: 'GENERAL SETUP', items: const [_txnDateSetupItem]),
      MobileMenuSection(items: const [
        MobileMenuItem(id: 'settings', label: 'Settings', nav: 'Settings'),
      ]),
    ], forceShow: true);
  }

  static const _salesNavLabels = {
    'Sales Order',
    'Sales',
    'AI Sales Mode',
    'Sales Return',
    'X Report',
    'Customer Wise Sales',
    'Customers',
    'Customer Category',
    'Sales Hub',
  };

  static const _accountsNavLabels = {
    'Cash Payment Voucher',
    'POS Settlement',
    'Trial Balance',
    'Profit & Loss',
    'Balance Sheet',
    'Customer Ledger',
    'Supplier Ledger',
    'Journal Entry',
    'Accounts Receivable',
    'Accounts Payable',
    'Accounts Hub',
  };

  int _shellIndexForNav(String nav) {
    if (nav == 'Settings' || nav == 'Transaction Date Setup') return _index;
    const reports = {
      'Reports Hub',
      'Summary',
      'Details',
      'Sales Details',
      'X Report',
      'Customer Wise Sales',
      'Stock Ledger',
      'Stock Summary',
      'Inventory History',
      'Inventory Aging',
      'Warehouse Summary',
      'Supplier Balance',
      'Business Summary',
      'Sales Reports',
    };
    if (reports.contains(nav)) return 4;
    if (_accountsNavLabels.contains(nav)) return 3;
    if (_salesNavLabels.contains(nav)) return 2;
    if (nav == 'Dashboard') return 0;
    return 1;
  }

  bool _hasAccountsMenus(List<MobileMenuSection> sections) {
    for (final block in sections) {
      if (block.section == 'ACCOUNTS' && block.items.isNotEmpty) return true;
    }
    return false;
  }

  bool _hasInventoryMenus(List<MobileMenuSection> sections) {
    for (final block in sections) {
      if (block.section == 'INVENTORY' || block.section == 'MASTERS') {
        if (block.items.isNotEmpty) return true;
      }
    }
    return false;
  }

  bool _hasReportMenus(List<MobileMenuSection> sections) {
    for (final block in sections) {
      if (block.section == 'REPORTS' && block.items.isNotEmpty) return true;
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final sections = _menuSections(auth);
    final showInventory = _hasInventoryMenus(sections);
    final showAccounts = _hasAccountsMenus(sections);
    final showReports = _hasReportMenus(sections);

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: const Color(0xFFF6F7FC),
      drawer: Drawer(
        width: 290,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.horizontal(right: Radius.circular(22)),
        ),
        child: SafeArea(
          child: Column(
            children: [
              Container(
                margin: const EdgeInsets.fromLTRB(12, 12, 12, 10),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                decoration: BoxDecoration(
                  color: Colors.black,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Center(
                  child: NexusErpLogo(maxWidth: 180, maxHeight: 72),
                ),
              ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(12, 2, 12, 12),
                  children: [
                    for (final block in sections) ...[
                      if (block.section != null) ...[
                        if (block != sections.first) const SizedBox(height: 12),
                        _MenuGroup(block.section!),
                      ],
                      for (final item in block.items)
                        _menuTile(
                          _menuIcons[item.id] ?? Icons.circle_outlined,
                          item.label,
                          selected: _selectedMenu == item.nav,
                          onTap: () => _navigateTo(_shellIndexForNav(item.nav), item.nav),
                        ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      body: _screens[_index],
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: const Color(0xFFF7F9FC),
          border: const Border(top: BorderSide(color: Color(0xFFE3E8F0))),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 12,
              offset: const Offset(0, -2),
            ),
          ],
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 68,
            child: Row(
              children: [
                Expanded(
                  child: _NavItem(
                    icon: Icons.dashboard_rounded,
                    label: 'Dashboard',
                    accent: const Color(0xFF1976D2),
                    selected: _index == 0,
                    onTap: () => _navigateTo(0, 'Dashboard'),
                  ),
                ),
                if (showInventory)
                  Expanded(
                    child: _NavItem(
                      icon: Icons.inventory_2_rounded,
                      label: 'Inventory',
                      accent: const Color(0xFF7B1FA2),
                      selected: _index == 1,
                      onTap: () => _navigateTo(1, 'Quick Actions'),
                    ),
                  ),
                Expanded(
                  child: _NavItem(
                    icon: Icons.point_of_sale_rounded,
                    label: 'Sales',
                    accent: const Color(0xFF2E7D32),
                    selected: _index == 2,
                    onTap: () => _navigateTo(2, 'Sales Hub'),
                  ),
                ),
                if (showAccounts)
                  Expanded(
                    child: _NavItem(
                      icon: Icons.account_balance_rounded,
                      label: 'Accounts',
                      accent: const Color(0xFFEF6C00),
                      selected: _index == 3,
                      onTap: () => _navigateTo(3, 'Accounts Hub'),
                    ),
                  ),
                if (showReports)
                  Expanded(
                    child: _NavItem(
                      icon: Icons.bar_chart_rounded,
                      label: 'Reports',
                      accent: const Color(0xFF5B3DF5),
                      selected: _index == 4,
                      onTap: () => _navigateTo(4, 'Reports Hub'),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _openProfile() {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => const ProfileSettingsScreen()),
    );
  }

  void _navigateTo(int index, String menuLabel) {
    final auth = context.read<AuthProvider>();
    final user = auth.user;
    const shellHubLabels = {'Quick Actions', 'Sales Hub', 'Accounts Hub', 'Reports Hub'};
    if (user != null &&
        user.mobileMenus.isNotEmpty &&
        !shellHubLabels.contains(menuLabel) &&
        !user.canNavigate(menuLabel)) {
      showAccessDeniedAlert(context);
      return;
    }

    if (menuLabel == 'Settings') {
      Navigator.of(context).maybePop();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _openProfile();
      });
      return;
    }

    if (menuLabel == 'Transaction Date Setup') {
      Navigator.of(context).maybePop();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        Navigator.of(context).push<void>(
          MaterialPageRoute<void>(builder: (_) => const TransactionDateSetupScreen()),
        );
      });
      return;
    }

    setState(() {
      _index = index;
      _selectedMenu = menuLabel;
    });
    LastNavStorage.saveMenu(menuLabel);
    Navigator.of(context).maybePop();

    if (index == 1) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _inventoryNavKey.currentState?.syncFromShell(menuLabel);
      });
    }
    if (index == 2) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _salesNavKey.currentState?.syncFromShell(menuLabel);
      });
    }
    if (index == 3) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _accountsNavKey.currentState?.syncFromShell(menuLabel);
      });
    }
    void pushReport(Widget screen) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen));
      });
    }

    switch (menuLabel) {
      case 'Summary':
        pushReport(const TransactionReportScreen(mode: TransactionReportMode.summary));
      case 'Details':
        pushReport(const TransactionReportScreen(mode: TransactionReportMode.details));
      case 'Sales Details':
        pushReport(const SalesDetailsReportScreen());
      case 'X Report':
        pushReport(const SalesXReportScreen());
      case 'Customer Wise Sales':
        pushReport(const CustomerWiseSalesReportScreen());
      case 'Business Summary':
        pushReport(const BusinessSummaryScreen());
      case 'Sales Reports':
        pushReport(const SalesReportsScreen());
      case 'Stock Ledger':
        pushReport(const StockLedgerReportScreen());
      case 'Stock Summary':
        pushReport(const StockSummaryReportScreen());
      case 'Inventory History':
        pushReport(const InventoryHistoryReportScreen());
      case 'Inventory Aging':
        pushReport(const InventoryAgingReportScreen());
      case 'Warehouse Summary':
        pushReport(const WarehouseSummaryReportScreen());
      case 'Supplier Balance':
        pushReport(const SupplierBalanceReportScreen());
    }
  }

  Widget _menuTile(IconData icon, String title, {bool selected = false, VoidCallback? onTap}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        color: selected ? const Color(0xFFF2F0FF) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
      ),
      child: ListTile(
        dense: true,
        horizontalTitleGap: 8,
        leading: Icon(icon, color: const Color(0xFF3D4477), size: 20),
        title: Text(
          title,
          style: TextStyle(
            fontSize: 13.5,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w600,
            color: const Color(0xFF262C50),
          ),
        ),
        onTap: onTap,
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({
    required this.icon,
    required this.label,
    required this.accent,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Color accent;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final muted = const Color(0xFF8A90A1);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut,
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
            decoration: BoxDecoration(
              color: selected ? accent.withValues(alpha: 0.14) : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              icon,
              color: selected ? accent : accent.withValues(alpha: 0.55),
              size: 22,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: selected ? accent : muted,
              fontSize: 11,
              fontWeight: selected ? FontWeight.w800 : FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}

class _MenuGroup extends StatelessWidget {
  const _MenuGroup(this.title);
  final String title;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 4, 10, 8),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 11,
          color: Color(0xFF8A90A1),
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}
