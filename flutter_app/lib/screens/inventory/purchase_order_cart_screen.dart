import 'package:flutter/material.dart';

import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

class PurchaseOrderCartLineView {
  const PurchaseOrderCartLineView({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.qty,
    required this.rate,
    required this.amount,
    this.barcode = '',
  });

  final String itemCode;
  final String itemName;
  final String uom;
  final double qty;
  final double rate;
  final double amount;
  final String barcode;
}

/// Cart-style PO lines: qty steppers + editable purchase rate.
class PurchaseOrderCartScreen extends StatefulWidget {
  const PurchaseOrderCartScreen({
    super.key,
    required this.getLines,
    required this.getNetTotal,
    required this.onLineDelete,
    required this.onQtyChanged,
    required this.onRateChanged,
    this.onLineEdit,
    this.lpono = '',
    this.lpoDate = '',
    this.title = 'Purchase cart',
    this.emptyHint = 'Search or scan products to add lines to this purchase order.',
    this.continueLabel = 'Continue',
  });

  final List<PurchaseOrderCartLineView> Function() getLines;
  final double Function() getNetTotal;
  final void Function(int index) onLineDelete;
  final void Function(int index, double qty) onQtyChanged;
  final void Function(int index, double rate) onRateChanged;
  final Future<void> Function(int index)? onLineEdit;
  final String lpono;
  final String lpoDate;
  final String title;
  final String emptyHint;
  final String continueLabel;

  @override
  State<PurchaseOrderCartScreen> createState() => _PurchaseOrderCartScreenState();
}

class _PurchaseOrderCartScreenState extends State<PurchaseOrderCartScreen> {
  static const _bg = Color(0xFFF4F5F8);
  static const _ink = Color(0xFF111827);
  static const _muted = Color(0xFF6B7280);
  static const _accent = Color(0xFF1565C0);

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(2);
  }

  void _refresh() {
    if (mounted) setState(() {});
  }

  void _adjustQty(int index, double delta) {
    final lines = widget.getLines();
    if (index < 0 || index >= lines.length) return;
    final next = lines[index].qty + delta;
    if (next <= 0) {
      widget.onLineDelete(index);
      _refresh();
      return;
    }
    widget.onQtyChanged(index, next);
    _refresh();
  }

  Future<void> _editQty(int index, double current) async {
    final ctrl = TextEditingController(
      text: current == current.roundToDouble() ? current.round().toString() : current.toStringAsFixed(2),
    );
    final next = await showDialog<double>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Quantity'),
        content: NumericTextField(
          controller: ctrl,
          autofocus: true,
          selectAllOnFocus: true,
          labelText: 'Qty',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: _accent),
            onPressed: () {
              final v = double.tryParse(ctrl.text.trim().replaceAll(',', '')) ?? 0;
              if (v <= 0) return;
              Navigator.pop(ctx, v);
            },
            child: const Text('OK'),
          ),
        ],
      ),
    );
    // Dispose after dialog element tree is gone (avoids used-after-dispose).
    WidgetsBinding.instance.addPostFrameCallback((_) => ctrl.dispose());
    if (next == null || !mounted) return;
    widget.onQtyChanged(index, next);
    _refresh();
  }

  Future<void> _editRate(int index, double current) async {
    final ctrl = TextEditingController(text: current.toStringAsFixed(2));
    final next = await showDialog<double>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Purchase rate'),
        content: NumericTextField(
          controller: ctrl,
          autofocus: true,
          selectAllOnFocus: true,
          labelText: 'Rate',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: _accent),
            onPressed: () {
              final v = double.tryParse(ctrl.text.trim().replaceAll(',', '')) ?? -1;
              if (v < 0) return;
              Navigator.pop(ctx, v);
            },
            child: const Text('OK'),
          ),
        ],
      ),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => ctrl.dispose());
    if (next == null || !mounted) return;
    widget.onRateChanged(index, next);
    _refresh();
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
            Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            Text(
              widget.lpono.isNotEmpty
                  ? '${widget.lpono} • ${widget.lpoDate.isEmpty ? '—' : widget.lpoDate}'
                  : 'Checkout lines',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: Colors.grey.shade600),
            ),
          ],
        ),
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
                    '${widget.continueLabel} • ${netTotal.toStringAsFixed(2)}',
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
              widget.emptyHint,
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

  Widget _cartBody(List<PurchaseOrderCartLineView> lines, double netTotal, String itemLabel) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      children: [
        Text(itemLabel, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: _ink)),
        const SizedBox(height: 8),
        ...lines.asMap().entries.map(
              (e) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _cartLineCard(e.value, e.key),
              ),
            ),
        const SizedBox(height: 4),
        Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE5E7EB)),
          ),
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
          child: Row(
            children: [
              Text(
                'Total (${lines.length} item${lines.length == 1 ? '' : 's'})',
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: _ink),
              ),
              const Spacer(),
              Text(
                netTotal.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 20, color: _ink),
              ),
            ],
          ),
        ),
        const SizedBox(height: 72),
      ],
    );
  }

  Widget _cartLineCard(PurchaseOrderCartLineView line, int index) {
    final name = line.itemName.isNotEmpty ? line.itemName : line.itemCode;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE5E7EB)),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 8, offset: const Offset(0, 2)),
        ],
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15, color: _ink, height: 1.25),
                ),
              ),
              IconButton(
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                icon: const Icon(Icons.delete_outline, size: 20, color: Color(0xFFEF4444)),
                onPressed: () {
                  widget.onLineDelete(index);
                  _refresh();
                },
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Code ${line.itemCode} · ${line.uom}'
            '${line.barcode.isNotEmpty ? ' · BC ${line.barcode}' : ''}',
            style: const TextStyle(fontSize: 12, color: _muted, height: 1.3),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              if (widget.onLineEdit != null) ...[
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () async {
                      await widget.onLineEdit!(index);
                      _refresh();
                    },
                    icon: const Icon(Icons.tune_outlined, size: 16),
                    label: Text('UOM ${line.uom}', style: const TextStyle(fontSize: 12)),
                    style: OutlinedButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
              ],
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _editRate(index, line.rate),
                  style: OutlinedButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                  ),
                  child: Text(
                    'Rate ${line.rate.toStringAsFixed(2)}',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              _qtyStepper(line, index),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Text(
                '${_fmtQty(line.qty)} × ${line.rate.toStringAsFixed(2)}',
                style: const TextStyle(fontSize: 12, color: _muted),
              ),
              const Spacer(),
              Text(
                line.amount.toStringAsFixed(2),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17, color: _ink),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _qtyStepper(PurchaseOrderCartLineView line, int index) {
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: const Color(0xFFE5E7EB)),
        borderRadius: BorderRadius.circular(24),
        color: Colors.white,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _stepperButton(icon: Icons.remove, onTap: () => _adjustQty(index, -1)),
          InkWell(
            onTap: () => _editQty(index, line.qty),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Text(
                _fmtQty(line.qty),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: _ink),
              ),
            ),
          ),
          _stepperButton(icon: Icons.add, onTap: () => _adjustQty(index, 1)),
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
}
