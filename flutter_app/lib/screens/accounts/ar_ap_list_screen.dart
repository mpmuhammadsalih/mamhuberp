import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/ar_ap_service.dart';
import '../../widgets/api_error_banner.dart';
import 'ar_ap_detail_screen.dart';
import '../../core/theme/app_theme.dart';

enum ArApKind { receivable, payable }

class AccountsReceivableListScreen extends StatelessWidget {
  const AccountsReceivableListScreen({super.key});

  @override
  Widget build(BuildContext context) => const _ArApListScreen(kind: ArApKind.receivable);
}

class AccountsPayableListScreen extends StatelessWidget {
  const AccountsPayableListScreen({super.key});

  @override
  Widget build(BuildContext context) => const _ArApListScreen(kind: ArApKind.payable);
}

class _ArApListScreen extends StatefulWidget {
  const _ArApListScreen({required this.kind});

  final ArApKind kind;

  @override
  State<_ArApListScreen> createState() => _ArApListScreenState();
}

class _ArApListScreenState extends State<_ArApListScreen> {
  static const _bg = Color(0xFFF4F5F8);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<ArApPartyRow> _rows = [];
  ArApTotals _totals = const ArApTotals();
  String _balance = 'positive';

  bool get _isAr => widget.kind == ArApKind.receivable;
  Color get _accent => _isAr ? const Color(0xFF1565C0) : const Color(0xFF6A1B9A);
  String get _title => _isAr ? 'Accounts Receivable' : 'Accounts Payable';
  String get _partyLabel => _isAr ? 'customer' : 'supplier';

  @override
  void initState() {
    super.initState();
    _search.addListener(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
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
      final svc = context.read<ArApService>();
      final result = _isAr
          ? await svc.listReceivables(q: _search.text.trim(), balance: _balance)
          : await svc.listPayables(q: _search.text.trim(), balance: _balance);
      if (!mounted) return;
      setState(() {
        _rows = result.rows;
        _totals = result.totals;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _totals = const ArApTotals();
        _loading = false;
      });
    }
  }

  Future<void> _openDetail(ArApPartyRow row) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => ArApDetailScreen(kind: widget.kind, partyCode: row.partyCode),
      ),
    );
  }

  String _fmtAmt(double v) {
    final abs = v.abs();
    final s = abs >= 1000
        ? abs.toStringAsFixed(2).replaceAllMapped(
              RegExp(r'(\d)(?=(\d{3})+\.)'),
              (m) => '${m[1]},',
            )
        : abs.toStringAsFixed(2);
    if (v < 0) return '-$s';
    return s;
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
        title: Text(_title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(onPressed: _loading ? null : _reload, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      body: Column(
        children: [
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
                      hintText: 'Search code, name, location…',
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
                      focusedBorder: UnderlineInputBorder(
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
                        for (final opt in const [
                          ('positive', 'Outstanding'),
                          ('nonzero', 'Non-zero'),
                          ('all', 'All'),
                          ('zero', 'Zero'),
                          ('negative', 'Credit'),
                        ]) ...[
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(opt.$2, style: const TextStyle(fontSize: 12.5)),
                              selected: _balance == opt.$1,
                              selectedColor: _accent.withValues(alpha: 0.15),
                              labelStyle: TextStyle(
                                color: _balance == opt.$1 ? _accent : const Color(0xFF5A6275),
                                fontWeight: _balance == opt.$1 ? FontWeight.w700 : FontWeight.w500,
                              ),
                              onSelected: (_) {
                                setState(() => _balance = opt.$1);
                                _reload();
                              },
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  if (!_loading && _error == null) ...[
                    const SizedBox(height: 8),
                    Text(
                      '${_totals.count} $_partyLabel${_totals.count == 1 ? '' : 's'}'
                      '  ·  Total ${_fmtAmt(_totals.outstanding)}',
                      style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700, fontWeight: FontWeight.w600),
                    ),
                  ],
                ],
              ),
            ),
          ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading && _rows.isEmpty) {
      return Center(child: CircularProgressIndicator(color: _accent));
    }
    if (_error != null && _rows.isEmpty) {
      return ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _reload);
    }
    if (_rows.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(
            _search.text.trim().isNotEmpty
                ? 'No matches for your search.'
                : 'No $_partyLabel balances for this filter.\nSame data as ERP $_title.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey.shade600, height: 1.4),
          ),
        ),
      );
    }

    return RefreshIndicator(
      color: _accent,
      onRefresh: _reload,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
        itemCount: _rows.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          final row = _rows[i];
          final balColor = row.balance < 0
              ? const Color(0xFF2E7D32)
              : (row.balance > 0 ? const Color(0xFFC62828) : const Color(0xFF5A6275));
          return Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => _openDetail(row),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
                child: Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: _accent.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(
                        _isAr ? Icons.person_outline_rounded : Icons.storefront_outlined,
                        color: _accent,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            row.displayName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 14.5,
                              color: Color(0xFF262C50),
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            [
                              if (row.partyCode.isNotEmpty) row.partyCode,
                              if (row.locationCode.isNotEmpty) 'Loc ${row.locationCode}',
                              if (row.glAccount.isNotEmpty) 'A/C ${row.glAccount}',
                            ].join(' · '),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          _fmtAmt(row.balance),
                          style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 14.5,
                            color: balColor,
                          ),
                        ),
                        Icon(Icons.chevron_right_rounded, color: Colors.grey.shade400, size: 20),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
