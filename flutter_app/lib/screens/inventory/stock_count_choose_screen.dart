import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_client.dart';
import '../../core/network/access_denied_alert.dart';
import '../../core/network/api_error_handler.dart';
import '../../widgets/api_error_banner.dart';
import '../../models/stock_count_session.dart';
import '../../repositories/stock_count_repository.dart';
import '../../services/stock_count_service.dart';
import 'stock_count_screen.dart';
import '../../core/theme/app_theme.dart';

StockCountRepository _stockCountRepo(BuildContext context) {
  try {
    return context.read<StockCountRepository>();
  } on ProviderNotFoundException {
    return StockCountRepository(StockCountService(context.read<ApiClient>()));
  }
}

/// Pick an existing DRAFT stock count created in ERP (not created on mobile).
class StockCountChooseScreen extends StatefulWidget {
  const StockCountChooseScreen({super.key});

  @override
  State<StockCountChooseScreen> createState() => _StockCountChooseScreenState();
}

class _StockCountChooseScreenState extends State<StockCountChooseScreen> {
  static const _accent = Color(0xFF5E35B1);
  static const _accentLight = Color(0xFFF3EEFF);
  static const _titleColor = Color(0xFF262C50);

  final TextEditingController _locationFilterCtrl = TextEditingController();

  bool _loading = false;
  bool _opening = false;
  String? _error;
  Object? _errorCause;
  List<StockCountSummary> _counts = [];

  @override
  void dispose() {
    _locationFilterCtrl.dispose();
    super.dispose();
  }

  int? get _locationFilter {
    final raw = _locationFilterCtrl.text.trim();
    if (raw.isEmpty) return null;
    return int.tryParse(raw);
  }

  Future<void> _loadCounts() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
      _errorCause = null;
    });
    try {
      final rows = await _stockCountRepo(context).listAvailableDrafts(
        locationcode: _locationFilter,
      );
      if (!mounted) return;
      setState(() {
        _counts = rows;
        _loading = false;
        if (rows.isEmpty && _locationFilter != null) {
          _error = 'No counts for location $_locationFilter. Try clearing the filter.';
        }
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

  void _clearFilter() {
    _locationFilterCtrl.clear();
    _loadCounts();
  }

  Future<void> _openCount(StockCountSummary summary) async {
    if (!summary.canOpen) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Only open (non-posted) counts can be counted here.')),
      );
      return;
    }

    setState(() => _opening = true);
    try {
      if (!mounted) return;
      await Navigator.of(context).push<void>(
        MaterialPageRoute<void>(
          builder: (_) => StockCountScreen(
            locationcode: summary.locationcode,
            countNo: summary.countNo,
            warehouseId: summary.warehouseId,
          ),
        ),
      );
      if (mounted) await _loadCounts();
    } catch (e) {
      if (!mounted) return;
      if (!maybeShowAccessDeniedAlert(context, e)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(handleApiError(context, e, authenticatedContext: true, showAccessDialog: false))),
        );
      }
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadCounts());
  }

  @override
  Widget build(BuildContext context) {
    final bottomPad = MediaQuery.paddingOf(context).bottom;

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
        title: const Text('Stock counts', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: Stack(
        children: [
          RefreshIndicator(
            color: _accent,
            onRefresh: _loadCounts,
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [Color(0xFF5E35B1), Color(0xFF4527A0)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: const [
                          BoxShadow(
                            color: Color(0x285E35B1),
                            blurRadius: 12,
                            offset: Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(Icons.fact_check_rounded, color: Colors.white, size: 26),
                          ),
                          const SizedBox(width: 14),
                          const Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Choose a count',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w800,
                                    fontSize: 17,
                                  ),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  'Counts are created in ERP. Open one to start or continue counting.',
                                  style: TextStyle(
                                    color: Color(0xFFE8DEFF),
                                    fontSize: 12.5,
                                    height: 1.35,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 14, 16, 0),
                    child: Material(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(14),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            TextField(
                              controller: _locationFilterCtrl,
                              keyboardType: TextInputType.number,
                              textInputAction: TextInputAction.search,
                              decoration: InputDecoration(
                                labelText: 'Location code',
                                hintText: 'All locations',
                                prefixIcon: const Icon(Icons.store_outlined, size: 22),
                                filled: true,
                                fillColor: const Color(0xFFF6F7FC),
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  borderSide: const BorderSide(color: Color(0xFFE8EBF3)),
                                ),
                                isDense: true,
                              ),
                              onSubmitted: (_) => _loadCounts(),
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                Expanded(
                                  child: OutlinedButton.icon(
                                    onPressed: _loading || _opening ? null : _clearFilter,
                                    style: OutlinedButton.styleFrom(
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                      side: const BorderSide(color: Color(0xFFE8EBF3)),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                    ),
                                    icon: const Icon(Icons.filter_alt_off_outlined, size: 18),
                                    label: const Text('Clear'),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  flex: 2,
                                  child: FilledButton.icon(
                                    onPressed: _loading || _opening ? null : _loadCounts,
                                    style: FilledButton.styleFrom(
                                      backgroundColor: _accent,
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                    ),
                                    icon: _loading
                                        ? const SizedBox(
                                            width: 16,
                                            height: 16,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: Colors.white,
                                            ),
                                          )
                                        : const Icon(Icons.search_rounded, size: 20),
                                    label: Text(_loading ? 'Loading…' : 'Search counts'),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                if (_error != null)
                  SliverToBoxAdapter(
                    child: ApiErrorBanner(message: _error!, error: _errorCause),
                  ),
                if (_loading && _counts.isEmpty)
                  const SliverFillRemaining(
                    hasScrollBody: false,
                    child: Center(child: CircularProgressIndicator(color: _accent)),
                  )
                else if (_counts.isEmpty)
                  SliverFillRemaining(
                    hasScrollBody: false,
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            width: 72,
                            height: 72,
                            decoration: BoxDecoration(
                              color: _accentLight,
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: const Icon(Icons.inventory_2_outlined, color: _accent, size: 36),
                          ),
                          const SizedBox(height: 16),
                          const Text(
                            'No open counts',
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 18,
                              color: _titleColor,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Create DRAFT counts in ERP, or clear the location filter and search again.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: Colors.grey.shade600, height: 1.4, fontSize: 14),
                          ),
                          const SizedBox(height: 20),
                          FilledButton.icon(
                            onPressed: _loading ? null : _loadCounts,
                            style: FilledButton.styleFrom(
                              backgroundColor: _accent,
                              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            ),
                            icon: const Icon(Icons.refresh_rounded),
                            label: const Text('Refresh list'),
                          ),
                        ],
                      ),
                    ),
                  )
                else ...[
                  SliverToBoxAdapter(child: _SectionHeader(
                    title: 'Open counts',
                    count: _counts.length,
                    color: _accent,
                    bgColor: _accentLight,
                  )),
                  SliverPadding(
                    padding: EdgeInsets.fromLTRB(16, 0, 16, 24 + bottomPad),
                    sliver: SliverList(
                      delegate: SliverChildBuilderDelegate(
                        (context, index) => Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _CountCard(
                            summary: _counts[index],
                            busy: _opening,
                            onAction: () => _openCount(_counts[index]),
                          ),
                        ),
                        childCount: _counts.length,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (_opening)
            const ColoredBox(
              color: Color(0x44000000),
              child: Center(child: CircularProgressIndicator(color: _accent)),
            ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    required this.count,
    required this.color,
    required this.bgColor,
  });

  final String title;
  final int count;
  final Color color;
  final Color bgColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 10),
      child: Row(
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w800,
              color: Color(0xFF262C50),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: bgColor,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              '$count',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color),
            ),
          ),
        ],
      ),
    );
  }
}

