import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Numeric [TextField] that reliably opens the soft keyboard (no custom onTap).
class NumericTextField extends StatefulWidget {
  const NumericTextField({
    super.key,
    required this.controller,
    this.autofocus = false,
    this.decoration,
    this.labelText,
    this.hintText,
    this.helperText,
    this.onChanged,
    this.textInputAction,
    this.selectAllOnFocus = false,
    this.signed = false,
    this.maxDecimalPlaces = 2,
    this.textAlign = TextAlign.start,
  });

  final TextEditingController controller;
  final bool autofocus;
  final InputDecoration? decoration;
  final String? labelText;
  final String? hintText;
  final String? helperText;
  final ValueChanged<String>? onChanged;
  final TextInputAction? textInputAction;
  final bool selectAllOnFocus;
  final bool signed;
  final int maxDecimalPlaces;
  final TextAlign textAlign;

  @override
  State<NumericTextField> createState() => _NumericTextFieldState();
}

class _NumericTextFieldState extends State<NumericTextField> {
  late final FocusNode _focusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    if (widget.autofocus) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _requestKeyboard());
    }
    _focusNode.addListener(_handleFocus);
  }

  @override
  void dispose() {
    _focusNode.removeListener(_handleFocus);
    _focusNode.dispose();
    super.dispose();
  }

  void _handleFocus() {
    if (!_focusNode.hasFocus || !widget.selectAllOnFocus) return;
    final text = widget.controller.text;
    if (text.isEmpty) return;
    widget.controller.selection = TextSelection(baseOffset: 0, extentOffset: text.length);
  }

  void _requestKeyboard() {
    if (!mounted) return;
    _focusNode.requestFocus();
  }

  InputDecoration get _decoration {
    final base = widget.decoration ?? const InputDecoration();
    return base.copyWith(
      labelText: widget.labelText ?? base.labelText,
      hintText: widget.hintText ?? base.hintText,
      helperText: widget.helperText ?? base.helperText,
    );
  }

  RegExp get _inputPattern {
    if (widget.signed) {
      return RegExp(r'^-?\d*\.?\d*');
    }
    if (widget.maxDecimalPlaces <= 0) {
      return RegExp(r'^\d*');
    }
    return RegExp(r'^\d*\.?\d{0,' '${widget.maxDecimalPlaces}' r'}');
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: widget.controller,
      focusNode: _focusNode,
      autofocus: widget.autofocus,
      textAlign: widget.textAlign,
      keyboardType: TextInputType.numberWithOptions(
        decimal: widget.maxDecimalPlaces > 0,
        signed: widget.signed,
      ),
      textInputAction: widget.textInputAction,
      inputFormatters: [FilteringTextInputFormatter.allow(_inputPattern)],
      decoration: _decoration,
      onChanged: widget.onChanged,
    );
  }
}
