import 'package:flutter/material.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/reports_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_indicator.dart';
import '../../core/theme/app_theme.dart';

typedef InventoryReportLoader = Future<InventoryReportPayload> Function({
  required String q,
  required String dateFrom,
  required String dateTo,
});

typedef InventoryReportItemBuilder = Widget Function(
  BuildContext context,
  Map<String, dynamic> row,
  Color accent,
);

enum InventoryReportDateMode { none, range, asOn }

String invStr(Map<String, dynamic> row, List<String> keys, {String fallback = ''}) {
  for (final k in keys) {
    final v = row[k];
    if (v == null) continue;
    final s = v.toString().trim();
    if (s.isNotEmpty && s.toLowerCase() != 'null') return s;
  }
  return fallback;
}

double? invNum(Map<String, dynamic> row, List<String> keys) {
  for (final k in keys) {
    final v = row[k];
    if (v == null) continue;
    if (v is num) return v.toDouble();
    final s = v.toString().trim().replaceAll(',', '');
    if (s.isEmpty) continue;
    final n = double.tryParse(s);
    if (n != null) return n;
  }
  return null;
}

String invFmtNum(num? v, {int decimals = 2}) {
  if (v == null) return '—';
  if (v == v.roundToDouble()) return v.round().toString();
  return v.toStringAsFixed(decimals);
}

String invFmtMoney(num? v) {
  if (v == null) return '—';
  return v.toStringAsFixed(2);
}

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

String _prettySummaryKey(String key) {
  return key
      .replaceAll('_', ' ')
      .split(' ')
      .where((p) => p.isNotEmpty)
      .map((p) => '${p[0].toUpperCase()}${p.substring(1)}')
      .join(' ');
}

String _summaryValue(dynamic v) {
  if (v == null) return '—';
  if (v is num) return invFmtNum(v);
  final s = v.toString().trim();
  return s.isEmpty ? '—' : s;
}

/// Reusable inventory report list with search, optional dates, summary chips.
class InventoryReportScreen extends StatefulWidget {
  const InventoryReportScreen({
    super.key,
    required this.title,
    required this.accent,
    required this.loader,
    required this.itemBuilder,
    this.showSearch = true,
    this.dateMode = InventoryReportDateMode.none,
    this.searchHint = 'Search…',
    this.emptyMessage = 'No rows for this report.',
  });

  final String title;
  final Color accent;
  final InventoryReportLoader loader;
  final InventoryReportItemBuilder itemBuilder;
  final bool showSearch;
  final InventoryReportDateMode dateMode;
  final String searchHint;
  final String emptyMessage;

  @override
  State<InventoryReportScreen> createState() => _InventoryReportScreenState();
}

class _InventoryReportScreenState extends State<InventoryReportScreen> {
  static const _bg = Color(0xFFF6F7FC);
  static const _titleColor = Color(0xFF262C50);

  final _searchCtrl = TextEditingController();

  bool _loading = true;
  bool _refreshing = false;
  String? _error;
  Object? _errorCause;
  List<Map<String, dynamic>> _rows = const [];
  Map<String, dynamic>? _summary;

  late DateTime _dateFrom;
  late DateTime _dateTo;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    _dateTo = today;
    _dateFrom = today.subtract(const Duration(days: 13));
    _searchCtrl.addListener(() {
      if (mounted) setState(() {});
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load({bool refresh = false}) async {
    if (refresh) {
      setState(() {
        _refreshing = true;
        _error = null;
        _errorCause = null;
      });
    } else {
      setState(() {
        _loading = true;
        _error = null;
        _errorCause = null;
      });
    }

    try {
      final payload = await widget.loader(
        q: _searchCtrl.text.trim(),
        dateFrom: _iso(_dateFrom),
        dateTo: _iso(_dateTo),
      );
      if (!mounted) return;
      setState(() {
        _rows = payload.rows;
        _summary = payload.summary;
        _loading = false;
        _refreshing = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
        _refreshing = false;
      });
    }
  }

  Future<void> _pickDateRange() async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2015),
      lastDate: today,
      initialDateRange: DateTimeRange(start: _dateFrom, end: _dateTo),
      helpText: 'Select date range',
      saveText: 'Apply',
    );
    if (picked == null || !mounted) return;
    setState(() {
      _dateFrom = DateTime(picked.start.year, picked.start.month, picked.start.day);
      _dateTo = DateTime(picked.end.year, picked.end.month, picked.end.day);
    });
    await _load();
  }

  Future<void> _pickAsOnDate() async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final picked = await showDatePicker(
      context: context,
      initialDate: _dateTo,
      firstDate: DateTime(2015),
      lastDate: today,
      helpText: 'As on date',
    );
    if (picked == null || !mounted) return;
    setState(() {
      _dateTo = DateTime(picked.year, picked.month, picked.day);
      _dateFrom = _dateTo;
    });
    await _load();
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
        title: Text(
          widget.title,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : () => _load(refresh: true),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: Column(
        children: [
          if (widget.showSearch || widget.dateMode != InventoryReportDateMode.none)
            _FilterBar(
              accent: widget.accent,
              showSearch: widget.showSearch,
              searchHint: widget.searchHint,
              searchCtrl: _searchCtrl,
              dateMode: widget.dateMode,
              dateFrom: _dateFrom,
              dateTo: _dateTo,
              onSearch: () => _load(),
              onClearSearch: () {
                _searchCtrl.clear();
                _load();
              },
              onPickDates: widget.dateMode == InventoryReportDateMode.asOn
                  ? _pickAsOnDate
                  : _pickDateRange,
            ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading && _rows.isEmpty) {
      return const AppLoadingIndicator();
    }
    if (_error != null && _rows.isEmpty) {
      return ApiErrorCenter(
        message: _error!,
        error: _errorCause,
        onRetry: () => _load(),
      );
    }

    final chips = _summaryChips();

    return RefreshIndicator(
      color: widget.accent,
      onRefresh: () => _load(refresh: true),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (_error != null)
            SliverToBoxAdapter(
              child: ApiErrorBanner(message: _error!, error: _errorCause),
            ),
          if (_refreshing)
            SliverToBoxAdapter(
              child: LinearProgressIndicator(
                minHeight: 2,
                color: widget.accent,
                backgroundColor: Color.lerp(widget.accent, Colors.white, 0.85),
              ),
            ),
          if (chips.isNotEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: chips,
                ),
              ),
            ),
          if (_rows.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Text(
                    widget.emptyMessage,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 14),
                  ),
                ),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
              sliver: SliverList.separated(
                itemCount: _rows.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (context, index) {
                  return widget.itemBuilder(context, _rows[index], widget.accent);
                },
              ),
            ),
        ],
      ),
    );
  }

  List<Widget> _summaryChips() {
    final s = _summary;
    if (s == null || s.isEmpty) return const [];
    final out = <Widget>[];
    for (final e in s.entries) {
      if (e.value is Map || e.value is List) continue;
      out.add(
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: Color.lerp(widget.accent, Colors.white, 0.92),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: Color.lerp(widget.accent, Colors.white, 0.7)!),
          ),
          child: Text(
            '${_prettySummaryKey(e.key)}: ${_summaryValue(e.value)}',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Color.lerp(widget.accent, _titleColor, 0.35),
            ),
          ),
        ),
      );
      if (out.length >= 6) break;
    }
    return out;
  }
}

