import 'package:flutter/material.dart';

import 'sales_invoice_catalog_step.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

class SalesInvoiceCartScreen extends StatefulWidget {
  const SalesInvoiceCartScreen({
    super.key,
    required this.getLines,
    required this.getNetTotal,
    required this.onLineEdit,
    required this.onLineDelete,
    required this.onQtyChanged,
    required this.onRateChanged,
    required this.onDiscountChanged,
    this.billNo = '',
    this.billDate = '',
  });

  final List<SalesInvoiceLineView> Function() getLines;
  final double Function() getNetTotal;
  final Future<void> Function(int index) onLineEdit;
  final void Function(int index) onLineDelete;
  final void Function(int index, double qty) onQtyChanged;
  final void Function(int index, double rate) onRateChanged;
  final void Function(int index, double discount) onDiscountChanged;
  final String billNo;
  final String billDate;

  @override
  State<SalesInvoiceCartScreen> createState() => _SalesInvoiceCartScreenState();
}

class _SalesInvoiceCartScreenState extends State<SalesInvoiceCartScreen> {
  static const _bg = Color(0xFFF4F5F8);
  static const _titleColor = Color(0xFF262C50);
  static const _ink = Color(0xFF111827);
  static const _muted = Color(0xFF6B7280);
  static const _accent = Color(0xFF1565C0);

  bool _editing = false;

  void _refresh() {
    if (mounted) setState(() {});
  }

  Future<void> _editLine(int index) async {
    await widget.onLineEdit(index);
    _refresh();
  }

  void _deleteLine(int index) {
    widget.onLineDelete(index);
    _refresh();
  }

