import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/purchase_order_service.dart';
import '../../services/purchase_service.dart';
import '../../services/supplier_master_service.dart';
import '../../widgets/loading_overlay.dart';
import '../masters/supplier_form_screen.dart';
import 'grn_ai_create_item_screen.dart';
import '../../core/theme/app_theme.dart';

/// Separate AI GRN flow (ERP invoice AI extract → review → create item → save draft).
class GrnAiScreen extends StatefulWidget {
  const GrnAiScreen({super.key});

  @override
  State<GrnAiScreen> createState() => _GrnAiScreenState();
}

class _AiLine {
  _AiLine({
    required this.itemCode,
    required this.itemName,
    required this.barcode,
    required this.uom,
    required this.qty,
    required this.rate,
    required this.matched,
    this.invoiceDescription = '',
    this.aiReadBarcode = '',
  });

  String itemCode;
  String itemName;
  String barcode;
  String uom;
  double qty;
  double rate;
  bool matched;
  String invoiceDescription;
  String aiReadBarcode;

  double get amount => qty * rate;
}

class _GrnAiScreenState extends State<GrnAiScreen> {
  static const _accent = Color(0xFF0277BD);

  final _picker = ImagePicker();
  final List<({Uint8List bytes, String filename})> _files = [];

  bool _extracting = false;
  bool _saving = false;
  String? _error;

  Map<String, dynamic> _header = {};
  Map<String, dynamic> _extracted = {};
  Map<String, dynamic> _importReport = {};
  List<_AiLine> _lines = [];
  List<String> _warnings = [];

  final _invoiceNo = TextEditingController();
  final _remarks = TextEditingController();
  String _invoiceDateIso = '';
  String _supplierCode = '';
  String _supplierDisplay = '';
  String _supplierMatch = '';
  String _extractedSupplierName = '';

  String _normCode(dynamic v) {
    final s = '$v'.trim();
    if (s.isEmpty || s == 'null' || s == 'None') return '';
    final n = num.tryParse(s);
    if (n != null && n == n.roundToDouble()) return '${n.round()}';
    return s;
  }

