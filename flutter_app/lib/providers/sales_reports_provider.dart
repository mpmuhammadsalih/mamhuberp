import 'package:flutter/material.dart';

import '../core/network/provider_api_error.dart';
import '../models/sales_reports.dart';
import '../repositories/sales_reports_repository.dart';

enum SalesReportsPeriod { today, last7, last30, last90, custom }

extension SalesReportsPeriodX on SalesReportsPeriod {
  String label({DateTime? customFrom, DateTime? customTo}) {
    switch (this) {
      case SalesReportsPeriod.today:
        return 'Today';
      case SalesReportsPeriod.last7:
        return '7 days';
      case SalesReportsPeriod.last30:
        return '30 days';
      case SalesReportsPeriod.last90:
        return '90 days';
      case SalesReportsPeriod.custom:
        if (customFrom != null && customTo != null) {
          return '${_fmtShort(customFrom)} – ${_fmtShort(customTo)}';
        }
        return 'Custom';
    }
  }

  (String from, String to) dateRange({DateTime? customFrom, DateTime? customTo}) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    String iso(DateTime d) =>
        '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    switch (this) {
      case SalesReportsPeriod.today:
        return (iso(today), iso(today));
      case SalesReportsPeriod.last7:
        return (iso(today.subtract(const Duration(days: 6))), iso(today));
      case SalesReportsPeriod.last30:
        return (iso(today.subtract(const Duration(days: 29))), iso(today));
      case SalesReportsPeriod.last90:
        return (iso(today.subtract(const Duration(days: 89))), iso(today));
      case SalesReportsPeriod.custom:
        final from = customFrom ?? today.subtract(const Duration(days: 29));
        final to = customTo ?? today;
        if (from.isAfter(to)) return (iso(to), iso(from));
        return (iso(from), iso(to));
    }
  }
}

String _fmtShort(DateTime d) => '${d.day}/${d.month}/${d.year}';

DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

class SalesReportsProvider extends ChangeNotifier {
  SalesReportsProvider(this._repository);

  final SalesReportsRepository _repository;

  SalesReportsPeriod period = SalesReportsPeriod.last30;
  DateTime? customDateFrom;
  DateTime? customDateTo;
  bool isLoading = false;
  bool isRefreshing = false;
  String? error;
  Object? errorCause;
  SalesReportsData? data;

  (String from, String to) get activeDateRange =>
      period.dateRange(customFrom: customDateFrom, customTo: customDateTo);

  Future<void> load({
    SalesReportsPeriod? nextPeriod,
    DateTime? customFrom,
    DateTime? customTo,
    bool forceRefresh = false,
  }) async {
    if (nextPeriod != null) period = nextPeriod;
    if (customFrom != null) customDateFrom = _dateOnly(customFrom);
    if (customTo != null) customDateTo = _dateOnly(customTo);
    if (period == SalesReportsPeriod.custom &&
        customDateFrom != null &&
        customDateTo != null &&
        customDateFrom!.isAfter(customDateTo!)) {
      final swap = customDateFrom;
      customDateFrom = customDateTo;
      customDateTo = swap;
    }

    error = null;
    errorCause = null;
    isRefreshing = true;
    notifyListeners();

    final (from, to) = activeDateRange;
    final cached = await _repository.readCache(from, to);
    if (cached != null) {
      data = cached;
      isLoading = false;
      notifyListeners();
    } else {
      isLoading = true;
      notifyListeners();
    }

    final skipNetwork = !forceRefresh && cached != null && await _repository.isCacheFresh(from, to);
    if (skipNetwork) {
      isRefreshing = false;
      notifyListeners();
      return;
    }

    try {
      data = await _repository.getReports(dateFrom: from, dateTo: to, forceRefresh: forceRefresh);
      if (data?.error != null && data!.dailyTrend.isEmpty) {
        error = data!.error;
      }
    } catch (e) {
      if (data == null) {
        errorCause = e;
        error = providerApiError(e);
      }
    } finally {
      isLoading = false;
      isRefreshing = false;
      notifyListeners();
    }
  }
}
