import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/reports_service.dart';
import 'inventory_report_screen.dart';

class StockSummaryReportScreen extends StatelessWidget {
  const StockSummaryReportScreen({super.key});

  static const accent = Color(0xFF2E7D32);

  static void open(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const StockSummaryReportScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.read<ReportsService>();
    return InventoryReportScreen(
      title: 'Stock Summary',
      accent: accent,
      searchHint: 'Search item…',
      emptyMessage: 'No on-hand stock rows.',
      loader: ({required q, required dateFrom, required dateTo}) => svc.getStockSummary(q: q),
      itemBuilder: (context, row, color) {
        final code = invStr(row, const ['itemcode', 'item_code']);
        final name = invStr(row, const ['itemname', 'item_name']);
        final qty = invNum(row, const ['qty', 'quantity', 'total_qty']);
        final unitCost = invNum(row, const ['unitcost', 'unit_cost', 'costprice']);
        final value = invNum(row, const ['stockvalue', 'stock_value', 'value']);
        final wh = invStr(row, const ['warehouse_name', 'warehouse_code', 'warehouse']);
        return InventoryReportCard(
          accent: color,
          title: name.isNotEmpty ? name : (code.isNotEmpty ? code : 'Item'),
          subtitle: code.isNotEmpty && name.isNotEmpty ? code : null,
          trailing: Text(
            invFmtNum(qty, decimals: 3),
            style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 14),
          ),
          lines: [
            'Cost ${invFmtMoney(unitCost)} · Value ${invFmtMoney(value)}',
            if (wh.isNotEmpty) wh,
          ],
        );
      },
    );
  }
}
