import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/storage/transaction_draft_storage.dart';
import '../models/grn_receipt.dart';
import '../providers/auth_provider.dart';
import '../providers/purchase_provider.dart';
import 'inventory/inventory_transaction_draft.dart';
import '../services/grn_resume_storage.dart';
import '../services/purchase_service.dart';
import '../utils/grn_display.dart';
import '../widgets/loading_overlay.dart';
import '../widgets/provider_error_body.dart';
import '../widgets/numeric_text_field.dart';
import '../widgets/transaction_draft_banner.dart';
import '../core/theme/app_theme.dart';

class PurchaseScreen extends StatefulWidget {
  const PurchaseScreen({super.key});

  @override
  State<PurchaseScreen> createState() => _PurchaseScreenState();
}

class _PurchaseScreenState extends State<PurchaseScreen> {
  /// Item-details search (Goods Receiving step 2): distinct tint from neutral grays.
  static const Color _itemDetailsSearchFill = Color(0xFFE8E4FF);
  static const Color _itemDetailsSearchBorder = Color(0xFFD8CFF8);

  /// (API query value, UI tab label).
  static const List<(String, String)> _grnTabs = [
    ('Pending', 'Pending'),
    ('Progressing', 'In progress'),
    ('Completed', 'Completed'),
    ('Cancelled', 'Cancelled'),
    ('All', 'All'),
  ];

  bool _isCreating = false;
  int _step = 0;
  bool _prefillLoading = false;
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _itemDetailsSearchController = TextEditingController();
  String _selectedPoNo = 'PO-000126';
  String _selectedPoDate = 'May 24, 2024';
  String _selectedSupplier = 'Modern Suppliers Ltd.';
  String _selectedBranch = 'Main Warehouse';
  String _poHeaderLocationCode = '';
  String _selectedReceiptDate = 'May 24, 2024';
  /// When non-null, line-item dialogs persist to ERP (`PATCH /purchase/po/.../line`).
  String? _persistPoNo;
  /// Last unfinished wizard (`Continue PO …`); persists with SharedPreferences only.
  String? _resumeReceiptNo;
  final TextEditingController _remarksController = TextEditingController(text: 'Laptop and accessories');
  double _selectedTotalAmount = 12450;

  static const List<_ItemRow> _seedItems = [
    _ItemRow(code: 'ITM-000125', name: 'Dell Laptop 15', unit: 'PCS', orderedQty: 10, receivedQty: 0, bonusBaseUnit: 0, isFocEnabled: false, bonusQty: 0, batchNo: '', expiryDate: '', store: '', bin: '', lineSeq: null),
    _ItemRow(code: 'ITM-000126', name: 'HP Wireless Mouse', unit: 'PCS', orderedQty: 20, receivedQty: 0, bonusBaseUnit: 0, isFocEnabled: false, bonusQty: 0, batchNo: '', expiryDate: '', store: '', bin: '', lineSeq: null),
    _ItemRow(code: 'ITM-000127', name: 'Logitech Keyboard', unit: 'PCS', orderedQty: 15, receivedQty: 0, bonusBaseUnit: 0, isFocEnabled: false, bonusQty: 0, batchNo: '', expiryDate: '', store: '', bin: '', lineSeq: null),
    _ItemRow(code: 'ITM-000128', name: 'USB-C Hub 6 in 1', unit: 'PCS', orderedQty: 8, receivedQty: 0, bonusBaseUnit: 0, isFocEnabled: false, bonusQty: 0, batchNo: '', expiryDate: '', store: '', bin: '', lineSeq: null),
    _ItemRow(code: 'ITM-000129', name: 'Laptop Bag 15.6"', unit: 'PCS', orderedQty: 12, receivedQty: 0, bonusBaseUnit: 0, isFocEnabled: false, bonusQty: 0, batchNo: '', expiryDate: '', store: '', bin: '', lineSeq: null),
  ];
  late List<_ItemRow> _items;

