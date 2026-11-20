import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/transaction_draft_banner.dart';
import '../../services/sales_service.dart';
import 'sales_billing_tabs.dart';
import 'sales_return_detail_screen.dart';
import 'sales_return_form_screen.dart';
import 'sales_transaction_draft.dart';
import '../../core/theme/app_theme.dart';

class _SalesReturnFilters {
  const _SalesReturnFilters({
    this.dateFrom,
    this.dateTo,
    this.customer,
    this.billingType,
  });

  final DateTime? dateFrom;
  final DateTime? dateTo;
  final SalesCustomerOption? customer;
  /// `CASH` (cash/card sales) or `CREDIT`.
  final String? billingType;

  bool get hasAny =>
      dateFrom != null || dateTo != null || customer != null || (billingType != null && billingType!.isNotEmpty);
}

class SalesReturnListScreen extends StatefulWidget {
  const SalesReturnListScreen({super.key});

  @override
  State<SalesReturnListScreen> createState() => _SalesReturnListScreenState();
}

class _SalesReturnListScreenState extends State<SalesReturnListScreen> {
  static const _accent = Color(0xFF6A1B9A);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<SalesInvoiceSummary> _rows = [];
  _SalesReturnFilters _filters = const _SalesReturnFilters();
  Map<String, dynamic>? _draft;

