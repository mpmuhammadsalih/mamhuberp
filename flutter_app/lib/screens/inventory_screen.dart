import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/inventory_provider.dart';
import '../widgets/loading_indicator.dart';
import '../widgets/loading_overlay.dart';
import '../widgets/provider_error_body.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<InventoryProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<InventoryProvider>();
    if (state.isLoading && state.items.isEmpty) {
      return const AppLoadingIndicator();
    }
    if (state.error != null && state.items.isEmpty) {
      return ProviderErrorBody(
        message: state.error!,
        errorCause: state.errorCause,
        onRetry: () => context.read<InventoryProvider>().load(),
      );
    }
    return SafeArea(
      child: LoadingOverlay(
        loading: state.isFetching,
        child: RefreshIndicator(
          onRefresh: () => context.read<InventoryProvider>().load(),
          child: ListView.separated(
            padding: const EdgeInsets.all(12),
            itemCount: state.items.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final item = state.items[index];
              return Card(
                child: ListTile(
                  title: Text(item.itemName),
                  subtitle: Text('${item.itemCode} | ${item.unit}'),
                  trailing: Text(item.qtyOnHand.toStringAsFixed(2)),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

