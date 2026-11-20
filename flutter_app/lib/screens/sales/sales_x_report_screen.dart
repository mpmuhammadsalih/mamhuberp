import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/reports_service.dart';
import '../../widgets/api_error_banner.dart';
import '../accounts/accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

/// Sales X Report — same totals layout as ERP POS X Report / shift TIME CHECK.
class SalesXReportScreen extends StatefulWidget {
  const SalesXReportScreen({super.key});

  static Future<void> open(BuildContext context) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => const SalesXReportScreen()),
    );
  }

  @override
  State<SalesXReportScreen> createState() => _SalesXReportScreenState();
}

class _SalesXReportScreenState extends State<SalesXReportScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _accent = Color(0xFF1565C0);
  static const _navy = Color(0xFF262C50);

  bool _booting = true;
  bool _loading = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;

  late DateTime _from;
  late DateTime _to;
  int _counterCode = 0;
  List<({int code, String name})> _counters = const [(code: 0, name: 'All counters')];

  Map<String, dynamic>? _report;
  String _receiptText = '';

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = DateTime(now.year, now.month, now.day);
    _to = _from;
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  Future<void> _bootstrap() async {
    setState(() {
      _booting = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final open = await context.read<ReportsService>().getXReportOpen();
      if (!mounted) return;
      final counters = <({int code, String name})>[(code: 0, name: 'All counters')];
      final raw = open['counters'];
      if (raw is List) {
        for (final r in raw) {
          if (r is! Map) continue;
          final m = Map<String, dynamic>.from(r);
          final code = int.tryParse('${m['counter_code'] ?? 0}') ?? 0;
          if (code <= 0) continue;
          final name = '${m['counter_name'] ?? ''}'.trim();
          counters.add((code: code, name: name.isEmpty ? 'Counter $code' : name));
        }
      }
      final def = DateTime.tryParse('${open['default_date'] ?? ''}'.trim());
      setState(() {
        _counters = counters;
        if (def != null) {
          _from = DateTime(def.year, def.month, def.day);
          _to = _from;
        }
        if (_counters.length == 2) {
          // Prefer the only real counter when available (classic X Report).
          _counterCode = _counters[1].code;
        }
        _booting = false;
      });
      await _load();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _booting = false;
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final sameDay = _from.year == _to.year && _from.month == _to.month && _from.day == _to.day;
      final data = await context.read<ReportsService>().getXReport(
            counterCode: _counterCode,
            posDate: sameDay ? isoDate(_from) : '',
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
          );
      if (!mounted) return;
      final report = data['report'];
      setState(() {
        _report = report is Map ? Map<String, dynamic>.from(report) : null;
        _receiptText = '${data['receipt_text'] ?? ''}'.trim();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _report = null;
        _receiptText = '';
      });
    }
  }

  Future<File> _writePdf() async {
    final sameDay = _from.year == _to.year && _from.month == _to.month && _from.day == _to.day;
    final bytes = await context.read<ReportsService>().downloadXReportPdf(
          counterCode: _counterCode,
          posDate: sameDay ? isoDate(_from) : '',
          dateFrom: isoDate(_from),
          dateTo: isoDate(_to),
        );
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/x_report_${isoDate(_from)}_${_counterCode}.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _printCopy() async {
    if (_pdfBusy) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writePdf();
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(opened.message.isNotEmpty ? opened.message : 'Could not open PDF.')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writePdf();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'X Report ${isoDate(_from)}',
        text: 'X Report ${isoDate(_from)}',
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _pickFrom() async {
    await pickReportDate(
      context,
      initial: _from,
      onPicked: (d) {
        setState(() {
          _from = DateTime(d.year, d.month, d.day);
          if (_to.isBefore(_from)) _to = _from;
        });
      },
    );
  }

  Future<void> _pickTo() async {
    await pickReportDate(
      context,
      initial: _to,
      onPicked: (d) {
        setState(() {
          _to = DateTime(d.year, d.month, d.day);
          if (_to.isBefore(_from)) _from = _to;
        });
      },
    );
  }

  String _money(dynamic v) {
    final n = double.tryParse('$v'.replaceAll(',', '')) ?? 0;
    return fmtMoney(n);
  }

  @override
  Widget build(BuildContext context) {
    final busy = _booting || _loading || _pdfBusy;
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('X Report', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          if (_report != null)
            IconButton(
              tooltip: 'Share PDF',
              onPressed: busy ? null : _sharePdf,
              icon: _pdfBusy
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.share_outlined),
            ),
          if (_report != null)
            IconButton(
              tooltip: 'Print copy',
              onPressed: busy ? null : _printCopy,
              icon: const Icon(Icons.picture_as_pdf_outlined),
            ),
          IconButton(
            tooltip: 'Refresh',
            onPressed: busy ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: _booting
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : Column(
              children: [
                _filters(busy),
                Expanded(
                  child: _error != null && _report == null
                      ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
                      : RefreshIndicator(
                          color: _accent,
                          onRefresh: _load,
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(14, 4, 14, 24),
                            children: [
                              if (_loading)
                                const Padding(
                                  padding: EdgeInsets.only(bottom: 10),
                                  child: LinearProgressIndicator(minHeight: 2, color: _accent),
                                ),
                              if (_error != null && _report != null)
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 10),
                                  child: Text(_error!, style: const TextStyle(color: Color(0xFFC62828), fontSize: 12.5)),
                                ),
                              if (_report != null) _receiptCard(_report!),
                              if (_report == null && !_loading)
                                const Padding(
                                  padding: EdgeInsets.only(top: 40),
                                  child: Center(child: Text('No report data.')),
                                ),
                            ],
                          ),
                        ),
                ),
              ],
            ),
    );
  }

  Widget _filters(bool busy) {
    return Material(
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: _dateChip('From', isoDate(_from), busy ? null : _pickFrom),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _dateChip('To', isoDate(_to), busy ? null : _pickTo),
                ),
              ],
            ),
            const SizedBox(height: 8),
            InputDecorator(
              decoration: InputDecoration(
                labelText: 'Counter',
                filled: true,
                fillColor: const Color(0xFFF6F7FC),
                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<int>(
                  isExpanded: true,
                  value: _counters.any((c) => c.code == _counterCode) ? _counterCode : 0,
                  items: [
                    for (final c in _counters)
                      DropdownMenuItem(
                        value: c.code,
                        child: Text(c.code == 0 ? c.name : '${c.code} · ${c.name}'),
                      ),
                  ],
                  onChanged: busy
                      ? null
                      : (v) {
                          if (v == null) return;
                          setState(() => _counterCode = v);
                        },
                ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: busy ? null : _load,
                style: FilledButton.styleFrom(
                  backgroundColor: _accent,
                  minimumSize: const Size.fromHeight(44),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                icon: const Icon(Icons.assessment_outlined, size: 20),
                label: Text(_loading ? 'Loading…' : 'Run X Report'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dateChip(String label, String value, VoidCallback? onTap) {
    return Material(
      color: const Color(0xFFF6F7FC),
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text(value, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: _navy)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _receiptCard(Map<String, dynamic> r) {
    final loc = '${r['location_name'] ?? ''}'.trim();
    final phones = '${r['location_phones'] ?? ''}'.trim();
    final isFinal = r['is_final'] == true;
    final counterCode = r['counter_code'];
    final counterName = '${r['counter_name'] ?? ''}'.trim();
    final counterDisp = [
      if (counterCode != null && '$counterCode' != '0' && '$counterCode'.isNotEmpty) '$counterCode',
      if (counterName.isNotEmpty) counterName,
    ].join(' ').trim();
    final tenders = (r['tender_breakdown'] is List) ? List<dynamic>.from(r['tender_breakdown'] as List) : const [];

    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 18, 16, 18),
        child: Column(
          children: [
            if (loc.isNotEmpty)
              Text(loc.toUpperCase(), textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: _navy)),
            if (phones.isNotEmpty) ...[
              const SizedBox(height: 2),
              Text(phones, textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
            ],
            const SizedBox(height: 12),
            Text(
              isFinal ? '*** SHIFT CLOSE COPY ***' : '*** X REPORT COPY ***',
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: _navy),
            ),
            Text(
              isFinal ? 'Final shift close' : 'Interim report (not final)',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
            const SizedBox(height: 10),
            _kv('Counter day', '${r['pos_date_display'] ?? ''}'),
            const Divider(height: 18),
            _kv('Counter', counterDisp.isEmpty ? 'All counters' : counterDisp),
            if ('${r['cashier'] ?? ''}'.trim().isNotEmpty) _kv('Cashier', '${r['cashier']}'),
            _kv('Check Time', '${r['check_time_display'] ?? ''}'),
            const Divider(height: 18),
            _kv('Cash customer sale', _money(r['direct_customer'])),
            _kv('Credit customer sale', _money(r['credit_sales'])),
            _kv('Total Sales', _money(r['total_sales']), bold: true),
            _kv('Total Discount', _money(r['total_discount'] ?? r['discount_lines'])),
            _kv('Sales returns', _money(r['sales_returns'])),
            _kv('Total Cancel', _money(r['total_cancel'])),
            const Divider(height: 18),
            ..._tenderRows(tenders, r),
            if ((double.tryParse('${r['collection_total'] ?? 0}') ?? 0).abs() > 0.0005)
              _kv('Total collection', _money(r['collection_total']), bold: true),
            const Divider(height: 18),
            Text(
              isFinal ? 'Shift closed.' : 'Use Close for official final print.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
            const SizedBox(height: 4),
            Text(
              'Bills: ${r['bill_count'] ?? 0}',
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: _navy),
            ),
            if (_receiptText.isNotEmpty) ...[
              const SizedBox(height: 14),
              Align(
                alignment: Alignment.centerLeft,
                child: Text('Receipt text', style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
              ),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF6F7FC),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: SelectableText(
                  _receiptText,
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 11.5, height: 1.35, color: _navy),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> _tenderRows(List<dynamic> tenders, Map<String, dynamic> r) {
    const creditCodes = {'CREDIT', 'ON_ACCOUNT', 'ONACCOUNT', 'CREDIT_ON_ACCOUNT', 'ACCOUNT'};
    final out = <Widget>[];
    Map<String, dynamic>? cashRow;
    for (final raw in tenders) {
      if (raw is! Map) continue;
      final row = Map<String, dynamic>.from(raw);
      final code = '${row['code'] ?? ''}'.trim().toUpperCase();
      if (creditCodes.contains(code)) continue;
      final amt = double.tryParse('${row['amount'] ?? 0}') ?? 0;
      if (amt.abs() <= 0.0005) continue;
      final isCash = row['is_cash'] == true || code == 'CASH';
      if (isCash) {
        cashRow = row;
        continue;
      }
      final label = '${row['label'] ?? row['code'] ?? '—'}'.trim();
      out.add(_kv(label, _money(amt)));
    }
    if (cashRow != null) {
      out.add(_kv('Cash in Box', _money(cashRow['amount'])));
    } else {
      out.add(_kv('Cash in Box', _money(r['cash_in_box'])));
    }
    return out;
  }

  Widget _kv(String left, String right, {bool bold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Expanded(
            child: Text(
              left,
              style: TextStyle(
                fontSize: 13,
                fontWeight: bold ? FontWeight.w800 : FontWeight.w600,
                color: _navy,
              ),
            ),
          ),
          Text(
            right,
            style: TextStyle(
              fontSize: 13.5,
              fontWeight: bold ? FontWeight.w800 : FontWeight.w700,
              color: _navy,
            ),
          ),
        ],
      ),
    );
  }
}
