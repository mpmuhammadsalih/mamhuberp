import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/ui/confirm_save.dart';
import '../../providers/purchase_provider.dart';
import '../../services/purchase_order_service.dart';
import '../../services/purchase_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/numeric_text_field.dart';
import 'purchase_order_cart_screen.dart';
import '../../core/theme/app_theme.dart';

enum GrnWizardMode { fromApprovedPo, editDraft, viewPosted }

class _GrnLine {
  _GrnLine({
    required this.code,
    required this.name,
    required this.unit,
    required this.rate,
    required this.qty,
    this.warehouseId,
    this.warehouseCode,
  });

  final String code;
  final String name;
  String unit;
  double rate;
  double qty;
  final int? warehouseId;
  final String? warehouseCode;

  double get amount => qty * rate;
}

class _GrnLineEditResult {
  const _GrnLineEditResult({required this.qty, required this.rate, required this.unit});
  final double qty;
  final double rate;
  final String unit;
}

String _pickStr(Map<String, dynamic> m, List<String> keys, {String fallback = ''}) {
  for (final k in keys) {
    final v = m[k];
    final t = '${v ?? ''}'.trim();
    if (t.isNotEmpty) return t;
  }
  return fallback;
}

double _pickNum(Map<String, dynamic> m, List<String> keys) {
  for (final k in keys) {
    final v = m[k];
    if (v == null) continue;
    if (v is num) return v.toDouble();
    final n = double.tryParse('$v'.replaceAll(',', '').trim());
    if (n != null) return n;
  }
  return 0;
}

String _displayDateToIso(String displayDate) {
  final months = <String, String>{
    'Jan': '01',
    'Feb': '02',
    'Mar': '03',
    'Apr': '04',
    'May': '05',
    'Jun': '06',
    'Jul': '07',
    'Aug': '08',
    'Sep': '09',
    'Oct': '10',
    'Nov': '11',
    'Dec': '12',
  };
  final parts = displayDate.replaceAll(',', '').split(' ').where((e) => e.isNotEmpty).toList();
  if (parts.length == 3 && months.containsKey(parts[0])) {
    return '${parts[2]}-${months[parts[0]]}-${parts[1].padLeft(2, '0')}';
  }
  if (displayDate.length >= 10 && displayDate[4] == '-') return displayDate.substring(0, 10);
  final now = DateTime.now();
  return '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
}

String _stripPoPrefix(String raw) {
  var s = raw.trim();
  if (s.toUpperCase().startsWith('PO-')) {
    s = s.substring(3).trim();
  }
  return s;
}

/// Keep series document numbers (PO-000003) for API lookup — do not strip prefix.
String _poApiKey(String raw) => raw.trim();

class GrnPoWizardScreen extends StatefulWidget {
  const GrnPoWizardScreen({
    required this.poLookupKey,
    this.receiptNo,
    this.initialSupplier = '',
    this.mode = GrnWizardMode.fromApprovedPo,
    this.onSaved,
    super.key,
  });

  final String poLookupKey;
  final String? receiptNo;
  /// Supplier label from list row (fallback if load-from-lpo omits name).
  final String initialSupplier;
  final GrnWizardMode mode;
  final VoidCallback? onSaved;

  @override
  State<GrnPoWizardScreen> createState() => _GrnPoWizardScreenState();
}

class _GrnPoWizardScreenState extends State<GrnPoWizardScreen> {
  static const _accent = Color(0xFF0277BD);

  int _step = 0;
  bool _loading = true;
  String? _loadError;
  Object? _loadErrorCause;

  late String _poDisplay;
  String _poDate = '';
  String _supplierDisp = '';
  String _supplierCode = '';
  String _branchDisp = '';
  String _warehouseDisp = '';
  String _remarks = '';
  String _assignedReceiptNo = '';

  late String _receiptDateDisp;
  late String _invoiceDateDisp;
  final _invoiceNo = TextEditingController();
  final _confirmInvoiceAmount = TextEditingController();

  late String _persistPoNo;
  int? _warehouseId;
  /// `grn_draft` | `grn_only` | `grn_invoice_posting`
  String _saveMode = 'grn_only';
  bool _inventoryPosted = false;
  bool _accountPosted = false;
  bool _canCancel = false;
  bool _cancelling = false;
  bool _postingAccounts = false;
  bool _pdfBusy = false;
  List<_GrnLine> _lines = [];

  bool get _readOnly => widget.mode == GrnWizardMode.viewPosted;

  String get _printReceiptNo {
    final a = _assignedReceiptNo.trim();
    if (a.isNotEmpty) return a;
    return (widget.receiptNo ?? '').trim();
  }

  bool get _canPrint {
    if (_loading || _loadError != null) return false;
    if (_printReceiptNo.isEmpty) return false;
    // From-PO create uses a reserved next number before save — PDF only after a real GRN exists.
    return widget.mode != GrnWizardMode.fromApprovedPo;
  }

