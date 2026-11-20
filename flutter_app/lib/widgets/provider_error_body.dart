import 'package:flutter/material.dart';

import '../core/network/access_denied_alert.dart';
import '../core/network/api_error_message.dart';
import 'api_error_banner.dart';

/// Full-page error for ChangeNotifier providers — shows access alert on 403.
class ProviderErrorBody extends StatefulWidget {
  const ProviderErrorBody({
    super.key,
    required this.message,
    this.errorCause,
    this.onRetry,
  });

  final String message;
  final Object? errorCause;
  final VoidCallback? onRetry;

  @override
  State<ProviderErrorBody> createState() => _ProviderErrorBodyState();
}

class _ProviderErrorBodyState extends State<ProviderErrorBody> {
  Object? _dialogShownFor;

  @override
  void didUpdateWidget(covariant ProviderErrorBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    _maybeShowAccessDialog();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeShowAccessDialog());
  }

  void _maybeShowAccessDialog() {
    final cause = widget.errorCause;
    if (cause == null || !isAccessDenied(cause) || identical(cause, _dialogShownFor)) {
      return;
    }
    _dialogShownFor = cause;
    maybeShowAccessDeniedAlert(context, cause);
  }

  @override
  Widget build(BuildContext context) {
    return ApiErrorCenter(
      message: widget.message,
      error: widget.errorCause,
      onRetry: widget.onRetry,
    );
  }
}
