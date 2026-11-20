import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/theme/app_theme.dart';
import '../models/dashboard_summary.dart';
import '../providers/auth_provider.dart';
import '../providers/dashboard_provider.dart';
import '../widgets/dashboard_kpi_sheet.dart';
import '../widgets/loading_indicator.dart';
import '../widgets/loading_overlay.dart';
import '../widgets/provider_error_body.dart';
import 'profile_settings_screen.dart';

String _fmtMoney(double v) {
  final neg = v < 0;
  final parts = v.abs().toStringAsFixed(2).split('.');
  final digits = parts[0];
  final buf = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buf.write(',');
    buf.write(digits[i]);
  }
  return '${neg ? '-' : ''}${buf.toString()}.${parts[1]}';
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, this.onOpenMenu});

  /// Navigate shell tabs / drawer menus (e.g. 'Sales Hub', 'Accounts Hub').
  final void Function(String menuLabel)? onOpenMenu;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static const _navy = Color(0xFF1F2544);
  static const _appBarBlue = AppTheme.appBarBlue;
  static const _pageBg = Color(0xFFF2F4F8);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DashboardProvider>().load();
    });
  }

  void _go(String menu) => widget.onOpenMenu?.call(menu);

  Future<void> _openPeriodPicker() async {
    final provider = context.read<DashboardProvider>();
    final choice = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        Widget option({
          required String id,
          required String label,
          IconData icon = Icons.calendar_today_outlined,
        }) {
          return ListTile(
            leading: Icon(icon, color: _appBarBlue),
            title: Text(label, style: const TextStyle(fontWeight: FontWeight.w700, color: _navy)),
            onTap: () => Navigator.of(ctx).pop(id),
          );
        }

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const Text(
                  'Select period',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: _navy),
                ),
                const SizedBox(height: 4),
                option(id: 'today', label: 'Today', icon: Icons.today_rounded),
                option(id: 'yesterday', label: 'Yesterday', icon: Icons.history_rounded),
                option(id: 'last7', label: 'Last 7 days', icon: Icons.date_range_rounded),
                option(id: 'month', label: 'This month', icon: Icons.calendar_month_rounded),
                option(id: 'custom', label: 'Custom range…', icon: Icons.edit_calendar_rounded),
              ],
            ),
          ),
        );
      },
    );
    if (!mounted || choice == null) return;

    switch (choice) {
      case 'today':
        await provider.setToday();
      case 'yesterday':
        await provider.setYesterday();
      case 'last7':
        await provider.setLast7Days();
      case 'month':
        await provider.setThisMonth();
      case 'custom':
        await _pickCustomRange(provider);
    }

    if (!mounted) return;
    final err = provider.error;
    if (err != null && provider.summary != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(err), behavior: SnackBarBehavior.floating),
      );
    }
  }

  Future<void> _pickCustomRange(DashboardProvider provider) async {
    final today = DateTime(DateTime.now().year, DateTime.now().month, DateTime.now().day);
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2015),
      lastDate: today,
      initialDateRange: DateTimeRange(start: provider.dateFrom, end: provider.dateTo),
      helpText: 'Select date range',
      saveText: 'Apply',
    );
    if (picked == null || !mounted) return;
    await provider.setCustomRange(picked.start, picked.end);
  }

  String _locationName(DashboardSummary s) {
    final fromSummary = s.branchName.trim();
    if (fromSummary.isNotEmpty) return fromSummary;
    final auth = context.read<AuthProvider>();
    final tenantId = (auth.user?.tenantId ?? '').trim();
    for (final t in auth.tenantOptions) {
      if (t.tenantId == tenantId && t.displayName.trim().isNotEmpty) {
        return t.displayName.trim();
      }
    }
    return tenantId;
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<DashboardProvider>();
    if (state.isLoading && state.summary == null) {
      return const AppLoadingIndicator();
    }
    if (state.error != null && state.summary == null) {
      return ProviderErrorBody(
        message: state.error!,
        errorCause: state.errorCause,
        onRetry: () => context.read<DashboardProvider>().load(),
      );
    }
    final s = state.summary;
    if (s == null) return const SizedBox.shrink();
    final locationName = _locationName(s);

    return ColoredBox(
      color: _pageBg,
      child: Column(
        children: [
          _DashboardAppBar(
            locationName: locationName,
            onMenu: () => Scaffold.of(context).openDrawer(),
            onSearch: _openPeriodPicker,
            onProfile: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(builder: (_) => const ProfileSettingsScreen()),
              );
            },
          ),
          Expanded(
            child: LoadingOverlay(
              loading: state.isRefreshing,
              child: RefreshIndicator(
                color: _appBarBlue,
                onRefresh: () => context.read<DashboardProvider>().load(),
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 96),
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Material(
                            color: Colors.white,
                            elevation: 0.5,
                            shadowColor: Colors.black26,
                            borderRadius: BorderRadius.circular(14),
                            child: InkWell(
                              onTap: _openPeriodPicker,
                              borderRadius: BorderRadius.circular(14),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                                child: Row(
                                  children: [
                                    const Icon(Icons.calendar_month_rounded, size: 18, color: _appBarBlue),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        state.periodLabel,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w700,
                                          fontSize: 13.5,
                                          color: _navy,
                                        ),
                                      ),
                                    ),
                                    Icon(Icons.expand_more_rounded, size: 20, color: Colors.grey.shade500),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Material(
                          color: Colors.white,
                          elevation: 0.5,
                          shadowColor: Colors.black26,
                          borderRadius: BorderRadius.circular(14),
                          child: InkWell(
                            onTap: _openPeriodPicker,
                            borderRadius: BorderRadius.circular(14),
                            child: const SizedBox(
                              width: 48,
                              height: 48,
                              child: Icon(Icons.filter_alt_outlined, color: _appBarBlue),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: _KpiChip(
                            label: 'Sales',
                            value: s.todaySales,
                            trendPct: s.salesTrendPct,
                            icon: Icons.shopping_cart_rounded,
                            tint: const Color(0xFF2E7D32),
                            onTap: () => showDashboardKpiSummary(
                              context,
                              kpiId: 'today_sales',
                              accent: const Color(0xFF2E7D32),
                              onOpenMenu: widget.onOpenMenu,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _KpiChip(
                            label: 'Purchase',
                            value: s.purchases,
                            trendPct: s.purchasesTrendPct,
                            icon: Icons.local_shipping_rounded,
                            tint: const Color(0xFF1976D2),
                            onTap: () => showDashboardKpiSummary(
                              context,
                              kpiId: 'purchases',
                              accent: const Color(0xFF1976D2),
                              onOpenMenu: widget.onOpenMenu,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _KpiChip(
                            label: 'Cash Payment',
                            value: s.expenses,
                            trendPct: s.expensesTrendPct,
                            icon: Icons.account_balance_wallet_rounded,
                            tint: const Color(0xFFEF6C00),
                            onTap: () => showDashboardKpiSummary(
                              context,
                              kpiId: 'expenses',
                              accent: const Color(0xFFEF6C00),
                              onOpenMenu: widget.onOpenMenu,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    // Equal-height cards per row.
                    IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: _ModuleCard(
                              title: 'Inventory',
                              valueLabel: 'Total Stock Value',
                              value: s.inventoryValue > 0 ? s.inventoryValue : s.stockValue,
                              accent: const Color(0xFF7B1FA2),
                              decorIcon: Icons.inventory_2_rounded,
                              titleIcon: Icons.inventory_2_outlined,
                              rows: [
                                _ModuleRow('Items (SKU)', '${s.totalItems}'),
                                _ModuleRow('In Stock', '${s.itemsInStock > 0 ? s.itemsInStock : s.totalItems}'),
                                _ModuleRow('Low Stock', '${s.lowStockItems}', danger: s.lowStockItems > 0),
                              ],
                              link: 'View Inventory',
                              onTap: () => showDashboardKpiSummary(
                                context,
                                kpiId: 'inventory',
                                accent: const Color(0xFF7B1FA2),
                                onOpenMenu: widget.onOpenMenu,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: _ModuleCard(
                              title: 'Receivables',
                              valueLabel: 'Total Outstanding',
                              value: s.outstandingAmount,
                              accent: const Color(0xFF2E7D32),
                              decorIcon: Icons.account_balance_wallet_rounded,
                              titleIcon: Icons.account_balance_wallet_outlined,
                              rows: [
                                _ModuleRow('Overdue', _fmtMoney(s.receivablesOverdue), danger: s.receivablesOverdue > 0),
                                _ModuleRow(
                                  'Not Due',
                                  _fmtMoney(s.receivablesNotDue > 0 ? s.receivablesNotDue : s.outstandingAmount),
                                ),
                              ],
                              link: 'View Receivables',
                              onTap: () => showDashboardKpiSummary(
                                context,
                                kpiId: 'receivables',
                                accent: const Color(0xFF2E7D32),
                                onOpenMenu: widget.onOpenMenu,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 10),
                    IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(
                            child: _ModuleCard(
                              title: 'Payables',
                              valueLabel: 'Total Payable',
                              value: s.payablesTotal,
                              accent: const Color(0xFFEF6C00),
                              decorIcon: Icons.receipt_long_rounded,
                              titleIcon: Icons.receipt_long_outlined,
                              rows: [
                                _ModuleRow('Overdue', _fmtMoney(s.payablesOverdue), danger: s.payablesOverdue > 0),
                                _ModuleRow(
                                  'Not Due',
                                  _fmtMoney(s.payablesNotDue > 0 ? s.payablesNotDue : s.payablesTotal),
                                ),
                              ],
                              link: 'View Payables',
                              onTap: () => showDashboardKpiSummary(
                                context,
                                kpiId: 'payables',
                                accent: const Color(0xFFEF6C00),
                                onOpenMenu: widget.onOpenMenu,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: _ModuleCard(
                              title: 'Cash & Bank',
                              valueLabel: 'Total Balance',
                              value: s.cashBankTotal,
                              accent: const Color(0xFF1976D2),
                              decorIcon: Icons.account_balance_rounded,
                              titleIcon: Icons.account_balance_outlined,
                              rows: [
                                _ModuleRow('Cash', _fmtMoney(s.cashBalance)),
                                _ModuleRow('Bank', _fmtMoney(s.bankBalance)),
                              ],
                              link: 'View Cash & Bank',
                              onTap: () => showDashboardKpiSummary(
                                context,
                                kpiId: 'cash_bank',
                                accent: const Color(0xFF1976D2),
                                onOpenMenu: widget.onOpenMenu,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    const Text(
                      'Quick Actions',
                      style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: _navy),
                    ),
                    const SizedBox(height: 12),
                    _QuickActionsRow(onOpen: _go),
                    const SizedBox(height: 16),
                    LayoutBuilder(
                      builder: (context, c) {
                        final stacked = c.maxWidth < 640;
                        final activity = _ActivityCard(items: s.recentActivity);
                        final alerts = _AlertsCard(items: s.alerts);
                        if (stacked) {
                          return Column(children: [activity, const SizedBox(height: 10), alerts]);
                        }
                        return Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(child: activity),
                            const SizedBox(width: 10),
                            Expanded(child: alerts),
                          ],
                        );
                      },
                    ),
                    const SizedBox(height: 12),
                    _TodaySnapshot(
                      visits: s.visitsToday,
                      orders: s.salesOrdersToday,
                      invoices: s.invoiceCount,
                      returns: s.returnCount,
                      newCustomers: s.newCustomersToday,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DashboardAppBar extends StatelessWidget {
  const _DashboardAppBar({
    required this.locationName,
    required this.onMenu,
    required this.onSearch,
    required this.onProfile,
  });

  final String locationName;
  final VoidCallback onMenu;
  final VoidCallback onSearch;
  final VoidCallback onProfile;

  static const _blue = AppTheme.appBarBlue;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: _blue,
      elevation: 2,
      shadowColor: Colors.black26,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 6, 4, 12),
          child: Row(
            children: [
              IconButton(
                onPressed: onMenu,
                icon: const Icon(Icons.menu_rounded, color: Colors.white),
              ),
              Expanded(
                child: Column(
                  children: [
                    const Text(
                      'ERP Summary',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: Colors.white,
                        letterSpacing: 0.2,
                      ),
                    ),
                    if (locationName.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.place_rounded, size: 13, color: Colors.white),
                          const SizedBox(width: 3),
                          Flexible(
                            child: Text(
                              locationName,
                              textAlign: TextAlign.center,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: Colors.white.withValues(alpha: 0.92),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Period',
                onPressed: onSearch,
                icon: const Icon(Icons.search_rounded, color: Colors.white),
              ),
              IconButton(
                tooltip: 'Profile',
                onPressed: onProfile,
                icon: const Icon(Icons.notifications_none_rounded, color: Colors.white),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _KpiChip extends StatelessWidget {
  const _KpiChip({
    required this.label,
    required this.value,
    required this.trendPct,
    required this.icon,
    required this.tint,
    this.onTap,
  });

  final String label;
  final double value;
  final double trendPct;
  final IconData icon;
  final Color tint;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final up = trendPct >= 0;
    return Material(
      color: Colors.white,
      elevation: 1,
      shadowColor: Colors.black12,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.fromLTRB(10, 10, 10, 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border(
              bottom: BorderSide(color: tint.withValues(alpha: 0.55), width: 3),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 20, color: tint),
              const SizedBox(height: 8),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.grey.shade600),
              ),
              const SizedBox(height: 2),
              Text(
                _fmtMoney(value),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: tint),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: tint.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '${up ? '↑' : '↓'} ${trendPct.abs().toStringAsFixed(1)}%',
                  style: TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w800,
                    color: up ? tint : const Color(0xFFC62828),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModuleRow {
  const _ModuleRow(this.label, this.value, {this.danger = false});
  final String label;
  final String value;
  final bool danger;
}

class _ModuleCard extends StatelessWidget {
  const _ModuleCard({
    required this.title,
    required this.valueLabel,
    required this.value,
    required this.rows,
    required this.link,
    required this.accent,
    required this.decorIcon,
    required this.titleIcon,
    this.onTap,
  });

  final String title;
  final String valueLabel;
  final double value;
  final List<_ModuleRow> rows;
  final String link;
  final Color accent;
  final IconData decorIcon;
  final IconData titleIcon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      elevation: 1.5,
      shadowColor: Colors.black12,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(18),
          child: Stack(
            children: [
              Positioned(
                right: -8,
                top: 36,
                child: Icon(
                  decorIcon,
                  size: 78,
                  color: accent.withValues(alpha: 0.12),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(titleIcon, size: 18, color: accent),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            title,
                            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: accent),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(valueLabel, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                    Text(
                      _fmtMoney(value),
                      style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: accent),
                    ),
                    const SizedBox(height: 8),
                    for (var i = 0; i < 3; i++)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 3),
                        child: i < rows.length
                            ? Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      rows[i].label,
                                      style: TextStyle(
                                        fontSize: 11.5,
                                        fontWeight: rows[i].danger ? FontWeight.w700 : FontWeight.w500,
                                        color: rows[i].danger
                                            ? const Color(0xFFC62828)
                                            : Colors.grey.shade700,
                                      ),
                                    ),
                                  ),
                                  Text(
                                    rows[i].value,
                                    style: TextStyle(
                                      fontSize: 11.5,
                                      fontWeight: FontWeight.w700,
                                      color: rows[i].danger
                                          ? const Color(0xFFC62828)
                                          : const Color(0xFF1F2544),
                                    ),
                                  ),
                                ],
                              )
                            : const SizedBox(height: 17),
                      ),
                    const Spacer(),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: Material(
                        color: accent.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                        child: InkWell(
                          onTap: onTap,
                          borderRadius: BorderRadius.circular(10),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    link,
                                    style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: accent),
                                  ),
                                ),
                                Icon(Icons.arrow_forward_rounded, size: 16, color: accent),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickActionsRow extends StatelessWidget {
  const _QuickActionsRow({required this.onOpen});

  final void Function(String menu) onOpen;

  @override
  Widget build(BuildContext context) {
    final actions = <(String, IconData, Color, String)>[
      ('Sales Orders', Icons.assignment_outlined, const Color(0xFF7B1FA2), 'Sales Order'),
      ('Invoices', Icons.receipt_long_outlined, const Color(0xFF2E7D32), 'Sales'),
      ('GRN', Icons.local_shipping_outlined, const Color(0xFFEF6C00), 'Goods Receiving'),
      ('Purchase Orders', Icons.description_outlined, const Color(0xFFE91E63), 'Purchase Order'),
      ('Inventory', Icons.inventory_2_outlined, const Color(0xFF00897B), 'Stock Lookup'),
      ('Customers', Icons.people_outline_rounded, const Color(0xFF5C6BC0), 'Customers'),
      ('Suppliers', Icons.storefront_outlined, const Color(0xFF00838F), 'Suppliers'),
      ('Payments', Icons.payments_outlined, const Color(0xFFC62828), 'Cash Payment Voucher'),
      ('Reports', Icons.bar_chart_rounded, const Color(0xFF4527A0), 'Reports Hub'),
      ('More', Icons.apps_rounded, const Color(0xFF546E7A), 'Quick Actions'),
    ];
    return SizedBox(
      height: 88,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: actions.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (_, i) {
          final a = actions[i];
          return InkWell(
            onTap: () => onOpen(a.$4),
            borderRadius: BorderRadius.circular(14),
            child: SizedBox(
              width: 72,
              child: Column(
                children: [
                  Container(
                    width: 54,
                    height: 54,
                    decoration: BoxDecoration(
                      color: a.$3.withValues(alpha: 0.14),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Icon(a.$2, color: a.$3, size: 26),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    a.$1,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF374151),
                      height: 1.15,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _ActivityCard extends StatelessWidget {
  const _ActivityCard({required this.items});

  final List<DashboardActivityItem> items;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      title: 'Recent Activity',
      child: items.isEmpty
          ? Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text('No activity yet today.', style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
            )
          : Builder(
              builder: (_) {
                final rows = items.take(5).toList();
                return Column(
                  children: [
                    for (var i = 0; i < rows.length; i++) ...[
                      if (i > 0) Divider(height: 1, color: Colors.grey.shade200),
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(rows[i].title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                                  Text(
                                    [
                                      if (rows[i].subtitle.isNotEmpty) rows[i].subtitle,
                                      if (rows[i].time.isNotEmpty) rows[i].time,
                                    ].join(' · '),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                                  ),
                                ],
                              ),
                            ),
                            Text(
                              '${rows[i].signed < 0 ? '-' : ''}${_fmtMoney(rows[i].amount.abs())}',
                              style: TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 12.5,
                                color: rows[i].signed < 0 ? const Color(0xFFE65100) : const Color(0xFF2E7D32),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                );
              },
            ),
    );
  }
}

class _AlertsCard extends StatelessWidget {
  const _AlertsCard({required this.items});

  final List<DashboardAlertItem> items;

  @override
  Widget build(BuildContext context) {
    final rows = items.take(5).toList();
    return _Panel(
      title: 'Alerts',
      child: rows.isEmpty
          ? Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text('No alerts right now.', style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
            )
          : Column(
              children: [
                for (var i = 0; i < rows.length; i++) ...[
                  if (i > 0) Divider(height: 1, color: Colors.grey.shade200),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          rows[i].severity == 'critical'
                              ? Icons.error_outline_rounded
                              : rows[i].severity == 'warning'
                                  ? Icons.warning_amber_rounded
                                  : Icons.info_outline_rounded,
                          size: 18,
                          color: rows[i].severity == 'critical'
                              ? const Color(0xFFC62828)
                              : rows[i].severity == 'warning'
                                  ? const Color(0xFFEF6C00)
                                  : const Color(0xFF1565C0),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(rows[i].title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5)),
                              if (rows[i].subtitle.isNotEmpty)
                                Text(rows[i].subtitle, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
    );
  }
}

class _TodaySnapshot extends StatelessWidget {
  const _TodaySnapshot({
    required this.visits,
    required this.orders,
    required this.invoices,
    required this.returns,
    required this.newCustomers,
  });

  final int visits;
  final int orders;
  final int invoices;
  final int returns;
  final int newCustomers;

  @override
  Widget build(BuildContext context) {
    final cells = [
      ('Visits', '$visits'),
      ('Orders Created', '$orders'),
      ('Invoices', '$invoices'),
      ('Returns', '$returns'),
      ('New Customers', '$newCustomers'),
    ];
    return _Panel(
      title: "Today's Snapshot",
      child: Row(
        children: [
          for (var i = 0; i < cells.length; i++) ...[
            if (i > 0) Container(width: 1, height: 36, color: Colors.grey.shade200),
            Expanded(
              child: Column(
                children: [
                  Text(
                    cells[i].$1,
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 10, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    cells[i].$2,
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: Color(0xFF1F2544)),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF1F2544))),
          const SizedBox(height: 6),
          child,
        ],
      ),
    );
  }
}