  @override
  void initState() {
    super.initState();
    _search.addListener(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDraftBanner();
      _reload();
    });
  }

  Future<void> _loadDraftBanner() async {
    final user = context.read<AuthProvider>().user;
    if (user == null) {
      if (mounted) setState(() => _draft = null);
      return;
    }
    final draft = await TransactionDraftStorage.read(
      docType: TransactionDraftType.salesReturn,
      tenantId: user.tenantId ?? '',
      username: user.username,
    );
    if (!mounted) return;
    setState(() => _draft = draft);
  }

  Future<void> _dismissDraft() async {
    final user = context.read<AuthProvider>().user;
    if (user != null) {
      await TransactionDraftStorage.clear(
        docType: TransactionDraftType.salesReturn,
        tenantId: user.tenantId ?? '',
        username: user.username,
      );
    }
    if (mounted) setState(() => _draft = null);
  }

  Future<void> _continueDraft() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => const SalesReturnFormScreen(restoreDraft: true),
      ),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    if (saved == true) _reload();
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

  String _fmtApiDate(DateTime d) {
    final m = d.month.toString().padLeft(2, '0');
    final day = d.day.toString().padLeft(2, '0');
    return '${d.year}-$m-$day';
  }

  String _fmtDisplayDate(DateTime d) {
    final m = d.month.toString().padLeft(2, '0');
    final day = d.day.toString().padLeft(2, '0');
    return '$day/$m/${d.year}';
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final rows = await context.read<SalesService>().listReturns(
            q: _search.text.trim(),
            limit: 60,
            days: _filters.hasAny && (_filters.dateFrom != null || _filters.dateTo != null) ? 365 : 90,
            dateFrom: _filters.dateFrom != null ? _fmtApiDate(_filters.dateFrom!) : '',
            dateTo: _filters.dateTo != null ? _fmtApiDate(_filters.dateTo!) : '',
            customerCode: _filters.customer?.code ?? '',
            billingType: _filters.billingType ?? '',
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

  Future<void> _openReturnDetail(SalesInvoiceSummary invoice) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => SalesReturnDetailScreen(billno: invoice.billno),
      ),
    );
  }

  Future<void> _openNewReturn() async {
    if (_draft != null) {
      final action = await showPendingDraftAlert(
        context,
        summary: SalesTransactionDraft.summaryLabel(_draft!),
        documentLabel: 'sales return',
      );
      if (!mounted) return;
      if (action == PendingDraftAction.cancel) return;
      if (action == PendingDraftAction.continuePending) {
        await _continueDraft();
        return;
      }
      await _dismissDraft();
    }
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const SalesReturnFormScreen()),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    if (saved == true) _reload();
  }

  Future<void> _openFilters() async {
    final updated = await showModalBottomSheet<_SalesReturnFilters>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => _SalesReturnFilterSheet(
        initial: _filters,
        service: context.read<SalesService>(),
        fmtDisplayDate: _fmtDisplayDate,
      ),
    );
    if (updated == null || !mounted) return;
    setState(() => _filters = updated);
    await _reload();
  }

  void _clearFilters() {
    setState(() => _filters = _SalesReturnFilters(billingType: _filters.billingType));
    _reload();
  }

  bool get _hasSheetFilters =>
      _filters.dateFrom != null || _filters.dateTo != null || _filters.customer != null;

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
        title: const Text('Sales Returns', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(
            onPressed: _loading ? null : _reload,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _openNewReturn,
        backgroundColor: _accent,
        child: const Icon(Icons.add_rounded),
      ),
      body: Column(
        children: [
          if (_draft != null)
            TransactionDraftBanner(
              title: 'Continue draft',
              subtitle: SalesTransactionDraft.summaryLabel(_draft!),
              accent: _accent,
              onContinue: _continueDraft,
              onDismiss: _dismissDraft,
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _search,
                    decoration: InputDecoration(
                      hintText: 'Search return no, customer, invoice ref…',
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
                      focusedBorder: const UnderlineInputBorder(
                        borderSide: BorderSide(color: _accent, width: 2),
                      ),
                    ),
                    onChanged: (_) => _scheduleSearch(),
                    onSubmitted: (_) => _reload(),
                  ),
                ),
                IconButton(
                  tooltip: 'Filter',
                  onPressed: _openFilters,
                  icon: Badge(
                    isLabelVisible: _hasSheetFilters,
                    smallSize: 8,
                    child: const Icon(Icons.filter_alt_outlined),
                  ),
                ),
              ],
            ),
          ),
          SalesBillingTabs(
            billingType: _filters.billingType,
            accent: _accent,
            onChanged: (v) {
              setState(() {
                _filters = _SalesReturnFilters(
                  dateFrom: _filters.dateFrom,
                  dateTo: _filters.dateTo,
                  customer: _filters.customer,
                  billingType: v,
                );
              });
              _reload();
            },
          ),
          if (_hasSheetFilters)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        if (_filters.dateFrom != null)
                          _activeFilterChip('From ${_fmtDisplayDate(_filters.dateFrom!)}'),
                        if (_filters.dateTo != null)
                          _activeFilterChip('To ${_fmtDisplayDate(_filters.dateTo!)}'),
                        if (_filters.customer != null)
                          _activeFilterChip(_filters.customer!.name.isNotEmpty
                              ? _filters.customer!.name
                              : _filters.customer!.code),
                      ],
                    ),
                  ),
                  TextButton(onPressed: _clearFilters, child: const Text('Clear')),
                ],
              ),
            ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: _accent))
                : _error != null
                    ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _reload)
                    : _rows.isEmpty
                        ? Center(
                            child: Text(
                              _search.text.trim().isEmpty && !_filters.hasAny
                                  ? 'No sales returns in the last 90 days.'
                                  : 'No returns match your search or filters.',
                              style: TextStyle(color: Colors.grey.shade600),
                            ),
                          )
                        : RefreshIndicator(
                            color: _accent,
                            onRefresh: _reload,
                            child: ListView.separated(
                              padding: const EdgeInsets.fromLTRB(14, 8, 14, 94),
                              itemCount: _rows.length,
                              separatorBuilder: (_, __) => const SizedBox(height: 9),
                              itemBuilder: (_, i) => _SalesReturnCard(
                                invoice: _rows[i],
                                onTap: () => _openReturnDetail(_rows[i]),
                              ),
                            ),
                          ),
          ),
        ],
      ),
    );
  }

  Widget _activeFilterChip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xFFF3E5F5),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: _accent)),
    );
  }
}

class _SalesReturnFilterSheet extends StatefulWidget {
  const _SalesReturnFilterSheet({
    required this.initial,
    required this.service,
    required this.fmtDisplayDate,
  });

