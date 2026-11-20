import 'package:flutter/material.dart';

/// Invisible field that receives Bluetooth HID barcode scanner input (Zebra, etc.).
///
/// Pair the scanner with the device in Bluetooth settings (keyboard/HID mode).
/// When this field has focus, scans arrive as keystrokes + Enter.
class HardwareBarcodeCapture extends StatelessWidget {
  const HardwareBarcodeCapture({
    super.key,
    required this.focusNode,
    required this.controller,
    required this.onScan,
    this.enabled = true,
  });

  final FocusNode focusNode;
  final TextEditingController controller;
  final ValueChanged<String> onScan;
  final bool enabled;

  void _submit(String raw) {
    final code = raw.trim();
    controller.clear();
    if (code.isEmpty || !enabled) return;
    onScan(code);
  }

  @override
  Widget build(BuildContext context) {
    return Offstage(
      offstage: true,
      child: TextField(
        focusNode: focusNode,
        controller: controller,
        enabled: enabled,
        autofocus: false,
        enableSuggestions: false,
        autocorrect: false,
        enableInteractiveSelection: false,
        showCursor: false,
        keyboardType: TextInputType.visiblePassword,
        textInputAction: TextInputAction.done,
        onSubmitted: _submit,
        onChanged: (value) {
          if (value.contains('\n') || value.contains('\r')) {
            _submit(value.replaceAll(RegExp(r'[\r\n]+'), ''));
          }
        },
        decoration: const InputDecoration(
          border: InputBorder.none,
          isDense: true,
          contentPadding: EdgeInsets.zero,
        ),
        style: const TextStyle(fontSize: 1, height: 1),
      ),
    );
  }
}
