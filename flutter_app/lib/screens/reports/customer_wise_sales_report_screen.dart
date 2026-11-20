import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/reports_service.dart';
import '../../widgets/api_error_banner.dart';
import '../accounts/accounts_report_helpers.dart';
import '../../core/theme/app_theme.dart';

/// Mobile Customer Wise Sales — same aggregates as ERP Customer Wise Sales.
class CustomerWiseSalesReportScreen extends StatefulWidget {
  const CustomerWiseSalesReportScreen({super.key});

  static Future<void> open(BuildContext context) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => const CustomerWiseSalesReportScreen()),
    );
  }

  @override
  State<CustomerWiseSalesReportScreen> createState() => _CustomerWiseSalesReportScreenState();
}

class _CustomerWiseSalesReportScreenState extends State<CustomerWiseSalesReportScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _accent = Color(0xFF00897B);
  static const _navy = Color(0xFF262C50);

  late DateTime _from;
  late DateTime _to;
  String _billType = '';
  String _customerCode = '';
  String _customerLabel = '';

  bool _loading = false;
  String? _error;
  Object? _errorCause;
  Map<String, dynamic>? _summary;
  List<Map<String, dynamic>> _rows = const [];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _from = now.subtract(const Duration(days: 29));
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
      final data = await context.read<ReportsService>().getCustomerWiseSales(
            dateFrom: isoDate(_from),
            dateTo: isoDate(_to),
            customerCode: _customerCode,
            billType: _billType,
          );
      if (!mounted) return;
      final rowsRaw = data['rows'];
      final rows = <Map<String, dynamic>>[];
      if (rowsRaw is List) {
        for (final r in rowsRaw) {
          if (r is Map) rows.add(Map<String, dynamic>.from(r));
        }
      }
      final summary = data['summary'];
      setState(() {
        _rows = rows;
        _summary = summary is Map ? Map<String, dynamic>.from(summary) : null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = const [];
        _summary = null;
      });
    }
  }

  Future<void> _pickFrom() async {
    await pickReportDate(
      context,
      initial: _from,
      onPicked: (d) {
        setState(() {
          _from = DateTime(d.year, d.month, d.day);
          if (_to.isBefore(_from)) _to = _from;
        });
      },
    );
  }

  Future<void> _pickTo() async {
    await pickReportDate(
      context,
      initial: _to,
      onPicked: (d) {
        setState(() {
          _to = DateTime(d.year, d.month, d.day);
          if (_to.isBefore(_from)) _from = _to;
        });
      },
    );
  }

  Future<void> _pickCustomer() async {
    final picked = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        var q = '';
        var loading = true;
        var rows = <Map<String, dynamic>>[];
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            Future<void> reload(String query) async {
              setLocal(() => loading = true);
              try {
                final list = await context.read<ReportsService>().searchSalesDetailCustomers(q: query);
                setLocal(() {
                  rows = list;
                  loading = false;
                });
              } catch (_) {
                setLocal(() {
                  rows = [];
                  loading = false;
                });
              }
            }

            if (loading && rows.isEmpty) {
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (q.isEmpty && rows.isEmpty) reload('');
              });
            }

            return SafeArea(
              child: SizedBox(
                height: MediaQuery.of(ctx).size.height * 0.72,
                child: Column(
                  children: [
                    const SizedBox(height: 10),
                    Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 14, 8, 8),
                      child: Row(
                        children: [
                          const Expanded(
                            child: Text('Select customer', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(ctx, {'code': '', 'label': ''}),
                            child: const Text('Clear'),
                          ),
                          IconButton(onPressed: () => Navigator.pop(ctx), icon: const Icon(Icons.close)),
                        ],
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: TextField(
                        decoration: InputDecoration(
                          hintText: 'Search customer code/name…',
                          prefixIcon: const Icon(Icons.search),
                          filled: true,
                          fillColor: const Color(0xFFF6F7FC),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                        ),
                        onChanged: (v) {
                          q = v.trim();
                          reload(q);
                        },
                      ),
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: loading
                          ? const Center(child: CircularProgressIndicator(color: _accent))
                          : ListView.builder(
                              itemCount: rows.length,
                              itemBuilder: (_, i) {
                                final r = rows[i];
                                final label = '${r['label'] ?? r['name'] ?? r['code'] ?? ''}'.trim();
                                return ListTile(
                                  title: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
                                  onTap: () => Navigator.pop(ctx, r),
                                );
                              },
                            ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
    if (picked == null || !mounted) return;
    setState(() {
      _customerCode = '${picked['code'] ?? ''}'.trim();
      _customerLabel = '${picked['label'] ?? picked['name'] ?? _customerCode}'.trim();
    });
  }

  double _num(dynamic v) => double.tryParse('$v'.replaceAll(',', '')) ?? 0;

  @override
  Widget build(BuildContext context) {
    final s = _summary ?? const {};
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Customer Wise Sales', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: Column(
        children: [
          _filters(),
          if (_loading) const LinearProgressIndicator(minHeight: 2, color: _accent),
          Expanded(
            child: _error != null && _rows.isEmpty
                ? ApiErrorCenter(message: _error!, error: _errorCause, onRetry: _load)
                : RefreshIndicator(
                    color: _accent,
                    onRefresh: _load,
                    child: ListView(
                      padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
                      children: [
                        _summaryGrid(s),
                        const SizedBox(height: 12),
                        if (_rows.isEmpty && !_loading)
                          const Padding(
                            padding: EdgeInsets.only(top: 40),
                            child: Center(child: Text('No customer sales for this period.')),
                          ),
                        for (final row in _rows) ...[
                          _customerCard(row),
                          const SizedBox(height: 8),
                        ],
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _filters() {
    return Material(
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 8, 14, 12),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(child: _dateChip('From', isoDate(_from), _loading ? null : _pickFrom)),
                const SizedBox(width: 8),
                Expanded(child: _dateChip('To', isoDate(_to), _loading ? null : _pickTo)),
              ],
            ),
            const SizedBox(height: 8),
            InkWell(
              onTap: _loading ? null : _pickCustomer,
              borderRadius: BorderRadius.circular(10),
              child: InputDecorator(
                decoration: InputDecoration(
                  labelText: 'Customer',
                  filled: true,
                  fillColor: const Color(0xFFF6F7FC),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                  suffixIcon: _customerCode.isEmpty
                      ? const Icon(Icons.arrow_drop_down)
                      : IconButton(
                          icon: const Icon(Icons.clear, size: 18),
                          onPressed: () => setState(() {
                            _customerCode = '';
                            _customerLabel = '';
                          }),
                        ),
                ),
                child: Text(
                  _customerLabel.isEmpty ? 'All customers' : _customerLabel,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: _customerLabel.isEmpty ? Colors.grey.shade600 : _navy,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            InputDecorator(
              decoration: InputDecoration(
                labelText: 'Bill type',
                filled: true,
                fillColor: const Color(0xFFF6F7FC),
                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  isExpanded: true,
                  value: _billType,
                  items: const [
                    DropdownMenuItem(value: '', child: Text('All')),
                    DropdownMenuItem(value: 'C', child: Text('Cash')),
                    DropdownMenuItem(value: 'R', child: Text('Credit')),
                    DropdownMenuItem(value: 'D', child: Text('Card / Other')),
                  ],
                  onChanged: _loading
                      ? null
                      : (v) {
                          if (v == null) return;
                          setState(() => _billType = v);
                        },
                ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _loading ? null : _load,
                style: FilledButton.styleFrom(
                  backgroundColor: _accent,
                  minimumSize: const Size.fromHeight(44),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                icon: const Icon(Icons.people_alt_outlined, size: 20),
                label: Text(_loading ? 'Loading…' : 'Run report'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dateChip(String label, String value, VoidCallback? onTap) {
    return Material(
      color: const Color(0xFFF6F7FC),
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Text(value, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: _navy)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _summaryGrid(Map<String, dynamic> s) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(child: _stat('Customers', '${s['customer_count'] ?? _rows.length}')),
                const SizedBox(width: 8),
                Expanded(child: _stat('Sales bills', '${s['bill_count'] ?? 0}')),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: _stat('Sales amount', fmtMoney(_num(s['sales_amount'])))),
                const SizedBox(width: 8),
                Expanded(child: _stat('Returns', fmtMoney(_num(s['sales_return'])))),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(child: _stat('Return bills', '${s['return_bill_count'] ?? 0}')),
                const SizedBox(width: 8),
                Expanded(child: _stat('Net sales', fmtMoney(_num(s['total_sale'])), emphasize: true)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _stat(String label, String value, {bool emphasize = false}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      decoration: BoxDecoration(
        color: emphasize ? const Color(0xFFE0F2F1) : const Color(0xFFF6F7FC),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontWeight: FontWeight.w800,
              fontSize: 15,
              color: emphasize ? _accent : _navy,
            ),
          ),
        ],
      ),
    );
  }

  Widget _customerCard(Map<String, dynamic> row) {
    final code = '${row['customer_code'] ?? ''}'.trim();
    final name = '${row['customer_name'] ?? ''}'.trim();
    final title = name.isEmpty ? (code.isEmpty ? 'Walk-in / Unknown' : code) : (code.isEmpty ? name : '$code · $name');
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: _navy)),
            const SizedBox(height: 8),
            _kv('Bill count', '${row['bill_count'] ?? 0}'),
            _kv('Sales amount', fmtMoney(_num(row['sales_amount']))),
            _kv('Return bills', '${row['return_bill_count'] ?? 0}'),
            _kv('Sales return', fmtMoney(_num(row['sales_return']))),
            _kv('Total bills', '${row['total_bill_count'] ?? 0}'),
            _kv('Total sale', fmtMoney(_num(row['total_sale'])), bold: true),
          ],
        ),
      ),
    );
  }

  Widget _kv(String left, String right, {bool bold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Expanded(
            child: Text(
              left,
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: bold ? FontWeight.w800 : FontWeight.w600,
                color: Colors.grey.shade700,
              ),
            ),
          ),
          Text(
            right,
            style: TextStyle(
              fontSize: 13,
              fontWeight: bold ? FontWeight.w800 : FontWeight.w700,
              color: _navy,
            ),
          ),
        ],
      ),
    );
  }
}