  double get _lineTotal => _lines.fold(0.0, (s, l) => s + l.amount);

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    _receiptDateDisp = '${m[now.month - 1]} ${now.day}, ${now.year}';
    _invoiceDateDisp = _receiptDateDisp;
    _persistPoNo = widget.poLookupKey.trim();
    _saveMode = widget.mode == GrnWizardMode.fromApprovedPo ? 'grn_only' : 'grn_draft';
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  String _saveModeLabel() {
    switch (_saveMode) {
      case 'grn_invoice_posting':
        return 'Post stock + accounts';
      case 'grn_only':
        return 'Post stock';
      default:
        return 'Save draft';
    }
  }

  String _fmtQty(double q) => q == q.roundToDouble() ? q.round().toString() : q.toStringAsFixed(2);

  Future<void> _openCart({bool proceedToReview = false}) async {
    final goReview = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => PurchaseOrderCartScreen(
          title: 'GRN cart',
          emptyHint: 'Add items from the Items step.',
          continueLabel: proceedToReview ? 'Checkout' : 'Done',
          lpono: _assignedReceiptNo.isEmpty ? _poDisplay : _assignedReceiptNo,
          lpoDate: _receiptDateDisp,
          getLines: () => _lines
              .map(
                (l) => PurchaseOrderCartLineView(
                  itemCode: l.code,
                  itemName: l.name,
                  uom: l.unit,
                  qty: l.qty,
                  rate: l.rate,
                  amount: l.amount,
                ),
              )
              .toList(),
          getNetTotal: () => _lineTotal,
          onLineDelete: (i) {
            if (_readOnly || i < 0 || i >= _lines.length) return;
            setState(() {
              _lines.removeAt(i);
              _syncConfirmAmount();
            });
          },
          onQtyChanged: (i, qty) {
            if (_readOnly || i < 0 || i >= _lines.length) return;
            setState(() {
              _lines[i].qty = qty;
              _syncConfirmAmount();
            });
          },
          onRateChanged: (i, rate) {
            if (_readOnly || i < 0 || i >= _lines.length) return;
            setState(() {
              _lines[i].rate = rate;
              _syncConfirmAmount();
            });
          },
          onLineEdit: _readOnly
              ? null
              : (i) async {
                  await _editLine(i);
                },
        ),
      ),
    );
    if (!mounted) return;
    setState(() => _syncConfirmAmount());
    if (proceedToReview && goReview == true && _lines.where((l) => l.qty > 0).isNotEmpty) {
      setState(() => _step = 2);
    }
  }

  @override
  void dispose() {
    _invoiceNo.dispose();
    _confirmInvoiceAmount.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _loadErrorCause = null;
    });
    try {
      final svc = context.read<PurchaseService>();
      late Map<String, dynamic> data;
      final poKey = _poApiKey(widget.poLookupKey);
      if (widget.mode == GrnWizardMode.fromApprovedPo) {
        // Pass full series key (PO-000003). Backend also tries 000003 / PO-000003 variants.
        data = await svc.loadGrnFromLpo(poKey);
      } else {
        final key = (widget.receiptNo ?? widget.poLookupKey).trim();
        data = await svc.getGrnDetails(key);
      }

      final docType = _pickStr(data, const ['document_type']);
      final isFormal = docType == 'formal_receipt';
      final isLpo = docType == 'lpo_bootstrap' || widget.mode == GrnWizardMode.fromApprovedPo;

      final rawList = data['items'] ?? data['lines'] ?? const [];
      final items = (rawList is List ? rawList : const [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      final received = <_GrnLine>[];
      for (final e in items) {
        final lineQty = _pickNum(e, const ['qty', 'quantity', 'ordered_qty', 'baseqty']);
        final mq = _pickNum(e, const ['mobile_received_qty']);
        final erpRecv = _pickNum(e, const ['erp_received_qty', 'received_qty', 'inquantity']);
        final useQty = isFormal || isLpo
            ? (lineQty > 0 ? lineQty : erpRecv)
            : (mq > 0 ? mq : (erpRecv > 0 ? erpRecv : 0.0));
        if (useQty <= 0) continue;
        final rate = _pickNum(e, const ['rate']);
        final whId = e['warehouse_id'];
        var code = _pickStr(e, const ['item_code', 'itemcode']);
        final asNum = double.tryParse(code);
        if (asNum != null && asNum == asNum.roundToDouble()) {
          code = asNum.toInt().toString();
        }
        if (code.isEmpty || code == '0') continue;
        received.add(
          _GrnLine(
            code: code,
            name: _pickStr(e, const ['item_name', 'itemname', 'item_code'], fallback: code),
            unit: _pickStr(e, const ['unit', 'uom'], fallback: 'PCS'),
            rate: rate > 0 ? rate : 1,
            qty: useQty,
            warehouseId: whId is num ? whId.toInt() : int.tryParse('$whId'),
            warehouseCode: _pickStr(e, const ['warehouse_code', 'location']),
          ),
        );
      }

      if (!mounted) return;

      final invNo = _pickStr(data, const ['invoice_no', 'invoiceno']);
      final invDate = _pickStr(data, const ['invoice_date', 'invoicedate']);
      final grnDate = _pickStr(data, const ['grn_date', 'receipt_date', 'receiptdate']);
      final whRaw = data['warehouse_id'];
      final whId = whRaw is num ? whRaw.toInt() : int.tryParse('$whRaw');

      setState(() {
        _assignedReceiptNo = _pickStr(data, const ['receipt_no', 'next_receipt_no'], fallback: '');
        _persistPoNo = _pickStr(data, const ['po_no', 'lpono'], fallback: widget.poLookupKey.trim());
        _poDisplay = _persistPoNo.isNotEmpty ? _persistPoNo : widget.poLookupKey.trim();
        _poDate = _pickStr(data, const ['po_date', 'grn_date', 'receipt_date']);
        _supplierDisp = _pickStr(
          data,
          const ['supplier_display', 'supplier_name', 'suppliername', 'supplier'],
          fallback: widget.initialSupplier.trim(),
        );
        _supplierCode = _pickStr(
          data,
          const ['supplier_code', 'suppliercode', 'supplier'],
          fallback: '',
        );
        // Display may be "code - name"; keep numeric code for save when possible.
        if (_supplierCode.isEmpty && _supplierDisp.contains(' - ')) {
          _supplierCode = _supplierDisp.split(' - ').first.trim();
        }
        if (_supplierCode.isEmpty) {
          _supplierCode = _supplierDisp;
        }
        _branchDisp = _pickStr(data, const ['location_name'], fallback: '');
        _warehouseDisp = _pickStr(data, const ['warehouse_display'], fallback: '');
        _warehouseId = whId;
        _remarks = _pickStr(data, const ['remarks'], fallback: '');
        if (grnDate.isNotEmpty) _receiptDateDisp = grnDate;
        if (invDate.isNotEmpty) _invoiceDateDisp = invDate;
        if (invNo.isNotEmpty) _invoiceNo.text = invNo;
        _lines = received;
        _inventoryPosted = data['inventory_posted'] == true ||
            data['inventory_posted'] == 1 ||
            '${data['inventory_posted'] ?? ''}'.toLowerCase() == 'y';
        _accountPosted = data['account_posted'] == true ||
            data['account_posted'] == 1 ||
            '${data['account_posted'] ?? ''}'.toLowerCase() == 'y';
        if (widget.mode == GrnWizardMode.editDraft) {
          _saveMode = 'grn_draft';
        } else if (widget.mode == GrnWizardMode.fromApprovedPo) {
          _saveMode = 'grn_only';
        }
        _canCancel = widget.mode == GrnWizardMode.editDraft &&
            (data['can_delete'] == true ||
                data['can_edit'] == true ||
                '${data['status'] ?? ''}'.toLowerCase() == 'draft');
        _confirmInvoiceAmount.text = _lineTotal.toStringAsFixed(2);
        _loading = false;
      });

      if (received.isEmpty && mounted && widget.mode == GrnWizardMode.fromApprovedPo) {
        final srcCount = data['lpo_line_count'];
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              srcCount is num && srcCount > 0
                  ? 'PO has $srcCount line(s) but qty is zero. Check QUANTITY on LPODTL for this PO.'
                  : 'No lines found on this PO ($poKey). Open the PO in Purchase Order and confirm items were saved.',
            ),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _loadErrorCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  List<Map<String, dynamic>> _buildLinePayload() {
    return _lines
        .where((e) => e.qty > 0)
        .map(
          (e) => {
            'item_code': e.code,
            'itemcode': e.code,
            'qty': e.qty,
            'quantity': e.qty,
            // Do not send receivedqty=qty — API sets base receivedqty = qty × UOM factor
            'rate': e.rate,
            'amount': e.amount,
            'unit': e.unit.isEmpty ? 'PCS' : e.unit,
            'uom': e.unit.isEmpty ? 'PCS' : e.unit,
            if (e.warehouseId != null) 'warehouse_id': e.warehouseId,
            if (e.warehouseCode != null && e.warehouseCode!.isNotEmpty) 'warehouse_code': e.warehouseCode,
          },
        )
        .toList();
  }

  void _syncConfirmAmount() {
    _confirmInvoiceAmount.text = _lineTotal.toStringAsFixed(2);
  }

  Future<_GrnLineEditResult?> _showLineEditDialog({
    required String itemName,
    required String itemCode,
    required String unit,
    required double initialQty,
    required double initialRate,
    required String confirmLabel,
  }) {
    return showDialog<_GrnLineEditResult>(
      context: context,
      builder: (ctx) => _GrnLineEditDialog(
        itemName: itemName,
        itemCode: itemCode,
        initialUnit: unit,
        initialQty: initialQty,
        initialRate: initialRate,
        confirmLabel: confirmLabel,
      ),
    );
  }

  Future<void> _editLine(int index) async {
    if (_readOnly || index < 0 || index >= _lines.length) return;
    final line = _lines[index];
    final edited = await _showLineEditDialog(
      itemName: line.name.isNotEmpty ? line.name : line.code,
      itemCode: line.code,
      unit: line.unit,
      initialQty: line.qty,
      initialRate: line.rate,
      confirmLabel: 'Update line',
    );
    if (!mounted || edited == null) return;
    setState(() {
      if (edited.qty <= 0) {
        _lines.removeAt(index);
      } else {
        line.qty = edited.qty;
        line.rate = edited.rate;
        line.unit = edited.unit;
      }
      _syncConfirmAmount();
    });
  }

  void _removeLine(int index) {
    if (_readOnly || index < 0 || index >= _lines.length) return;
    setState(() {
      _lines.removeAt(index);
      _syncConfirmAmount();
    });
  }

  Future<void> _addItem() async {
    if (_readOnly) return;
    final picked = await showModalBottomSheet<PurchaseCatalogItem>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _GrnItemPickerSheet(
        service: context.read<PurchaseOrderService>(),
      ),
    );
    if (picked == null || !mounted) return;

    final existingIdx = _lines.indexWhere(
      (l) => l.code == picked.itemCode && l.unit.toUpperCase() == picked.uom.toUpperCase(),
    );
    final existing = existingIdx >= 0 ? _lines[existingIdx] : null;
    final edited = await _showLineEditDialog(
      itemName: picked.itemName.isNotEmpty ? picked.itemName : picked.itemCode,
      itemCode: picked.itemCode,
      unit: existing?.unit ?? picked.uom,
      initialQty: existing?.qty ?? 1,
      initialRate: existing?.rate ?? (picked.rate > 0 ? picked.rate : 1),
      confirmLabel: existing != null ? 'Update line' : 'Add line',
    );
    if (!mounted || edited == null || edited.qty <= 0) return;

    setState(() {
      if (existingIdx >= 0) {
        _lines[existingIdx].qty = edited.qty;
        _lines[existingIdx].rate = edited.rate;
        _lines[existingIdx].unit = edited.unit;
      } else {
        _lines.add(
          _GrnLine(
            code: picked.itemCode,
            name: picked.itemName.isNotEmpty ? picked.itemName : picked.itemCode,
            unit: edited.unit,
            rate: edited.rate,
            qty: edited.qty,
            warehouseId: _warehouseId,
            warehouseCode: _warehouseDisp,
          ),
        );
      }
      _syncConfirmAmount();
    });
  }

  Future<void> _submitSave(PurchaseProvider purchase) async {
    if (purchase.isSubmitting) return;
    final lines = _buildLinePayload();
    if (lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add at least one GRN line with qty > 0.')),
      );
      return;
    }
    final confirm = double.tryParse(_confirmInvoiceAmount.text.trim()) ?? 0;
    if ((confirm - _lineTotal).abs() > 0.02) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Confirm invoice amount must match line total (${_lineTotal.toStringAsFixed(2)}).')),
      );
      return;
    }

    final ok = await confirmSaveTransaction(
      context,
      title: 'Save GRN?',
      message: 'Save GRN ${_assignedReceiptNo.isEmpty ? '(new)' : _assignedReceiptNo} for ${_lineTotal.toStringAsFixed(2)}?',
      confirmLabel: 'Save GRN',
      confirmColor: const Color(0xFF0277BD),
    );
    if (!ok || !mounted) return;

    final poBind = _poApiKey(_persistPoNo);
    try {
      final result = await purchase.saveGrn(
        receiptNo: _assignedReceiptNo,
        receiptDate: _displayDateToIso(_receiptDateDisp),
        supplierCode: _supplierCode.isEmpty ? _supplierDisp : _supplierCode,
        poNo: poBind,
        invoiceNo: _invoiceNo.text.trim(),
        invoiceDate: _displayDateToIso(_invoiceDateDisp),
        invoiceAmount: _lineTotal,
        remarks: _remarks.trim(),
        lines: lines,
        saveMode: _saveMode,
        warehouseId: _warehouseId,
      );
      if (!mounted) return;
      widget.onSaved?.call();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${result['message'] ?? 'Saved successfully'}')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(purchase.error ?? 'Failed to save GRN')),
      );
    }
  }

  Future<void> _submitPostInventory(PurchaseProvider purchase) async {
    final ok = await confirmSaveTransaction(
      context,
      title: 'Post GRN stock?',
      message: 'Post stock for GRN $_assignedReceiptNo?',
      confirmLabel: 'Post stock',
      confirmColor: const Color(0xFF0277BD),
    );
    if (!ok || !mounted) return;
    try {
      final result = await purchase.postGrnInventory(
        receiptNo: _assignedReceiptNo,
        invoiceNo: _invoiceNo.text.trim(),
        invoiceDate: _displayDateToIso(_invoiceDateDisp),
        warehouseId: _warehouseId,
        lines: _buildLinePayload(),
      );
      if (!mounted) return;
      widget.onSaved?.call();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${result['message'] ?? 'Stock posted'}')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(purchase.error ?? 'Failed to post stock')),
      );
    }
  }

  Future<void> _submitPostAccounts(PurchaseProvider purchase) async {
    final rn = _assignedReceiptNo.trim();
    if (rn.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Missing GRN number.')),
      );
      return;
    }
    final ok = await confirmSaveTransaction(
      context,
      title: 'Post GRN accounts?',
      message: 'Post accounts for GRN $rn?',
      confirmLabel: 'Post accounts',
      confirmColor: const Color(0xFF0277BD),
    );
    if (!ok || !mounted) return;
    setState(() => _postingAccounts = true);
    try {
      final result = await purchase.postGrnAccounts(receiptNo: rn);
      if (!mounted) return;
      setState(() {
        _accountPosted = true;
        _inventoryPosted = true;
        _postingAccounts = false;
      });
      widget.onSaved?.call();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${result['message'] ?? 'Accounts posted'}')),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() => _postingAccounts = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(purchase.error ?? 'Failed to post accounts')),
      );
    }
  }

  Future<void> _pickDate(ValueChanged<String> onPicked, String current) async {
    if (_readOnly) return;
    DateTime initial = DateTime.now();
    try {
      final iso = _displayDateToIso(current);
      final p = iso.split('-');
      if (p.length == 3) {
        initial = DateTime(int.parse(p[0]), int.parse(p[1]), int.parse(p[2]));
      }
    } catch (_) {}

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    onPicked('${months[picked.month - 1]} ${picked.day}, ${picked.year}');
  }

  InputDecoration _fieldDec(String hint) => InputDecoration(
        hintText: hint,
        filled: true,
        fillColor: const Color(0xFFF6F7FC),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        enabledBorder:
            OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
      );

  String get _title => switch (widget.mode) {
        GrnWizardMode.fromApprovedPo => 'New GRN',
        GrnWizardMode.editDraft => 'Edit GRN',
        GrnWizardMode.viewPosted => 'GRN',
      };

  Future<File> _writeGrnPdfFile() async {
    final rn = _printReceiptNo;
    final bytes = await context.read<PurchaseService>().downloadGrnPdf(rn);
    final dir = await getTemporaryDirectory();
    final safe = rn.replaceAll(RegExp(r'[^\w\-]+'), '_');
    final file = File('${dir.path}/GRN_$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _sharePdf() async {
    if (_pdfBusy || !_canPrint) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writeGrnPdfFile();
      await Share.shareXFiles(
        [XFile(file.path, mimeType: 'application/pdf')],
        subject: 'GRN $_printReceiptNo',
        text: 'GRN $_printReceiptNo',
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _printCopy() async {
    if (_pdfBusy || !_canPrint) return;
    setState(() => _pdfBusy = true);
    try {
      final file = await _writeGrnPdfFile();
      final opened = await OpenFilex.open(file.path, type: 'application/pdf');
      if (!mounted) return;
      if (opened.type != ResultType.done) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(opened.message.isNotEmpty ? opened.message : 'Could not open PDF.')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _pdfBusy = false);
    }
  }

  Future<void> _cancelDraft() async {
    final rn = (_assignedReceiptNo.isNotEmpty ? _assignedReceiptNo : (widget.receiptNo ?? '')).trim();
    if (rn.isEmpty || _cancelling) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel GRN'),
        content: Text(
          'Cancel $rn?\n\nThis deletes the draft receipt. The purchase order will return to Pending.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cancel GRN'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _cancelling = true);
    try {
      await context.read<PurchaseService>().cancelGrn(rn);
      if (!mounted) return;
      widget.onSaved?.call();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$rn canceled.')));
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _cancelling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(
backgroundColor: AppTheme.appBarBlue,
foregroundColor: Colors.white,
surfaceTintColor: Colors.transparent,title: Text(_title)),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (_loadError != null) {
      return Scaffold(
        appBar: AppBar(
backgroundColor: AppTheme.appBarBlue,
foregroundColor: Colors.white,
surfaceTintColor: Colors.transparent,title: Text(_title)),
        body: ApiErrorCenter(message: _loadError!, error: _loadErrorCause),
      );
    }

    final purchase = context.watch<PurchaseProvider>();
    final isLast = _step == 2;
    final rightLabel = _readOnly
        ? (_step < 2 ? 'Next' : 'Close')
        : (_step == 0
            ? 'Next: Items'
            : (_step == 1 ? 'Next: Review' : _saveModeLabel()));

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(_title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          if (_canPrint)
            IconButton(
              tooltip: 'Share PDF',
              onPressed: (_pdfBusy || purchase.isSubmitting) ? null : _sharePdf,
              icon: _pdfBusy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.share_outlined),
            ),
          if (_canPrint)
            IconButton(
              tooltip: 'Print copy',
              onPressed: (_pdfBusy || purchase.isSubmitting) ? null : _printCopy,
              icon: const Icon(Icons.picture_as_pdf_outlined),
            ),
          if (_canCancel)
            IconButton(
              tooltip: 'Cancel GRN',
              onPressed: (_cancelling || purchase.isSubmitting) ? null : _cancelDraft,
              icon: _cancelling
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.cancel_outlined, color: Color(0xFFC62828)),
            ),
        ],
      ),
      body: Column(
        children: [
          if (!_readOnly)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 6, 20, 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _dot(0),
                  Expanded(child: Container(height: 2, color: _step >= 1 ? _accent : const Color(0xFFE8EBF3))),
                  _dot(1),
                  Expanded(child: Container(height: 2, color: _step >= 2 ? _accent : const Color(0xFFE8EBF3))),
                  _dot(2),
                ],
              ),
            ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 92),
              child: switch (_step) {
                0 => _stepHeaderInvoice(),
                1 => _stepItems(),
                _ => _stepReview(),
              },
            ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () {
                        if (_step <= 0) {
                          Navigator.of(context).pop();
                        } else {
                          setState(() => _step -= 1);
                        }
                      },
                      child: Text(_step == 0 ? 'Cancel' : 'Back'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    flex: 2,
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(backgroundColor: _accent),
                      onPressed: purchase.isSubmitting
                          ? null
                          : () async {
                              if (_readOnly) {
                                if (_step < 2) {
                                  setState(() => _step += 1);
                                } else {
                                  Navigator.of(context).pop();
                                }
                                return;
                              }
                              if (_step == 0) {
                                if (_invoiceNo.text.trim().isEmpty || _invoiceDateDisp.isEmpty) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Enter invoice number and invoice date.')),
                                  );
                                  return;
                                }
                                if (_lines.isEmpty) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Nothing to receive on this PO.')),
                                  );
                                  return;
                                }
                                setState(() => _step = 1);
                                return;
                              }
                              if (_step == 1) {
                                if (_lines.where((l) => l.qty > 0).isEmpty) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Add at least one item.')),
                                  );
                                  return;
                                }
                                await _openCart(proceedToReview: true);
                                return;
                              }
                              await _submitSave(purchase);
                            },
                      icon: Icon(isLast && !_readOnly ? Icons.check_circle_outline : Icons.arrow_forward_rounded),
                      label: purchase.isSubmitting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : Text(rightLabel),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _dot(int idx) {
    final past = idx < _step;
    final active = idx == _step;
    return Container(
      width: active ? 26 : 22,
      height: active ? 26 : 22,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: past || active ? _accent : const Color(0xFFE8EBF3),
        shape: BoxShape.circle,
      ),
      child: past
          ? const Icon(Icons.check, size: 14, color: Colors.white)
          : Text(
              '${idx + 1}',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: active ? Colors.white : const Color(0xFF757C8A),
              ),
            ),
    );
  }

  Widget _stepHeaderInvoice() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('From purchase order',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: _accent)),
        const SizedBox(height: 12),
        _readonlyRow('GRN No.', _assignedReceiptNo.isEmpty ? '(auto)' : _assignedReceiptNo),
        const SizedBox(height: 8),
        _readonlyRow('PO No.', _poDisplay),
        const SizedBox(height: 10),
        _readonlyRow('PO Date', _poDate.isEmpty ? '—' : _poDate),
        const SizedBox(height: 10),
        _readonlyRow('Supplier', _supplierDisp.isEmpty ? '—' : _supplierDisp),
        if (_branchDisp.isNotEmpty) ...[
          const SizedBox(height: 10),
          _readonlyRow('Branch', _branchDisp),
        ],
        if (_warehouseDisp.isNotEmpty) ...[
          const SizedBox(height: 10),
          _readonlyRow('Warehouse', _warehouseDisp),
        ],
        const SizedBox(height: 14),
        const Divider(),
        const SizedBox(height: 12),
        const Text('Receipt & supplier invoice',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: _accent)),
        const SizedBox(height: 10),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Receipt date *'),
          subtitle: Text(_receiptDateDisp),
          trailing: const Icon(Icons.calendar_today_rounded),
          onTap: () => _pickDate((v) => setState(() => _receiptDateDisp = v), _receiptDateDisp),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: _invoiceNo,
          readOnly: _readOnly,
          decoration: _fieldDec('Supplier invoice number *'),
        ),
        const SizedBox(height: 12),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Invoice date *'),
          subtitle: Text(_invoiceDateDisp),
          trailing: const Icon(Icons.calendar_today_rounded),
          onTap: () => _pickDate((v) => setState(() => _invoiceDateDisp = v), _invoiceDateDisp),
        ),
      ],
    );
  }

  Widget _readonlyRow(String label, String value) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 100, child: Text(label, style: TextStyle(fontSize: 13, color: Colors.grey.shade700))),
          Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
        ],
      );

  Widget _stepItems() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Lines (${_lines.length})',
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: _accent),
              ),
            ),
            if (_lines.isNotEmpty)
              TextButton.icon(
                onPressed: () => _openCart(proceedToReview: !_readOnly),
                icon: const Icon(Icons.shopping_cart_outlined, size: 18),
                label: Text(_readOnly ? 'View cart' : 'Checkout'),
                style: TextButton.styleFrom(foregroundColor: _accent),
              ),
            if (!_readOnly)
              TextButton.icon(
                onPressed: _addItem,
                icon: const Icon(Icons.add_rounded, size: 18),
                label: const Text('Add item'),
                style: TextButton.styleFrom(foregroundColor: _accent),
              ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Total: ${_lineTotal.toStringAsFixed(2)}',
          style: const TextStyle(fontSize: 13, color: Color(0xFF6F7482)),
        ),
        if (!_readOnly) ...[
          const SizedBox(height: 4),
          Text(
            'Tap a line to edit qty / rate. Open cart to list all items at checkout.',
            style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
          ),
        ],
        const SizedBox(height: 12),
        Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFE8EBF3)),
          ),
          child: Column(
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(10, 10, 10, 6),
                child: Row(children: [
                  SizedBox(width: 26, child: Text('#', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                  Expanded(child: Text('Item', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                  SizedBox(width: 88, child: Text('Qty / Rate', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                ]),
              ),
              const Divider(height: 1),
              if (_lines.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 28),
                  child: Text(
                    _readOnly ? 'No lines.' : 'No lines yet. Tap Add item.',
                    style: TextStyle(color: Colors.grey.shade600),
                  ),
                )
              else
                ..._lines.asMap().entries.map((e) {
                  final i = e.key;
                  final l = e.value;
                  final qtyLabel =
                      l.qty == l.qty.roundToDouble() ? '${l.qty.toInt()} ${l.unit}' : '${l.qty} ${l.unit}';
                  final tile = ListTile(
                    dense: true,
                    onTap: _readOnly ? null : () => _editLine(i),
                    leading: Text('${i + 1}'),
                    title: Text(l.name.isEmpty ? l.code : l.name, style: const TextStyle(fontSize: 13)),
                    subtitle: Text(
                      '${l.code} · @ ${l.rate.toStringAsFixed(2)}',
                      style: const TextStyle(fontSize: 11),
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(qtyLabel, style: const TextStyle(fontWeight: FontWeight.w700)),
                        if (!_readOnly) ...[
                          const SizedBox(width: 4),
                          Icon(Icons.edit_outlined, size: 16, color: Colors.grey.shade600),
                        ],
                      ],
                    ),
                  );
                  if (_readOnly) return tile;
                  return Dismissible(
                    key: ValueKey('grn-line-${l.code}-$i-${l.unit}'),
                    direction: DismissDirection.endToStart,
                    background: Container(
                      alignment: Alignment.centerRight,
                      padding: const EdgeInsets.only(right: 16),
                      color: const Color(0xFFC62828),
                      child: const Icon(Icons.delete_outline, color: Colors.white),
                    ),
                    onDismissed: (_) => _removeLine(i),
                    child: tile,
                  );
                }),
            ],
          ),
        ),
      ],
    );
  }

  Widget _stepReview() {
    final purchase = context.watch<PurchaseProvider>();
    final activeLines = _lines.where((l) => l.qty > 0).toList();
    final canPostAccounts =
        _assignedReceiptNo.trim().isNotEmpty && (_inventoryPosted || _readOnly) && !_accountPosted;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          _readOnly ? 'Checkout' : 'Review & save',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17, color: _accent),
        ),
        const SizedBox(height: 10),
        _readonlyRow('GRN', _assignedReceiptNo),
        _readonlyRow('PO', _poDisplay),
        _readonlyRow('Receipt date', _receiptDateDisp),
        _readonlyRow('Invoice', _invoiceNo.text.trim()),
        _readonlyRow('Invoice date', _invoiceDateDisp),
        _readonlyRow('Line total', _lineTotal.toStringAsFixed(2)),
        if (_readOnly || _inventoryPosted || _accountPosted) ...[
          _readonlyRow('Stock', _inventoryPosted ? 'Posted' : 'Not posted'),
          _readonlyRow('Accounts', _accountPosted ? 'Posted' : 'Not posted'),
        ],
        const SizedBox(height: 14),
        Row(
          children: [
            const Expanded(
              child: Text('Checkout items', style: TextStyle(fontWeight: FontWeight.w700)),
            ),
            TextButton.icon(
              onPressed: () => _openCart(),
              icon: const Icon(Icons.shopping_cart_outlined, size: 18),
              label: const Text('Open cart'),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFE8EBF3)),
          ),
          child: activeLines.isEmpty
              ? Text('No lines.', style: TextStyle(color: Colors.grey.shade600))
              : Column(
                  children: [
                    for (final l in activeLines) ...[
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  l.name.isNotEmpty ? l.name : l.code,
                                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  '${l.code} · ${_fmtQty(l.qty)} ${l.unit} @ ${l.rate.toStringAsFixed(2)}',
                                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                ),
                              ],
                            ),
                          ),
                          Text(l.amount.toStringAsFixed(2), style: const TextStyle(fontWeight: FontWeight.w800)),
                        ],
                      ),
                      if (l != activeLines.last) ...[
                        const SizedBox(height: 8),
                        Divider(height: 1, color: Colors.grey.shade200),
                        const SizedBox(height: 8),
                      ],
                    ],
                  ],
                ),
        ),
        const SizedBox(height: 14),
        if (!_readOnly) ...[
          const Text('Save as', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
          const SizedBox(height: 8),
          RadioListTile<String>(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: const Text('Draft (no stock posting)'),
            subtitle: const Text('Same as ERP — open later and post to stock'),
            value: 'grn_draft',
            groupValue: _saveMode,
            onChanged: (v) => setState(() => _saveMode = v ?? 'grn_draft'),
          ),
          RadioListTile<String>(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: const Text('Approve & post stock'),
            subtitle: const Text('Updates warehouse stock and item journal'),
            value: 'grn_only',
            groupValue: _saveMode,
            onChanged: (v) => setState(() => _saveMode = v ?? 'grn_only'),
          ),
          RadioListTile<String>(
            dense: true,
            contentPadding: EdgeInsets.zero,
            title: const Text('Post stock + accounts'),
            subtitle: const Text('Stock + purchase invoice / AP (ERP)'),
            value: 'grn_invoice_posting',
            groupValue: _saveMode,
            onChanged: (v) => setState(() => _saveMode = v ?? 'grn_invoice_posting'),
          ),
          const SizedBox(height: 12),
          NumericTextField(
            controller: _confirmInvoiceAmount,
            decoration: _fieldDec('Confirm invoice amount *'),
          ),
          if (widget.mode == GrnWizardMode.editDraft) ...[
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: purchase.isSubmitting ? null : () => _submitPostInventory(purchase),
              icon: const Icon(Icons.inventory_2_outlined),
              label: const Text('Post to stock only'),
            ),
          ],
        ],
        if (canPostAccounts) ...[
          const SizedBox(height: 12),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: _accent),
            onPressed: (purchase.isSubmitting || _postingAccounts)
                ? null
                : () => _submitPostAccounts(purchase),
            icon: _postingAccounts
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.account_balance_outlined),
            label: Text(_postingAccounts ? 'Posting accounts…' : 'Post accounts'),
          ),
        ] else if (_accountPosted) ...[
          const SizedBox(height: 12),
          Text('Accounts already posted.', style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
        ],
      ],
    );
  }
}

