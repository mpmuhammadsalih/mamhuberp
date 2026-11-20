import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_message.dart';
import '../../services/accounts_reports_service.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/provider_error_body.dart';
import 'accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

class TrialBalanceScreen extends StatefulWidget {
  const TrialBalanceScreen({super.key});

  @override
  State<TrialBalanceScreen> createState() => _TrialBalanceScreenState();
}

class _TrialBalanceScreenState extends State<TrialBalanceScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _accent = Color(0xFF00897B);

  late DateTime _from;
  late DateTime _to;
  bool _excludeClosing = true;
  bool _loading = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  TrialBalanceReport? _report;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = monthStart(now);
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
      final report = await context.read<AccountsReportsService>().getTrialBalance(
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
            excludeClosing: _excludeClosing,
          );
      if (!mounted) return;
      setState(() => _report = report);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(e, authenticatedContext: true);
        _errorCause = e;
        _report = null;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openPdf() async {
    await openPdfBytes(
      context,
      loadBytes: () => context.read<AccountsReportsService>().downloadTrialBalancePdf(
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
            excludeClosing: _excludeClosing,
          ),
      fileName: 'Trial_Balance_${isoDate(_to)}.pdf',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _sharePdf() async {
    await sharePdfBytes(
      context,
      loadBytes: () => context.read<AccountsReportsService>().downloadTrialBalancePdf(
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
            excludeClosing: _excludeClosing,
          ),
      fileName: 'Trial_Balance_${isoDate(_to)}.pdf',
      subject: 'Trial Balance',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  @override
  Widget build(BuildContext context) {
    final report = _report;
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Trial Balance', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
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
                        FilterChip(
                          label: const Text('Exclude closing', style: TextStyle(fontSize: 12.5)),
                          selected: _excludeClosing,
                          onSelected: (v) => setState(() => _excludeClosing = v),
                          selectedColor: _accent.withValues(alpha: 0.15),
                          checkmarkColor: _accent,
                        ),
                        FilledButton(
                          onPressed: _loading ? null : _load,
                          style: FilledButton.styleFrom(
                            backgroundColor: _accent,
                            visualDensity: VisualDensity.compact,
                          ),
                          child: const Text('Run'),
                        ),
                      ],
                    ),
                    if (report != null) ...[
                      const SizedBox(height: 6),
                      Text(
                        report.periodDisplay,
                        style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            Expanded(child: _body(report)),
          ],
        ),
      ),
    );
  }

  Widget _body(TrialBalanceReport? report) {
    if (_loading && report == null) {
      return const Center(child: AppLoadingIndicator());
    }
    if (_error != null && report == null) {
      return ProviderErrorBody(message: _error!, errorCause: _errorCause, onRetry: _load);
    }
    if (report == null) return const SizedBox.shrink();
    if (report.rows.isEmpty) {
      return Center(child: Text('No balances for this period.', style: TextStyle(color: Colors.grey.shade600)));
    }

    return RefreshIndicator(
      color: _accent,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 28),
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: Row(
              children: [
                Expanded(child: _totalTile('Total Debit', report.totalDebit, const Color(0xFF1565C0))),
                Container(width: 1, height: 36, color: const Color(0xFFE8EBF3)),
                Expanded(child: _totalTile('Total Credit', report.totalCredit, const Color(0xFF2E7D32))),
              ],
            ),
          ),
          const SizedBox(height: 10),
          ...report.rows.map((r) {
            return Container(
              margin: const EdgeInsets.only(bottom: 6),
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE8EBF3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${r.code}  ${r.name}',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Expanded(child: Text('Dr ${fmtMoney(r.debit)}', style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700))),
                      Expanded(child: Text('Cr ${fmtMoney(r.credit)}', style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700))),
                      Text(
                        'Bal ${fmtMoney(r.balance)}',
                        style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _totalTile(String label, double value, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Column(
        children: [
          Text(label, style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600)),
          const SizedBox(height: 2),
          Text(
            fmtMoney(value),
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: color),
          ),
        ],
      ),
    );
  }
}
