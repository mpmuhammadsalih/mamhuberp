import 'package:flutter/material.dart';

import '../core/network/provider_api_error.dart';
import '../models/grn_receipt.dart';
import '../repositories/purchase_repository.dart';

class PurchaseProvider extends ChangeNotifier {
  PurchaseProvider(this._repository);

  final PurchaseRepository _repository;

  bool isLoading = false;
  /// True while a network list request is in flight (including stale-while-revalidate after cache paint).
  bool isFetchingList = false;
  bool isSubmitting = false;
  String? error;
  Object? errorCause;
  List<GrnReceipt> receipts = [];
  String selectedStatus = 'All';

  Future<void> load({String search = ''}) async {
    error = null;
    errorCause = null;
    isFetchingList = true;
    notifyListeners();

    final statusFilter = selectedStatus == 'All' ? '' : selectedStatus;

    final cached = await _repository.readGrnCache(search: search, status: statusFilter);
    if (cached != null && cached.isNotEmpty) {
      receipts = cached;
      isLoading = false;
      notifyListeners();
    } else {
      isLoading = true;
      notifyListeners();
    }

    try {
      receipts = await _repository.getGrnList(search: search, status: statusFilter);
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
    } finally {
      isLoading = false;
      isFetchingList = false;
      notifyListeners();
    }
  }

  Future<void> updateStatus(String status, {String search = ''}) async {
    selectedStatus = status;
    await load(search: search);
  }

  Future<bool> finalizeReceiving({required String poNo, String search = ''}) async {
    isSubmitting = true;
    error = null;
    errorCause = null;
    notifyListeners();
    try {
      await _repository.finalizeReceiving(poNo: poNo);
      await load(search: search);
      return true;
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      return false;
    } finally {
      isSubmitting = false;
      notifyListeners();
    }
  }

  /// ERP GRN save — [saveMode] `grn_draft`, `grn_only`, or `grn_invoice_posting`.
  /// [poNo] optional for direct GRN (no purchase order).
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
  }) async {
    if (isSubmitting) {
      throw StateError('A GRN save is already in progress.');
    }
    isSubmitting = true;
    error = null;
    notifyListeners();
    try {
      final result = await _repository.saveGrn(
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
      return result;
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      rethrow;
    } finally {
      isSubmitting = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>> postGrnInventory({
    required String receiptNo,
    String? invoiceNo,
    String? invoiceDate,
    int? warehouseId,
    List<Map<String, dynamic>>? lines,
  }) async {
    isSubmitting = true;
    error = null;
    notifyListeners();
    try {
      return await _repository.postGrnInventory(
        receiptNo: receiptNo,
        invoiceNo: invoiceNo,
        invoiceDate: invoiceDate,
        warehouseId: warehouseId,
        lines: lines,
      );
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      rethrow;
    } finally {
      isSubmitting = false;
      notifyListeners();
    }
  }

  Future<Map<String, dynamic>> postGrnAccounts({required String receiptNo}) async {
    isSubmitting = true;
    error = null;
    notifyListeners();
    try {
      return await _repository.postGrnAccounts(receiptNo: receiptNo);
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      rethrow;
    } finally {
      isSubmitting = false;
      notifyListeners();
    }
  }

  /// Posts RECEIPTHDR / RECEIPTDTL (legacy — prefer [saveGrn]).
  Future<bool> submitFormalGrn({
    required String receiptDate,
    required String supplierCode,
    required String poNo,
    required String invoiceNo,
    required String remarks,
    required List<Map<String, dynamic>> items,
    required String invoiceDate,
  }) async {
    isSubmitting = true;
    error = null;
    notifyListeners();
    try {
      await _repository.createGrn(
        receiptDate: receiptDate,
        supplierCode: supplierCode,
        poNo: poNo,
        invoiceNo: invoiceNo,
        remarks: remarks,
        items: items,
        invoiceDate: invoiceDate,
      );
      return true;
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      return false;
    } finally {
      isSubmitting = false;
      notifyListeners();
    }
  }

  /// Saves one LPODTL row (Pending PO): sets INQUANTITY from [receivedQty]. [lineSeq] optional if item is unique on the PO.
  Future<bool> persistPoLineSnapshot({
    required String poNo,
    required String itemCode,
    int? lineSeq,
    required double receivedQty,
    required double bonusQty,
    required double bonusBaseUnit,
    required bool focEnabled,
    required String batchNo,
    required String expiryDate,
    required String store,
    required String bin,
    String? locationCode,
  }) async {
    error = null;
    notifyListeners();
    try {
      final payload = <String, dynamic>{
        'item_code': itemCode,
        'received_qty': receivedQty,
        'bonus_qty': bonusQty,
        'bonus_base_unit': bonusBaseUnit,
        'foc_enabled': focEnabled,
        'batch_no': batchNo,
        'expiry_date': expiryDate,
        'store_code': store,
        'bin_code': bin,
      };
      if (lineSeq != null && lineSeq >= 1) {
        payload['line_seq'] = lineSeq;
      }
      final lcRaw = locationCode?.trim();
      if (lcRaw != null && lcRaw.isNotEmpty) {
        final n = int.tryParse(lcRaw);
        if (n != null) {
          payload['LOCATIONCODE'] = n;
        }
      }
      await _repository.patchLpoLine(
        poNo: poNo,
        payload: payload,
      );
      return true;
    } catch (e) {
      errorCause = e;
      error = providerApiError(e);
      notifyListeners();
      return false;
    }
  }
}
