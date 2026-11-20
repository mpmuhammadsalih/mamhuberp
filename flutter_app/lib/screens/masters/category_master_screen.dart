import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/category_brand_master_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_indicator.dart';
import '../../core/theme/app_theme.dart';

/// ERP Category Master — expandable Main → Category → Micro tree.
class CategoryMasterScreen extends StatefulWidget {
  const CategoryMasterScreen({super.key});

  @override
  State<CategoryMasterScreen> createState() => _CategoryMasterScreenState();
}

class _CategoryMasterScreenState extends State<CategoryMasterScreen> {
  static const _accent = Color(0xFF00897B);
  static const _navy = Color(0xFF262C50);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<CategoryMasterRow> _tree = [];
  int _rowCount = 0;
  final Set<String> _expanded = {};
  bool _didInitialExpand = false;

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

  Iterable<String> _allExpandableKeys(List<CategoryMasterRow> nodes) sync* {
    for (final n in nodes) {
      if (n.hasChildren) {
        yield n.nodeKey;
        yield* _allExpandableKeys(n.children);
      }
    }
  }

  Set<String> _keysMatchingSearch(List<CategoryMasterRow> nodes, String q) {
    final out = <String>{};
    if (q.isEmpty) return out;

    bool walk(CategoryMasterRow n) {
      final selfMatch =
          n.name.toUpperCase().contains(q) || '${n.code}'.contains(q) || n.levelName.toUpperCase().contains(q);
      var childMatch = false;
      for (final c in n.children) {
        if (walk(c)) childMatch = true;
      }
      if (childMatch && n.hasChildren) out.add(n.nodeKey);
      return selfMatch || childMatch;
    }

    for (final n in nodes) {
      walk(n);
    }
    return out;
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final q = _search.text.trim();
      final payload = await context.read<CategoryBrandMasterService>().listCategories(q: q);
      if (!mounted) return;
      final tree = payload.tree;
      setState(() {
        _tree = tree;
        _rowCount = payload.rows.isNotEmpty
            ? payload.rows.length
            : _countNodes(tree);
        _loading = false;
        if (q.isNotEmpty) {
          _expanded
            ..clear()
            ..addAll(_keysMatchingSearch(tree, q.toUpperCase()));
        } else if (!_didInitialExpand) {
          // First open: expand mains so Category/Micro rows are visible.
          _didInitialExpand = true;
          _expanded
            ..clear()
            ..addAll(_allExpandableKeys(tree));
        } else {
          // Keep existing expanded keys that still exist.
          final valid = _allExpandableKeys(tree).toSet();
          _expanded.removeWhere((k) => !valid.contains(k));
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _tree = [];
        _loading = false;
      });
    }
  }

  void _showAll() {
    setState(() {
      _expanded
        ..clear()
        ..addAll(_allExpandableKeys(_tree));
    });
  }

  void _showTop() {
    setState(_expanded.clear);
  }

  Future<String?> _promptName({
    required String title,
    String initial = '',
  }) {
    return showDialog<String>(
      context: context,
      builder: (ctx) => _NamePromptDialog(title: title, initial: initial),
    );
  }

  int _countNodes(List<CategoryMasterRow> nodes) {
    var n = 0;
    for (final node in nodes) {
      n += 1 + _countNodes(node.children);
    }
    return n;
  }

  Future<void> _createMain() async {
    final name = await _promptName(title: 'New Main Category');
    if (name == null || name.isEmpty || !mounted) return;
    await _mutate(() => context.read<CategoryBrandMasterService>().createCategory(flag: 'M', name: name));
  }

  Future<void> _createChild(CategoryMasterRow parent) async {
    if (parent.code <= 0) return;
    if (parent.flag == 'M') {
      final name = await _promptName(title: 'New Category under ${parent.name}');
      if (name == null || name.isEmpty || !mounted) return;
      await _mutate(
        () => context.read<CategoryBrandMasterService>().createCategory(
              flag: 'D',
              name: name,
              mainCode: parent.code,
            ),
      );
      setState(() => _expanded.add(parent.nodeKey));
    } else if (parent.flag == 'D') {
      final name = await _promptName(title: 'New Micro under ${parent.name}');
      if (name == null || name.isEmpty || !mounted) return;
      await _mutate(
        () => context.read<CategoryBrandMasterService>().createCategory(
              flag: 'C',
              name: name,
              dCode: parent.code,
              mainCode: parent.parentMainCode,
            ),
      );
      setState(() => _expanded.add(parent.nodeKey));
    }
  }