class _CountCard extends StatelessWidget {
  const _CountCard({
    required this.summary,
    required this.busy,
    required this.onAction,
  });

  final StockCountSummary summary;
  final bool busy;
  final VoidCallback onAction;

  static const _accent = Color(0xFF5E35B1);
  static const _titleColor = Color(0xFF262C50);
  static const _muted = Color(0xFF6F778A);

  @override
  Widget build(BuildContext context) {
    const actionColor = _accent;
    const actionBg = Color(0xFFF3EEFF);
    final wh = summary.warehouseId;

    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: busy ? null : onAction,
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(color: const Color(0xFFE8EBF3)),
            borderRadius: BorderRadius.circular(14),
            boxShadow: const [
              BoxShadow(color: Color(0x08000000), blurRadius: 6, offset: Offset(0, 2)),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                height: 4,
                color: actionColor,
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: actionBg,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(
                            Icons.playlist_add_check_rounded,
                            color: actionColor,
                            size: 22,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    'Count #${summary.countNo}',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w800,
                                      fontSize: 16,
                                      color: _titleColor,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  _StatusChip(status: summary.status),
                                ],
                              ),
                              const SizedBox(height: 6),
                              Wrap(
                                spacing: 6,
                                runSpacing: 6,
                                children: [
                                  _MetaChip(
                                    icon: Icons.location_on_outlined,
                                    label: 'Loc ${summary.locationcode}',
                                  ),
                                  if (wh != null)
                                    _MetaChip(
                                      icon: Icons.warehouse_outlined,
                                      label: 'WH $wh',
                                    ),
                                  _MetaChip(
                                    icon: Icons.format_list_numbered_rounded,
                                    label: '${summary.lineCount} lines',
                                  ),
                                ],
                              ),
                              if (summary.countDate.isNotEmpty ||
                                  summary.createdBy.isNotEmpty ||
                                  summary.assignedTo.isNotEmpty) ...[
                                const SizedBox(height: 8),
                                Text(
                                  [
                                    if (summary.countDate.isNotEmpty) summary.countDate,
                                    if (summary.assignedTo.isNotEmpty &&
                                        summary.assignedTo != summary.createdBy)
                                      'Counted by ${summary.assignedTo}',
                                    if (summary.createdBy.isNotEmpty)
                                      summary.assignedTo.isNotEmpty &&
                                              summary.assignedTo != summary.createdBy
                                          ? 'Created ${summary.createdBy}'
                                          : summary.createdBy,
                                  ].join(' · '),
                                  style: const TextStyle(fontSize: 12, color: _muted),
                                ),
                              ],
                              if (summary.remarks.isNotEmpty) ...[
                                const SizedBox(height: 6),
                                Text(
                                  summary.remarks,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                ),

                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: busy ? null : onAction,
                        style: FilledButton.styleFrom(
                          backgroundColor: actionColor,
                          disabledBackgroundColor: actionColor.withValues(alpha: 0.4),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                        label: const Text(
                          'Open count',
                          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                        ),
                      ),
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

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    if (status.isEmpty) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: const Color(0xFFF6F7FC),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Text(
        status.toUpperCase(),
        style: const TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: Color(0xFF6F778A),
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF6F7FC),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: const Color(0xFF6F778A)),
          const SizedBox(width: 4),
          Text(
            label,
            style: const TextStyle(
              fontSize: 11.5,
              fontWeight: FontWeight.w600,
              color: Color(0xFF6F778A),
            ),
          ),
        ],
      ),
    );
  }
}
