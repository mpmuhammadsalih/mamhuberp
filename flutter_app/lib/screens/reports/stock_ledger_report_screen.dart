import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../services/reports_service.dart';
import 'inventory_report_screen.dart';

class StockLedgerReportScreen extends StatelessWidget {
  const StockLedgerReportScreen({super.key});

  static const accent = Color(0xFF1565C0);

  static void open(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const StockLedgerReportScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.read<ReportsService>();
    return InventoryReportScreen(
      title: 'Stock Ledger',
      accent: accent,
      dateMode: InventoryReportDateMode.range,
      searchHint: 'Search item / doc…',
      emptyMessage: 'No stock movements in this period.',
      loader: ({required q, required dateFrom, required dateTo}) => svc.getStockLedger(
        q: q,
        dateFrom: dateFrom,
        dateTo: dateTo,
      ),
      itemBuilder: (context, row, color) {
        final code = invStr(row, const ['itemcode', 'item_code']);
        final name = invStr(row, const ['itemname', 'item_name']);
        final qty = invNum(row, const ['net_qty', 'qty', 'quantity']);
        final qtyIn = invNum(row, const ['qty_in']);
        final qtyOut = invNum(row, const ['qty_out']);
        final date = invStr(row, const ['stock_date', 'date']);
        final tt = invStr(row, const ['transtype', 'trans_type', 'type']);
        final doc = invStr(row, const ['source_doc', 'sourcedoc']);
        final no = invStr(row, const ['source_no', 'sourceno']);
        final wh = invStr(row, const ['warehouse_code', 'warehouse', 'warehouse_name']);
        final docLine = [doc, no].where((s) => s.isNotEmpty).join(' · ');
        String qtyLine;
        if (qtyIn != null || qtyOut != null) {
          qtyLine = 'In ${invFmtNum(qtyIn ?? 0)} · Out ${invFmtNum(qtyOut ?? 0)}';
        } else {
          qtyLine = 'Qty ${invFmtNum(qty)}';
        }
        return InventoryReportCard(
          accent: color,
          title: name.isNotEmpty ? name : (code.isNotEmpty ? code : 'Item'),
          subtitle: [
            if (code.isNotEmpty && name.isNotEmpty) code,
            if (date.isNotEmpty) date,
            if (tt.isNotEmpty) tt,
          ].where((s) => s.isNotEmpty).join(' · '),
          trailing: Text(
            invFmtNum(qty ?? ((qtyIn ?? 0) - (qtyOut ?? 0))),
            style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 14),
          ),
          lines: [
            qtyLine,
            if (docLine.isNotEmpty) docLine,
            if (wh.isNotEmpty) 'WH: $wh',
          ],
        );
      },
    );
  }
}
