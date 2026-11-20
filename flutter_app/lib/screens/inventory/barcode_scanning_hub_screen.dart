import 'package:flutter/material.dart';

import 'barcode_print_list_screen.dart';
import 'barcode_print_scan_screen.dart';
import '../../core/theme/app_theme.dart';

/// Hub: product/shelf print lists (documents) + quick single reprint.
class BarcodeScanningHubScreen extends StatelessWidget {
  const BarcodeScanningHubScreen({super.key});

  static const _navy = Color(0xFF262C50);

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
        title: const Text(
          'Barcode Scanning',
          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        centerTitle: true,
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
        children: [
          const Text(
            'Build a print list on the phone, save it as a document, then open that list number in ERP Barcode Management to print labels.',
            style: TextStyle(color: Color(0xFF6B7280), fontSize: 14, height: 1.35),
          ),
          const SizedBox(height: 16),
          _ScanTypeCard(
            icon: Icons.playlist_add_check_rounded,
            color: const Color(0xFF0277BD),
            title: 'Product print lists',
            subtitle: 'Scan items into a list → save document → open list no. in ERP.',
            onTap: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(
                  builder: (_) => const BarcodePrintListScreen(listType: 'PRODUCT'),
                ),
              );
            },
          ),
          const SizedBox(height: 12),
          _ScanTypeCard(
            icon: Icons.view_module_rounded,
            color: const Color(0xFF00897B),
            title: 'Shelf print lists',
            subtitle: 'Scan shelves/bins into a list document for ERP printing.',
            onTap: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(
                  builder: (_) => const BarcodePrintListScreen(listType: 'SHELF'),
                ),
              );
            },
          ),
          const SizedBox(height: 20),
          const Text(
            'Quick reprint',
            style: TextStyle(fontWeight: FontWeight.w700, color: _navy, fontSize: 14),
          ),
          const SizedBox(height: 8),
          _ScanTypeCard(
            icon: Icons.print_outlined,
            color: const Color(0xFF5B3DF5),
            title: 'Single product / shelf',
            subtitle: 'Scan one code and print immediately on the phone printer.',
            onTap: () {
              Navigator.of(context).push<void>(
                MaterialPageRoute<void>(
                  builder: (_) => const BarcodePrintScanScreen(
                    mode: BarcodePrintMode.product,
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}

class _ScanTypeCard extends StatelessWidget {
  const _ScanTypeCard({
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFFE4E7F0)),
          ),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: color, size: 26),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                        color: Color(0xFF262C50),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        fontSize: 13,
                        color: Color(0xFF6B7280),
                        height: 1.3,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, color: color.withValues(alpha: 0.7)),
            ],
          ),
        ),
      ),
    );
  }
}
