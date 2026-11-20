import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/reports_service.dart';
import 'inventory_report_screen.dart';

class InventoryAgingReportScreen extends StatelessWidget {
  const InventoryAgingReportScreen({super.key});

  static const accent = Color(0xFFEF6C00);

  static void open(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const InventoryAgingReportScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.read<ReportsService>();
    return InventoryReportScreen(
      title: 'Inventory Aging',
      accent: accent,
      dateMode: InventoryReportDateMode.asOn,
      searchHint: 'Search item…',
      emptyMessage: 'No aging rows for this date.',
      loader: ({required q, required dateFrom, required dateTo}) => svc.getInventoryAging(
        q: q,
        asOnDate: dateTo,
      ),
      itemBuilder: (context, row, color) {
        final code = invStr(row, const ['itemcode', 'item_code']);
        final name = invStr(row, const ['itemname', 'item_name']);
        final qty = invNum(row, const ['currentstock', 'qty', 'quantity', 'stock']);
        final age = invNum(row, const ['age_days', 'agedays', 'age']);
        final bucket = invStr(row, const ['aging_bucket', 'bucket', 'age_bucket']);
        final status = invStr(row, const ['status', 'movement_status']);
        final value = invNum(row, const ['stockvalue', 'stock_value', 'value']);
        return InventoryReportCard(
          accent: color,
          title: name.isNotEmpty ? name : (code.isNotEmpty ? code : 'Item'),
          subtitle: code.isNotEmpty && name.isNotEmpty ? code : null,
          trailing: Text(
            age != null ? '${invFmtNum(age, decimals: 0)}d' : '—',
            style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 14),
          ),
          lines: [
            'Qty ${invFmtNum(qty, decimals: 3)} · Value ${invFmtMoney(value)}',
            [
              if (bucket.isNotEmpty) bucket,
              if (status.isNotEmpty) status,
            ].where((s) => s.isNotEmpty).join(' · '),
          ],
        );
      },
    );
  }
}
