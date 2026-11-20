import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../providers/auth_provider.dart';
import '../../services/journal_entry_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/transaction_draft_banner.dart';
import 'accounts_report_helpers.dart';
import 'journal_entry_detail_screen.dart';
import 'journal_entry_form_screen.dart';
import '../../core/theme/app_theme.dart';

class JournalEntryListScreen extends StatefulWidget {
  const JournalEntryListScreen({super.key});

  @override
  State<JournalEntryListScreen> createState() => _JournalEntryListScreenState();
}

class _JournalEntryListScreenState extends State<JournalEntryListScreen> {
  static const _accent = Color(0xFF6A1B9A);
  static const _bg = Color(0xFFF4F5F8);

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
  List<JeSummary> _rows = [];
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
      docType: TransactionDraftType.journalEntry,
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
        docType: TransactionDraftType.journalEntry,
        tenantId: user.tenantId ?? '',
        username: user.username,
      );
    }
    if (mounted) setState(() => _localDraft = null);
  }

  Future<void> _continueLocalDraft() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => const JournalEntryFormScreen(restoreDraft: true),
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
    if (lines > 0) return 'Journal · $lines line${lines == 1 ? '' : 's'}';
    return 'Unfinished journal entry';
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
      final rows = await context.read<JournalEntryService>().listJournals(
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

  Future<void> _openDetail(JeSummary row) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => JournalEntryDetailScreen(docId: row.docKey),
      ),
    );
    if (mounted) _reload();
  }

  Future<void> _openNew() async {
    if (_localDraft != null) {
      final action = await showPendingDraftAlert(
        context,
        summary: _localDraftSubtitle(_localDraft!),
        documentLabel: 'journal entry',
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
      MaterialPageRoute<bool>(builder: (_) => const JournalEntryFormScreen()),
    );
    if (!mounted) return;
    await _loadLocalDraftBanner();
    if (saved == true) _reload();
  }

  @override
  Widget build(BuildContext context) {
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
        title: const Text('Journal Entry', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(onPressed: _loading ? null : _reload, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNew,
        backgroundColor: _accent,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_rounded),
        label: const Text('New Journal'),
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
          Material(
            color: Colors.white,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _search,
                    decoration: InputDecoration(
                      hintText: 'Search voucher, ref, narration…',
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
                      border: const UnderlineInputBorder(),
                      focusedBorder: const UnderlineInputBorder(
                        borderSide: BorderSide(color: _accent, width: 2),
                      ),
                    ),
                    onChanged: (_) => _scheduleSearch(),
                    onSubmitted: (_) => _reload(),
                  ),
                  const SizedBox(height: 10),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        for (final tab in _tabs)
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(tab.$2, style: const TextStyle(fontSize: 12.5)),
                              selected: _tabKey == tab.$1,
                              selectedColor: _accent.withValues(alpha: 0.15),
                              labelStyle: TextStyle(
                                color: _tabKey == tab.$1 ? _accent : const Color(0xFF5A6275),
                                fontWeight: _tabKey == tab.$1 ? FontWeight.w700 : FontWeight.w500,
                              ),
                              onSelected: (_) {
                                setState(() => _tabKey = tab.$1);
                                _reload();
                              },
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _rows.isEmpty
                    ? Center(
                        child: Text(
                          _error != null ? '' : 'No journal entries found.',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: _reload,
                        child: ListView.separated(
                          padding: const EdgeInsets.fromLTRB(12, 10, 12, 100),
                          itemCount: _rows.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 8),
                          itemBuilder: (context, i) {
                            final row = _rows[i];
                            return Material(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              child: InkWell(
                                borderRadius: BorderRadius.circular(12),
                                onTap: () => _openDetail(row),
                                child: Ink(
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(color: const Color(0xFFE8EBF3)),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          children: [
                                            Expanded(
                                              child: Text(
                                                row.voucherNo,
                                                style: const TextStyle(
                                                  fontWeight: FontWeight.w800,
                                                  fontSize: 14.5,
                                                ),
                                              ),
                                            ),
                                            _StatusChip(status: row.status, source: row.source),
                                          ],
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          [
                                            if (row.voucherDate.isNotEmpty) row.voucherDate,
                                            if (row.referenceNo.isNotEmpty) 'Ref ${row.referenceNo}',
                                            if (row.source.isNotEmpty && !row.isDraft) row.source,
                                          ].join(' · '),
                                          style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                                        ),
                                        if (row.narration.isNotEmpty) ...[
                                          const SizedBox(height: 4),
                                          Text(
                                            row.narration,
                                            maxLines: 2,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(fontSize: 13, color: Colors.grey.shade800),
                                          ),
                                        ],
                                        const SizedBox(height: 8),
                                        Row(
                                          children: [
                                            Text(
                                              'Dr ${fmtMoney(row.totalDebit)}',
                                              style: const TextStyle(
                                                fontSize: 12.5,
                                                fontWeight: FontWeight.w700,
                                                color: Color(0xFFC62828),
                                              ),
                                            ),
                                            const SizedBox(width: 14),
                                            Text(
                                              'Cr ${fmtMoney(row.totalCredit)}',
                                              style: const TextStyle(
                                                fontSize: 12.5,
                                                fontWeight: FontWeight.w700,
                                                color: Color(0xFF2E7D32),
                                              ),
                                            ),
                                            const Spacer(),
                                            Text(
                                              '${row.lineCount} lines',
                                              style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status, required this.source});

  final String status;
  final String source;

  @override
  Widget build(BuildContext context) {
    final isDraft = status == 'DRAFT';
    final color = isDraft ? const Color(0xFFEF6C00) : const Color(0xFF2E7D32);
    final label = isDraft ? 'DRAFT' : (source.isNotEmpty && source != 'MANUAL' ? source : 'POSTED');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: color),
      ),
    );
  }
}
