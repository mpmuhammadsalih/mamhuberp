import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/reports_service.dart';
import 'inventory_report_screen.dart';

class SupplierBalanceReportScreen extends StatelessWidget {
  const SupplierBalanceReportScreen({super.key});

  static const accent = Color(0xFF00838F);

  static void open(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const SupplierBalanceReportScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.read<ReportsService>();
    return InventoryReportScreen(
      title: 'Supplier Balance',
      accent: accent,
      searchHint: 'Search supplier…',
      emptyMessage: 'No supplier balances found.',
      loader: ({required q, required dateFrom, required dateTo}) => svc.getSupplierBalance(q: q),
      itemBuilder: (context, row, color) {
        final code = invStr(row, const ['suppliercode', 'supplier_code', 'code']);
        final name = invStr(row, const ['suppliername', 'supplier_name', 'name']);
        final bal = invNum(row, const ['payable_balance', 'balance', 'outstanding']);
        return InventoryReportCard(
          accent: color,
          title: name.isNotEmpty ? name : (code.isNotEmpty ? code : 'Supplier'),
          subtitle: code.isNotEmpty && name.isNotEmpty ? code : null,
          trailing: Text(
            invFmtMoney(bal),
            style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 14),
          ),
          lines: const ['Payable balance'],
        );
      },
    );
  }
}