  void _adjustQty(int index, double delta) {
    final lines = widget.getLines();
    if (index < 0 || index >= lines.length) return;
    final next = lines[index].qty + delta;
    if (next <= 0) {
      _deleteLine(index);
      return;
    }
    widget.onQtyChanged(index, next);
    _refresh();
  }

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(2);
  }

  @override
  Widget build(BuildContext context) {
    final lines = widget.getLines();
    final netTotal = widget.getNetTotal();
    final itemLabel = lines.length == 1 ? '1 Item' : '${lines.length} Items';

    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Sales Invoice', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            Text(
              widget.billNo.isNotEmpty
                  ? 'Bill No. ${widget.billNo} • ${widget.billDate.isEmpty ? '—' : widget.billDate}'
                  : 'Cart',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: Colors.white.withValues(alpha: 0.85)),
            ),
          ],
        ),
        actions: [
          if (lines.isNotEmpty)
            IconButton(
              tooltip: 'Line options',
              icon: Icon(_editing ? Icons.check_rounded : Icons.edit_outlined, size: 22),
              onPressed: () => setState(() => _editing = !_editing),
            )
          else
            const SizedBox(width: 8),
        ],
      ),
      body: lines.isEmpty ? _emptyBody() : _cartBody(lines, netTotal, itemLabel),
      bottomNavigationBar: lines.isEmpty
          ? null
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: _accent,
                    foregroundColor: Colors.white,
                    minimumSize: const Size(double.infinity, 52),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    elevation: 0,
                  ),
                  onPressed: () => Navigator.of(context).pop(true),
                  child: Text(
                    'Proceed to checkout • ${netTotal.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                  ),
                ),
              ),
            ),
    );
  }

  Widget _emptyBody() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.shopping_cart_outlined, size: 64, color: Colors.grey.shade400),
            const SizedBox(height: 16),
            const Text('Your cart is empty', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18, color: _ink)),
            const SizedBox(height: 8),
            Text(
              'Search or scan products to add items to your invoice.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: Colors.grey.shade600, height: 1.4),
            ),
            const SizedBox(height: 24),
            OutlinedButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Add items'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cartBody(List<SalesInvoiceLineView> lines, double netTotal, String itemLabel) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(28, 8, 28, 8),
      children: [
        Row(
          children: [
            Text(itemLabel, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: _ink)),
            const Spacer(),
            TextButton(
              onPressed: () => setState(() => _editing = !_editing),
              child: Text(_editing ? 'Done' : 'Edit'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        ...lines.asMap().entries.map((e) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _cartLineCard(e.value, e.key),
            )),
        const SizedBox(height: 4),
        _orderSummary(lines, netTotal),
        const SizedBox(height: 72),
      ],
    );
  }

  Widget _cartLineCard(SalesInvoiceLineView line, int index) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 8, offset: const Offset(0, 2)),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Text(
                  line.itemName,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: _ink, height: 1.15),
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                icon: Icon(
                  Icons.delete_outline,
                  size: 20,
                  color: _editing ? const Color(0xFFEF4444) : const Color(0xFF9CA3AF),
                ),
                onPressed: () => _deleteLine(index),
              ),
            ],
          ),
          Text(
            'Code ${line.itemCode}${line.subtitle.isNotEmpty ? ' • ${line.subtitle}' : ''}',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12, color: _muted, height: 1.2),
          ),
          if (line.discount > 0) ...[
            const SizedBox(height: 4),
            Text(
              'Discount ${_fmtQty(line.qty)} × ${line.discount.toStringAsFixed(2)} = −${line.discountTotal.toStringAsFixed(2)}',
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFFC62828)),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          line.amount.toStringAsFixed(2),
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17, color: _ink),
                        ),
                        const SizedBox(width: 8),
                        const Text(
                          'In Stock',
                          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF16A34A)),
                        ),
                      ],
                    ),
                    if (line.qty != 1 || line.discount > 0)
                      Text(
                        line.discount > 0
                            ? '${line.rate.toStringAsFixed(2)} × ${_fmtQty(line.qty)} − ${line.discountTotal.toStringAsFixed(2)}'
                            : '${line.rate.toStringAsFixed(2)} × ${_fmtQty(line.qty)}',
                        style: const TextStyle(fontSize: 11, color: _muted),
                      ),
                  ],
                ),
              ),
              if (!_editing) _qtyStepper(line, index),
            ],
          ),
          if (_editing) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _editLine(index),
                    icon: const Icon(Icons.tune_outlined, size: 16),
                    label: const Text('UOM / bin / lot', style: TextStyle(fontSize: 12)),
                    style: OutlinedButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _showRateDialog(index, line.rate),
                    style: OutlinedButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    ),
                    child: Text('Rate ${line.rate.toStringAsFixed(2)}', style: const TextStyle(fontSize: 12)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => _showDiscountDialog(index, line),
                icon: const Icon(Icons.discount_outlined, size: 16),
                label: Text(
                  line.discount > 0
                      ? 'Disc/unit ${line.discount.toStringAsFixed(2)}'
                      : 'Add discount',
                  style: const TextStyle(fontSize: 12),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFFC62828),
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _qtyStepper(SalesInvoiceLineView line, int index) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFE5E7EB)),
        borderRadius: BorderRadius.circular(24),
        color: Colors.white,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _stepperButton(
            icon: Icons.remove,
            onTap: () => _adjustQty(index, -1),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Text(
              _fmtQty(line.qty),
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: _ink),
            ),
          ),
          _stepperButton(
            icon: Icons.add,
            onTap: () => _adjustQty(index, 1),
          ),
        ],
      ),
    );
  }

  Widget _stepperButton({required IconData icon, required VoidCallback onTap}) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: SizedBox(
          width: 36,
          height: 36,
          child: Icon(icon, size: 18, color: _ink),
        ),
      ),
    );
  }

  Widget _orderSummary(List<SalesInvoiceLineView> lines, double netTotal) {
    final gross = lines.fold<double>(0, (s, l) => s + l.gross);
    final discountTotal = lines.fold<double>(0, (s, l) => s + l.discountTotal);
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        children: [
          _summaryRow('Subtotal (${lines.length} item${lines.length == 1 ? '' : 's'})', gross.toStringAsFixed(2)),
          const SizedBox(height: 10),
          _summaryRow(
            'Discount',
            discountTotal > 0 ? '−${discountTotal.toStringAsFixed(2)}' : '0.00',
            valueColor: discountTotal > 0 ? const Color(0xFFC62828) : null,
          ),
          const SizedBox(height: 10),
          _summaryRow('Tax', '0.00'),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Divider(height: 1, color: Color(0xFFE5E7EB)),
          ),
          Row(
            children: [
              const Text('Total', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: _ink)),
              const Spacer(),
              Text(
                netTotal.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: _ink),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _summaryRow(String label, String value, {Color? valueColor}) {
    return Row(
      children: [
        Text(label, style: const TextStyle(fontSize: 14, color: _muted)),
        const Spacer(),
        Text(
          value,
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: valueColor ?? _ink),
        ),
      ],
    );
  }

  Future<void> _showRateDialog(int index, double currentRate) async {
    final controller = TextEditingController(text: currentRate.toStringAsFixed(2));
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit rate'),
        content: NumericTextField(
          controller: controller,
          autofocus: true,
          selectAllOnFocus: true,
          labelText: 'Rate',
          decoration: const InputDecoration(border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (saved != true || !mounted) return;
    final parsed = double.tryParse(controller.text.trim());
    if (parsed == null || parsed < 0) return;
    widget.onRateChanged(index, parsed);
    _refresh();
  }

  Future<void> _showDiscountDialog(int index, SalesInvoiceLineView line) async {
    final maxPerUnit = line.rate;
    final controller = TextEditingController(
      text: line.discount > 0 ? line.discount.toStringAsFixed(2) : '',
    );
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Discount / unit'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Rate ${maxPerUnit.toStringAsFixed(2)}. Total discount = (disc / unit) × qty.',
              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
            ),
            const SizedBox(height: 12),
            NumericTextField(
              controller: controller,
              autofocus: true,
              selectAllOnFocus: true,
              labelText: 'Discount per unit',
              decoration: const InputDecoration(border: OutlineInputBorder()),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              controller.text = '0';
              Navigator.of(ctx).pop(true);
            },
            child: const Text('Clear'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (saved != true || !mounted) return;
    final parsed = double.tryParse(controller.text.trim().replaceAll(',', '')) ?? 0;
    if (parsed < 0) return;
    final clamped = parsed > maxPerUnit ? maxPerUnit : parsed;
    widget.onDiscountChanged(index, clamped);
    _refresh();
  }
}
