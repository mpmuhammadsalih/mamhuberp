import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/sales_reports.dart';
import '../../providers/sales_reports_provider.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/provider_error_body.dart';
import '../../core/theme/app_theme.dart';

String _fmtMoney(double v) {
  if (v.abs() >= 1000000) return '${(v / 1000000).toStringAsFixed(1)}M';
  if (v.abs() >= 1000) return '${(v / 1000).toStringAsFixed(1)}K';
  if (v == v.roundToDouble()) return v.round().toString();
  return v.toStringAsFixed(2);
}

String _fmtMoneyFull(double v) => v.toStringAsFixed(2);

class SalesReportsScreen extends StatefulWidget {
  const SalesReportsScreen({super.key});

  @override
  State<SalesReportsScreen> createState() => _SalesReportsScreenState();
}

class _SalesReportsScreenState extends State<SalesReportsScreen> {
  static const _accent = Color(0xFFEF6C00);
  static const _accent2 = Color(0xFF1565C0);
  static const _bg = Color(0xFFF6F7FC);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SalesReportsProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<SalesReportsProvider>();

    if (state.isLoading && state.data == null) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(context),
        body: const AppLoadingIndicator(),
      );
    }

    if (state.error != null && state.data == null) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(context),
        body: ProviderErrorBody(
          message: state.error!,
          errorCause: state.errorCause,
          onRetry: () => state.load(),
        ),
      );
    }

    final data = state.data;
    if (data == null) return Scaffold(backgroundColor: _bg, appBar: _appBar(context));

    return Scaffold(
      backgroundColor: _bg,
      appBar: _appBar(context),
      body: LoadingOverlay(
        loading: state.isRefreshing,
        child: RefreshIndicator(
          color: _accent,
          onRefresh: () => state.load(forceRefresh: true),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
            children: [
              _PeriodSelector(
                selected: state.period,
                customFrom: state.customDateFrom,
                customTo: state.customDateTo,
                onSelected: (p) {
                  if (p == SalesReportsPeriod.custom) {
                    _pickCustomRange(state);
                  } else {
                    state.load(nextPeriod: p);
                  }
                },
                onPickDates: () => _pickCustomRange(state),
              ),
              const SizedBox(height: 14),
              Text(
                '${data.dateFrom} → ${data.dateTo}',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
              ),
              const SizedBox(height: 14),
              _KpiGrid(summary: data.summary, periodDays: data.periodDays),
              const SizedBox(height: 16),
              _SectionTitle('Daily sales trend', Icons.show_chart_rounded),
              const SizedBox(height: 8),
              _TrendChart(points: data.dailyTrend),
              const SizedBox(height: 16),
              _SectionTitle('This week vs last week', Icons.compare_arrows_rounded),
              const SizedBox(height: 8),
              _WeekCompareChart(points: data.weekComparison),
              const SizedBox(height: 16),
              _SectionTitle('Top customers', Icons.people_outline_rounded),
              const SizedBox(height: 8),
              _RankedBars(
                items: data.topCustomers
                    .map((c) => _RankItem(label: c.name, value: c.amount, subtitle: '${c.invoices} bills'))
                    .toList(),
                color: _accent2,
                emptyMessage: 'No customer sales in this period.',
              ),
              const SizedBox(height: 16),
              _SectionTitle('Top selling items', Icons.inventory_2_outlined),
              const SizedBox(height: 8),
              _RankedBars(
                items: data.topItems
                    .map((i) => _RankItem(
                          label: i.name,
                          value: i.amount,
                          subtitle: '${_fmtQty(i.qty)} qty',
                        ))
                    .toList(),
                color: const Color(0xFF2E7D32),
                emptyMessage: 'No line-level sales data available.',
              ),
              const SizedBox(height: 12),
              _ComparisonCard(summary: data.summary, periodDays: data.periodDays),
            ],
          ),
        ),
      ),
    );
  }

  PreferredSizeWidget _appBar(BuildContext context) {
    return AppBar(
      backgroundColor: AppTheme.appBarBlue,
      foregroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      leading: IconButton(
        icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
        onPressed: () => Navigator.of(context).maybePop(),
      ),
      title: const Text('Sales Reports', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      centerTitle: true,
      actions: [
        IconButton(
          tooltip: 'Pick date range',
          icon: const Icon(Icons.date_range_rounded, size: 22),
          onPressed: () => _pickCustomRange(context.read<SalesReportsProvider>()),
        ),
      ],
    );
  }

  Future<void> _pickCustomRange(SalesReportsProvider state) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final initialStart = state.customDateFrom ?? today.subtract(const Duration(days: 29));
    final initialEnd = state.customDateTo ?? today;
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2015),
      lastDate: today,
      initialDateRange: DateTimeRange(start: initialStart, end: initialEnd),
      helpText: 'Select date range',
      saveText: 'Apply',
      fieldStartHintText: 'From',
      fieldEndHintText: 'To',
    );
    if (picked == null || !mounted) return;
    await state.load(
      nextPeriod: SalesReportsPeriod.custom,
      customFrom: picked.start,
      customTo: picked.end,
    );
  }

  String _fmtQty(double v) {
    if (v == v.roundToDouble()) return v.round().toString();
    return v.toStringAsFixed(1);
  }
}

