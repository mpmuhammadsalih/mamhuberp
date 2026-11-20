import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../core/network/api_client.dart';
import '../models/grn_receipt.dart';

class PurchaseService {
  PurchaseService(this._apiClient);

  final ApiClient _apiClient;

  Future<List<GrnReceipt>> getGrnList({
    int page = 1,
    int pageSize = 20,
    String search = '',
    String status = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/grn',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        if (search.trim().isNotEmpty) 'search': search.trim(),
        if (status.trim().isNotEmpty) 'status': status.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map(GrnReceipt.fromJson).toList();
  }

  Future<String> createGrn({
    required String receiptDate,
    required String supplierCode,
    required String poNo,
    required String invoiceNo,
    required String remarks,
    required List<Map<String, dynamic>> items,
    String? invoiceDate,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn',
      data: {
        'receipt_date': receiptDate,
        'supplier_code': supplierCode,
        'po_no': poNo,
        'invoice_no': invoiceNo,
        'remarks': remarks,
        'items': items,
        if (invoiceDate != null && invoiceDate.trim().isNotEmpty) 'invoice_date': invoiceDate.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    return (data['receipt_no'] ?? '').toString();
  }

  Future<void> finalizeReceiving({required String poNo}) async {
    final enc = Uri.encodeComponent(poNo);
    await _apiClient.dio.post('/api/v1/purchase/po/$enc/finalize-receiving');
  }

  /// Persists receiving fields onto [LPODTL] (INQUANTITY) for a Pending PO.
  Future<void> patchLpoLine({
    required String poNo,
    required Map<String, dynamic> payload,
  }) async {
    final enc = Uri.encodeComponent(poNo);
    // POST: same Flask handler as PATCH; POST is accepted by more proxies than PATCH.
    await _apiClient.dio.post('/api/v1/purchase/po/$enc/line', data: payload);
  }

  Future<Map<String, dynamic>> getGrnDetails(String receiptNo) async {
    final enc = Uri.encodeComponent(receiptNo);
    final response = await _apiClient.dio.get('/api/v1/purchase/grn/$enc');
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> loadGrnFromLpo(String lpoNo) async {
    final enc = Uri.encodeComponent(lpoNo.trim());
    final response = await _apiClient.dio.get('/api/v1/purchase/grn/load-from-lpo/$enc');
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>);
  }

  Future<String> nextGrnNo() async {
    final response = await _apiClient.dio.get('/api/v1/purchase/grn/next-no');
    final data = (response.data as Map<String, dynamic>)['data'];
    if (data is Map) {
      return '${data['receipt_no'] ?? ''}'.trim();
    }
    return '';
  }

  /// ERP save — [saveMode] `grn_draft`, `grn_only` (stock), or `grn_invoice_posting` (stock + accounts).
  /// [poNo] is optional (direct GRN without PO).
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
    final mode = saveMode.trim().toLowerCase();
    final postInventory = mode == 'grn_only' || mode == 'grn_invoice_posting';
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn/save',
      data: {
        'receipt_no': receiptNo,
        'receipt_date': receiptDate,
        'supplier_code': supplierCode,
        if (poNo.trim().isNotEmpty) 'po_no': poNo.trim(),
        'invoice_no': invoiceNo,
        'invoice_date': invoiceDate,
        'invoice_amount': invoiceAmount,
        'remarks': remarks,
        'lines': lines,
        'save_mode': mode.isEmpty ? 'grn_draft' : mode,
        'post_inventory': postInventory,
        if (warehouseId != null) 'warehouse_id': warehouseId,
      },
    );
    final raw = response.data;
    if (raw is! Map) {
      throw Exception('Unexpected save response from server.');
    }
    final root = Map<String, dynamic>.from(raw);
    if (root['success'] == false) {
      final msg = '${root['message'] ?? 'Failed to save GRN'}'.trim();
      throw Exception(msg.isEmpty ? 'Failed to save GRN' : msg);
    }
    final data = root['data'];
    final map = data is Map
        ? Map<String, dynamic>.from(data)
        : root;
    final no = '${map['receipt_no'] ?? map['receiptno'] ?? ''}'.trim();
    if (no.isEmpty && receiptNo.trim().isEmpty) {
      throw Exception('Save completed but no GRN number was returned. Check the GRN list.');
    }
    return map;
  }

  Future<Map<String, dynamic>> postGrnInventory({
    required String receiptNo,
    String? invoiceNo,
    String? invoiceDate,
    int? warehouseId,
    List<Map<String, dynamic>>? lines,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn/post-inventory',
      data: {
        'receipt_no': receiptNo,
        if (invoiceNo != null) 'invoice_no': invoiceNo,
        if (invoiceDate != null) 'invoice_date': invoiceDate,
        if (warehouseId != null) 'warehouse_id': warehouseId,
        if (lines != null) 'lines': lines,
      },
    );
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  Future<Map<String, dynamic>> postGrnAccounts({required String receiptNo}) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn/post-accounts',
      data: {'receipt_no': receiptNo},
    );
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  /// Cancel/delete a draft GRN (not stock-posted). Linked PO returns to Pending.
  Future<Map<String, dynamic>> cancelGrn(String receiptNo) async {
    final enc = Uri.encodeComponent(receiptNo.trim());
    final response = await _apiClient.dio.post('/api/v1/purchase/grn/$enc/cancel');
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  Future<List<GrnReceipt>> getGrnHubPending({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/grn',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'grn_hub': 'pending',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map(GrnReceipt.fromJson).toList();
  }

  Future<List<GrnReceipt>> getGrnHubPosted({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/grn',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'grn_hub': 'posted',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map(GrnReceipt.fromJson).toList();
  }

  Future<List<GrnReceipt>> getGrnHubDraft({
    int page = 1,
    int pageSize = 20,
    String search = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/grn',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        'grn_hub': 'draft',
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    final data = root['data'] as Map<String, dynamic>;
    final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
    return rows.map(GrnReceipt.fromJson).toList();
  }

  /// ERP AI invoice extract — multipart field `file` (images/PDF). Long-running.
  Future<Map<String, dynamic>> extractGrnAiInvoice({
    required List<({Uint8List bytes, String filename})> files,
  }) async {
    final form = FormData();
    for (final f in files) {
      form.files.add(
        MapEntry(
          'file',
          MultipartFile.fromBytes(f.bytes, filename: f.filename),
        ),
      );
    }
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn/ai/extract',
      data: form,
      options: Options(
        sendTimeout: const Duration(minutes: 3),
        receiveTimeout: const Duration(minutes: 5),
        contentType: 'multipart/form-data',
      ),
    );
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  Future<Map<String, dynamic>> grnAiQuickItemLookups() async {
    final response = await _apiClient.dio.get('/api/v1/purchase/grn/ai/quick-item');
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  Future<Map<String, dynamic>> grnAiBarcodeCheck(String barcode) async {
    final response = await _apiClient.dio.get(
      '/api/v1/purchase/grn/ai/quick-item/barcode-check',
      queryParameters: {'barcode': barcode.trim()},
    );
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  Future<Map<String, dynamic>> createGrnAiQuickItem(Map<String, dynamic> payload) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn/ai/quick-item',
      data: payload,
    );
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  /// ERP Item Master AI: barcode web + similar-item general fill.
  Future<Map<String, dynamic>> suggestGrnAiQuickItem({
    String barcode = '',
    String itemName = '',
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/purchase/grn/ai/quick-item/suggest',
      data: {
        if (barcode.trim().isNotEmpty) 'barcode': barcode.trim(),
        if (itemName.trim().isNotEmpty) 'item_name': itemName.trim(),
      },
    );
    final root = response.data as Map<String, dynamic>;
    return (root['data'] as Map<String, dynamic>? ?? root);
  }

  /// ERP GRN PDF bytes for [receiptNo].
  Future<List<int>> downloadGrnPdf(String receiptNo) async {
    final encoded = Uri.encodeComponent(receiptNo.trim());
    final response = await _apiClient.dio.get<List<int>>(
      '/api/v1/purchase/grn/$encoded/pdf',
      options: Options(responseType: ResponseType.bytes),
    );
    final bytes = response.data;
    if (bytes == null || bytes.isEmpty) {
      throw Exception('Empty PDF response.');
    }
    return bytes;
  }
}
