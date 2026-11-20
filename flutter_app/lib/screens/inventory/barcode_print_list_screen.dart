import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../models/barcode_print_list.dart';
import '../../services/barcode_print_list_service.dart';
import '../../widgets/api_error_banner.dart';
import 'barcode_print_list_form_screen.dart';
import '../../core/theme/app_theme.dart';

/// Saved barcode print-list documents (open in ERP Barcode Management by list no.).
class BarcodePrintListScreen extends StatefulWidget {
  const BarcodePrintListScreen({
    super.key,
    this.listType = 'PRODUCT',
  });

  final String listType;

  @override
  State<BarcodePrintListScreen> createState() => _BarcodePrintListScreenState();
}

class _BarcodePrintListScreenState extends State<BarcodePrintListScreen> {
  static const _navy = Color(0xFF262C50);

  bool _loading = true;
  String? _error;
  Object? _errorCause;
  List<BarcodePrintListSummary> _rows = [];

  bool get _isShelf => widget.listType.toUpperCase() == 'SHELF';

  Color get _accent =>
      _isShelf ? const Color(0xFF00897B) : const Color(0xFF0277BD);

  String get _title => _isShelf ? 'Shelf print lists' : 'Product print lists';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final rows = await context.read<BarcodePrintListService>().listDocuments(
            listType: widget.listType,
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
        _loading = false;
      });
    }
  }

  Future<void> _openNew() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => BarcodePrintListFormScreen(listType: widget.listType),
      ),
    );
    if (saved == true && mounted) _load();
  }

  Future<void> _openExisting(BarcodePrintListSummary row) async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => BarcodePrintListFormScreen(
          listType: widget.listType,
          printNo: row.printNo,
        ),
      ),
    );
    if (saved == true && mounted) _load();
  }

  String _dateLabel(String? raw) {
    if (raw == null || raw.isEmpty) return '';
    return raw.length >= 10 ? raw.substring(0, 10) : raw;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(_title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNew,
        backgroundColor: _accent,
        icon: const Icon(Icons.add_rounded),
        label: const Text('New list'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
          children: [
            Text(
              _isShelf
                  ? 'Build a shelf/bin barcode list on mobile, then open the list number in ERP Barcode Management to print.'
                  : 'Scan products into a list, save it, then open that list number in ERP → Barcode Management → Open print list.',
              style: const TextStyle(color: Color(0xFF6B7280), fontSize: 13.5, height: 1.35),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              ApiErrorBanner(message: _error!, error: _errorCause, padding: EdgeInsets.zero),
            ],
            const SizedBox(height: 14),
            if (_loading)
              const Padding(
                padding: EdgeInsets.only(top: 40),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_rows.isEmpty)
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFFE4E7F0)),
                ),
                child: Column(
                  children: [
                    Icon(Icons.playlist_add_rounded, size: 40, color: _accent.withValues(alpha: 0.7)),
                    const SizedBox(height: 10),
                    const Text(
                      'No print lists yet',
                      style: TextStyle(fontWeight: FontWeight.w700, color: _navy),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Tap New list and scan barcodes to create document #1, #2, …',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Color(0xFF6B7280), fontSize: 13),
                    ),
                  ],
                ),
              )
            else
              ..._rows.map((r) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: Material(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(14),
                      onTap: () => _openExisting(r),
                      child: Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFFE4E7F0)),
                        ),
                        child: Row(
                          children: [
                            Container(
                              width: 52,
                              height: 52,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: _accent.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                '#${r.printNo}',
                                style: TextStyle(
                                  color: _accent,
                                  fontWeight: FontWeight.w800,
                                  fontSize: 14,
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    r.remarks.trim().isEmpty
                                        ? 'Print list #${r.printNo}'
                                        : r.remarks.trim(),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      color: _navy,
                                      fontSize: 15,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    [
                                      if (_dateLabel(r.printDate).isNotEmpty) _dateLabel(r.printDate),
                                      '${r.lineCount} lines',
                                      '${r.labelCount} labels',
                                      r.status,
                                    ].join(' · '),
                                    style: const TextStyle(color: Color(0xFF6B7280), fontSize: 12.5),
                                  ),
                                ],
                              ),
                            ),
                            Icon(Icons.chevron_right_rounded, color: _accent.withValues(alpha: 0.6)),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }
}
