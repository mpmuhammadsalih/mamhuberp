import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/unit_master_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_indicator.dart';
import '../../core/theme/app_theme.dart';

/// ERP Unit of measurement — UNITOFMEASUREMENT (code + name).
class UnitMasterScreen extends StatefulWidget {
  const UnitMasterScreen({super.key});

  @override
  State<UnitMasterScreen> createState() => _UnitMasterScreenState();
}

class _UnitMasterScreenState extends State<UnitMasterScreen> {
  static const _accent = Color(0xFF455A64);
  static const _navy = Color(0xFF262C50);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<UnitMasterRow> _rows = [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _scheduleSearch() {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), _reload);
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final rows = await context.read<UnitMasterService>().listUnits(q: _search.text.trim());
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _loading = false;
      });
    }
  }

  Future<void> _create() async {
    final result = await showDialog<_UnitFormResult>(
      context: context,
      builder: (ctx) => const _UnitFormDialog(title: 'New unit'),
    );
    if (result == null || !mounted) return;
    await _mutate(
      () => context.read<UnitMasterService>().createUnit(code: result.code, name: result.name),
    );
  }

  Future<void> _edit(UnitMasterRow row) async {
    final result = await showDialog<_UnitFormResult>(
      context: context,
      builder: (ctx) => _UnitFormDialog(
        title: 'Edit unit',
        initialCode: row.code,
        initialName: row.name,
        codeLocked: true,
      ),
    );
    if (result == null || !mounted) return;
    await _mutate(
      () => context.read<UnitMasterService>().updateUnit(code: row.code, name: result.name),
    );
  }

  Future<void> _delete(UnitMasterRow row) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete unit?'),
        content: Text(
          'Delete ${row.code}${row.name.isNotEmpty ? ' — ${row.name}' : ''}?\n'
          'Blocked if any item uses it as base UOM.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    await _mutate(() => context.read<UnitMasterService>().deleteUnit(code: row.code));
  }

  Future<void> _mutate(Future<Map<String, dynamic>> Function() op) async {
    try {
      await op();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Saved'), behavior: SnackBarBehavior.floating),
      );
      await _reload();
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Unit of measurement', style: TextStyle(fontWeight: FontWeight.w800)),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _loading ? null : _create,
        backgroundColor: _accent,
        icon: const Icon(Icons.add),
        label: const Text('Unit'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: TextField(
              controller: _search,
              onChanged: (_) => _scheduleSearch(),
              decoration: InputDecoration(
                hintText: 'Search code / name…',
                prefixIcon: const Icon(Icons.search_rounded, size: 20),
                isDense: true,
                filled: true,
                fillColor: Colors.white,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFFE4E7F0)),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFFE4E7F0)),
                ),
              ),
            ),
          ),
          if (_error != null)
            ApiErrorBanner(
              message: _error!,
              error: _errorCause,
            ),
          Expanded(
            child: _loading && _rows.isEmpty
                ? const AppLoadingIndicator()
                : RefreshIndicator(
                    color: _accent,
                    onRefresh: _reload,
                    child: _rows.isEmpty
                        ? ListView(
                            children: const [
                              SizedBox(height: 80),
                              Center(child: Text('No units found.')),
                            ],
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.fromLTRB(12, 8, 12, 88),
                            itemCount: _rows.length,
                            itemBuilder: (context, i) {
                              final row = _rows[i];
                              return Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Material(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(12),
                                  child: InkWell(
                                    borderRadius: BorderRadius.circular(12),
                                    onTap: () => _edit(row),
                                    onLongPress: () => _delete(row),
                                    child: Container(
                                      padding: const EdgeInsets.fromLTRB(14, 12, 4, 12),
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(12),
                                        border: Border.all(color: const Color(0xFFE8EBF3)),
                                      ),
                                      child: Row(
                                        children: [
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  row.code,
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w800,
                                                    color: _navy,
                                                    fontSize: 14,
                                                  ),
                                                ),
                                                if (row.name.isNotEmpty) ...[
                                                  const SizedBox(height: 2),
                                                  Text(
                                                    row.name,
                                                    style: TextStyle(
                                                      fontSize: 12.5,
                                                      color: Colors.grey.shade600,
                                                    ),
                                                  ),
                                                ],
                                              ],
                                            ),
                                          ),
                                          IconButton(
                                            onPressed: () => _edit(row),
                                            icon: Icon(Icons.edit_outlined, color: Colors.grey.shade600),
                                          ),
                                          IconButton(
                                            onPressed: () => _delete(row),
                                            icon: Icon(Icons.delete_outline, color: Colors.grey.shade500),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _UnitFormResult {
  const _UnitFormResult({required this.code, required this.name});
  final String code;
  final String name;
}

class _UnitFormDialog extends StatefulWidget {
  const _UnitFormDialog({
    required this.title,
    this.initialCode = '',
    this.initialName = '',
    this.codeLocked = false,
  });

  final String title;
  final String initialCode;
  final String initialName;
  final bool codeLocked;

  @override
  State<_UnitFormDialog> createState() => _UnitFormDialogState();
}

class _UnitFormDialogState extends State<_UnitFormDialog> {
  late final TextEditingController _code;
  late final TextEditingController _name;

  @override
  void initState() {
    super.initState();
    _code = TextEditingController(text: widget.initialCode);
    _name = TextEditingController(text: widget.initialName);
  }

  @override
  void dispose() {
    _code.dispose();
    _name.dispose();
    super.dispose();
  }

  void _submit() {
    final code = _code.text.trim().toUpperCase();
    final name = _name.text.trim();
    if (code.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unit code is required')),
      );
      return;
    }
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unit name is required')),
      );
      return;
    }
    Navigator.pop(context, _UnitFormResult(code: code, name: name));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _code,
            autofocus: !widget.codeLocked,
            enabled: !widget.codeLocked,
            textCapitalization: TextCapitalization.characters,
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[A-Za-z0-9_\-]')),
              LengthLimitingTextInputFormatter(30),
              _UpperCaseTextFormatter(),
            ],
            decoration: const InputDecoration(
              labelText: 'Unit code',
              hintText: 'e.g. PCS',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _name,
            autofocus: widget.codeLocked,
            maxLength: 200,
            decoration: const InputDecoration(labelText: 'Unit name'),
            onSubmitted: (_) => _submit(),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _submit, child: const Text('Save')),
      ],
    );
  }
}

class _UpperCaseTextFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    return TextEditingValue(
      text: newValue.text.toUpperCase(),
      selection: newValue.selection,
    );
  }
}
