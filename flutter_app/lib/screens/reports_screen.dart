import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/network/access_denied_alert.dart';
import '../core/theme/app_theme.dart';
import '../providers/auth_provider.dart';
import 'reports/business_summary_screen.dart';
import 'reports/inventory_aging_report_screen.dart';
import 'reports/inventory_history_report_screen.dart';
import 'reports/sales_reports_screen.dart';
import 'reports/stock_ledger_report_screen.dart';
import 'reports/stock_summary_report_screen.dart';
import 'reports/supplier_balance_report_screen.dart';
import 'reports/sales_details_report_screen.dart';
import 'reports/transaction_report_screen.dart';
import 'reports/warehouse_summary_report_screen.dart';
import 'reports/customer_wise_sales_report_screen.dart';
import 'sales/sales_x_report_screen.dart';

class ReportsScreen extends StatelessWidget {
  const ReportsScreen({super.key});

  static const _accent = Color(0xFF5B3DF5);

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final items = _visibleItems(auth);

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          onPressed: () => Scaffold.of(context).openDrawer(),
          icon: const Icon(Icons.menu_rounded, size: 22),
        ),
        title: const Text('Reports', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
              child: Text(
                'Business insights & inventory summaries',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
              ),
            ),
            Expanded(
              child: GridView.builder(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 88),
                itemCount: items.length,
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 1.08,
                ),
                itemBuilder: (_, index) {
                  final item = items[index];
                  return Material(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    child: InkWell(
                      onTap: item.enabled
                          ? () => _openReport(context, item)
                          : () => showAccessDeniedAlert(context),
                      borderRadius: BorderRadius.circular(14),
                      child: Ink(
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFFE8EBF3)),
                          boxShadow: const [
                            BoxShadow(color: Color(0x08000000), blurRadius: 6, offset: Offset(0, 2)),
                          ],
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
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
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
            ),
          ],
      ),
    );
  }

  bool _canAny(AuthProvider auth, List<String> paths) {
    final user = auth.user;
    if (user == null) return false;
    if (user.allowAllPermissions) return true;
    if (user.mobileMenus.isEmpty) return true; // legacy
    for (final p in paths) {
      if (user.hasMenuPath(p)) return true;
    }
    return false;
  }

  List<_ReportItem> _visibleItems(AuthProvider auth) {
    final canBusiness = _canAny(auth, const [
      'business_summary.dashboard',
      'mobile.business_summary',
    ]);
    final canSalesReports = _canAny(auth, const [
      'mobile.sales_reports',
      'sales_summary.sales_summary',
      'reports.sales_details',
    ]);
    final canXReport = _canAny(auth, const [
      'pos_billing.pos_counter_operations_page',
      'pos_billing.pos_sales_list_page',
      'pos_billing.pos_sales_list_summary_api',
      'pos_billing.pos_counter_operations_preclose_report',
      'reports.sales_details',
      'mobile.sales_reports',
      'mobile.reports',
      'sales_summary.sales_summary',
      'mobile.transaction_summary',
    ]);
    final canCustomerWise = _canAny(auth, const [
      'reports.customer_wise_sales_report',
      'reports.sales_details',
      'mobile.sales_reports',
      'mobile.reports',
      'sales_summary.sales_summary',
      'mobile.transaction_summary',
    ]);
    final canStockLedger = _canAny(auth, const [
      'mobile.stock_ledger',
      'reports.stock_report',
      'reports.stock_report_datewise',
      'mobile.reports',
    ]);
    final canStockSummary = _canAny(auth, const [
      'mobile.stock_summary',
      'reports.stock_report',
      'purchase.inventory_valuation',
      'mobile.reports',
    ]);
    final canInvHistory = _canAny(auth, const [
      'mobile.inventory_history',
      'purchase.item_journal_list',
      'reports.stock_report',
      'mobile.reports',
    ]);
    final canInvAging = _canAny(auth, const [
      'mobile.inventory_aging',
      'reports.stock_aging_report',
      'mobile.reports',
    ]);
    final canWhSummary = _canAny(auth, const [
      'mobile.warehouse_summary',
      'reports.warehouse_summary_report',
      'mobile.reports',
    ]);
    final canSupplierBal = _canAny(auth, const [
      'mobile.supplier_balance',
      'reports.supplier_balance_report',
      'accounts.accounts_payable',
      'mobile.reports',
    ]);
    final canTxReports = _canAny(auth, const [
      'mobile.transaction_summary',
      'mobile.transaction_details',
      'mobile.reports',
      'business_summary.dashboard',
      'reports.sales_details',
      'reports.last_transactions_report',
      'sales_summary.sales_summary',
    ]);

    return [
      _ReportItem(
        'Summary',
        'All transactions by type',
        Icons.summarize_outlined,
        const Color(0xFF1565C0),
        route: _ReportRoute.txSummary,
        enabled: canTxReports,
      ),
      _ReportItem(
        'Details',
        'All transactions — item-wise lines & PDF',
        Icons.list_alt_rounded,
        const Color(0xFF00897B),
        route: _ReportRoute.txDetails,
        enabled: canTxReports,
      ),
      _ReportItem(
        'Sales Details',
        'Invoice lines like ERP Sales Details',
        Icons.receipt_long_outlined,
        const Color(0xFF00695C),
        route: _ReportRoute.salesDetails,
        enabled: canTxReports,
      ),
      _ReportItem(
        'X Report',
        'POS-style day / counter totals',
        Icons.assessment_outlined,
        const Color(0xFFEF6C00),
        route: _ReportRoute.xReport,
        enabled: canXReport,
      ),
      _ReportItem(
        'Customer Wise Sales',
        'Sales by customer like ERP',
        Icons.people_outline_rounded,
        const Color(0xFF00695C),
        route: _ReportRoute.customerWiseSales,
        enabled: canCustomerWise,
      ),
      _ReportItem(
        'Business Summary',
        'Daily KPIs, sales & profit charts',
        Icons.insights_rounded,
        _accent,
        route: _ReportRoute.businessSummary,
        enabled: canBusiness,
      ),
      _ReportItem(
        'Sales Reports',
        'Sales trends, top customers & items',
        Icons.bar_chart_rounded,
        const Color(0xFFEF6C00),
        route: _ReportRoute.salesReports,
        enabled: canSalesReports,
      ),
      _ReportItem(
        'Stock Ledger',
        'Item-wise stock movements',
        Icons.receipt_long_rounded,
        const Color(0xFF1565C0),
        route: _ReportRoute.stockLedger,
        enabled: canStockLedger,
      ),
      _ReportItem(
        'Stock Summary',
        'On-hand by warehouse',
        Icons.pie_chart_outline_rounded,
        const Color(0xFF2E7D32),
        route: _ReportRoute.stockSummary,
        enabled: canStockSummary,
      ),
      _ReportItem(
        'Inventory History',
        'Transaction history',
        Icons.history_rounded,
        const Color(0xFF6A1B9A),
        route: _ReportRoute.inventoryHistory,
        enabled: canInvHistory,
      ),
      _ReportItem(
        'Inventory Aging',
        'Slow & aged stock',
        Icons.timelapse_rounded,
        const Color(0xFFEF6C00),
        route: _ReportRoute.inventoryAging,
        enabled: canInvAging,
      ),
      _ReportItem(
        'Warehouse Summary',
        'Warehouse totals',
        Icons.warehouse_outlined,
        const Color(0xFF0277BD),
        route: _ReportRoute.warehouseSummary,
        enabled: canWhSummary,
      ),
      _ReportItem(
        'Supplier Balance',
        'Outstanding payables',
        Icons.people_alt_outlined,
        const Color(0xFF00838F),
        route: _ReportRoute.supplierBalance,
        enabled: canSupplierBal,
      ),
    ];
  }

  void _openReport(BuildContext context, _ReportItem item) {
    switch (item.route) {
      case _ReportRoute.txSummary:
        TransactionReportScreen.openSummary(context);
      case _ReportRoute.txDetails:
        TransactionReportScreen.openDetails(context);
      case _ReportRoute.salesDetails:
        SalesDetailsReportScreen.open(context);
      case _ReportRoute.xReport:
        SalesXReportScreen.open(context);
      case _ReportRoute.customerWiseSales:
        CustomerWiseSalesReportScreen.open(context);
      case _ReportRoute.businessSummary:
        Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => const BusinessSummaryScreen()),
        );
      case _ReportRoute.salesReports:
        Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => const SalesReportsScreen()),
        );
      case _ReportRoute.stockLedger:
        StockLedgerReportScreen.open(context);
      case _ReportRoute.stockSummary:
        StockSummaryReportScreen.open(context);
      case _ReportRoute.inventoryHistory:
        InventoryHistoryReportScreen.open(context);
      case _ReportRoute.inventoryAging:
        InventoryAgingReportScreen.open(context);
      case _ReportRoute.warehouseSummary:
        WarehouseSummaryReportScreen.open(context);
      case _ReportRoute.supplierBalance:
        SupplierBalanceReportScreen.open(context);
      case _ReportRoute.none:
        break;
    }
  }
}

enum _ReportRoute {
  none,
  txSummary,
  txDetails,
  salesDetails,
  xReport,
  customerWiseSales,
  businessSummary,
  salesReports,
  stockLedger,
  stockSummary,
  inventoryHistory,
  inventoryAging,
  warehouseSummary,
  supplierBalance,
}

class _ReportItem {
  const _ReportItem(
    this.title,
    this.subtitle,
    this.icon,
    this.color, {
    this.route = _ReportRoute.none,
    this.enabled = false,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final _ReportRoute route;
  final bool enabled;
}
