import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../models/barcode_print_list.dart';
import '../../models/inventory_item.dart';
import '../../models/storage_location.dart';
import '../../services/barcode_print_list_service.dart';
import '../../services/inventory_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/hardware_barcode_capture.dart';
import '../barcode_scanner_screen.dart';
import '../../core/theme/app_theme.dart';

/// Scan items/shelves into a print-list document, then save for ERP Barcode Management.
class BarcodePrintListFormScreen extends StatefulWidget {
  const BarcodePrintListFormScreen({
    super.key,
    this.listType = 'PRODUCT',
    this.printNo,
  });

  final String listType;
  final int? printNo;

  @override
  State<BarcodePrintListFormScreen> createState() => _BarcodePrintListFormScreenState();
}

class _BarcodePrintListFormScreenState extends State<BarcodePrintListFormScreen> {
  static const _navy = Color(0xFF262C50);

  final _remarksCtrl = TextEditingController();
  final _hwCtrl = TextEditingController();
  final _hwFocus = FocusNode();

  final List<BarcodePrintListLine> _lines = [];
  int? _printNo;
  bool _loading = false;
  bool _saving = false;
  bool _lookingUp = false;
  String? _error;
  Object? _errorCause;
  String? _lastScanMsg;

  bool get _isShelf => widget.listType.toUpperCase() == 'SHELF';

  Color get _accent =>
      _isShelf ? const Color(0xFF00897B) : const Color(0xFF0277BD);

  String get _title {
    if (_printNo != null && _printNo! > 0) {
      return _isShelf ? 'Shelf list #$_printNo' : 'Product list #$_printNo';
    }
    return _isShelf ? 'New shelf print list' : 'New product print list';
  }

  int get _labelCount => _lines.fold<int>(0, (s, l) => s + l.printQty);

  @override
  void initState() {
    super.initState();
    _printNo = widget.printNo;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_printNo != null && _printNo! > 0) {
        _loadExisting();
      } else {
        _hwFocus.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _remarksCtrl.dispose();
    _hwCtrl.dispose();
    _hwFocus.dispose();
    super.dispose();
  }