  @override
  void initState() {
    super.initState();
    _items = List<_ItemRow>.from(_seedItems);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PurchaseProvider>().load();
      GrnResumeStorage.peek().then((v) {
        if (!mounted || v == null || v.trim().isEmpty) return;
        setState(() => _resumeReceiptNo = v.trim());
      });
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _itemDetailsSearchController.dispose();
    _remarksController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_isCreating) {
      return SafeArea(child: _buildCreateGrn());
    }
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          onPressed: () {
            final nav = Navigator.maybeOf(context);
            if (nav != null && nav.canPop()) {
              nav.pop();
            }
          },
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
        ),
        title: const Text('Goods Receiving', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(onPressed: () {}, icon: const Icon(Icons.filter_alt_outlined)),
        ],
      ),
      body: _buildGrnList(),
    );
  }

  Widget _buildGrnList() {
    final purchase = context.watch<PurchaseProvider>();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 8),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _searchController,
                  onSubmitted: (value) => context.read<PurchaseProvider>().load(search: value),
                  decoration: InputDecoration(
                    hintText: 'Search PO No, Supplier...',
                    hintStyle: const TextStyle(fontSize: 13),
                    prefixIcon: const Icon(Icons.search, size: 20),
                    filled: true,
                    fillColor: const Color(0xFFF4F5FA),
                    contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                  ),
                ),
              ),
            ],
          ),
        ),
        if ((_resumeReceiptNo ?? '').trim().isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: const Color(0xFFFFF8F0),
                borderRadius: BorderRadius.circular(11),
                border: Border.all(color: const Color(0xFFFFB74D)),
              ),
              child: Row(
                children: [
                  const SizedBox(width: 12),
                  const Icon(Icons.play_circle_fill_rounded, color: Color(0xFFE65100), size: 28),
                  const SizedBox(width: 10),
                  Expanded(
                    child: InkWell(
                      onTap: () async {
                        final rid = _resumeReceiptNo!;
                        await GrnResumeStorage.clear();
                        if (mounted) setState(() => _resumeReceiptNo = null);
                        await _openPoWizard(rid, restoreDraft: true);
                      },
                      borderRadius: BorderRadius.circular(10),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Resume',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Color(0xFF7D8393)),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              formatPoBannerLabel(_resumeReceiptNo!),
                              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Color(0xFF5B3DF5)),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Dismiss',
                    onPressed: () async {
                      await GrnResumeStorage.clear();
                      await _clearGoodsReceivingDraft();
                      if (mounted) setState(() => _resumeReceiptNo = null);
                    },
                    icon: const Icon(Icons.close_rounded, size: 20),
                  ),
                  const SizedBox(width: 8),
                ],
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (var i = 0; i < _grnTabs.length; i++) ...[
                  _StatusTab(
                    _grnTabs[i].$2,
                    purchase.selectedStatus == _grnTabs[i].$1,
                    onTap: () => context.read<PurchaseProvider>().updateStatus(
                          _grnTabs[i].$1,
                          search: _searchController.text,
                        ),
                  ),
                  if (i < _grnTabs.length - 1) const SizedBox(width: 20),
                ],
              ],
            ),
          ),
        ),
        Expanded(
          child: purchase.isLoading && purchase.receipts.isEmpty
              ? const Center(child: CircularProgressIndicator())
              : LoadingOverlay(
                  loading: purchase.isFetchingList,
                  child: _grnListBody(purchase),
                ),
        ),
      ],
    );
  }

  Widget _grnListBody(PurchaseProvider purchase) {
    if (purchase.error != null) {
      return ProviderErrorBody(
        message: purchase.error!,
        errorCause: purchase.errorCause,
        onRetry: () => context.read<PurchaseProvider>().load(search: _searchController.text),
      );
    }
    if (purchase.receipts.isEmpty) {
      return Center(
        child: Text(
          purchase.selectedStatus == 'Progressing'
              ? 'No in-progress POs yet.\nSave line details from a pending PO, or set LRFLAG partial in ERP.'
              : 'No goods receipts found',
          textAlign: TextAlign.center,
          style: const TextStyle(color: Color(0xFF7C8191)),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 94),
      itemBuilder: (context, index) => _GrnCard(
        row: purchase.receipts[index],
        onTap: () => _onReceiptTap(purchase.receipts[index]),
      ),
      separatorBuilder: (_, __) => const SizedBox(height: 9),
      itemCount: purchase.receipts.length,
    );
  }

  Widget _buildCreateGrn() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 6),
          child: Row(
            children: [
              IconButton(
                onPressed: () async {
                  if (_step > 0) {
                    setState(() => _step -= 1);
                  } else {
                    await _exitWizardToGrnList(persistResumeCandidate: true);
                  }
                },
                icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
              ),
              const Expanded(
                child: Text('New Goods Receiving', textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
              ),
              IconButton(onPressed: () {}, icon: const Icon(Icons.tune_rounded)),
              IconButton(onPressed: () {}, icon: const Icon(Icons.more_vert)),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
          child: _StepHeader(currentStep: _step),
        ),
        Expanded(
          child: _prefillLoading
              ? const Center(child: CircularProgressIndicator())
              : _step == 1
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildStepTwoPinned(),
                        Expanded(
                          child: ListView(
                            padding: const EdgeInsets.fromLTRB(14, 0, 14, 88),
                            children: [_buildStepTwoScrollingTable()],
                          ),
                        ),
                      ],
                    )
                  : SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(14, 0, 14, 88),
                      child: _step == 0 ? _buildStepOne() : _buildStepThree(),
                    ),
        ),
        _buildBottomButtons(),
      ],
    );
  }

  Widget _buildStepOne() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 6),
        const Text('Receiving', style: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF5B3DF5))),
        const SizedBox(height: 10),
        _EditableField(
          label: 'Receiving date *',
          value: _selectedReceiptDate,
          hint: 'Pick date',
          readOnly: true,
          trailing: Icons.calendar_today_outlined,
          onTap: () => _pickDate(
            initialText: _selectedReceiptDate,
            onPicked: (value) => setState(() => _selectedReceiptDate = value),
          ),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(child: _InputBox(label: 'PO No. *', value: _selectedPoNo, trailing: Icons.keyboard_arrow_down_rounded)),
            const SizedBox(width: 10),
            Expanded(child: _InputBox(label: 'PO Date', value: _selectedPoDate, trailing: Icons.calendar_today_outlined)),
          ],
        ),
        const SizedBox(height: 10),
        _InputBox(label: 'Supplier *', value: _selectedSupplier, trailing: Icons.keyboard_arrow_down_rounded),
        const SizedBox(height: 10),
        _InputBox(label: 'Branch *', value: _selectedBranch, trailing: Icons.keyboard_arrow_down_rounded),
        const SizedBox(height: 10),
        _EditableField(
          label: 'Remarks',
          controller: _remarksController,
          hint: 'Enter remarks',
          minLines: 2,
          maxLines: 3,
        ),
        const SizedBox(height: 14),
        _SummaryStrip(
          items: [
            ('Total Items', '${_items.length}'),
            ('Total Ordered Qty', '${_items.fold<int>(0, (sum, e) => sum + e.orderedQty)}'),
            ('Total Amount', _selectedTotalAmount.toStringAsFixed(2)),
          ],
        ),
      ],
    );
  }

  List<({int index, _ItemRow row})> _filteredItemDetailEntries() {
    final q = _itemDetailsSearchController.text.trim().toLowerCase();
    if (q.isEmpty) {
      return _items.asMap().entries.map((e) => (index: e.key, row: e.value)).toList();
    }
    final out = <({int index, _ItemRow row})>[];
    for (var i = 0; i < _items.length; i++) {
      final e = _items[i];
      if (e.name.toLowerCase().contains(q) || e.code.toLowerCase().contains(q)) {
        out.add((index: i, row: e));
      }
    }
    return out;
  }

  Widget _buildStepTwoPinned() {
    final totalOrdered = _items.fold<int>(0, (sum, e) => sum + e.orderedQty);
    final totalReceived = _items.fold<int>(0, (sum, e) => sum + e.receivedQty);

    return Material(
      color: Colors.white,
      elevation: 1.5,
      shadowColor: const Color(0x24000000),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 0, 14, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 6),
            const Text('Item Details', style: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF5B3DF5))),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _itemDetailsSearchController,
                    onChanged: (_) => setState(() {}),
                    decoration: InputDecoration(
                      hintText: 'Search item by name or code...',
                      hintStyle: const TextStyle(fontSize: 13),
                      prefixIcon: const Icon(Icons.search, size: 20, color: Color(0xFF5B3DF5)),
                      filled: true,
                      fillColor: _itemDetailsSearchFill,
                      contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: _itemDetailsSearchBorder, width: 1),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: _itemDetailsSearchBorder, width: 1),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: Color(0xFF5B3DF5), width: 1.5),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: () {},
                  style: IconButton.styleFrom(
                    backgroundColor: _itemDetailsSearchFill,
                    foregroundColor: const Color(0xFF5B3DF5),
                    side: const BorderSide(color: _itemDetailsSearchBorder),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  icon: const Icon(Icons.tune_rounded),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _SummaryStrip(
              items: [
                ('Total Item', '${_items.length}'),
                ('Total Ordered Qty', '$totalOrdered'),
                ('Total Received Qty', '$totalReceived'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStepTwoScrollingTable() {
    final filtered = _filteredItemDetailEntries();
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EAF2)),
      ),
      child: Column(
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(10, 10, 10, 8),
            child: Row(
              children: [
                SizedBox(width: 24, child: Text('#', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12))),
                Expanded(flex: 4, child: Text('Item Details', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12))),
                Expanded(child: Text('Ordered Qty', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12))),
                Expanded(child: Text('Received Qty', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12))),
                SizedBox(width: 18),
              ],
            ),
          ),
          if (filtered.isEmpty)
            const Padding(
              padding: EdgeInsets.fromLTRB(10, 0, 10, 16),
              child: Text('No items match your search', style: TextStyle(color: Color(0xFF7C8191), fontSize: 13)),
            )
          else
            ...filtered.asMap().entries.map(
                  (entry) {
                    final displayNo = entry.key + 1;
                    final originalIndex = entry.value.index;
                    final row = entry.value.row;
                    return _ItemTableRow(
                      index: displayNo,
                      item: row,
                      onTapEdit: () => _showReceivedQtyDialog(originalIndex),
                    );
                  },
                )
        ],
      ),
    );
  }

  Widget _buildStepThree() {
    final totalOrdered = _items.fold<int>(0, (sum, e) => sum + e.orderedQty);
    final totalReceived = _items.fold<int>(0, (sum, e) => sum + e.receivedQty);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 6),
        const Text('Review & Confirm', style: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF5B3DF5))),
        const SizedBox(height: 10),
        _ReviewCard(
          title: 'Receiving',
          lines: [
            ('Receiving date', _selectedReceiptDate),
            ('PO No.', _selectedPoNo),
            ('PO Date', _selectedPoDate),
            ('Supplier', _selectedSupplier),
            ('Branch', _selectedBranch),
          ],
        ),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFE8EAF2)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.all(12),
                child: Text('Item Summary', style: TextStyle(fontWeight: FontWeight.w700)),
              ),
              ..._items.asMap().entries.map(
                    (entry) => Padding(
                      padding: const EdgeInsets.fromLTRB(12, 2, 12, 6),
                      child: Row(
                        children: [
                          SizedBox(width: 24, child: Text('${entry.key + 1}', style: const TextStyle(fontSize: 12))),
                          Expanded(flex: 4, child: Text('${entry.value.name} (${entry.value.code})', style: const TextStyle(fontSize: 12))),
                          Expanded(child: Text(entry.value.qtyLabel(entry.value.orderedQty), style: const TextStyle(fontSize: 12))),
                          Expanded(child: Text(entry.value.qtyLabel(entry.value.receivedQty), style: const TextStyle(fontSize: 12))),
                        ],
                      ),
                    ),
                  ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        const Text('Remarks', style: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF4B4F60))),
        const SizedBox(height: 4),
        Text(_remarksController.text, style: const TextStyle(color: Color(0xFF6E7382))),
        const SizedBox(height: 10),
        _SummaryStrip(
          items: [
            ('Total Items', '${_items.length}'),
            ('Total Ordered Qty', '$totalOrdered'),
            ('Total Received Qty', '$totalReceived'),
            ('Total Amount', _selectedTotalAmount.toStringAsFixed(2)),
          ],
        ),
      ],
    );
  }

  Widget _buildBottomButtons() {
    final purchase = context.watch<PurchaseProvider>();
    final isLast = _step == 2;
    final leftLabel = _step == 0 ? 'Cancel' : 'Back';
    final rightLabel = _step == 0 ? 'Next: Receive qty' : (isLast ? 'Submit' : 'Next: Review');

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
      decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: Color(0xFFE7E9F2)))),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton(
              onPressed: () async {
                if (_step == 0) {
                  await _exitWizardToGrnList(persistResumeCandidate: true);
                } else {
                  setState(() => _step -= 1);
                }
              },
              child: Text(leftLabel),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            flex: 2,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: const Color(0xFF5B3DF5)),
              onPressed: purchase.isSubmitting
                  ? null
                  : () async {
                      if (isLast) {
                        final submissionItems = _items
                            .where((e) => e.receivedQty > 0)
                            .map(
                              (e) => {
                                'item_code': e.code,
                                'qty': e.receivedQty,
                                'rate': 1,
                                'unit': e.unit,
                              },
                            )
                            .toList();
                        if (submissionItems.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Set Received Qty greater than 0 for at least one item.')),
                          );
                          return;
                        }
                        final poApi = (_persistPoNo ?? _canonicalReceiptLookupKey(_selectedPoNo)).trim();
                        if (poApi.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('PO number is missing.')),
                          );
                          return;
                        }
                        final ok = await context.read<PurchaseProvider>().finalizeReceiving(
                              poNo: poApi,
                              search: _searchController.text,
                            );
                        if (!mounted) return;
                        if (ok) {
                          await GrnResumeStorage.clear();
                          await _clearGoodsReceivingDraft();
                          if (!mounted) return;
                          setState(() {
                            _isCreating = false;
                            _step = 0;
                            _persistPoNo = null;
                            _resumeReceiptNo = null;
                          });
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Receiving completed — post formal GRN from the GRN menu.')),
                          );
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text(purchase.error ?? 'Unable to finalize receiving')),
                          );
                        }
                        return;
                      }
                      setState(() => _step += 1);
                    },
              icon: Icon(isLast ? Icons.check_circle_outline : Icons.arrow_forward_rounded),
              label: purchase.isSubmitting
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : Text(rightLabel),
            ),
          ),
        ],
      ),
    );
  }

  String _pickFirstNonBlank(List<dynamic> values, {String fallback = ''}) {
    for (final value in values) {
      final text = (value ?? '').toString().trim();
      if (text.isNotEmpty) return text;
    }
    return fallback;
  }

  /// Used when deriving resume key from hand-typed PO display values.
  String _canonicalReceiptLookupKey(String raw) {
    var s = raw.trim();
    final upper = s.toUpperCase();
    if (upper.startsWith('PO-')) {
      s = s.substring(3).trim();
    }
    return s;
  }

  ({String tenantId, String username})? _draftScope() {
    final user = context.read<AuthProvider>().user;
    if (user == null) return null;
    final username = user.username.trim();
    if (username.isEmpty) return null;
    return (tenantId: user.tenantId ?? '', username: username);
  }

  Map<String, dynamic> _encodeItemRow(_ItemRow e) => {
        'code': e.code,
        'name': e.name,
        'unit': e.unit,
        'ordered_qty': e.orderedQty,
        'received_qty': e.receivedQty,
        'bonus_base_unit': e.bonusBaseUnit,
        'is_foc_enabled': e.isFocEnabled,
        'bonus_qty': e.bonusQty,
        'batch_no': e.batchNo,
        'expiry_date': e.expiryDate,
        'store': e.store,
        'bin': e.bin,
        'line_seq': e.lineSeq,
      };

  Future<void> _persistGoodsReceivingDraft() async {
    final scope = _draftScope();
    if (scope == null) return;
    final draft = <String, dynamic>{
      'step': _step,
      'po_no': _selectedPoNo,
      'po_date': _selectedPoDate,
      'supplier': _selectedSupplier,
      'branch': _selectedBranch,
      'remarks': _remarksController.text,
      'persist_po_no': _persistPoNo,
      'items': _items.map(_encodeItemRow).toList(),
    };
    await TransactionDraftStorage.save(
      docType: TransactionDraftType.goodsReceiving,
      tenantId: scope.tenantId,
      username: scope.username,
      draft: draft,
    );
  }

  Future<void> _clearGoodsReceivingDraft() async {
    final scope = _draftScope();
    if (scope == null) return;
    await TransactionDraftStorage.clear(
      docType: TransactionDraftType.goodsReceiving,
      tenantId: scope.tenantId,
      username: scope.username,
    );
  }

  void _applyGoodsReceivingDraft(Map<String, dynamic> draft) {
    final step = InventoryTransactionDraft.intOf(draft['step']);
    if (step >= 0 && step <= 2) {
      _step = step;
    }

    final poNo = '${draft['po_no'] ?? ''}'.trim();
    if (poNo.isNotEmpty) _selectedPoNo = poNo;
    final poDate = '${draft['po_date'] ?? ''}'.trim();
    if (poDate.isNotEmpty) _selectedPoDate = poDate;
    final supplier = '${draft['supplier'] ?? ''}'.trim();
    if (supplier.isNotEmpty) _selectedSupplier = supplier;
    final branch = '${draft['branch'] ?? ''}'.trim();
    if (branch.isNotEmpty) _selectedBranch = branch;

    final persist = draft['persist_po_no'];
    if (persist != null) {
      final p = '$persist'.trim();
      if (p.isNotEmpty) _persistPoNo = p;
    }

    if (draft.containsKey('remarks')) {
      _remarksController.text = '${draft['remarks'] ?? ''}';
    }

    final draftItems = (draft['items'] as List?) ?? const [];
    if (draftItems.isEmpty) return;

    final bySeq = <int, Map<String, dynamic>>{};
    final byCode = <String, Map<String, dynamic>>{};
    for (final raw in draftItems) {
      if (raw is! Map) continue;
      final m = Map<String, dynamic>.from(raw);
      final seq = InventoryTransactionDraft.intOf(m['line_seq']);
      if (seq > 0) bySeq[seq] = m;
      final code = '${m['code'] ?? ''}'.trim();
      if (code.isNotEmpty) byCode[code] = m;
    }

    _items = _items.map((item) {
      Map<String, dynamic>? m;
      if (item.lineSeq != null && bySeq.containsKey(item.lineSeq)) {
        m = bySeq[item.lineSeq!];
      } else {
        m = byCode[item.code];
      }
      if (m == null) return item;
      return item.copyWith(
        receivedQty: InventoryTransactionDraft.intOf(m['received_qty']),
        bonusBaseUnit: InventoryTransactionDraft.numOf(m['bonus_base_unit']),
        isFocEnabled: m['is_foc_enabled'] == true,
        bonusQty: InventoryTransactionDraft.intOf(m['bonus_qty']),
        batchNo: '${m['batch_no'] ?? ''}',
        expiryDate: '${m['expiry_date'] ?? ''}',
        store: '${m['store'] ?? ''}',
        bin: '${m['bin'] ?? ''}',
      );
    }).toList();
  }

  Future<void> _exitWizardToGrnList({bool persistResumeCandidate = false}) async {
    if (persistResumeCandidate && (_persistPoNo != null || _step >= 1)) {
      final candidate = (_persistPoNo ?? _canonicalReceiptLookupKey(_selectedPoNo)).trim();
      if (candidate.isNotEmpty) {
        await GrnResumeStorage.remember(candidate);
        await _persistGoodsReceivingDraft();
        if (mounted) setState(() => _resumeReceiptNo = candidate);
      }
    }
    if (!mounted) return;
    setState(() {
      _isCreating = false;
      _persistPoNo = null;
    });
  }

  Future<void> _openPoWizard(String receiptNoRaw, {GrnReceipt? listRow, bool restoreDraft = false}) async {
    final key = receiptNoRaw.trim();
    if (key.isEmpty) return;

    final preStatus = listRow?.status.toLowerCase();
    if (preStatus != null && preStatus != 'pending' && preStatus != 'progressing') {
      return;
    }

    setState(() {
      _isCreating = true;
      _step = 0;
      _prefillLoading = true;
      _persistPoNo = key;
    });
    try {
      final data = await context.read<PurchaseService>().getGrnDetails(key);
      final stApi = (data['status'] ?? '').toString().toLowerCase();
      if (!mounted) return;
      if (stApi.isNotEmpty && stApi != 'pending' && stApi != 'progressing') {
        setState(() {
          _prefillLoading = false;
          _persistPoNo = null;
          _isCreating = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('This PO cannot be edited here (status $stApi).')),
        );
        return;
      }

      final fetchedItems = ((data['items'] as List<dynamic>? ?? const []))
          .map((e) => Map<String, dynamic>.from(e as Map))
          .map(
            (e) => _ItemRow(
              code: _pickFirstNonBlank([e['item_code']]),
              name: _pickFirstNonBlank([e['item_name'], e['item_code']]),
              unit: (e['unit'] ?? '').toString().trim(),
              orderedQty: (e['qty'] as num?)?.toInt() ?? 0,
              receivedQty: (e['mobile_received_qty'] as num?)?.toInt() ??
                  (e['erp_received_qty'] as num?)?.toInt() ??
                  0,
              bonusBaseUnit:
                  (e['mobile_bonus_base_unit'] as num?)?.toDouble() ?? (e['bonus_base_unit'] as num?)?.toDouble() ?? 0,
              isFocEnabled: e['mobile_foc'] == true,
              bonusQty: (e['mobile_bonus_qty'] as num?)?.toInt() ?? 0,
              batchNo: _pickFirstNonBlank([e['mobile_batch_no'], e['batch_no']]),
              expiryDate: _pickFirstNonBlank([e['mobile_expiry'], e['expiry_date']]),
              store: _pickFirstNonBlank([e['mobile_store'], e['store_code'], e['store']]),
              bin: _pickFirstNonBlank([e['mobile_bin'], e['bin_code'], e['bin']]),
              lineSeq: (e['line_seq'] as num?)?.toInt(),
            ),
          )
          .toList();

      Map<String, dynamic>? draft;
      if (restoreDraft) {
        final scope = _draftScope();
        if (scope != null) {
          draft = await TransactionDraftStorage.read(
            docType: TransactionDraftType.goodsReceiving,
            tenantId: scope.tenantId,
            username: scope.username,
          );
        }
      }

      if (!mounted) return;
      setState(() {
        final row = listRow;
        final poFb = row?.poNo ?? key;
        _selectedPoNo = _pickFirstNonBlank([data['po_no'], if (row != null) row.poNo], fallback: poFb);
        _selectedPoDate = _pickFirstNonBlank([
          data['po_date'],
          data['receipt_date'],
          if (row != null) row.receiptDate,
        ], fallback: row?.receiptDate ?? '');
        _selectedSupplier =
            _pickFirstNonBlank([data['supplier_name'], data['supplier'], if (row != null) row.supplier],
                fallback: row?.supplier ?? '');
        _selectedReceiptDate =
            _pickFirstNonBlank([data['grn_date'], data['receipt_date'], if (row != null) row.receiptDate],
                fallback: row?.receiptDate ?? '');
        _selectedBranch = _pickFirstNonBlank([
          data['location_name'],
          data['LOCATIONCODE'],
          data['location_code'],
        ], fallback: 'Main Branch');
        _remarksController.text =
            _pickFirstNonBlank([data['remarks']], fallback: 'Laptop and accessories');
        _selectedTotalAmount =
            (data['amount'] as num?)?.toDouble() ?? row?.amount ?? _selectedTotalAmount;
        _poHeaderLocationCode = _pickFirstNonBlank([data['LOCATIONCODE'], data['location_code']]);
        _items = fetchedItems.isEmpty ? List<_ItemRow>.from(_seedItems) : fetchedItems;
        _itemDetailsSearchController.clear();
        if (draft != null) {
          _applyGoodsReceivingDraft(draft);
        }
        _prefillLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _prefillLoading = false;
        _persistPoNo = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Unable to load PO details: $e')),
      );
    }
  }

  Future<void> _onReceiptTap(GrnReceipt row) async {
    final pending = (_resumeReceiptNo ?? '').trim();
    if (pending.isNotEmpty) {
      final action = await showPendingDraftAlert(
        context,
        summary: formatPoBannerLabel(pending),
        documentLabel: 'goods receiving',
      );
      if (!mounted) return;
      if (action == PendingDraftAction.cancel) return;
      if (action == PendingDraftAction.continuePending) {
        final rid = pending;
        await GrnResumeStorage.clear();
        if (mounted) setState(() => _resumeReceiptNo = null);
        await _openPoWizard(rid, restoreDraft: true);
        return;
      }
      await GrnResumeStorage.clear();
      final user = context.read<AuthProvider>().user;
      if (user != null) {
        await TransactionDraftStorage.clear(
          docType: TransactionDraftType.goodsReceiving,
          tenantId: user.tenantId ?? '',
          username: user.username,
        );
      }
      if (mounted) setState(() => _resumeReceiptNo = null);
    }
    await _openPoWizard(row.receiptNo, listRow: row);
  }

  Future<void> _showReceivedQtyDialog(int itemIndex) async {
    final item = _items[itemIndex];
    final controller = TextEditingController(
      text: item.receivedQty > 0 ? item.receivedQty.toString() : '',
    );
    final bonusController = TextEditingController(text: item.bonusQty.toString());
    final batchController = TextEditingController(text: item.batchNo);
    final expiryController = TextEditingController(text: item.expiryDate);
    final storeController = TextEditingController(text: item.store);
    final binController = TextEditingController(text: item.bin);
    bool focEnabled = item.isFocEnabled;

    InputDecoration fieldDecoration(String label) => InputDecoration(
          labelText: label,
          filled: true,
          fillColor: const Color(0xFFF6F7FC),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFFE4E7F0)),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: Color(0xFFE4E7F0)),
          ),
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        );

    final result = await showDialog<_ItemRow>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocalState) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
          titlePadding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
          contentPadding: const EdgeInsets.fromLTRB(16, 2, 16, 8),
          actionsPadding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
          title: const Row(
            children: [
              Icon(Icons.edit_note_rounded, color: Color(0xFF5B3DF5)),
              SizedBox(width: 8),
              Text('Update Item', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            ],
          ),
          content: SizedBox(
            width: 430,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF6F7FC),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(item.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 2),
                        Text(item.code, style: const TextStyle(fontSize: 12, color: Color(0xFF6F7482))),
                        const SizedBox(height: 2),
                        Text('Ordered Qty: ${item.orderedQty}', style: const TextStyle(fontSize: 12, color: Color(0xFF6F7482))),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  NumericTextField(
                    controller: controller,
                    autofocus: true,
                    selectAllOnFocus: true,
                    decoration: fieldDecoration('Received Qty'),
                  ),
                  const SizedBox(height: 6),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Enable FOC'),
                    value: focEnabled,
                    onChanged: (value) => setLocalState(() => focEnabled = value),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: bonusController,
                    keyboardType: TextInputType.number,
                    enabled: focEnabled,
                    decoration: fieldDecoration('Bonus Qty'),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: batchController,
                          decoration: fieldDecoration('Batch No'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: expiryController,
                          readOnly: true,
                          decoration: fieldDecoration('Expiry Date').copyWith(
                            suffixIcon: const Icon(Icons.calendar_today_outlined, size: 16),
                          ),
                          onTap: () async {
                            final picked = await showDatePicker(
                              context: context,
                              initialDate: DateTime.now(),
                              firstDate: DateTime(2000),
                              lastDate: DateTime(2100),
                            );
                            if (picked == null) return;
                            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                            expiryController.text = '${months[picked.month - 1]} ${picked.day}, ${picked.year}';
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: storeController,
                          decoration: fieldDecoration('Store'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextField(
                          controller: binController,
                          decoration: fieldDecoration('Bin'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () {
                final parsedReceived = int.tryParse(controller.text.trim()) ?? 0;
                final parsedBonus = int.tryParse(bonusController.text.trim()) ?? 0;
                Navigator.of(context).pop(
                  item.copyWith(
                    receivedQty: parsedReceived,
                    isFocEnabled: focEnabled,
                    bonusQty: focEnabled ? parsedBonus : 0,
                    batchNo: batchController.text.trim(),
                    expiryDate: expiryController.text.trim(),
                    store: storeController.text.trim(),
                    bin: binController.text.trim(),
                  ),
                );
              },
              child: const Text('Update'),
            ),
          ],
        ),
      ),
    );
    if (result == null || !mounted) return;

    final persistPoNo = _persistPoNo;
    final seq = result.lineSeq;
    if (persistPoNo != null) {
      final provider = context.read<PurchaseProvider>();
      final saved = await provider.persistPoLineSnapshot(
        poNo: persistPoNo,
        itemCode: result.code,
        lineSeq: seq,
        receivedQty: result.receivedQty.toDouble(),
        bonusQty: result.bonusQty.toDouble(),
        bonusBaseUnit: result.bonusBaseUnit,
        focEnabled: result.isFocEnabled,
        batchNo: result.batchNo,
        expiryDate: result.expiryDate,
        store: result.store,
        bin: result.bin,
        locationCode:
            _poHeaderLocationCode.trim().isNotEmpty ? _poHeaderLocationCode.trim() : null,
      );
      if (!mounted) return;
      if (!saved) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(provider.error ?? 'Unable to save line item to ERP')),
        );
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Saved — INQUANTITY updated on LPODTL')),
      );
    }

    setState(() {
      _items[itemIndex] = result;
    });
  }

  String _toApiDate(String displayDate) {
    final months = <String, String>{
      'Jan': '01',
      'Feb': '02',
      'Mar': '03',
      'Apr': '04',
      'May': '05',
      'Jun': '06',
      'Jul': '07',
      'Aug': '08',
      'Sep': '09',
      'Oct': '10',
      'Nov': '11',
      'Dec': '12',
    };
    final parts = displayDate.replaceAll(',', '').split(' ').where((e) => e.isNotEmpty).toList();
    if (parts.length == 3 && months.containsKey(parts[0])) {
      return '${parts[2]}-${months[parts[0]]}-${parts[1].padLeft(2, '0')}';
    }
    return '2024-05-24';
  }

  Future<void> _pickDate({
    required String initialText,
    required ValueChanged<String> onPicked,
  }) async {
    DateTime initial = DateTime.now();
    try {
      final parsed = _toApiDate(initialText);
      final parts = parsed.split('-');
      if (parts.length == 3) {
        initial = DateTime(
          int.parse(parts[0]),
          int.parse(parts[1]),
          int.parse(parts[2]),
        );
      }
    } catch (_) {}

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    onPicked('${months[picked.month - 1]} ${picked.day}, ${picked.year}');
  }
}

