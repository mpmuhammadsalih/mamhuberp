import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../models/stock_transfer.dart';
import '../../providers/auth_provider.dart';
import '../../services/stock_transfer_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/transaction_draft_banner.dart';
import 'inventory_transaction_draft.dart';
import 'stock_transfer_form_screen.dart';
import '../../core/theme/app_theme.dart';

class StockTransferListScreen extends StatefulWidget {
  const StockTransferListScreen({super.key});

  @override
  State<StockTransferListScreen> createState() => _StockTransferListScreenState();
}

class _StockTransferListScreenState extends State<StockTransferListScreen> {
  static const _accent = Color(0xFF5B3DF5);

  static const _tabKeys = ['created', 'transit', 'completed', 'all'];
  static const _tabLabels = ['To transfer', 'To approve', 'Completed', 'All'];

  final _searchController = TextEditingController();

  String _bucket = 'created';
  bool _loading = false;
  String? _error;
  Object? _errorCause;
  List<StockTransferSummary> _rows = [];
  Map<String, dynamic>? _draft;

  @override
  void initState() {
    super.initState();
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
      docType: TransactionDraftType.stockTransfer,
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
        docType: TransactionDraftType.stockTransfer,
        tenantId: user.tenantId ?? '',
        username: user.username,
      );
    }
    if (mounted) setState(() => _draft = null);
  }

  Future<void> _continueDraft() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => const StockTransferFormScreen(restoreDraft: true),
      ),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    _reload();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<StockTransferSummary> get _filteredRows {
    final q = _searchController.text.trim().toUpperCase();
    if (q.isEmpty) return _rows;
    return _rows.where((row) {
      final haystack = [
        row.transferNo,
        row.fromStore,
        row.toStore,
        row.statusLabel,
        row.transferDate,
        row.createdBy,
        row.remarks,
      ].join(' ').toUpperCase();
      return haystack.contains(q);
    }).toList();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<StockTransferService>();
      final rows = await svc.listTransfers(bucket: _bucket);
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

  Future<void> _openNewTransfer() async {
    if (_draft != null) {
      final action = await showPendingDraftAlert(
        context,
        summary: InventoryTransactionDraft.summaryLabel(
          _draft!,
          fallback: 'Stock Transfer',
        ),
        documentLabel: 'stock transfer',
      );
      if (!mounted) return;
      if (action == PendingDraftAction.cancel) return;
      if (action == PendingDraftAction.continuePending) {
        await _continueDraft();
        return;
      }
      await _dismissDraft();
    }
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => const StockTransferFormScreen(),
      ),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    _reload();
  }

  Future<void> _openTransfer(StockTransferSummary row) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => StockTransferFormScreen(transferNo: row.transferNo),
      ),
    );
    if (mounted) _reload();
  }

  String _emptyMessage() {
    if (_searchController.text.trim().isNotEmpty) {
      return 'No transfers match your search.';
    }
    return switch (_bucket) {
      'created' => 'No transfers waiting to send.\nTap New transfer to create one.',
      'transit' => 'No transfers awaiting approval.',
      'completed' => 'No completed transfers yet.',
      _ => 'No transfers found.',
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
        ),
        title: const Text('Stock Transfer', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(
            onPressed: _loading ? null : _reload,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_draft != null)
              TransactionDraftBanner(
                title: 'Continue draft',
                subtitle: InventoryTransactionDraft.summaryLabel(
                  _draft!,
                  fallback: 'Stock Transfer',
                ),
                accent: _accent,
                onContinue: _continueDraft,
                onDismiss: _dismissDraft,
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
              child: TextField(
                controller: _searchController,
                onChanged: (_) => setState(() {}),
                onSubmitted: (_) => setState(() {}),
                decoration: InputDecoration(
                  hintText: 'Search transfer no, store...',
                  hintStyle: const TextStyle(fontSize: 13),
                  prefixIcon: const Icon(Icons.search, size: 20),
                  filled: true,
                  fillColor: const Color(0xFFF4F5FA),
                  contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  for (var i = 0; i < _tabKeys.length; i++)
                    _TransferStatusTab(
                      _tabLabels[i],
                      _bucket == _tabKeys[i],
                      onTap: _loading
                          ? null
                          : () {
                              if (_bucket == _tabKeys[i]) return;
                              setState(() => _bucket = _tabKeys[i]);
                              _reload();
                            },
                    ),
                ],
              ),
            ),
            Expanded(
              child: _loading && _rows.isEmpty
                  ? const Center(child: CircularProgressIndicator())
                  : LoadingOverlay(
                      loading: _loading && _rows.isNotEmpty,
                      child: _buildBody(),
                    ),
            ),
          ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNewTransfer,
        backgroundColor: _accent,
        icon: const Icon(Icons.add_rounded),
        label: const Text('New transfer'),
      ),
    );
  }

  Widget _buildBody() {
    if (_error != null) {
      return ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _reload);
    }

    final rows = _filteredRows;
    if (rows.isEmpty) {
      return Center(
        child: Text(
          _emptyMessage(),
          textAlign: TextAlign.center,
          style: const TextStyle(color: Color(0xFF7C8191), height: 1.35),
        ),
      );
    }

    return RefreshIndicator(
      color: _accent,
      onRefresh: _reload,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 94),
        itemCount: rows.length,
        separatorBuilder: (_, __) => const SizedBox(height: 9),
        itemBuilder: (context, i) => _TransferCard(
          row: rows[i],
          onTap: () => _openTransfer(rows[i]),
        ),
      ),
    );
  }
}

