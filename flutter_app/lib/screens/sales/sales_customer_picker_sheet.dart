import 'dart:async';

import 'package:flutter/material.dart';

import '../../services/customer_master_service.dart';
import '../../services/sales_service.dart';
import '../masters/customer_form_screen.dart';

/// Shared Sales customer picker with **New Customer** (includes category + Add).
class SalesCustomerPickerSheet extends StatefulWidget {
  const SalesCustomerPickerSheet({
    super.key,
    required this.service,
    this.billingType = '',
  });

  final SalesService service;
  final String billingType;

  static Future<SalesCustomerOption?> open(
    BuildContext context, {
    required SalesService service,
    String billingType = '',
  }) {
    return showModalBottomSheet<SalesCustomerOption>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => SalesCustomerPickerSheet(
        service: service,
        billingType: billingType,
      ),
    );
  }

  @override
  State<SalesCustomerPickerSheet> createState() => _SalesCustomerPickerSheetState();
}

class _SalesCustomerPickerSheetState extends State<SalesCustomerPickerSheet> {
  final _search = TextEditingController();
  List<SalesCustomerOption> _rows = [];
  bool _loading = false;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _fetch('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _scheduleFetch(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _fetch(q.trim()));
  }

  Future<void> _fetch(String q) async {
    setState(() => _loading = true);
    try {
      final rows = await widget.service.searchCustomers(
        q: q,
        limit: 40,
        billingType: widget.billingType,
      );
      if (mounted) setState(() => _rows = rows);
    } catch (_) {
      if (mounted) setState(() => _rows = []);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openNewCustomer() async {
    final bt = widget.billingType.trim().toUpperCase();
    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        builder: (_) => CustomerFormScreen(
          initialBillingType: (bt == 'CASH' || bt == 'CREDIT') ? bt : null,
        ),
      ),
    );
    if (!mounted || result == null) return;

    if (result is CustomerSaveResult && result.customerCode > 0) {
      SalesCustomerOption selected = SalesCustomerOption(
        code: '${result.customerCode}',
        name: result.customerName,
        billingType: (bt == 'CREDIT' || bt == 'CASH') ? bt : 'CASH',
      );
      try {
        selected = await widget.service.fetchCustomerOutstanding(selected.code);
      } catch (_) {}
      if (!mounted) return;
      Navigator.of(context).pop(selected);
      return;
    }

    await _fetch(_search.text.trim());
  }

  @override
  Widget build(BuildContext context) {
    const accent = Color(0xFF1565C0);
    const bg = Color(0xFFF6F7FC);
    const titleColor = Color(0xFF262C50);
    final h = MediaQuery.of(context).size.height * 0.78;
    final bt = widget.billingType.trim().toUpperCase();
    final title = bt == 'CREDIT'
        ? 'Select credit customer'
        : bt == 'CASH'
            ? 'Select cash customer'
            : 'Select customer';

    return SizedBox(
      height: h,
      child: ColoredBox(
        color: bg,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 8),
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade300,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 8, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      title,
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18, color: titleColor),
                    ),
                  ),
                  TextButton.icon(
                    onPressed: _openNewCustomer,
                    icon: const Icon(Icons.person_add_alt_1_rounded, size: 18),
                    label: const Text('New'),
                    style: TextButton.styleFrom(foregroundColor: accent),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: TextField(
                controller: _search,
                decoration: InputDecoration(
                  hintText: 'Search customer name or code',
                  hintStyle: TextStyle(color: Colors.grey.shade500, fontSize: 14),
                  prefixIcon: Icon(Icons.search_rounded, color: Colors.grey.shade500),
                  filled: true,
                  fillColor: Colors.white,
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.grey.shade200),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.grey.shade200),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: accent, width: 1.5),
                  ),
                ),
                onSubmitted: _fetch,
                onChanged: _scheduleFetch,
              ),
            ),
            if (!_loading && _rows.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text(
                  '${_rows.length} customer${_rows.length == 1 ? '' : 's'}',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: Colors.grey.shade600,
                  ),
                ),
              ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: accent))
                  : _rows.isEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.person_search_outlined, size: 48, color: Colors.grey.shade400),
                                const SizedBox(height: 12),
                                Text(
                                  _search.text.trim().isEmpty
                                      ? (bt == 'CREDIT'
                                          ? 'No credit customers found.'
                                          : bt == 'CASH'
                                              ? 'No cash customers found.'
                                              : 'No customers found.')
                                      : 'No customers match your search.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: Colors.grey.shade600, height: 1.35),
                                ),
                                const SizedBox(height: 14),
                                FilledButton.icon(
                                  onPressed: _openNewCustomer,
                                  icon: const Icon(Icons.person_add_alt_1_rounded),
                                  label: const Text('New Customer'),
                                  style: FilledButton.styleFrom(backgroundColor: accent),
                                ),
                              ],
                            ),
                          ),
                        )
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          itemCount: _rows.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 10),
                          itemBuilder: (_, i) => _customerCard(_rows[i]),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _customerCard(SalesCustomerOption c) {
    const accent = Color(0xFF1565C0);
    const titleColor = Color(0xFF262C50);
    final displayName = c.name.isNotEmpty ? c.name : 'Customer ${c.code}';
    final initials = _initials(displayName);
    final isCredit = c.isCredit;

    return Material(
      color: Colors.white,
      elevation: 1,
      shadowColor: Colors.black12,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.of(context).pop(c),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: isCredit ? const Color(0xFFFFF3E0) : const Color(0xFFE3F2FD),
                  borderRadius: BorderRadius.circular(12),
                ),
                alignment: Alignment.center,
                child: Text(
                  initials,
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 16,
                    color: isCredit ? const Color(0xFFEF6C00) : accent,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      displayName,
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: titleColor),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      [
                        if (c.code.isNotEmpty) '#${c.code}',
                        if (c.categoryName.isNotEmpty) c.categoryName,
                        if (c.phone.isNotEmpty) c.phone,
                      ].join(' · '),
                      style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                    ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        _chip(
                          isCredit ? 'CREDIT' : 'CASH',
                          isCredit ? const Color(0xFFFFF3E0) : const Color(0xFFE3F2FD),
                          isCredit ? const Color(0xFFEF6C00) : accent,
                        ),
                        if (c.categoryName.isNotEmpty)
                          _chip(c.categoryName, const Color(0xFFF3EEFF), const Color(0xFF5E35B1)),
                      ],
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, color: Colors.grey.shade400),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chip(String text, Color bg, Color fg) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)),
      child: Text(text, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: fg)),
    );
  }

  String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts[0].substring(0, 1) + parts[1].substring(0, 1)).toUpperCase();
  }
}
