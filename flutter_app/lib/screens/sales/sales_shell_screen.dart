import 'package:flutter/material.dart';

import '../../core/storage/last_nav_storage.dart';
import '../masters/customer_category_list_screen.dart';
import '../masters/customer_list_screen.dart';
import '../sales_order_screen.dart';
import '../sales_return_screen.dart';
import '../sales_screen.dart';
import 'sales_ai_mode_setup_screen.dart';
import 'sales_x_report_screen.dart';
import '../reports/customer_wise_sales_report_screen.dart';
import '../../core/theme/app_theme.dart';

/// Bottom-tab root for Sales: hub with quick actions for order, invoice, return, reports.
class SalesShellScreen extends StatefulWidget {
  const SalesShellScreen({super.key, this.onOpenDrawer});

  final VoidCallback? onOpenDrawer;

  @override
  State<SalesShellScreen> createState() => SalesShellScreenState();
}

class SalesShellScreenState extends State<SalesShellScreen> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  void syncFromShell(String menuLabel) {
    final nav = _navigatorKey.currentState;
    if (nav == null) return;

    nav.popUntil((route) => route.isFirst);

    if (menuLabel == 'Sales Hub' || menuLabel == 'Quick Sales') {
      return;
    }

    final page = salesPageForLabel(menuLabel);
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
          builder: (ctx) => SalesQuickActionsScreen(
            onOpenDrawer: widget.onOpenDrawer,
            onActionSelected: (label) {
              LastNavStorage.saveMenu(label);
              final next = salesPageForLabel(label);
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

Widget? salesPageForLabel(String label) {
  switch (label) {
    case 'Sales Order':
      return const SalesOrderScreen();
    case 'Sales':
      return const SalesScreen();
    case 'AI Sales Mode':
      return const SalesAiModeSetupScreen();
    case 'Sales Return':
      return const SalesReturnScreen();
    case 'X Report':
      return const SalesXReportScreen();
    case 'Customer Wise Sales':
      return const CustomerWiseSalesReportScreen();
    case 'Customers':
      return const CustomerListScreen();
    case 'Customer Category':
      return const CustomerCategoryListScreen();
    default:
      return null;
  }
}

class SalesQuickActionsScreen extends StatelessWidget {
  const SalesQuickActionsScreen({
    super.key,
    this.onOpenDrawer,
    required this.onActionSelected,
  });

  final VoidCallback? onOpenDrawer;
  final void Function(String label) onActionSelected;

  static const List<_SalesActionItem> _items = [
    _SalesActionItem('Sales Order', 'Orders & fulfilment', Icons.assignment_outlined, Color(0xFF1565C0)),
    _SalesActionItem('Sales', 'Sales invoices', Icons.receipt_long_outlined, Color(0xFF2E7D32)),
    _SalesActionItem('AI Sales Mode', 'Voice & chat shopping', Icons.record_voice_over_outlined, Color(0xFF0D9488)),
    _SalesActionItem('Sales Return', 'Returns & credits', Icons.assignment_return_outlined, Color(0xFF6A1B9A)),
    _SalesActionItem('X Report', 'POS-style day / counter totals', Icons.assessment_outlined, Color(0xFFEF6C00)),
    _SalesActionItem('Customer Wise Sales', 'Sales by customer like ERP', Icons.people_outline_rounded, Color(0xFF00695C)),
    _SalesActionItem('Customers', 'Create & manage customers', Icons.people_alt_outlined, Color(0xFF00897B)),
    _SalesActionItem('Customer Category', 'Manage customer categories', Icons.category_outlined, Color(0xFF5D4037)),
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
        title: const Text('Sales', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
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

class _SalesActionItem {
  const _SalesActionItem(this.title, this.subtitle, this.icon, this.color);

  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
}

class SalesPlaceholderScreen extends StatelessWidget {
  const SalesPlaceholderScreen({
    super.key,
    required this.title,
    required this.subtitle,
    this.icon = Icons.point_of_sale_outlined,
  });

  final String title;
  final String subtitle;
  final IconData icon;

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
              Icon(icon, size: 40, color: const Color(0xFF5B3DF5)),
              const SizedBox(height: 16),
              Text(subtitle, style: TextStyle(fontSize: 15, color: Colors.grey.shade700, height: 1.35)),
              const SizedBox(height: 14),
              Text(
                'This flow will connect to the ERP sales module when ready.',
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade500),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