  Future<void> _edit(CategoryMasterRow row) async {
    if (row.code <= 0) return;
    final name = await _promptName(title: 'Edit ${row.levelName}', initial: row.name);
    if (name == null || name.isEmpty || !mounted) return;
    await _mutate(
      () => context.read<CategoryBrandMasterService>().updateCategory(
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

  Color _flagColor(String flag) {
    switch (flag) {
      case 'M':
        return const Color(0xFF1565C0);
      case 'D':
        return const Color(0xFF00897B);
      default:
        return const Color(0xFF6A1B9A);
    }
  }

  Widget _nodeTile(CategoryMasterRow node) {
    final color = _flagColor(node.flag);
    final canExpand = node.hasChildren;
    final isOpen = _expanded.contains(node.nodeKey);

    return Padding(
      padding: EdgeInsets.only(left: node.level * 14.0, bottom: 6),
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: canExpand
              ? () {
                  setState(() {
                    if (isOpen) {
                      _expanded.remove(node.nodeKey);
                    } else {
                      _expanded.add(node.nodeKey);
                    }
                  });
                }
              : (node.code > 0 ? () => _edit(node) : null),
          onLongPress: node.code > 0 ? () => _edit(node) : null,
          child: Container(
            padding: const EdgeInsets.fromLTRB(8, 8, 4, 8),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: Column(
              children: [
                Row(
                  children: [
                    SizedBox(
                      width: 32,
                      child: canExpand
                          ? Icon(
                              isOpen ? Icons.expand_more_rounded : Icons.chevron_right_rounded,
                              color: color,
                            )
                          : Icon(Icons.circle, size: 8, color: color.withValues(alpha: 0.55)),
                    ),
                    Container(
                      width: 28,
                      height: 28,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        node.flag,
                        style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12, color: color),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            node.code > 0
                                ? (node.name.isEmpty ? '${node.code}' : '${node.code} — ${node.name}')
                                : (node.name.isEmpty ? '—' : node.name),
                            style: const TextStyle(fontWeight: FontWeight.w800, color: _navy, fontSize: 13.5),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${node.levelName}'
                            '${canExpand ? ' · ${node.children.length} child${node.children.length == 1 ? '' : 'ren'}' : ''}',
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          ),
                        ],
                      ),
                    ),
                    if ((node.flag == 'M' || node.flag == 'D') && node.code > 0)
                      IconButton(
                        tooltip: node.flag == 'M' ? 'Add category' : 'Add micro',
                        onPressed: () => _createChild(node),
                        icon: Icon(Icons.add_circle_outline, color: color),
                      ),
                    if (node.code > 0)
                      IconButton(
                        tooltip: 'Edit',
                        onPressed: () => _edit(node),
                        icon: Icon(Icons.edit_outlined, color: Colors.grey.shade600, size: 20),
                      ),
                  ],
                ),
                if (canExpand && isOpen)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Column(
                      children: [
                        for (final child in node.children) _nodeTile(child),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
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
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Category Master', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
            if (!_loading && _rowCount > 0)
              Text(
                '$_rowCount rows · Main → Category → Micro',
                style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600, fontWeight: FontWeight.w500),
              ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'New Main',
            onPressed: _loading ? null : _createMain,
            icon: const Icon(Icons.add_rounded),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _loading ? null : _createMain,
        backgroundColor: _accent,
        icon: const Icon(Icons.add),
        label: const Text('Main'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
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
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _tree.isEmpty ? null : _showAll,
                    icon: const Icon(Icons.unfold_more_rounded, size: 18),
                    label: const Text('Show all'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: _navy,
                      side: const BorderSide(color: Color(0xFFD5DAE8)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _tree.isEmpty ? null : _showTop,
                    icon: const Icon(Icons.unfold_less_rounded, size: 18),
                    label: const Text('Top'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: _navy,
                      side: const BorderSide(color: Color(0xFFD5DAE8)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (_error != null)
            ApiErrorBanner(
              message: _error!,
              error: _errorCause,
            ),
          Expanded(
            child: _loading && _tree.isEmpty
                ? const AppLoadingIndicator()
                : RefreshIndicator(
                    color: _accent,
                    onRefresh: _reload,
                    child: _tree.isEmpty
                        ? ListView(
                            children: const [
                              SizedBox(height: 80),
                              Center(child: Text('No categories found.')),
                            ],
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.fromLTRB(12, 0, 12, 88),
                            itemCount: _tree.length,
                            itemBuilder: (context, i) => _nodeTile(_tree[i]),
                          ),
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
        decoration: const InputDecoration(
          labelText: 'Name',
          hintText: 'Enter name',
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _submit, child: const Text('Save')),
      ],
    );
  }
}
