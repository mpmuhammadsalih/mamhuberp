import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/party_ledger_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_overlay.dart';
import 'accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

class CustomerLedgerScreen extends StatelessWidget {
  const CustomerLedgerScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      const PartyLedgerListScreen(kind: PartyLedgerKind.customer);
}

class SupplierLedgerScreen extends StatelessWidget {
  const SupplierLedgerScreen({super.key});

  @override
  Widget build(BuildContext context) =>
      const PartyLedgerListScreen(kind: PartyLedgerKind.supplier);
}

class PartyLedgerListScreen extends StatefulWidget {
  const PartyLedgerListScreen({super.key, required this.kind});

  final PartyLedgerKind kind;

  @override
  State<PartyLedgerListScreen> createState() => _PartyLedgerListScreenState();
}

class _PartyLedgerListScreenState extends State<PartyLedgerListScreen> {
  static const _bg = Color(0xFFF4F5F8);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<PartyLedgerParty> _parties = [];

  bool get _isCustomer => widget.kind == PartyLedgerKind.customer;
  Color get _accent => _isCustomer ? const Color(0xFF1565C0) : const Color(0xFF2E7D32);
  String get _title => _isCustomer ? 'Customer Ledger' : 'Supplier Ledger';
  String get _partyLabel => _isCustomer ? 'customer' : 'supplier';

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
      final rows = await context.read<PartyLedgerService>().listParties(
            widget.kind,
            q: _search.text.trim(),
          );
      if (!mounted) return;
      setState(() {
        _parties = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _parties = [];
        _loading = false;
      });
    }
  }

  void _openStatement(PartyLedgerParty party) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => PartyLedgerStatementScreen(
          kind: widget.kind,
          partyCode: party.partyCode,
          partyName: party.displayName,
        ),
      ),
    );
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
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: TextField(
                controller: _search,
                decoration: InputDecoration(
                  hintText: 'Search $_partyLabel code or name…',
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
            ),
          ),
          if (_error != null)
            ApiErrorBanner(
              message: _error!,
              error: _errorCause,
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _parties.isEmpty
                    ? Center(
                        child: Text(
                          _error != null ? '' : 'No ${_partyLabel}s found.',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: _reload,
                        child: ListView.separated(
                          padding: const EdgeInsets.fromLTRB(12, 10, 12, 88),
                          itemCount: _parties.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 8),
                          itemBuilder: (context, i) {
                            final p = _parties[i];
                            return Material(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              child: InkWell(
                                borderRadius: BorderRadius.circular(12),
                                onTap: () => _openStatement(p),
                                child: Ink(
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(12),
                                    border: Border.all(color: const Color(0xFFE8EBF3)),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 40,
                                          height: 40,
                                          decoration: BoxDecoration(
                                            borderRadius: BorderRadius.circular(10),
                                            color: _accent.withValues(alpha: 0.1),
                                          ),
                                          child: Icon(
                                            _isCustomer
                                                ? Icons.person_outline_rounded
                                                : Icons.storefront_outlined,
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
                                                p.displayName,
                                                style: const TextStyle(
                                                  fontWeight: FontWeight.w700,
                                                  fontSize: 14.5,
                                                ),
                                              ),
                                              const SizedBox(height: 2),
                                              Text(
                                                p.glAccount.isNotEmpty
                                                    ? '${p.partyCode} · GL ${p.glAccount}'
                                                    : p.partyCode,
                                                style: TextStyle(
                                                  fontSize: 12.5,
                                                  color: Colors.grey.shade600,
                                                ),
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
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}

class PartyLedgerStatementScreen extends StatefulWidget {
  const PartyLedgerStatementScreen({
    super.key,
    required this.kind,
    required this.partyCode,
    this.partyName = '',
  });

  final PartyLedgerKind kind;
  final String partyCode;
  final String partyName;

  @override
  State<PartyLedgerStatementScreen> createState() => _PartyLedgerStatementScreenState();
}

class _PartyLedgerStatementScreenState extends State<PartyLedgerStatementScreen> {
  static const _bg = Color(0xFFF6F7FC);

  late DateTime _from;
  late DateTime _to;
  bool _loading = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  PartyLedgerStatement? _statement;

  bool get _isCustomer => widget.kind == PartyLedgerKind.customer;
  Color get _accent => _isCustomer ? const Color(0xFF1565C0) : const Color(0xFF2E7D32);

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = DateTime(now.year, 1, 1);
    _to = DateTime(now.year, now.month, now.day);
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final stmt = await context.read<PartyLedgerService>().getStatement(
            widget.kind,
            widget.partyCode,
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
          );
      if (!mounted) return;
      setState(() => _statement = stmt);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = handleApiError(context, e, authenticatedContext: true);
        _errorCause = e;
        _statement = null;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openPdf() async {
    final code = widget.partyCode;
    await openPdfBytes(
      context,
      loadBytes: () => context.read<PartyLedgerService>().downloadPdf(
            widget.kind,
            code,
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
          ),
      fileName: '${_isCustomer ? 'Customer' : 'Supplier'}_Ledger_$code.pdf',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _sharePdf() async {
    final code = widget.partyCode;
    final name = _statement?.displayName ?? widget.partyName;
    await sharePdfBytes(
      context,
      loadBytes: () => context.read<PartyLedgerService>().downloadPdf(
            widget.kind,
            code,
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
          ),
      fileName: '${_isCustomer ? 'Customer' : 'Supplier'}_Ledger_$code.pdf',
      subject: '${_isCustomer ? 'Customer' : 'Supplier'} Ledger — $name',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  @override
  Widget build(BuildContext context) {
    final stmt = _statement;
    final titleName = stmt?.displayName.isNotEmpty == true
        ? stmt!.displayName
        : (widget.partyName.isNotEmpty ? widget.partyName : widget.partyCode);

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
        title: Column(
          children: [
            Text(
              _isCustomer ? 'Customer Ledger' : 'Supplier Ledger',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            Text(
              titleName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, color: Colors.grey.shade600, fontWeight: FontWeight.w500),
            ),
          ],
        ),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Share PDF',
            onPressed: _pdfBusy || _loading ? null : _sharePdf,
            icon: const Icon(Icons.share_outlined, size: 20),
          ),
          IconButton(
            tooltip: 'PDF',
            onPressed: _pdfBusy || _loading ? null : _openPdf,
            icon: _pdfBusy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.picture_as_pdf_outlined, size: 22),
          ),
        ],
      ),
      body: LoadingOverlay(
        loading: _pdfBusy,
        child: Column(
          children: [
            Material(
              color: Colors.white,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Wrap(
                      spacing: 8,
                      runSpacing: 6,
                      children: [
                        ReportFilterChip(
                          label: 'From ${isoDate(_from)}',
                          onTap: () => pickReportDate(
                            context,
                            initial: _from,
                            onPicked: (d) => setState(() => _from = d),
                          ),
                        ),
                        ReportFilterChip(
                          label: 'To ${isoDate(_to)}',
                          onTap: () => pickReportDate(
                            context,
                            initial: _to,
                            onPicked: (d) => setState(() => _to = d),
                          ),
                        ),
                        ActionChip(
                          label: const Text('Apply', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700)),
                          onPressed: _loading ? null : _load,
                          backgroundColor: _accent.withValues(alpha: 0.12),
                          side: BorderSide(color: _accent.withValues(alpha: 0.35)),
                          labelStyle: TextStyle(color: _accent),
                        ),
                      ],
                    ),
                    if (stmt != null) ...[
                      const SizedBox(height: 10),
                      _SummaryStrip(
                        accent: _accent,
                        opening: stmt.openingBalance,
                        debit: stmt.totalDebit,
                        credit: stmt.totalCredit,
                        closing: stmt.closingBalance,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            if (_error != null)
              ApiErrorBanner(
                message: _error!,
                error: _errorCause,
              ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : stmt == null
                      ? Center(
                          child: Text(
                            _error != null ? '' : 'No ledger data.',
                            style: TextStyle(color: Colors.grey.shade600),
                          ),
                        )
                      : RefreshIndicator(
                          onRefresh: _load,
                          child: ListView.builder(
                            padding: const EdgeInsets.fromLTRB(12, 10, 12, 88),
                            itemCount: stmt.lines.isEmpty ? 1 : stmt.lines.length + 1,
                            itemBuilder: (context, i) {
                              if (stmt.lines.isEmpty) {
                                return Padding(
                                  padding: const EdgeInsets.only(top: 40),
                                  child: Center(
                                    child: Text(
                                      'No movements in this period.\nOpening ${fmtMoney(stmt.openingBalance)}',
                                      textAlign: TextAlign.center,
                                      style: TextStyle(color: Colors.grey.shade600, height: 1.4),
                                    ),
                                  ),
                                );
                              }
                              if (i == 0) {
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Text(
                                    '${stmt.lines.length} line${stmt.lines.length == 1 ? '' : 's'}'
                                    '${stmt.glAccount.isNotEmpty ? ' · GL ${stmt.glAccount}' : ''}',
                                    style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                                  ),
                                );
                              }
                              final line = stmt.lines[i - 1];
                              return _LedgerLineTile(line: line, accent: _accent);
                            },
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SummaryStrip extends StatelessWidget {
  const _SummaryStrip({
    required this.accent,
    required this.opening,
    required this.debit,
    required this.credit,
    required this.closing,
  });

  final Color accent;
  final double opening;
  final double debit;
  final double credit;
  final double closing;

  @override
  Widget build(BuildContext context) {
    Widget cell(String label, double value, {bool emphasize = false}) {
      return Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
            const SizedBox(height: 2),
            Text(
              fmtMoney(value),
              style: TextStyle(
                fontSize: emphasize ? 14 : 13,
                fontWeight: emphasize ? FontWeight.w800 : FontWeight.w700,
                color: emphasize ? accent : const Color(0xFF262C50),
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F8FC),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Row(
        children: [
          cell('Opening', opening),
          cell('Debit', debit),
          cell('Credit', credit),
          cell('Closing', closing, emphasize: true),
        ],
      ),
    );
  }
}

class _LedgerLineTile extends StatelessWidget {
  const _LedgerLineTile({required this.line, required this.accent});

  final PartyLedgerLine line;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    final detail = [
      if (line.referenceNo.isNotEmpty) line.referenceNo,
      if (line.source.isNotEmpty) line.source,
      if (line.narration.isNotEmpty) line.narration,
    ].join(' · ');

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  line.voucherNo.isNotEmpty ? line.voucherNo : '—',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
                ),
              ),
              Text(
                line.voucherDate.isNotEmpty ? line.voucherDate : '—',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
            ],
          ),
          if (detail.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              detail,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700, height: 1.3),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  line.debit > 0 ? 'Dr ${fmtMoney(line.debit)}' : '—',
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600,
                    color: line.debit > 0 ? const Color(0xFFC62828) : Colors.grey.shade400,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  line.credit > 0 ? 'Cr ${fmtMoney(line.credit)}' : '—',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600,
                    color: line.credit > 0 ? const Color(0xFF2E7D32) : Colors.grey.shade400,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  fmtMoney(line.runningBalance),
                  textAlign: TextAlign.end,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: accent,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
