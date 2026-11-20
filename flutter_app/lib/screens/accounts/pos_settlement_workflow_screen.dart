import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/ui/confirm_save.dart';
import '../../services/pos_settlement_service.dart';
import '../../widgets/api_error_banner.dart';
import 'pos_settlement_detail_screen.dart';
import '../../core/theme/app_theme.dart';

/// Create POS settlement draft: pick date → bills → counted tenders → save.
class PosSettlementWorkflowScreen extends StatefulWidget {
  const PosSettlementWorkflowScreen({super.key, this.initialDate});

  final String? initialDate;

  @override
  State<PosSettlementWorkflowScreen> createState() => _PosSettlementWorkflowScreenState();
}

class _PosSettlementWorkflowScreenState extends State<PosSettlementWorkflowScreen> {
  static const _accent = Color(0xFF5E35B1);
  static const _navy = Color(0xFF262C50);

  String _date = '';
  bool _loading = true;
  bool _saving = false;
  String? _error;
  Object? _errorCause;
  PosSettlementOpenContext? _ctx;
  List<PosSettlementBill> _bills = [];
  final Set<String> _selected = {};
  final Map<String, TextEditingController> _counted = {};
  List<PosPaymodeLine> _payLines = [];

  @override
  void initState() {
    super.initState();
    _date = (widget.initialDate ?? '').trim();
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    for (final c in _counted.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _bootstrap() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<PosSettlementService>();
      final ctx = await svc.getOpenContext();
      if (!mounted) return;
      if (_date.isEmpty) {
        // Prefer a day that still has pending bills over closed POS day with none.
        var pick = ctx.defaultDate.trim();
        try {
          final days = await svc.listPendingByDate(limit: 1);
          if (days.isNotEmpty && days.first.billDate.isNotEmpty) {
            pick = days.first.billDate;
          }
        } catch (_) {}
        _date = pick;
      }
      setState(() => _ctx = ctx);
      await _loadBills();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _loadBills() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<PosSettlementService>();
      final bills = await svc.listBills(fromDate: _date, toDate: _date, settlementScope: 'pending');
      if (!mounted) return;
      _selected
        ..clear()
        ..addAll(bills.map((b) => b.billNo));
      setState(() {
        _bills = bills;
        _loading = false;
      });
      await _refreshPaymodes();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _bills = [];
        _loading = false;
      });
    }
  }

  Future<void> _refreshPaymodes() async {
    final nos = _selected.toList()..sort();
    if (nos.isEmpty) {
      setState(() => _payLines = []);
      return;
    }
    try {
      final lines = await context.read<PosSettlementService>().paymentModeSummary(nos);
      if (!mounted) return;
      for (final c in _counted.values) {
        c.dispose();
      }
      _counted.clear();
      for (final line in lines) {
        _counted[line.code] = TextEditingController(text: line.amount.toStringAsFixed(2));
      }
      setState(() => _payLines = lines);
    } catch (_) {
      if (mounted) setState(() => _payLines = []);
    }
  }

  Future<void> _pickDate() async {
    final now = DateTime.tryParse(_date) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(now.year - 2),
      lastDate: DateTime(now.year + 1),
    );
    if (picked == null) return;
    setState(() {
      _date =
          '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
    });
    await _loadBills();
  }

  Future<void> _saveDraft() async {
    final nos = _selected.toList()..sort();
    if (nos.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select at least one bill.')),
      );
      return;
    }
    final accounts = Map<String, String>.from(_ctx?.accounts ?? {});
    if ((accounts['sales_acc'] ?? '').isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Sales account is not configured for POS settlement.')),
      );
      return;
    }
    final rows = <Map<String, dynamic>>[];
    double sumAct = 0;
    double sumOpen = 0;
    double sumExp = 0;
    for (final line in _payLines) {
      final ctrl = _counted[line.code];
      final actual = double.tryParse((ctrl?.text ?? '').replaceAll(',', '').trim()) ?? 0;
      sumAct += actual;
      rows.add({
        'cashier': 'MOBILE',
        'tender_type': line.label,
        'tender_code': line.code,
        'trans_amount': line.amount,
        'opening_cash': 0,
        'cash_sales': line.code == 'CASH' ? line.amount : 0,
        'cash_return': 0,
        'expenses': 0,
        'closing_system': line.amount,
        'actual_cash': actual,
        'short_excess': actual - line.amount,
        'settlement_balance': line.code == 'CASH' ? actual : line.amount,
      });
    }
    final meta = <String, dynamic>{
      'opening_cash': sumOpen,
      'cash_return': 0,
      'expenses': sumExp,
      'actual_cash': sumAct,
      'cash_variance_sum': 0,
      'settlement_amount_source': 'counted',
      'cashier_settlement_rows': rows,
      'approved_by': '',
      'remarks_panel': 'Mobile POS settlement $_date',
    };

    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save settlement draft?',
      message: 'Save POS settlement draft for $_date with ${nos.length} bill(s)?',
      confirmLabel: 'Save draft',
    );
    if (!confirmed || !mounted) return;

    setState(() => _saving = true);
    try {
      final detail = await context.read<PosSettlementService>().generateDraft(
            billNos: nos,
            accounts: accounts,
            meta: meta,
          );
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute<bool>(
          builder: (_) => PosSettlementDetailScreen(draftId: detail.draftId),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _money(double v) => v.toStringAsFixed(2);

  @override
  Widget build(BuildContext context) {
    final selectedNet = _bills.where((b) => _selected.contains(b.billNo)).fold<double>(0, (s, b) => s + b.netAmount);

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('New Settlement', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          TextButton(
            onPressed: _saving ? null : _pickDate,
            child: Text(_date.isEmpty ? 'Date' : _date, style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: FilledButton.icon(
            onPressed: _saving || _loading ? null : _saveDraft,
            style: FilledButton.styleFrom(
              backgroundColor: _accent,
              minimumSize: const Size.fromHeight(48),
            ),
            icon: _saving
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.save_outlined),
            label: Text(_saving ? 'Saving…' : 'Save Draft'),
          ),
        ),
      ),
      body: Column(
        children: [
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
          Material(
            color: Colors.white,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '${_selected.length}/${_bills.length} selected · ${_money(selectedNet)}',
                      style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade700),
                    ),
                  ),
                  TextButton(
                    onPressed: _bills.isEmpty
                        ? null
                        : () async {
                            setState(() {
                              if (_selected.length == _bills.length) {
                                _selected.clear();
                              } else {
                                _selected
                                  ..clear()
                                  ..addAll(_bills.map((b) => b.billNo));
                              }
                            });
                            await _refreshPaymodes();
                          },
                    child: Text(_selected.length == _bills.length && _bills.isNotEmpty ? 'Clear' : 'Select all'),
                  ),
                ],
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: _accent))
                : ListView(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
                    children: [
                      if (_payLines.isNotEmpty) ...[
                        const Text('Counted tenders', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                        const SizedBox(height: 8),
                        ..._payLines.map((line) {
                          final ctrl = _counted[line.code];
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Material(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              child: Padding(
                                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            line.label.isNotEmpty ? line.label : line.code,
                                            style: const TextStyle(fontWeight: FontWeight.w700),
                                          ),
                                          Text(
                                            'Expected ${_money(line.amount)}',
                                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                          ),
                                        ],
                                      ),
                                    ),
                                    SizedBox(
                                      width: 110,
                                      child: TextField(
                                        controller: ctrl,
                                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                        inputFormatters: [
                                          FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
                                        ],
                                        decoration: const InputDecoration(
                                          isDense: true,
                                          labelText: 'Counted',
                                          border: OutlineInputBorder(),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        }),
                        const SizedBox(height: 12),
                      ],
                      const Text('Bills', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                      const SizedBox(height: 8),
                      if (_bills.isEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 40),
                          child: Center(
                            child: Text('No pending bills for $_date.', style: TextStyle(color: Colors.grey.shade600)),
                          ),
                        )
                      else
                        ..._bills.map((b) {
                          final on = _selected.contains(b.billNo);
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Material(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              child: CheckboxListTile(
                                value: on,
                                activeColor: _accent,
                                controlAffinity: ListTileControlAffinity.leading,
                                title: Text(
                                  '#${b.billNo} · ${_money(b.netAmount)}',
                                  style: const TextStyle(fontWeight: FontWeight.w700, color: _navy),
                                ),
                                subtitle: Text(
                                  [
                                    if (b.customerName.isNotEmpty) b.customerName,
                                    if (b.paymentMode.isNotEmpty) b.paymentMode,
                                  ].join(' · '),
                                ),
                                onChanged: (v) async {
                                  setState(() {
                                    if (v == true) {
                                      _selected.add(b.billNo);
                                    } else {
                                      _selected.remove(b.billNo);
                                    }
                                  });
                                  await _refreshPaymodes();
                                },
                              ),
                            ),
                          );
                        }),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
