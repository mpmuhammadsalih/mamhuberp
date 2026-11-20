import 'package:flutter/material.dart';

import '../../services/sales_service.dart';
import '../../widgets/numeric_text_field.dart';

/// POS-style payment tender rows for non-credit sales invoices.
class SalesInvoicePaymentPanel extends StatefulWidget {
  const SalesInvoicePaymentPanel({
    super.key,
    required this.netTotal,
    required this.tenders,
    required this.amounts,
    required this.onChanged,
  });

  final double netTotal;
  final List<SalesPaymentTender> tenders;
  final Map<String, double> amounts;
  final ValueChanged<Map<String, double>> onChanged;

  @override
  State<SalesInvoicePaymentPanel> createState() => _SalesInvoicePaymentPanelState();
}

class _SalesInvoicePaymentPanelState extends State<SalesInvoicePaymentPanel> {
  String? _selectedCode;
  final _controllers = <String, TextEditingController>{};
  /// Methods filled via long press — second long press on same row clears amount.
  final Set<String> _longPressFilled = {};

  @override
  void initState() {
    super.initState();
    _syncControllers();
  }

  @override
  void didUpdateWidget(covariant SalesInvoicePaymentPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.tenders != widget.tenders || oldWidget.amounts != widget.amounts) {
      _syncControllers();
    }
  }

  void _syncControllers() {
    for (final t in widget.tenders) {
      final code = t.tenderCode;
      final val = widget.amounts[code] ?? 0.0;
      final ctrl = _controllers.putIfAbsent(code, () => TextEditingController());
      final text = val == 0 ? '0' : val.toStringAsFixed(val == val.roundToDouble() ? 0 : 2);
      if (ctrl.text != text) {
        ctrl.text = text;
      }
    }
  }

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  double _parse(String text) => double.tryParse(text.replaceAll(',', '').trim()) ?? 0;

  void _emit(Map<String, double> next) {
    widget.onChanged(next);
  }

  void _onRowTap(String code) {
    setState(() => _selectedCode = code);
  }

  void _onRowLongPress(String code) {
    setState(() => _selectedCode = code);
    final next = Map<String, double>.from(widget.amounts);

    if (_longPressFilled.contains(code)) {
      next[code] = 0;
      _longPressFilled.remove(code);
      _emit(next);
      return;
    }

    var sumOthers = 0.0;
    for (final t in widget.tenders) {
      final tc = t.tenderCode;
      if (tc == code) continue;
      sumOthers += next[tc] ?? 0;
    }
    next[code] = (widget.netTotal - sumOthers).clamp(0, double.infinity);
    _longPressFilled.add(code);
    _emit(next);
  }

  void _onAmountEdited(String code, String text) {
    _longPressFilled.remove(code);
    final amt = _parse(text);
    final next = Map<String, double>.from(widget.amounts);
    next[code] = amt;
    _emit(next);
  }

  double get _totalPaid =>
      widget.amounts.values.fold(0.0, (s, v) => s + v);

  double get _changeDue => (_totalPaid - widget.netTotal).clamp(0, double.infinity);

  double get _balanceDue => (widget.netTotal - _totalPaid).clamp(0, double.infinity);

  IconData _iconFor(SalesPaymentTender t) {
    final cat = t.category.toUpperCase();
    final key = t.iconKey.toLowerCase();
    if (cat == 'CASH' || key.contains('cash')) return Icons.payments_outlined;
    if (cat == 'CARD' || key.contains('card')) return Icons.credit_card_outlined;
    if (cat == 'WALLET' || key.contains('wallet')) return Icons.account_balance_wallet_outlined;
    if (t.tenderCode == 'LOYALTY' || t.tenderCode == 'POINTS') return Icons.stars_outlined;
    return Icons.account_balance_outlined;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.tenders.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final t in widget.tenders) ...[
          _PaymentRow(
            tender: t,
            icon: _iconFor(t),
            selected: _selectedCode == t.tenderCode,
            controller: _controllers.putIfAbsent(
              t.tenderCode,
              () => TextEditingController(
                text: (widget.amounts[t.tenderCode] ?? 0).toStringAsFixed(2),
              ),
            ),
            onTap: () => _onRowTap(t.tenderCode),
            onLongPress: () => _onRowLongPress(t.tenderCode),
            onAmountChanged: (v) => _onAmountEdited(t.tenderCode, v),
          ),
          const SizedBox(height: 8),
        ],
        const Divider(height: 20),
        _summaryRow('Net total', widget.netTotal.toStringAsFixed(2), bold: true),
        const SizedBox(height: 6),
        _summaryRow('Total paid', _totalPaid.toStringAsFixed(2)),
        if (_balanceDue >= 0.01)
          _summaryRow(
            'Balance due',
            _balanceDue.toStringAsFixed(2),
            color: Colors.orange.shade800,
          ),
        if (_changeDue >= 0.01)
          _summaryRow(
            'Change',
            _changeDue.toStringAsFixed(2),
            color: Colors.green.shade800,
          ),
      ],
    );
  }

  Widget _summaryRow(String label, String value, {bool bold = false, Color? color}) {
    return Row(
      children: [
        Text(label, style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
        const Spacer(),
        Text(
          value,
          style: TextStyle(
            fontWeight: bold ? FontWeight.w800 : FontWeight.w600,
            fontSize: bold ? 16 : 14,
            color: color,
          ),
        ),
      ],
    );
  }
}

