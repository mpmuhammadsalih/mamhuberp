import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/ar_ap_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/numeric_text_field.dart';
import 'ar_ap_list_screen.dart';
import '../../core/theme/app_theme.dart';

class ArApPostScreen extends StatefulWidget {
  const ArApPostScreen({super.key, required this.kind, required this.partyCode});

  final ArApKind kind;
  final String partyCode;

  @override
  State<ArApPostScreen> createState() => _ArApPostScreenState();
}

class _ArApPostScreenState extends State<ArApPostScreen> {
  static const _bg = Color(0xFFF4F5F8);

  bool _loading = true;
  bool _submitting = false;
  String? _error;
  Object? _errorCause;

  ArApPartyDetail? _detail;
  List<ArApCashBankAccount> _cashBanks = [];
  String _paymentDate = '';
  ArApCashBankAccount? _cashBank;
  final _reference = TextEditingController();
  final _remarks = TextEditingController();
  final _discount = TextEditingController(text: '0');

  /// voucher_no -> allocate amount (positive); supports full or partial.
  final Map<String, double> _alloc = {};
  final Map<String, TextEditingController> _allocCtrls = {};

  bool get _isAr => widget.kind == ArApKind.receivable;
  Color get _accent => _isAr ? const Color(0xFF1565C0) : const Color(0xFF6A1B9A);
  String get _title => _isAr ? 'Customer Receipt' : 'Supplier Payment';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _reference.dispose();
    _remarks.dispose();
    _discount.dispose();
    for (final c in _allocCtrls.values) {
      c.dispose();
    }
    _allocCtrls.clear();
    super.dispose();
  }

  double _capFor(ArApOpenDoc doc) {
    final cap = doc.isCredit ? doc.openAmount.abs() : doc.openAmount;
    return cap < 0 ? 0 : double.parse(cap.toStringAsFixed(2));
  }

  void _clearAllocControllers() {
    for (final c in _allocCtrls.values) {
      c.dispose();
    }
    _allocCtrls.clear();
    _alloc.clear();
  }

  void _selectDoc(ArApOpenDoc doc, {double? amount}) {
    final cap = _capFor(doc);
    if (cap <= 0) return;
    final amt = (amount ?? cap).clamp(0.0, cap).toDouble();
    final rounded = double.parse(amt.toStringAsFixed(2));
    _alloc[doc.voucherNo] = rounded;
    final ctrl = _allocCtrls.putIfAbsent(
      doc.voucherNo,
      () => TextEditingController(text: _fmt(rounded)),
    );
    if (ctrl.text != _fmt(rounded)) {
      ctrl.text = _fmt(rounded);
    }
  }

  void _deselectDoc(String voucherNo) {
    _alloc.remove(voucherNo);
    _allocCtrls.remove(voucherNo)?.dispose();
  }

  void _setPartialAmount(ArApOpenDoc doc, double raw) {
    final cap = _capFor(doc);
    if (raw <= 0) {
      // Keep row selected while clearing; commit/clear chip removes it.
      _alloc[doc.voucherNo] = 0;
      return;
    }
    _alloc[doc.voucherNo] = double.parse((raw > cap ? cap : raw).toStringAsFixed(2));
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<ArApService>();
      final ctx = _isAr
          ? await svc.getReceiptOpen(widget.partyCode)
          : await svc.getPaymentOpen(widget.partyCode);
      if (!mounted) return;
      _clearAllocControllers();
      for (final d in ctx.detail.openDocuments) {
        if (d.voucherNo.isEmpty) continue;
        // Pre-select payable docs at full open; user can lower for partial.
        if (d.isPayable && d.openAmount > 0) {
          _selectDoc(d);
        }
      }
      setState(() {
        _detail = ctx.detail;
        _cashBanks = ctx.cashBankAccounts;
        _paymentDate = ctx.paymentDate.isNotEmpty
            ? ctx.paymentDate
            : DateTime.now().toIso8601String().substring(0, 10);
        _cashBank = ctx.cashBankAccounts.isNotEmpty ? ctx.cashBankAccounts.first : null;
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

  double get _invoiceTotal {
    final d = _detail;
    if (d == null) return 0;
    var t = 0.0;
    for (final doc in d.openDocuments) {
      if (doc.isCredit) continue;
      t += _alloc[doc.voucherNo] ?? 0;
    }
    return double.parse(t.toStringAsFixed(2));
  }

  double get _creditTotal {
    final d = _detail;
    if (d == null) return 0;
    var t = 0.0;
    for (final doc in d.openDocuments) {
      if (!doc.isCredit) continue;
      t += _alloc[doc.voucherNo] ?? 0;
    }
    return double.parse(t.toStringAsFixed(2));
  }

  double get _discountAmt {
    final v = double.tryParse(_discount.text.trim()) ?? 0;
    return v < 0 ? 0 : double.parse(v.toStringAsFixed(2));
  }

  double get _netCash {
    final n = _invoiceTotal - _creditTotal - _discountAmt;
    return n < 0 ? 0 : double.parse(n.toStringAsFixed(2));
  }

  String _fmt(double v) => v.toStringAsFixed(2);

  Future<void> _pickDate() async {
    final initial = DateTime.tryParse(_paymentDate) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _paymentDate =
          '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
    });
  }

  Future<void> _pickCashBank() async {
    if (_cashBanks.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No Cash/Bank accounts found in Chart of Accounts.')),
      );
      return;
    }
    final picked = await showModalBottomSheet<ArApCashBankAccount>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: SizedBox(
            height: MediaQuery.of(ctx).size.height * 0.55,
            child: Column(
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(16, 14, 16, 8),
                  child: Text('Cash / Bank account', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                ),
                Expanded(
                  child: ListView.builder(
                    itemCount: _cashBanks.length,
                    itemBuilder: (_, i) {
                      final a = _cashBanks[i];
                      final selected = _cashBank?.code == a.code;
                      return ListTile(
                        title: Text(a.label),
                        trailing: selected ? Icon(Icons.check_rounded, color: _accent) : null,
                        onTap: () => Navigator.of(ctx).pop(a),
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
    if (picked == null || !mounted) return;
    setState(() => _cashBank = picked);
  }

  void _toggleDoc(ArApOpenDoc doc) {
    setState(() {
      if (_alloc.containsKey(doc.voucherNo)) {
        _deselectDoc(doc.voucherNo);
      } else {
        _selectDoc(doc);
      }
    });
  }

  void _applyQuickAmount(ArApOpenDoc doc, double amount) {
    setState(() => _selectDoc(doc, amount: amount));
  }

  void _onAllocTextChanged(ArApOpenDoc doc, String text) {
    final raw = double.tryParse(text.trim());
    if (raw == null) return;
    setState(() => _setPartialAmount(doc, raw));
  }

  void _commitAllocField(ArApOpenDoc doc) {
    final ctrl = _allocCtrls[doc.voucherNo];
    if (ctrl == null) return;
    final cap = _capFor(doc);
    final raw = double.tryParse(ctrl.text.trim()) ?? 0;
    setState(() {
      if (raw <= 0) {
        _deselectDoc(doc.voucherNo);
        return;
      }
      final amt = double.parse((raw > cap ? cap : raw).toStringAsFixed(2));
      _alloc[doc.voucherNo] = amt;
      ctrl.text = _fmt(amt);
    });
  }

  Future<void> _submit() async {
    final d = _detail;
    if (d == null) return;
    // Commit any in-progress amount fields before validate/post.
    for (final doc in d.openDocuments) {
      if (_allocCtrls.containsKey(doc.voucherNo)) {
        _commitAllocField(doc);
      }
    }
    final activeAlloc = Map<String, double>.fromEntries(
      _alloc.entries.where((e) => e.value > 0.009),
    );
    if (activeAlloc.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a full or partial amount on at least one document.')),
      );
      return;
    }
    if (_creditTotal > _invoiceTotal + 0.009) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Credits applied cannot exceed selected invoices.')),
      );
      return;
    }
    final maxDisc = (_invoiceTotal - _creditTotal).clamp(0.0, double.infinity);
    if (_discountAmt > maxDisc + 0.009) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Discount cannot exceed ${_fmt(maxDisc)}.')),
      );
      return;
    }
    if (_netCash > 0 && (_cashBank == null || _cashBank!.code.isEmpty)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select a Cash/Bank account.')),
      );
      return;
    }

    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(_isAr ? 'Post receipt?' : 'Post payment?'),
        content: Text(
          'Net cash: ${_fmt(_netCash)}\n'
          'Invoices: ${_fmt(_invoiceTotal)}  ·  Credits: ${_fmt(_creditTotal)}\n'
          'This posts to GL like ERP.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: _accent),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Post'),
          ),
        ],
      ),
    );
    if (confirm != true || !mounted) return;

    setState(() => _submitting = true);
    try {
      final allocations = activeAlloc.entries
          .map((e) => {
                'invoice_voucher_no': e.key,
                'allocate_amount': e.value,
              })
          .toList();
      final body = <String, dynamic>{
        'payment_date': _paymentDate,
        'cash_bank_account': _cashBank?.code ?? '',
        'reference_no': _reference.text.trim(),
        'remarks': _remarks.text.trim(),
        'discount_amount': _discountAmt,
        'allocations': allocations,
        if (_isAr) 'collected_amount': _netCash,
        if (!_isAr) 'amount': _netCash,
      };
      final svc = context.read<ArApService>();
      final result = _isAr
          ? await svc.postReceivableReceipt(customerCode: widget.partyCode, body: body)
          : await svc.postPayablePayment(supplierCode: widget.partyCode, body: body);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => _ArApPostedDialog(
          kind: widget.kind,
          result: result,
          accent: _accent,
        ),
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
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
        title: Text(_title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      ),
      body: _loading
          ? Center(child: CircularProgressIndicator(color: _accent))
          : _error != null && d == null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : d == null
                  ? const Center(child: Text('Not found.'))
                  : Column(
                      children: [
                        Expanded(
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(14, 10, 14, 16),
                            children: [
                              _partyHeader(d),
                              const SizedBox(height: 12),
                              _fieldCard(),
                              const SizedBox(height: 12),
                              Text(
                                'Open documents',
                                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Colors.grey.shade800),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Select a document, then enter a full or partial amount.',
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                              ),
                              const SizedBox(height: 8),
                              if (d.openDocuments.isEmpty)
                                _emptyDocs()
                              else
                                ...d.openDocuments.map(_docTile),
                            ],
                          ),
                        ),
                        _footerBar(),
                      ],
                    ),
    );
  }

  Widget _partyHeader(ArApPartyDetail d) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(d.partyName, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: Color(0xFF262C50))),
          const SizedBox(height: 2),
          Text(
            '${d.partyCode}${d.glAccount.isNotEmpty ? ' · A/C ${d.glAccount}' : ''}',
            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
          ),
          const SizedBox(height: 8),
          Text(
            'Balance ${_fmt(d.balance)}',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: _accent),
          ),
        ],
      ),
    );
  }

  Widget _fieldCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        children: [
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Payment date', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            subtitle: Text(_paymentDate, style: const TextStyle(fontWeight: FontWeight.w700)),
            trailing: Icon(Icons.calendar_month_outlined, color: _accent),
            onTap: _submitting ? null : _pickDate,
          ),
          const Divider(height: 1),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Cash / Bank', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            subtitle: Text(
              _cashBank?.label ?? 'Select account',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: _cashBank == null ? Colors.grey : const Color(0xFF262C50),
              ),
            ),
            trailing: Icon(Icons.account_balance_outlined, color: _accent),
            onTap: _submitting ? null : _pickCashBank,
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _reference,
            enabled: !_submitting,
            decoration: const InputDecoration(
              labelText: 'Reference',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _remarks,
            enabled: !_submitting,
            maxLines: 2,
            decoration: const InputDecoration(
              labelText: 'Remarks',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
          const SizedBox(height: 10),
          IgnorePointer(
            ignoring: _submitting,
            child: NumericTextField(
              controller: _discount,
              decoration: const InputDecoration(
                labelText: 'Settlement discount',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              onChanged: (_) => setState(() {}),
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyDocs() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)),
      child: Text('No open documents to allocate.', textAlign: TextAlign.center, style: TextStyle(color: Colors.grey.shade600)),
    );
  }

  Widget _docTile(ArApOpenDoc doc) {
    final selected = _alloc.containsKey(doc.voucherNo);
    final cap = _capFor(doc);
    final amt = _alloc[doc.voucherNo];
    final isPartial = selected && amt != null && (amt - cap).abs() > 0.009;
    final ctrl = _allocCtrls[doc.voucherNo];

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? _accent : const Color(0xFFE8EBF3),
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            InkWell(
              onTap: _submitting ? null : () => _toggleDoc(doc),
              child: Row(
                children: [
                  Icon(
                    selected ? Icons.check_circle_rounded : Icons.circle_outlined,
                    color: selected ? _accent : Colors.grey.shade400,
                    size: 22,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(doc.voucherNo, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5)),
                        Text(
                          [
                            if (doc.voucherDate.isNotEmpty) doc.voucherDate,
                            doc.isCredit ? 'Credit' : 'Invoice',
                            'Open ${_fmt(cap)}',
                          ].join(' · '),
                          style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                        ),
                      ],
                    ),
                  ),
                  if (isPartial)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: _accent.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        'Partial',
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: _accent),
                      ),
                    ),
                ],
              ),
            ),
            if (selected && ctrl != null) ...[
              const SizedBox(height: 10),
              IgnorePointer(
                ignoring: _submitting,
                child: NumericTextField(
                  controller: ctrl,
                  decoration: InputDecoration(
                    labelText: 'Allocate amount (max ${_fmt(cap)})',
                    helperText: isPartial
                        ? 'Partial: ${_fmt(amt)} of ${_fmt(cap)} remaining open'
                        : 'Full open amount selected — change for partial',
                    border: const OutlineInputBorder(),
                    isDense: true,
                    suffixIcon: IconButton(
                      tooltip: 'Apply',
                      icon: Icon(Icons.check_rounded, color: _accent, size: 20),
                      onPressed: _submitting ? null : () => _commitAllocField(doc),
                    ),
                  ),
                  onChanged: (t) => _onAllocTextChanged(doc, t),
                  textInputAction: TextInputAction.done,
                ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  ActionChip(
                    label: const Text('Full', style: TextStyle(fontSize: 12)),
                    onPressed: _submitting ? null : () => _applyQuickAmount(doc, cap),
                  ),
                  if (cap > 0.02)
                    ActionChip(
                      label: const Text('Half', style: TextStyle(fontSize: 12)),
                      onPressed: _submitting
                          ? null
                          : () => _applyQuickAmount(doc, double.parse((cap / 2).toStringAsFixed(2))),
                    ),
                  ActionChip(
                    label: const Text('Clear', style: TextStyle(fontSize: 12)),
                    onPressed: _submitting ? null : () => setState(() => _deselectDoc(doc.voucherNo)),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _footerBar() {
    return Material(
      color: Colors.white,
      elevation: 8,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Inv ${_fmt(_invoiceTotal)} · Cr ${_fmt(_creditTotal)} · Disc ${_fmt(_discountAmt)}',
                      style: TextStyle(fontSize: 11.5, color: Colors.grey.shade700),
                    ),
                  ),
                  Text(
                    'Net ${_fmt(_netCash)}',
                    style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16, color: _accent),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: _accent,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: _submitting ? null : _submit,
                  icon: _submitting
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.publish_rounded),
                  label: Text(_submitting ? 'Posting…' : (_isAr ? 'Post receipt' : 'Post payment')),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ArApPostedDialog extends StatefulWidget {
  const _ArApPostedDialog({
    required this.kind,
    required this.result,
    required this.accent,
  });

  final ArApKind kind;
  final ArApPostResult result;
  final Color accent;

  @override
  State<_ArApPostedDialog> createState() => _ArApPostedDialogState();
}

class _ArApPostedDialogState extends State<_ArApPostedDialog> {
  bool _pdfBusy = false;
  String? _pdfError;
  bool _autoOpened = false;

  bool get _isAr => widget.kind == ArApKind.receivable;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _autoOpenPdf());
  }

  Future<void> _autoOpenPdf() async {
    if (_autoOpened || !mounted) return;
    _autoOpened = true;
    await _openPdf();
  }

  Future<File> _writePdfFile() async {
    final svc = context.read<ArApService>();
    final bytes = _isAr
        ? await svc.downloadReceivableReceiptPdf(widget.result.voucherNo)
        : await svc.downloadPayablePaymentPdf(widget.result.voucherNo);
    final dir = await getTemporaryDirectory();
    final safe = widget.result.voucherNo.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final prefix = _isAr ? 'AR_Receipt' : 'AP_Payment';
    final file = File('${dir.path}/${prefix}_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _openPdf() async {
    if (_pdfBusy) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final file = await _writePdfFile();
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        setState(() {
          _pdfError = opened.message.isNotEmpty ? opened.message : 'Could not open PDF.';
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _pdfError = handleApiError(context, e, authenticatedContext: true));
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy) return;
    setState(() {
      _pdfBusy = true;
      _pdfError = null;
    });
    try {
      final file = await _writePdfFile();
      final subject = _isAr
          ? 'Customer Receipt ${widget.result.voucherNo}'
          : 'Supplier Payment ${widget.result.voucherNo}';
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: subject,
        text: subject,
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
    final accent = widget.accent;
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
            Text(
              _isAr ? 'Receipt posted' : 'Payment posted',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Color(0xFF262C50)),
            ),
            const SizedBox(height: 6),
            Text(
              result.voucherNo,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: accent, height: 1.1),
            ),
            const SizedBox(height: 8),
            Text(
              'Net cash ${result.netCash.toStringAsFixed(2)}',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
            ),
            if (_pdfBusy) ...[
              const SizedBox(height: 14),
              Text('Preparing PDF…', style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
            ],
            if (_pdfError != null) ...[
              const SizedBox(height: 10),
              Text(
                _pdfError!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12.5, color: Color(0xFFC62828)),
              ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _pdfBusy ? null : _openPdf,
                icon: const Icon(Icons.picture_as_pdf_outlined),
                label: Text(_pdfBusy ? 'Preparing…' : 'Open PDF'),
                style: FilledButton.styleFrom(
                  backgroundColor: accent,
                  padding: const EdgeInsets.symmetric(vertical: 13),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _pdfBusy ? null : _sharePdf,
                icon: const Icon(Icons.share_outlined),
                label: const Text('Share PDF'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: accent,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
            const SizedBox(height: 6),
            TextButton(
              onPressed: _pdfBusy ? null : () => Navigator.of(context).pop(),
              child: const Text('Done'),
            ),
          ],
        ),
      ),
    );
  }
}
