import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../providers/auth_provider.dart';
import '../../services/cash_payment_voucher_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/transaction_draft_banner.dart';
import 'cash_payment_voucher_detail_screen.dart';
import 'cash_payment_voucher_form_screen.dart';
import '../../core/theme/app_theme.dart';

class CashPaymentVoucherListScreen extends StatefulWidget {
  const CashPaymentVoucherListScreen({super.key});

  @override
  State<CashPaymentVoucherListScreen> createState() => _CashPaymentVoucherListScreenState();
}

class _CashPaymentVoucherListScreenState extends State<CashPaymentVoucherListScreen> {
  static const _accent = Color(0xFF00897B);

  static const _tabs = [
    ('draft', 'Draft'),
    ('posted', 'Posted'),
    ('all', 'All'),
  ];

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<CpvSummary> _rows = [];
  String _tabKey = 'draft';
  Map<String, dynamic>? _localDraft;

  @override
  void initState() {
    super.initState();
    _search.addListener(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadLocalDraftBanner();
      _reload();
    });
  }

  Future<void> _loadLocalDraftBanner() async {
    final user = context.read<AuthProvider>().user;
    if (user == null) {
      if (mounted) setState(() => _localDraft = null);
      return;
    }
    final draft = await TransactionDraftStorage.read(
      docType: TransactionDraftType.cashPaymentVoucher,
      tenantId: user.tenantId ?? '',
      username: user.username,
    );
    if (!mounted) return;
    setState(() => _localDraft = draft);
  }

  Future<void> _dismissLocalDraft() async {
    final user = context.read<AuthProvider>().user;
    if (user != null) {
      await TransactionDraftStorage.clear(
        docType: TransactionDraftType.cashPaymentVoucher,
        tenantId: user.tenantId ?? '',
        username: user.username,
      );
    }
    if (mounted) setState(() => _localDraft = null);
  }

  Future<void> _continueLocalDraft() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => const CashPaymentVoucherFormScreen(restoreDraft: true),
      ),
    );
    if (!mounted) return;
    await _loadLocalDraftBanner();
    if (saved == true) _reload();
  }

  String _localDraftSubtitle(Map<String, dynamic> draft) {
    final ref = '${draft['reference'] ?? ''}'.trim();
    final lines = (draft['lines'] as List?)?.length ?? 0;
    if (ref.isNotEmpty) {
      return lines > 0 ? '$ref · $lines line${lines == 1 ? '' : 's'}' : ref;
    }
    if (lines > 0) return 'Cash payment · $lines line${lines == 1 ? '' : 's'}';
    return 'Unfinished cash payment';
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _scheduleSearch() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), _reload);
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final rows = await context.read<CashPaymentVoucherService>().listVouchers(
            q: _search.text.trim(),
            status: _tabKey,
          );
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _loading = false;
      });
    }
  }

  Future<void> _openDetail(CpvSummary row) async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => CashPaymentVoucherDetailScreen(voucherNo: row.voucherNo),
      ),
    );
    if (mounted) _reload();
  }

  Future<void> _openNew() async {
    if (_localDraft != null) {
      final action = await showPendingDraftAlert(
        context,
        summary: _localDraftSubtitle(_localDraft!),
        documentLabel: 'cash payment voucher',
      );
      if (!mounted) return;
      if (action == PendingDraftAction.cancel) return;
      if (action == PendingDraftAction.continuePending) {
        await _continueLocalDraft();
        return;
      }
      await _dismissLocalDraft();
    }
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const CashPaymentVoucherFormScreen()),
    );
    if (!mounted) return;
    await _loadLocalDraftBanner();
    if (saved == true) _reload();
  }

  String _emptyMessage() {
    if (_search.text.trim().isNotEmpty) {
      return 'No cash payment vouchers match your search.';
    }
    return switch (_tabKey) {
      'posted' => 'No posted cash payment vouchers.',
      'all' => 'No cash payment vouchers found.',
      _ => 'No draft cash payment vouchers.\nTap + to create one.',
    };
  }

  @override
  Widget build(BuildContext context) {
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
        title: const Text(
          'Cash Payment Vouchers',
          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        actions: [
          IconButton(
            onPressed: _loading ? null : _reload,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _openNew,
        backgroundColor: _accent,
        child: const Icon(Icons.add_rounded),
      ),
      body: Column(
        children: [
          if (_localDraft != null)
            TransactionDraftBanner(
              title: 'Continue draft',
              subtitle: _localDraftSubtitle(_localDraft!),
              accent: _accent,
              onContinue: _continueLocalDraft,
              onDismiss: _dismissLocalDraft,
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search voucher no, ref, narration…',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _search.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          _search.clear();
                          _reload();
                        },
                      )
                    : null,
                isDense: true,
                filled: false,
                border: const UnderlineInputBorder(),
                enabledBorder: UnderlineInputBorder(
                  borderSide: BorderSide(color: Colors.grey.shade400),
                ),
                focusedBorder: const UnderlineInputBorder(
                  borderSide: BorderSide(color: _accent, width: 2),
                ),
              ),
              onChanged: (_) => _scheduleSearch(),
              onSubmitted: (_) => _reload(),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (var i = 0; i < _tabs.length; i++) ...[
                    _CpvStatusTab(
                      label: _tabs[i].$2,
                      active: _tabKey == _tabs[i].$1,
                      onTap: () {
                        if (_tabKey == _tabs[i].$1) return;
                        setState(() => _tabKey = _tabs[i].$1);
                        _reload();
                      },
                    ),
                    if (i < _tabs.length - 1) const SizedBox(width: 20),
                  ],
                ],
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: _accent))
                : _error != null
                    ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _reload)
                    : _rows.isEmpty
                        ? Center(
                            child: Text(
                              _emptyMessage(),
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.grey.shade600),
                            ),
                          )
                        : RefreshIndicator(
                            color: _accent,
                            onRefresh: _reload,
                            child: ListView.separated(
                              padding: const EdgeInsets.fromLTRB(14, 8, 14, 94),
                              itemCount: _rows.length,
                              separatorBuilder: (_, __) => const SizedBox(height: 9),
                              itemBuilder: (_, i) => _CpvCard(
                                row: _rows[i],
                                onTap: () => _openDetail(_rows[i]),
                              ),
                            ),
                          ),
          ),
        ],
      ),
    );
  }
}

