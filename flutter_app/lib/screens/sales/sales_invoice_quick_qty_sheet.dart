import 'package:flutter/material.dart';
import '../../core/ui/app_snackbar.dart';

import '../../widgets/numeric_text_field.dart';

/// Qty-only bottom sheet for quick add from the catalog + button.
class SalesInvoiceQuickQtySheet extends StatefulWidget {
  const SalesInvoiceQuickQtySheet({
    super.key,
    required this.itemCode,
    required this.itemName,
  });

  final String itemCode;
  final String itemName;

  @override
  State<SalesInvoiceQuickQtySheet> createState() => _SalesInvoiceQuickQtySheetState();
}

class _SalesInvoiceQuickQtySheetState extends State<SalesInvoiceQuickQtySheet> {
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF6F7FC);

  late final TextEditingController _qtyCtrl;

  double get _qty {
    final v = double.tryParse(_qtyCtrl.text.trim());
    if (v == null || v <= 0) return 0;
    return v;
  }

  @override
  void initState() {
    super.initState();
    _qtyCtrl = TextEditingController(text: '1');
  }

  @override
  void dispose() {
    _qtyCtrl.dispose();
    super.dispose();
  }

  void _adjustQty(double delta) {
    final current = _qty > 0 ? _qty : 1;
    final next = (current + delta).clamp(1.0, 999999.0);
    _qtyCtrl.text = _fmtQty(next);
    setState(() {});
  }

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(2);
  }

  void _confirm() {
    if (_qty <= 0) {
      showAppSnackBar(context, 'Enter a valid quantity.');
      return;
    }
    Navigator.of(context).pop(_qty);
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
          const SizedBox(height: 14),
          Text(
            widget.itemCode,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
          ),
          if (widget.itemName.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              widget.itemName,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
            ),
          ],
          const SizedBox(height: 16),
          NumericTextField(
            controller: _qtyCtrl,
            autofocus: true,
            selectAllOnFocus: true,
            decoration: InputDecoration(
              labelText: 'Qty',
              filled: true,
              fillColor: _bg,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
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
          const SizedBox(height: 18),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: _accent,
              minimumSize: const Size(double.infinity, 48),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            onPressed: _confirm,
            child: const Text('Add to cart', style: TextStyle(fontWeight: FontWeight.w700)),
          ),
        ],
      ),
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
