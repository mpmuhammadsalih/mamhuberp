import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/cash_payment_voucher_service.dart';
import '../../widgets/api_error_banner.dart';
import 'cash_payment_voucher_form_screen.dart';
import '../../core/theme/app_theme.dart';

class CashPaymentVoucherDetailScreen extends StatefulWidget {
  const CashPaymentVoucherDetailScreen({
    super.key,
    required this.voucherNo,
  });

  final String voucherNo;

  @override
  State<CashPaymentVoucherDetailScreen> createState() => _CashPaymentVoucherDetailScreenState();
}

class _CashPaymentVoucherDetailScreenState extends State<CashPaymentVoucherDetailScreen> {
  static const _accent = Color(0xFF00897B);

  bool _loading = true;
  bool _posting = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  CpvDetail? _detail;

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
      final detail = await context.read<CashPaymentVoucherService>().getDetail(widget.voucherNo);
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

  Future<void> _editVoucher() async {
    final detail = _detail;
    if (detail == null || !detail.canEdit) return;
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => CashPaymentVoucherFormScreen(editVoucherNo: widget.voucherNo),
      ),
    );
    if (saved == true && mounted) await _load();
  }

  Future<File> _writePdfFile() async {
    final bytes = await context.read<CashPaymentVoucherService>().downloadPdf(widget.voucherNo);
    final dir = await getTemporaryDirectory();
    final safe = widget.voucherNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/CPV_$safe.pdf');
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
        subject: 'Cash Payment Voucher ${widget.voucherNo}',
        text: 'Cash Payment Voucher ${widget.voucherNo}',
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

  Future<void> _postFromDetail() async {
    final detail = _detail;
    if (detail == null || _posting || !detail.canPost) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Post to GL'),
        content: Text(
          'Post Cash Payment Voucher ${widget.voucherNo} to the general ledger?\n\n'
          'This cannot be undone.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Post voucher'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _posting = true);
    try {
      final header = <String, dynamic>{
        'voucher_no': detail.voucherNo,
        'voucher_date': detail.voucherDate,
        'petty_cash_account': detail.pettyCashAccount,
        'expense_parent_account': detail.expenseParentAccount,
        'reference_no': detail.referenceNo,
        'narration': detail.narration,
      };
      final lines = detail.lines
          .map(
            (l) => <String, dynamic>{
              'account_code': l.accountCode,
              'description': l.description,
              'amount': l.amount,
            },
          )
          .toList();

      final result = await context.read<CashPaymentVoucherService>().postVoucher(
            header: header,
            lines: lines,
          );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => _CpvPostedDialog(result: result),
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _posting = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  String _statusLabel(CpvDetail detail) => detail.isPosted ? 'POSTED' : 'DRAFT';

  Color _statusColor(CpvDetail detail) =>
      detail.isPosted ? const Color(0xFF2E7D32) : const Color(0xFF00695C);

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final busy = _loading || _posting || _pdfBusy;
    final canEdit = detail != null && detail.canEdit && !busy;
    final canPost = detail != null && detail.canPost && !busy;
    final showPdf = detail != null && detail.isPosted;
    final showBottomBar = canEdit || canPost;

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(
          detail?.voucherNo ?? widget.voucherNo,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        actions: [
          if (showPdf)
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
          if (showPdf)
            IconButton(
              tooltip: 'Print copy',
              onPressed: busy ? null : _viewPdf,
              icon: const Icon(Icons.picture_as_pdf_outlined),
            ),
          if (canEdit)
            IconButton(
              tooltip: 'Edit',
              onPressed: _editVoucher,
              icon: const Icon(Icons.edit_outlined),
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
                    if (canPost)
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: _postFromDetail,
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF2E7D32),
                            minimumSize: const Size.fromHeight(46),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                          icon: _posting
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                )
                              : const Icon(Icons.check_circle_outline),
                          label: Text(_posting ? 'Posting…' : 'Post to GL'),
                        ),
                      ),
                    if (canPost && canEdit) const SizedBox(height: 10),
                    if (canEdit)
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: _editVoucher,
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
                  ],
                ),
              ),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : _error != null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : detail == null
                  ? const Center(child: Text('Cash Payment Voucher not found.'))
                  : RefreshIndicator(
                      color: _accent,
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
                        children: [
                          _headerCard(detail),
                          const SizedBox(height: 12),
                          Text(
                            'Expense lines (${detail.lines.length})',
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
                                'No expense lines on this voucher.',
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

  Widget _headerCard(CpvDetail detail) {
    final status = _statusLabel(detail);
    final statusColor = _statusColor(detail);
    final stripe = detail.isPosted ? const Color(0xFF66BB6A) : const Color(0xFF00897B);

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
                  detail.voucherNo,
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
          if (detail.pettyCashAccount.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'Petty cash: ${detail.pettyCashName.isNotEmpty ? detail.pettyCashName : detail.pettyCashAccount}',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
            ),
          ],
          if (detail.expenseParentAccount.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Expense parent: ${detail.expenseParentName.isNotEmpty ? detail.expenseParentName : detail.expenseParentAccount}',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
            ),
          ],
          if (detail.referenceNo.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('Reference ${detail.referenceNo}', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          if (detail.narration.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(detail.narration, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ],
          if (detail.glVoucherNo.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'GL voucher no. ${detail.glVoucherNo}',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              _metaChip(Icons.calendar_today_outlined, detail.voucherDate.isEmpty ? '—' : detail.voucherDate),
              const SizedBox(width: 8),
              _metaChip(Icons.format_list_numbered_rounded, '${detail.lines.length} lines'),
            ],
          ),
          const Divider(height: 22),
          Row(
            children: [
              const Text('Total', style: TextStyle(fontSize: 13, color: Color(0xFF6F7482))),
              const Spacer(),
              Text(
                detail.totalAmount.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: Color(0xFF00897B)),
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
        color: const Color(0xFFE0F2F1),
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

  Widget _lineCard(CpvLine line) {
    final name = line.accountName.isNotEmpty ? line.accountName : line.accountCode;
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
              color: const Color(0xFFE0F2F1),
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
                if (line.accountCode.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(line.accountCode, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ],
                if (line.description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(line.description, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                ],
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

class _CpvPostedDialog extends StatefulWidget {
  const _CpvPostedDialog({required this.result});

  final CpvPostResult result;

  @override
  State<_CpvPostedDialog> createState() => _CpvPostedDialogState();
}

class _CpvPostedDialogState extends State<_CpvPostedDialog> {
  static const _accent = Color(0xFF00897B);

  bool _pdfBusy = false;
  String? _pdfError;

  Future<File> _writePdfFile() async {
    final bytes = await context.read<CashPaymentVoucherService>().downloadPdf(widget.result.voucherNo);
    final dir = await getTemporaryDirectory();
    final safe = widget.result.voucherNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/CPV_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final file = await _writePdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'Cash Payment Voucher ${widget.result.voucherNo}',
        text: 'Cash Payment Voucher ${widget.result.voucherNo}',
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _pdfError = handleApiError(context, e, authenticatedContext: true));
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    return Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 28),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(22, 28, 22, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: const BoxDecoration(color: Color(0xFFE8F5E9), shape: BoxShape.circle),
              child: const Icon(Icons.check_rounded, size: 40, color: Color(0xFF2E7D32)),
            ),
            const SizedBox(height: 18),
            const Text(
              'Voucher posted',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Color(0xFF262C50)),
            ),
            const SizedBox(height: 6),
            Text(
              result.voucherNo,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: _accent, height: 1.1),
            ),
            if (result.glVoucherNo.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                'GL Voucher No: ${result.glVoucherNo}',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Colors.grey.shade800),
              ),
            ],
            if (result.totalAmount > 0) ...[
              const SizedBox(height: 8),
              Text(
                'Total ${result.totalAmount.toStringAsFixed(2)}',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
              ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _pdfBusy ? null : _sharePdf,
                icon: _pdfBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.share_outlined),
                label: Text(_pdfBusy ? 'Preparing PDF…' : 'Share PDF'),
                style: FilledButton.styleFrom(
                  backgroundColor: _accent,
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            if (_pdfError != null) ...[
              const SizedBox(height: 8),
              Text(
                _pdfError!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12, color: Color(0xFFC62828), height: 1.3),
              ),
            ],
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: TextButton(
                onPressed: _pdfBusy ? null : () => Navigator.of(context).pop(),
                child: const Text('Done', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
