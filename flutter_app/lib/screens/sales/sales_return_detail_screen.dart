import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../widgets/api_error_banner.dart';
import '../../services/sales_service.dart';
import '../../core/theme/app_theme.dart';

class SalesReturnDetailScreen extends StatefulWidget {
  const SalesReturnDetailScreen({super.key, required this.billno});

  final String billno;

  @override
  State<SalesReturnDetailScreen> createState() => _SalesReturnDetailScreenState();
}

class _SalesReturnDetailScreenState extends State<SalesReturnDetailScreen> {
  static const _accent = Color(0xFF6A1B9A);

  bool _loading = true;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  SalesInvoiceDetail? _detail;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final detail = await context.read<SalesService>().getReturnDetail(widget.billno);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _downloadPdf() async {
    if (_pdfBusy || widget.billno.trim().isEmpty) return;
    setState(() => _pdfBusy = true);
    try {
      final bytes = await context.read<SalesService>().downloadReturnPdf(widget.billno);
      final dir = await getTemporaryDirectory();
      final safe = widget.billno.replaceAll(RegExp(r'[^\w\-]+'), '_');
      final file = File('${dir.path}/return_$safe.pdf');
      await file.writeAsBytes(bytes, flush: true);
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PDF saved to ${file.path}')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  String _fmtQty(double q) {
    final a = q.abs();
    if (a == a.roundToDouble()) return a.round().toString();
    return a.toStringAsFixed(2);
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text('Return-${widget.billno}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(
            tooltip: 'Print copy',
            onPressed: _loading || _pdfBusy ? null : _downloadPdf,
            icon: _pdfBusy
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: _accent),
                  )
                : const Icon(Icons.picture_as_pdf_outlined),
          ),
          IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : _error != null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : detail == null
                  ? const Center(child: Text('Return not found.'))
                  : RefreshIndicator(
                      color: _accent,
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
                        children: [
                          _headerCard(detail.summary, detail.lines.length),
                          const SizedBox(height: 12),
                          Text(
                            'Items (${detail.lines.length})',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                              color: Colors.grey.shade800,
                            ),
                          ),
                          const SizedBox(height: 8),
                          if (detail.lines.isEmpty)
                            Container(
                              padding: const EdgeInsets.all(20),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                'No line items on this return.',
                                style: TextStyle(color: Colors.grey.shade600),
                              ),
                            )
                          else
                            ...detail.lines.map(_lineCard),
                        ],
                      ),
                    ),
    );
  }

  Widget _headerCard(SalesInvoiceSummary inv, int lineCount) {
    final isCredit = inv.billingType == 'CREDIT';
    final netAbs = inv.netAmount.abs();
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: const Border(left: BorderSide(color: _accent, width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  inv.customerLabel,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: const Color(0xFFF3E5F5),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Text(
                  'Return',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: _accent),
                ),
              ),
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: isCredit ? const Color(0xFFF3E5F5) : const Color(0xFFE9F9EF),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  inv.billingType,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: isCredit ? const Color(0xFF6A1B9A) : const Color(0xFF1C9C58),
                  ),
                ),
              ),
            ],
          ),
          if (inv.customerCode.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('Code ${inv.customerCode}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          if (inv.orderNo.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text('Order / Invoice ref ${inv.orderNo}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              _metaChip(Icons.calendar_today_outlined, inv.billDate),
              const SizedBox(width: 8),
              _metaChip(Icons.format_list_numbered_rounded, '$lineCount lines'),
            ],
          ),
          const Divider(height: 22),
          Row(
            children: [
              const Text('Return total', style: TextStyle(fontSize: 13, color: Color(0xFF6F7482))),
              const Spacer(),
              Text(
                netAbs.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: _accent),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metaChip(IconData icon, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF0F4FA),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: _accent),
          const SizedBox(width: 4),
          Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Widget _lineCard(SalesInvoiceDetailLine line) {
    final name = line.itemName.isNotEmpty ? line.itemName : line.itemCode;
    final subtitle = [
      if (line.itemCode.isNotEmpty && line.itemName.isNotEmpty) 'Code ${line.itemCode}',
      if (line.uom.isNotEmpty) line.uom,
    ].join(' · ');
    final qtyAbs = line.qty.abs();
    final amountAbs = line.amount.abs();
    final discAbs = line.discount.abs();
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EAED)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFFF3E5F5),
              borderRadius: BorderRadius.circular(10),
            ),
            alignment: Alignment.center,
            child: Text(
              '${line.lineNo}',
              style: const TextStyle(fontWeight: FontWeight.w800, color: _accent, fontSize: 13),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
                if (subtitle.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(subtitle, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ],
                const SizedBox(height: 6),
                Text(
                  '${_fmtQty(qtyAbs)} × ${line.rate.abs().toStringAsFixed(2)}'
                  '${discAbs > 0 ? ' (−${discAbs.toStringAsFixed(2)} disc)' : ''}',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            amountAbs.toStringAsFixed(2),
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
          ),
        ],
      ),
    );
  }
}
