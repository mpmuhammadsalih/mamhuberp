import 'dart:async';

import '../core/storage/local_cache.dart';
import '../models/grn_receipt.dart';
import '../services/purchase_service.dart';

class PurchaseRepository {
  PurchaseRepository(this._service, this._cache);

  final PurchaseService _service;
  final LocalCache _cache;

  String _grnListKey({
    required int page,
    required int pageSize,
    required String search,
    required String status,
  }) =>
      'grn_${page}_${pageSize}_${search.trim()}_${status.trim()}';

  /// Offline / stale-first: last successful list snapshot for these parameters.
  Future<List<GrnReceipt>?> readGrnCache({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String status = '',
  }) async {
    final key = _grnListKey(page: page, pageSize: pageSize, search: search, status: status);
    final cached = await _cache.getJsonList(key);
    if (cached == null) return null;
    return cached.cast<Map<String, dynamic>>().map(GrnReceipt.fromJson).toList();
  }

  Future<List<GrnReceipt>> getGrnList({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String status = '',
  }) async {
    final key = _grnListKey(page: page, pageSize: pageSize, search: search, status: status);
    try {
      final rows = await _service.getGrnList(
        page: page,
        pageSize: pageSize,
        search: search,
        status: status,
      );
      unawaited(
        _cache.saveJson(
          key,
          rows
              .map(
                (e) => {
                  'receipt_no': e.receiptNo,
                  'supplier': e.supplier,
                  'po_no': e.poNo,
                  'invoice_no': e.invoiceNo,
                  'receipt_date': e.receiptDate,
                  'amount': e.amount,
                  'remarks': e.remarks,
                  'total_qty': e.totalQty,
                  'status': e.status,
                  'mobile_lines_touched': e.mobileLinesTouched,
                  if (e.mobileLastSavedAt != null) 'mobile_last_saved_at': e.mobileLastSavedAt,
                },
              )
              .toList(),
        ),
      );
      return rows;
    } catch (_) {
      final cached = await _cache.getJsonList(key);
      if (cached == null) rethrow;
      return cached.cast<Map<String, dynamic>>().map(GrnReceipt.fromJson).toList();
    }
  }

  Future<String> createGrn({
    required String receiptDate,
    required String supplierCode,
    required String poNo,
    required String invoiceNo,
    required String remarks,
    required List<Map<String, dynamic>> items,
    String? invoiceDate,
  }) {
    return _service.createGrn(
      receiptDate: receiptDate,
      supplierCode: supplierCode,
      poNo: poNo,
      invoiceNo: invoiceNo,
      remarks: remarks,
      items: items,
      invoiceDate: invoiceDate,
    );
  }

  Future<void> finalizeReceiving({required String poNo}) {
    return _service.finalizeReceiving(poNo: poNo);
  }

  Future<Map<String, dynamic>> saveGrn({
    required String receiptNo,
    required String receiptDate,
    required String supplierCode,
    String poNo = '',
    required String invoiceNo,
    required String invoiceDate,
    required double invoiceAmount,
    required String remarks,
    required List<Map<String, dynamic>> lines,
    required String saveMode,
    int? warehouseId,
  }) {
    return _service.saveGrn(
      receiptNo: receiptNo,
      receiptDate: receiptDate,
      supplierCode: supplierCode,
      poNo: poNo,
      invoiceNo: invoiceNo,
      invoiceDate: invoiceDate,
      invoiceAmount: invoiceAmount,
      remarks: remarks,
      lines: lines,
      saveMode: saveMode,
      warehouseId: warehouseId,
    );
  }

  Future<Map<String, dynamic>> postGrnInventory({
    required String receiptNo,
    String? invoiceNo,
    String? invoiceDate,
    int? warehouseId,
    List<Map<String, dynamic>>? lines,
  }) {
    return _service.postGrnInventory(
      receiptNo: receiptNo,
      invoiceNo: invoiceNo,
      invoiceDate: invoiceDate,
      warehouseId: warehouseId,
      lines: lines,
    );
  }

  Future<Map<String, dynamic>> postGrnAccounts({required String receiptNo}) {
    return _service.postGrnAccounts(receiptNo: receiptNo);
  }

  Future<void> patchLpoLine({
    required String poNo,
    required Map<String, dynamic> payload,
  }) {
    return _service.patchLpoLine(poNo: poNo, payload: payload);
  }
}