class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.accent,
    required this.showSearch,
    required this.searchHint,
    required this.searchCtrl,
    required this.dateMode,
    required this.dateFrom,
    required this.dateTo,
    required this.onSearch,
    required this.onClearSearch,
    required this.onPickDates,
  });

  final Color accent;
  final bool showSearch;
  final String searchHint;
  final TextEditingController searchCtrl;
  final InventoryReportDateMode dateMode;
  final DateTime dateFrom;
  final DateTime dateTo;
  final VoidCallback onSearch;
  final VoidCallback onClearSearch;
  final VoidCallback onPickDates;

  @override
  Widget build(BuildContext context) {
    final dateLabel = dateMode == InventoryReportDateMode.asOn
        ? 'As on ${_iso(dateTo)}'
        : '${_iso(dateFrom)} → ${_iso(dateTo)}';

    return Material(
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
        child: Column(
          children: [
            if (showSearch)
              TextField(
                controller: searchCtrl,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => onSearch(),
                decoration: InputDecoration(
                  hintText: searchHint,
                  isDense: true,
                  prefixIcon: Icon(Icons.search_rounded, color: accent, size: 20),
                  suffixIcon: searchCtrl.text.isNotEmpty
                      ? IconButton(
                          icon: const Icon(Icons.clear_rounded, size: 18),
                          onPressed: onClearSearch,
                        )
                      : IconButton(
                          icon: Icon(Icons.arrow_forward_rounded, color: accent, size: 20),
                          onPressed: onSearch,
                        ),
                  filled: true,
                  fillColor: const Color(0xFFF6F7FC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Color(0xFFE8EBF3)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Color(0xFFE8EBF3)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: accent),
                  ),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                ),
              ),
            if (dateMode != InventoryReportDateMode.none) ...[
              if (showSearch) const SizedBox(height: 8),
              InkWell(
                onTap: onPickDates,
                borderRadius: BorderRadius.circular(10),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF6F7FC),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFFE8EBF3)),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        dateMode == InventoryReportDateMode.asOn
                            ? Icons.event_rounded
                            : Icons.date_range_rounded,
                        size: 18,
                        color: accent,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          dateLabel,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF262C50),
                          ),
                        ),
                      ),
                      Text(
                        'Change',
                        style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: accent),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Shared white card tile used by inventory report row builders.
class InventoryReportCard extends StatelessWidget {
  const InventoryReportCard({
    super.key,
    required this.accent,
    required this.title,
    this.subtitle,
    this.trailing,
    this.lines = const [],
  });

  final Color accent;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(12),
      child: Ink(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE8EBF3)),
          boxShadow: const [
            BoxShadow(color: Color(0x08000000), blurRadius: 6, offset: Offset(0, 2)),
          ],
        ),
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
          leading: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              color: Color.lerp(accent, Colors.white, 0.92),
            ),
            child: Icon(Icons.inventory_2_outlined, color: accent, size: 20),
          ),
          title: Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              fontSize: 14,
              color: Color(0xFF262C50),
            ),
          ),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (subtitle != null && subtitle!.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(subtitle!, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700)),
              ],
              for (final line in lines)
                if (line.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(line, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ],
            ],
          ),
          trailing: trailing,
        ),
      ),
    );
  }
}
