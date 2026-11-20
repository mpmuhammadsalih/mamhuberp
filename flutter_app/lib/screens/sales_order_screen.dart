import 'package:flutter/material.dart';

import 'sales/sales_order_list_screen.dart';

/// Entry point for Sales → Sales Order list (+ FAB for new order).
class SalesOrderScreen extends StatelessWidget {
  const SalesOrderScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const SalesOrderListScreen();
  }
}