class _StatusTab extends StatelessWidget {
  const _StatusTab(this.label, this.active, {required this.onTap});
  final String label;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: active ? FontWeight.w700 : FontWeight.w500,
              color: active ? const Color(0xFF5B3DF5) : const Color(0xFF6F7482),
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 28,
            height: 2,
            color: active ? const Color(0xFF5B3DF5) : Colors.transparent,
          ),
        ],
      ),
    );
  }
}

class _GrnCard extends StatelessWidget {
  const _GrnCard({required this.row, required this.onTap});
  final GrnReceipt row;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    Color statusBg;
    Color statusFg;
    Color stripeColor;
    switch (row.status) {
      case 'Completed':
        statusBg = const Color(0xFFE9F9EF);
        statusFg = const Color(0xFF1C9C58);
        stripeColor = const Color(0xFF1BBF6B);
        break;
      case 'Progressing':
        statusBg = const Color(0xFFFFF3E0);
        statusFg = const Color(0xFFE65100);
        stripeColor = const Color(0xFFFF9800);
        break;
      case 'In Progress':
        statusBg = const Color(0xFFEAF0FF);
        statusFg = const Color(0xFF3E63F5);
        stripeColor = const Color(0xFF3E63F5);
        break;
      case 'Draft':
      case 'Pending':
        statusBg = const Color(0xFFFFF5E9);
        statusFg = const Color(0xFFE38A18);
        stripeColor = const Color(0xFFFFA726);
        break;
      case 'Posted':
        statusBg = const Color(0xFFE1F5FE);
        statusFg = const Color(0xFF0277BD);
        stripeColor = const Color(0xFF039BE5);
        break;
      default:
        statusBg = const Color(0xFFF2F2F5);
        statusFg = const Color(0xFF6F7482);
        stripeColor = const Color(0xFFF04B4B);
    }

