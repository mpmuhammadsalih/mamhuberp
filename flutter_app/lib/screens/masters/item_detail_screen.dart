import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/item_master_service.dart';
import '../inventory/item_ledger_screen.dart';
import 'item_form_screen.dart';
import '../../core/theme/app_theme.dart';

class ItemDetailScreen extends StatefulWidget {
  const ItemDetailScreen({super.key, required this.itemCode});

  final int itemCode;

  @override
  State<ItemDetailScreen> createState() => _ItemDetailScreenState();
}

class _ItemDetailScreenState extends State<ItemDetailScreen> {
  static const _accent = Color(0xFF5E35B1);

  bool _loading = true;
  bool _changed = false;
  String? _error;
  ItemDetail? _item;
  Uint8List? _imageBytes;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final svc = context.read<ItemMasterService>();
      final item = await svc.getItem(widget.itemCode);
      Uint8List? imageBytes;
      if (item.hasImage) {
        imageBytes = await svc.fetchItemImageBytes(item.itemCode);
      }
      if (!mounted) return;
      setState(() {
        _item = item;
        _imageBytes = imageBytes;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  Future<void> _edit() async {
    final saved = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        builder: (_) => ItemFormScreen(itemCode: widget.itemCode),
      ),
    );
    if (!mounted || saved == null) return;
    if (saved == 'deleted') {
      Navigator.of(context).pop(true);
      return;
    }
    if (saved == true) {
      _changed = true;
      await _load();
    }
  }

  String _money(double v) => v.toStringAsFixed(2);

  @override
  Widget build(BuildContext context) {
    final item = _item;
    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).pop(_changed ? true : null),
        ),
        title: const Text('Item Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          TextButton(
            onPressed: _loading || item == null ? null : _edit,
            child: Text(
              'Edit',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: _loading || item == null ? Colors.grey : _accent,
              ),
            ),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 12),
                        FilledButton(onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : item == null
                  ? const Center(child: Text('Item not found.'))
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                      children: [
                        _card(
                          children: [
                            if (_imageBytes != null) ...[
                              ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: AspectRatio(
                                  aspectRatio: 16 / 9,
                                  child: Image.memory(_imageBytes!, fit: BoxFit.cover),
                                ),
                              ),
                              const SizedBox(height: 12),
                            ],
                            Text(
                              item.itemName.isNotEmpty ? item.itemName : 'Item ${item.itemCode}',
                              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              '#${item.itemCode}${item.barcode.isNotEmpty ? ' · ${item.barcode}' : ''}',
                              style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _card(
                          children: [
                            _row('Base UOM', item.baseUom),
                            _row('Main Category', item.mainCategoryName.isNotEmpty
                                ? item.mainCategoryName
                                : (item.mainCategory > 0 ? '${item.mainCategory}' : '—')),
                            _row('Department', item.departmentName.isNotEmpty
                                ? item.departmentName
                                : (item.departmentCode > 0 ? '${item.departmentCode}' : '—')),
                            _row('Category', item.categoryName.isNotEmpty
                                ? item.categoryName
                                : (item.categoryCode > 0 ? '${item.categoryCode}' : '—')),
                            _row('Brand', item.brandName.isNotEmpty
                                ? item.brandName
                                : (item.brandCode > 0 ? '${item.brandCode}' : '—')),
                            _row(
                              'Supplier',
                              item.supCode <= 0
                                  ? '—'
                                  : (item.supplierName.isNotEmpty
                                      ? '${item.supCode} — ${item.supplierName}'
                                      : '${item.supCode}'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        _card(
                          children: [
                            _row('Cost', _money(item.costPrice)),
                            _row('Average cost', _money(item.averageCost)),
                            _row('Retail', _money(item.retailPrice)),
                            _row('VAT %', item.vatPercent.toStringAsFixed(2)),
                            _row('Stock', item.currentStock.toStringAsFixed(3)),
                          ],
                        ),
                        if (item.alternateUoms.isNotEmpty) ...[
                          const SizedBox(height: 12),
                          _card(
                            children: [
                              const Text(
                                'Alternate UOMs',
                                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14),
                              ),
                              const SizedBox(height: 8),
                              for (final a in item.alternateUoms) ...[
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 10),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        '${a.uomCode}  × ${a.conversionFactor}',
                                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        [
                                          'Cost ${_money(a.costPrice > 0 ? a.costPrice : a.conversionFactor * item.costPrice)}',
                                          'Retail ${_money(a.retailPrice)}',
                                          if (a.barcode.isNotEmpty) a.barcode,
                                        ].join('  ·  '),
                                        style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ],
                        const SizedBox(height: 14),
                        FilledButton.icon(
                          onPressed: () {
                            final it = item;
                            Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => ItemLedgerScreen(
                                  initialItemCode: it.itemCode,
                                  initialItemName: it.itemName,
                                ),
                              ),
                            );
                          },
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF00838F),
                            minimumSize: const Size.fromHeight(48),
                          ),
                          icon: const Icon(Icons.menu_book_rounded),
                          label: const Text('Item ledger', style: TextStyle(fontWeight: FontWeight.w700)),
                        ),
                        const SizedBox(height: 10),
                        FilledButton.icon(
                          onPressed: _edit,
                          style: FilledButton.styleFrom(
                            backgroundColor: _accent,
                            minimumSize: const Size.fromHeight(48),
                          ),
                          icon: const Icon(Icons.edit_outlined),
                          label: const Text('Edit Item', style: TextStyle(fontWeight: FontWeight.w700)),
                        ),
                      ],
                    ),
    );
  }

  Widget _card({required List<Widget> children}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(label, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600)),
          ),
          Expanded(
            child: Text(
              value.isEmpty ? '—' : value,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5),
            ),
          ),
        ],
      ),
    );
  }
}
