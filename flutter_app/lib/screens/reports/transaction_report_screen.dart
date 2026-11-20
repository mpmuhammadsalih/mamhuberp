import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_message.dart';
import '../../services/reports_service.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/provider_error_body.dart';
import '../accounts/accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

enum TransactionReportMode { summary, details }

class TransactionReportScreen extends StatefulWidget {
  const TransactionReportScreen({
    super.key,
    required this.mode,
    this.initialDateFrom,
    this.initialDateTo,
    this.initialTypes = const {},
  });

  final TransactionReportMode mode;
  final DateTime? initialDateFrom;
  final DateTime? initialDateTo;
  final Set<String> initialTypes;

  static Future<void> openSummary(BuildContext context) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => const TransactionReportScreen(mode: TransactionReportMode.summary),
      ),
    );
  }

  static Future<void> openDetails(
    BuildContext context, {
    DateTime? dateFrom,
    DateTime? dateTo,
    Set<String> types = const {},
  }) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => TransactionReportScreen(
          mode: TransactionReportMode.details,
          initialDateFrom: dateFrom,
          initialDateTo: dateTo,
          initialTypes: types,
        ),
      ),
    );
  }

  @override
  State<TransactionReportScreen> createState() => _TransactionReportScreenState();
}

class _TransactionReportScreenState extends State<TransactionReportScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _accent = Color(0xFF1565C0);
  static const _navy = Color(0xFF262C50);

  late DateTime _from;
  late DateTime _to;
  final _search = TextEditingController();
  final Set<String> _selectedTypes = {};
  List<Map<String, dynamic>> _typeOptions = const [];

  bool _loading = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  InventoryReportPayload? _payload;

  bool get _isSummary => widget.mode == TransactionReportMode.summary;
  String get _title {
    if (_isSummary) return 'Summary';
    if (_selectedTypes.length == 1) {
      final code = _selectedTypes.first;
      for (final o in _typeOptions) {
        if ('${o['code']}' == code) {
          final label = '${o['label'] ?? ''}'.trim();
          if (label.isNotEmpty) return label;
        }
      }
      return 'Details';
    }
    return 'Details';
  }

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = widget.initialDateFrom ?? now.subtract(const Duration(days: 29));
    _to = widget.initialDateTo ?? DateTime(now.year, now.month, now.day);
    _selectedTypes.addAll(widget.initialTypes.where((e) => e.trim().isNotEmpty));
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  String get _typesParam {
    if (_selectedTypes.isEmpty) return '';
    return _selectedTypes.join(',');
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<ReportsService>();
      final payload = _isSummary
          ? await svc.getTransactionSummary(
              dateFrom: isoDate(_from),
              dateTo: isoDate(_to),
              transactionTypes: _typesParam,
            )
          : await svc.getTransactionDetails(
              dateFrom: isoDate(_from),
              dateTo: isoDate(_to),
              transactionTypes: _typesParam,
              q: _search.text.trim(),
              limit: 400,
            );
      if (!mounted) return;
      final opts = <Map<String, dynamic>>[];
      final rawOpts = payload.meta['type_options'];
      if (rawOpts is List) {
        for (final o in rawOpts) {
          if (o is Map) opts.add(Map<String, dynamic>.from(o));
        }
      }
      setState(() {
        _payload = payload;
        if (opts.isNotEmpty) _typeOptions = opts;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(e, authenticatedContext: true);
        _errorCause = e;
        _payload = null;
        _loading = false;
      });
    }
  }

  Future<void> _openPdf() async {
    final svc = context.read<ReportsService>();
    await openPdfBytes(
      context,
      loadBytes: () => _isSummary
          ? svc.downloadTransactionSummaryPdf(
              dateFrom: isoDate(_from),
              dateTo: isoDate(_to),
              transactionTypes: _typesParam,
            )
          : svc.downloadTransactionDetailsPdf(
              dateFrom: isoDate(_from),
              dateTo: isoDate(_to),
              transactionTypes: _typesParam,
              q: _search.text.trim(),
            ),
      fileName: _isSummary
          ? 'Transactions_Summary_${isoDate(_to)}.pdf'
          : 'Transactions_Details_${isoDate(_to)}.pdf',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _sharePdf() async {
    final svc = context.read<ReportsService>();
    await sharePdfBytes(
      context,
      loadBytes: () => _isSummary
          ? svc.downloadTransactionSummaryPdf(
              dateFrom: isoDate(_from),
              dateTo: isoDate(_to),
              transactionTypes: _typesParam,
            )
          : svc.downloadTransactionDetailsPdf(
              dateFrom: isoDate(_from),
              dateTo: isoDate(_to),
              transactionTypes: _typesParam,
              q: _search.text.trim(),
            ),
      fileName: _isSummary
          ? 'Transactions_Summary_${isoDate(_to)}.pdf'
          : 'Transactions_Details_${isoDate(_to)}.pdf',
      subject: _isSummary ? 'Transactions Summary' : 'Transactions Details',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _pickTypes() async {
    final options = _typeOptions.isNotEmpty
        ? _typeOptions
        : const [
            {'code': 'sales_invoice', 'label': 'Sales Invoice'},
            {'code': 'sales_return', 'label': 'Sales Return'},
            {'code': 'sales_order', 'label': 'Sales Order'},
            {'code': 'purchase_order', 'label': 'Purchase Order'},
            {'code': 'grn', 'label': 'GRN / Goods Received'},
            {'code': 'purchase_return', 'label': 'Purchase Return'},
            {'code': 'stock_adjustment', 'label': 'Stock Adjustment'},
            {'code': 'stock_transfer', 'label': 'Stock Transfer'},
            {'code': 'cash_payment', 'label': 'Cash Payment Voucher'},
            {'code': 'journal', 'label': 'Journal Entry'},
          ];
    final temp = Set<String>.from(_selectedTypes);
    final applied = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModal) {
            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade300,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Transaction types',
                      style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: _navy),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Leave empty for all types',
                      style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                    ),
                    const SizedBox(height: 8),
                    ConstrainedBox(
                      constraints: BoxConstraints(
                        maxHeight: MediaQuery.of(ctx).size.height * 0.5,
                      ),
                      child: ListView(
                        shrinkWrap: true,
                        children: [
                          for (final o in options)
                            CheckboxListTile(
                              dense: true,
                              value: temp.contains('${o['code'] ?? ''}'),
                              title: Text('${o['label'] ?? o['code'] ?? ''}'),
                              controlAffinity: ListTileControlAffinity.leading,
                              activeColor: _accent,
                              onChanged: (v) {
                                final code = '${o['code'] ?? ''}'.trim();
                                if (code.isEmpty) return;
                                setModal(() {
                                  if (v == true) {
                                    temp.add(code);
                                  } else {
                                    temp.remove(code);
                                  }
                                });
                              },
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        TextButton(
                          onPressed: () => setModal(temp.clear),
                          child: const Text('Clear'),
                        ),
                        const Spacer(),
                        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
                        const SizedBox(width: 8),
                        FilledButton(
                          onPressed: () => Navigator.pop(ctx, true),
                          style: FilledButton.styleFrom(backgroundColor: _accent),
                          child: const Text('Apply'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
    if (applied == true && mounted) {
      setState(() {
        _selectedTypes
          ..clear()
          ..addAll(temp);
      });
      await _load();
    }
  }

  double _num(dynamic v) {
    if (v is num) return v.toDouble();
    return double.tryParse('$v') ?? 0;
  }

  int _int(dynamic v) {
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse('$v') ?? 0;
  }

  @override
  Widget build(BuildContext context) {
    final payload = _payload;
    final summary = payload?.summary ?? const <String, dynamic>{};
    final period = '${payload?.meta['period_label'] ?? ''}'.trim();

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(_title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Share PDF',
            onPressed: _pdfBusy || _loading ? null : _sharePdf,
            icon: const Icon(Icons.share_outlined, size: 20),
          ),
          IconButton(
            tooltip: 'PDF',
            onPressed: _pdfBusy || _loading ? null : _openPdf,
            icon: _pdfBusy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.picture_as_pdf_outlined, size: 22),
          ),
        ],
      ),
      body: LoadingOverlay(
        loading: _pdfBusy,
        child: Column(
          children: [
            Material(
              color: Colors.white,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Wrap(
                      spacing: 8,
                      runSpacing: 6,
                      children: [
                        ReportFilterChip(
                          label: 'From ${isoDate(_from)}',
                          onTap: () => pickReportDate(
                            context,
                            initial: _from,
                            onPicked: (d) => setState(() => _from = d),
                          ),
                        ),
                        ReportFilterChip(
                          label: 'To ${isoDate(_to)}',
                          onTap: () => pickReportDate(
                            context,
                            initial: _to,
                            onPicked: (d) => setState(() => _to = d),
                          ),
                        ),
                        ReportFilterChip(
                          label: _selectedTypes.isEmpty
                              ? 'All types'
                              : '${_selectedTypes.length} type${_selectedTypes.length == 1 ? '' : 's'}',
                          onTap: _pickTypes,
                        ),
                        FilledButton.tonal(
                          onPressed: _loading ? null : _load,
                          child: const Text('Apply'),
                        ),
                      ],
                    ),
                    if (!_isSummary) ...[
                      const SizedBox(height: 8),
                      TextField(
                        controller: _search,
                        textInputAction: TextInputAction.search,
                        onSubmitted: (_) => _load(),
                        decoration: InputDecoration(
                          hintText: 'Search item, doc no, party…',
                          prefixIcon: const Icon(Icons.search_rounded, size: 20),
                          isDense: true,
                          filled: true,
                          fillColor: const Color(0xFFF0F2FA),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),
                    ],
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
              child: _loading && payload == null
                  ? const AppLoadingIndicator()
                  : _error != null && payload == null
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
                                    if (_isSummary) ...[
                                      Row(
                                        children: [
                                          Expanded(
                                            child: _statCard(
                                              'Cash sales',
                                              fmtMoney(_num(payload?.meta['cash_sales'])),
                                              const Color(0xFF00897B),
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Expanded(
                                            child: _statCard(
                                              'Credit sales',
                                              fmtMoney(_num(payload?.meta['credit_sales'])),
                                              const Color(0xFF6A1B9A),
                                            ),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 14),
                                      const Text(
                                        'By transaction',
                                        style: TextStyle(
                                          fontWeight: FontWeight.w800,
                                          fontSize: 15,
                                          color: _navy,
                                        ),
                                      ),
                                      const SizedBox(height: 8),
                                      if ((payload?.rows ?? const []).isEmpty)
                                        Padding(
                                          padding: const EdgeInsets.symmetric(vertical: 40),
                                          child: Center(
                                            child: Text(
                                              'No transactions in this period.',
                                              style: TextStyle(color: Colors.grey.shade600),
                                            ),
                                          ),
                                        )
                                      else
                                        for (final row in payload!.rows) _summaryRow(row),
                                    ] else ...[
                                      if ((payload?.rows ?? const []).isEmpty)
                                        Padding(
                                          padding: const EdgeInsets.symmetric(vertical: 40),
                                          child: Center(
                                            child: Text(
                                              'No item lines match your filters.',
                                              style: TextStyle(color: Colors.grey.shade600),
                                            ),
                                          ),
                                        )
                                      else
                                        for (final row in payload!.rows) _detailRow(row),
                                    ],
                                  ],
                                ),
                              ),
                            ),
                            _stickyTotalBar(
                              countLabel: _isSummary ? 'Total docs' : 'Item lines',
                              countValue: _isSummary
                                  ? '${_int(summary['total_count'])}'
                                  : '${_int(summary['row_count'])}',
                              qtyLabel: _isSummary ? null : 'Total qty',
                              qtyValue: _isSummary ? null : _num(summary['total_qty']),
                              docsLabel: _isSummary ? null : 'Docs',
                              docsValue: _isSummary ? null : _int(summary['doc_count']),
                            ),
                          ],
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stickyTotalBar({
    required String countLabel,
    required String countValue,
    String? qtyLabel,
    double? qtyValue,
    String? docsLabel,
    int? docsValue,
  }) {
    Widget metric(String label, String value, {TextAlign align = TextAlign.left}) {
      return Column(
        crossAxisAlignment: align == TextAlign.right
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.grey.shade600,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            textAlign: align,
            style: const TextStyle(
              fontWeight: FontWeight.w800,
              fontSize: 16,
              color: _navy,
            ),
          ),
        ],
      );
    }

    return Material(
      elevation: 8,
      color: Colors.white,
      child: SafeArea(
        top: false,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          decoration: const BoxDecoration(
            color: Colors.white,
            border: Border(top: BorderSide(color: Color(0xFFE4E7F0))),
          ),
          child: Row(
            children: [
              Expanded(child: metric(countLabel, countValue)),
              if (docsLabel != null && docsValue != null) ...[
                Expanded(child: metric(docsLabel, '$docsValue')),
              ],
              if (qtyLabel != null && qtyValue != null) ...[
                Expanded(
                  child: metric(
                    qtyLabel,
                    qtyValue == qtyValue.roundToDouble()
                        ? '${qtyValue.toInt()}'
                        : qtyValue.toStringAsFixed(3),
                    align: TextAlign.right,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _statCard(String label, String value, Color tint) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 12, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(value, style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: tint)),
        ],
      ),
    );
  }

  void _openTypeDetails(Map<String, dynamic> row) {
    final type = '${row['transaction_type'] ?? ''}'.trim();
    if (type.isEmpty) return;
    TransactionReportScreen.openDetails(
      context,
      dateFrom: _from,
      dateTo: _to,
      types: {type},
    );
  }

  Widget _summaryRow(Map<String, dynamic> row) {
    final name = '${row['transaction'] ?? row['transaction_type'] ?? '—'}';
    final count = _int(row['count']);
    final amount = _num(row['amount']);
    final pct = _num(row['percentage']);
    final type = '${row['transaction_type'] ?? ''}'.trim();
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: type.isEmpty ? null : () => _openTypeDetails(row),
          child: Ink(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 10, 12),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(name, style: const TextStyle(fontWeight: FontWeight.w700, color: _navy)),
                        const SizedBox(height: 2),
                        Text(
                          '$count doc${count == 1 ? '' : 's'} · ${pct.toStringAsFixed(1)}% · Tap for item details',
                          style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    fmtMoney(amount),
                    style: const TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF2E7D32)),
                  ),
                  if (type.isNotEmpty) ...[
                    const SizedBox(width: 4),
                    Icon(Icons.chevron_right_rounded, color: Colors.grey.shade500),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _detailRow(Map<String, dynamic> row) {
    final type = '${row['transaction'] ?? row['transaction_type'] ?? ''}';
    final docNo = '${row['doc_no'] ?? ''}'.trim();
    final party = '${row['party_name'] ?? ''}'.trim();
    final date = '${row['doc_date'] ?? ''}'.trim();
    final status = '${row['status'] ?? ''}'.trim();
    final billing = '${row['billing_type'] ?? ''}'.trim();
    final itemCode = '${row['item_code'] ?? ''}'.trim();
    final itemName = '${row['item_name'] ?? ''}'.trim();
    final uom = '${row['uom'] ?? ''}'.trim();
    final qty = _num(row['qty']);
    final rate = _num(row['rate']);
    final amount = _num(row['amount']);
    final qtyText = qty == qty.roundToDouble()
        ? '${qty.toInt()}'
        : qty.toStringAsFixed(3);
    final rateText = rate == 0
        ? ''
        : (rate == rate.roundToDouble()
            ? rate.toInt().toString()
            : rate.toStringAsFixed(2));
    final itemTitle = [
      if (itemCode.isNotEmpty) itemCode,
      if (itemName.isNotEmpty) itemName,
    ].join(' · ');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  itemTitle.isEmpty
                      ? (docNo.isEmpty ? type : '$type · #$docNo')
                      : itemTitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800, color: _navy, fontSize: 13.5),
                ),
                const SizedBox(height: 3),
                Text(
                  [
                    if (type.isNotEmpty) type,
                    if (docNo.isNotEmpty) '#$docNo',
                    if (date.isNotEmpty) date,
                    if (party.isNotEmpty) party,
                    if (billing.isNotEmpty) billing,
                    if (status.isNotEmpty) status,
                  ].join(' · '),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700, height: 1.3),
                ),
                const SizedBox(height: 4),
                Text(
                  [
                    'Qty $qtyText${uom.isNotEmpty ? ' $uom' : ''}',
                    if (rateText.isNotEmpty) '@ $rateText',
                  ].join(' '),
                  style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: Colors.grey.shade800),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(
            fmtMoney(amount),
            style: const TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF2E7D32)),
          ),
        ],
      ),
    );
  }
}