class _PeriodSelector extends StatelessWidget {
  const _PeriodSelector({
    required this.selected,
    required this.onSelected,
    required this.onPickDates,
    this.customFrom,
    this.customTo,
  });

  final SalesReportsPeriod selected;
  final DateTime? customFrom;
  final DateTime? customTo;
  final ValueChanged<SalesReportsPeriod> onSelected;
  final VoidCallback onPickDates;

  @override
  Widget build(BuildContext context) {
    const presets = [
      SalesReportsPeriod.today,
      SalesReportsPeriod.last7,
      SalesReportsPeriod.last30,
      SalesReportsPeriod.last90,
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final period in presets) ...[
            _periodChip(
              label: period.label(),
              isSelected: selected == period,
              onTap: () => onSelected(period),
            ),
            const SizedBox(width: 8),
          ],
          _periodChip(
            label: selected == SalesReportsPeriod.custom
                ? SalesReportsPeriod.custom.label(customFrom: customFrom, customTo: customTo)
                : 'Custom',
            isSelected: selected == SalesReportsPeriod.custom,
            onTap: onPickDates,
          ),
        ],
      ),
    );
  }

  Widget _periodChip({
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Material(
      color: isSelected ? const Color(0xFFEF6C00) : Colors.white,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected ? const Color(0xFFEF6C00) : const Color(0xFFE8EBF3),
            ),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontWeight: FontWeight.w700,
              fontSize: 13,
              color: isSelected ? Colors.white : const Color(0xFF3D4477),
            ),
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title, this.icon);

  final String title;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: const Color(0xFFEF6C00)),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50))),
      ],
    );
  }
}

class _KpiGrid extends StatelessWidget {
  const _KpiGrid({required this.summary, required this.periodDays});

  final SalesReportsSummary summary;
  final int periodDays;

  @override
  Widget build(BuildContext context) {
    final isToday = periodDays == 1;
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 1.35,
      children: [
        _KpiTile(
          title: isToday ? "Today's sales" : 'Period sales',
          value: _fmtMoneyFull(summary.totalSales),
          icon: Icons.payments_rounded,
          tint: const Color(0xFFEF6C00),
          changePct: summary.salesChangePct,
        ),
        _KpiTile(
          title: 'Invoices',
          value: '${summary.invoiceCount}',
          icon: Icons.receipt_long_outlined,
          tint: const Color(0xFF1565C0),
          changePct: summary.invoiceChangePct,
        ),
        _KpiTile(
          title: 'Avg ticket',
          value: _fmtMoneyFull(summary.avgTicket),
          icon: Icons.confirmation_number_outlined,
          tint: const Color(0xFF2E7D32),
        ),
        if (!isToday)
          _KpiTile(
            title: "Today's sales",
            value: _fmtMoneyFull(summary.todaySales),
            subtitle: '${summary.todayInvoices} bills',
            icon: Icons.today_outlined,
            tint: const Color(0xFF6A1B9A),
          )
        else
          _KpiTile(
            title: 'Returns',
            value: _fmtMoneyFull(summary.returnAmount.abs()),
            subtitle: summary.returnAmount < 0 ? 'Credit notes' : null,
            icon: Icons.undo_rounded,
            tint: const Color(0xFF6A1B9A),
          ),
      ],
    );
  }
}

class _KpiTile extends StatelessWidget {
  const _KpiTile({
    required this.title,
    required this.value,
    required this.icon,
    required this.tint,
    this.subtitle,
    this.changePct,
  });

