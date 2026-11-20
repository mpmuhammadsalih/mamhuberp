import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/transaction_date_setup_service.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/loading_overlay.dart';
import '../../core/theme/app_theme.dart';

class TransactionDateSetupScreen extends StatefulWidget {
  const TransactionDateSetupScreen({super.key});

  @override
  State<TransactionDateSetupScreen> createState() => _TransactionDateSetupScreenState();
}

class _TransactionDateSetupScreenState extends State<TransactionDateSetupScreen> {
  static const _navy = Color(0xFF1F2544);
  static const _accent = Color(0xFF4F6BED);

  bool _loading = true;
  bool _busy = false;
  String? _error;
  TxnDateSetupBootstrap? _data;

  int? _locationCode;
  String _mode = 'all';
  DateTime? _allFrom;
  DateTime? _allTo;
  final Map<String, DateTime?> _modFrom = {};
  final Map<String, DateTime?> _modTo = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  DateTime? _parseDate(String raw) {
    final s = raw.trim();
    if (s.isEmpty) return null;
    return DateTime.tryParse(s.length >= 10 ? s.substring(0, 10) : s);
  }

  String _iso(DateTime? d) {
    if (d == null) return '';
    final y = d.year.toString().padLeft(4, '0');
    final m = d.month.toString().padLeft(2, '0');
    final day = d.day.toString().padLeft(2, '0');
    return '$y-$m-$day';
  }

  String _fmt(DateTime? d) {
    if (d == null) return 'Select';
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${d.day.toString().padLeft(2, '0')} ${months[d.month - 1]} ${d.year}';
  }

  void _applyBootstrap(TxnDateSetupBootstrap boot) {
    _data = boot;
    _locationCode = boot.locationCode;
    _mode = boot.mode == 'separate' ? 'separate' : 'all';
    _allFrom = _parseDate(boot.allDateFrom) ?? DateTime.now();
    _allTo = _parseDate(boot.allDateTo) ?? _allFrom;
    _modFrom.clear();
    _modTo.clear();
    for (final m in boot.modules) {
      _modFrom[m.key] = _parseDate(m.dateFrom) ?? _allFrom;
      _modTo[m.key] = _parseDate(m.dateTo) ?? _modFrom[m.key];
    }
  }

  Future<void> _load({int? locationCode}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final boot = await context.read<TransactionDateSetupService>().getBootstrap(
            locationCode: locationCode ?? _locationCode,
          );
      if (!mounted) return;
      setState(() {
        _applyBootstrap(boot);
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

  DateTime _firstDateFor(String? moduleKey) {
    final boot = _data;
    if (boot == null || boot.allowAnyDate) return DateTime(2015);
    String minRaw = boot.minDate;
    if (moduleKey != null) {
      for (final m in boot.modules) {
        if (m.key == moduleKey && m.minDate.isNotEmpty) {
          minRaw = m.minDate;
          break;
        }
      }
    }
    return _parseDate(minRaw) ?? DateTime(2015);
  }

  Future<void> _pickDate({
    required DateTime? initial,
    required ValueChanged<DateTime> onPicked,
    String? moduleKey,
  }) async {
    final first = _firstDateFor(moduleKey);
    final today = DateTime.now();
    final last = DateTime(today.year + 2, 12, 31);
    var init = initial ?? today;
    if (init.isBefore(first)) init = first;
    if (init.isAfter(last)) init = last;
    final picked = await showDatePicker(
      context: context,
      initialDate: init,
      firstDate: first,
      lastDate: last,
      helpText: 'Select date',
    );
    if (picked != null) onPicked(DateTime(picked.year, picked.month, picked.day));
  }

  Future<void> _save() async {
    final loc = _locationCode;
    if (loc == null || loc <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select a location.')),
      );
      return;
    }
    final payload = <String, dynamic>{
      'location_code': loc,
      'mode': _mode,
    };
    if (_mode == 'all') {
      final from = _allFrom;
      final to = _allTo ?? from;
      if (from == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Enter From / To dates.')),
        );
        return;
      }
      payload['all_date_from'] = _iso(from);
      payload['all_date_to'] = _iso(to);
    } else {
      final moduleDates = <String, dynamic>{};
      final modules = _data?.modules ?? const <TxnDateModule>[];
      for (final m in modules) {
        final from = _modFrom[m.key];
        final to = _modTo[m.key] ?? from;
        if (from == null) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${m.label}: enter From / To dates.')),
          );
          return;
        }
        moduleDates[m.key] = {'from': _iso(from), 'to': _iso(to)};
      }
      payload['module_dates'] = moduleDates;
    }

