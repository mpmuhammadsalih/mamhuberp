import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../providers/auth_provider.dart';
import '../../services/stock_return_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/transaction_draft_banner.dart';
import 'inventory_transaction_draft.dart';
import 'stock_return_detail_screen.dart';
import 'stock_return_form_screen.dart';
import '../../core/theme/app_theme.dart';

class StockReturnListScreen extends StatefulWidget {
  const StockReturnListScreen({super.key});

  @override
  State<StockReturnListScreen> createState() => _StockReturnListScreenState();
}

class _StockReturnListScreenState extends State<StockReturnListScreen> {
  static const _accent = Color(0xFF1565C0);

  static const _tabs = [
    ('draft', 'Draft'),
    ('posted', 'Posted'),
  ];

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<StockReturnSummary> _rows = [];
  String _tabKey = 'draft';
  Map<String, dynamic>? _draft;

  @override
  void initState() {
    super.initState();
    _search.addListener(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDraftBanner();
      _reload();
    });
  }

  Future<void> _loadDraftBanner() async {
    final user = context.read<AuthProvider>().user;
    if (user == null) {
      if (mounted) setState(() => _draft = null);
      return;
    }
    final draft = await TransactionDraftStorage.read(
      docType: TransactionDraftType.purchaseReturn,
      tenantId: user.tenantId ?? '',
      username: user.username,
    );
    if (!mounted) return;
    setState(() => _draft = draft);
  }

  Future<void> _dismissDraft() async {
    final user = context.read<AuthProvider>().user;
    if (user != null) {
      await TransactionDraftStorage.clear(
        docType: TransactionDraftType.purchaseReturn,
        tenantId: user.tenantId ?? '',
        username: user.username,
      );
    }
    if (mounted) setState(() => _draft = null);
  }

  Future<void> _continueDraft() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => const StockReturnFormScreen(restoreDraft: true),
      ),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    if (saved == true) _reload();
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
      final rows = await context.read<StockReturnService>().listReturns(
            q: _search.text.trim(),
            tab: _tabKey,
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

  Future<void> _openDetail(StockReturnSummary row) async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => StockReturnDetailScreen(
          returnNo: row.returnNo,
          rowKind: row.rowKind,
        ),
      ),
    );
    if (mounted) _reload();
  }

  Future<void> _openNew() async {
    if (_draft != null) {
      final action = await showPendingDraftAlert(
        context,
        summary: InventoryTransactionDraft.summaryLabel(_draft!),
        documentLabel: 'purchase return',
      );
      if (!mounted) return;
      if (action == PendingDraftAction.cancel) return;
      if (action == PendingDraftAction.continuePending) {
        await _continueDraft();
        return;
      }
      await _dismissDraft();
    }
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const StockReturnFormScreen()),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    if (saved == true) _reload();
  }

  String _emptyMessage() {
    if (_search.text.trim().isNotEmpty) {
      return 'No purchase returns match your search.';
    }
    return switch (_tabKey) {
      'posted' => 'No posted purchase returns.',
      _ => 'No draft purchase returns.\nTap + to create one.',
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
        title: const Text('Purchase Returns', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
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
          if (_draft != null)
            TransactionDraftBanner(
              title: 'Continue draft',
              subtitle: InventoryTransactionDraft.summaryLabel(_draft!),
              accent: _accent,
              onContinue: _continueDraft,
              onDismiss: _dismissDraft,
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search RT no, supplier…',
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
                    _RtStatusTab(
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
                              itemBuilder: (_, i) => _RtCard(
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

class _RtStatusTab extends StatelessWidget {
  const _RtStatusTab({
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
              color: active ? const Color(0xFF1565C0) : const Color(0xFF6F7482),
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 28,
            height: 2,
            color: active ? const Color(0xFF1565C0) : Colors.transparent,
          ),
        ],
      ),
    );
  }
}

class _RtCard extends StatelessWidget {
  const _RtCard({required this.row, required this.onTap});

  final StockReturnSummary row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final status = row.approvalStatus.isEmpty ? 'DRAFT' : row.approvalStatus;
    final (statusBg, statusFg, stripeColor) = switch (status) {
      'POSTED' || 'APPROVED' => (
          const Color(0xFFE8F5E9),
          const Color(0xFF2E7D32),
          const Color(0xFF66BB6A),
        ),
      'CANCELLED' || 'CANCELED' => (
          const Color(0xFFFFEBEE),
          const Color(0xFFC62828),
          const Color(0xFFE57373),
        ),
      _ => (
          const Color(0xFFFFF3E0),
          const Color(0xFFE65100),
          const Color(0xFFFFB74D),
        ),
    };

    final chipLabel = switch (status) {
      'CANCELLED' || 'CANCELED' => 'CANCELED',
      'POSTED' || 'APPROVED' => 'POSTED',
      _ => 'DRAFT',
    };

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
        title: Text('PR-${row.returnNo}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                row.supplierLabel,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13),
              ),
              if (row.supplierCode.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  'Code ${row.supplierCode}',
                  style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12.5),
                ),
              ],
            ],
          ),
        ),
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
                row.returnDate.isEmpty ? '—' : row.returnDate,
                style: const TextStyle(fontSize: 11, color: Color(0xFF6F7482), height: 1.0),
              ),
              const SizedBox(height: 2),
              Text(
                row.amount.toStringAsFixed(2),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF3E63F5), height: 1.0),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
