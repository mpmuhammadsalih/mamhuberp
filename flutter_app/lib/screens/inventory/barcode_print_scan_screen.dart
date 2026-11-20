import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../models/inventory_item.dart';
import '../../models/storage_location.dart';
import '../../services/inventory_service.dart';
import '../../services/label_print_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/hardware_barcode_capture.dart';
import '../barcode_scanner_screen.dart';
import '../printer_settings_screen.dart';
import '../../core/theme/app_theme.dart';

enum BarcodePrintMode { product, shelf }

class BarcodePrintScanScreen extends StatefulWidget {
  const BarcodePrintScanScreen({super.key, required this.mode});

  final BarcodePrintMode mode;

  @override
  State<BarcodePrintScanScreen> createState() => _BarcodePrintScanScreenState();
}

class _BarcodePrintScanScreenState extends State<BarcodePrintScanScreen> {
  static const _navy = Color(0xFF262C50);

  final _searchCtrl = TextEditingController();
  final _hwCtrl = TextEditingController();
  final _hwFocus = FocusNode();
  final _copiesCtrl = TextEditingController(text: '1');

  bool _lookingUp = false;
  bool _printing = false;
  String? _error;
  Object? _errorCause;
  InventoryItem? _product;
  StorageLocation? _shelf;

  bool get _isProduct => widget.mode == BarcodePrintMode.product;

  String get _title => _isProduct ? 'Product barcode' : 'Shelf barcode';

  String get _hint =>
      _isProduct ? 'Item code or barcode…' : 'Shelf / bin barcode or code…';