  @override
  void dispose() {
    _invoiceNo.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _pick(ImageSource source) async {
    try {
      if (source == ImageSource.gallery) {
        final imgs = await _picker.pickMultiImage(imageQuality: 85);
        if (imgs.isEmpty) return;
        for (final img in imgs) {
          final bytes = await img.readAsBytes();
          _files.add((bytes: bytes, filename: img.name.isNotEmpty ? img.name : 'invoice.jpg'));
        }
      } else {
        final img = await _picker.pickImage(source: source, imageQuality: 85);
        if (img == null) return;
        final bytes = await img.readAsBytes();
        _files.add((bytes: bytes, filename: img.name.isNotEmpty ? img.name : 'invoice.jpg'));
      }
      if (mounted) setState(() => _error = null);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Could not pick image.');
    }
  }

  Future<void> _extract() async {
    if (_files.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add invoice photo(s) first')),
      );
      return;
    }
    setState(() {
      _extracting = true;
      _error = null;
    });
    try {
      final data = await context.read<PurchaseService>().extractGrnAiInvoice(files: _files);
      if (!mounted) return;
      final header = Map<String, dynamic>.from(data['header'] as Map? ?? const {});
      final rawLines = (data['lines'] as List?) ?? const [];
      final lines = <_AiLine>[];
      for (final row in rawLines) {
        if (row is! Map) continue;
        final m = Map<String, dynamic>.from(row);
        final code = '${m['itemcode'] ?? m['item_code'] ?? ''}'.trim();
        final qty = _num(m['qty'] ?? m['receivedqty'] ?? m['quantity']);
        final rate = _num(m['rate'] ?? m['unit_price']);
        lines.add(
          _AiLine(
            itemCode: code,
            itemName: '${m['itemname'] ?? m['item_name'] ?? m['invoice_description'] ?? ''}'.trim(),
            barcode: '${m['barcode'] ?? m['printed_barcode'] ?? ''}'.trim(),
            uom: '${m['uom'] ?? 'PCS'}'.trim().isEmpty ? 'PCS' : '${m['uom']}'.trim(),
            qty: qty <= 0 ? 1 : qty,
            rate: rate,
            matched: code.isNotEmpty,
            invoiceDescription: '${m['invoice_description'] ?? m['description'] ?? ''}'.trim(),
            aiReadBarcode: '${m['ai_read_barcode'] ?? m['printed_barcode'] ?? m['barcode'] ?? ''}'.trim(),
          ),
        );
      }
      final extracted = Map<String, dynamic>.from(data['extracted'] as Map? ?? const {});
      final importReport = Map<String, dynamic>.from(data['import_report'] as Map? ?? const {});
      final sc = _normCode(header['suppliercode']);
      var sd = '${header['supplier_display'] ?? ''}'.trim();
      if (sd.isEmpty && sc.isNotEmpty) {
        final mst = '${header['supplier_name_master'] ?? importReport['matched_supplier_master_name'] ?? ''}'.trim();
        sd = mst.isNotEmpty ? '$sc - $mst' : sc;
      }
      final invSup = '${importReport['extracted_supplier_name'] ?? extracted['supplier_name'] ?? ''}'.trim();
      setState(() {
        _header = header;
        _extracted = extracted;
        _importReport = importReport;
        _lines = lines;
        _warnings = ((data['warnings'] as List?) ?? const []).map((e) => '$e').toList();
        _supplierCode = sc;
        _supplierDisplay = sd;
        _supplierMatch = '${header['supplier_match'] ?? ''}'.trim().toLowerCase();
        _extractedSupplierName = invSup;
        _invoiceNo.text = '${header['invoiceno'] ?? ''}'.trim();
        _invoiceDateIso = '${header['invoicedate'] ?? ''}'.trim();
        _remarks.text = '${header['remarks'] ?? 'AI GRN import'}'.trim();
        _extracting = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _extracting = false;
        _error = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  double _num(dynamic v) {
    if (v is num) return v.toDouble();
    return double.tryParse('$v'.trim()) ?? 0;
  }

  Future<void> _pickSupplier() async {
    final picked = await showModalBottomSheet<PurchaseSupplierOption>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _AiSupplierPickerSheet(service: context.read<PurchaseOrderService>()),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _supplierCode = _normCode(picked.code);
      _supplierDisplay = picked.name.isNotEmpty ? '$_supplierCode - ${picked.name}' : _supplierCode;
      _supplierMatch = 'manual';
    });
  }

  Future<void> _createSupplierFromInvoice() async {
    final ext = _extracted;
    final invName = _extractedSupplierName.trim().isNotEmpty
        ? _extractedSupplierName.trim()
        : '${ext['supplier_name'] ?? ''}'.trim();
    final tax = '${_importReport['extracted_supplier_tax_id'] ?? ext['supplier_tax_id'] ?? ''}'.trim();
    final invNo = _invoiceNo.text.trim().isNotEmpty
        ? _invoiceNo.text.trim()
        : '${ext['invoice_no'] ?? ''}'.trim();
    final crParts = <String>[];
    if (tax.isNotEmpty) crParts.add('VAT/TRN: $tax');
    if (_invoiceDateIso.isNotEmpty) crParts.add('Invoice date: ${_invoiceDateIso.length >= 10 ? _invoiceDateIso.substring(0, 10) : _invoiceDateIso}');

    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute(
        builder: (_) => SupplierFormScreen(
          prefillName: invName,
          prefillAddress: '${ext['supplier_address'] ?? ''}'.trim(),
          prefillTelephone: '${ext['supplier_telephone'] ?? ''}'.trim(),
          prefillMobile: '${ext['supplier_mobile'] ?? ''}'.trim(),
          prefillEmail: '${ext['supplier_email'] ?? ''}'.trim(),
          prefillContact: '${ext['supplier_contact_person'] ?? ''}'.trim(),
          prefillCr: crParts.join(' · '),
          prefillRef: invNo.isNotEmpty ? 'Inv. $invNo' : '',
        ),
      ),
    );
    if (!mounted || result == null) return;
    if (result is SupplierSaveResult && result.supplierCode > 0) {
      setState(() {
        _supplierCode = '${result.supplierCode}';
        _supplierDisplay = result.supplierName.isNotEmpty
            ? '$_supplierCode - ${result.supplierName}'
            : _supplierCode;
        _supplierMatch = 'created';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Supplier $_supplierCode selected for this GRN')),
      );
    }
  }

  Future<void> _createItemFor(_AiLine line) async {
    if (_supplierCode.isEmpty) {
      final go = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Supplier required'),
          content: Text(
            _extractedSupplierName.isNotEmpty
                ? 'Invoice vendor "$_extractedSupplierName" was not matched. Pick or create a supplier first (same as ERP).'
                : 'Select or create a supplier before creating items (same as ERP).',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Pick / create')),
          ],
        ),
      );
      if (go == true && mounted) {
        await _pickSupplier();
        if (_supplierCode.isEmpty && mounted) await _createSupplierFromInvoice();
      }
      if (_supplierCode.isEmpty || !mounted) return;
    }
    final created = await Navigator.of(context).push<Map<String, dynamic>>(
      MaterialPageRoute(
        builder: (_) => GrnAiCreateItemScreen(
          barcode: line.aiReadBarcode.isNotEmpty ? line.aiReadBarcode : line.barcode,
          description: line.invoiceDescription.isNotEmpty ? line.invoiceDescription : line.itemName,
          uom: line.uom,
          rate: line.rate,
          supplierCode: _supplierCode,
          supplierDisplay: _supplierDisplay,
        ),
      ),
    );
    if (created == null || !mounted) return;
    setState(() {
      line.itemCode = '${created['itemcode'] ?? ''}'.trim();
      line.itemName = '${created['itemname'] ?? line.itemName}'.trim();
      line.barcode = '${created['barcode'] ?? line.barcode}'.trim();
      line.uom = '${created['uom'] ?? line.uom}'.trim();
      line.matched = line.itemCode.isNotEmpty;
    });
  }