    final subLine = progressingCardSubtitle(apiStatus: row.status, linesTouched: row.mobileLinesTouched);

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: stripeColor, width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
        onTap: onTap,
        title: Text('PO-${row.receiptNo}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(row.supplier, style: const TextStyle(fontSize: 13)),
              const SizedBox(height: 2),
              Text(row.poNo.isEmpty ? row.invoiceNo : row.poNo,
                  style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12.5)),
              if (subLine.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child:
                      Text(subLine, style: const TextStyle(fontSize: 11.5, color: Color(0xFF9E6B2C), height: 1.2)),
                ),
            ],
          ),
        ),
        trailing: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 108),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(color: statusBg, borderRadius: BorderRadius.circular(50)),
                child: Text(grnStatusChipLabel(row.status),
                    style: TextStyle(color: statusFg, fontSize: 10.5, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(height: 2),
              Text(row.receiptDate, style: const TextStyle(fontSize: 11, color: Color(0xFF6F7482), height: 1.0)),
              const SizedBox(height: 2),
              Text(row.amount.toStringAsFixed(2), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF3E63F5), height: 1.0)),
            ],
          ),
        ),
      ),
    );
  }
}

class _StepHeader extends StatelessWidget {
  const _StepHeader({required this.currentStep});
  final int currentStep;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _StepNode(index: 0, title: 'PO / Date', active: currentStep >= 0, done: currentStep > 0),
        const Expanded(child: Divider()),
        _StepNode(index: 1, title: 'Receive qty', active: currentStep >= 1, done: currentStep > 1),
        const Expanded(child: Divider()),
        _StepNode(index: 2, title: 'Review', active: currentStep >= 2, done: false),
      ],
    );
  }
}

