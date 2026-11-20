import 'package:flutter/material.dart';

import '../core/network/provider_api_error.dart';
import '../models/dashboard_summary.dart';
import '../repositories/dashboard_repository.dart';

const _monthNames = <String>[
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

String _isoDate(DateTime d) {
  final y = d.year.toString().padLeft(4, '0');
  final m = d.month.toString().padLeft(2, '0');
  final day = d.day.toString().padLeft(2, '0');
  return '$y-$m-$day';
}

DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

String _fmtDay(DateTime d) {
  final day = d.day.toString().padLeft(2, '0');
  return '$day ${_monthNames[d.month - 1]} ${d.year}';
}

String formatDashboardPeriodLabel(DateTime from, DateTime to) {
  final f = _dateOnly(from);
  final t = _dateOnly(to);
  final today = _dateOnly(DateTime.now());
  final yesterday = today.subtract(const Duration(days: 1));
  if (f == t) {
    if (f == today) return 'Today, ${_fmtDay(f)}';
    if (f == yesterday) return 'Yesterday, ${_fmtDay(f)}';
    return _fmtDay(f);
  }
  return '${_fmtDay(f)} – ${_fmtDay(t)}';
}

class DashboardProvider extends ChangeNotifier {
  DashboardProvider(this._repository);

  final DashboardRepository _repository;

  bool isLoading = false;

  /// Covers pull-to-refresh and background fetch when [summary] is already shown.
  bool isRefreshing = false;
  String? error;
  Object? errorCause;
  DashboardSummary? summary;

  DateTime dateFrom = _dateOnly(DateTime.now());
  DateTime dateTo = _dateOnly(DateTime.now());

  String get dateFromIso => _isoDate(dateFrom);
  String get dateToIso => _isoDate(dateTo);

  /// Always reflects the selected range (updates immediately on pick).
  String get periodLabel => formatDashboardPeriodLabel(dateFrom, dateTo);

  Future<void> load({DateTime? nextFrom, DateTime? nextTo}) async {
    if (nextFrom != null || nextTo != null) {
      final f = _dateOnly(nextFrom ?? dateFrom);
      final t = _dateOnly(nextTo ?? dateTo);
      if (f.isAfter(t)) {
        dateFrom = t;
        dateTo = f;
      } else {
        dateFrom = f;
        dateTo = t;
      }
    }

    error = null;
    errorCause = null;
    isRefreshing = true;
    // Push selected dates to UI immediately (before network).
    notifyListeners();

    final cached = await _repository.readSummaryCache(
      dateFrom: dateFromIso,
      dateTo: dateToIso,
    );
    if (cached != null) {
      summary = cached;
      isLoading = false;
      notifyListeners();
    } else if (summary == null) {
      isLoading = true;
      notifyListeners();
    }

    try {
      summary = await _repository.getSummary(
        dateFrom: dateFromIso,
        dateTo: dateToIso,
      );
      final serverFrom = (summary?.dateFrom ?? '').trim();
      final serverTo = (summary?.dateTo ?? '').trim();
      if (serverFrom.isNotEmpty) {
        final parsed = DateTime.tryParse(serverFrom);
        if (parsed != null) dateFrom = _dateOnly(parsed);
      }
      if (serverTo.isNotEmpty) {
        final parsed = DateTime.tryParse(serverTo);
        if (parsed != null) dateTo = _dateOnly(parsed);
      }
      error = null;
      errorCause = null;
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      if (summary == null) {
        // keep error for full-screen body
      }
    } finally {
      isLoading = false;
      isRefreshing = false;
      notifyListeners();
    }
  }

  Future<void> setToday() {
    final t = _dateOnly(DateTime.now());
    return load(nextFrom: t, nextTo: t);
  }

  Future<void> setYesterday() {
    final t = _dateOnly(DateTime.now()).subtract(const Duration(days: 1));
    return load(nextFrom: t, nextTo: t);
  }

  Future<void> setLast7Days() {
    final end = _dateOnly(DateTime.now());
    final start = end.subtract(const Duration(days: 6));
    return load(nextFrom: start, nextTo: end);
  }

  Future<void> setThisMonth() {
    final end = _dateOnly(DateTime.now());
    final start = DateTime(end.year, end.month, 1);
    return load(nextFrom: start, nextTo: end);
  }

  Future<void> setCustomRange(DateTime from, DateTime to) {
    return load(nextFrom: from, nextTo: to);
  }
}
