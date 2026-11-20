import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/stock_return_service.dart';
import '../../widgets/api_error_banner.dart';
import 'stock_return_form_screen.dart';
import '../../core/theme/app_theme.dart';

class StockReturnDetailScreen extends StatefulWidget {
  const StockReturnDetailScreen({
    super.key,
    required this.returnNo,
    this.rowKind = 'request',
  });

  final String returnNo;
  final String rowKind;

  @override
  State<StockReturnDetailScreen> createState() => _StockReturnDetailScreenState();
}

class _StockReturnDetailScreenState extends State<StockReturnDetailScreen> {
  static const _accent = Color(0xFF1565C0);

  bool _loading = true;
  bool _cancelling = false;
  bool _approving = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  StockReturnDetail? _detail;

  @override
  void initState() {
    super.initState();
    _load();
  }

  String get _apiKind {
    final k = widget.rowKind.toLowerCase();
    if (k == 'posted' || k.startsWith('pr_') || k == 'posted_linked') return 'posted';
    return 'request';
  }

  String get _pdfKind =>
      _detail?.documentType == 'posted_return' || _apiKind == 'posted' ? 'posted' : 'request';

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final detail = await context.read<StockReturnService>().getReturnDetail(
            widget.returnNo,
            kind: _apiKind,
          );
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

