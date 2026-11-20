import 'package:flutter/material.dart';

/// Shared “confirm before save” for transaction create/edit screens.
Future<bool> confirmSaveTransaction(
  BuildContext context, {
  required String title,
  String? message,
  String confirmLabel = 'Save',
  Color? confirmColor,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: Text(message ?? 'Do you want to save this transaction?'),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: confirmColor ?? const Color(0xFF1565C0),
          ),
          onPressed: () => Navigator.of(ctx).pop(true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result == true;
}
