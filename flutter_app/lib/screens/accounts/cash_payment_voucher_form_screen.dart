import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../core/ui/confirm_save.dart';
import '../../providers/auth_provider.dart';
import '../../services/cash_payment_voucher_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

class _CpvFormLine {
  _CpvFormLine({
    this.accountCode = '',
    this.accountName = '',
    this.description = '',
    this.amount = 0,
  });

  String accountCode;
  String accountName;
  String description;
  double amount;

  final descriptionCtrl = TextEditingController();
  final amountCtrl = TextEditingController();

  void dispose() {
    descriptionCtrl.dispose();
    amountCtrl.dispose();
  }
}

class CashPaymentVoucherFormScreen extends StatefulWidget {
  const CashPaymentVoucherFormScreen({super.key, this.editVoucherNo, this.restoreDraft = false});

  final String? editVoucherNo;
  final bool restoreDraft;

  @override
  State<CashPaymentVoucherFormScreen> createState() => _CashPaymentVoucherFormScreenState();
}

class _CashPaymentVoucherFormScreenState extends State<CashPaymentVoucherFormScreen> with WidgetsBindingObserver {
  static const _accent = Color(0xFF00897B);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  bool _loading = true;
  bool _submitting = false;
  String? _loadError;
  Object? _loadErrorCause;

  bool get _isEditing => (widget.editVoucherNo ?? '').trim().isNotEmpty;

  String _voucherNo = '';
  String _voucherDate = '';
  List<CpvAccountOption> _pettyAccounts = [];
  List<CpvAccountOption> _expenseParents = [];
  List<CpvAccountOption> _expenseChildren = [];
  bool _loadingChildren = false;

  CpvAccountOption? _pettyCash;
  CpvAccountOption? _expenseParent;
  final _reference = TextEditingController();
  final _narration = TextEditingController();
  final List<_CpvFormLine> _lines = [];

