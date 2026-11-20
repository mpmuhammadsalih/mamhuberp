import 'package:flutter/material.dart';

import '../core/network/provider_api_error.dart';
import '../models/business_summary.dart';
import '../repositories/business_summary_repository.dart';

enum BusinessSummaryPeriod { today, thisMonth, last7, last30, custom }

extension BusinessSummaryPeriodX on BusinessSummaryPeriod {
  String label({DateTime? customFrom, DateTime? customTo}) {
    switch (this) {
      case BusinessSummaryPeriod.today:
        return 'Today';
      case BusinessSummaryPeriod.thisMonth:
        return 'This month';
      case BusinessSummaryPeriod.last7:
        return '7 days';
      case BusinessSummaryPeriod.last30:
        return '30 days';
      case BusinessSummaryPeriod.custom:
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
      case BusinessSummaryPeriod.today:
        return (iso(today), iso(today));
      case BusinessSummaryPeriod.thisMonth:
        return (iso(DateTime(today.year, today.month, 1)), iso(today));
      case BusinessSummaryPeriod.last7:
        return (iso(today.subtract(const Duration(days: 6))), iso(today));
      case BusinessSummaryPeriod.last30:
        return (iso(today.subtract(const Duration(days: 29))), iso(today));
      case BusinessSummaryPeriod.custom:
        final from = customFrom ?? DateTime(today.year, today.month, 1);
        final to = customTo ?? today;
        if (from.isAfter(to)) return (iso(to), iso(from));
        return (iso(from), iso(to));
    }
  }
}

String _fmtShort(DateTime d) => '${d.day}/${d.month}/${d.year}';

DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

class BusinessSummaryProvider extends ChangeNotifier {
  BusinessSummaryProvider(this._repository);

  final BusinessSummaryRepository _repository;

  BusinessSummaryPeriod period = BusinessSummaryPeriod.thisMonth;
  DateTime? customDateFrom;
  DateTime? customDateTo;
  bool isLoading = false;
  bool isRefreshing = false;
  String? error;
  Object? errorCause;
  BusinessSummaryData? data;

  (String from, String to) get activeDateRange =>
      period.dateRange(customFrom: customDateFrom, customTo: customDateTo);

  Future<void> load({
    BusinessSummaryPeriod? nextPeriod,
    DateTime? customFrom,
    DateTime? customTo,
    bool forceRefresh = false,
  }) async {
    if (nextPeriod != null) period = nextPeriod;
    if (customFrom != null) customDateFrom = _dateOnly(customFrom);
    if (customTo != null) customDateTo = _dateOnly(customTo);
    if (period == BusinessSummaryPeriod.custom &&
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
      data = await _repository.getSummary(dateFrom: from, dateTo: to, forceRefresh: forceRefresh);
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