class _TransferStatusTab extends StatelessWidget {
  const _TransferStatusTab(this.label, this.active, {required this.onTap});

  final String label;
  final bool active;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: 13,
                fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                color: active ? const Color(0xFF5B3DF5) : const Color(0xFF6F7482),
              ),
            ),
            const SizedBox(height: 6),
            Container(
              width: active ? 32 : 24,
              height: 2,
              decoration: BoxDecoration(
                color: active ? const Color(0xFF5B3DF5) : Colors.transparent,
                borderRadius: BorderRadius.circular(1),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TransferCard extends StatelessWidget {
  const _TransferCard({required this.row, required this.onTap});

  final StockTransferSummary row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    late final Color statusBg;
    late final Color statusFg;
    late final Color stripeColor;

    switch (row.status.toUpperCase()) {
      case 'C':
        statusBg = const Color(0xFFFFF5E9);
        statusFg = const Color(0xFFE38A18);
        stripeColor = const Color(0xFFFFA726);
        break;
      case 'T':
      case 'P':
        statusBg = const Color(0xFFEAF0FF);
        statusFg = const Color(0xFF3E63F5);
        stripeColor = const Color(0xFF3E63F5);
        break;
      case 'A':
        statusBg = const Color(0xFFE9F9EF);
        statusFg = const Color(0xFF1C9C58);
        stripeColor = const Color(0xFF1BBF6B);
        break;
      default:
        statusBg = const Color(0xFFF2F2F5);
        statusFg = const Color(0xFF6F7482);
        stripeColor = const Color(0xFF90A4AE);
    }

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: stripeColor, width: 3)),
        boxShadow: const [
          BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2)),
        ],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
        onTap: onTap,
        title: Text(
          row.transferNo,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${row.fromStore} → ${row.toStore}',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
              if (row.transferDate.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  row.transferDate,
                  style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12.5),
                ),
              ],
              if (row.createdBy.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  row.createdBy,
                  style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12),
                ),
              ],
            ],
          ),
        ),
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
          decoration: BoxDecoration(
            color: statusBg,
            borderRadius: BorderRadius.circular(50),
          ),
          child: Text(
            row.statusLabel,
            style: TextStyle(color: statusFg, fontSize: 10.5, fontWeight: FontWeight.w700),
          ),
        ),
      ),
    );
  }
}