class _StepNode extends StatelessWidget {
  const _StepNode({required this.index, required this.title, required this.active, required this.done});
  final int index;
  final String title;
  final bool active;
  final bool done;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        CircleAvatar(
          radius: 11,
          backgroundColor: active ? const Color(0xFF5B3DF5) : const Color(0xFFE6E8F1),
          child: Text(done ? '✓' : '${index + 1}', style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
        ),
        const SizedBox(height: 5),
        Text(title, style: TextStyle(fontSize: 11, color: active ? const Color(0xFF463E82) : const Color(0xFF8A90A1), fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _InputBox extends StatelessWidget {
  const _InputBox({required this.label, required this.value, this.trailing});
  final String label;
  final String value;
  final IconData? trailing;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 10, 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF7B8191))),
                const SizedBox(height: 3),
                Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
              ],
            ),
          ),
          if (trailing != null) Icon(trailing, size: 16, color: const Color(0xFF9096A6)),
        ],
      ),
    );
  }
}

class _EditableField extends StatelessWidget {
  const _EditableField({
    required this.label,
    this.value,
    this.controller,
    this.hint,
    this.trailing,
    this.readOnly = false,
    this.onTap,
    this.minLines = 1,
    this.maxLines = 1,
  });

  final String label;
  final String? value;
  final TextEditingController? controller;
  final String? hint;
  final IconData? trailing;
  final bool readOnly;
  final VoidCallback? onTap;
  final int minLines;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    final effectiveController = controller ?? TextEditingController(text: value ?? '');
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 10, 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF7B8191))),
                const SizedBox(height: 3),
                TextField(
                  controller: effectiveController,
                  readOnly: readOnly,
                  onTap: onTap,
                  minLines: minLines,
                  maxLines: maxLines,
                  decoration: InputDecoration(
                    isDense: true,
                    border: InputBorder.none,
                    hintText: hint,
                    contentPadding: EdgeInsets.zero,
                  ),
                ),
              ],
            ),
          ),
          if (trailing != null) Icon(trailing, size: 16, color: const Color(0xFF9096A6)),
        ],
      ),
    );
  }
}

