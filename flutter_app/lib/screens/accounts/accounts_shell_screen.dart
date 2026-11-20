import 'package:flutter/material.dart';

import '../../core/storage/last_nav_storage.dart';
import 'ar_ap_list_screen.dart';
import 'balance_sheet_screen.dart';
import 'cash_payment_voucher_list_screen.dart';
import 'journal_entry_list_screen.dart';
import 'party_ledger_screen.dart';
import 'pos_settlement_list_screen.dart';
import 'profit_loss_screen.dart';
import 'trial_balance_screen.dart';
import '../../core/theme/app_theme.dart';

/// Bottom-tab root for Accounts: hub with quick actions.
class AccountsShellScreen extends StatefulWidget {
  const AccountsShellScreen({super.key, this.onOpenDrawer});

  final VoidCallback? onOpenDrawer;

  @override
  State<AccountsShellScreen> createState() => AccountsShellScreenState();
}

class AccountsShellScreenState extends State<AccountsShellScreen> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  void syncFromShell(String menuLabel) {
    final nav = _navigatorKey.currentState;
    if (nav == null) return;

    nav.popUntil((route) => route.isFirst);

    if (menuLabel == 'Accounts Hub' || menuLabel == 'Quick Accounts') {
      return;
    }

    final page = accountsPageForLabel(menuLabel);
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
          builder: (ctx) => AccountsQuickActionsScreen(
            onOpenDrawer: widget.onOpenDrawer,
            onActionSelected: (label) {
              LastNavStorage.saveMenu(label);
              final next = accountsPageForLabel(label);
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

Widget? accountsPageForLabel(String label) {
  switch (label) {
    case 'Customer Ledger':
      return const CustomerLedgerScreen();
    case 'Cash Payment Voucher':
      return const CashPaymentVoucherListScreen();
    case 'POS Settlement':
      return const PosSettlementListScreen();
    case 'Trial Balance':
      return const TrialBalanceScreen();
    case 'Profit & Loss':
      return const ProfitLossScreen();
    case 'Balance Sheet':
      return const BalanceSheetScreen();
    case 'Supplier Ledger':
      return const SupplierLedgerScreen();
    case 'Journal Entry':
      return const JournalEntryListScreen();
    case 'Accounts Receivable':
      return const AccountsReceivableListScreen();
    case 'Accounts Payable':
      return const AccountsPayableListScreen();
    default:
      return null;
  }
}

class AccountsQuickActionsScreen extends StatelessWidget {
  const AccountsQuickActionsScreen({
    super.key,
    this.onOpenDrawer,
    required this.onActionSelected,
  });

  final VoidCallback? onOpenDrawer;
  final void Function(String label) onActionSelected;

  static const List<_AccountsActionItem> _items = [
    _AccountsActionItem(
      'Cash Payment Voucher',
      'Petty cash expenses',
      Icons.payments_outlined,
      Color(0xFF00897B),
    ),
    _AccountsActionItem(
      'POS Settlement',
      'End-of-day POS posting',
      Icons.point_of_sale_outlined,
      Color(0xFF5E35B1),
    ),
    _AccountsActionItem('Trial Balance', 'Debits & credits', Icons.account_balance_wallet_outlined, Color(0xFF00897B)),
    _AccountsActionItem('Profit & Loss', 'Income statement', Icons.trending_up_rounded, Color(0xFF6A1B9A)),
    _AccountsActionItem('Balance Sheet', 'Assets & equity', Icons.account_balance_outlined, Color(0xFF1565C0)),
    _AccountsActionItem('Customer Ledger', 'Sub-ledger statement', Icons.people_outline_rounded, Color(0xFF1565C0)),
    _AccountsActionItem('Supplier Ledger', 'Sub-ledger statement', Icons.storefront_outlined, Color(0xFF2E7D32)),
    _AccountsActionItem('Journal Entry', 'GL journals', Icons.menu_book_outlined, Color(0xFF6A1B9A)),
    _AccountsActionItem('Accounts Receivable', 'Customer receipts', Icons.call_received_rounded, Color(0xFF0277BD)),
    _AccountsActionItem('Accounts Payable', 'Supplier payments', Icons.call_made_rounded, Color(0xFFEF6C00)),
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
        title: const Text('Accounts', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
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

class _AccountsActionItem {
  const _AccountsActionItem(this.title, this.subtitle, this.icon, this.color);

  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
}

class AccountsPlaceholderScreen extends StatelessWidget {
  const AccountsPlaceholderScreen({
    super.key,
    required this.title,
    required this.subtitle,
    this.icon = Icons.account_balance_outlined,
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
                'This flow will connect to the ERP accounts module when ready.',
                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade500),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
