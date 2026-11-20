import 'package:flutter/material.dart';

import 'purchase_order_list_screen.dart';

/// Entry point for Inventory → Purchase Order list (+ FAB for new order).
class PurchaseOrderScreen extends StatelessWidget {
  const PurchaseOrderScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const PurchaseOrderListScreen();
  }
}
