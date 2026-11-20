import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_message.dart';
import '../../services/accounts_reports_service.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/provider_error_body.dart';
import 'accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

class BalanceSheetScreen extends StatefulWidget {
  const BalanceSheetScreen({super.key});

  @override
  State<BalanceSheetScreen> createState() => _BalanceSheetScreenState();
}

class _BalanceSheetScreenState extends State<BalanceSheetScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _accent = Color(0xFF1565C0);

  late DateTime _asOf;
  bool _loading = false;
  bool _pdfBusy = false;
  String? _error;
  Object? _errorCause;
  BalanceSheetReport? _report;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _asOf = DateTime(now.year, now.month, now.day);
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final report = await context.read<AccountsReportsService>().getBalanceSheet(
            asOfDate: isoDate(_asOf),
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
      loadBytes: () => context.read<AccountsReportsService>().downloadBalanceSheetPdf(
            asOfDate: isoDate(_asOf),
          ),
      fileName: 'Balance_Sheet_${isoDate(_asOf)}.pdf',
      isMounted: () => mounted,
      setBusy: (b) => setState(() => _pdfBusy = b),
    );
  }

  Future<void> _sharePdf() async {
    await sharePdfBytes(
      context,
      loadBytes: () => context.read<AccountsReportsService>().downloadBalanceSheetPdf(
            asOfDate: isoDate(_asOf),
          ),
      fileName: 'Balance_Sheet_${isoDate(_asOf)}.pdf',
      subject: 'Balance Sheet',
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
        title: const Text('Balance Sheet', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
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
                child: Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    ReportFilterChip(
                      label: 'As of ${isoDate(_asOf)}',
                      onTap: () => pickReportDate(
                        context,
                        initial: _asOf,
                        onPicked: (d) => setState(() => _asOf = d),
                      ),
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
              ),
            ),
            Expanded(child: _body(report)),
          ],
        ),
      ),
    );
  }

  Widget _body(BalanceSheetReport? report) {
    if (_loading && report == null) {
      return const Center(child: AppLoadingIndicator());
    }
    if (_error != null && report == null) {
      return ProviderErrorBody(message: _error!, errorCause: _errorCause, onRetry: _load);
    }
    if (report == null) return const SizedBox.shrink();

    return RefreshIndicator(
      color: _accent,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 28),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  report.companyName.isNotEmpty ? report.companyName : 'Balance Sheet',
                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15),
                ),
                const SizedBox(height: 4),
                Text(
                  report.asOfDateDisplay.isNotEmpty
                      ? 'As of ${report.asOfDateDisplay}'
                      : 'As of ${report.asOfDate}',
                  style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(child: _kpi('Assets', report.totalAssets, _accent)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _kpi('Liab. + Equity', report.liabilitiesPlusEquity, const Color(0xFF2E7D32)),
                    ),
                  ],
                ),
                if (report.difference.abs() >= 0.01) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Difference: ${fmtMoney(report.difference)}',
                    style: const TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFFC62828),
                    ),
                  ),
                ],
              ],
            ),
          ),
          _section('Assets', report.assetAccounts, report.totalAssets),
          _section('Liabilities', report.liabilityAccounts, report.totalLiabilities),
          _section('Equity', report.equityAccounts, report.totalEquity),
          Container(
            margin: const EdgeInsets.only(top: 8),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: ReportAmountRow(
              label: 'Liabilities + Equity',
              amount: report.liabilitiesPlusEquity,
              bold: true,
            ),
          ),
        ],
      ),
    );
  }

  Widget _kpi(String label, double value, Color color) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 11.5, color: Colors.grey.shade700)),
          const SizedBox(height: 4),
          Text(
            fmtMoney(value),
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: color),
          ),
        ],
      ),
    );
  }

  Widget _section(String title, List<BalanceSheetRow> rows, double total) {
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ReportSectionHeader(title, trailing: fmtMoney(total)),
          if (rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Text('No lines', style: TextStyle(color: Colors.grey.shade500, fontSize: 12.5)),
            )
          else
            ...rows.map(
              (r) => ReportAmountRow(
                label: r.isGroup ? '▸ ${r.name}' : r.name,
                code: r.code,
                amount: r.amount,
                indent: r.depth,
                bold: r.isGroup,
                muted: r.isGroup && r.amount == 0,
              ),
            ),
        ],
      ),
    );
  }
}
