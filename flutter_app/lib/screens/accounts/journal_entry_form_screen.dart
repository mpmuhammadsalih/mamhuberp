import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../core/ui/confirm_save.dart';
import '../../providers/auth_provider.dart';
import '../../services/journal_entry_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/numeric_text_field.dart';
import 'accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

class _JeFormLine {
  _JeFormLine({
    this.accountCode = '',
    this.accountName = '',
    this.debit = 0,
    this.credit = 0,
    this.remarks = '',
    this.partyType = '',
    this.partyCode = '',
    this.partyName = '',
  });

  String accountCode;
  String accountName;
  double debit;
  double credit;
  String remarks;
  String partyType;
  String partyCode;
  String partyName;

  final remarksCtrl = TextEditingController();
  final debitCtrl = TextEditingController();
  final creditCtrl = TextEditingController();

  void dispose() {
    remarksCtrl.dispose();
    debitCtrl.dispose();
    creditCtrl.dispose();
  }
}

class JournalEntryFormScreen extends StatefulWidget {
  const JournalEntryFormScreen({super.key, this.editDocId, this.restoreDraft = false});

  final String? editDocId;
  final bool restoreDraft;

  @override
  State<JournalEntryFormScreen> createState() => _JournalEntryFormScreenState();
}

class _JournalEntryFormScreenState extends State<JournalEntryFormScreen> with WidgetsBindingObserver {
  static const _accent = Color(0xFF6A1B9A);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  bool _loading = true;
  bool _submitting = false;
  String? _loadError;
  Object? _loadErrorCause;

  String _draftId = '';
  String _editVoucherNo = '';
  late DateTime _voucherDate;
  String _defaultRecv = '1200';
  String _defaultPay = '2110';

  final _reference = TextEditingController();
  final _narration = TextEditingController();
  final List<_JeFormLine> _lines = [];

  Timer? _localDraftDebounce;
  String _localDraftTenantId = '';
  String _localDraftUsername = '';
  bool _localDraftCleared = false;

