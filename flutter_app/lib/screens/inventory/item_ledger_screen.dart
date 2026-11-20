import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/item_master_service.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_indicator.dart';
import '../barcode_scanner_screen.dart';
import '../../core/theme/app_theme.dart';

/// ERP Item Master → Ledger (document tabs, not ITEMJOURNAL stock ledger).
class ItemLedgerScreen extends StatefulWidget {
  const ItemLedgerScreen({super.key, this.initialItemCode, this.initialItemName = ''});

  final int? initialItemCode;
  final String initialItemName;

  @override
  State<ItemLedgerScreen> createState() => _ItemLedgerScreenState();
}

class _ItemLedgerScreenState extends State<ItemLedgerScreen> with SingleTickerProviderStateMixin {
  static const _accent = Color(0xFF00838F);
  static const _navy = Color(0xFF262C50);

  static const _tabs = <({String key, String label})>[
    (key: 'journal', label: 'Journal'),
    (key: 'purchase', label: 'Purchase'),
    (key: 'purchase_return', label: 'PR'),
    (key: 'sale', label: 'Sale'),
    (key: 'sale_return', label: 'Sale ret.'),
    (key: 'stock_adjustment', label: 'Stk adj'),
  ];

  late final TabController _tabCtrl;
  final _search = TextEditingController();
  final _searchFocus = FocusNode();
  Timer? _debounce;

  int? _itemCode;
  String _itemName = '';
  String _barcode = '';
  String _journalRange = '';
  bool _loading = false;
  bool _picking = false;
  String? _error;
  Object? _errorCause;
  String? _pickError;
  List<ItemLedgerRow> _rows = [];
  List<ItemJournalRow> _journalRows = [];
  List<ItemMasterRow> _pickRows = [];

