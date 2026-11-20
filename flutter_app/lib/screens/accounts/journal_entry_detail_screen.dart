import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/journal_entry_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_overlay.dart';
import 'accounts_report_helpers.dart';
import 'journal_entry_form_screen.dart';
import '../../core/theme/app_theme.dart';

class JournalEntryDetailScreen extends StatefulWidget {
  const JournalEntryDetailScreen({super.key, required this.docId});

  final String docId;

  @override
  State<JournalEntryDetailScreen> createState() => _JournalEntryDetailScreenState();
}

class _JournalEntryDetailScreenState extends State<JournalEntryDetailScreen> {
  static const _accent = Color(0xFF6A1B9A);
  static const _bg = Color(0xFFF6F7FC);

  bool _loading = true;
  bool _busy = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  JeDetail? _detail;

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
      final detail = await context.read<JournalEntryService>().getDetail(widget.docId);
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

  Future<void> _edit() async {
    final d = _detail;
    if (d == null || !d.canEdit) return;
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => JournalEntryFormScreen(
          editDocId: d.isDraft ? d.draftId : d.voucherNo,
        ),
      ),
    );
    if (saved == true && mounted) await _load();
  }

  Future<void> _openPdf() async {
    final d = _detail;
    if (d == null || d.isDraft) return;
    await openPdfBytes(
      context,
      loadBytes: () => context.read<JournalEntryService>().downloadPdf(d.voucherNo),
      fileName: 'Journal_${d.voucherNo}.pdf',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _sharePdf() async {
    final d = _detail;
    if (d == null || d.isDraft) return;
    await sharePdfBytes(
      context,
      loadBytes: () => context.read<JournalEntryService>().downloadPdf(d.voucherNo),
      fileName: 'Journal_${d.voucherNo}.pdf',
      subject: 'Journal ${d.voucherNo}',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _confirmReverse() async {
    final d = _detail;
    if (d == null || !d.canReverse) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reverse journal?'),
        content: Text(
          'This posts a reversing voucher for ${d.voucherNo}. Continue?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Reverse')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final result = await context.read<JournalEntryService>().reverseJournal(d.voucherNo);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Reversed')),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = _detail;
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(
          d?.voucherNo.isNotEmpty == true ? d!.voucherNo : 'Journal',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        actions: [
          if (d != null && d.isPosted) ...[
            IconButton(
              tooltip: 'Share PDF',
              onPressed: _pdfBusy || _busy ? null : _sharePdf,
              icon: const Icon(Icons.share_outlined, size: 20),
            ),
            IconButton(
              tooltip: 'Print copy',
              onPressed: _pdfBusy || _busy ? null : _openPdf,
              icon: _pdfBusy
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.picture_as_pdf_outlined, size: 22),
            ),
          ],
          if (d != null && d.canEdit)
            IconButton(
              tooltip: 'Edit',
              onPressed: _busy ? null : _edit,
              icon: const Icon(Icons.edit_outlined),
            ),
        ],
      ),
      body: LoadingOverlay(
        loading: _busy || _pdfBusy,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : d == null
                ? Column(
                    children: [
                      if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
                      Expanded(
                        child: Center(
                          child: Text(_error ?? 'Not found', style: TextStyle(color: Colors.grey.shade600)),
                        ),
                      ),
                    ],
                  )
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(12, 10, 12, 100),
                      children: [
                        if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
                        Container(
                          padding: const EdgeInsets.all(14),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFFE8EBF3)),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                    decoration: BoxDecoration(
                                      color: (d.isDraft ? const Color(0xFFEF6C00) : const Color(0xFF2E7D32))
                                          .withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      d.isDraft ? 'DRAFT' : d.source,
                                      style: TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w800,
                                        color: d.isDraft ? const Color(0xFFEF6C00) : const Color(0xFF2E7D32),
                                      ),
                                    ),
                                  ),
                                  const Spacer(),
                                  Text(d.voucherDate, style: TextStyle(color: Colors.grey.shade600)),
                                ],
                              ),
                              if (d.referenceNo.isNotEmpty) ...[
                                const SizedBox(height: 8),
                                Text('Ref ${d.referenceNo}', style: const TextStyle(fontWeight: FontWeight.w600)),
                              ],
                              if (d.narration.isNotEmpty) ...[
                                const SizedBox(height: 6),
                                Text(d.narration, style: TextStyle(color: Colors.grey.shade800, height: 1.35)),
                              ],
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: _AmtBox(label: 'Debit', value: d.totalDebit, color: const Color(0xFFC62828)),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: _AmtBox(label: 'Credit', value: d.totalCredit, color: const Color(0xFF2E7D32)),
                                  ),
                                ],
                              ),
                              if (d.reversalVoucherNo.isNotEmpty) ...[
                                const SizedBox(height: 10),
                                Text(
                                  'Reversed by ${d.reversalVoucherNo}',
                                  style: const TextStyle(color: Color(0xFFC62828), fontWeight: FontWeight.w600),
                                ),
                              ],
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          '${d.lines.length} lines',
                          style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                        ),
                        const SizedBox(height: 8),
                        for (final ln in d.lines) _LineCard(line: ln),
                        if (d.canReverse) ...[
                          const SizedBox(height: 16),
                          OutlinedButton.icon(
                            onPressed: _busy ? null : _confirmReverse,
                            icon: const Icon(Icons.undo_rounded),
                            label: const Text('Reverse journal'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: const Color(0xFFC62828),
                              side: const BorderSide(color: Color(0xFFEF9A9A)),
                              minimumSize: const Size.fromHeight(44),
                            ),
                          ),
                        ],
                        if (d.canEdit) ...[
                          const SizedBox(height: 10),
                          FilledButton.icon(
                            onPressed: _busy ? null : _edit,
                            icon: const Icon(Icons.edit_outlined),
                            label: Text(d.isDraft ? 'Edit draft' : 'Edit journal'),
                            style: FilledButton.styleFrom(
                              backgroundColor: _accent,
                              minimumSize: const Size.fromHeight(44),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
      ),
    );
  }
}

class _AmtBox extends StatelessWidget {
  const _AmtBox({required this.label, required this.value, required this.color});

  final String label;
  final double value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
          Text(fmtMoney(value), style: TextStyle(fontWeight: FontWeight.w800, color: color)),
        ],
      ),
    );
  }
}

class _LineCard extends StatelessWidget {
  const _LineCard({required this.line});

  final JeLine line;

  @override
  Widget build(BuildContext context) {
    final party = [
      if (line.partyType.isNotEmpty) line.partyType,
      if (line.partyCode.isNotEmpty) line.partyCode,
      if (line.partyName.isNotEmpty) line.partyName,
    ].join(' ');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            line.accountName.isNotEmpty ? '${line.accountCode} — ${line.accountName}' : line.accountCode,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
          ),
          if (line.remarks.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(line.remarks, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700)),
          ],
          if (party.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(party, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  line.debit > 0 ? 'Dr ${fmtMoney(line.debit)}' : '—',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: line.debit > 0 ? const Color(0xFFC62828) : Colors.grey.shade400,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  line.credit > 0 ? 'Cr ${fmtMoney(line.credit)}' : '—',
                  textAlign: TextAlign.end,
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: line.credit > 0 ? const Color(0xFF2E7D32) : Colors.grey.shade400,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
