import 'package:flutter/material.dart';

import '../ui/app_snackbar.dart';
import 'access_denied_alert.dart';
import 'api_error_message.dart';

/// Maps an API failure to user text; shows access alert for 403 when [context] is set.
String handleApiError(
  BuildContext? context,
  Object e, {
  required bool authenticatedContext,
  bool showAccessDialog = true,
}) {
  if (isAccessDenied(e)) {
    if (context != null && showAccessDialog) {
      maybeShowAccessDeniedAlert(context, e);
    }
    return accessDeniedMessage(e);
  }
  return apiErrorMessage(e, authenticatedContext: authenticatedContext);
}

bool _preferErrorDialog(String message) {
  if (message.length >= 90) return true;
  final lower = message.toLowerCase();
  return lower.contains('setup date') ||
      lower.contains('transaction date') ||
      lower.contains('from–to') ||
      lower.contains('from-to') ||
      lower.contains('\n');
}

/// Shows a blocking dialog so long API messages stay readable on phones.
Future<void> showApiErrorDialog(
  BuildContext context,
  String message, {
  String title = 'Cannot continue',
}) async {
  if (!context.mounted) return;
  await showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: SingleChildScrollView(
        child: Text(message, style: const TextStyle(height: 1.35)),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('OK'),
        ),
      ],
    ),
  );
}

/// SnackBar for short API failures; longer / setup-date messages use a dialog.
/// 403 shows access alert instead of error snack.
void showApiErrorSnackBar(
  BuildContext context,
  Object e, {
  required bool authenticatedContext,
}) {
  if (maybeShowAccessDeniedAlert(context, e)) return;
  final message = apiErrorMessage(e, authenticatedContext: authenticatedContext);
  if (_preferErrorDialog(message)) {
    showApiErrorDialog(context, message);
    return;
  }
  showAppSnackBar(
    context,
    message,
    duration: const Duration(seconds: 5),
  );
}
