import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/stock_adjustment_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../core/theme/app_theme.dart';

class StockAdjustmentDetailScreen extends StatefulWidget {
  const StockAdjustmentDetailScreen({
    super.key,
    required this.adjNo,
  });

  final String adjNo;

  @override
  State<StockAdjustmentDetailScreen> createState() => _StockAdjustmentDetailScreenState();
}

class _StockAdjustmentDetailScreenState extends State<StockAdjustmentDetailScreen> {
  static const _accent = Color(0xFFEF6C00);

  bool _loading = true;
  bool _reversing = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  StockAdjustmentDetail? _detail;

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
      final detail = await context.read<StockAdjustmentService>().getAdjustmentDetail(widget.adjNo);
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

  Future<File> _writePdfFile() async {
    final bytes = await context.read<StockAdjustmentService>().downloadPdf(widget.adjNo);
    final dir = await getTemporaryDirectory();
    final safe = widget.adjNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/SA_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writePdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'Stock Adjustment ${widget.adjNo}',
        text: 'Stock Adjustment SA-${widget.adjNo}',
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _viewPdf() async {
    if (_pdfBusy) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writePdfFile();
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

  Future<void> _reverseAdjustment() async {
    final detail = _detail;
    if (detail == null || _reversing || !detail.canReverse) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reverse Stock Adjustment'),
        content: Text(
          'Reverse SA-${widget.adjNo}?\n\n'
          'A reversal document will be created and inventory will be updated.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Reverse'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _reversing = true);
    try {
      final result = await context.read<StockAdjustmentService>().reverseAdjustment(widget.adjNo);
      if (!mounted) return;
      final msg = (result['message'] as String?)?.trim();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg?.isNotEmpty == true ? msg! : 'SA-${widget.adjNo} reversed.')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _reversing = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  String _fmtQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  Color _adjustColor(double adjustQty) {
    if (adjustQty > 0) return const Color(0xFF2E7D32);
    if (adjustQty < 0) return const Color(0xFFC62828);
    return Colors.grey.shade600;
  }

  (Color, Color, Color) _statusColors(String status) {
    return switch (status) {
      'POSTED' => (
          const Color(0xFF2E7D32),
          const Color(0xFFE8F5E9),
          const Color(0xFF66BB6A),
        ),
      'REVERSED' => (
          const Color(0xFFC62828),
          const Color(0xFFFFEBEE),
          const Color(0xFFE57373),
        ),
      'REVERSAL' => (
          const Color(0xFF1565C0),
          const Color(0xFFE3F2FD),
          const Color(0xFF64B5F6),
        ),
      _ => (
          const Color(0xFFEF6C00),
          const Color(0xFFFFF3E0),
          const Color(0xFFFFB74D),
        ),
    };
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final busy = _loading || _reversing || _pdfBusy;
    final canReverse = detail != null && detail.canReverse && !busy;

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text('SA-${widget.adjNo}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          if (detail != null)
            IconButton(
              tooltip: 'Share PDF',
              onPressed: busy ? null : _sharePdf,
              icon: _pdfBusy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.share_outlined),
            ),
          if (detail != null)
            IconButton(
              tooltip: 'Print copy',
              onPressed: busy ? null : _viewPdf,
              icon: const Icon(Icons.picture_as_pdf_outlined),
            ),
          IconButton(onPressed: busy ? null : _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      bottomNavigationBar: !canReverse
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _reverseAdjustment,
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFFC62828),
                      minimumSize: const Size.fromHeight(46),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    icon: _reversing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.undo_rounded),
                    label: Text(_reversing ? 'Reversing…' : 'Reverse adjustment'),
                  ),
                ),
              ),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : _error != null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : detail == null
                  ? const Center(child: Text('Stock adjustment not found.'))
                  : RefreshIndicator(
                      color: _accent,
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
                        children: [
                          _headerCard(detail),
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
                                'No line items on this adjustment.',
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

  Widget _headerCard(StockAdjustmentDetail detail) {
    final inv = detail.summary;
    final status = inv.status.isEmpty ? 'POSTED' : inv.status;
    final (statusFg, statusBg, stripe) = _statusColors(status);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: stripe, width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Stock Adjustment',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: statusBg,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  status,
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: statusFg),
                ),
              ),
            ],
          ),
          if (detail.store.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('Store ${detail.store}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          if (detail.remarks.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(detail.remarks, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ],
          if (detail.reversalOfAdjNo.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'Reversal of SA-${detail.reversalOfAdjNo}',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
            ),
          ],
          if (detail.reversedAdjNo.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Reversed by SA-${detail.reversedAdjNo}',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              _metaChip(Icons.calendar_today_outlined, inv.adjDate.isEmpty ? '—' : inv.adjDate),
              const SizedBox(width: 8),
              _metaChip(Icons.format_list_numbered_rounded, '${detail.lines.length} lines'),
            ],
          ),
          const Divider(height: 22),
          Row(
            children: [
              const Text('Stock value', style: TextStyle(fontSize: 13, color: Color(0xFF6F7482))),
              const Spacer(),
              Text(
                inv.stockValue.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: Color(0xFFEF6C00)),
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
        color: const Color(0xFFFFF3E0),
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

  Widget _lineCard(StockAdjustmentLine line) {
    final name = line.itemName.isNotEmpty ? line.itemName : line.itemCode;
    final subtitle = [
      if (line.itemCode.isNotEmpty && line.itemName.isNotEmpty) 'Code ${line.itemCode}',
      if (line.uom.isNotEmpty) line.uom,
      if (line.store.isNotEmpty) line.store,
    ].join(' · ');
    final adjustColor = _adjustColor(line.adjustQty);
    final adjustPrefix = line.adjustQty > 0 ? '+' : '';

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
              color: adjustColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            alignment: Alignment.center,
            child: Icon(
              line.adjustQty >= 0 ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
              color: adjustColor,
              size: 20,
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
                  'Current ${_fmtQty(line.currentQty)} → New ${_fmtQty(line.newQty)}',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                ),
                if (line.cost > 0)
                  Text(
                    'Cost ${line.cost.toStringAsFixed(2)}',
                    style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '$adjustPrefix${_fmtQty(line.adjustQty)}',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: adjustColor),
              ),
              Text(
                line.uom,
                style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