  final _SalesReturnFilters initial;
  final SalesService service;
  final String Function(DateTime) fmtDisplayDate;

  @override
  State<_SalesReturnFilterSheet> createState() => _SalesReturnFilterSheetState();
}

class _SalesReturnFilterSheetState extends State<_SalesReturnFilterSheet> {
  static const _accent = Color(0xFF6A1B9A);

  late DateTime? _dateFrom;
  late DateTime? _dateTo;
  late SalesCustomerOption? _customer;
  late String? _billingType;

  final _customerSearch = TextEditingController();
  List<SalesCustomerOption> _customerRows = [];
  bool _customerLoading = false;
  Timer? _customerDebounce;

  @override
  void initState() {
    super.initState();
    _dateFrom = widget.initial.dateFrom;
    _dateTo = widget.initial.dateTo;
    _customer = widget.initial.customer;
    _billingType = widget.initial.billingType;
    _fetchCustomers('');
  }

  @override
  void dispose() {
    _customerDebounce?.cancel();
    _customerSearch.dispose();
    super.dispose();
  }

  Future<void> _pickDate({required bool isFrom}) async {
    final initial = isFrom ? (_dateFrom ?? DateTime.now()) : (_dateTo ?? _dateFrom ?? DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2015),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (isFrom) {
        _dateFrom = picked;
        if (_dateTo != null && _dateTo!.isBefore(picked)) _dateTo = picked;
      } else {
        _dateTo = picked;
        if (_dateFrom != null && _dateFrom!.isAfter(picked)) _dateFrom = picked;
      }
    });
  }

  void _scheduleCustomerSearch(String q) {
    _customerDebounce?.cancel();
    _customerDebounce = Timer(const Duration(milliseconds: 350), () => _fetchCustomers(q.trim()));
  }

  Future<void> _fetchCustomers(String q) async {
    setState(() => _customerLoading = true);
    try {
      final rows = await widget.service.searchCustomers(q: q, limit: 30);
      if (mounted) setState(() => _customerRows = rows);
    } catch (_) {
      if (mounted) setState(() => _customerRows = []);
    } finally {
      if (mounted) setState(() => _customerLoading = false);
    }
  }

  void _apply() {
    Navigator.of(context).pop(
      _SalesReturnFilters(
        dateFrom: _dateFrom,
        dateTo: _dateTo,
        customer: _customer,
        billingType: _billingType,
      ),
    );
  }

  void _reset() {
    setState(() {
      _dateFrom = null;
      _dateTo = null;
      _customer = null;
      _billingType = null;
      _customerSearch.clear();
      _customerRows = [];
    });
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Text('Filter returns', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const Spacer(),
              TextButton(onPressed: _reset, child: const Text('Reset')),
            ],
          ),
          const SizedBox(height: 16),
          const Text('Date range', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _pickDate(isFrom: true),
                  icon: const Icon(Icons.calendar_today_outlined, size: 16),
                  label: Text(_dateFrom == null ? 'From date' : widget.fmtDisplayDate(_dateFrom!)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _pickDate(isFrom: false),
                  icon: const Icon(Icons.calendar_today_outlined, size: 16),
                  label: Text(_dateTo == null ? 'To date' : widget.fmtDisplayDate(_dateTo!)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          const Text('Customer', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          const SizedBox(height: 8),
          if (_customer != null)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(_customer!.name.isNotEmpty ? _customer!.name : _customer!.code),
              subtitle: Text('Code ${_customer!.code}'),
              trailing: IconButton(
                icon: const Icon(Icons.close, size: 20),
                onPressed: () => setState(() => _customer = null),
              ),
            )
          else ...[
            TextField(
              controller: _customerSearch,
              decoration: InputDecoration(
                hintText: 'Search customer name or code',
                prefixIcon: const Icon(Icons.person_search_outlined, size: 20),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                isDense: true,
              ),
              onChanged: _scheduleCustomerSearch,
              onSubmitted: _fetchCustomers,
            ),
            if (_customerLoading)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))),
              )
            else if (_customerRows.isNotEmpty)
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 200),
                child: ListView.separated(
                  shrinkWrap: true,
                  padding: const EdgeInsets.only(top: 8),
                  itemCount: _customerRows.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (_, i) {
                    final c = _customerRows[i];
                    final name = c.name.isNotEmpty ? c.name : c.code;
                    final isCredit = c.isCredit;
                    return Material(
                      color: Colors.white,
                      elevation: 0.5,
                      borderRadius: BorderRadius.circular(10),
                      clipBehavior: Clip.antiAlias,
                      child: InkWell(
                        onTap: () => setState(() {
                          _customer = c;
                          _customerSearch.clear();
                          _customerRows = [];
                        }),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          child: Row(
                            children: [
                              Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: isCredit ? const Color(0xFFFFF3E0) : const Color(0xFFF3E5F5),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                alignment: Alignment.center,
                                child: Text(
                                  name.isNotEmpty ? name[0].toUpperCase() : '?',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: isCredit ? const Color(0xFFE65100) : const Color(0xFF6A1B9A),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      name,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                                    ),
                                    Text(
                                      'Code ${c.code} • ${c.creditLimitLabel}',
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
          ],
          const SizedBox(height: 18),
          const Text('Cash / card or credit', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              FilterChip(
                label: const Text('All'),
                selected: _billingType == null,
                onSelected: (_) => setState(() => _billingType = null),
              ),
              FilterChip(
                label: const Text('Cash / Card'),
                selected: _billingType == 'CASH',
                onSelected: (_) => setState(() => _billingType = 'CASH'),
              ),
              FilterChip(
                label: const Text('Credit'),
                selected: _billingType == 'CREDIT',
                onSelected: (_) => setState(() => _billingType = 'CREDIT'),
              ),
            ],
          ),
          const SizedBox(height: 20),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: _accent, minimumSize: const Size(double.infinity, 48)),
            onPressed: _apply,
            child: const Text('Apply filters', style: TextStyle(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
    );
  }
}

class _SalesReturnCard extends StatelessWidget {
  const _SalesReturnCard({required this.invoice, required this.onTap});

  final SalesInvoiceSummary invoice;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isCredit = invoice.billingType == 'CREDIT';
    final statusBg = isCredit ? const Color(0xFFF3E5F5) : const Color(0xFFE9F9EF);
    final statusFg = isCredit ? const Color(0xFF6A1B9A) : const Color(0xFF1C9C58);
    const stripeColor = Color(0xFF6A1B9A);
    final displayAmount = invoice.netAmount.abs();

    final secondaryLine = invoice.orderNo.isNotEmpty
        ? 'Ref ${invoice.orderNo}'
        : (invoice.customerCode.isNotEmpty ? 'Code ${invoice.customerCode}' : '');

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: const Border(left: BorderSide(color: stripeColor, width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
        onTap: onTap,
        title: Text('Return-${invoice.billno}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                invoice.customerLabel,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13),
              ),
              if (secondaryLine.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(secondaryLine, style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12.5)),
              ],
            ],
          ),
        ),
        trailing: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 112),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Wrap(
                spacing: 4,
                runSpacing: 2,
                alignment: WrapAlignment.end,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF3E5F5),
                      borderRadius: BorderRadius.circular(50),
                    ),
                    child: const Text(
                      'Return',
                      style: TextStyle(color: Color(0xFF6A1B9A), fontSize: 10.5, fontWeight: FontWeight.w700),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(color: statusBg, borderRadius: BorderRadius.circular(50)),
                    child: Text(
                      invoice.billingType,
                      style: TextStyle(color: statusFg, fontSize: 10.5, fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 2),
              Text(
                invoice.billDate,
                style: const TextStyle(fontSize: 11, color: Color(0xFF6F7482), height: 1.0),
              ),
              const SizedBox(height: 2),
              Text(
                displayAmount.toStringAsFixed(2),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF6A1B9A), height: 1.0),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
