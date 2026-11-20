import 'package:flutter/material.dart';

/// Choice when creating a new document while a draft is still pending.
enum PendingDraftAction {
  continuePending,
  clearAndCreate,
  cancel,
}

/// Alert: continue the pending draft, clear it and start new, or cancel.
Future<PendingDraftAction> showPendingDraftAlert(
  BuildContext context, {
  required String summary,
  String documentLabel = 'transaction',
}) async {
  final result = await showDialog<PendingDraftAction>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Pending draft'),
      content: Text(
        'You have an unfinished $documentLabel:\n\n$summary\n\n'
        'Continue the pending draft, or clear it and start a new one?',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(PendingDraftAction.cancel),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(PendingDraftAction.clearAndCreate),
          child: const Text('Clear & new'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(ctx).pop(PendingDraftAction.continuePending),
          child: const Text('Continue'),
        ),
      ],
    ),
  );
  return result ?? PendingDraftAction.cancel;
}

/// Banner offering to resume an unfinished transaction draft.
class TransactionDraftBanner extends StatelessWidget {
  const TransactionDraftBanner({
    super.key,
    required this.title,
    required this.subtitle,
    required this.onContinue,
    required this.onDismiss,
    this.accent = const Color(0xFFE65100),
  });

  final String title;
  final String subtitle;
  final VoidCallback onContinue;
  final VoidCallback onDismiss;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 8, 14, 4),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: const Color(0xFFFFF8F0),
          borderRadius: BorderRadius.circular(11),
          border: Border.all(color: const Color(0xFFFFB74D)),
        ),
        child: Row(
          children: [
            const SizedBox(width: 12),
            Icon(Icons.play_circle_fill_rounded, color: accent, size: 28),
            const SizedBox(width: 10),
            Expanded(
              child: InkWell(
                onTap: onContinue,
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF7D8393),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        subtitle,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: accent,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            IconButton(
              tooltip: 'Dismiss',
              onPressed: onDismiss,
              icon: const Icon(Icons.close_rounded, size: 20),
            ),
            const SizedBox(width: 4),
          ],
        ),
      ),
    );
  }
}