class _SummaryStrip extends StatelessWidget {
  const _SummaryStrip({required this.items});
  final List<(String, String)> items;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
      decoration: BoxDecoration(
        color: const Color(0xFFF4F1FF),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: items
            .map(
              (it) => Expanded(
                child: Column(
                  children: [
                    Text(it.$1, style: const TextStyle(fontSize: 11, color: Color(0xFF70758A))),
                    const SizedBox(height: 4),
                    Text(it.$2, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700, color: Color(0xFF3A2E80))),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }
}

class _ItemTableRow extends StatelessWidget {
  const _ItemTableRow({
    required this.index,
    required this.item,
    required this.onTapEdit,
  });
  final int index;
  final _ItemRow item;
  final VoidCallback onTapEdit;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTapEdit,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.fromLTRB(10, 4, 10, 8),
        padding: const EdgeInsets.fromLTRB(10, 10, 10, 10),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFE7EAF3)),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF1F3FD),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  alignment: Alignment.center,
                  child: Text('$index', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 2),
                      Text(item.code, style: const TextStyle(fontSize: 11.5, color: Color(0xFF6E7486))),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF2F0FF),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.edit_outlined, size: 14, color: Color(0xFF5B3DF5)),
                      SizedBox(width: 4),
                      Text('Update', style: TextStyle(fontSize: 11, color: Color(0xFF5B3DF5), fontWeight: FontWeight.w700)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(child: _metricTile('Ordered', item.qtyLabel(item.orderedQty))),
                const SizedBox(width: 6),
                Expanded(child: _metricTile('Received', item.qtyLabel(item.receivedQty), highlight: true)),
                const SizedBox(width: 6),
                Expanded(child: _metricTile('Bonus(Base)', item.bonusBaseUnit.toStringAsFixed(2))),
              ],
            ),
            if (item.isFocEnabled || item.batchNo.isNotEmpty || item.expiryDate.isNotEmpty || item.store.isNotEmpty || item.bin.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  if (item.isFocEnabled) _chip('FOC ON'),
                  if (item.isFocEnabled) _chip('Bonus Qty: ${item.bonusQty}'),
                  if (item.batchNo.isNotEmpty) _chip('Batch: ${item.batchNo}'),
                  if (item.expiryDate.isNotEmpty) _chip('Expiry: ${item.expiryDate}'),
                  if (item.store.isNotEmpty) _chip('Store: ${item.store}'),
                  if (item.bin.isNotEmpty) _chip('Bin: ${item.bin}'),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _metricTile(String title, String value, {bool highlight = false}) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 7),
      decoration: BoxDecoration(
        color: highlight ? const Color(0xFFF2F0FF) : const Color(0xFFF8F9FD),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFE6E8F0)),
      ),
      child: Column(
        children: [
          Text(title, style: const TextStyle(fontSize: 10.5, color: Color(0xFF71788A))),
          const SizedBox(height: 2),
          Text(value, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: highlight ? const Color(0xFF5B3DF5) : const Color(0xFF2E3356))),
        ],
      ),
    );
  }

  Widget _chip(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF6F7FC),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE4E7F0)),
      ),
      child: Text(text, style: const TextStyle(fontSize: 10.5, color: Color(0xFF5E6478))),
    );
  }
}

