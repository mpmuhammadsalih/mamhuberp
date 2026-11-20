import 'package:flutter/material.dart';

import '../core/network/api_error_message.dart';

/// Inline banner for API failures — access denied uses info styling, not error red.
class ApiErrorBanner extends StatelessWidget {
  const ApiErrorBanner({
    super.key,
    required this.message,
    this.error,
    this.padding = const EdgeInsets.fromLTRB(16, 10, 16, 0),
  });

  final String message;
  final Object? error;
  final EdgeInsets padding;

  bool get _accessDenied => error != null && isAccessDenied(error!);

  @override
  Widget build(BuildContext context) {
    final bg = _accessDenied ? const Color(0xFFFFF8E1) : const Color(0xFFFFEBEE);
    final fg = _accessDenied ? const Color(0xFF6D4C00) : const Color(0xFFC62828);
    final icon = _accessDenied ? Icons.lock_outline_rounded : Icons.error_outline_rounded;

    return Padding(
      padding: padding,
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(10),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: fg, size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  message.length > 400 ? '${message.substring(0, 397)}…' : message,
                  style: TextStyle(color: fg, fontSize: 13),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Full-page API failure body (list screens).
class ApiErrorCenter extends StatelessWidget {
  const ApiErrorCenter({
    super.key,
    required this.message,
    this.error,
    this.onRetry,
  });

  final String message;
  final Object? error;
  final VoidCallback? onRetry;

  bool get _accessDenied => error != null && isAccessDenied(error!);

  @override
  Widget build(BuildContext context) {
    final fg = _accessDenied ? const Color(0xFF6D4C00) : null;
    final icon = _accessDenied ? Icons.lock_outline_rounded : Icons.error_outline_rounded;
    final iconColor = _accessDenied ? const Color(0xFFE65100) : Colors.grey;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: iconColor),
            const SizedBox(height: 12),
            Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: fg),
            ),
            if (!_accessDenied && onRetry != null) ...[
              const SizedBox(height: 12),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ],
        ),
      ),
    );
  }
}
