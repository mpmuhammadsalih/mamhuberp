import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/ar_ap_service.dart';
import '../../widgets/api_error_banner.dart';
import 'ar_ap_list_screen.dart';
import 'ar_ap_post_screen.dart';
import '../../core/theme/app_theme.dart';

class ArApDetailScreen extends StatefulWidget {
  const ArApDetailScreen({super.key, required this.kind, required this.partyCode});

  final ArApKind kind;
  final String partyCode;

  @override
  State<ArApDetailScreen> createState() => _ArApDetailScreenState();
}

class _ArApDetailScreenState extends State<ArApDetailScreen> {
  static const _bg = Color(0xFFF4F5F8);

  bool _loading = true;
  String? _error;
  Object? _errorCause;
  ArApPartyDetail? _detail;

  bool get _isAr => widget.kind == ArApKind.receivable;
  Color get _accent => _isAr ? const Color(0xFF1565C0) : const Color(0xFF6A1B9A);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final svc = context.read<ArApService>();
      final detail = _isAr
          ? await svc.getReceivableDetail(widget.partyCode)
          : await svc.getPayableDetail(widget.partyCode);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
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

  String _fmtDate(String iso) {
    if (iso.length < 10) return iso;
    final p = iso.substring(0, 10).split('-');
    if (p.length != 3) return iso;
    return '${p[2]}/${p[1]}/${p[0]}';
  }

  Future<void> _openPost() async {
    final posted = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => ArApPostScreen(kind: widget.kind, partyCode: widget.partyCode),
      ),
    );
    if (posted == true && mounted) _load();
  }

  @override
  Widget build(BuildContext context) {
    final d = _detail;
    return Scaffold(
      backgroundColor: _bg,
      floatingActionButton: d == null
          ? null
          : FloatingActionButton.extended(
              onPressed: _loading ? null : _openPost,
              backgroundColor: _accent,
              foregroundColor: Colors.white,
              icon: Icon(_isAr ? Icons.call_received_rounded : Icons.call_made_rounded),
              label: Text(_isAr ? 'Receive' : 'Pay'),
            ),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(
          d?.partyName.isNotEmpty == true ? d!.partyName : widget.partyCode,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        actions: [
          IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      body: _loading && d == null
          ? Center(child: CircularProgressIndicator(color: _accent))
          : _error != null && d == null
              ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
              : d == null
                  ? const Center(child: Text('Not found.'))
                  : RefreshIndicator(
                      color: _accent,
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
                        children: [
                          _headerCard(d),
                          const SizedBox(height: 14),
                          Text(
                            'Open documents',
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 15,
                              color: Colors.grey.shade800,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            _isAr
                                ? 'Same open invoices as ERP Accounts Receivable receipt.'
                                : 'Same open bills as ERP Accounts Payable payment.',
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          ),
                          const SizedBox(height: 10),
                          if (d.openDocuments.isEmpty)
                            Container(
                              padding: const EdgeInsets.all(20),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                'No open documents.',
                                textAlign: TextAlign.center,
                                style: TextStyle(color: Colors.grey.shade600),
                              ),
                            )
                          else
                            ...d.openDocuments.map(_docCard),
                        ],
                      ),
                    ),
    );
  }

  Widget _headerCard(ArApPartyDetail d) {
    final balColor = d.balance < 0
        ? const Color(0xFF2E7D32)
        : (d.balance > 0 ? const Color(0xFFC62828) : const Color(0xFF5A6275));
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _isAr ? 'Receivable balance' : 'Payable balance',
            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            _fmtAmt(d.balance),
            style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: balColor),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _metaChip('Code', d.partyCode),
              if (d.locationCode.isNotEmpty) _metaChip('Location', d.locationCode),
              if (d.glAccount.isNotEmpty) _metaChip('GL', d.glAccount),
              _metaChip('Open', _fmtAmt(d.openPayableTotal)),
              if (d.openCreditTotal > 0) _metaChip('Credits', _fmtAmt(d.openCreditTotal)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metaChip(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: _accent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: '$label  ',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
            ),
            TextSpan(
              text: value,
              style: TextStyle(fontSize: 12, color: _accent, fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }

  Widget _docCard(ArApOpenDoc doc) {
    final amtColor = doc.isCredit
        ? const Color(0xFF2E7D32)
        : const Color(0xFFC62828);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
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
                  doc.voucherNo.isNotEmpty ? doc.voucherNo : '—',
                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF262C50)),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: (doc.isCredit ? const Color(0xFF2E7D32) : _accent).withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  doc.isCredit
                      ? (doc.source.toUpperCase().contains('RETURN') ? 'Return' : 'Credit')
                      : (doc.isPayable ? 'Open' : 'Doc'),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: doc.isCredit ? const Color(0xFF2E7D32) : _accent,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            [
              if (doc.voucherDate.isNotEmpty) _fmtDate(doc.voucherDate),
              if (doc.orderNo.isNotEmpty) 'Order ${doc.orderNo}',
              if (doc.referenceNo.isNotEmpty) doc.referenceNo,
              if (doc.source.isNotEmpty) doc.source,
            ].join(' · '),
            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
          ),
          if (doc.narration.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(doc.narration, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              Text('Invoice ${_fmtAmt(doc.invoiceAmount)}', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
              const Spacer(),
              Text(
                'Open ${_fmtAmt(doc.openAmount)}',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5, color: amtColor),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