  final String title;
  final String value;
  final IconData icon;
  final Color tint;
  final String? subtitle;
  final double? changePct;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: tint.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(icon, size: 16, color: tint),
              ),
              const Spacer(),
              if (changePct != null) _ChangeBadge(pct: changePct!),
            ],
          ),
          const Spacer(),
          Text(title, style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: Color(0xFF262C50)),
          ),
          if (subtitle != null)
            Text(subtitle!, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        ],
      ),
    );
  }
}

class _ChangeBadge extends StatelessWidget {
  const _ChangeBadge({required this.pct});

  final double pct;

  @override
  Widget build(BuildContext context) {
    final up = pct >= 0;
    final color = up ? const Color(0xFF1E8E5A) : const Color(0xFFE63946);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(up ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded, size: 11, color: color),
          Text(
            '${pct.abs().toStringAsFixed(1)}%',
            style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: color),
          ),
        ],
      ),
    );
  }
}

class _TrendChart extends StatelessWidget {
  const _TrendChart({required this.points});

  final List<SalesDailyPoint> points;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) return _emptyChart('No daily sales in this period.');

    final maxY = points.map((p) => p.amount).reduce((a, b) => a > b ? a : b);
    final spots = <FlSpot>[];
    for (var i = 0; i < points.length; i++) {
      spots.add(FlSpot(i.toDouble(), points[i].amount));
    }

    return _ChartCard(
      height: 220,
      child: LineChart(
        LineChartData(
          minY: 0,
          maxY: maxY <= 0 ? 1 : maxY * 1.15,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            horizontalInterval: maxY > 0 ? maxY / 4 : 1,
            getDrawingHorizontalLine: (_) => FlLine(color: Colors.grey.shade200, strokeWidth: 1),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 42,
                getTitlesWidget: (v, _) => Text(
                  _fmtMoney(v),
                  style: TextStyle(fontSize: 9, color: Colors.grey.shade600),
                ),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 28,
                interval: (points.length / 5).ceilToDouble().clamp(1, 999),
                getTitlesWidget: (v, _) {
                  final i = v.round();
                  if (i < 0 || i >= points.length) return const SizedBox.shrink();
                  final d = points[i].date;
                  final label = d.length >= 10 ? d.substring(5) : d;
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(label, style: TextStyle(fontSize: 9, color: Colors.grey.shade600)),
                  );
                },
              ),
            ),
          ),
          lineTouchData: LineTouchData(
            touchTooltipData: LineTouchTooltipData(
              getTooltipItems: (spots) => spots
                  .map(
                    (s) => LineTooltipItem(
                      '${points[s.x.round()].date}\n${_fmtMoneyFull(s.y)}',
                      const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 11),
                    ),
                  )
                  .toList(),
            ),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: const Color(0xFFEF6C00),
              barWidth: 2.5,
              dotData: FlDotData(
                show: points.length <= 14,
                getDotPainter: (_, __, ___, ____) => FlDotCirclePainter(
                  radius: 3,
                  color: Colors.white,
                  strokeWidth: 2,
                  strokeColor: const Color(0xFFEF6C00),
                ),
              ),
              belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFFEF6C00).withValues(alpha: 0.12),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WeekCompareChart extends StatelessWidget {
  const _WeekCompareChart({required this.points});

  final List<SalesWeekComparePoint> points;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) return _emptyChart('Not enough data for weekly comparison.');

    final maxVal = points
        .expand((p) => [p.current, p.previous])
        .fold<double>(0, (m, v) => v > m ? v : m);

    return _ChartCard(
      height: 240,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 8, bottom: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _legendDot(const Color(0xFFEF6C00), 'This week'),
                const SizedBox(width: 16),
                _legendDot(const Color(0xFF90A4AE), 'Last week'),
              ],
            ),
          ),
          Expanded(
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: maxVal <= 0 ? 1 : maxVal * 1.2,
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (_) => FlLine(color: Colors.grey.shade200, strokeWidth: 1),
                ),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 40,
                      getTitlesWidget: (v, _) => Text(
                        _fmtMoney(v),
                        style: TextStyle(fontSize: 9, color: Colors.grey.shade600),
                      ),
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (v, meta) {
                        final i = meta.appliedInterval == 0 ? v.toInt() : v.round();
                        if (i < 0 || i >= points.length) return const SizedBox.shrink();
                        return Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            points[i].day,
                            style: TextStyle(fontSize: 10, color: Colors.grey.shade700, fontWeight: FontWeight.w600),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                barGroups: [
                  for (var i = 0; i < points.length; i++)
                    BarChartGroupData(
                      x: i,
                      barRods: [
                        BarChartRodData(
                          toY: points[i].current,
                          color: const Color(0xFFEF6C00),
                          width: 10,
                          borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                        ),
                        BarChartRodData(
                          toY: points[i].previous,
                          color: const Color(0xFFCFD8DC),
                          width: 10,
                          borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                        ),
                      ],
                      barsSpace: 4,
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _legendDot(Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
        const SizedBox(width: 6),
        Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade700)),
      ],
    );
  }
}

