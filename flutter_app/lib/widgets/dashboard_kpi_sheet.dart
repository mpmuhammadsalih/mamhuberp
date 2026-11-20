import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/theme/app_theme.dart';
import '../providers/dashboard_provider.dart';
import '../services/dashboard_service.dart';

String _fmtMoney(dynamic v) {
  final n = v is num ? v.toDouble() : double.tryParse('$v') ?? 0;
  final neg = n < 0;
  final parts = n.abs().toStringAsFixed(2).split('.');
  final digits = parts[0];
  final buf = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buf.write(',');
    buf.write(digits[i]);
  }
  return '${neg ? '-' : ''}${buf.toString()}.${parts[1]}';
}

Future<void> showDashboardKpiSummary(
  BuildContext context, {
  required String kpiId,
  required Color accent,
  void Function(String menuLabel)? onOpenMenu,
}) {
  final provider = context.read<DashboardProvider>();
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
    ),
    builder: (ctx) => _DashboardKpiSheet(
      kpiId: kpiId,
      accent: accent,
      dateFrom: provider.dateFromIso,
      dateTo: provider.dateToIso,
      periodLabel: provider.periodLabel,
      onOpenMenu: onOpenMenu,
    ),
  );
}

class _DashboardKpiSheet extends StatefulWidget {
  const _DashboardKpiSheet({
    required this.kpiId,
    required this.accent,
    required this.dateFrom,
    required this.dateTo,
    required this.periodLabel,
    this.onOpenMenu,
  });

  final String kpiId;
  final Color accent;
  final String dateFrom;
  final String dateTo;
  final String periodLabel;
  final void Function(String menuLabel)? onOpenMenu;

  @override
  State<_DashboardKpiSheet> createState() => _DashboardKpiSheetState();
}

