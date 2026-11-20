import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/category_brand_master_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_indicator.dart';
import '../../core/theme/app_theme.dart';

/// ERP Brand Master — Brand (B) / Shelf (Z) / Color (L).
class BrandMasterScreen extends StatefulWidget {
  const BrandMasterScreen({super.key});

  @override
  State<BrandMasterScreen> createState() => _BrandMasterScreenState();
}

class _BrandMasterScreenState extends State<BrandMasterScreen> with SingleTickerProviderStateMixin {
  static const _accent = Color(0xFF6A1B9A);
  static const _navy = Color(0xFF262C50);

  late final TabController _tabs;
  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<BrandMasterRow> _brands = [];
  List<BrandMasterRow> _shelves = [];
  List<BrandMasterRow> _colors = [];

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    _tabs.dispose();
    super.dispose();
  }

  String get _activeFlag {
    switch (_tabs.index) {
      case 1:
        return 'Z';
      case 2:
        return 'L';
      default:
        return 'B';
    }
  }

  String get _activeLabel {
    switch (_activeFlag) {
      case 'Z':
        return 'Shelf';
      case 'L':
        return 'Color';
      default:
        return 'Brand';
    }
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
      final data = await context.read<CategoryBrandMasterService>().listBrands(
            q: _search.text.trim(),
          );
      if (!mounted) return;
      setState(() {
        _brands = data['brands'] ?? [];
        _shelves = data['shelves'] ?? [];
        _colors = data['colors'] ?? [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _brands = [];
        _shelves = [];
        _colors = [];
        _loading = false;
      });
    }
  }

  Future<String?> _promptName({required String title, String initial = ''}) {
    return showDialog<String>(
      context: context,
      builder: (ctx) => _NamePromptDialog(title: title, initial: initial),
    );
  }

  Future<void> _create() async {
    final name = await _promptName(title: 'New $_activeLabel');
    if (name == null || name.isEmpty || !mounted) return;
    await _mutate(
      () => context.read<CategoryBrandMasterService>().createBrand(flag: _activeFlag, name: name),
    );
  }

  Future<void> _edit(BrandMasterRow row) async {
    final name = await _promptName(title: 'Edit ${row.typeLabel}', initial: row.name);
    if (name == null || name.isEmpty || !mounted) return;
    await _mutate(
      () => context.read<CategoryBrandMasterService>().updateBrand(
            code: row.code,
            flag: row.flag,
            name: name,
          ),
    );
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

  Widget _list(List<BrandMasterRow> rows) {
    if (_loading && rows.isEmpty) return const AppLoadingIndicator();
    if (rows.isEmpty) {
      return ListView(
        children: const [
          SizedBox(height: 80),
          Center(child: Text('No rows found.')),
        ],
      );
    }
    return RefreshIndicator(
      color: _accent,
      onRefresh: _reload,
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 88),
        itemCount: rows.length,
        itemBuilder: (context, i) {
          final row = rows[i];
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Material(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => _edit(row),
                child: Container(
                  padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
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
                              row.code > 0
                                  ? (row.name.isEmpty ? '${row.code}' : '${row.code} — ${row.name}')
                                  : (row.name.isEmpty ? '—' : row.name),
                              style: const TextStyle(fontWeight: FontWeight.w800, color: _navy, fontSize: 14),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              row.typeLabel,
                              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: () => _edit(row),
                        icon: Icon(Icons.edit_outlined, color: Colors.grey.shade600),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
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
        title: const Text('Brand Master', style: TextStyle(fontWeight: FontWeight.w800)),
        bottom: TabBar(
          controller: _tabs,
          labelColor: _accent,
          unselectedLabelColor: Colors.grey.shade600,
          indicatorColor: _accent,
          onTap: (_) => setState(() {}),
          tabs: [
            Tab(text: 'Brand (${_brands.length})'),
            Tab(text: 'Shelf (${_shelves.length})'),
            Tab(text: 'Color (${_colors.length})'),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _loading ? null : _create,
        backgroundColor: _accent,
        icon: const Icon(Icons.add),
        label: Text(_activeLabel),
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
            child: TabBarView(
              controller: _tabs,
              children: [
                _list(_brands),
                _list(_shelves),
                _list(_colors),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _NamePromptDialog extends StatefulWidget {
  const _NamePromptDialog({required this.title, this.initial = ''});

  final String title;
  final String initial;

  @override
  State<_NamePromptDialog> createState() => _NamePromptDialogState();
}

class _NamePromptDialogState extends State<_NamePromptDialog> {
  late final TextEditingController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: widget.initial);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _submit() => Navigator.pop(context, _ctrl.text.trim());

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: TextField(
        controller: _ctrl,
        autofocus: true,
        textCapitalization: TextCapitalization.characters,
        maxLength: 200,
        decoration: const InputDecoration(labelText: 'Name'),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _submit, child: const Text('Save')),
      ],
    );
  }
}
