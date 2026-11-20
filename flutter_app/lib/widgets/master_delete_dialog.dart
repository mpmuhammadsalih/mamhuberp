import 'package:flutter/material.dart';

/// Password-gated delete confirm (ERP HO item delete uses password ``123``;
/// login password is also accepted by the API).
Future<String?> showMasterDeletePasswordDialog(
  BuildContext context, {
  required String title,
  required String entityLabel,
}) {
  final password = TextEditingController();
  return showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) {
      return AlertDialog(
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Delete $entityLabel permanently? This cannot be undone.',
              style: TextStyle(fontSize: 13.5, color: Colors.grey.shade800),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: password,
              obscureText: true,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Delete password',
                hintText: 'Password',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              onSubmitted: (v) {
                final p = v.trim();
                if (p.isNotEmpty) Navigator.of(ctx).pop(p);
              },
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () {
              final p = password.text.trim();
              if (p.isEmpty) return;
              Navigator.of(ctx).pop(p);
            },
            child: const Text('Delete'),
          ),
        ],
      );
    },
  ).whenComplete(password.dispose);
}
