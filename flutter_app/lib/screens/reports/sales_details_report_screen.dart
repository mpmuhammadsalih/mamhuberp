import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_message.dart';
import '../../services/reports_service.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/provider_error_body.dart';
import '../accounts/accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

/// Mobile Sales Details — same invoice line layout as ERP Sales Details Report.
class SalesDetailsReportScreen extends StatefulWidget {
  const SalesDetailsReportScreen({
    super.key,
    this.initialDateFrom,
    this.initialDateTo,
    this.initialTxnKind = 'all',
  });

  final DateTime? initialDateFrom;
  final DateTime? initialDateTo;
  final String initialTxnKind;

  static Future<void> open(
    BuildContext context, {
    DateTime? dateFrom,
    DateTime? dateTo,
    String txnKind = 'all',
  }) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => SalesDetailsReportScreen(
          initialDateFrom: dateFrom,
          initialDateTo: dateTo,
          initialTxnKind: txnKind,
        ),
      ),
    );
  }

  @override
  State<SalesDetailsReportScreen> createState() => _SalesDetailsReportScreenState();
}

class _SalesDetailsReportScreenState extends State<SalesDetailsReportScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _accent = Color(0xFF00897B);
  static const _navy = Color(0xFF262C50);

  late DateTime _from;
  late DateTime _to;
  final _billNo = TextEditingController();
  final _orderNo = TextEditingController();
  String _billType = '';
  String _txnKind = 'all';
  String _customerCode = '';
  String _customerLabel = '';
  String _itemCode = '';
  String _itemLabel = '';

  bool _loading = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  InventoryReportPayload? _payload;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = widget.initialDateFrom ?? now.subtract(const Duration(days: 29));
    _to = widget.initialDateTo ?? DateTime(now.year, now.month, now.day);
    final tk = widget.initialTxnKind.trim().toLowerCase();
    _txnKind = (tk == 'sale' || tk == 'salesreturn') ? tk : 'all';
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _billNo.dispose();
    _orderNo.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<ReportsService>();
      final data = await svc.getSalesDetails(
        dateFrom: isoDate(_from),
        dateTo: isoDate(_to),
        billNo: _billNo.text.trim(),
        orderNo: _orderNo.text.trim(),
        customerCode: _customerCode,
        billType: _billType,
        txnKind: _txnKind,
        itemCode: _itemCode,
      );
      if (!mounted) return;
      setState(() {
        _payload = data;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = apiErrorMessage(e, authenticatedContext: true);
        _errorCause = e;
      });
    }
  }

  Map<String, dynamic> get _summary => _payload?.summary ?? const {};

  Future<void> _openPdf() async {
    final svc = context.read<ReportsService>();
    await openPdfBytes(
      context,
      loadBytes: () => svc.downloadSalesDetailsPdf(
        dateFrom: isoDate(_from),
        dateTo: isoDate(_to),
        billNo: _billNo.text.trim(),
        orderNo: _orderNo.text.trim(),
        customerCode: _customerCode,
        billType: _billType,
        txnKind: _txnKind,
        itemCode: _itemCode,
      ),
      fileName: 'Sales_Details_${isoDate(_to)}.pdf',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _sharePdf() async {
    final svc = context.read<ReportsService>();
    await sharePdfBytes(
      context,
      loadBytes: () => svc.downloadSalesDetailsPdf(
        dateFrom: isoDate(_from),
        dateTo: isoDate(_to),
        billNo: _billNo.text.trim(),
        orderNo: _orderNo.text.trim(),
        customerCode: _customerCode,
        billType: _billType,
        txnKind: _txnKind,
        itemCode: _itemCode,
      ),
      fileName: 'Sales_Details_${isoDate(_to)}.pdf',
      subject: 'Sales Details Report',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _pickCustomer() async {
    final picked = await _showLookupSheet(
      title: 'Select customer',
      hint: 'Search customer code/name…',
      loader: (q) => context.read<ReportsService>().searchSalesDetailCustomers(q: q),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _customerCode = '${picked['code'] ?? ''}'.trim();
      _customerLabel = '${picked['label'] ?? picked['name'] ?? _customerCode}'.trim();
    });
  }

  Future<void> _pickItem() async {
    final picked = await _showLookupSheet(
      title: 'Select item',
      hint: 'Search item code/name…',
      loader: (q) => context.read<ReportsService>().searchSalesDetailItems(q: q),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _itemCode = '${picked['code'] ?? ''}'.trim();
      _itemLabel = '${picked['label'] ?? picked['name'] ?? _itemCode}'.trim();
    });
  }

  Future<Map<String, dynamic>?> _showLookupSheet({
    required String title,
    required String hint,
    required Future<List<Map<String, dynamic>>> Function(String q) loader,
  }) async {
    return showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        final search = TextEditingController();
        var rows = <Map<String, dynamic>>[];
        var busy = true;
        String? err;
        final started = <bool>[false];

        Future<void> run(StateSetter setModal) async {
          setModal(() {
            busy = true;
            err = null;
          });
          try {
            final list = await loader(search.text.trim());
            setModal(() {
              rows = list;
              busy = false;
            });
          } catch (e) {
            setModal(() {
              busy = false;
              err = apiErrorMessage(e, authenticatedContext: true);
            });
          }
        }

        return StatefulBuilder(
          builder: (context, setModal) {
            if (!started[0]) {
              started[0] = true;
              WidgetsBinding.instance.addPostFrameCallback((_) => run(setModal));
            }
            final bottom = MediaQuery.of(context).viewInsets.bottom;
            return Padding(
              padding: EdgeInsets.only(bottom: bottom),
              child: SizedBox(
                height: MediaQuery.of(context).size.height * 0.72,
                child: Column(
                  children: [
                    const SizedBox(height: 8),
                    Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(99),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              title,
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 16,
                                color: _navy,
                              ),
                            ),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(ctx),
                            child: const Text('Close'),
                          ),
                        ],
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: TextField(
                        controller: search,
                        textInputAction: TextInputAction.search,
                        onSubmitted: (_) => run(setModal),
                        decoration: InputDecoration(
                          hintText: hint,
                          prefixIcon: const Icon(Icons.search_rounded, size: 20),
                          isDense: true,
                          filled: true,
                          fillColor: const Color(0xFFF0F2FA),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                            borderSide: BorderSide.none,
                          ),
                          suffixIcon: IconButton(
                            onPressed: () => run(setModal),
                            icon: const Icon(Icons.arrow_forward_rounded),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: busy
                          ? const AppLoadingIndicator()
                          : err != null
                              ? Center(child: Text(err!, textAlign: TextAlign.center))
                              : rows.isEmpty
                                  ? Center(
                                      child: Text(
                                        'No matches.',
                                        style: TextStyle(color: Colors.grey.shade600),
                                      ),
                                    )
                                  : ListView.separated(
                                      itemCount: rows.length,
                                      separatorBuilder: (_, __) => const Divider(height: 1),
                                      itemBuilder: (_, i) {
                                        final r = rows[i];
                                        final label = '${r['label'] ?? r['name'] ?? r['code'] ?? ''}';
                                        return ListTile(
                                          title: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
                                          onTap: () => Navigator.pop(ctx, r),
                                        );
                                      },
                                    ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  double _num(dynamic v) {
    if (v is num) return v.toDouble();
    return double.tryParse('${v ?? ''}'.replaceAll(',', '')) ?? 0;
  }

  int _int(dynamic v) {
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('${v ?? ''}'.split('.').first) ?? 0;
  }

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return '${v.toInt()}';
    return v.toStringAsFixed(3);
  }

  @override
  Widget build(BuildContext context) {
    final period = '${_payload?.meta['period_label'] ?? ''}'.trim();
    final summary = _summary;

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        title: const Text('Sales Details'),
        elevation: 0.5,
        actions: [
          IconButton(
            tooltip: 'Open PDF',
            onPressed: _pdfBusy || _loading ? null : _openPdf,
            icon: const Icon(Icons.picture_as_pdf_outlined),
          ),
          IconButton(
            tooltip: 'Share PDF',
            onPressed: _pdfBusy || _loading ? null : _sharePdf,
            icon: const Icon(Icons.share_outlined),
          ),
        ],
      ),
      body: LoadingOverlay(
        loading: _loading && _payload != null,
        child: Column(
          children: [
            Material(
              color: Colors.white,
              elevation: 1,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: _dateChip('From', _from, (d) => setState(() => _from = d)),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _dateChip('To', _to, (d) => setState(() => _to = d)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _billNo,
                            keyboardType: TextInputType.number,
                            decoration: _fieldDeco('Bill No'),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TextField(
                            controller: _orderNo,
                            decoration: _fieldDeco('Order No'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: DropdownButtonFormField<String>(
                            value: _billType,
                            decoration: _fieldDeco('Bill type'),
                            items: const [
                              DropdownMenuItem(value: '', child: Text('All types')),
                              DropdownMenuItem(value: 'C', child: Text('Cash (C)')),
                              DropdownMenuItem(value: 'R', child: Text('Credit (R)')),
                              DropdownMenuItem(value: 'D', child: Text('Card (D)')),
                            ],
                            onChanged: (v) => setState(() => _billType = v ?? ''),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: DropdownButtonFormField<String>(
                            value: _txnKind,
                            decoration: _fieldDeco('Sale / Return'),
                            items: const [
                              DropdownMenuItem(value: 'all', child: Text('All')),
                              DropdownMenuItem(value: 'sale', child: Text('Sale')),
                              DropdownMenuItem(value: 'salesreturn', child: Text('Sales Return')),
                            ],
                            onChanged: (v) => setState(() => _txnKind = v ?? 'all'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    _pickerField(
                      label: _customerLabel.isEmpty ? 'Customer (popup)' : _customerLabel,
                      onTap: _pickCustomer,
                      onClear: _customerCode.isEmpty
                          ? null
                          : () => setState(() {
                                _customerCode = '';
                                _customerLabel = '';
                              }),
                    ),
                    const SizedBox(height: 8),
                    _pickerField(
                      label: _itemLabel.isEmpty ? 'Item (popup)' : _itemLabel,
                      onTap: _pickItem,
                      onClear: _itemCode.isEmpty
                          ? null
                          : () => setState(() {
                                _itemCode = '';
                                _itemLabel = '';
                              }),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _loading ? null : _load,
                        style: FilledButton.styleFrom(backgroundColor: _accent),
                        child: const Text('Apply Filters'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (period.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    period,
                    style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
                  ),
                ),
              ),
            Expanded(
              child: _loading && _payload == null
                  ? const AppLoadingIndicator()
                  : _error != null && _payload == null
                      ? ProviderErrorBody(
                          message: _error!,
                          errorCause: _errorCause,
                          onRetry: _load,
                        )
                      : Column(
                          children: [
                            Expanded(
                              child: RefreshIndicator(
                                color: _accent,
                                onRefresh: _load,
                                child: ListView(
                                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                                  children: [
                                    if ((_payload?.rows ?? const []).isEmpty)
                                      Padding(
                                        padding: const EdgeInsets.symmetric(vertical: 40),
                                        child: Center(
                                          child: Text(
                                            'No sales details found.',
                                            style: TextStyle(color: Colors.grey.shade600),
                                          ),
                                        ),
                                      )
                                    else
                                      for (final row in _payload!.rows) _lineCard(row),
                                  ],
                                ),
                              ),
                            ),
                            _stickyBar(
                              lines: _int(summary['row_count']),
                              bills: _int(summary['bill_count']),
                              qty: _num(summary['total_qty']),
                              amount: _num(summary['total_amount']),
                            ),
                          ],
                        ),
            ),
          ],
        ),
      ),
    );
  }

  InputDecoration _fieldDeco(String hint) {
    return InputDecoration(
      hintText: hint,
      labelText: hint,
      isDense: true,
      filled: true,
      fillColor: const Color(0xFFF0F2FA),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide.none,
      ),
    );
  }

  Widget _dateChip(String label, DateTime value, ValueChanged<DateTime> onPicked) {
    return InkWell(
      onTap: () => pickReportDate(context, initial: value, onPicked: onPicked),
      borderRadius: BorderRadius.circular(10),
      child: Ink(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFFF0F2FA),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
            const SizedBox(height: 2),
            Text(isoDate(value), style: const TextStyle(fontWeight: FontWeight.w700, color: _navy)),
          ],
        ),
      ),
    );
  }

  Widget _pickerField({
    required String label,
    required VoidCallback onTap,
    VoidCallback? onClear,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Ink(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFFF0F2FA),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: label.contains('(popup)') ? Colors.grey.shade600 : _navy,
                ),
              ),
            ),
            if (onClear != null)
              IconButton(
                visualDensity: VisualDensity.compact,
                onPressed: onClear,
                icon: const Icon(Icons.close_rounded, size: 18),
              )
            else
              Icon(Icons.arrow_drop_down_rounded, color: Colors.grey.shade600),
          ],
        ),
      ),
    );
  }

  Widget _stickyBar({
    required int lines,
    required int bills,
    required double qty,
    required double amount,
  }) {
    Widget m(String label, String value) => Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.grey.shade600)),
              const SizedBox(height: 2),
              Text(value, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: _navy)),
            ],
          ),
        );
    return Material(
      elevation: 8,
      color: Colors.white,
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: Color(0xFFE4E7F0))),
          ),
          child: Row(
            children: [
              m('Lines', '$lines'),
              m('Bills', '$bills'),
              m('Qty', _fmtQty(qty)),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('Line total', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.grey.shade600)),
                  const SizedBox(height: 2),
                  Text(
                    fmtMoney(amount),
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: Color(0xFF2E7D32)),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _lineCard(Map<String, dynamic> row) {
    final bill = '${row['billno'] ?? ''}'.trim();
    final date = '${row['billdate'] ?? ''}'.trim();
    final time = '${row['billtime'] ?? ''}'.trim();
    final type = '${row['billing_type'] ?? row['billtype'] ?? ''}'.trim();
    final customer = '${row['customername'] ?? ''}'.trim();
    final custCode = '${row['customercode'] ?? ''}'.trim();
    final orderNo = '${row['orderno'] ?? ''}'.trim();
    final itemCode = '${row['itemcode'] ?? ''}'.trim();
    final itemName = '${row['itemname'] ?? ''}'.trim();
    final uom = '${row['uom'] ?? ''}'.trim();
    final store = '${row['storecode'] ?? ''}'.trim();
    final status = '${row['billstatus'] ?? ''}'.trim();
    final sl = '${row['slno'] ?? ''}'.trim();
    final qty = _num(row['quantity']);
    final rate = _num(row['rate']);
    final disc = _num(row['linediscount']);
    final amount = _num(row['lineamount']);
    final netBill = _num(row['netbillamount']);

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  [
                    if (itemCode.isNotEmpty) itemCode,
                    if (itemName.isNotEmpty) itemName,
                  ].join(' · '),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800, color: _navy, fontSize: 13.5),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                fmtMoney(amount),
                style: const TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF2E7D32)),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            [
              if (bill.isNotEmpty) 'Bill #$bill',
              if (sl.isNotEmpty) 'Sl $sl',
              if (date.isNotEmpty) date,
              if (time.isNotEmpty) time,
              if (type.isNotEmpty) type,
              if (status.isNotEmpty) status,
            ].join(' · '),
            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700, height: 1.3),
          ),
          if (customer.isNotEmpty || custCode.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(
              customer.isNotEmpty
                  ? (custCode.isNotEmpty ? '$custCode · $customer' : customer)
                  : custCode,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
            ),
          ],
          const SizedBox(height: 4),
          Text(
            [
              'Qty ${_fmtQty(qty)}${uom.isNotEmpty ? ' $uom' : ''}',
              '@ ${rate == rate.roundToDouble() ? rate.toInt() : rate.toStringAsFixed(2)}',
              if (disc != 0) 'Disc ${fmtMoney(disc)}',
              if (store.isNotEmpty) 'Store $store',
              if (orderNo.isNotEmpty) 'Order $orderNo',
              if (netBill != 0) 'Bill ${fmtMoney(netBill)}',
            ].join(' · '),
            style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: Colors.grey.shade800),
          ),
        ],
      ),
    );
  }
}
