import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/storage/transaction_draft_storage.dart';
import '../../models/grn_receipt.dart';
import '../../providers/auth_provider.dart';
import '../../services/purchase_service.dart';
import '../../utils/grn_display.dart';
import '../../widgets/api_error_banner.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/transaction_draft_banner.dart';
import 'grn_ai_screen.dart';
import 'grn_form_screen.dart';
import 'grn_po_wizard_screen.dart';
import 'inventory_transaction_draft.dart';
import '../../core/theme/app_theme.dart';

/// Formal GRN hub — same tabs as ERP goods receipt list:
/// Approved PO | Draft GRN | Posted GRN.
class GrnScreen extends StatefulWidget {
  const GrnScreen({super.key});

  @override
  State<GrnScreen> createState() => _GrnScreenState();
}

class _GrnScreenState extends State<GrnScreen> {
  static const _accent = Color(0xFF0277BD);
  static const _tabs = [
    ('pending', 'Approved PO'),
    ('draft', 'Draft'),
    ('posted', 'Completed'),
  ];

  String _tabKey = 'pending';
  bool _loading = false;
  String? _error;
  Object? _errorCause;
  List<GrnReceipt> _rows = [];
  final TextEditingController _searchController = TextEditingController();
  Map<String, dynamic>? _draft;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDraftBanner();
      _reload();
    });
  }

  Future<void> _loadDraftBanner() async {
    final user = context.read<AuthProvider>().user;
    if (user == null) {
      if (mounted) setState(() => _draft = null);
      return;
    }
    final draft = await TransactionDraftStorage.read(
      docType: TransactionDraftType.grn,
      tenantId: user.tenantId ?? '',
      username: user.username,
    );
    if (!mounted) return;
    setState(() => _draft = draft);
  }

  Future<void> _dismissDraft() async {
    final user = context.read<AuthProvider>().user;
    if (user != null) {
      await TransactionDraftStorage.clear(
        docType: TransactionDraftType.grn,
        tenantId: user.tenantId ?? '',
        username: user.username,
      );
    }
    if (mounted) setState(() => _draft = null);
  }

  Future<void> _continueDraft() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => const GrnFormScreen(restoreDraft: true),
      ),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    if (saved == true) {
      setState(() => _tabKey = 'draft');
      await _reload();
    }
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    final svc = context.read<PurchaseService>();
    final search = _searchController.text;
    try {
      final List<GrnReceipt> next;
      switch (_tabKey) {
        case 'posted':
          next = await svc.getGrnHubPosted(search: search);
          break;
        case 'draft':
          next = await svc.getGrnHubDraft(search: search);
          break;
        default:
          next = await svc.getGrnHubPending(search: search);
      }
      if (!mounted) return;
      setState(() {
        _rows = next;
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

  Future<void> _openNewGrn() async {
    if (_draft != null) {
      final action = await showPendingDraftAlert(
        context,
        summary: InventoryTransactionDraft.summaryLabel(_draft!, fallback: 'New GRN'),
        documentLabel: 'GRN',
      );
      if (!mounted) return;
      if (action == PendingDraftAction.cancel) return;
      if (action == PendingDraftAction.continuePending) {
        await _continueDraft();
        return;
      }
      await _dismissDraft();
    }

    final choice = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey.shade300,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              const Text('New GRN', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              const SizedBox(height: 6),
              Text(
                'Choose how to create this goods receipt.',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
              ),
              const SizedBox(height: 16),
              ListTile(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: Color(0xFFE4E7F0)),
                ),
                leading: const CircleAvatar(
                  backgroundColor: Color(0xFFE3F2FD),
                  child: Icon(Icons.auto_awesome_rounded, color: Color(0xFF0277BD)),
                ),
                title: const Text('AI GRN', style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text('Extract supplier invoice (same as ERP AI)'),
                onTap: () => Navigator.pop(ctx, 'ai'),
              ),
              const SizedBox(height: 10),
              ListTile(
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: Color(0xFFE4E7F0)),
                ),
                leading: const CircleAvatar(
                  backgroundColor: Color(0xFFE8F5E9),
                  child: Icon(Icons.edit_note_rounded, color: Color(0xFF2E7D32)),
                ),
                title: const Text('Normal GRN', style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text('Manual entry / catalog lines'),
                onTap: () => Navigator.pop(ctx, 'normal'),
              ),
            ],
          ),
        ),
      ),
    );
    if (!mounted || choice == null) return;

    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => choice == 'ai' ? const GrnAiScreen() : const GrnFormScreen(),
      ),
    );
    if (!mounted) return;
    await _loadDraftBanner();
    if (saved == true) {
      setState(() => _tabKey = 'draft');
      await _reload();
    }
  }

  void _openFormalGrnWizard(GrnReceipt row) {
    final mode = switch (_tabKey) {
      'draft' => GrnWizardMode.editDraft,
      'posted' => GrnWizardMode.viewPosted,
      _ => GrnWizardMode.fromApprovedPo,
    };
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => GrnPoWizardScreen(
          poLookupKey: _tabKey == 'pending'
              ? (row.poNo.isNotEmpty ? row.poNo : row.receiptNo)
              : (row.poNo.isNotEmpty ? row.poNo : row.receiptNo),
          receiptNo: _tabKey == 'pending' ? null : row.receiptNo,
          initialSupplier: row.supplier,
          mode: mode,
          onSaved: () {
            if (mounted) _reload();
          },
        ),
      ),
    );
  }

  Future<void> _cancelDraftGrn(GrnReceipt row) async {
    final label = row.receiptNo.trim().isEmpty ? 'this GRN' : row.receiptNo;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel GRN'),
        content: Text(
          'Cancel $label?\n\nThis deletes the draft receipt. The purchase order will return to Pending.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Keep')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFC62828)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cancel GRN'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _loading = true);
    try {
      await context.read<PurchaseService>().cancelGrn(row.receiptNo);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$label canceled.')),
      );
      await _reload();
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  Widget _grnHubBody() {
    if (_error != null) {
      return ApiErrorCenter(
        message: _error!,
        error: _errorCause,
        onRetry: _reload,
      );
    }
    if (_rows.isEmpty) {
      final emptyMsg = switch (_tabKey) {
        'posted' => 'No posted receipts in RECEIPTHDR.',
        'draft' =>
          'No draft GRNs.\nTap + to create a GRN, or save from Approved PO without posting stock.',
        _ =>
          'No approved POs without GRN.\nTap + to create a direct GRN, or approve a PO first.',
      };
      return Center(
        child: Text(
          emptyMsg,
          textAlign: TextAlign.center,
          style: const TextStyle(color: Color(0xFF7C8191)),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 94),
      itemCount: _rows.length,
      separatorBuilder: (_, __) => const SizedBox(height: 9),
      itemBuilder: (context, index) {
        final row = _rows[index];
        return _GrnHubCard(
          row: row,
          emphasizePo: _tabKey == 'pending',
          onTap: () => _openFormalGrnWizard(row),
          onEdit: (_tabKey == 'draft' && row.canEdit) ? () => _openFormalGrnWizard(row) : null,
          onCancel: (_tabKey == 'draft' && row.canDelete) ? () => _cancelDraftGrn(row) : null,
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openNewGrn,
        backgroundColor: const Color(0xFF0277BD),
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_rounded),
        label: const Text('New GRN'),
      ),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
        ),
        title: const Text('GRN', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(onPressed: _loading ? null : _reload, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      body: Column(
        children: [
          if (_draft != null)
            TransactionDraftBanner(
              title: 'Continue draft',
              subtitle: InventoryTransactionDraft.summaryLabel(_draft!, fallback: 'New GRN'),
              accent: _accent,
              onContinue: _continueDraft,
              onDismiss: _dismissDraft,
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _searchController,
                    onSubmitted: (_) => _reload(),
                    decoration: InputDecoration(
                      hintText: _tabKey == 'pending'
                          ? 'Search PO No, Supplier...'
                          : 'Search receipt no, PO, supplier...',
                      hintStyle: const TextStyle(fontSize: 13),
                      prefixIcon: const Icon(Icons.search, size: 20),
                      filled: true,
                      fillColor: const Color(0xFFF4F5FA),
                      contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 10),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(
                  width: 42,
                  height: 42,
                  child: FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF0277BD),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      padding: EdgeInsets.zero,
                    ),
                    onPressed: _reload,
                    child: const Icon(Icons.refresh_rounded),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  for (var i = 0; i < _tabs.length; i++) ...[
                    _GrnHubTab(
                      _tabs[i].$2,
                      _tabKey == _tabs[i].$1,
                      onTap: () {
                        if (_tabKey == _tabs[i].$1) return;
                        setState(() => _tabKey = _tabs[i].$1);
                        _reload();
                      },
                    ),
                    if (i < _tabs.length - 1) const SizedBox(width: 20),
                  ],
                ],
              ),
            ),
          ),
          Expanded(
            child: _loading && _rows.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : LoadingOverlay(
                    loading: _loading,
                    child: _grnHubBody(),
                  ),
          ),
        ],
      ),
    );
  }
}

