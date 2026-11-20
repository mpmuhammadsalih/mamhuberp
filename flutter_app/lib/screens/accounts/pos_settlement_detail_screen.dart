import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/pos_settlement_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../core/theme/app_theme.dart';

class PosSettlementDetailScreen extends StatefulWidget {
  const PosSettlementDetailScreen({super.key, required this.draftId});

  final int draftId;

  @override
  State<PosSettlementDetailScreen> createState() => _PosSettlementDetailScreenState();
}

class _PosSettlementDetailScreenState extends State<PosSettlementDetailScreen> {
  static const _accent = Color(0xFF5E35B1);
  static const _navy = Color(0xFF262C50);

  bool _loading = true;
  bool _busy = false;
  bool _changed = false;
  String? _error;
  Object? _errorCause;
  PosSettlementDraftDetail? _detail;
  List<PosSettlementBill> _bills = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final result = await context.read<PosSettlementService>().getDraft(widget.draftId);
      if (!mounted) return;
      setState(() {
        _detail = result.detail;
        _bills = result.bills;
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

  Future<void> _verify() async {
    setState(() => _busy = true);
    try {
      final d = await context.read<PosSettlementService>().verifyDraft(widget.draftId);
      if (!mounted) return;
      setState(() {
        _detail = d;
        _changed = true;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settlement verified.'), behavior: SnackBarBehavior.floating),
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel draft?'),
        content: const Text('Bills will stay pending for a new settlement.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Cancel draft')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final d = await context.read<PosSettlementService>().cancelDraft(widget.draftId);
      if (!mounted) return;
      setState(() {
        _detail = d;
        _changed = true;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settlement cancelled.'), behavior: SnackBarBehavior.floating),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _post() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Post settlement?'),
        content: const Text('This posts the GL journal and marks bills as settled.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Back')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Post')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final result = await context.read<PosSettlementService>().postDraft(
            widget.draftId,
            voucherDate: _detail?.voucherDate ?? '',
          );
      if (!mounted) return;
      setState(() {
        _detail = result.detail;
        _changed = true;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.voucherNo.isNotEmpty
                ? 'Posted · voucher ${result.voucherNo}'
                : 'Settlement posted.',
          ),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _money(double v) => v.toStringAsFixed(2);

  @override
  Widget build(BuildContext context) {
    final d = _detail;
    final status = d?.status ?? '';
    final canVerify = status == 'DRAFT';
    final canPost = status == 'VERIFIED';
    final canCancel = status == 'DRAFT' || status == 'VERIFIED';

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).pop(_changed),
        ),
        title: Text(
          d?.referenceNo.isNotEmpty == true ? d!.referenceNo : 'Settlement #${widget.draftId}',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        centerTitle: true,
      ),
      bottomNavigationBar: d == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                child: Row(
                  children: [
                    if (canCancel)
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _busy ? null : _cancel,
                          child: const Text('Cancel'),
                        ),
                      ),
                    if (canCancel && (canVerify || canPost)) const SizedBox(width: 8),
                    if (canVerify)
                      Expanded(
                        child: FilledButton(
                          onPressed: _busy ? null : _verify,
                          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF1565C0)),
                          child: const Text('Verify'),
                        ),
                      ),
                    if (canPost)
                      Expanded(
                        child: FilledButton(
                          onPressed: _busy ? null : _post,
                          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF2E7D32)),
                          child: const Text('Post'),
                        ),
                      ),
                  ],
                ),
              ),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : Column(
              children: [
                if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
                if (d != null)
                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
                      children: [
                        _card(
                          children: [
                            _kv('Status', d.status),
                            if (d.voucherNo.isNotEmpty) _kv('Voucher', d.voucherNo),
                            if (d.voucherDate.isNotEmpty) _kv('Voucher date', d.voucherDate),
                            _kv('Bills', '${d.billNos.length}'),
                            if (d.narration.isNotEmpty) _kv('Narration', d.narration),
                          ],
                        ),
                        const SizedBox(height: 12),
                        const Text('Journal lines', style: TextStyle(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 8),
                        if (d.journalLines.isEmpty)
                          Text('No journal lines.', style: TextStyle(color: Colors.grey.shade600))
                        else
                          ...d.journalLines.map((ln) {
                            final code = '${ln['account_code'] ?? ''}'.trim();
                            final debit = _money(_toD(ln['debit']));
                            final credit = _money(_toD(ln['credit']));
                            final remarks = '${ln['remarks'] ?? ''}'.trim();
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: _card(
                                children: [
                                  Text(code, style: const TextStyle(fontWeight: FontWeight.w800, color: _navy)),
                                  if (remarks.isNotEmpty)
                                    Text(remarks, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
                                  const SizedBox(height: 4),
                                  Text('Dr $debit · Cr $credit', style: const TextStyle(fontWeight: FontWeight.w600)),
                                ],
                              ),
                            );
                          }),
                        const SizedBox(height: 12),
                        const Text('Bills', style: TextStyle(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 8),
                        if (_bills.isEmpty)
                          Text(
                            d.billNos.map((e) => '#$e').join(', '),
                            style: TextStyle(color: Colors.grey.shade700),
                          )
                        else
                          ..._bills.map(
                            (b) => Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: _card(
                                children: [
                                  Text(
                                    '#${b.billNo} · ${_money(b.netAmount)}',
                                    style: const TextStyle(fontWeight: FontWeight.w700),
                                  ),
                                  Text(
                                    [
                                      if (b.billDate.isNotEmpty) b.billDate,
                                      if (b.customerName.isNotEmpty) b.customerName,
                                    ].join(' · '),
                                    style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                                  ),
                                ],
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
              ],
            ),
    );
  }

  double _toD(dynamic v) {
    if (v is num) return v.toDouble();
    return double.tryParse('$v'.replaceAll(',', '')) ?? 0;
  }

  Widget _card({required List<Widget> children}) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE8EBF3)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 110, child: Text(k, style: TextStyle(color: Colors.grey.shade600))),
          Expanded(child: Text(v, style: const TextStyle(fontWeight: FontWeight.w700, color: _navy))),
        ],
      ),
    );
  }
}
