import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/pos_settlement_service.dart';
import '../../widgets/api_error_banner.dart';
import 'pos_settlement_detail_screen.dart';
import 'pos_settlement_workflow_screen.dart';
import '../../core/theme/app_theme.dart';

class PosSettlementListScreen extends StatefulWidget {
  const PosSettlementListScreen({super.key});

  @override
  State<PosSettlementListScreen> createState() => _PosSettlementListScreenState();
}

class _PosSettlementListScreenState extends State<PosSettlementListScreen>
    with SingleTickerProviderStateMixin {
  static const _accent = Color(0xFF5E35B1);
  static const _navy = Color(0xFF262C50);

  late final TabController _tabs;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<PosSettlementPendingDay> _days = [];
  List<PosSettlementDraftSummary> _drafts = [];

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<PosSettlementService>();
      final days = await svc.listPendingByDate();
      final drafts = await svc.listDrafts();
      if (!mounted) return;
      setState(() {
        _days = days;
        _drafts = drafts;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _days = [];
        _drafts = [];
        _loading = false;
      });
    }
  }

  Future<void> _openNew({String? billDate}) async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => PosSettlementWorkflowScreen(initialDate: billDate),
      ),
    );
    if (mounted) _reload();
  }

  Future<void> _openDraft(PosSettlementDraftSummary row) async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => PosSettlementDetailScreen(draftId: row.draftId),
      ),
    );
    if (mounted) _reload();
  }

  String _money(double v) => v.toStringAsFixed(2);

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
        title: const Text('POS Settlement', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        bottom: TabBar(
          controller: _tabs,
          labelColor: _accent,
          unselectedLabelColor: Colors.grey.shade600,
          indicatorColor: _accent,
          tabs: const [
            Tab(text: 'Pending'),
            Tab(text: 'Drafts'),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _openNew(),
        backgroundColor: _accent,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_rounded),
        label: const Text('New Settlement'),
      ),
      body: Column(
        children: [
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
          Expanded(
            child: RefreshIndicator(
              color: _accent,
              onRefresh: _reload,
              child: TabBarView(
                controller: _tabs,
                children: [
                  _pendingList(),
                  _draftsList(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _pendingList() {
    if (_loading && _days.isEmpty) {
      return const Center(child: CircularProgressIndicator(color: _accent));
    }
    if (_days.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Icon(Icons.event_available_outlined, size: 48, color: Colors.grey.shade400),
          const SizedBox(height: 12),
          Center(child: Text('No pending POS bills.', style: TextStyle(color: Colors.grey.shade600))),
        ],
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 88),
      itemCount: _days.length,
      itemBuilder: (context, i) {
        final d = _days[i];
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => _openNew(billDate: d.billDate),
              child: Container(
                padding: const EdgeInsets.fromLTRB(14, 14, 10, 14),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE8EBF3)),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: const Color(0xFFEDE7F6),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(Icons.calendar_today_outlined, color: _accent, size: 20),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            d.billDate,
                            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: _navy),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${d.billCount} bill${d.billCount == 1 ? '' : 's'} · ${_money(d.netAmount)}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        ],
                      ),
                    ),
                    Icon(Icons.chevron_right_rounded, color: Colors.grey.shade400),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _draftsList() {
    if (_loading && _drafts.isEmpty) {
      return const Center(child: CircularProgressIndicator(color: _accent));
    }
    if (_drafts.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Icon(Icons.folder_open_outlined, size: 48, color: Colors.grey.shade400),
          const SizedBox(height: 12),
          Center(child: Text('No settlement drafts.', style: TextStyle(color: Colors.grey.shade600))),
        ],
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 88),
      itemCount: _drafts.length,
      itemBuilder: (context, i) {
        final d = _drafts[i];
        final statusColor = switch (d.status) {
          'POSTED' => const Color(0xFF2E7D32),
          'VERIFIED' => const Color(0xFF1565C0),
          _ => const Color(0xFFEF6C00),
        };
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => _openDraft(d),
              child: Container(
                padding: const EdgeInsets.fromLTRB(14, 14, 10, 14),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE8EBF3)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            d.referenceNo.isNotEmpty ? d.referenceNo : 'Draft #${d.draftId}',
                            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14.5, color: _navy),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            [
                              '${d.billCount} bills',
                              if (d.voucherNo.isNotEmpty) d.voucherNo,
                              if (d.createdAt.isNotEmpty) d.createdAt,
                            ].join(' · '),
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: statusColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(99),
                      ),
                      child: Text(
                        d.status,
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: statusColor),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
