import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/supplier_master_service.dart';
import '../../widgets/api_error_banner.dart';
import 'supplier_detail_screen.dart';
import 'supplier_form_screen.dart';
import '../../core/theme/app_theme.dart';

class SupplierListScreen extends StatefulWidget {
  const SupplierListScreen({super.key});

  @override
  State<SupplierListScreen> createState() => _SupplierListScreenState();
}

class _SupplierListScreenState extends State<SupplierListScreen> {
  static const _accent = Color(0xFF2E7D32);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<SupplierMasterRow> _rows = [];

  @override
  void initState() {
    super.initState();
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
      final rows = await context.read<SupplierMasterService>().listSuppliers(
            q: _search.text.trim(),
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

  Future<void> _openNew() async {
    final saved = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(builder: (_) => const SupplierFormScreen()),
    );
    if (saved != null && mounted) _reload();
  }

  Future<void> _openDetail(SupplierMasterRow row) async {
    if (row.supplierCode <= 0) return;
    final changed = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        builder: (_) => SupplierDetailScreen(supplierCode: row.supplierCode),
      ),
    );
    if (changed != null && mounted) _reload();
  }

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
        title: const Text('Suppliers', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNew,
        backgroundColor: _accent,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.storefront_outlined),
        label: const Text('New Supplier'),
      ),
      body: Column(
        children: [
          Material(
            color: Colors.white,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
              child: TextField(
                controller: _search,
                onChanged: (_) => _scheduleSearch(),
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  hintText: 'Search name, code, contact…',
                  prefixIcon: const Icon(Icons.search_rounded, size: 20),
                  isDense: true,
                  filled: true,
                  fillColor: const Color(0xFFF0F2FA),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
          ),
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
          Expanded(
            child: RefreshIndicator(
              color: _accent,
              onRefresh: _reload,
              child: _loading && _rows.isEmpty
                  ? ListView(
                      children: const [
                        SizedBox(height: 120),
                        Center(child: CircularProgressIndicator()),
                      ],
                    )
                  : _rows.isEmpty
                      ? ListView(
                          children: [
                            const SizedBox(height: 80),
                            Icon(Icons.storefront_outlined, size: 42, color: Colors.grey.shade400),
                            const SizedBox(height: 12),
                            Text(
                              _search.text.trim().isEmpty
                                  ? 'No suppliers yet.\nTap New Supplier to create one.'
                                  : 'No suppliers match your search.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.grey.shade600, height: 1.35),
                            ),
                          ],
                        )
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(12, 8, 12, 100),
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
                                    padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 42,
                                          height: 42,
                                          decoration: BoxDecoration(
                                            color: _accent.withValues(alpha: 0.1),
                                            borderRadius: BorderRadius.circular(10),
                                          ),
                                          child: Icon(
                                            Icons.storefront_outlined,
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
                                                row.supplierName.isNotEmpty
                                                    ? row.supplierName
                                                    : 'Supplier ${row.supplierCode}',
                                                style: const TextStyle(
                                                  fontWeight: FontWeight.w700,
                                                  fontSize: 14.5,
                                                ),
                                              ),
                                              const SizedBox(height: 3),
                                              Text(
                                                [
                                                  if (row.supplierCode > 0) '#${row.supplierCode}',
                                                  if (row.billingType.isNotEmpty) row.billingType,
                                                  if (row.supplierType.isNotEmpty) row.supplierType,
                                                  if (row.phone.isNotEmpty) row.phone,
                                                  if (row.contactPerson.isNotEmpty) row.contactPerson,
                                                ].join(' · '),
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
                        ),
            ),
          ),
        ],
      ),
    );
  }
}