class _GrnLineEditDialog extends StatefulWidget {
  const _GrnLineEditDialog({
    required this.itemName,
    required this.itemCode,
    required this.initialUnit,
    required this.initialQty,
    required this.initialRate,
    required this.confirmLabel,
  });

  final String itemName;
  final String itemCode;
  final String initialUnit;
  final double initialQty;
  final double initialRate;
  final String confirmLabel;

  @override
  State<_GrnLineEditDialog> createState() => _GrnLineEditDialogState();
}

class _GrnLineEditDialogState extends State<_GrnLineEditDialog> {
  late final TextEditingController _qty;
  late final TextEditingController _rate;
  late final TextEditingController _unit;

  @override
  void initState() {
    super.initState();
    final q = widget.initialQty;
    _qty = TextEditingController(
      text: q == q.roundToDouble() ? q.round().toString() : q.toStringAsFixed(2),
    );
    _rate = TextEditingController(text: widget.initialRate.toStringAsFixed(2));
    _unit = TextEditingController(text: widget.initialUnit.isNotEmpty ? widget.initialUnit : 'PCS');
  }

  @override
  void dispose() {
    _qty.dispose();
    _rate.dispose();
    _unit.dispose();
    super.dispose();
  }

  void _submit() {
    final qty = double.tryParse(_qty.text.trim().replaceAll(',', '')) ?? 0;
    final rate = double.tryParse(_rate.text.trim().replaceAll(',', '')) ?? 0;
    final unit = _unit.text.trim().isEmpty ? 'PCS' : _unit.text.trim();
    if (qty < 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Qty cannot be negative.')),
      );
      return;
    }
    Navigator.pop(
      context,
      _GrnLineEditResult(qty: qty, rate: rate > 0 ? rate : 0, unit: unit),
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Edit line', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(widget.itemName, style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text('Code ${widget.itemCode}', style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
            const SizedBox(height: 14),
            TextField(
              controller: _qty,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Quantity', isDense: true),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _rate,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Rate', isDense: true),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _unit,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(labelText: 'UOM', isDense: true),
            ),
            const SizedBox(height: 6),
            Text(
              'Set qty to 0 to remove this line.',
              style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0277BD)),
          onPressed: _submit,
          child: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}