class _ReviewCard extends StatelessWidget {
  const _ReviewCard({required this.title, required this.lines});
  final String title;
  final List<(String, String)> lines;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EAF2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          ...lines.map(
            (line) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                children: [
                  Expanded(child: Text(line.$1, style: const TextStyle(fontSize: 12, color: Color(0xFF7A8091)))),
                  Expanded(child: Text(line.$2, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600))),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ItemRow {
  const _ItemRow({
    required this.code,
    required this.name,
    required this.unit,
    required this.orderedQty,
    required this.receivedQty,
    required this.bonusBaseUnit,
    required this.isFocEnabled,
    required this.bonusQty,
    required this.batchNo,
    required this.expiryDate,
    required this.store,
    required this.bin,
    this.lineSeq,
  });

  final String code;
  final String name;
  /// From LPODTL `UNITOFMEASUREMENT` (API field `unit`).
  final String unit;
  final int orderedQty;
  final int receivedQty;
  final double bonusBaseUnit;
  final bool isFocEnabled;
  final int bonusQty;
  final String batchNo;
  final String expiryDate;
  final String store;
  final String bin;
  /// Line index from ERP details (`line_seq`). Null for wizard-only/mock rows.
  final int? lineSeq;

  String qtyLabel(num qty) {
    final u = unit.trim();
    return u.isEmpty ? '$qty' : '$qty $u';
  }

  _ItemRow copyWith({
    String? code,
    String? name,
    String? unit,
    int? orderedQty,
    int? receivedQty,
    double? bonusBaseUnit,
    bool? isFocEnabled,
    int? bonusQty,
    String? batchNo,
    String? expiryDate,
    String? store,
    String? bin,
    int? lineSeq,
  }) {
    return _ItemRow(
      code: code ?? this.code,
      name: name ?? this.name,
      unit: unit ?? this.unit,
      orderedQty: orderedQty ?? this.orderedQty,
      receivedQty: receivedQty ?? this.receivedQty,
      bonusBaseUnit: bonusBaseUnit ?? this.bonusBaseUnit,
      isFocEnabled: isFocEnabled ?? this.isFocEnabled,
      bonusQty: bonusQty ?? this.bonusQty,
      batchNo: batchNo ?? this.batchNo,
      expiryDate: expiryDate ?? this.expiryDate,
      store: store ?? this.store,
      bin: bin ?? this.bin,
      lineSeq: lineSeq ?? this.lineSeq,
    );
  }
}