  Future<void> _editReturn() async {
    final detail = _detail;
    if (detail == null || !detail.canEdit) return;
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => StockReturnFormScreen(editReturnNo: widget.returnNo),
      ),
    );
    if (saved == true && mounted) await _load();
  }

  Future<File> _writePdfFile() async {
    final bytes = await context.read<StockReturnService>().downloadReturnPdf(
          widget.returnNo,
          kind: _pdfKind,
        );
    final dir = await getTemporaryDirectory();
    final safe = widget.returnNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/RT_$safe.pdf');
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
        subject: 'Purchase Return ${widget.returnNo}',
        text: 'Purchase Return ${widget.returnNo}',
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

  Future<void> _cancelReturn() async {
    final detail = _detail;
    if (detail == null || _cancelling || !detail.canCancel) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel Purchase Return'),
        content: Text(
          'Cancel PR-${widget.returnNo}?\n\n'
          'This cannot be undone.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cancel return'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _cancelling = true);
    try {
      await context.read<StockReturnService>().cancelReturn(widget.returnNo);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('PR-${widget.returnNo} cancelled.')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _cancelling = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  Future<void> _approveReturn() async {
    final detail = _detail;
    if (detail == null || _approving || !detail.canApprove) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Post Purchase Return'),
        content: Text(
          'Approve and post PR-${widget.returnNo}?\n\n'
          'Stock will be returned from inventory.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: _accent),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Post return'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _approving = true);
    try {
      final result = await context.read<StockReturnService>().approveReturn(widget.returnNo);
      if (!mounted) return;
      final msg = (result['message'] as String?)?.trim();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg?.isNotEmpty == true ? msg! : 'PR-${widget.returnNo} posted.')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _approving = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  String _fmtQty(double q) {
    if (q == q.roundToDouble()) return q.round().toString();
    return q.toStringAsFixed(2);
  }

  String _statusLabel(StockReturnDetail detail) {
    if (detail.isCanceled) return 'CANCELED';
    if (detail.isPosted) return 'POSTED';
    return 'DRAFT';
  }

  Color _statusColor(StockReturnDetail detail) {
    if (detail.isCanceled) return const Color(0xFFC62828);
    if (detail.isPosted) return const Color(0xFF2E7D32);
    return const Color(0xFFE65100);
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final busy = _loading || _cancelling || _approving || _pdfBusy;
    final canEdit = detail != null && detail.canEdit && !busy;
    final canCancel = detail != null && detail.canCancel && !busy;
    final canApprove = detail != null && detail.canApprove && !busy;
    final showBottomBar = canEdit || canCancel || canApprove;

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text('PR-${widget.returnNo}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
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
          if (canEdit)
            IconButton(
              tooltip: 'Edit',
              onPressed: _editReturn,
              icon: const Icon(Icons.edit_outlined),
            ),
          if (canCancel)
            IconButton(
              tooltip: 'Cancel return',
              onPressed: _cancelReturn,
              icon: const Icon(Icons.cancel_outlined, color: Color(0xFFC62828)),
            ),
          IconButton(onPressed: busy ? null : _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      bottomNavigationBar: !showBottomBar
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (canApprove)
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: _approveReturn,
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF2E7D32),
                            minimumSize: const Size.fromHeight(46),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                          icon: _approving
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                )
                              : const Icon(Icons.check_circle_outline),
                          label: Text(_approving ? 'Posting…' : 'Approve / Post'),
                        ),
                      ),
                    if (canApprove && (canEdit || canCancel)) const SizedBox(height: 10),
                    if (canEdit || canCancel)
                      Row(
                        children: [
                          if (canEdit)
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: _editReturn,
                                style: OutlinedButton.styleFrom(
                                  foregroundColor: _accent,
                                  minimumSize: const Size.fromHeight(46),
                                  side: const BorderSide(color: _accent),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                ),
                                icon: const Icon(Icons.edit_outlined),
                                label: const Text('Edit'),
                              ),
                            ),
                          if (canEdit && canCancel) const SizedBox(width: 10),
                          if (canCancel)
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: _cancelReturn,
                                style: OutlinedButton.styleFrom(
                                  foregroundColor: const Color(0xFFC62828),
                                  minimumSize: const Size.fromHeight(46),
                                  side: const BorderSide(color: Color(0xFFC62828)),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                ),
                                icon: _cancelling
                                    ? const SizedBox(
                                        width: 18,
                                        height: 18,
                                        child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFC62828)),
                                      )
                                    : const Icon(Icons.cancel_outlined),
                                label: Text(_cancelling ? 'Cancelling…' : 'Cancel return'),
                              ),
                            ),
                        ],
                      ),
                  ],
                ),
              ),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : _error != null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : detail == null
                  ? const Center(child: Text('Purchase Return not found.'))
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

  Widget _headerCard(StockReturnDetail detail) {
    final inv = detail.summary;
    final status = _statusLabel(detail);
    final statusColor = _statusColor(detail);
    final stripe = detail.isPosted
        ? const Color(0xFF66BB6A)
        : detail.isCanceled
            ? const Color(0xFFE57373)
            : const Color(0xFFFFB74D);

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
              Expanded(
                child: Text(
                  inv.supplierLabel,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  status,
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: statusColor),
                ),
              ),
            ],
          ),
          if (inv.supplierCode.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('Code ${inv.supplierCode}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          if (detail.remarks.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(detail.remarks, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ],
          if (detail.postedStockNo.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'Posted stock no. ${detail.postedStockNo}',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
            ),
          ],
          if (detail.receiptNo.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Receipt ${detail.receiptNo}',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              _metaChip(Icons.calendar_today_outlined, inv.returnDate.isEmpty ? '—' : inv.returnDate),
              const SizedBox(width: 8),
              _metaChip(Icons.format_list_numbered_rounded, '${detail.lines.length} lines'),
            ],
          ),
          const Divider(height: 22),
          Row(
            children: [
              const Text('Amount', style: TextStyle(fontSize: 13, color: Color(0xFF6F7482))),
              const Spacer(),
              Text(
                inv.amount.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: Color(0xFF3E63F5)),
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

  Widget _lineCard(StockReturnLine line) {
    final name = line.itemName.isNotEmpty ? line.itemName : line.itemCode;
    final subtitle = [
      if (line.itemCode.isNotEmpty && line.itemName.isNotEmpty) 'Code ${line.itemCode}',
      if (line.uom.isNotEmpty) line.uom,
    ].join(' · ');
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
              color: const Color(0xFFE3F2FD),
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
                  '${_fmtQty(line.qty)} × ${line.rate.toStringAsFixed(2)}'
                  '${line.discount > 0 ? ' (−${line.discount.toStringAsFixed(2)} disc)' : ''}',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            line.amount.toStringAsFixed(2),
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
          ),
        ],
      ),
    );
  }
}