  bool get _isEditing => (widget.editDocId ?? '').trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final now = DateTime.now();
    _voucherDate = DateTime(now.year, now.month, now.day);
    _reference.addListener(_scheduleLocalDraftSave);
    _narration.addListener(_scheduleLocalDraftSave);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = context.read<AuthProvider>().user;
      _localDraftTenantId = user?.tenantId ?? '';
      _localDraftUsername = user?.username ?? '';
      _load();
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.inactive) {
      _persistLocalDraft();
    }
  }

  @override
  void dispose() {
    _persistLocalDraft();
    WidgetsBinding.instance.removeObserver(this);
    _reference.removeListener(_scheduleLocalDraftSave);
    _narration.removeListener(_scheduleLocalDraftSave);
    _localDraftDebounce?.cancel();
    _reference.dispose();
    _narration.dispose();
    for (final l in _lines) {
      l.dispose();
    }
    super.dispose();
  }

  double get _totalDebit => _lines.fold(0.0, (s, l) => s + l.debit);
  double get _totalCredit => _lines.fold(0.0, (s, l) => s + l.credit);
  double get _difference => (_totalDebit - _totalCredit);
  bool get _balanced => (_totalDebit - _totalCredit).abs() < 0.005 && _totalDebit > 0;

  void _scheduleLocalDraftSave() {
    if (_isEditing || _localDraftCleared || _loading || _submitting) return;
    _localDraftDebounce?.cancel();
    _localDraftDebounce = Timer(const Duration(milliseconds: 400), _persistLocalDraft);
  }

  bool get _hasMeaningfulLocalDraft {
    if (_reference.text.trim().isNotEmpty || _narration.text.trim().isNotEmpty) return true;
    for (final l in _lines) {
      if (l.accountCode.trim().isNotEmpty) return true;
      if (l.debit > 0 || l.credit > 0) return true;
      if (l.remarksCtrl.text.trim().isNotEmpty) return true;
      if (l.partyCode.trim().isNotEmpty) return true;
    }
    return false;
  }

  void _syncLineAmountsSilent() {
    for (final l in _lines) {
      final dRaw = l.debitCtrl.text.trim().replaceAll(',', '');
      final cRaw = l.creditCtrl.text.trim().replaceAll(',', '');
      l.debit = double.tryParse(dRaw) ?? 0;
      l.credit = double.tryParse(cRaw) ?? 0;
      l.remarks = l.remarksCtrl.text;
    }
  }

  Future<void> _persistLocalDraft() async {
    if (_isEditing || _localDraftCleared || _submitting) return;
    if (!_hasMeaningfulLocalDraft) return;
    if (_localDraftUsername.isEmpty) return;
    _syncLineAmountsSilent();
    final draft = <String, dynamic>{
      'voucher_date': isoDate(_voucherDate),
      'reference': _reference.text,
      'narration': _narration.text,
      'lines': [
        for (final l in _lines)
          {
            'account_code': l.accountCode,
            'account_name': l.accountName,
            'debit': l.debit,
            'credit': l.credit,
            'remarks': l.remarksCtrl.text,
            'party_type': l.partyType,
            'party_code': l.partyCode,
            'party_name': l.partyName,
          },
      ],
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.journalEntry,
      tenantId: _localDraftTenantId,
      username: _localDraftUsername,
      draft: draft,
    );
  }

  Future<void> _clearLocalDraft() async {
    _localDraftCleared = true;
    _localDraftDebounce?.cancel();
    if (_localDraftUsername.isEmpty) return;
    await TransactionDraftStorage.clear(
      docType: TransactionDraftType.journalEntry,
      tenantId: _localDraftTenantId,
      username: _localDraftUsername,
    );
  }

  void _applyLocalDraft(Map<String, dynamic> draft) {
    final dateRaw = '${draft['voucher_date'] ?? ''}'.trim();
    final parsed = DateTime.tryParse(dateRaw);
    if (parsed != null) {
      _voucherDate = DateTime(parsed.year, parsed.month, parsed.day);
    }
    _reference.text = '${draft['reference'] ?? ''}';
    _narration.text = '${draft['narration'] ?? ''}';

    for (final l in _lines) {
      l.dispose();
    }
    _lines.clear();
    final linesRaw = (draft['lines'] as List?) ?? const [];
    for (final raw in linesRaw) {
      if (raw is! Map) continue;
      final m = Map<String, dynamic>.from(raw);
      final debit = (m['debit'] is num) ? (m['debit'] as num).toDouble() : double.tryParse('${m['debit']}') ?? 0;
      final credit = (m['credit'] is num) ? (m['credit'] as num).toDouble() : double.tryParse('${m['credit']}') ?? 0;
      final fl = _JeFormLine(
        accountCode: '${m['account_code'] ?? ''}'.trim(),
        accountName: '${m['account_name'] ?? ''}'.trim(),
        debit: debit,
        credit: credit,
        remarks: '${m['remarks'] ?? ''}',
        partyType: '${m['party_type'] ?? ''}'.trim(),
        partyCode: '${m['party_code'] ?? ''}'.trim(),
        partyName: '${m['party_name'] ?? ''}'.trim(),
      );
      fl.remarksCtrl.text = fl.remarks;
      fl.debitCtrl.text = debit > 0 ? debit.toStringAsFixed(2) : '';
      fl.creditCtrl.text = credit > 0 ? credit.toStringAsFixed(2) : '';
      _lines.add(fl);
    }
    while (_lines.length < 2) {
      _lines.add(_JeFormLine());
    }
  }

  void _addLine() {
    final line = _JeFormLine();
    line.debitCtrl.text = '';
    line.creditCtrl.text = '';
    setState(() => _lines.add(line));
    _scheduleLocalDraftSave();
  }

  void _removeLine(int index) {
    if (_lines.length <= 2) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Keep at least two lines.')),
      );
      return;
    }
    setState(() {
      _lines[index].dispose();
      _lines.removeAt(index);
    });
    _scheduleLocalDraftSave();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _loadErrorCause = null;
    });
    try {
      final svc = context.read<JournalEntryService>();
      final open = await svc.getOpen();
      if (!mounted) return;
      _defaultRecv = open.defaultCustomerReceivable.isNotEmpty ? open.defaultCustomerReceivable : '1200';
      _defaultPay = open.defaultSupplierPayable.isNotEmpty ? open.defaultSupplierPayable : '2110';

      if (_isEditing) {
        final detail = await svc.getDetail(widget.editDocId!.trim());
        if (!mounted) return;
        if (!detail.canEdit) {
          setState(() {
            _loadError = 'This journal cannot be edited.';
            _loading = false;
          });
          return;
        }
        final parsed = DateTime.tryParse(detail.voucherDate);
        _voucherDate = parsed ?? _voucherDate;
        _reference.text = detail.referenceNo;
        _narration.text = detail.narration;
        if (detail.isDraft) {
          _draftId = detail.draftId.isNotEmpty ? detail.draftId : detail.voucherNo;
          _editVoucherNo = '';
        } else {
          _draftId = '';
          _editVoucherNo = detail.voucherNo;
        }
        for (final l in _lines) {
          l.dispose();
        }
        _lines.clear();
        for (final ln in detail.lines) {
          final fl = _JeFormLine(
            accountCode: ln.accountCode,
            accountName: ln.accountName,
            debit: ln.debit,
            credit: ln.credit,
            remarks: ln.remarks,
            partyType: ln.partyType,
            partyCode: ln.partyCode,
            partyName: ln.partyName,
          );
          fl.remarksCtrl.text = ln.remarks;
          fl.debitCtrl.text = ln.debit > 0 ? ln.debit.toStringAsFixed(2) : '';
          fl.creditCtrl.text = ln.credit > 0 ? ln.credit.toStringAsFixed(2) : '';
          _lines.add(fl);
        }
        while (_lines.length < 2) {
          _lines.add(_JeFormLine());
        }
        setState(() => _loading = false);
        return;
      }

      if (open.voucherDate.isNotEmpty) {
        final parsed = DateTime.tryParse(open.voucherDate);
        if (parsed != null) _voucherDate = parsed;
      }
      for (final l in _lines) {
        l.dispose();
      }
      _lines
        ..clear()
        ..add(_JeFormLine())
        ..add(_JeFormLine());

      if (widget.restoreDraft && !_isEditing && _localDraftUsername.isNotEmpty) {
        final draft = await TransactionDraftStorage.read(
          docType: TransactionDraftType.journalEntry,
          tenantId: _localDraftTenantId,
          username: _localDraftUsername,
        );
        if (!mounted) return;
        if (draft != null) {
          setState(() {
            _applyLocalDraft(draft);
            _loading = false;
          });
          return;
        }
      }

      setState(() => _loading = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadErrorCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<JeAccountOption?> _pickAccount() async {
    return showModalBottomSheet<JeAccountOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => const _AccountPickerSheet(),
    );
  }

  Future<JePartyOption?> _pickParty(String partyType) async {
    return showModalBottomSheet<JePartyOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _PartyPickerSheet(partyType: partyType),
    );
  }

  Map<String, dynamic> _payload() {
    return {
      'header': {
        if (_draftId.isNotEmpty) 'draft_id': _draftId,
        if (_editVoucherNo.isNotEmpty) 'edit_voucher_no': _editVoucherNo,
        'voucher_date': isoDate(_voucherDate),
        'reference_no': _reference.text.trim(),
        'narration': _narration.text.trim(),
      },
      'lines': [
        for (final l in _lines)
          if (l.accountCode.isNotEmpty || l.debit > 0 || l.credit > 0 || l.remarks.trim().isNotEmpty)
            {
              'account_code': l.accountCode,
              'debit': l.debit,
              'credit': l.credit,
              'remarks': l.remarksCtrl.text.trim(),
              'party_type': l.partyType,
              'party_code': l.partyCode,
            },
      ],
    };
  }

  Future<void> _saveDraft() async {
    if (_editVoucherNo.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Draft save is not available while editing a posted voucher.')),
      );
      return;
    }
    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save draft?',
      message: 'Save this journal entry as draft?',
      confirmLabel: 'Save draft',
    );
    if (!confirmed || !mounted) return;
    setState(() => _submitting = true);
    try {
      final result = await context.read<JournalEntryService>().saveDraft(_payload());
      if (!mounted) return;
      await _clearLocalDraft();
      if (!mounted) return;
      _draftId = result.draftId.isNotEmpty ? result.draftId : result.voucherNo;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Draft saved')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _post() async {
    if (!_balanced) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Totals must balance. Debit ${fmtMoney(_totalDebit)} vs Credit ${fmtMoney(_totalCredit)}.',
          ),
        ),
      );
      return;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(_editVoucherNo.isNotEmpty ? 'Update journal?' : 'Post journal?'),
        content: Text(
          _editVoucherNo.isNotEmpty
              ? 'Update voucher $_editVoucherNo with these lines.'
              : 'Post this balanced journal entry to the general ledger.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(_editVoucherNo.isNotEmpty ? 'Update' : 'Post'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _submitting = true);
    try {
      final result = await context.read<JournalEntryService>().postJournal(_payload());
      if (!mounted) return;
      await _clearLocalDraft();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Posted')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = _editVoucherNo.isNotEmpty
        ? 'Edit $_editVoucherNo'
        : (_draftId.isNotEmpty ? 'Draft $_draftId' : 'New Journal');

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _loadError != null
              ? Column(
                  children: [
                    ApiErrorBanner(message: _loadError!, error: _loadErrorCause),
                    TextButton(onPressed: _load, child: const Text('Retry')),
                  ],
                )
              : Column(
                  children: [
                    Expanded(
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(12, 10, 12, 16),
                        children: [
                          Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: const Color(0xFFE8EBF3)),
                            ),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: ReportFilterChip(
                                        label: 'Date ${isoDate(_voucherDate)}',
                                        onTap: () => pickReportDate(
                                          context,
                                          initial: _voucherDate,
                                          onPicked: (d) {
                                            setState(() => _voucherDate = d);
                                            _scheduleLocalDraftSave();
                                          },
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 10),
                                TextField(
                                  controller: _reference,
                                  decoration: const InputDecoration(
                                    labelText: 'Reference',
                                    isDense: true,
                                    border: OutlineInputBorder(),
                                  ),
                                ),
                                const SizedBox(height: 10),
                                TextField(
                                  controller: _narration,
                                  maxLines: 2,
                                  decoration: const InputDecoration(
                                    labelText: 'Narration',
                                    isDense: true,
                                    border: OutlineInputBorder(),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Text(
                                'Lines',
                                style: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  color: Colors.grey.shade800,
                                ),
                              ),
                              const Spacer(),
                              TextButton.icon(
                                onPressed: _submitting ? null : _addLine,
                                icon: const Icon(Icons.add, size: 18),
                                label: const Text('Add'),
                              ),
                            ],
                          ),
                          for (var i = 0; i < _lines.length; i++) _buildLineCard(i),
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: _balanced ? const Color(0xFFA5D6A7) : const Color(0xFFFFCC80),
                              ),
                            ),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    Expanded(child: Text('Debit ${fmtMoney(_totalDebit)}')),
                                    Expanded(
                                      child: Text(
                                        'Credit ${fmtMoney(_totalCredit)}',
                                        textAlign: TextAlign.end,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  _balanced
                                      ? 'Balanced'
                                      : 'Difference ${fmtMoney(_difference.abs())}',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: _balanced ? const Color(0xFF2E7D32) : const Color(0xFFEF6C00),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    SafeArea(
                      top: false,
                      child: Material(
                        color: Colors.white,
                        elevation: 8,
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                          child: Row(
                            children: [
                              if (_editVoucherNo.isEmpty)
                                Expanded(
                                  child: OutlinedButton(
                                    onPressed: _submitting ? null : _saveDraft,
                                    child: const Text('Save draft'),
                                  ),
                                ),
                              if (_editVoucherNo.isEmpty) const SizedBox(width: 10),
                              Expanded(
                                flex: 2,
                                child: FilledButton(
                                  onPressed: _submitting ? null : _post,
                                  style: FilledButton.styleFrom(backgroundColor: _accent),
                                  child: _submitting
                                      ? const SizedBox(
                                          width: 18,
                                          height: 18,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: Colors.white,
                                          ),
                                        )
                                      : Text(_editVoucherNo.isNotEmpty ? 'Update' : 'Post'),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }

  Widget _buildLineCard(int index) {
    final line = _lines[index];
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text('Line ${index + 1}', style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade700)),
              const Spacer(),
              IconButton(
                visualDensity: VisualDensity.compact,
                onPressed: _submitting ? null : () => _removeLine(index),
                icon: Icon(Icons.delete_outline, color: Colors.grey.shade500, size: 20),
              ),
            ],
          ),
          InkWell(
            onTap: _submitting
                ? null
                : () async {
                    final acc = await _pickAccount();
                    if (acc == null || !mounted) return;
                    setState(() {
                      line.accountCode = acc.code;
                      line.accountName = acc.name;
                    });
                    _scheduleLocalDraftSave();
                  },
            borderRadius: BorderRadius.circular(8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              decoration: BoxDecoration(
                border: Border.all(color: _border),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      line.accountCode.isEmpty
                          ? 'Select account'
                          : (line.accountName.isNotEmpty
                              ? '${line.accountCode} — ${line.accountName}'
                              : line.accountCode),
                      style: TextStyle(
                        color: line.accountCode.isEmpty ? Colors.grey.shade500 : const Color(0xFF262C50),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Icon(Icons.expand_more, color: Colors.grey.shade500),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: NumericTextField(
                  controller: line.debitCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Debit',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  onChanged: (v) {
                    final n = double.tryParse(v.replaceAll(',', '')) ?? 0;
                    setState(() {
                      line.debit = n;
                      if (n > 0) {
                        line.credit = 0;
                        line.creditCtrl.text = '';
                      }
                    });
                    _scheduleLocalDraftSave();
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: NumericTextField(
                  controller: line.creditCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Credit',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  onChanged: (v) {
                    final n = double.tryParse(v.replaceAll(',', '')) ?? 0;
                    setState(() {
                      line.credit = n;
                      if (n > 0) {
                        line.debit = 0;
                        line.debitCtrl.text = '';
                      }
                    });
                    _scheduleLocalDraftSave();
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: line.remarksCtrl,
            decoration: const InputDecoration(
              labelText: 'Remarks',
              isDense: true,
              border: OutlineInputBorder(),
            ),
            onChanged: (v) {
              line.remarks = v;
              _scheduleLocalDraftSave();
            },
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              ChoiceChip(
                label: const Text('No party', style: TextStyle(fontSize: 12)),
                selected: line.partyType.isEmpty,
                onSelected: (_) {
                  setState(() {
                    line.partyType = '';
                    line.partyCode = '';
                    line.partyName = '';
                  });
                  _scheduleLocalDraftSave();
                },
              ),
              ChoiceChip(
                label: const Text('Customer', style: TextStyle(fontSize: 12)),
                selected: line.partyType == 'CUSTOMER',
                onSelected: (_) async {
                  final p = await _pickParty('CUSTOMER');
                  if (p == null || !mounted) return;
                  setState(() {
                    line.partyType = 'CUSTOMER';
                    line.partyCode = p.partyCode;
                    line.partyName = p.partyName;
                    if (line.accountCode.isEmpty) {
                      line.accountCode = p.glAccount.isNotEmpty ? p.glAccount : _defaultRecv;
                      line.accountName = '';
                    }
                  });
                  _scheduleLocalDraftSave();
                },
              ),
              ChoiceChip(
                label: const Text('Supplier', style: TextStyle(fontSize: 12)),
                selected: line.partyType == 'SUPPLIER',
                onSelected: (_) async {
                  final p = await _pickParty('SUPPLIER');
                  if (p == null || !mounted) return;
                  setState(() {
                    line.partyType = 'SUPPLIER';
                    line.partyCode = p.partyCode;
                    line.partyName = p.partyName;
                    if (line.accountCode.isEmpty) {
                      line.accountCode = p.glAccount.isNotEmpty ? p.glAccount : _defaultPay;
                      line.accountName = '';
                    }
                  });
                  _scheduleLocalDraftSave();
                },
              ),
            ],
          ),
          if (line.partyCode.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '${line.partyType} ${line.partyCode}${line.partyName.isNotEmpty ? ' — ${line.partyName}' : ''}',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
            ),
        ],
      ),
    );
  }
}

class _AccountPickerSheet extends StatefulWidget {
  const _AccountPickerSheet();

  @override
  State<_AccountPickerSheet> createState() => _AccountPickerSheetState();
}

class _AccountPickerSheetState extends State<_AccountPickerSheet> {
  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  List<JeAccountOption> _rows = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await context.read<JournalEntryService>().listAccounts(q: _search.text.trim());
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.of(context).size.height * 0.75;
    return SizedBox(
      height: h,
      child: Column(
        children: [
          const SizedBox(height: 10),
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(4)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
            child: TextField(
              controller: _search,
              autofocus: true,
              decoration: const InputDecoration(
                hintText: 'Search account code or name…',
                prefixIcon: Icon(Icons.search),
                isDense: true,
                border: OutlineInputBorder(),
              ),
              onChanged: (_) {
                _debounce?.cancel();
                _debounce = Timer(const Duration(milliseconds: 300), _reload);
              },
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(_error!, style: const TextStyle(color: Color(0xFFC62828))),
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    itemCount: _rows.length,
                    itemBuilder: (context, i) {
                      final a = _rows[i];
                      return ListTile(
                        title: Text(a.code, style: const TextStyle(fontWeight: FontWeight.w700)),
                        subtitle: Text(a.name),
                        onTap: () => Navigator.pop(context, a),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _PartyPickerSheet extends StatefulWidget {
  const _PartyPickerSheet({required this.partyType});

  final String partyType;

  @override
  State<_PartyPickerSheet> createState() => _PartyPickerSheetState();
}

class _PartyPickerSheetState extends State<_PartyPickerSheet> {
  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  List<JePartyOption> _rows = [];
  String? _error;

  bool get _isCustomer => widget.partyType == 'CUSTOMER';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final svc = context.read<JournalEntryService>();
      final rows = _isCustomer
          ? await svc.listCustomers(q: _search.text.trim())
          : await svc.listSuppliers(q: _search.text.trim());
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.of(context).size.height * 0.75;
    return SizedBox(
      height: h,
      child: Column(
        children: [
          const SizedBox(height: 10),
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(4)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
            child: TextField(
              controller: _search,
              autofocus: true,
              decoration: InputDecoration(
                hintText: _isCustomer ? 'Search customer…' : 'Search supplier…',
                prefixIcon: const Icon(Icons.search),
                isDense: true,
                border: const OutlineInputBorder(),
              ),
              onChanged: (_) {
                _debounce?.cancel();
                _debounce = Timer(const Duration(milliseconds: 300), _reload);
              },
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(_error!, style: const TextStyle(color: Color(0xFFC62828))),
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    itemCount: _rows.length,
                    itemBuilder: (context, i) {
                      final p = _rows[i];
                      return ListTile(
                        title: Text(p.partyName, style: const TextStyle(fontWeight: FontWeight.w700)),
                        subtitle: Text(
                          p.glAccount.isNotEmpty ? '${p.partyCode} · GL ${p.glAccount}' : p.partyCode,
                        ),
                        onTap: () => Navigator.pop(context, p),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