class _GrnHubTab extends StatelessWidget {
  const _GrnHubTab(this.label, this.active, {required this.onTap});
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
              color: active ? const Color(0xFF0277BD) : const Color(0xFF6F7482),
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 28,
            height: 2,
            color: active ? const Color(0xFF0277BD) : Colors.transparent,
          ),
        ],
      ),
    );
  }
}

class _GrnHubCard extends StatelessWidget {
  const _GrnHubCard({
    required this.row,
    required this.onTap,
    required this.emphasizePo,
    this.onEdit,
    this.onCancel,
  });
  final GrnReceipt row;
  final VoidCallback onTap;
  final bool emphasizePo;
  final VoidCallback? onEdit;
  final VoidCallback? onCancel;

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
      case 'Posted':
        statusBg = const Color(0xFFE1F5FE);
        statusFg = const Color(0xFF0277BD);
        stripeColor = const Color(0xFF039BE5);
        break;
      case 'Draft':
        statusBg = const Color(0xFFFFF3E0);
        statusFg = const Color(0xFFE65100);
        stripeColor = const Color(0xFFFFB74D);
        break;
      case 'Approved':
        statusBg = const Color(0xFFE8F5E9);
        statusFg = const Color(0xFF2E7D32);
        stripeColor = const Color(0xFF66BB6A);
        break;
      default:
        statusBg = const Color(0xFFF2F2F5);
        statusFg = const Color(0xFF6F7482);
        stripeColor = const Color(0xFF90A4AE);
    }

    String _docLabel(String raw, {required String prefix}) {
      final s = raw.trim();
      if (s.isEmpty) return prefix;
      final up = s.toUpperCase();
      if (up.startsWith('PO-') || up.startsWith('LPO-') || up.startsWith('GRN-') || up.startsWith('RN-')) {
        return s;
      }
      return '$prefix$s';
    }

    final primaryNo = emphasizePo
        ? _docLabel(row.poNo.isNotEmpty ? row.poNo : row.receiptNo, prefix: 'PO-')
        : _docLabel(row.receiptNo, prefix: 'RN-');
    final subLine = progressingCardSubtitle(apiStatus: row.status, linesTouched: row.mobileLinesTouched);

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: stripeColor, width: 3)),
        boxShadow: const [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(primaryNo, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                    const SizedBox(height: 2),
                    Text(row.supplier, style: const TextStyle(fontSize: 13)),
                    const SizedBox(height: 2),
                    if (!emphasizePo && row.poNo.isNotEmpty)
                      Text(
                        row.poNo.toUpperCase().startsWith('PO-') ? row.poNo : 'PO-${row.poNo}',
                        style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12.5),
                      ),
                    if (emphasizePo)
                      Text(row.receiptDate, style: const TextStyle(color: Color(0xFF7D8393), fontSize: 12.5)),
                    if (subLine.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          subLine,
                          style: const TextStyle(fontSize: 11.5, color: Color(0xFF9E6B2C), height: 1.2),
                        ),
                      ),
                    if (onEdit != null || onCancel != null) ...[
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          if (onEdit != null)
                            TextButton.icon(
                              onPressed: onEdit,
                              icon: const Icon(Icons.edit_outlined, size: 16),
                              label: const Text('Edit'),
                              style: TextButton.styleFrom(
                                foregroundColor: const Color(0xFF0277BD),
                                visualDensity: VisualDensity.compact,
                                padding: const EdgeInsets.symmetric(horizontal: 6),
                              ),
                            ),
                          if (onCancel != null)
                            TextButton.icon(
                              onPressed: onCancel,
                              icon: const Icon(Icons.cancel_outlined, size: 16),
                              label: const Text('Cancel'),
                              style: TextButton.styleFrom(
                                foregroundColor: const Color(0xFFC62828),
                                visualDensity: VisualDensity.compact,
                                padding: const EdgeInsets.symmetric(horizontal: 6),
                              ),
                            ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 108),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(color: statusBg, borderRadius: BorderRadius.circular(50)),
                      child: Text(
                        grnStatusChipLabel(row.status),
                        style: TextStyle(color: statusFg, fontSize: 10.5, fontWeight: FontWeight.w700),
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      row.amount.toStringAsFixed(0),
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