class _CpvStatusTab extends StatelessWidget {
  const _CpvStatusTab({
    required this.label,
    required this.active,
    required this.onTap,
  });

  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: active ? FontWeight.w700 : FontWeight.w500,
              color: active ? const Color(0xFF00897B) : const Color(0xFF6F7482),
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 28,
            height: 2,
            color: active ? const Color(0xFF00897B) : Colors.transparent,
          ),
        ],
      ),
    );
  }
}

class _CpvCard extends StatelessWidget {
  const _CpvCard({required this.row, required this.onTap});

  final CpvSummary row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final status = row.status.isEmpty ? 'DRAFT' : row.status;
    final (statusBg, statusFg, stripeColor) = switch (status) {
      'POSTED' => (
          const Color(0xFFE8F5E9),
          const Color(0xFF2E7D32),
          const Color(0xFF66BB6A),
        ),
      _ => (
          const Color(0xFFE0F2F1),
          const Color(0xFF00695C),
          const Color(0xFF00897B),
        ),
    };

    final chipLabel = status == 'POSTED' ? 'POSTED' : 'DRAFT';
    final subtitle = row.subtitle;

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: stripeColor, width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
        onTap: onTap,
        title: Text(
          row.voucherNo,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
        ),
        subtitle: subtitle.isNotEmpty
            ? Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13),
                ),
              )
            : null,
        trailing: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 108),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(color: statusBg, borderRadius: BorderRadius.circular(50)),
                child: Text(
                  chipLabel,
                  style: TextStyle(color: statusFg, fontSize: 10.5, fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                row.voucherDate.isEmpty ? '—' : row.voucherDate,
                style: const TextStyle(fontSize: 11, color: Color(0xFF6F7482), height: 1.0),
              ),
              const SizedBox(height: 2),
              Text(
                row.totalAmount.toStringAsFixed(2),
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF00897B),
                  height: 1.0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
