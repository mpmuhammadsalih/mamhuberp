import 'package:flutter/material.dart';
import '../../core/ui/app_snackbar.dart';

import '../../services/sales_service.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

/// User choices from the item detail page before adding to invoice cart.
class SalesInvoiceItemAddRequest {
  const SalesInvoiceItemAddRequest({
    required this.uom,
    required this.qty,
    required this.rate,
    this.discount = 0,
  });

  final String uom;
  final double qty;
  final double rate;
  /// Discount **per unit** (total = this × qty). Not percent.
  final double discount;
}

class SalesInvoiceItemDetailScreen extends StatefulWidget {
  const SalesInvoiceItemDetailScreen({
    super.key,
    required this.catalogItem,
    required this.service,
    this.imageUrl,
    this.customerCode = '',
    this.customerName = '',
    this.allowAddWithoutStock = false,
  });

  final SalesCatalogItem catalogItem;
  final SalesService service;
  final String? imageUrl;
  final String customerCode;
  final String customerName;
  /// ERP minus billing / sales return — allow Add when stock is 0.
  final bool allowAddWithoutStock;

  @override
  State<SalesInvoiceItemDetailScreen> createState() => _SalesInvoiceItemDetailScreenState();
}

class _SalesInvoiceItemDetailScreenState extends State<SalesInvoiceItemDetailScreen> {
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF6F7FC);

  bool _loading = true;
  bool _lastSaleLoading = false;
  String? _loadError;
  SalesItemInfo? _itemInfo;
  SalesItemLastSale? _lastSale;
  bool _lastSaleChecked = false;
  List<SalesUomOption> _uoms = [];
  late String _uom;
  /// Base-UOM average cost (ITEMMASTER.AVERAGECOST).
  double _averageCost = 0;
  double _costPrice = 0;
  late final TextEditingController _rateCtrl;
  late final TextEditingController _qtyCtrl;
  late final TextEditingController _discountCtrl;

  SalesCatalogItem get _item => widget.catalogItem;

  bool get _inStock => _item.stock > 0;

  bool get _canAdd => _inStock || widget.allowAddWithoutStock;

  double get _qty {
    final v = double.tryParse(_qtyCtrl.text.trim());
    if (v == null || v <= 0) return 0;
    return v;
  }

  double get _rate {
    final v = double.tryParse(_rateCtrl.text.trim());
    if (v == null || v < 0) return 0;
    return v;
  }

  double get _discountPerUnit {
    final v = double.tryParse(_discountCtrl.text.trim().replaceAll(',', ''));
    if (v == null || v < 0) return 0;
    return v > _rate ? _rate : v;
  }

  double get _discountTotal => _qty * _discountPerUnit;

  double get _lineAmount => (_qty * _rate) - _discountTotal;

  /// Prefer average cost; fall back to cost price when avg is 0.
  double get _displayUnitCost => _averageCost > 0 ? _averageCost : _costPrice;

  bool get _displayingAverageCost => _averageCost > 0;

  @override
  void initState() {
    super.initState();
    _uom = _item.unit.isNotEmpty ? _item.unit : 'PCS';
    _rateCtrl = TextEditingController(text: _item.rate.toStringAsFixed(2));
    _qtyCtrl = TextEditingController(text: '1');
    _discountCtrl = TextEditingController(text: '0');
    _load();
  }

  @override
  void dispose() {
    _rateCtrl.dispose();
    _qtyCtrl.dispose();
    _discountCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final info = await widget.service.lookupItem(_item.itemCode);
      final uoms = await widget.service.getItemUoms(_item.itemCode);
      if (!mounted) return;
      final uom = uoms.any((u) => u.code == _uom)
          ? _uom
          : (uoms.isNotEmpty
              ? uoms.first.code
              : (info.baseUom.isNotEmpty ? info.baseUom : _uom));
      final pricing = await widget.service.getUomPricing(_item.itemCode, uom);
      if (!mounted) return;
      setState(() {
        _itemInfo = info;
        _uoms = uoms;
        _uom = uom;
        _averageCost = pricing.averageCost > 0 ? pricing.averageCost : info.averageCost;
        _costPrice = pricing.costPrice > 0 ? pricing.costPrice : info.costPrice;
        final rate = pricing.rate > 0 ? pricing.rate : (_item.rate > 0 ? _item.rate : info.retailPrice);
        _rateCtrl.text = rate.toStringAsFixed(2);
        _loading = false;
        _lastSaleLoading = true;
        _lastSaleChecked = false;
      });
      SalesItemLastSale? lastSale;
      try {
        lastSale = await widget.service.getItemLastSale(
          itemCode: _item.itemCode,
          customerCode: widget.customerCode,
        );
      } catch (_) {
        lastSale = null;
      }
      if (!mounted) return;
      setState(() {
        _lastSale = lastSale;
        _lastSaleLoading = false;
        _lastSaleChecked = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _lastSaleLoading = false;
        _loadError = '$e';
      });
    }
  }

  void _applyLastSale() {
    final last = _lastSale;
    if (last == null) return;
    setState(() {
      if (last.uom.isNotEmpty && (_uoms.isEmpty || _uoms.any((u) => u.code == last.uom))) {
        _uom = last.uom;
      }
      if (last.qty > 0) {
        _qtyCtrl.text = _fmtQty(last.qty);
      }
      final price = last.netRate > 0 ? last.netRate : last.rate;
      if (price >= 0) {
        _rateCtrl.text = price.toStringAsFixed(2);
      }
    });
  }

  Future<void> _onUomChanged(String? value) async {
    if (value == null || value.isEmpty || value == _uom) return;
    setState(() => _loading = true);
    try {
      final pricing = await widget.service.getUomPricing(_item.itemCode, value);
      if (!mounted) return;
      setState(() {
        _uom = value;
        _averageCost = pricing.averageCost;
        if (pricing.costPrice > 0) {
          _costPrice = pricing.costPrice;
        }
        if (pricing.rate > 0) {
          _rateCtrl.text = pricing.rate.toStringAsFixed(2);
        }
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showAppSnackBar(context, '$e');
    }
  }

  void _adjustQty(double delta) {
    final current = _qty > 0 ? _qty : 1;
    final next = (current + delta).clamp(1.0, 999999.0);
    _qtyCtrl.text = _fmtQty(next);
    setState(() {});
  }

  void _addToCart() {
    if (!_canAdd) {
      showAppSnackBar(context, 'Item is out of stock.');
      return;
    }
    if (_qty <= 0) {
      showAppSnackBar(context, 'Enter a valid quantity.');
      return;
    }
    if (_rate < 0) {
      showAppSnackBar(context, 'Enter a valid price.');
      return;
    }
    Navigator.of(context).pop(
      SalesInvoiceItemAddRequest(uom: _uom, qty: _qty, rate: _rate, discount: _discountPerUnit),
    );
  }

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(2);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Item details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      ),
      body: _loading && _itemInfo == null
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : _loadError != null && _itemInfo == null
              ? _errorBody()
              : _body(),
      bottomNavigationBar: _loadError != null && _itemInfo == null
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: _canAdd ? _accent : Colors.grey.shade400,
                    minimumSize: const Size(double.infinity, 52),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  onPressed: !_canAdd ? null : _addToCart,
                  icon: const Icon(Icons.add_shopping_cart_outlined),
                  label: Text(
                    _canAdd
                        ? 'Add to cart • ${_lineAmount.toStringAsFixed(2)}'
                        : 'Out of stock',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                  ),
                ),
              ),
            ),
    );
  }

  Widget _errorBody() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            Text(_loadError!, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }

  Widget _body() {
    final stock = _itemInfo?.currentStock ?? _item.stock;
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 100),
          children: [
            _imageArea(),
            const SizedBox(height: 12),
            _detailsCard(stock),
            const SizedBox(height: 12),
            _lastSaleSection(),
            const SizedBox(height: 12),
            _optionsCard(),
          ],
        ),
        if (_loading)
          const Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: LinearProgressIndicator(minHeight: 2, color: _accent),
          ),
      ],
    );
  }

  Widget _imageArea() {
    final url = widget.imageUrl?.trim();
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: AspectRatio(
        aspectRatio: 1.35,
        child: url != null && url.isNotEmpty
            ? Image.network(
                url,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => _imagePlaceholder(),
                loadingBuilder: (context, child, progress) {
                  if (progress == null) return child;
                  return Center(
                    child: CircularProgressIndicator(
                      color: _accent,
                      value: progress.expectedTotalBytes != null
                          ? progress.cumulativeBytesLoaded / progress.expectedTotalBytes!
                          : null,
                    ),
                  );
                },
              )
            : _imagePlaceholder(),
      ),
    );
  }

  Widget _imagePlaceholder() {
    return Container(
      color: const Color(0xFFF0F2F8),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.inventory_2_outlined, size: 56, color: Colors.grey.shade400),
          const SizedBox(height: 8),
          Text(
            _item.itemCode,
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }

  Widget _detailsCard(double stock) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _item.itemCode,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
            ),
            if (_item.itemName.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                _item.itemName,
                style: TextStyle(fontSize: 14, height: 1.35, color: Colors.grey.shade800),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (_item.brand.isNotEmpty) _detailChip(Icons.sell_outlined, _item.brand),
                if (_item.barcode.isNotEmpty) _detailChip(Icons.qr_code_2_outlined, _item.barcode),
                _detailChip(
                  Icons.layers_outlined,
                  'Stock ${_fmtQty(stock)}',
                  fg: stock > 0 ? const Color(0xFF2E7D32) : const Color(0xFFC62828),
                  bg: stock > 0 ? const Color(0xFFE8F5E9) : const Color(0xFFFFEBEE),
                ),
                _detailChip(
                  Icons.payments_outlined,
                  '${_displayingAverageCost ? 'Avg' : 'Cost'} ${_displayUnitCost.toStringAsFixed(2)}',
                  fg: const Color(0xFF262C50),
                  bg: const Color(0xFFEEF2FF),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _detailChip(IconData icon, String label, {Color? fg, Color? bg}) {
    final foreground = fg ?? const Color(0xFF5A6275);
    final background = bg ?? const Color(0xFFF0F2F8);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(8)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: foreground),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: foreground)),
        ],
      ),
    );
  }

  Widget _lastSaleSection() {
    if (_lastSaleLoading) {
      return Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 18),
          child: Row(
            children: [
              SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: _accent)),
              SizedBox(width: 12),
              Text('Loading last sale…', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            ],
          ),
        ),
      );
    }
    final last = _lastSale;
    if (last == null) {
      if (!_lastSaleChecked) return const SizedBox.shrink();
      return Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
          child: Row(
            children: [
              Icon(Icons.history_rounded, size: 18, color: Colors.grey.shade500),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  widget.customerCode.isNotEmpty
                      ? 'No previous sale for this customer on this item.'
                      : 'No previous sale found for this item.',
                  style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: Colors.grey.shade700),
                ),
              ),
            ],
          ),
        ),
      );
    }

    final title = last.forSelectedCustomer
        ? 'Last sale to ${widget.customerName.isNotEmpty ? widget.customerName : last.customerLabel}'
        : 'Last sold to ${last.customerLabel}';
    final qtyLabel = last.uom.isNotEmpty ? '${_fmtQty(last.qty)} ${last.uom}' : _fmtQty(last.qty);
    final price = last.netRate > 0 ? last.netRate : last.rate;
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.history_rounded, size: 18, color: _accent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: Color(0xFF262C50)),
                  ),
                ),
              ],
            ),
            if (last.billDate.isNotEmpty || last.billno.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                [
                  if (last.billDate.isNotEmpty) last.billDate,
                  if (last.billno.isNotEmpty) 'Bill ${last.billno}',
                ].join(' • '),
                style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: _lastSaleStat('Qty', qtyLabel)),
                const SizedBox(width: 10),
                Expanded(child: _lastSaleStat('Price', price.toStringAsFixed(2))),
              ],
            ),
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: _applyLastSale,
                icon: const Icon(Icons.content_copy_rounded, size: 16),
                label: const Text('Use qty & price'),
                style: TextButton.styleFrom(
                  foregroundColor: _accent,
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _lastSaleStat(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF0F2F8),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
          const SizedBox(height: 2),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50))),
        ],
      ),
    );
  }

  Widget _optionsCard() {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Add to invoice', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
            const SizedBox(height: 14),
            if (_uoms.length > 1)
              DropdownButtonFormField<String>(
                value: _uom,
                decoration: InputDecoration(
                  labelText: 'UOM',
                  filled: true,
                  fillColor: _bg,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                ),
                items: _uoms.map((u) => DropdownMenuItem(value: u.code, child: Text(u.code))).toList(),
                onChanged: _loading ? null : _onUomChanged,
              )
            else
              _optionRow('UOM', _uom),
            const SizedBox(height: 14),
            NumericTextField(
              controller: _rateCtrl,
              decoration: InputDecoration(
                labelText: 'Price',
                filled: true,
                fillColor: _bg,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 14),
            NumericTextField(
              controller: _qtyCtrl,
              labelText: 'Qty',
              decoration: InputDecoration(
                labelText: 'Qty',
                filled: true,
                fillColor: _bg,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 14),
            NumericTextField(
              controller: _discountCtrl,
              decoration: InputDecoration(
                labelText: 'Discount / unit',
                helperText: 'Per unit × qty = total discount',
                filled: true,
                fillColor: _bg,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _qtyButton(Icons.remove_rounded, () => _adjustQty(-1)),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 28),
                  child: Text(
                    _fmtQty(_qty > 0 ? _qty : 0),
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 22, color: Color(0xFF262C50)),
                  ),
                ),
                _qtyButton(Icons.add_rounded, () => _adjustQty(1)),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFE3F2FD),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Column(
                children: [
                  if (_discountTotal > 0)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        children: [
                          Text('Gross', style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                          const Spacer(),
                          Text(
                            (_qty * _rate).toStringAsFixed(2),
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey.shade800),
                          ),
                        ],
                      ),
                    ),
                  if (_discountTotal > 0)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Row(
                        children: [
                          Text(
                            'Discount (${_fmtQty(_qty)} × ${_discountPerUnit.toStringAsFixed(2)})',
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                          ),
                          const Spacer(),
                          Text(
                            '−${_discountTotal.toStringAsFixed(2)}',
                            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFFC62828)),
                          ),
                        ],
                      ),
                    ),
                  Row(
                    children: [
                      const Text('Line amount', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                      const Spacer(),
                      Text(
                        _lineAmount.toStringAsFixed(2),
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: _accent),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _optionRow(String label, String value) {
    return Row(
      children: [
        Text('$label', style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
        const Spacer(),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
      ],
    );
  }

  Widget _qtyButton(IconData icon, VoidCallback onTap) {
    return Material(
      color: _accent,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: SizedBox(
          width: 48,
          height: 48,
          child: Icon(icon, color: Colors.white, size: 26),
        ),
      ),
    );
  }
}
