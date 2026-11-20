import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/customer_master_service.dart';
import 'customer_form_screen.dart';
import '../../core/theme/app_theme.dart';

class CustomerDetailScreen extends StatefulWidget {
  const CustomerDetailScreen({super.key, required this.customerCode});

  final int customerCode;

  @override
  State<CustomerDetailScreen> createState() => _CustomerDetailScreenState();
}

class _CustomerDetailScreenState extends State<CustomerDetailScreen> {
  static const _accent = Color(0xFF1565C0);

  bool _loading = true;
  bool _changed = false;
  String? _error;
  CustomerDetail? _customer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final customer = await context.read<CustomerMasterService>().getCustomer(widget.customerCode);
      if (!mounted) return;
      setState(() {
        _customer = customer;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _edit() async {
    final saved = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        builder: (_) => CustomerFormScreen(customerCode: widget.customerCode),
      ),
    );
    if (!mounted || saved == null) return;
    if (saved == 'deleted') {
      Navigator.of(context).pop(true);
      return;
    }
    _changed = true;
    await _load();
  }

  String _money(double v) => v.toStringAsFixed(2);

  @override
  Widget build(BuildContext context) {
    final c = _customer;
    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).pop(_changed ? true : null),
        ),
        title: const Text('Customer Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          TextButton(
            onPressed: _loading || c == null ? null : _edit,
            child: Text(
              'Edit',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: _loading || c == null ? Colors.grey : _accent,
              ),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 12),
                        FilledButton(onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : c == null
                  ? const Center(child: Text('Customer not found.'))
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                      children: [
                        _card(
                          children: [
                            Row(
                              children: [
                                Container(
                                  width: 48,
                                  height: 48,
                                  decoration: BoxDecoration(
                                    color: _accent.withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Icon(
                                    c.billingType == 'CREDIT'
                                        ? Icons.credit_card_rounded
                                        : Icons.payments_outlined,
                                    color: _accent,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        c.customerName.isNotEmpty
                                            ? c.customerName
                                            : 'Customer ${c.customerCode}',
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w800,
                                          fontSize: 18,
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        [
                                          if (c.customerCode > 0) '#${c.customerCode}',
                                          if (c.ccode.isNotEmpty) c.ccode,
                                          c.billingType == 'CREDIT' ? 'Credit' : 'Cash',
                                          if (c.closed == 'Y') 'Closed',
                                        ].join(' · '),
                                        style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _card(
                          children: [
                            _row('Category', c.categoryName.isNotEmpty
                                ? c.categoryName
                                : (c.categoryCode > 0 ? '${c.categoryCode}' : '—')),
                            _row('Mobile', c.mobile),
                            _row('Telephone', c.telephone),
                            _row('WhatsApp', c.whatsapp),
                            _row('Email', c.email),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _card(
                          children: [
                            _row('Address', c.address),
                            _row('CR No', c.crno),
                          ],
                        ),
                        if (c.billingType == 'CREDIT') ...[
                          const SizedBox(height: 12),
                          _card(
                            children: [
                              _row('Credit Limit', _money(c.creditLimit)),
                              _row(
                                'Credit Term',
                                c.creditTerm == c.creditTerm.roundToDouble()
                                    ? '${c.creditTerm.round()} days'
                                    : '${c.creditTerm.toStringAsFixed(1)} days',
                              ),
                              _row('Current Credit', _money(c.currentCredit)),
                            ],
                          ),
                        ],
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: _edit,
                          style: FilledButton.styleFrom(
                            backgroundColor: _accent,
                            minimumSize: const Size.fromHeight(48),
                          ),
                          icon: const Icon(Icons.edit_outlined),
                          label: const Text('Edit Customer', style: TextStyle(fontWeight: FontWeight.w700)),
                        ),
                      ],
                    ),
    );
  }

  Widget _card({required List<Widget> children}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(label, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
          ),
          Expanded(
            child: Text(
              value.isEmpty ? '—' : value,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5),
            ),
          ),
        ],
      ),
    );
  }
}