  Timer? _draftDebounce;
  String _draftTenantId = '';
  String _draftUsername = '';
  bool _draftCleared = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _reference.addListener(_scheduleDraftSave);
    _narration.addListener(_scheduleDraftSave);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = context.read<AuthProvider>().user;
      _draftTenantId = user?.tenantId ?? '';
      _draftUsername = user?.username ?? '';
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
    _reference.removeListener(_scheduleDraftSave);
    _narration.removeListener(_scheduleDraftSave);
    _draftDebounce?.cancel();
    _reference.dispose();
    _narration.dispose();
    for (final l in _lines) {
      l.dispose();
    }
    super.dispose();
  }

  void _scheduleDraftSave() {
    if (_isEditing || _draftCleared || _loading || _submitting) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), _persistLocalDraft);
  }

  bool get _hasMeaningfulLocalDraft {
    if (_reference.text.trim().isNotEmpty || _narration.text.trim().isNotEmpty) return true;
    for (final l in _lines) {
      if (l.accountCode.trim().isNotEmpty) return true;
      if (l.descriptionCtrl.text.trim().isNotEmpty) return true;
      if (l.amount > 0) return true;
    }
    return false;
  }

  void _syncLineAmountsSilent() {
    for (final l in _lines) {
      final raw = l.amountCtrl.text.trim().replaceAll(',', '');
      l.amount = double.tryParse(raw) ?? 0;
      l.description = l.descriptionCtrl.text;
    }
  }

  Future<void> _persistLocalDraft() async {
    if (_isEditing || _draftCleared || _submitting) return;
    if (!_hasMeaningfulLocalDraft) return;
    if (_draftUsername.isEmpty) return;
    _syncLineAmountsSilent();
    final draft = <String, dynamic>{
      'reference': _reference.text,
      'narration': _narration.text,
      'petty_cash_code': _pettyCash?.code ?? '',
      'petty_cash_name': _pettyCash?.name ?? '',
      'expense_parent_code': _expenseParent?.code ?? '',
      'expense_parent_name': _expenseParent?.name ?? '',
      'lines': [
        for (final l in _lines)
          {
            'account_code': l.accountCode,
            'account_name': l.accountName,
            'description': l.descriptionCtrl.text,
            'amount': l.amount,
          },
      ],
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.cashPaymentVoucher,
      tenantId: _draftTenantId,
      username: _draftUsername,
      draft: draft,
    );
  }

  Future<void> _clearLocalDraft() async {
    _draftCleared = true;
    _draftDebounce?.cancel();
    if (_draftUsername.isEmpty) return;
    await TransactionDraftStorage.clear(
      docType: TransactionDraftType.cashPaymentVoucher,
      tenantId: _draftTenantId,
      username: _draftUsername,
    );
  }

  Future<void> _applyLocalDraft(Map<String, dynamic> draft) async {
    final pettyCode = '${draft['petty_cash_code'] ?? ''}'.trim();
    final parentCode = '${draft['expense_parent_code'] ?? ''}'.trim();
    if (pettyCode.isNotEmpty) {
      _pettyCash = _findAccount(_pettyAccounts, pettyCode) ??
          CpvAccountOption(code: pettyCode, name: '${draft['petty_cash_name'] ?? ''}');
    }
    if (parentCode.isNotEmpty) {
      _expenseParent = _findAccount(_expenseParents, parentCode) ??
          CpvAccountOption(code: parentCode, name: '${draft['expense_parent_name'] ?? ''}');
      await _loadExpenseChildren(parentCode, preserveLines: true);
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
      final amount = (m['amount'] is num)
          ? (m['amount'] as num).toDouble()
          : double.tryParse('${m['amount']}') ?? 0;
      final line = _CpvFormLine(
        accountCode: '${m['account_code'] ?? ''}'.trim(),
        accountName: '${m['account_name'] ?? ''}'.trim(),
        description: '${m['description'] ?? ''}',
        amount: amount,
      );
      line.descriptionCtrl.text = line.description;
      line.amountCtrl.text = amount > 0 ? amount.toStringAsFixed(2) : '';
      _lines.add(line);
    }
    if (_lines.isEmpty) _addLine();
    if (mounted) setState(() {});
  }

  double get _total => _lines.fold(0.0, (s, l) => s + l.amount);

  CpvAccountOption? _findAccount(List<CpvAccountOption> list, String code) {
    for (final a in list) {
      if (a.code == code) return a;
    }
    return null;
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _loadErrorCause = null;
    });
    try {
      final svc = context.read<CashPaymentVoucherService>();
      final open = await svc.getOpen();
      if (!mounted) return;

      if (_isEditing) {
        final detail = await svc.getDetail(widget.editVoucherNo!.trim());
        if (!mounted) return;
        if (!detail.canEdit) {
          setState(() {
            _loadError = detail.isPosted
                ? 'This Cash Payment Voucher is posted and cannot be edited.'
                : 'This Cash Payment Voucher cannot be edited.';
            _loading = false;
          });
          return;
        }
        await _applyEditDetail(detail, open: open, svc: svc);
        return;
      }

      CpvAccountOption? petty;
      CpvAccountOption? parent;
      if (open.defaultPettyCash.isNotEmpty) {
        petty = _findAccount(open.pettyAccounts, open.defaultPettyCash);
      }
      petty ??= open.pettyAccounts.isNotEmpty ? open.pettyAccounts.first : null;

      if (open.defaultExpenseParent.isNotEmpty) {
        parent = _findAccount(open.expenseParentAccounts, open.defaultExpenseParent);
      }
      parent ??= open.expenseParentAccounts.isNotEmpty ? open.expenseParentAccounts.first : null;

      setState(() {
        _voucherNo = open.voucherNo;
        _voucherDate = open.voucherDate;
        _pettyAccounts = open.pettyAccounts;
        _expenseParents = open.expenseParentAccounts;
        _pettyCash = petty;
        _expenseParent = parent;
        _loading = false;
      });

      if (widget.restoreDraft && !_isEditing && _draftUsername.isNotEmpty) {
        final draft = await TransactionDraftStorage.read(
          docType: TransactionDraftType.cashPaymentVoucher,
          tenantId: _draftTenantId,
          username: _draftUsername,
        );
        if (!mounted) return;
        if (draft != null) {
          await _applyLocalDraft(draft);
          return;
        }
      }

      if (parent != null) {
        await _loadExpenseChildren(parent.code, preserveLines: false);
      } else {
        _addLine();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadErrorCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _applyEditDetail(
    CpvDetail detail, {
    required CpvOpenContext open,
    required CashPaymentVoucherService svc,
  }) async {
    final petty = _findAccount(open.pettyAccounts, detail.pettyCashAccount) ??
        (detail.pettyCashAccount.isNotEmpty
            ? CpvAccountOption(code: detail.pettyCashAccount, name: detail.pettyCashName)
            : null);
    final parent = _findAccount(open.expenseParentAccounts, detail.expenseParentAccount) ??
        (detail.expenseParentAccount.isNotEmpty
            ? CpvAccountOption(code: detail.expenseParentAccount, name: detail.expenseParentName)
            : null);

    for (final l in _lines) {
      l.dispose();
    }
    _lines.clear();

    setState(() {
      _voucherNo = detail.voucherNo.isNotEmpty ? detail.voucherNo : open.voucherNo;
      _voucherDate = detail.voucherDate.isNotEmpty ? detail.voucherDate : open.voucherDate;
      _pettyAccounts = open.pettyAccounts;
      _expenseParents = open.expenseParentAccounts;
      _pettyCash = petty;
      _expenseParent = parent;
      _reference.text = detail.referenceNo;
      _narration.text = detail.narration;
      _loading = false;
    });

    if (parent != null) {
      await _loadExpenseChildren(parent.code, preserveLines: false);
    }

    for (final ln in detail.lines) {
      final formLine = _CpvFormLine(
        accountCode: ln.accountCode,
        accountName: ln.accountName,
        description: ln.description,
        amount: ln.amount,
      );
      formLine.descriptionCtrl.text = ln.description;
      formLine.amountCtrl.text = ln.amount.toStringAsFixed(2);
      _lines.add(formLine);
    }

    if (_lines.isEmpty) _addLine();
    if (mounted) setState(() {});
  }

  Future<void> _loadExpenseChildren(String parentCode, {required bool preserveLines}) async {
    if (parentCode.trim().isEmpty) {
      setState(() {
        _expenseChildren = [];
        _loadingChildren = false;
      });
      return;
    }
    setState(() => _loadingChildren = true);
    try {
      final children = await context.read<CashPaymentVoucherService>().listExpenseChildren(parentCode);
      if (!mounted) return;
      setState(() {
        _expenseChildren = children;
        _loadingChildren = false;
      });
      if (!preserveLines) {
        for (final l in _lines) {
          l.accountCode = '';
          l.accountName = '';
        }
      } else {
        final valid = children.map((c) => c.code).toSet();
        for (final l in _lines) {
          if (l.accountCode.isNotEmpty && !valid.contains(l.accountCode)) {
            l.accountCode = '';
            l.accountName = '';
          }
        }
      }
      if (mounted) setState(() {});
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingChildren = false;
        _expenseChildren = [];
      });
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  void _addLine() {
    setState(() => _lines.add(_CpvFormLine()));
    _scheduleDraftSave();
  }

  void _removeLine(int index) {
    if (index < 0 || index >= _lines.length) return;
    final line = _lines.removeAt(index);
    line.dispose();
    setState(() {});
    _scheduleDraftSave();
  }

  void _syncLineAmount(int index) {
    if (index < 0 || index >= _lines.length) return;
    final raw = _lines[index].amountCtrl.text.trim().replaceAll(',', '');
    _lines[index].amount = double.tryParse(raw) ?? 0;
    setState(() {});
    _scheduleDraftSave();
  }

  void _syncAllLineAmounts() {
    for (var i = 0; i < _lines.length; i++) {
      _syncLineAmount(i);
    }
  }

  Map<String, dynamic> _buildHeader() => {
        'voucher_no': _voucherNo,
        'voucher_date': _voucherDate,
        'petty_cash_account': _pettyCash?.code ?? '',
        'expense_parent_account': _expenseParent?.code ?? '',
        'reference_no': _reference.text.trim(),
        'narration': _narration.text.trim(),
      };

  List<Map<String, dynamic>> _buildLinesPayload() {
    return _lines
        .map(
          (l) => <String, dynamic>{
            'account_code': l.accountCode,
            'description': l.descriptionCtrl.text.trim(),
            'amount': l.amount,
          },
        )
        .toList();
  }

  Future<void> _pickPettyCash() async {
    final picked = await _showAccountPicker(
      title: 'Petty Cash Account',
      accounts: _pettyAccounts,
      selected: _pettyCash,
    );
    if (picked == null || !mounted) return;
    setState(() => _pettyCash = picked);
    _scheduleDraftSave();
  }

  Future<void> _pickExpenseParent() async {
    final picked = await _showAccountPicker(
      title: 'Expense Parent Account',
      accounts: _expenseParents,
      selected: _expenseParent,
    );
    if (picked == null || !mounted) return;
    if (_expenseParent?.code == picked.code) return;
    setState(() => _expenseParent = picked);
    await _loadExpenseChildren(picked.code, preserveLines: false);
    _scheduleDraftSave();
  }

  Future<void> _pickLineAccount(int index) async {
    if (_expenseParent == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select an Expense Parent Account first.')),
      );
      return;
    }
    final parentCode = _expenseParent!.code;
    final current = _lines[index].accountCode.isNotEmpty
        ? CpvAccountOption(code: _lines[index].accountCode, name: _lines[index].accountName)
        : null;
    final picked = await _showAccountPicker(
      title: 'Expense Sub Account',
      accounts: _expenseChildren,
      selected: current,
      allowCreate: true,
      createLabel: 'Add',
      onCreate: (name, code) async {
        final created = await context.read<CashPaymentVoucherService>().createExpenseSubAccount(
              parentCode: parentCode,
              name: name,
              code: code,
            );
        if (mounted) {
          setState(() {
            if (!_expenseChildren.any((a) => a.code == created.code)) {
              _expenseChildren = [..._expenseChildren, created]
                ..sort((a, b) => a.code.compareTo(b.code));
            }
          });
        }
        return created;
      },
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (!_expenseChildren.any((a) => a.code == picked.code)) {
        _expenseChildren = [..._expenseChildren, picked]..sort((a, b) => a.code.compareTo(b.code));
      }
      _lines[index].accountCode = picked.code;
      _lines[index].accountName = picked.name;
    });
    _scheduleDraftSave();
  }

  Future<CpvAccountOption?> _showAccountPicker({
    required String title,
    required List<CpvAccountOption> accounts,
    CpvAccountOption? selected,
    bool allowCreate = false,
    String createLabel = 'Add',
    Future<CpvAccountOption> Function(String name, String code)? onCreate,
  }) {
    return showModalBottomSheet<CpvAccountOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _AccountPickerSheet(
        title: title,
        accounts: accounts,
        selectedCode: selected?.code,
        allowCreate: allowCreate,
        createLabel: createLabel,
        onCreate: onCreate,
      ),
    );
  }

  Future<void> _saveDraft() async {
    if (_submitting) return;
    final confirmed = await confirmSaveTransaction(
      context,
      title: 'Save draft?',
      message: 'Save Cash Payment Voucher $_voucherNo as draft?',
      confirmLabel: 'Save draft',
      confirmColor: const Color(0xFF2E7D32),
    );
    if (!confirmed || !mounted) return;
    _syncAllLineAmounts();
    setState(() => _submitting = true);
    try {
      final result = await context.read<CashPaymentVoucherService>().saveDraft(
            header: _buildHeader(),
            lines: _buildLinesPayload(),
          );
      if (!mounted) return;
      await _clearLocalDraft();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.message.isNotEmpty ? result.message : 'Draft saved: ${result.voucherNo}',
          ),
        ),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _postVoucher() async {
    if (_submitting) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Post to GL'),
        content: Text(
          'Post Cash Payment Voucher $_voucherNo to the general ledger?\n\n'
          'Total: ${_total.toStringAsFixed(2)}',
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

    _syncAllLineAmounts();
    setState(() => _submitting = true);
    try {
      final result = await context.read<CashPaymentVoucherService>().postVoucher(
            header: _buildHeader(),
            lines: _buildLinesPayload(),
          );
      if (!mounted) return;
      await _clearLocalDraft();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => _CpvPostedDialog(result: result),
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Widget _card({required Widget child, EdgeInsetsGeometry? padding}) => Container(
        width: double.infinity,
        padding: padding ?? const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: _border),
        ),
        child: child,
      );

  Widget _pickerField({
    required String label,
    required String value,
    required String hint,
    required IconData icon,
    required VoidCallback onTap,
    String? subtitle,
  }) =>
      InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                    const SizedBox(height: 2),
                    Text(
                      value.isNotEmpty ? value : hint,
                      style: TextStyle(
                        fontWeight: value.isNotEmpty ? FontWeight.w600 : FontWeight.w400,
                        color: value.isNotEmpty ? const Color(0xFF262C50) : Colors.grey.shade500,
                      ),
                    ),
                    if (subtitle != null && subtitle.isNotEmpty)
                      Text(subtitle, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                  ],
                ),
              ),
              Icon(icon, size: 20, color: Colors.grey.shade600),
            ],
          ),
        ),
      );

  Widget _readonlyRow(String label, String value) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 110, child: Text(label, style: TextStyle(fontSize: 13, color: Colors.grey.shade700))),
            Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
          ],
        ),
      );

  Widget _lineCard(int index) {
    final line = _lines[index];
    final accountLabel = line.accountName.isNotEmpty
        ? '${line.accountCode} — ${line.accountName}'
        : (line.accountCode.isNotEmpty ? line.accountCode : 'Select expense account');

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text('Line ${index + 1}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
              const Spacer(),
              if (_lines.length > 1)
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: Color(0xFFC62828), size: 20),
                  onPressed: _submitting ? null : () => _removeLine(index),
                  tooltip: 'Remove line',
                ),
            ],
          ),
          InkWell(
            onTap: _submitting ? null : () => _pickLineAccount(index),
            borderRadius: BorderRadius.circular(4),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Expense account *', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                        const SizedBox(height: 2),
                        Text(
                          accountLabel,
                          style: TextStyle(
                            fontWeight: line.accountCode.isNotEmpty ? FontWeight.w600 : FontWeight.w400,
                            color: line.accountCode.isNotEmpty
                                ? const Color(0xFF262C50)
                                : Colors.grey.shade500,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(Icons.arrow_drop_down, color: Colors.grey.shade600),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: line.descriptionCtrl,
            readOnly: _submitting,
            maxLines: 2,
            decoration: const InputDecoration(
              labelText: 'Description',
              border: OutlineInputBorder(),
              isDense: true,
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            ),
            onChanged: (_) {
              line.description = line.descriptionCtrl.text.trim();
              _scheduleDraftSave();
            },
          ),
          const SizedBox(height: 10),
          AbsorbPointer(
            absorbing: _submitting,
            child: NumericTextField(
            controller: line.amountCtrl,
            labelText: 'Amount *',
            selectAllOnFocus: true,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              isDense: true,
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            ),
            onChanged: (_) => _syncLineAmount(index),
          ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(),
        body: const Center(child: CircularProgressIndicator(color: _accent)),
      );
    }
    if (_loadError != null) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(),
        body: ApiErrorCenter(message: _loadError!, error: _loadErrorCause, onRetry: _load),
      );
    }

    final pettyLabel = _pettyCash == null
        ? ''
        : (_pettyCash!.name.isNotEmpty ? '${_pettyCash!.code} — ${_pettyCash!.name}' : _pettyCash!.code);
    final parentLabel = _expenseParent == null
        ? ''
        : (_expenseParent!.name.isNotEmpty
            ? '${_expenseParent!.code} — ${_expenseParent!.name}'
            : _expenseParent!.code);

    return Scaffold(
      backgroundColor: _bg,
      appBar: _appBar(),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _card(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _readonlyRow('Voucher No.', _voucherNo.isEmpty ? '—' : _voucherNo),
                        _readonlyRow('Date', _voucherDate.isEmpty ? '—' : _voucherDate),
                        const Divider(height: 16),
                        _pickerField(
                          label: 'Petty Cash Account *',
                          value: pettyLabel,
                          hint: 'Select petty cash account',
                          icon: Icons.account_balance_wallet_outlined,
                          onTap: _pickPettyCash,
                        ),
                        const Divider(height: 1),
                        _pickerField(
                          label: 'Expense Parent Account *',
                          value: parentLabel,
                          hint: 'Select expense parent',
                          icon: Icons.account_tree_outlined,
                          onTap: _pickExpenseParent,
                        ),
                        const Divider(height: 1),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _reference,
                          readOnly: _submitting,
                          decoration: const InputDecoration(
                            labelText: 'Reference No.',
                            border: OutlineInputBorder(),
                            isDense: true,
                            contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _narration,
                          readOnly: _submitting,
                          maxLines: 3,
                          decoration: const InputDecoration(
                            labelText: 'Narration',
                            border: OutlineInputBorder(),
                            isDense: true,
                            contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Text(
                        'Expense lines',
                        style: TextStyle(fontWeight: FontWeight.w700, color: Colors.grey.shade800),
                      ),
                      if (_loadingChildren) ...[
                        const SizedBox(width: 8),
                        const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2, color: _accent),
                        ),
                      ],
                      const Spacer(),
                      TextButton.icon(
                        onPressed: _submitting || _loadingChildren ? null : _addLine,
                        icon: const Icon(Icons.add, size: 18),
                        label: const Text('Add line'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  for (var i = 0; i < _lines.length; i++) _lineCard(i),
                  const SizedBox(height: 8),
                  _card(
                    child: Row(
                      children: [
                        Text('Total', style: TextStyle(fontSize: 14, color: Colors.grey.shade700)),
                        const Spacer(),
                        Text(
                          _total.toStringAsFixed(2),
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: _accent),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            color: Colors.white,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Divider(height: 1, color: Color(0xFFE8EBF3)),
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
                    child: Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: _submitting ? null : _saveDraft,
                            style: OutlinedButton.styleFrom(
                              foregroundColor: _accent,
                              side: const BorderSide(color: _accent),
                              minimumSize: const Size.fromHeight(46),
                            ),
                            child: Text(_submitting ? 'Saving…' : 'Save Draft'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          flex: 2,
                          child: FilledButton.icon(
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFF2E7D32),
                              minimumSize: const Size.fromHeight(46),
                            ),
                            onPressed: _submitting ? null : _postVoucher,
                            icon: _submitting
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : const Icon(Icons.check_circle_outline),
                            label: Text(_submitting ? 'Posting…' : 'Post to GL'),
                          ),
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

  PreferredSizeWidget _appBar() => AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: _submitting ? null : () => Navigator.of(context).maybePop(),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _isEditing ? 'Edit Cash Payment Voucher' : 'Cash Payment Voucher',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            if (_voucherNo.isNotEmpty)
              Text(
                '$_voucherNo • ${_voucherDate.isEmpty ? '—' : _voucherDate}',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
              ),
          ],
        ),
      );
}

class _AccountPickerSheet extends StatefulWidget {
  const _AccountPickerSheet({
    required this.title,
    required this.accounts,
    this.selectedCode,
    this.allowCreate = false,
    this.createLabel = 'Add',
    this.onCreate,
  });

  final String title;
  final List<CpvAccountOption> accounts;
  final String? selectedCode;
  final bool allowCreate;
  final String createLabel;
  final Future<CpvAccountOption> Function(String name, String code)? onCreate;

  @override
  State<_AccountPickerSheet> createState() => _AccountPickerSheetState();
}

class _AccountPickerSheetState extends State<_AccountPickerSheet> {
  static const _accent = Color(0xFF00897B);

  final _search = TextEditingController();
  late List<CpvAccountOption> _accounts;
  late List<CpvAccountOption> _filtered;
  bool _creating = false;

  @override
  void initState() {
    super.initState();
    _accounts = List<CpvAccountOption>.from(widget.accounts);
    _filtered = _accounts;
    _search.addListener(_filter);
  }

  @override
  void dispose() {
    _search.removeListener(_filter);
    _search.dispose();
    super.dispose();
  }

  void _filter() {
    final q = _search.text.trim().toLowerCase();
    setState(() {
      if (q.isEmpty) {
        _filtered = _accounts;
        return;
      }
      _filtered = _accounts.where((a) {
        return a.code.toLowerCase().contains(q) || a.name.toLowerCase().contains(q);
      }).toList();
    });
  }

  Future<void> _createSubAccount() async {
    if (widget.onCreate == null || _creating) return;
    final nameCtrl = TextEditingController();
    final codeCtrl = TextEditingController();
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Create sub-account'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              autofocus: true,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Account name *',
                hintText: 'e.g. Office Supplies',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: codeCtrl,
              keyboardType: TextInputType.text,
              decoration: const InputDecoration(
                labelText: 'Account code (optional)',
                hintText: 'Leave blank to auto-assign',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: _accent),
            onPressed: () => Navigator.of(ctx).pop({
              'name': nameCtrl.text.trim(),
              'code': codeCtrl.text.trim(),
            }),
            child: const Text('Create'),
          ),
        ],
      ),
    );
    final name = (result?['name'] ?? '').trim();
    final code = (result?['code'] ?? '').trim();
    if (name.isEmpty || !mounted) return;

    setState(() => _creating = true);
    try {
      final created = await widget.onCreate!(name, code);
      if (!mounted) return;
      setState(() {
        _accounts = [..._accounts.where((a) => a.code != created.code), created]
          ..sort((a, b) => a.code.compareTo(b.code));
        final q = _search.text.trim().toLowerCase();
        _filtered = q.isEmpty
            ? _accounts
            : _accounts
                .where((a) => a.code.toLowerCase().contains(q) || a.name.toLowerCase().contains(q))
                .toList();
        _creating = false;
      });
      Navigator.pop(context, created);
    } catch (e) {
      if (!mounted) return;
      setState(() => _creating = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    final showSearch = _accounts.length > 8 || widget.allowCreate;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              if (widget.allowCreate && widget.onCreate != null)
                TextButton.icon(
                  onPressed: _creating ? null : _createSubAccount,
                  icon: _creating
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.add_rounded, size: 20),
                  label: Text(widget.createLabel),
                ),
            ],
          ),
          const SizedBox(height: 12),
          if (showSearch)
            TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search code or name',
                prefixIcon: const Icon(Icons.search, size: 20),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                isDense: true,
              ),
            ),
          if (showSearch) const SizedBox(height: 8),
          if (_filtered.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Column(
                children: [
                  Text(
                    widget.allowCreate
                        ? 'No sub-accounts yet. Tap Add to create one.'
                        : 'No accounts found.',
                    style: TextStyle(color: Colors.grey.shade600),
                    textAlign: TextAlign.center,
                  ),
                  if (widget.allowCreate && widget.onCreate != null) ...[
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      style: FilledButton.styleFrom(backgroundColor: _accent),
                      onPressed: _creating ? null : _createSubAccount,
                      icon: const Icon(Icons.add_rounded),
                      label: const Text('Create sub-account'),
                    ),
                  ],
                ],
              ),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.45),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _filtered.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final a = _filtered[i];
                  final selected = a.code == widget.selectedCode;
                  return ListTile(
                    onTap: () => Navigator.pop(context, a),
                    selected: selected,
                    selectedTileColor: const Color(0xFFE0F2F1),
                    title: Text(
                      a.name.isNotEmpty ? a.name : a.code,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    subtitle: Text(a.code),
                    trailing: selected ? const Icon(Icons.check_rounded, color: _accent) : null,
                  );
                },
              ),
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
