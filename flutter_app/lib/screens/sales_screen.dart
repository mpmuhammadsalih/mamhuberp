import 'package:flutter/material.dart';

import 'sales/sales_invoice_list_screen.dart';

/// Entry point for Sales → Sales Invoice list (+ FAB for new invoice).
class SalesScreen extends StatelessWidget {
  const SalesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const SalesInvoiceListScreen();
  }
}