class _GrnItemPickerSheet extends StatefulWidget {
  const _GrnItemPickerSheet({required this.service});

  final PurchaseOrderService service;

  @override
  State<_GrnItemPickerSheet> createState() => _GrnItemPickerSheetState();
}

class _GrnItemPickerSheetState extends State<_GrnItemPickerSheet> {
  static const _accent = Color(0xFF0277BD);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = false;
  String? _error;
  List<PurchaseCatalogItem> _rows = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _fetch(''));
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _schedule(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _fetch(q.trim()));
  }

  Future<void> _fetch(String q) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.service.searchCatalog(q: q, limit: 80);
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _rows = [];
        _error = 'Could not load items.';
      });
    }
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
          const Text('Add item', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 12),
          TextField(
            controller: _search,
            autofocus: true,
            decoration: InputDecoration(
              hintText: 'Search name, code, barcode…',
              prefixIcon: const Icon(Icons.search, size: 20),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              isDense: true,
            ),
            onChanged: _schedule,
            onSubmitted: _fetch,
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(child: CircularProgressIndicator(color: _accent)),
            )
          else if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(child: Text(_error!, style: TextStyle(color: Colors.grey.shade600))),
            )
          else if (_rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(child: Text('No items found.', style: TextStyle(color: Colors.grey.shade600))),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.5),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final item = _rows[i];
                  return ListTile(
                    onTap: () => Navigator.pop(context, item),
                    title: Text(
                      item.itemName.isNotEmpty ? item.itemName : item.itemCode,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    subtitle: Text(
                      [
                        if (item.itemCode.isNotEmpty) item.itemCode,
                        if (item.uom.isNotEmpty) item.uom,
                        if (item.barcode.isNotEmpty) item.barcode,
                      ].join(' · '),
                    ),
                    trailing: Text(
                      item.rate.toStringAsFixed(2),
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
