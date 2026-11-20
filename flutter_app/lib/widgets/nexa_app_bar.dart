import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Shared blue app bar — use instead of raw [AppBar] so colour always applies.
PreferredSizeWidget nexaAppBar({
  Key? key,
  Widget? title,
  String? titleText,
  List<Widget>? actions,
  Widget? leading,
  bool automaticallyImplyLeading = true,
  bool? centerTitle,
  double elevation = 0,
  PreferredSizeWidget? bottom,
  Color? backgroundColor,
  Color? foregroundColor,
}) {
  return AppBar(
    key: key,
    title: title ??
        (titleText == null
            ? null
            : Text(titleText, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17))),
    actions: actions,
    leading: leading,
    automaticallyImplyLeading: automaticallyImplyLeading,
    centerTitle: centerTitle,
    elevation: elevation,
    scrolledUnderElevation: 0,
    backgroundColor: backgroundColor ?? AppTheme.appBarBlue,
    foregroundColor: foregroundColor ?? Colors.white,
    surfaceTintColor: Colors.transparent,
    iconTheme: const IconThemeData(color: Colors.white),
    actionsIconTheme: const IconThemeData(color: Colors.white),
    bottom: bottom,
  );
}