    setState(() => _busy = true);
    try {
      final boot = await context.read<TransactionDateSetupService>().save(payload);
      if (!mounted) return;
      setState(() => _applyBootstrap(boot));
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(boot.message.isNotEmpty ? boot.message : 'Saved.')),
      );
      if (boot.warnings.isNotEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(boot.warnings.join('\n'))),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _closeDay() async {
    final loc = _locationCode;
    if (loc == null || loc <= 0) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Close day?'),
        content: const Text(
          'Close open transaction dates for this location? Documents will no longer post on those dates until reopened.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Close day')),
        ],
      ),
    );
    if (ok != true || !mounted) return;

    setState(() => _busy = true);
    try {
      final boot = await context.read<TransactionDateSetupService>().close({
        'location_code': loc,
        'mode': _mode,
      });
      if (!mounted) return;
      setState(() => _applyBootstrap(boot));
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(boot.message.isNotEmpty ? boot.message : 'Closed.')),
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF3F5FA),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        title: const Text('Transaction Date Setup'),
        elevation: 0,
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _busy || _loading ? null : () => _load(),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: _loading
          ? const AppLoadingIndicator()
          : _error != null && _data == null
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
              : LoadingOverlay(
                  loading: _busy,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
                    children: [
                      if (_data?.allowAnyDate == true)
                        Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFFEFF6FF),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: const Color(0xFFBFDBFE)),
                          ),
                          child: const Text(
                            'Admin mode: you can open past or previously closed business days. Period Closing still blocks closed accounting months.',
                            style: TextStyle(fontSize: 12.5, color: Color(0xFF1E40AF), height: 1.35),
                          ),
                        ),
                      _card(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Text('Location', style: TextStyle(fontWeight: FontWeight.w700, color: _navy)),
                            const SizedBox(height: 8),
                            DropdownButtonFormField<int>(
                              value: _locationCode,
                              decoration: _fieldDecoration(),
                              items: [
                                for (final loc in _data?.locations ?? const <TxnDateLocation>[])
                                  DropdownMenuItem(value: loc.code, child: Text(loc.label, overflow: TextOverflow.ellipsis)),
                              ],
                              onChanged: _busy
                                  ? null
                                  : (v) {
                                      if (v == null) return;
                                      _locationCode = v;
                                      _load(locationCode: v);
                                    },
                            ),
                            const SizedBox(height: 14),
                            const Text('Date mode', style: TextStyle(fontWeight: FontWeight.w700, color: _navy)),
                            const SizedBox(height: 6),
                            Wrap(
                              spacing: 8,
                              children: [
                                ChoiceChip(
                                  label: const Text('Same for all'),
                                  selected: _mode == 'all',
                                  onSelected: _busy ? null : (_) => setState(() => _mode = 'all'),
                                  selectedColor: _accent.withValues(alpha: 0.18),
                                  labelStyle: TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: _mode == 'all' ? _accent : _navy,
                                  ),
                                ),
                                ChoiceChip(
                                  label: const Text('Separate by module'),
                                  selected: _mode == 'separate',
                                  onSelected: _busy ? null : (_) => setState(() => _mode = 'separate'),
                                  selectedColor: _accent.withValues(alpha: 0.18),
                                  labelStyle: TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: _mode == 'separate' ? _accent : _navy,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      if (_mode == 'all')
                        _card(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Text(
                                'Open date range (all modules)',
                                style: TextStyle(fontWeight: FontWeight.w800, color: _navy),
                              ),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: _dateTile(
                                      label: 'From',
                                      value: _allFrom,
                                      onTap: () => _pickDate(
                                        initial: _allFrom,
                                        onPicked: (d) => setState(() {
                                          _allFrom = d;
                                          if (_allTo != null && _allTo!.isBefore(d)) _allTo = d;
                                        }),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: _dateTile(
                                      label: 'To',
                                      value: _allTo,
                                      onTap: () => _pickDate(
                                        initial: _allTo ?? _allFrom,
                                        onPicked: (d) => setState(() {
                                          _allTo = d;
                                          if (_allFrom != null && d.isBefore(_allFrom!)) _allFrom = d;
                                        }),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        )
                      else
                        _card(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Text(
                                'Open date range by module',
                                style: TextStyle(fontWeight: FontWeight.w800, color: _navy),
                              ),
                              const SizedBox(height: 8),
                              for (final m in _data?.modules ?? const <TxnDateModule>[]) ...[
                                const SizedBox(height: 10),
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        m.label,
                                        style: const TextStyle(fontWeight: FontWeight.w700, color: _navy),
                                      ),
                                    ),
                                    _statusChip(m),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Row(
                                  children: [
                                    Expanded(
                                      child: _dateTile(
                                        label: 'From',
                                        value: _modFrom[m.key],
                                        onTap: () => _pickDate(
                                          initial: _modFrom[m.key],
                                          moduleKey: m.key,
                                          onPicked: (d) => setState(() {
                                            _modFrom[m.key] = d;
                                            final to = _modTo[m.key];
                                            if (to != null && to.isBefore(d)) _modTo[m.key] = d;
                                          }),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: _dateTile(
                                        label: 'To',
                                        value: _modTo[m.key],
                                        onTap: () => _pickDate(
                                          initial: _modTo[m.key] ?? _modFrom[m.key],
                                          moduleKey: m.key,
                                          onPicked: (d) => setState(() {
                                            _modTo[m.key] = d;
                                            final from = _modFrom[m.key];
                                            if (from != null && d.isBefore(from)) _modFrom[m.key] = d;
                                          }),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ],
                          ),
                        ),
                      if ((_data?.modules ?? const []).isNotEmpty && _mode == 'all') ...[
                        const SizedBox(height: 12),
                        _card(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Text(
                                'Current status',
                                style: TextStyle(fontWeight: FontWeight.w800, color: _navy),
                              ),
                              const SizedBox(height: 8),
                              for (final m in _data!.modules)
                                Padding(
                                  padding: const EdgeInsets.symmetric(vertical: 4),
                                  child: Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          m.label,
                                          style: const TextStyle(fontWeight: FontWeight.w600, color: _navy),
                                        ),
                                      ),
                                      Text(
                                        m.dateFrom.isEmpty
                                            ? '—'
                                            : (m.dateFrom == m.dateTo
                                                ? m.dateFrom
                                                : '${m.dateFrom} → ${m.dateTo}'),
                                        style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
                                      ),
                                      const SizedBox(width: 8),
                                      _statusChip(m),
                                    ],
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ],
                      if ((_data?.closedPeriods ?? const []).isNotEmpty) ...[
                        const SizedBox(height: 12),
                        _card(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const Text(
                                'Closed accounting periods',
                                style: TextStyle(fontWeight: FontWeight.w800, color: _navy),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                'Ranges overlapping these months cannot be opened.',
                                style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
                              ),
                              const SizedBox(height: 8),
                              for (final p in _data!.closedPeriods.take(8))
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 4),
                                  child: Text(
                                    '${p['period_label'] ?? ''}  ${p['start_date'] ?? ''} – ${p['end_date'] ?? ''}'
                                        .trim(),
                                    style: const TextStyle(fontSize: 12.5, color: _navy),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ],
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: _busy ? null : _closeDay,
                              icon: const Icon(Icons.lock_outline_rounded),
                              label: const Text('Close day'),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: const Color(0xFFB91C1C),
                                side: const BorderSide(color: Color(0xFFFECACA)),
                                padding: const EdgeInsets.symmetric(vertical: 14),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: FilledButton.icon(
                              onPressed: _busy ? null : _save,
                              icon: const Icon(Icons.save_rounded),
                              label: const Text('Save'),
                              style: FilledButton.styleFrom(
                                backgroundColor: _accent,
                                padding: const EdgeInsets.symmetric(vertical: 14),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
    );
  }

  Widget _card({required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: child,
    );
  }

  InputDecoration _fieldDecoration() {
    return InputDecoration(
      filled: true,
      fillColor: const Color(0xFFF8FAFC),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: Color(0xFFE4E7F0))),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: Color(0xFFE4E7F0))),
    );
  }

  Widget _dateTile({
    required String label,
    required DateTime? value,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: _busy ? null : onTap,
      borderRadius: BorderRadius.circular(10),
      child: InputDecorator(
        decoration: _fieldDecoration().copyWith(labelText: label),
        child: Row(
          children: [
            Expanded(
              child: Text(
                _fmt(value),
                style: const TextStyle(fontWeight: FontWeight.w700, color: _navy),
              ),
            ),
            Icon(Icons.calendar_today_outlined, size: 16, color: Colors.grey.shade600),
          ],
        ),
      ),
    );
  }

  Widget _statusChip(TxnDateModule m) {
    final open = m.isOpen;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: open ? const Color(0xFFD4EDDA) : const Color(0xFFF1F5F9),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: open ? const Color(0xFFC3E6CB) : const Color(0xFFE2E8F0)),
      ),
      child: Text(
        open ? 'Open' : 'Closed',
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color: open ? const Color(0xFF155724) : const Color(0xFF64748B),
        ),
      ),
    );
  }
}