  Future<void> _loadExisting() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final doc = await context.read<BarcodePrintListService>().getDocument(_printNo!);
      if (!mounted) return;
      setState(() {
        _lines
          ..clear()
          ..addAll(doc.lines);
        _remarksCtrl.text = doc.remarks;
        _printNo = doc.printNo;
        _loading = false;
      });
      _hwFocus.requestFocus();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _openCamera() async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => BarcodeScannerScreen(
          title: _isShelf ? 'Scan shelf barcode' : 'Scan product barcode',
        ),
      ),
    );
    if (!mounted || code == null || code.trim().isEmpty) return;
    await _addByScan(code.trim());
  }

  Future<void> _addByScan(String code) async {
    if (_lookingUp || _saving) return;
    final q = code.trim();
    if (q.isEmpty) return;

    setState(() {
      _lookingUp = true;
      _error = null;
      _lastScanMsg = null;
    });

    try {
      final inv = context.read<InventoryService>();
      if (_isShelf) {
        final storage = await inv.lookupStorage(query: q);
        if (!mounted) return;
        _mergeShelf(storage);
      } else {
        final item = await inv.lookupItem(query: q);
        if (!mounted) return;
        _mergeProduct(item);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
      });
    } finally {
      if (mounted) {
        setState(() => _lookingUp = false);
        _hwFocus.requestFocus();
      }
    }
  }

  void _mergeProduct(InventoryItem item) {
    final barcode = item.barcode.trim().isNotEmpty ? item.barcode.trim() : item.itemCode.trim();
    if (barcode.isEmpty) {
      setState(() => _error = 'Item has no barcode to print.');
      return;
    }
    final existing = _lines.indexWhere(
      (l) => l.barcode.trim().toUpperCase() == barcode.toUpperCase() &&
          l.itemCode.trim() == item.itemCode.trim(),
    );
    setState(() {
      if (existing >= 0) {
        _lines[existing].printQty += 1;
        _lastScanMsg = '+1 → ${_lines[existing].displayName} (×${_lines[existing].printQty})';
      } else {
        _lines.insert(
          0,
          BarcodePrintListLine(
            itemCode: item.itemCode,
            itemName: item.itemName,
            barcode: barcode,
            uom: item.unit,
            retailPrice: item.retailPrice,
            printQty: 1,
          ),
        );
        _lastScanMsg = 'Added ${item.itemName.isEmpty ? barcode : item.itemName}';
      }
    });
  }

  void _mergeShelf(StorageLocation storage) {
    final barcode = storage.printValue;
    if (barcode.isEmpty) {
      setState(() => _error = 'Shelf/bin has no barcode to print.');
      return;
    }
    final existing = _lines.indexWhere(
      (l) => (l.storageId != null && l.storageId == storage.storageId) ||
          l.barcode.trim().toUpperCase() == barcode.toUpperCase(),
    );
    setState(() {
      if (existing >= 0) {
        _lines[existing].printQty += 1;
        _lastScanMsg = '+1 → ${_lines[existing].displayName} (×${_lines[existing].printQty})';
      } else {
        _lines.insert(
          0,
          BarcodePrintListLine(
            barcode: barcode,
            uom: storage.typeLabel,
            printQty: 1,
            storageId: storage.storageId > 0 ? storage.storageId : null,
            storageType: storage.storageType,
            storageCode: storage.code,
            storageName: storage.name,
            pathText: storage.path,
          ),
        );
        _lastScanMsg = 'Added ${storage.name.isEmpty ? barcode : storage.name}';
      }
    });
  }

  Future<void> _save() async {
    if (_saving) return;
    if (_lines.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Scan at least one barcode before saving.')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final doc = await context.read<BarcodePrintListService>().saveDocument(
            printNo: _printNo,
            listType: widget.listType,
            remarks: _remarksCtrl.text.trim(),
            lines: _lines.reversed.toList(), // keep scan order oldest→newest
          );
      if (!mounted) return;
      setState(() {
        _printNo = doc.printNo;
        _saving = false;
      });
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Print list saved'),
          content: Text(
            'Document #${doc.printNo}\n\n'
            'Open ERP → Barcode Management → Product barcode → '
            'Open print list → enter ${doc.printNo} → Open.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('OK'),
            ),
          ],
        ),
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _saving = false;
      });
    }
  }

  void _bumpQty(int index, int delta) {
    setState(() {
      final next = _lines[index].printQty + delta;
      if (next <= 0) {
        _lines.removeAt(index);
      } else {
        _lines[index].printQty = next.clamp(1, 999);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(_title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Camera scan',
            onPressed: _lookingUp || _saving ? null : _openCamera,
            icon: const Icon(Icons.qr_code_scanner_rounded),
          ),
        ],
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: _accent,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            onPressed: _loading || _saving || _lines.isEmpty ? null : _save,
            icon: _saving
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.save_rounded),
            label: Text(
              _saving
                  ? 'Saving…'
                  : (_printNo != null && _printNo! > 0
                      ? 'Update list #$_printNo'
                      : 'Save print list'),
            ),
          ),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                HardwareBarcodeCapture(
                  focusNode: _hwFocus,
                  controller: _hwCtrl,
                  enabled: !_lookingUp && !_saving,
                  onScan: _addByScan,
                ),
                ListView(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
                  children: [
                    if (_printNo != null && _printNo! > 0)
                      Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: _accent.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: _accent.withValues(alpha: 0.25)),
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.tag_rounded, color: _accent),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'ERP open number: $_printNo',
                                style: TextStyle(
                                  color: _accent,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 15,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    TextField(
                      controller: _remarksCtrl,
                      decoration: InputDecoration(
                        labelText: 'Remarks (optional)',
                        filled: true,
                        fillColor: Colors.white,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        isDense: true,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            _isShelf
                                ? 'Scan shelf / bin barcodes to add'
                                : 'Scan product barcodes to add',
                            style: const TextStyle(color: Color(0xFF6B7280), fontSize: 13),
                          ),
                        ),
                        if (_lookingUp)
                          const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        else
                          TextButton.icon(
                            onPressed: _openCamera,
                            icon: const Icon(Icons.qr_code_scanner_rounded, size: 18),
                            label: const Text('Scan'),
                          ),
                      ],
                    ),
                    if (_lastScanMsg != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        _lastScanMsg!,
                        style: TextStyle(color: _accent, fontWeight: FontWeight.w600, fontSize: 13),
                      ),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: 8),
                      ApiErrorBanner(
                        message: _error!,
                        error: _errorCause,
                        padding: EdgeInsets.zero,
                      ),
                    ],
                    const SizedBox(height: 8),
                    Text(
                      '${_lines.length} lines · $_labelCount labels',
                      style: const TextStyle(fontWeight: FontWeight.w700, color: _navy),
                    ),
                    const SizedBox(height: 8),
                    if (_lines.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFFE4E7F0)),
                        ),
                        child: const Text(
                          'No lines yet. Use a Bluetooth scanner or the camera button.',
                          style: TextStyle(color: Color(0xFF6B7280)),
                        ),
                      )
                    else
                      ...List.generate(_lines.length, (i) {
                        final line = _lines[i];
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Container(
                            padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: const Color(0xFFE4E7F0)),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        line.displayName,
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w700,
                                          color: _navy,
                                          fontSize: 14,
                                        ),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        [
                                          if (line.itemCode.isNotEmpty) line.itemCode,
                                          line.barcode,
                                          if (line.uom.isNotEmpty) line.uom,
                                        ].join(' · '),
                                        style: const TextStyle(
                                          color: Color(0xFF6B7280),
                                          fontSize: 12,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                IconButton(
                                  onPressed: () => _bumpQty(i, -1),
                                  icon: const Icon(Icons.remove_circle_outline),
                                  visualDensity: VisualDensity.compact,
                                ),
                                SizedBox(
                                  width: 36,
                                  child: Text(
                                    '${line.printQty}',
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(fontWeight: FontWeight.w800),
                                  ),
                                ),
                                IconButton(
                                  onPressed: () => _bumpQty(i, 1),
                                  icon: const Icon(Icons.add_circle_outline),
                                  visualDensity: VisualDensity.compact,
                                ),
                                IconButton(
                                  onPressed: () => setState(() => _lines.removeAt(i)),
                                  icon: const Icon(Icons.delete_outline_rounded, color: Color(0xFFC62828)),
                                  visualDensity: VisualDensity.compact,
                                ),
                              ],
                            ),
                          ),
                        );
                      }),
                    // Keep focus field usable after keyboard dismiss
                    const SizedBox(height: 8),
                    TextField(
                      readOnly: true,
                      onTap: () => _hwFocus.requestFocus(),
                      decoration: InputDecoration(
                        hintText: 'Ready for scanner…',
                        filled: true,
                        fillColor: Colors.white,
                        prefixIcon: Icon(Icons.qr_code_scanner_rounded, color: _accent),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        isDense: true,
                      ),
                      inputFormatters: [FilteringTextInputFormatter.deny(RegExp(r'.'))],
                    ),
                  ],
                ),
              ],
            ),
    );
  }
}
