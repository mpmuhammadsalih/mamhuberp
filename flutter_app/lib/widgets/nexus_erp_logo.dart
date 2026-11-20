import 'package:flutter/material.dart';

/// Nexus ERP brand logo (`static/img/nexus-erp-logo.png` from Dynamics ERP).
class NexusErpLogo extends StatelessWidget {
  const NexusErpLogo({
    super.key,
    this.maxWidth = 220,
    this.maxHeight = 140,
  });

  static const assetPath = 'assets/images/nexus-erp-logo.png';

  final double maxWidth;
  final double maxHeight;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      assetPath,
      fit: BoxFit.contain,
      width: maxWidth,
      height: maxHeight,
      semanticLabel: 'Nexus Erp',
      filterQuality: FilterQuality.high,
    );
  }
}
