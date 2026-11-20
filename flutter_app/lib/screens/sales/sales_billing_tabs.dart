import 'package:flutter/material.dart';

/// Billing-type tabs shared by Sales Invoice / Order / Return lists.
/// Visual style matches GRN hub tabs; row is centered.
class SalesBillingTabs extends StatelessWidget {
  const SalesBillingTabs({
    super.key,
    required this.billingType,
    required this.onChanged,
    this.accent = const Color(0xFF1565C0),
  });

  /// `null` / empty = All, `CASH`, or `CREDIT`.
  final String? billingType;
  final ValueChanged<String?> onChanged;
  final Color accent;

  static const _tabs = <(String?, String)>[
    (null, 'All'),
    ('CASH', 'Cash'),
    ('CREDIT', 'Credit'),
  ];

  @override
  Widget build(BuildContext context) {
    final current = (billingType ?? '').trim().toUpperCase();
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (var i = 0; i < _tabs.length; i++) ...[
            _Tab(
              label: _tabs[i].$2,
              active: (current.isEmpty && _tabs[i].$1 == null) ||
                  (current.isNotEmpty && current == (_tabs[i].$1 ?? '')),
              accent: accent,
              onTap: () {
                final next = _tabs[i].$1;
                final nextKey = (next ?? '').toUpperCase();
                if ((current.isEmpty && next == null) || current == nextKey) return;
                onChanged(next);
              },
            ),
            if (i < _tabs.length - 1) const SizedBox(width: 20),
          ],
        ],
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  const _Tab({
    required this.label,
    required this.active,
    required this.accent,
    required this.onTap,
  });

  final String label;
  final bool active;
  final Color accent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: active ? FontWeight.w700 : FontWeight.w500,
              color: active ? accent : const Color(0xFF6F7482),
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 28,
            height: 2,
            color: active ? accent : Colors.transparent,
          ),
        ],
      ),
    );
  }
}