  Future<void> _saveDraft() async {
    if (_supplierCode.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Supplier was not matched. Open Normal GRN and pick supplier, or re-extract.')),
      );
      return;
    }
    final usable = _lines.where((l) => l.matched && l.itemCode.isNotEmpty && l.qty > 0).toList();
    if (usable.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No matched lines to save. Create items for yellow lines first.')),
      );
      return;
    }
    final mode = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Save GRN'),
        content: const Text(
          'Draft does not change stock.\n'
          'Post stock updates Item Master qty (qty × UOM factor), same as ERP.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, 'grn_draft'),
            child: const Text('Save draft'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, 'grn_only'),
            child: const Text('Save & post stock'),
          ),
        ],
      ),
    );
    if (mode == null || !mounted) return;

    setState(() => _saving = true);
    try {
      final svc = context.read<PurchaseService>();
      final receiptNo = await svc.nextGrnNo();
      final today = DateTime.now();
      final receiptDate =
          '${today.year.toString().padLeft(4, '0')}-${today.month.toString().padLeft(2, '0')}-${today.day.toString().padLeft(2, '0')}';
      final invDate = _invoiceDateIso.length >= 10 ? _invoiceDateIso.substring(0, 10) : receiptDate;
      final amount = usable.fold<double>(0, (s, l) => s + l.amount);
      await svc.saveGrn(
        receiptNo: receiptNo,
        receiptDate: receiptDate,
        supplierCode: _supplierCode,
        invoiceNo: _invoiceNo.text.trim(),
        invoiceDate: invDate,
        invoiceAmount: amount,
        remarks: _remarks.text.trim().isEmpty ? 'AI GRN import' : _remarks.text.trim(),
        saveMode: mode,
        lines: [
          for (final l in usable)
            {
              'itemcode': l.itemCode,
              'itemname': l.itemName,
              'uom': l.uom,
              'qty': l.qty,
              'quantity': l.qty,
              'rate': l.rate,
              'barcode': l.barcode,
              'amount': l.amount,
            },
        ],
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            mode == 'grn_only'
                ? 'GRN $receiptNo saved — stock posted'
                : 'Draft GRN $receiptNo saved',
          ),
        ),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasResult = _lines.isNotEmpty || _header.isNotEmpty;
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        title: const Text('AI GRN', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      ),
      body: LoadingOverlay(
        loading: _extracting || _saving,
        message: _extracting ? 'Extracting invoice…' : 'Saving…',
        child: ListView(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 100),
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xFFE4E7F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Invoice photos', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                  const SizedBox(height: 4),
                  Text(
                    'Same as ERP AI GRN — photograph or pick invoice pages, then Extract & fill.',
                    style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _extracting ? null : () => _pick(ImageSource.camera),
                          icon: const Icon(Icons.photo_camera_outlined, size: 18),
                          label: const Text('Camera'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _extracting ? null : () => _pick(ImageSource.gallery),
                          icon: const Icon(Icons.photo_library_outlined, size: 18),
                          label: const Text('Gallery'),
                        ),
                      ),
                    ],
                  ),
                  if (_files.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    Text('${_files.length} file(s) ready', style: const TextStyle(fontWeight: FontWeight.w600)),
                    TextButton(
                      onPressed: _extracting
                          ? null
                          : () => setState(() {
                                _files.clear();
                                _lines = [];
                                _header = {};
                                _extracted = {};
                                _importReport = {};
                                _supplierCode = '';
                                _supplierDisplay = '';
                                _supplierMatch = '';
                                _extractedSupplierName = '';
                              }),
                      child: const Text('Clear files'),
                    ),
                  ],
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: _accent, minimumSize: const Size(double.infinity, 46)),
                    onPressed: _extracting ? null : _extract,
                    icon: const Icon(Icons.auto_awesome_rounded, size: 18),
                    label: const Text('Extract & fill', style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Color(0xFFC62828), fontWeight: FontWeight.w600)),
            ],
            if (hasResult) ...[
              const SizedBox(height: 16),
              _headerCard(),
              if (_warnings.isNotEmpty) ...[
                const SizedBox(height: 10),
                ..._warnings.take(6).map(
                      (w) => Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Text('• $w', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                      ),
                    ),
              ],
              const SizedBox(height: 14),
              Row(
                children: [
                  const Text('Lines', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                  const Spacer(),
                  Text(
                    '${_lines.where((l) => l.matched).length}/${_lines.length} matched',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              ..._lines.asMap().entries.map((e) => _lineCard(e.key, e.value)),
              const SizedBox(height: 16),
              FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF2E7D32),
                  minimumSize: const Size(double.infinity, 48),
                ),
                onPressed: _saving ? null : _saveDraft,
                child: const Text('Save draft GRN', style: TextStyle(fontWeight: FontWeight.w700)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _headerCard() {
    final unmatched = _supplierCode.isEmpty;
    final fuzzy = _supplierMatch == 'fuzzy';
    String matchHint = '';
    if (unmatched && _extractedSupplierName.isNotEmpty) {
      matchHint = 'Invoice vendor: $_extractedSupplierName — not in master. Create or pick.';
    } else if (fuzzy && _extractedSupplierName.isNotEmpty) {
      final pct = _header['supplier_match_score'];
      final score = pct is num ? ' (${(pct * 100).round()}%)' : '';
      matchHint = 'Fuzzy match$score · invoice: $_extractedSupplierName';
    } else if (_supplierMatch == 'matched' || _supplierMatch == 'created' || _supplierMatch == 'manual') {
      matchHint = _supplierMatch == 'matched' ? 'Auto-matched from invoice' : 'Selected for this GRN';
    }

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Supplier', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
          const SizedBox(height: 8),
          InkWell(
            onTap: _pickSupplier,
            borderRadius: BorderRadius.circular(10),
            child: InputDecorator(
              decoration: InputDecoration(
                isDense: true,
                filled: true,
                fillColor: unmatched ? const Color(0xFFFFEBEE) : const Color(0xFFF7F8FC),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                suffixIcon: const Icon(Icons.search, size: 20),
              ),
              child: Text(
                unmatched
                    ? (_extractedSupplierName.isNotEmpty
                        ? 'Not matched — tap to pick ($_extractedSupplierName)'
                        : 'Tap to select supplier')
                    : (_supplierDisplay.isNotEmpty ? _supplierDisplay : _supplierCode),
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: unmatched ? const Color(0xFFC62828) : const Color(0xFF262C50),
                ),
              ),
            ),
          ),
          if (matchHint.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(matchHint, style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ],
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              OutlinedButton.icon(
                onPressed: _pickSupplier,
                icon: const Icon(Icons.list_alt_rounded, size: 16),
                label: const Text('Pick supplier'),
              ),
              if (unmatched || fuzzy || _extractedSupplierName.isNotEmpty)
                FilledButton.icon(
                  style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0F766E)),
                  onPressed: _createSupplierFromInvoice,
                  icon: const Icon(Icons.person_add_alt_1_rounded, size: 16),
                  label: const Text('Create supplier'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _invoiceNo,
            decoration: const InputDecoration(
              labelText: 'Invoice no',
              isDense: true,
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            'Invoice date: ${_invoiceDateIso.isEmpty ? '—' : _invoiceDateIso}',
            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _remarks,
            decoration: const InputDecoration(
              labelText: 'Remarks',
              isDense: true,
              border: OutlineInputBorder(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _lineCard(int index, _AiLine line) {
    final unmatched = !line.matched;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: unmatched ? const Color(0xFFFFF8E1) : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: unmatched ? const Color(0xFFFFB300) : const Color(0xFFE4E7F0),
        ),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(12, 6, 8, 6),
        title: Text(
          line.itemName.isEmpty ? '(no description)' : line.itemName,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
        ),
        subtitle: Text(
          unmatched
              ? 'Unmatched · tap Create item'
              : 'Code ${line.itemCode} · ${line.qty} ${line.uom} × ${line.rate.toStringAsFixed(2)}',
          style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
        ),
        trailing: unmatched
            ? TextButton(
                onPressed: () => _createItemFor(line),
                child: const Text('Create'),
              )
            : Text(
                line.amount.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, color: _accent),
              ),
        onTap: unmatched ? () => _createItemFor(line) : null,
      ),
    );
  }
}

class _AiSupplierPickerSheet extends StatefulWidget {
  const _AiSupplierPickerSheet({required this.service});
  final PurchaseOrderService service;

  @override
  State<_AiSupplierPickerSheet> createState() => _AiSupplierPickerSheetState();
}

class _AiSupplierPickerSheetState extends State<_AiSupplierPickerSheet> {
  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  List<PurchaseSupplierOption> _rows = [];

  @override
  void initState() {
    super.initState();
    _fetch('');
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
    setState(() => _loading = true);
    try {
      final rows = await widget.service.searchSuppliers(q: q);
      if (mounted) setState(() => _rows = rows);
    } catch (_) {
      if (mounted) setState(() => _rows = []);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createSupplier() async {
    final prefill = _search.text.trim();
    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute(
        builder: (_) => SupplierFormScreen(prefillName: prefill),
      ),
    );
    if (!mounted || result == null) return;
    if (result is SupplierSaveResult && result.supplierCode > 0) {
      Navigator.pop(
        context,
        PurchaseSupplierOption(
          code: '${result.supplierCode}',
          name: result.supplierName.isNotEmpty ? result.supplierName : '${result.supplierCode}',
        ),
      );
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
          const SizedBox(height: 8),
          Row(
            children: [
              const Expanded(
                child: Text('Select supplier', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              TextButton.icon(
                onPressed: _createSupplier,
                icon: const Icon(Icons.person_add_alt_1_rounded, size: 18),
                label: const Text('New'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _search,
            autofocus: true,
            decoration: InputDecoration(
              hintText: 'Search name or code',
              prefixIcon: const Icon(Icons.search, size: 20),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              isDense: true,
            ),
            onChanged: _schedule,
            onSubmitted: _fetch,
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF0F766E)),
            onPressed: _createSupplier,
            icon: const Icon(Icons.add_business_rounded, size: 18),
            label: const Text('Create new supplier'),
          ),
          const SizedBox(height: 8),
          if (_loading)
            const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
          else if (_rows.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 20),
              child: Center(
                child: Text(
                  'No suppliers found. Create a new one above.',
                  style: TextStyle(color: Colors.grey.shade600),
                  textAlign: TextAlign.center,
                ),
              ),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.4),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final s = _rows[i];
                  return ListTile(
                    onTap: () => Navigator.pop(context, s),
                    title: Text(
                      s.name.isNotEmpty ? s.name : s.code,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    subtitle: Text('Code ${s.code}'),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
