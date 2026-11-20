import 'package:flutter/material.dart';

/// Shows a floating snackbar in the **middle** of the screen (safe, readable,
/// and clear of the status bar / app bar / bottom Next button).
void showAppSnackBar(
  BuildContext context,
  String message, {
  Duration duration = const Duration(seconds: 3),
  Color? backgroundColor,
  SnackBarAction? action,
}) {
  if (!context.mounted) return;
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    appSnackBar(
      context: context,
      content: Text(message),
      duration: duration,
      backgroundColor: backgroundColor,
      action: action,
    ),
  );
}

/// Builds a mid-screen floating [SnackBar].
SnackBar appSnackBar({
  required BuildContext context,
  required Widget content,
  Duration duration = const Duration(seconds: 3),
  Color? backgroundColor,
  SnackBarAction? action,
}) {
  // Use the root view metrics so Scaffold padding tricks can't zero the insets.
  final views = View.of(context);
  final dpr = views.devicePixelRatio;
  final screenH = views.physicalSize.height / dpr;
  final safeTop = views.padding.top / dpr;
  final safeBottom = views.padding.bottom / dpr;

  // Keep the bar in the middle band of the usable screen.
  final usable = (screenH - safeTop - safeBottom).clamp(200.0, screenH);
  final vInset = (usable * 0.36 + safeBottom).clamp(96.0, screenH * 0.42);

  return SnackBar(
    content: DefaultTextStyle.merge(
      style: const TextStyle(
        color: Colors.white,
        fontSize: 14,
        fontWeight: FontWeight.w600,
        height: 1.35,
      ),
      child: content,
    ),
    action: action,
    duration: duration,
    backgroundColor: backgroundColor ?? const Color(0xE6323232),
    behavior: SnackBarBehavior.floating,
    elevation: 8,
    margin: EdgeInsets.fromLTRB(16, vInset, 16, vInset),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
  );
}
