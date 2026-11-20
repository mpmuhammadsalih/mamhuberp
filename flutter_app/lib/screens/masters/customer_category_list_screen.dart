import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/customer_master_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../core/theme/app_theme.dart';

/// ERP customer categories (TBLCUSTOMERCATEGORY) — list + add.
class CustomerCategoryListScreen extends StatefulWidget {
  const CustomerCategoryListScreen({super.key});

  @override
  State<CustomerCategoryListScreen> createState() => _CustomerCategoryListScreenState();
}

class _CustomerCategoryListScreenState extends State<CustomerCategoryListScreen> {
  static const _accent = Color(0xFFEF6C00);
  static const _navy = Color(0xFF262C50);

  final _search = TextEditingController();
  Timer? _debounce;
  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<CustomerCategoryOption> _rows = [];

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
      final rows = await context.read<CustomerMasterService>().listCategories(
            q: _search.text.trim(),
          );
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

  Future<void> _openNew() async {
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => const _CategoryNameDialog(),
    );
    if (name == null || name.isEmpty || !mounted) return;
    try {
      await context.read<CustomerMasterService>().createCategory(name: name);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Customer category created.'), behavior: SnackBarBehavior.floating),
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
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('Customer Category', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNew,
        backgroundColor: _accent,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Add Category'),
      ),
      body: Column(
        children: [
          Material(
            color: Colors.white,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
              child: TextField(
                controller: _search,
                decoration: InputDecoration(
                  hintText: 'Search code or name',
                  prefixIcon: const Icon(Icons.search_rounded),
                  filled: true,
                  fillColor: const Color(0xFFF6F7FC),
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.grey.shade200),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.grey.shade200),
                  ),
                ),
                onChanged: (_) => _scheduleSearch(),
                onSubmitted: (_) => _reload(),
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
                ? const Center(child: CircularProgressIndicator(color: _accent))
                : RefreshIndicator(
                    color: _accent,
                    onRefresh: _reload,
                    child: _rows.isEmpty
                        ? ListView(
                            children: [
                              const SizedBox(height: 80),
                              Icon(Icons.category_outlined, size: 48, color: Colors.grey.shade400),
                              const SizedBox(height: 12),
                              Center(
                                child: Text(
                                  _search.text.trim().isEmpty
                                      ? 'No customer categories yet.'
                                      : 'No categories match your search.',
                                  style: TextStyle(color: Colors.grey.shade600),
                                ),
                              ),
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
                                  child: Container(
                                    padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(12),
                                      border: Border.all(color: const Color(0xFFE8EBF3)),
                                    ),
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 40,
                                          height: 40,
                                          alignment: Alignment.center,
                                          decoration: BoxDecoration(
                                            color: const Color(0xFFFFF3E0),
                                            borderRadius: BorderRadius.circular(10),
                                          ),
                                          child: Text(
                                            row.code,
                                            style: const TextStyle(
                                              fontWeight: FontWeight.w800,
                                              fontSize: 12,
                                              color: _accent,
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        Expanded(
                                          child: Text(
                                            row.name.isNotEmpty ? row.name : 'Category ${row.code}',
                                            style: const TextStyle(
                                              fontWeight: FontWeight.w700,
                                              fontSize: 15,
                                              color: _navy,
                                            ),
                                          ),
                                        ),
                                      ],
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

class _CategoryNameDialog extends StatefulWidget {
  const _CategoryNameDialog();

  @override
  State<_CategoryNameDialog> createState() => _CategoryNameDialogState();
}

class _CategoryNameDialogState extends State<_CategoryNameDialog> {
  late final TextEditingController _name;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController();
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add customer category'),
      content: TextField(
        controller: _name,
        autofocus: true,
        textCapitalization: TextCapitalization.words,
        decoration: const InputDecoration(
          hintText: 'Category name',
          border: OutlineInputBorder(),
        ),
        onSubmitted: (v) {
          final t = v.trim();
          if (t.isNotEmpty) Navigator.of(context).pop(t);
        },
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            final t = _name.text.trim();
            if (t.isEmpty) return;
            Navigator.of(context).pop(t);
          },
          child: const Text('Save'),
        ),
      ],
    );
  }
}
