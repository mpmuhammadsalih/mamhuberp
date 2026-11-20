import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/supplier_master_service.dart';
import 'supplier_form_screen.dart';
import '../../core/theme/app_theme.dart';

class SupplierDetailScreen extends StatefulWidget {
  const SupplierDetailScreen({super.key, required this.supplierCode});

  final int supplierCode;

  @override
  State<SupplierDetailScreen> createState() => _SupplierDetailScreenState();
}

class _SupplierDetailScreenState extends State<SupplierDetailScreen> {
  static const _accent = Color(0xFF2E7D32);

  bool _loading = true;
  bool _changed = false;
  String? _error;
  SupplierDetail? _supplier;

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
      final supplier = await context.read<SupplierMasterService>().getSupplier(widget.supplierCode);
      if (!mounted) return;
      setState(() {
        _supplier = supplier;
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
        builder: (_) => SupplierFormScreen(supplierCode: widget.supplierCode),
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

  @override
  Widget build(BuildContext context) {
    final s = _supplier;
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
        title: const Text('Supplier Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          TextButton(
            onPressed: _loading || s == null ? null : _edit,
            child: Text(
              'Edit',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: _loading || s == null ? Colors.grey : _accent,
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
              : s == null
                  ? const Center(child: Text('Supplier not found.'))
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                      children: [
                        _card(
                          children: [
                            Text(
                              s.supplierName.isNotEmpty ? s.supplierName : 'Supplier ${s.supplierCode}',
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 18,
                                color: Color(0xFF262C50),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                _chip('#${s.supplierCode}', const Color(0xFFE8F5E9), _accent),
                                if (s.billingType.isNotEmpty)
                                  _chip(
                                    s.billingType,
                                    s.billingType == 'CREDIT'
                                        ? const Color(0xFFFFF3E0)
                                        : const Color(0xFFE3F2FD),
                                    s.billingType == 'CREDIT'
                                        ? const Color(0xFFEF6C00)
                                        : const Color(0xFF1565C0),
                                  ),
                                if (s.supplierType.isNotEmpty)
                                  _chip(s.supplierType, const Color(0xFFF3EEFF), const Color(0xFF5E35B1)),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _card(
                          children: [
                            _kv('Contact', s.contactPerson),
                            _kv('Mobile', s.mobile),
                            _kv('Telephone', s.telephone),
                            _kv('Email', s.email),
                            _kv('Address', s.address),
                            _kv('CR No', s.supplierCr),
                            _kv('Supplier Ref', s.supplierRef),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _card(
                          children: [
                            _kv(
                              s.billingType == 'CASH' ? 'Cash account' : 'Payable account',
                              s.payableAccount > 0 ? '${s.payableAccount}' : '—',
                            ),
                            if (s.purchaseAccount > 0) _kv('Purchase account', '${s.purchaseAccount}'),
                            if (s.vatInputAccount > 0) _kv('VAT input account', '${s.vatInputAccount}'),
                            if (s.advanceAccount > 0) _kv('Advance account', '${s.advanceAccount}'),
                          ],
                        ),
                        const SizedBox(height: 18),
                        FilledButton.icon(
                          onPressed: _edit,
                          style: FilledButton.styleFrom(
                            backgroundColor: _accent,
                            minimumSize: const Size.fromHeight(48),
                          ),
                          icon: const Icon(Icons.edit_outlined),
                          label: const Text('Edit Supplier', style: TextStyle(fontWeight: FontWeight.w700)),
                        ),
                      ],
                    ),
    );
  }

  Widget _card({required List<Widget> children}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );
  }

  Widget _chip(String text, Color bg, Color fg) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)),
      child: Text(text, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: fg)),
    );
  }

  Widget _kv(String k, String v) {
    if (v.trim().isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 120, child: Text(k, style: TextStyle(color: Colors.grey.shade600, fontSize: 13))),
          Expanded(
            child: Text(v, style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF262C50))),
          ),
        ],
      ),
    );
  }
}