class _RankItem {
  const _RankItem({required this.label, required this.value, this.subtitle});

  final String label;
  final double value;
  final String? subtitle;
}

class _RankedBars extends StatelessWidget {
  const _RankedBars({required this.items, required this.color, required this.emptyMessage});

  final List<_RankItem> items;
  final Color color;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return _emptyChart(emptyMessage);

    final maxVal = items.map((e) => e.value).reduce((a, b) => a > b ? a : b);

    return _ChartCard(
      child: Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[
            if (i > 0) const SizedBox(height: 12),
            _RankRow(rank: i + 1, item: items[i], maxVal: maxVal, color: color),
          ],
        ],
      ),
    );
  }
}

class _RankRow extends StatelessWidget {
  const _RankRow({required this.rank, required this.item, required this.maxVal, required this.color});

  final int rank;
  final _RankItem item;
  final double maxVal;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final frac = maxVal > 0 ? (item.value / maxVal).clamp(0.05, 1.0) : 0.05;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('$rank', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: color)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                item.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ),
            Text(
              _fmtMoneyFull(item.value),
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFF262C50)),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: frac,
            minHeight: 8,
            backgroundColor: color.withValues(alpha: 0.08),
            color: color,
          ),
        ),
        if (item.subtitle != null) ...[
          const SizedBox(height: 4),
          Text(item.subtitle!, style: TextStyle(fontSize: 10.5, color: Colors.grey.shade600)),
        ],
      ],
    );
  }
}

class _ComparisonCard extends StatelessWidget {
  const _ComparisonCard({required this.summary, required this.periodDays});

  final SalesReportsSummary summary;
  final int periodDays;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Period comparison',
            style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF262C50)),
          ),
          const SizedBox(height: 12),
          _compareRow('Sales', summary.totalSales, summary.prevPeriodSales, summary.salesChangePct),
          const SizedBox(height: 10),
          _compareRow(
            'Invoices',
            summary.invoiceCount.toDouble(),
            summary.prevInvoiceCount.toDouble(),
            summary.invoiceChangePct,
            isCount: true,
          ),
          const SizedBox(height: 10),
          _compareRow('Returns', summary.returnAmount.abs(), 0, null, prefix: '-'),
          const SizedBox(height: 8),
          Text(
            periodDays == 1
                ? 'Yesterday: ${_fmtMoneyFull(summary.prevPeriodSales)} (${summary.prevInvoiceCount} invoices)'
                : 'Previous $periodDays days: ${_fmtMoneyFull(summary.prevPeriodSales)} (${summary.prevInvoiceCount} invoices)',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
          ),
        ],
      ),
    );
  }

  Widget _compareRow(
    String label,
    double current,
    double previous,
    double? changePct, {
    bool isCount = false,
    String prefix = '',
  }) {
    final curStr = isCount ? current.round().toString() : '$prefix${_fmtMoneyFull(current)}';
    final prevStr = isCount ? previous.round().toString() : _fmtMoneyFull(previous);
    return Row(
      children: [
        Expanded(
          flex: 2,
          child: Text(label, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700)),
        ),
        Expanded(
          flex: 3,
          child: Text(curStr, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
        ),
        if (changePct != null)
          _ChangeBadge(pct: changePct)
        else
          Text(prevStr, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
      ],
    );
  }
}

class _ChartCard extends StatelessWidget {
  const _ChartCard({required this.child, this.height});

  final Widget child;
  final double? height;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: child,
    );
  }
}

Widget _emptyChart(String message) {
  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: const Color(0xFFE8EBF3)),
    ),
    child: Text(message, style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
  );
}