class _PaymentRow extends StatelessWidget {
  const _PaymentRow({
    required this.tender,
    required this.icon,
    required this.selected,
    required this.controller,
    required this.onTap,
    required this.onLongPress,
    required this.onAmountChanged,
  });

  final SalesPaymentTender tender;
  final IconData icon;
  final bool selected;
  final TextEditingController controller;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final ValueChanged<String> onAmountChanged;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? const Color(0xFFE8F0FE) : Colors.white,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: selected ? const Color(0xFF1565C0) : const Color(0xFFDDE1EA),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: InkWell(
                onTap: onTap,
                onLongPress: onLongPress,
                borderRadius: BorderRadius.circular(6),
                child: Row(
                  children: [
                    Icon(icon, size: 22, color: const Color(0xFF1565C0)),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        tender.tenderName,
                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 96,
              child: NumericTextField(
                controller: controller,
                textAlign: TextAlign.right,
                selectAllOnFocus: true,
                decoration: const InputDecoration(
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                  border: OutlineInputBorder(),
                ),
                onChanged: onAmountChanged,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Build save payload fields from POS-style tender amounts (mirrors POS checkout).
Map<String, dynamic> buildSalesPaymentHeaderFields({
  required List<SalesPaymentTender> tenders,
  required Map<String, double> amounts,
  required double netTotal,
}) {
  final meta = {for (final t in tenders) t.tenderCode: t};
  final totalPaid = amounts.values.fold(0.0, (s, v) => s + v);
  final change = (totalPaid - netTotal).clamp(0.0, double.infinity);

  bool isCash(String code) {
    final cd = code.toUpperCase();
    if (cd == 'CASH') return true;
    final cat = (meta[cd]?.category ?? '').toUpperCase();
    return cat == 'CASH';
  }

  final saveAmounts = <String, double>{
    for (final e in amounts.entries)
      if (e.value >= 0.005) e.key.toUpperCase(): double.parse(e.value.toStringAsFixed(2)),
  };
  var remaining = double.parse(change.toStringAsFixed(2));
  if (remaining >= 0.005) {
    final cashCodes = saveAmounts.keys.where(isCash).toList()
      ..sort((a, b) => a == 'CASH' ? -1 : b == 'CASH' ? 1 : a.compareTo(b));
    for (final code in cashCodes) {
      if (remaining < 0.005) break;
      final amt = saveAmounts[code] ?? 0;
      if (amt < 0.005) continue;
      final deduct = amt < remaining ? amt : remaining;
      final net = double.parse((amt - deduct).toStringAsFixed(2));
      if (net >= 0.005) {
        saveAmounts[code] = net;
      } else {
        saveAmounts.remove(code);
      }
      remaining = double.parse((remaining - deduct).toStringAsFixed(2));
    }
  }

  var cash = 0.0;
  var card = 0.0;
  var wallet = 0.0;
  var loyalty = 0.0;
  var points = 0.0;
  final paymentModes = <Map<String, dynamic>>[];
  final seen = <String>{};

  for (final t in tenders) {
    final code = t.tenderCode;
    final amt = saveAmounts[code] ?? 0;
    if (amt >= 0.005) {
      paymentModes.add({'code': code, 'amount': amt, 'reference': ''});
      seen.add(code);
    }
  }
  for (final e in saveAmounts.entries) {
    if (e.value >= 0.005 && !seen.contains(e.key)) {
      paymentModes.add({'code': e.key, 'amount': e.value, 'reference': ''});
    }
  }

  for (final e in saveAmounts.entries) {
    final cd = e.key;
    final amt = e.value;
    final cat = (meta[cd]?.category ?? '').toUpperCase();
    if (cd == 'LOYALTY') {
      loyalty += amt;
    } else if (cd == 'POINTS') {
      points += amt;
    } else if (cat == 'CASH' || cd == 'CASH') {
      cash += amt;
    } else if (cat == 'CARD') {
      card += amt;
    } else if (cat == 'WALLET' || cat == 'VOUCHER') {
      wallet += amt;
    } else {
      wallet += amt;
    }
  }

  return {
    'cashamount': double.parse(cash.toStringAsFixed(2)),
    'cardamount': double.parse(card.toStringAsFixed(2)),
    'walletamount': double.parse(wallet.toStringAsFixed(2)),
    'loyaltyamount': double.parse(loyalty.toStringAsFixed(2)),
    'pointsamount': double.parse(points.toStringAsFixed(2)),
    'payment_modes': paymentModes,
    'record_payment_modes': true,
  };
}

String? validateSalesPayment({
  required Map<String, double> amounts,
  required double netTotal,
}) {
  if (netTotal <= 0.005) return null;
  final paid = amounts.values.fold(0.0, (s, v) => s + v);
  if (paid + 1e-6 < netTotal) {
    return 'Payment total ${paid.toStringAsFixed(2)} is less than net ${netTotal.toStringAsFixed(2)}.';
  }
  return null;
}