class _DashboardKpiSheetState extends State<_DashboardKpiSheet> {
  bool _loading = true;
  String? _error;
  DashboardKpiDetail? _detail;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final detail = await context.read<DashboardService>().getKpiDetail(
            widget.kpiId,
            limit: 60,
            dateFrom: widget.dateFrom,
            dateTo: widget.dateTo,
          );
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  void _open(String menu) {
    Navigator.of(context).maybePop();
    widget.onOpenMenu?.call(menu);
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.sizeOf(context).height * 0.78;
    return SizedBox(
      height: h,
      child: Column(
        children: [
          const SizedBox(height: 8),
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey.shade300,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _detail?.title.isNotEmpty == true ? _detail!.title : _fallbackTitle(),
                        style: TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                          color: widget.accent,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        widget.periodLabel.isNotEmpty ? widget.periodLabel : 'Selected period',
                        style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  onPressed: _loading ? null : _load,
                  icon: const Icon(Icons.refresh_rounded),
                  color: widget.accent,
                ),
                IconButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  icon: const Icon(Icons.close_rounded),
                ),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(_error!, textAlign: TextAlign.center, style: TextStyle(color: Colors.grey.shade700)),
                              const SizedBox(height: 12),
                              FilledButton(onPressed: _load, child: const Text('Retry')),
                            ],
                          ),
                        ),
                      )
                    : _body(_detail!),
          ),
        ],
      ),
    );
  }

  String _fallbackTitle() {
    switch (widget.kpiId) {
      case 'purchases':
        return 'Purchase';
      case 'expenses':
        return 'Cash Payment';
      case 'inventory':
        return 'Inventory';
      case 'receivables':
        return 'Receivables';
      case 'payables':
        return 'Payables';
      case 'cash_bank':
        return 'Cash & Bank';
      default:
        return 'Sales';
    }
  }

  String get _listTitle {
    switch (widget.kpiId) {
      case 'inventory':
        return 'Stock alerts';
      case 'receivables':
        return 'Customers';
      case 'payables':
        return 'Suppliers';
      case 'cash_bank':
        return 'Accounts';
      default:
        return 'Documents';
    }
  }

  Widget _body(DashboardKpiDetail d) {
    final related = d.related;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      children: [
        if (d.description.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(d.description, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600, height: 1.3)),
          ),
        ..._summaryCards(related),
        const SizedBox(height: 14),
        Row(
          children: [
            Text(
              _listTitle,
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Colors.grey.shade800),
            ),
            const Spacer(),
            Text(
              '${d.rows.length}',
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5, color: widget.accent),
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (d.rows.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 28),
            child: Center(
              child: Text(
                _emptyListMessage(),
                style: TextStyle(color: Colors.grey.shade600),
              ),
            ),
          )
        else
          ...d.rows.map(_docTile),
        const SizedBox(height: 12),
        ..._actionButtons(),
      ],
    );
  }

  String _emptyListMessage() {
    switch (widget.kpiId) {
      case 'inventory':
        return 'No low / out-of-stock items.';
      case 'receivables':
        return 'No outstanding customers.';
      case 'payables':
        return 'No outstanding suppliers.';
      case 'cash_bank':
        return 'No cash/bank accounts found.';
      default:
        return 'No documents in this period.';
    }
  }

  List<Widget> _summaryCards(Map<String, dynamic> related) {
    switch (widget.kpiId) {
      case 'purchases':
        return [
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'GRN',
                  value: _fmtMoney(related['grn_total'] ?? related['purchases']),
                  hint: '${related['grn_count'] ?? 0} docs',
                  color: const Color(0xFF1976D2),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: 'Purchase Return',
                  value: _fmtMoney(related['purchase_return']),
                  hint: '${related['purchase_return_count'] ?? 0} docs',
                  color: const Color(0xFF6A1B9A),
                ),
              ),
            ],
          ),
        ];
      case 'expenses':
        return [
          _StatCard(
            label: 'Cash Payment Voucher',
            value: _fmtMoney(related['cpv_total'] ?? related['expenses']),
            hint: '${related['cpv_count'] ?? 0} vouchers',
            color: const Color(0xFFEF6C00),
          ),
        ];
      case 'inventory':
        return [
          _StatCard(
            label: 'Total Stock Value',
            value: _fmtMoney(related['stock_value']),
            hint: 'SKU ${related['total_items'] ?? 0} · In stock ${related['items_in_stock'] ?? related['total_items'] ?? 0}',
            color: const Color(0xFF7B1FA2),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'Low Stock',
                  value: '${related['low_stock_items'] ?? 0}',
                  hint: 'Below reorder',
                  color: const Color(0xFFEF6C00),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: 'Out of Stock',
                  value: '${related['out_of_stock_items'] ?? 0}',
                  hint: 'Zero / negative qty',
                  color: const Color(0xFFC62828),
                ),
              ),
            ],
          ),
        ];
      case 'receivables':
        return [
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'Overdue',
                  value: _fmtMoney(related['receivables_overdue']),
                  hint: 'Past due',
                  color: const Color(0xFFC62828),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: 'Not Due',
                  value: _fmtMoney(related['receivables_not_due'] ?? related['outstanding_amount']),
                  hint: 'Total ${_fmtMoney(related['outstanding_amount'])}',
                  color: const Color(0xFF2E7D32),
                ),
              ),
            ],
          ),
        ];
      case 'payables':
        return [
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'Overdue',
                  value: _fmtMoney(related['payables_overdue']),
                  hint: 'Past due',
                  color: const Color(0xFFC62828),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: 'Not Due',
                  value: _fmtMoney(related['payables_not_due'] ?? related['payables_total']),
                  hint: 'Total ${_fmtMoney(related['payables_total'])}',
                  color: const Color(0xFFEF6C00),
                ),
              ),
            ],
          ),
        ];
      case 'cash_bank':
        return [
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'Cash',
                  value: _fmtMoney(related['cash_balance']),
                  hint: 'Petty / cash',
                  color: const Color(0xFF00897B),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: 'Bank',
                  value: _fmtMoney(related['bank_balance']),
                  hint: 'Total ${_fmtMoney(related['cash_bank_total'])}',
                  color: const Color(0xFF1976D2),
                ),
              ),
            ],
          ),
        ];
      default:
        final sales = related['sales_invoice_total'] ?? related['today_sales'];
        return [
          Row(
            children: [
              Expanded(
                child: _StatCard(
                  label: 'Sales',
                  value: _fmtMoney(sales),
                  hint: 'Cash ${_fmtMoney(related['cash_sales'])} · Credit ${_fmtMoney(related['credit_sales'])}',
                  color: const Color(0xFF2E7D32),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _StatCard(
                  label: 'Sales Return',
                  value: _fmtMoney(related['sales_return']),
                  hint: '${related['return_count'] ?? 0} docs',
                  color: const Color(0xFFC62828),
                ),
              ),
            ],
          ),
        ];
    }
  }

  List<Widget> _actionButtons() {
    switch (widget.kpiId) {
      case 'purchases':
        return [
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _open('Goods Receiving'),
                  child: const Text('Open GRN'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _open('Purchase Return'),
                  child: const Text('Purchase Return'),
                ),
              ),
            ],
          ),
        ];
      case 'expenses':
        return [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: AppTheme.appBarBlue),
              onPressed: () => _open('Cash Payment Voucher'),
              child: const Text('Open Cash Payment Voucher'),
            ),
          ),
        ];
      case 'inventory':
        return [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFF7B1FA2)),
              onPressed: () => _open('Stock Lookup'),
              child: const Text('Open Stock Lookup'),
            ),
          ),
        ];
      case 'receivables':
        return [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
              onPressed: () => _open('Accounts Receivable'),
              child: const Text('Open Receivables'),
            ),
          ),
        ];
      case 'payables':
        return [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFFEF6C00)),
              onPressed: () => _open('Accounts Payable'),
              child: const Text('Open Payables'),
            ),
          ),
        ];
      case 'cash_bank':
        return [
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1976D2)),
              onPressed: () => _open('Cash Payment Voucher'),
              child: const Text('Open Cash Payment'),
            ),
          ),
        ];
      default:
        return [
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _open('Sales'),
                  child: const Text('Sales Invoices'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _open('Sales Return'),
                  child: const Text('Sales Return'),
                ),
              ),
            ],
          ),
        ];
    }
  }

  Widget _docTile(Map<String, dynamic> row) {
    final kind = '${row['doc_kind'] ?? ''}'.trim().toLowerCase();
    final isReturn = kind == 'return' || kind == 'purchase_return';
    final isGrn = kind == 'grn';
    final isCpv = kind == 'cpv';
    final isAr = kind == 'ar';
    final isAp = kind == 'ap';
    final isStock = kind == 'stock_alert';
    final isGl = kind == 'gl_account';
    final no = '${row['bill_no'] ?? row['doc_no'] ?? ''}'.trim();
    final date = '${row['bill_date'] ?? row['doc_date'] ?? ''}'.trim();
    final party = '${row['customer_name'] ?? row['party_name'] ?? ''}'.trim();
    final status = '${row['status'] ?? ''}'.trim();
    final amount = row['amount'];
    final badge = isReturn
        ? (kind == 'purchase_return' ? 'PR' : 'SR')
        : isGrn
            ? 'GRN'
            : isCpv
                ? 'CPV'
                : isAr
                    ? 'AR'
                    : isAp
                        ? 'AP'
                        : isStock
                            ? (status == 'OUT' ? 'OUT' : 'LOW')
                            : isGl
                                ? 'GL'
                                : (row['billing_type'] ?? 'INV').toString();
    final badgeColor = isReturn || isStock
        ? const Color(0xFFC62828)
        : isGrn || isGl
            ? const Color(0xFF1976D2)
            : isCpv || isAp
                ? const Color(0xFFEF6C00)
                : isAr
                    ? const Color(0xFF2E7D32)
                    : widget.accent;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F9FC),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: badgeColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              badge,
              style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w800, color: badgeColor),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  no.isEmpty ? '—' : no,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                ),
                const SizedBox(height: 2),
                Text(
                  [
                    if (party.isNotEmpty) party,
                    if (date.isNotEmpty) date,
                    if (status.isNotEmpty) status,
                  ].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                ),
              ],
            ),
          ),
          Text(
            _fmtMoney(amount),
            style: TextStyle(
              fontWeight: FontWeight.w800,
              fontSize: 13,
              color: isReturn ? const Color(0xFFC62828) : const Color(0xFF1F2544),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    required this.hint,
    required this.color,
  });

  final String label;
  final String value;
  final String hint;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
          const SizedBox(height: 4),
          Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: color)),
          const SizedBox(height: 4),
          Text(hint, style: TextStyle(fontSize: 11, color: Colors.grey.shade700)),
        ],
      ),
    );
  }
}