  bool get _isJournalTab => _activeTab == 'journal';

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: _tabs.length, vsync: this);
    _tabCtrl.addListener(_onTabChanged);
    final ic = widget.initialItemCode ?? 0;
    if (ic > 0) {
      _itemCode = ic;
      _itemName = widget.initialItemName;
      WidgetsBinding.instance.addPostFrameCallback((_) => _loadLedger());
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _searchItems('');
        _searchFocus.requestFocus();
      });
    }
  }

  void _onTabChanged() {
    if (_tabCtrl.indexIsChanging) return;
    if (_itemCode != null && _itemCode! > 0) _loadLedger();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _tabCtrl.removeListener(_onTabChanged);
    _search.dispose();
    _searchFocus.dispose();
    _tabCtrl.dispose();
    super.dispose();
  }

  String get _activeTab => _tabs[_tabCtrl.index].key;

  String get _partyLabel {
    switch (_activeTab) {
      case 'stock_adjustment':
        return 'Warehouse';
      case 'sale':
      case 'sale_return':
        return 'Customer';
      default:
        return 'Supplier';
    }
  }

  Future<void> _loadLedger() async {
    final code = _itemCode ?? 0;
    if (code <= 0) return;
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
      _pickRows = [];
      _pickError = null;
    });
    try {
      final svc = context.read<ItemMasterService>();
      if (_isJournalTab) {
        final data = await svc.getItemJournal(itemCode: code);
        if (!mounted) return;
        setState(() {
          _itemCode = data.itemCode;
          if (data.itemName.isNotEmpty) _itemName = data.itemName;
          if (data.barcode.isNotEmpty) _barcode = data.barcode;
          _journalRows = data.rows;
          _rows = [];
          _journalRange = [
            if (data.dateFrom.isNotEmpty) data.dateFrom,
            if (data.dateTo.isNotEmpty) data.dateTo,
          ].join(' → ');
          _loading = false;
        });
        return;
      }
      final data = await svc.getItemLedger(itemCode: code, tab: _activeTab);
      if (!mounted) return;
      setState(() {
        _itemCode = data.itemCode;
        if (data.itemName.isNotEmpty) _itemName = data.itemName;
        _barcode = data.barcode;
        _rows = data.rows;
        _journalRows = [];
        _journalRange = '';
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCause = e;
        _error = handleApiError(context, e, authenticatedContext: true);
        _rows = [];
        _journalRows = [];
        _loading = false;
      });
    }
  }

  Future<void> _resolveAndLoad(String raw) async {
    final q = raw.trim();
    if (q.isEmpty) return;
    final asCode = int.tryParse(q);
    if (asCode != null && asCode > 0) {
      setState(() {
        _itemCode = asCode;
        _itemName = '';
        _barcode = '';
        _pickRows = [];
      });
      await _loadLedger();
      return;
    }
    // Try barcode / manufacturer id
    setState(() {
      _loading = true;
      _error = null;
      _pickRows = [];
    });
    try {
      final svc = context.read<ItemMasterService>();
      if (_isJournalTab) {
        final data = await svc.getItemJournal(barcode: q);
        if (!mounted) return;
        setState(() {
          _itemCode = data.itemCode;
          _itemName = data.itemName;
          _barcode = data.barcode.isNotEmpty ? data.barcode : q;
          _journalRows = data.rows;
          _rows = [];
          _journalRange = [
            if (data.dateFrom.isNotEmpty) data.dateFrom,
            if (data.dateTo.isNotEmpty) data.dateTo,
          ].join(' → ');
          _loading = false;
        });
        return;
      }
      final data = await svc.getItemLedger(barcode: q, tab: _activeTab);
      if (!mounted) return;
      setState(() {
        _itemCode = data.itemCode;
        _itemName = data.itemName;
        _barcode = data.barcode.isNotEmpty ? data.barcode : q;
        _rows = data.rows;
        _journalRows = [];
        _loading = false;
      });
    } catch (_) {
      // Fall back to item search and auto-pick first match
      try {
        final rows = await context.read<ItemMasterService>().listItems(q: q, limit: 20);
        if (!mounted) return;
        if (rows.isEmpty) {
          setState(() {
            _loading = false;
            _error = 'No item found for "$q"';
            _pickRows = [];
          });
          return;
        }
        if (rows.length == 1) {
          _selectItem(rows.first);
          return;
        }
        setState(() {
          _loading = false;
          _pickRows = rows;
          _pickError = null;
        });
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _loading = false;
          _errorCause = e;
          _error = handleApiError(context, e, authenticatedContext: true);
        });
      }
    }
  }

  Future<void> _scanBarcode() async {
    final code = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const BarcodeScannerScreen()),
    );
    if (code == null || code.trim().isEmpty || !mounted) return;
    _search.text = code.trim();
    await _resolveAndLoad(code.trim());
  }

  void _schedulePick(String q) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () => _searchItems(q.trim()));
  }

  Future<void> _searchItems(String q) async {
    setState(() {
      _picking = true;
      _pickError = null;
    });
    try {
      final rows = await context.read<ItemMasterService>().listItems(q: q, limit: 40);
      if (!mounted) return;
      setState(() {
        _pickRows = rows;
        _picking = false;
        if (rows.isEmpty && q.isNotEmpty) {
          _pickError = 'No items match "$q"';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _pickRows = [];
        _picking = false;
        _pickError = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  void _selectItem(ItemMasterRow item) {
    _search.clear();
    _searchFocus.unfocus();
    setState(() {
      _itemCode = item.itemCode;
      _itemName = item.itemName;
      _barcode = item.barcode;
      _pickRows = [];
      _pickError = null;
    });
    _loadLedger();
  }

  void _clearItem() {
    setState(() {
      _itemCode = null;
      _itemName = '';
      _barcode = '';
      _rows = [];
      _journalRows = [];
      _journalRange = '';
      _error = null;
    });
    _searchItems('');
    _searchFocus.requestFocus();
  }

  String _fmt(double v) {
    if (v == 0) return '0';
    if (v == v.roundToDouble()) return v.toStringAsFixed(0);
    return v.toStringAsFixed(3);
  }

  String _money(double v) => v.toStringAsFixed(2);

  double get _docTotalQty => _rows.fold<double>(0, (s, r) => s + r.qty);

  double get _docTotalAmount => _rows.fold<double>(0, (s, r) => s + r.amount);

  double get _journalQtyIn => _journalRows.fold<double>(0, (s, r) => s + r.qtyIn);

  double get _journalQtyOut => _journalRows.fold<double>(0, (s, r) => s + r.qtyOut);

  double get _journalNetQty {
    var net = 0.0;
    for (final r in _journalRows) {
      if (r.netQty != 0) {
        net += r.netQty;
      } else {
        net += r.qtyIn - r.qtyOut;
      }
    }
    return net;
  }

  Widget _stickyTotalsBar() {
    final hasItem = _itemCode != null && _itemCode! > 0;
    if (!hasItem || _loading) return const SizedBox.shrink();
    if (_isJournalTab && _journalRows.isEmpty) return const SizedBox.shrink();
    if (!_isJournalTab && _rows.isEmpty) return const SizedBox.shrink();

    final lines = <Widget>[];
    if (_isJournalTab) {
      lines.addAll([
        _totalChip('In', _fmt(_journalQtyIn), _accent),
        _totalChip('Out', _fmt(_journalQtyOut), const Color(0xFFC62828)),
        _totalChip('Net', _fmt(_journalNetQty), _navy),
      ]);
    } else {
      lines.addAll([
        _totalChip('Total qty', _fmt(_docTotalQty), _accent),
        _totalChip('Amount', _money(_docTotalAmount), _navy),
        _totalChip('Lines', '${_rows.length}', Colors.grey.shade700),
      ]);
    }

    return Material(
      elevation: 8,
      color: Colors.white,
      child: SafeArea(
        top: false,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: Color(0xFFE4E7F0))),
          ),
          child: Row(
            children: [
              for (var i = 0; i < lines.length; i++) ...[
                if (i > 0) const SizedBox(width: 10),
                Expanded(child: lines[i]),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _totalChip(String label, String value, Color valueColor) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F5F8),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
          const SizedBox(height: 2),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: valueColor),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasItem = _itemCode != null && _itemCode! > 0;
    final header = hasItem
        ? '${_itemCode!}${_itemName.isNotEmpty ? ' — $_itemName' : ''}'
        : 'Select an item below';

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Item ledger', style: TextStyle(fontWeight: FontWeight.w800)),
        actions: [
          if (hasItem)
            IconButton(
              tooltip: 'Change item',
              onPressed: _clearItem,
              icon: const Icon(Icons.close_rounded),
            ),
          IconButton(
            tooltip: 'Scan barcode',
            onPressed: _loading ? null : _scanBarcode,
            icon: const Icon(Icons.qr_code_scanner_rounded),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: TabBar(
            controller: _tabCtrl,
            isScrollable: true,
            labelColor: _accent,
            unselectedLabelColor: Colors.grey.shade600,
            indicatorColor: _accent,
            tabs: [for (final t in _tabs) Tab(text: t.label)],
          ),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
            child: TextField(
              controller: _search,
              focusNode: _searchFocus,
              onChanged: _schedulePick,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'Search item code / name / barcode…',
                prefixIcon: const Icon(Icons.search_rounded, size: 20),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.arrow_forward_rounded),
                  onPressed: () => _resolveAndLoad(_search.text),
                ),
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
              onSubmitted: _resolveAndLoad,
            ),
          ),
          if (_picking) const LinearProgressIndicator(minHeight: 2),
          if (_pickError != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Text(_pickError!, style: const TextStyle(color: Color(0xFFC62828), fontSize: 12.5)),
            ),
          if (!hasItem || _pickRows.isNotEmpty)
            ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.of(context).size.height * (hasItem ? 0.28 : 0.42),
              ),
              child: Material(
                color: Colors.white,
                child: _picking && _pickRows.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    : _pickRows.isEmpty
                        ? Padding(
                            padding: const EdgeInsets.all(20),
                            child: Text(
                              'Type a code/name or tap Scan to pick an item.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.grey.shade600),
                            ),
                          )
                        : ListView.separated(
                            shrinkWrap: true,
                            itemCount: _pickRows.length,
                            separatorBuilder: (_, __) => const Divider(height: 1),
                            itemBuilder: (_, i) {
                              final it = _pickRows[i];
                              return ListTile(
                                dense: true,
                                leading: CircleAvatar(
                                  radius: 16,
                                  backgroundColor: _accent.withValues(alpha: 0.12),
                                  child: Text(
                                    '${it.itemCode}'.length > 4
                                        ? '${it.itemCode}'.substring('${it.itemCode}'.length - 3)
                                        : '${it.itemCode}',
                                    style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w800, color: _accent),
                                  ),
                                ),
                                title: Text(
                                  it.itemName.isNotEmpty ? it.itemName : '${it.itemCode}',
                                  style: const TextStyle(fontWeight: FontWeight.w600),
                                ),
                                subtitle: Text(
                                  [
                                    'Code ${it.itemCode}',
                                    if (it.barcode.isNotEmpty) it.barcode,
                                    if (it.baseUom.isNotEmpty) it.baseUom,
                                  ].join(' · '),
                                ),
                                trailing: const Icon(Icons.chevron_right_rounded),
                                onTap: () => _selectItem(it),
                              );
                            },
                          ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
            child: Text(
              header,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: _navy),
            ),
          ),
          if (_barcode.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 4),
              child: Text('Barcode $_barcode', style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
            ),
          if (_isJournalTab && _journalRange.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 4),
              child: Text(
                'ITEMJOURNAL  ·  $_journalRange',
                style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
              ),
            ),
          if (_error != null) ApiErrorBanner(message: _error!, error: _errorCause),
          Expanded(
            child: !hasItem
                ? const SizedBox.shrink()
                : _loading
                    ? const AppLoadingIndicator()
                    : RefreshIndicator(
                        color: _accent,
                        onRefresh: _loadLedger,
                        child: _isJournalTab
                            ? _buildJournalList()
                            : _buildDocList(),
                      ),
          ),
          _stickyTotalsBar(),
        ],
      ),
    );
  }

  Widget _buildEmpty(String message) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        const SizedBox(height: 60),
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              message,
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade600, height: 1.4),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildJournalList() {
    if (_journalRows.isEmpty) {
      return _buildEmpty(
        'No ITEMJOURNAL movements for this item in the last 2 years.\n'
        'Try Purchase / Sale tabs for document history.',
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      itemCount: _journalRows.length,
      itemBuilder: (context, i) {
        final r = _journalRows[i];
        final doc = [r.sourceDoc, r.sourceNo].where((s) => s.isNotEmpty).join(' · ');
        final qtyLine = (r.qtyIn != 0 || r.qtyOut != 0)
            ? 'In ${_fmt(r.qtyIn)}  ·  Out ${_fmt(r.qtyOut)}'
            : 'Net ${_fmt(r.netQty)}';
        final net = r.netQty != 0 ? r.netQty : (r.qtyIn - r.qtyOut);
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Container(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        r.transtype.isNotEmpty ? r.transtype : 'Movement',
                        style: const TextStyle(fontWeight: FontWeight.w800, color: _navy, fontSize: 14),
                      ),
                    ),
                    Text(
                      [
                        if (r.stockDate.isNotEmpty) r.stockDate,
                        if (r.stockTime.isNotEmpty) r.stockTime,
                      ].join(' '),
                      style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                    ),
                  ],
                ),
                if (doc.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(doc, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700)),
                ],
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '$qtyLine${r.uom.isNotEmpty ? ' ${r.uom}' : ''}',
                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                      ),
                    ),
                    Text(
                      _fmt(net),
                      style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 14,
                        color: net < 0 ? const Color(0xFFC62828) : _accent,
                      ),
                    ),
                  ],
                ),
                if (r.warehouseCode.isNotEmpty || r.rate != 0)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      [
                        if (r.warehouseCode.isNotEmpty) 'WH ${r.warehouseCode}',
                        if (r.rate != 0) 'Rate ${_money(r.rate)}',
                        if (r.amount != 0) 'Amt ${_money(r.amount)}',
                      ].join('  ·  '),
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildDocList() {
    if (_rows.isEmpty) {
      return _buildEmpty(
        'No ${_tabs[_tabCtrl.index].label.toLowerCase()} documents for this item.\n'
        'Try Journal / Sale / PR / Stk adj.',
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      itemCount: _rows.length,
      itemBuilder: (context, i) {
        final r = _rows[i];
        final party = r.partyName.isNotEmpty
            ? r.partyName
            : (r.partyCode.isNotEmpty ? r.partyCode : '—');
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Container(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE8EBF3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        r.docNo.isNotEmpty ? r.docNo : '—',
                        style: const TextStyle(
                          fontWeight: FontWeight.w800,
                          color: _navy,
                          fontSize: 14,
                        ),
                      ),
                    ),
                    Text(
                      r.docDate.isNotEmpty ? r.docDate : '',
                      style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  '$_partyLabel: $party',
                  style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
                ),
                const SizedBox(height: 6),
                Text(
                  'Qty ${_fmt(r.qty)}${r.uom.isNotEmpty ? ' ${r.uom}' : ''}'
                  '  ·  Rate ${_money(r.rate)}'
                  '  ·  Amt ${_money(r.amount)}',
                  style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                ),
                if (r.bonus != 0 || r.discount != 0)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      [
                        if (r.bonus != 0) 'Bonus ${_fmt(r.bonus)}',
                        if (r.discount != 0) 'Disc ${_money(r.discount)}',
                      ].join(' · '),
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
