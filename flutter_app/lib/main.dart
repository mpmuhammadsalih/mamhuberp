import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/network/api_client.dart';
import 'core/network/transaction_overlay_controller.dart';
import 'core/storage/local_cache.dart';
import 'core/storage/token_storage.dart';
import 'core/theme/app_theme.dart';
import 'providers/business_summary_provider.dart';
import 'providers/auth_provider.dart';
import 'providers/dashboard_provider.dart';
import 'providers/inventory_provider.dart';
import 'providers/sales_reports_provider.dart';
import 'providers/purchase_provider.dart';
import 'repositories/business_summary_repository.dart';
import 'repositories/auth_repository.dart';
import 'repositories/dashboard_repository.dart';
import 'repositories/inventory_repository.dart';
import 'repositories/purchase_repository.dart';
import 'repositories/sales_reports_repository.dart';
import 'repositories/stock_count_repository.dart';
import 'screens/home_shell_screen.dart';
import 'screens/login_screen.dart';
import 'services/auth_service.dart';
import 'services/dashboard_service.dart';
import 'services/barcode_print_list_service.dart';
import 'services/inventory_service.dart';
import 'services/purchase_order_service.dart';
import 'services/stock_return_service.dart';
import 'services/accounts_reports_service.dart';
import 'services/ar_ap_service.dart';
import 'services/cash_payment_voucher_service.dart';
import 'services/journal_entry_service.dart';
import 'services/party_ledger_service.dart';
import 'services/pos_settlement_service.dart';
import 'services/category_brand_master_service.dart';
import 'services/customer_master_service.dart';
import 'services/item_master_service.dart';
import 'services/supplier_master_service.dart';
import 'services/unit_master_service.dart';
import 'services/purchase_service.dart';
import 'services/reports_service.dart';
import 'services/sales_ai_service.dart';
import 'services/sales_service.dart';
import 'services/stock_count_service.dart';
import 'services/stock_transfer_service.dart';
import 'services/stock_adjustment_service.dart';
import 'services/transaction_date_setup_service.dart';
import 'widgets/loading_overlay.dart';

Future<void> main() async {
  // ensureInitialized + runApp must share the same zone (hot restart safe).
  await runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();

    final tokenStorage = TokenStorage();
    final cache = LocalCache();
    final transactionOverlay = TransactionOverlayController();
    final apiClient = ApiClient(tokenStorage, transactionOverlay);
    await apiClient.initializeEndpoint();

    runApp(
      MultiProvider(
        providers: [
          Provider.value(value: tokenStorage),
          Provider.value(value: cache),
          Provider.value(value: apiClient),
          ChangeNotifierProvider.value(value: transactionOverlay),
          Provider(create: (_) => AuthService(apiClient)),
          Provider(create: (_) => DashboardService(apiClient)),
          Provider(create: (_) => InventoryService(apiClient)),
          Provider(create: (_) => BarcodePrintListService(apiClient)),
          Provider(create: (_) => PurchaseService(apiClient)),
          Provider(create: (_) => PurchaseOrderService(apiClient)),
          Provider(create: (_) => StockReturnService(apiClient)),
          Provider(create: (_) => CashPaymentVoucherService(apiClient)),
          Provider(create: (_) => PosSettlementService(apiClient)),
          Provider(create: (_) => ArApService(apiClient)),
          Provider(create: (_) => PartyLedgerService(apiClient)),
          Provider(create: (_) => JournalEntryService(apiClient)),
          Provider(create: (_) => AccountsReportsService(apiClient)),
          Provider(create: (_) => CustomerMasterService(apiClient)),
          Provider(create: (_) => SupplierMasterService(apiClient)),
          Provider(create: (_) => CategoryBrandMasterService(apiClient)),
          Provider(create: (_) => UnitMasterService(apiClient)),
          Provider(create: (_) => TransactionDateSetupService(apiClient)),
          Provider(create: (_) => ItemMasterService(apiClient)),
          Provider(create: (_) => SalesService(apiClient)),
          Provider(create: (_) => SalesAiService(apiClient)),
          Provider(create: (_) => StockCountService(apiClient)),
          Provider(create: (_) => StockTransferService(apiClient)),
          Provider(create: (_) => StockAdjustmentService(apiClient)),
          Provider(create: (_) => ReportsService(apiClient)),
          Provider(
            create: (context) => AuthRepository(
              context.read<AuthService>(),
              context.read<TokenStorage>(),
            ),
          ),
          Provider(
            create: (context) => DashboardRepository(
              context.read<DashboardService>(),
              context.read<LocalCache>(),
            ),
          ),
          Provider(
            create: (context) => InventoryRepository(
              context.read<InventoryService>(),
              context.read<LocalCache>(),
            ),
          ),
          Provider(
            create: (context) => PurchaseRepository(
              context.read<PurchaseService>(),
              context.read<LocalCache>(),
            ),
          ),
          Provider(
            create: (context) => SalesReportsRepository(
              context.read<SalesService>(),
              context.read<LocalCache>(),
            ),
          ),
          Provider(
            create: (context) => BusinessSummaryRepository(
              context.read<ReportsService>(),
              context.read<LocalCache>(),
            ),
          ),
          Provider(
            create: (context) => StockCountRepository(context.read<StockCountService>()),
          ),
          ChangeNotifierProvider(create: (context) => AuthProvider(context.read<AuthRepository>())),
          ChangeNotifierProvider(
            create: (context) => DashboardProvider(context.read<DashboardRepository>()),
          ),
          ChangeNotifierProvider(
            create: (context) => InventoryProvider(context.read<InventoryRepository>()),
          ),
          ChangeNotifierProvider(
            create: (context) => SalesReportsProvider(context.read<SalesReportsRepository>()),
          ),
          ChangeNotifierProvider(
            create: (context) => BusinessSummaryProvider(context.read<BusinessSummaryRepository>()),
          ),
          ChangeNotifierProvider(
            create: (context) => PurchaseProvider(context.read<PurchaseRepository>()),
          ),
        ],
        child: const NexaApp(),
      ),
    );
  }, (error, stack) {
    debugPrint('Uncaught error: $error\n$stack');
  });
}

class NexaApp extends StatefulWidget {
  const NexaApp({super.key});

  @override
  State<NexaApp> createState() => _NexaAppState();
}

class _NexaAppState extends State<NexaApp> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final api = context.read<ApiClient>();
      final auth = context.read<AuthProvider>();
      api.onSessionExpired = () {
        auth.clearLocalSession();
      };
      auth.restoreSession();
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final transactionOverlay = context.watch<TransactionOverlayController>();
    final isLoggedIn = auth.isAuthenticated;
    final Widget home;
    if (auth.isRestoringSession) {
      home = const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    } else if (isLoggedIn) {
      home = const HomeShellScreen();
    } else {
      home = const LoginScreen();
    }
    // Key forces a fresh navigator when auth flips so Logout leaves Profile/Settings
    // and shows Login (changing only `home` keeps pushed routes on the stack).
    return MaterialApp(
      key: ValueKey<String>(isLoggedIn ? 'nexa-authed' : 'nexa-login'),
      debugShowCheckedModeBanner: false,
      title: 'Nexus Erp',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.light,
      builder: (context, child) {
        return LoadingOverlay(
          loading: isLoggedIn && transactionOverlay.isBusy,
          message: 'Saving…',
          child: child ?? const SizedBox.shrink(),
        );
      },
      home: home,
    );
  }
}

