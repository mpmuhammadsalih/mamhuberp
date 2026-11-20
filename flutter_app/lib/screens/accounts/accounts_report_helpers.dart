import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_error_handler.dart';

String fmtMoney(double v) {
  final neg = v < 0;
  final abs = v.abs();
  final fixed = abs.toStringAsFixed(2);
  final parts = fixed.split('.');
  final whole = parts[0];
  final dec = parts.length > 1 ? parts[1] : '00';
  final buf = StringBuffer();
  for (var i = 0; i < whole.length; i++) {
    final fromEnd = whole.length - i;
    buf.write(whole[i]);
    if (fromEnd > 1 && fromEnd % 3 == 1) buf.write(',');
  }
  return '${neg ? '-' : ''}$buf.$dec';
}

String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

DateTime monthStart(DateTime d) => DateTime(d.year, d.month, 1);

Future<void> pickReportDate(
  BuildContext context, {
  required DateTime initial,
  required ValueChanged<DateTime> onPicked,
}) async {
  final picked = await showDatePicker(
    context: context,
    initialDate: initial,
    firstDate: DateTime(2000),
    lastDate: DateTime(2100),
  );
  if (picked != null) onPicked(picked);
}

Future<void> openPdfBytes(
  BuildContext context, {
  required Future<List<int>> Function() loadBytes,
  required String fileName,
  required bool Function() isMounted,
  void Function(bool busy)? setBusy,
}) async {
  setBusy?.call(true);
  try {
    final bytes = await loadBytes();
    final dir = await getTemporaryDirectory();
    final safe = fileName.replaceAll(RegExp(r'[^\w\-./]+'), '_');
    final file = File('${dir.path}/$safe');
    await file.writeAsBytes(bytes, flush: true);
    final opened = await OpenFilex.open(file.path, type: 'application/pdf');
    if (!isMounted()) return;
    if (opened.type != ResultType.done) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(opened.message.isNotEmpty ? opened.message : 'Could not open PDF.')),
      );
    }
  } catch (e) {
    if (!isMounted()) return;
    showApiErrorSnackBar(context, e, authenticatedContext: true);
  } finally {
    setBusy?.call(false);
  }
}

Future<void> sharePdfBytes(
  BuildContext context, {
  required Future<List<int>> Function() loadBytes,
  required String fileName,
  required String subject,
  required bool Function() isMounted,
  void Function(bool busy)? setBusy,
}) async {
  setBusy?.call(true);
  try {
    final bytes = await loadBytes();
    final dir = await getTemporaryDirectory();
    final safe = fileName.replaceAll(RegExp(r'[^\w\-./]+'), '_');
    final file = File('${dir.path}/$safe');
    await file.writeAsBytes(bytes, flush: true);
    await Share.shareXFiles(
      [XFile(file.path, mimeType: 'application/pdf')],
      subject: subject,
      text: subject,
    );
  } catch (e) {
    if (!isMounted()) return;
    showApiErrorSnackBar(context, e, authenticatedContext: true);
  } finally {
    setBusy?.call(false);
  }
}

class ReportFilterChip extends StatelessWidget {
  const ReportFilterChip({
    super.key,
    required this.label,
    required this.onTap,
  });

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(label, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
      onPressed: onTap,
      backgroundColor: const Color(0xFFF0F2FA),
      side: const BorderSide(color: Color(0xFFE0E4F0)),
    );
  }
}

class ReportSectionHeader extends StatelessWidget {
  const ReportSectionHeader(this.title, {super.key, this.trailing});

  final String title;
  final String? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 14, 4, 6),
      child: Row(
        children: [
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w800,
                color: Color(0xFF3D4477),
                letterSpacing: 0.2,
              ),
            ),
          ),
          if (trailing != null)
            Text(
              trailing!,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: Color(0xFF262C50)),
            ),
        ],
      ),
    );
  }
}

class ReportAmountRow extends StatelessWidget {
  const ReportAmountRow({
    super.key,
    required this.label,
    required this.amount,
    this.code = '',
    this.indent = 0,
    this.bold = false,
    this.muted = false,
  });

  final String label;
  final double amount;
  final String code;
  final int indent;
  final bool bold;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(
      fontSize: bold ? 13.5 : 13,
      fontWeight: bold ? FontWeight.w800 : FontWeight.w500,
      color: muted ? const Color(0xFF78909C) : const Color(0xFF262C50),
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(4.0 + indent * 12, 5, 4, 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Text(
              code.isNotEmpty ? '$code  $label' : label,
              style: style,
            ),
          ),
          const SizedBox(width: 8),
          Text(fmtMoney(amount), style: style.copyWith(fontFeatures: const [])),
        ],
      ),
    );
  }
}