  Color get _accent =>
      _isProduct ? const Color(0xFF0277BD) : const Color(0xFF00897B);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _hwFocus.requestFocus();
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _hwCtrl.dispose();
    _hwFocus.dispose();
    _copiesCtrl.dispose();
    super.dispose();
  }

  Future<void> _openCamera() async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(
        builder: (_) => BarcodeScannerScreen(
          title: _isProduct ? 'Scan product barcode' : 'Scan shelf barcode',
        ),
      ),
    );
    if (!mounted || code == null || code.trim().isEmpty) return;
    _searchCtrl.text = code.trim();
    await _lookup(code.trim());
  }

  Future<void> _lookup([String? raw]) async {
    final q = (raw ?? _searchCtrl.text).trim();
    if (q.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_isProduct ? 'Enter or scan a product barcode' : 'Enter or scan a shelf barcode')),
      );
      return;
    }

    setState(() {
      _lookingUp = true;
      _error = null;
      _errorCause = null;
      _product = null;
      _shelf = null;
    });

    try {
      final svc = context.read<InventoryService>();
      if (_isProduct) {
        final item = await svc.lookupItem(query: q);
        if (!mounted) return;
        setState(() {
          _product = item;
          _lookingUp = false;
          _searchCtrl.text = q;
        });
      } else {
        final storage = await svc.lookupStorage(query: q);
        if (!mounted) return;
        setState(() {
          _shelf = storage;
          _lookingUp = false;
          _searchCtrl.text = q;
        });
      }
      _hwFocus.requestFocus();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _lookingUp = false;
      });
      _hwFocus.requestFocus();
    }
  }

  int _copies() {
    final n = int.tryParse(_copiesCtrl.text.trim()) ?? 1;
    return n.clamp(1, 20);
  }

  Future<void> _print() async {
    if (_printing) return;
    if (_isProduct && _product == null) return;
    if (!_isProduct && _shelf == null) return;

    setState(() => _printing = true);
    try {
      final printer = LabelPrintService();
      if (_isProduct) {
        await printer.printProductLabel(_product!, copies: _copies());
      } else {
        await printer.printShelfLabel(_shelf!, copies: _copies());
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Printed ${_copies()} label${_copies() == 1 ? '' : 's'}')),
      );
      _hwFocus.requestFocus();
    } catch (e) {
      if (!mounted) return;
      final msg = '$e';
      final needsPrinter = msg.toLowerCase().contains('no printer') ||
          msg.toLowerCase().contains('choose printer');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(msg.replaceFirst('Exception: ', '')),
          action: needsPrinter
              ? SnackBarAction(
                  label: 'Printer',
                  onPressed: () {
                    Navigator.of(context).push<void>(
                      MaterialPageRoute<void>(
                        builder: (_) => const PrinterSettingsScreen(),
                      ),
                    );
                  },
                )
              : null,
        ),
      );
    } finally {
      if (mounted) setState(() => _printing = false);
    }
  }

  void _clearResult() {
    setState(() {
      _product = null;
      _shelf = null;
      _error = null;
      _errorCause = null;
      _searchCtrl.clear();
    });
    _hwFocus.requestFocus();
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
            tooltip: 'Printer settings',
            onPressed: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(
                  builder: (_) => const PrinterSettingsScreen(),
                ),
              );
            },
            icon: const Icon(Icons.print_outlined),
          ),
        ],
      ),
      body: Stack(
        children: [
          HardwareBarcodeCapture(
            focusNode: _hwFocus,
            controller: _hwCtrl,
            enabled: !_lookingUp && !_printing,
            onScan: (code) {
              _searchCtrl.text = code;
              _lookup(code);
            },
          ),
          ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
            children: [
              Text(
                _isProduct
                    ? 'Scan a product barcode to print an item label.'
                    : 'Scan a shelf, bin, or rack barcode to print a location label.',
                style: const TextStyle(color: Color(0xFF6B7280), fontSize: 13.5, height: 1.35),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _searchCtrl,
                      textInputAction: TextInputAction.search,
                      onSubmitted: (_) => _lookup(),
                      decoration: InputDecoration(
                        hintText: _hint,
                        filled: true,
                        fillColor: Colors.white,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    style: IconButton.styleFrom(
                      backgroundColor: _accent,
                      foregroundColor: Colors.white,
                      fixedSize: const Size(46, 46),
                    ),
                    onPressed: _lookingUp ? null : _openCamera,
                    icon: const Icon(Icons.qr_code_scanner_rounded),
                    tooltip: 'Camera scan',
                  ),
                  const SizedBox(width: 4),
                  IconButton.filled(
                    style: IconButton.styleFrom(
                      backgroundColor: _navy,
                      foregroundColor: Colors.white,
                      fixedSize: const Size(46, 46),
                    ),
                    onPressed: _lookingUp ? null : () => _lookup(),
                    icon: _lookingUp
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.search_rounded),
                    tooltip: 'Look up',
                  ),
                ],
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                ApiErrorBanner(
                  message: _error!,
                  error: _errorCause,
                  padding: EdgeInsets.zero,
                ),
              ],
              if (_product != null) ...[
                const SizedBox(height: 16),
                _ProductCard(item: _product!, accent: _accent),
              ],
              if (_shelf != null) ...[
                const SizedBox(height: 16),
                _ShelfCard(storage: _shelf!, accent: _accent),
              ],
              if (_product != null || _shelf != null) ...[
                const SizedBox(height: 16),
                Row(
                  children: [
                    const Text('Copies', style: TextStyle(fontWeight: FontWeight.w600, color: _navy)),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: 72,
                      child: TextField(
                        controller: _copiesCtrl,
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                          LengthLimitingTextInputFormatter(2),
                        ],
                        decoration: InputDecoration(
                          filled: true,
                          fillColor: Colors.white,
                          isDense: true,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _printing ? null : _clearResult,
                        child: const Text('Scan again'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 2,
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: _accent,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        ),
                        onPressed: _printing ? null : _print,
                        icon: _printing
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            : const Icon(Icons.print_rounded),
                        label: Text(_printing ? 'Printing…' : 'Print label'),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({required this.item, required this.accent});

  final InventoryItem item;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    final price = item.retailPrice;
    final priceText = price > 0
        ? (price == price.roundToDouble() ? price.round().toString() : price.toStringAsFixed(2))
        : '—';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.inventory_2_outlined, color: accent),
              const SizedBox(width: 8),
              const Text('Product found', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            ],
          ),
          const SizedBox(height: 12),
          Text(item.itemName, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: Color(0xFF262C50))),
          const SizedBox(height: 8),
          _kv('Code', item.itemCode),
          _kv('Barcode', item.barcode.isEmpty ? item.itemCode : item.barcode),
          _kv('UOM', item.unit),
          _kv('Price', priceText),
          _kv('On hand', item.qtyOnHand == item.qtyOnHand.roundToDouble()
              ? item.qtyOnHand.round().toString()
              : item.qtyOnHand.toStringAsFixed(2)),
        ],
      ),
    );
  }
}

class _ShelfCard extends StatelessWidget {
  const _ShelfCard({required this.storage, required this.accent});

  final StorageLocation storage;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.view_module_outlined, color: accent),
              const SizedBox(width: 8),
              const Text('Shelf / bin found', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            storage.name.isNotEmpty ? storage.name : storage.code,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: Color(0xFF262C50)),
          ),
          const SizedBox(height: 8),
          _kv('Type', storage.typeLabel),
          _kv('Code', storage.code),
          _kv('Barcode', storage.printValue),
          if (storage.path.isNotEmpty) _kv('Path', storage.path),
          if (storage.status.isNotEmpty) _kv('Status', storage.status),
        ],
      ),
    );
  }
}

Widget _kv(String k, String v) {
  return Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 78,
          child: Text(k, style: const TextStyle(color: Color(0xFF6B7280), fontSize: 13)),
        ),
        Expanded(
          child: Text(v, style: const TextStyle(color: Color(0xFF262C50), fontSize: 13, fontWeight: FontWeight.w600)),
        ),
      ],
    ),
  );
}
