import 'package:flutter/material.dart';

import 'api_error_message.dart';

/// Shows a non-error alert when the user lacks menu or feature permission.
Future<void> showAccessDeniedAlert(
  BuildContext context, {
  String? message,
}) {
  final text = message ?? accessDeniedMessageFromStatus();
  return showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      icon: const Icon(Icons.lock_outline_rounded, color: Color(0xFFE65100), size: 32),
      title: const Text('Access restricted'),
      content: Text(text),
      actions: [
        FilledButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('OK'),
        ),
      ],
    ),
  );
}

/// Returns true when [e] was handled as access denied (dialog shown).
bool maybeShowAccessDeniedAlert(BuildContext context, Object e) {
  if (!isAccessDenied(e)) return false;
  showAccessDeniedAlert(context, message: accessDeniedMessage(e));
  return true;
}
