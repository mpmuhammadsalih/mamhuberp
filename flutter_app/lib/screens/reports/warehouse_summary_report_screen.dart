import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/reports_service.dart';
import 'inventory_report_screen.dart';

class WarehouseSummaryReportScreen extends StatelessWidget {
  const WarehouseSummaryReportScreen({super.key});

  static const accent = Color(0xFF0277BD);

  static void open(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const WarehouseSummaryReportScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.read<ReportsService>();
    return InventoryReportScreen(
      title: 'Warehouse Summary',
      accent: accent,
      searchHint: 'Search warehouse…',
      emptyMessage: 'No warehouse totals found.',
      loader: ({required q, required dateFrom, required dateTo}) => svc.getWarehouseSummary(q: q),
      itemBuilder: (context, row, color) {
        final code = invStr(row, const ['warehouse_code', 'code']);
        final name = invStr(row, const ['warehouse_name', 'name']);
        final items = invNum(row, const ['item_count', 'items']);
        final qty = invNum(row, const ['total_qty', 'qty']);
        final value = invNum(row, const ['stock_value', 'stockvalue', 'value']);
        return InventoryReportCard(
          accent: color,
          title: name.isNotEmpty ? name : (code.isNotEmpty ? code : 'Warehouse'),
          subtitle: code.isNotEmpty && name.isNotEmpty ? code : null,
          trailing: Text(
            invFmtMoney(value),
            style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 13),
          ),
          lines: [
            'Items ${invFmtNum(items, decimals: 0)} · Qty ${invFmtNum(qty, decimals: 3)}',
          ],
        );
      },
    );
  }
}
