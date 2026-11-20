import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/reports_service.dart';
import 'inventory_report_screen.dart';

class InventoryHistoryReportScreen extends StatelessWidget {
  const InventoryHistoryReportScreen({super.key});

  static const accent = Color(0xFF6A1B9A);

  static void open(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const InventoryHistoryReportScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.read<ReportsService>();
    return InventoryReportScreen(
      title: 'Inventory History',
      accent: accent,
      dateMode: InventoryReportDateMode.range,
      searchHint: 'Search item / doc…',
      emptyMessage: 'No inventory history in this period.',
      loader: ({required q, required dateFrom, required dateTo}) => svc.getInventoryHistory(
        q: q,
        dateFrom: dateFrom,
        dateTo: dateTo,
      ),
      itemBuilder: (context, row, color) {
        final code = invStr(row, const ['itemcode', 'item_code']);
        final name = invStr(row, const ['itemname', 'item_name']);
        final qty = invNum(row, const ['net_qty', 'qty', 'quantity']);
        final date = invStr(row, const ['stock_date', 'date']);
        final tt = invStr(row, const ['transtype', 'trans_type', 'type']);
        final doc = invStr(row, const ['source_doc', 'sourcedoc']);
        final no = invStr(row, const ['source_no', 'sourceno']);
        final wh = invStr(row, const ['warehouse_code', 'warehouse', 'warehouse_name']);
        final docLine = [doc, no].where((s) => s.isNotEmpty).join(' · ');
        return InventoryReportCard(
          accent: color,
          title: name.isNotEmpty ? name : (code.isNotEmpty ? code : 'Item'),
          subtitle: [
            if (code.isNotEmpty && name.isNotEmpty) code,
            if (date.isNotEmpty) date,
            if (tt.isNotEmpty) tt,
          ].where((s) => s.isNotEmpty).join(' · '),
          trailing: Text(
            invFmtNum(qty),
            style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 14),
          ),
          lines: [
            if (docLine.isNotEmpty) docLine,
            if (wh.isNotEmpty) 'WH: $wh',
          ],
        );
      },
    );
  }
}
