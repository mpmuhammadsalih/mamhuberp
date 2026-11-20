import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/business_summary.dart';
import '../../providers/business_summary_provider.dart';
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

String _fmtKpi(BusinessSummaryKpi k) {
  if (k.format == 'percent') return '${k.value.toStringAsFixed(1)}%';
  if (k.format == 'number') {
    if (k.value == k.value.roundToDouble()) return k.value.round().toString();
    return k.value.toStringAsFixed(1);
  }
  return _fmtMoneyFull(k.value);
}

class BusinessSummaryScreen extends StatefulWidget {
  const BusinessSummaryScreen({super.key});

  @override
  State<BusinessSummaryScreen> createState() => _BusinessSummaryScreenState();
}

class _BusinessSummaryScreenState extends State<BusinessSummaryScreen> {
  static const _accent = Color(0xFF5B3DF5);
  static const _accent2 = Color(0xFF1565C0);
  static const _accent3 = Color(0xFF2E7D32);
  static const _bg = Color(0xFFF6F7FC);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<BusinessSummaryProvider>().load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<BusinessSummaryProvider>();

    if (state.isLoading && state.data == null) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(),
        body: const Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AppLoadingIndicator(),
              SizedBox(height: 16),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: 32),
                child: Text(
                  'Loading business summary from ERP…\nFirst load may take 20–40 seconds.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xFF616161), height: 1.4),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (state.error != null && state.data == null) {
      return Scaffold(
        backgroundColor: _bg,
        appBar: _appBar(),
        body: ProviderErrorBody(
          message: state.error!,
          errorCause: state.errorCause,
          onRetry: () => state.load(),
        ),
      );
    }

    final data = state.data;
    if (data == null) return Scaffold(backgroundColor: _bg, appBar: _appBar());

    return Scaffold(
      backgroundColor: _bg,
      appBar: _appBar(),
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
                  if (p == BusinessSummaryPeriod.custom) {
                    _pickCustomRange(state);
                  } else {
                    state.load(nextPeriod: p);
                  }
                },
                onPickDates: () => _pickCustomRange(state),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${data.dateFrom} → ${data.dateTo}',
                          style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                        ),
                        if (data.branch != null)
                          Text(
                            'Branch filter: ${data.branch}',
                            style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                          ),
                      ],
                    ),
                  ),
                  if (data.generatedAt.isNotEmpty)
                    Text(
                      data.generatedAt,
                      style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
                    ),
                ],
              ),
              if (data.warnings.isNotEmpty) ...[
                const SizedBox(height: 10),
                _WarningBanner(messages: data.warnings),
              ],
              const SizedBox(height: 14),
              _HeroCard(data: data),
              const SizedBox(height: 14),
              _KpiGrid(data: data),
              const SizedBox(height: 16),
              _SectionTitle('Sales vs purchases (GRN)', Icons.compare_arrows_rounded),
              const SizedBox(height: 8),
              _DualTrendChart(charts: data.charts),
              const SizedBox(height: 16),
              _SectionTitle('Daily sales', Icons.show_chart_rounded),
              const SizedBox(height: 8),
              _DailySalesChart(points: data.charts.dailySales),
              const SizedBox(height: 16),
              _SectionTitle('Net sales vs gross profit', Icons.pie_chart_outline_rounded),
              const SizedBox(height: 8),
              _ProfitCompareChart(charts: data.charts),
              const SizedBox(height: 16),
              _SectionTitle('Top customers', Icons.people_outline_rounded),
              const SizedBox(height: 8),
              _RankedBars(
                items: data.charts.topCustomers,
                color: _accent2,
                emptyMessage: 'No customer sales in this period.',
              ),
              const SizedBox(height: 16),
              _SectionTitle('Top items', Icons.inventory_2_outlined),
              const SizedBox(height: 8),
              _RankedBars(
                items: data.charts.topItems,
                color: _accent3,
                emptyMessage: 'No item sales in this period.',
              ),
              if (data.charts.categorySales.isNotEmpty) ...[
                const SizedBox(height: 16),
                _SectionTitle('Sales by category', Icons.category_outlined),
                const SizedBox(height: 8),
                _PieBreakdown(items: data.charts.categorySales, accent: _accent),
              ],
              if (data.charts.paymentMethods.isNotEmpty) ...[
                const SizedBox(height: 16),
                _SectionTitle('Payment methods', Icons.payments_outlined),
                const SizedBox(height: 8),
                _PieBreakdown(items: data.charts.paymentMethods, accent: const Color(0xFFEF6C00)),
              ],
              const SizedBox(height: 16),
              _SectionTitle('Transactions', Icons.receipt_long_outlined),
              const SizedBox(height: 8),
              _TransactionList(rows: data.transactions),
              const SizedBox(height: 16),
              _SectionTitle('Financial snapshot', Icons.account_balance_wallet_outlined),
              const SizedBox(height: 8),
              _FinancialCard(financial: data.financial),
            ],
          ),
        ),
      ),
    );
  }

  PreferredSizeWidget _appBar() {
    return AppBar(
      backgroundColor: AppTheme.appBarBlue,
      foregroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      leading: IconButton(
        icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
        onPressed: () => Navigator.of(context).maybePop(),
      ),
      title: const Text('Business Summary', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      centerTitle: true,
      actions: [
        IconButton(
          tooltip: 'Pick date range',
          icon: const Icon(Icons.date_range_rounded, size: 22),
          onPressed: () => _pickCustomRange(context.read<BusinessSummaryProvider>()),
        ),
      ],
    );
  }

  Future<void> _pickCustomRange(BusinessSummaryProvider state) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final initialStart = state.customDateFrom ?? DateTime(today.year, today.month, 1);
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
      nextPeriod: BusinessSummaryPeriod.custom,
      customFrom: picked.start,
      customTo: picked.end,
    );
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

  final BusinessSummaryPeriod selected;
  final DateTime? customFrom;
  final DateTime? customTo;
  final ValueChanged<BusinessSummaryPeriod> onSelected;
  final VoidCallback onPickDates;

  @override
  Widget build(BuildContext context) {
    const presets = [
      BusinessSummaryPeriod.today,
      BusinessSummaryPeriod.thisMonth,
      BusinessSummaryPeriod.last7,
      BusinessSummaryPeriod.last30,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final period in presets) ...[
                _periodChip(
                  period: period,
                  label: period.label(),
                  isSelected: selected == period,
                  onTap: () => onSelected(period),
                ),
                const SizedBox(width: 8),
              ],
              _periodChip(
                period: BusinessSummaryPeriod.custom,
                label: selected == BusinessSummaryPeriod.custom
                    ? BusinessSummaryPeriod.custom.label(customFrom: customFrom, customTo: customTo)
                    : 'Custom',
                isSelected: selected == BusinessSummaryPeriod.custom,
                onTap: onPickDates,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _periodChip({
    required BusinessSummaryPeriod period,
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Material(
      color: isSelected ? const Color(0xFF5B3DF5) : Colors.white,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected ? const Color(0xFF5B3DF5) : const Color(0xFFE8EBF3),
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

class _HeroCard extends StatelessWidget {
  const _HeroCard({required this.data});

  final BusinessSummaryData data;

  @override
  Widget build(BuildContext context) {
    final netSales = data.kpi('net_sales')?.value ?? data.financial.netSales;
    final grossProfit = data.kpi('gross_profit')?.value ?? data.financial.grossProfit;
    final margin = data.kpi('gross_margin_pct')?.value ?? data.financial.grossProfitPct;

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF5B3DF5), Color(0xFF7C4DFF)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF5B3DF5).withValues(alpha: 0.25),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Net sales',
            style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            _fmtMoneyFull(netSales),
            style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _heroStat('Gross profit', _fmtMoneyFull(grossProfit)),
              ),
              Expanded(
                child: _heroStat('Margin', '${margin.toStringAsFixed(1)}%'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _heroStat(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 11)),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _KpiGrid extends StatelessWidget {
  const _KpiGrid({required this.data});

  final BusinessSummaryData data;

  static const _primaryIds = [
    'total_sales',
    'sales_return',
    'total_purchases', // Purchases (GRN)
    'purchase_orders',
    'net_purchases',
    'purchase_return',
    'customer_receipts',
    'expenses',
    'outstanding_receivables',
    'outstanding_payables',
    'inventory_value',
    'cash_sales',
    'credit_sales',
  ];

  @override
  Widget build(BuildContext context) {
    final tiles = <BusinessSummaryKpi>[];
    for (final id in _primaryIds) {
      final k = data.kpi(id);
      if (k != null) tiles.add(k);
    }
    if (tiles.isEmpty && data.kpis.isNotEmpty) {
      tiles.addAll(data.kpis.take(8));
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: 10,
        crossAxisSpacing: 10,
        childAspectRatio: 1.45,
      ),
      itemCount: tiles.length,
      itemBuilder: (_, i) {
        final k = tiles[i];
        return Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE8EBF3)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                k.label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
              ),
              const Spacer(),
              Text(
                _fmtKpi(k),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: Color(0xFF262C50)),
              ),
            ],
          ),
        );
      },
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
        Icon(icon, size: 18, color: const Color(0xFF5B3DF5)),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50))),
      ],
    );
  }
}

class _WarningBanner extends StatelessWidget {
  const _WarningBanner({required this.messages});

  final List<String> messages;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final msg in messages) ...[
          if (msg != messages.first) const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFFF8E1),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFFFE082)),
            ),
            child: Text(
              msg,
              style: const TextStyle(fontSize: 12, color: Color(0xFF6D4C00), height: 1.35),
            ),
          ),
        ],
      ],
    );
  }
}

class _ChartCard extends StatelessWidget {
  const _ChartCard({required this.height, required this.child});

  final double height;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      padding: const EdgeInsets.fromLTRB(12, 16, 16, 12),
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
    height: 160,
    alignment: Alignment.center,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: const Color(0xFFE8EBF3)),
    ),
    child: Text(message, textAlign: TextAlign.center, style: TextStyle(color: Colors.grey.shade600)),
  );
}

class _DualTrendChart extends StatelessWidget {
  const _DualTrendChart({required this.charts});

  final BusinessSummaryCharts charts;

  @override
  Widget build(BuildContext context) {
    if (charts.trendLabels.isEmpty) {
      return _emptyChart('No sales or purchase trend for this period.');
    }

    final len = charts.trendLabels.length;
    final maxY = [
      ...charts.trendSales,
      ...charts.trendPurchase,
    ].fold<double>(0, (m, v) => v > m ? v : m);

    return _ChartCard(
      height: 240,
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
                reservedSize: 22,
                interval: len > 8 ? (len / 4).ceilToDouble() : 1,
                getTitlesWidget: (v, _) {
                  final i = v.round();
                  if (i < 0 || i >= len) return const SizedBox.shrink();
                  final label = charts.trendLabels[i];
                  final short = label.length >= 10 ? label.substring(5) : label;
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(short, style: TextStyle(fontSize: 9, color: Colors.grey.shade600)),
                  );
                },
              ),
            ),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: [
                for (var i = 0; i < len; i++) FlSpot(i.toDouble(), charts.trendSales[i]),
              ],
              isCurved: true,
              color: const Color(0xFF5B3DF5),
              barWidth: 2.5,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFF5B3DF5).withValues(alpha: 0.08),
              ),
            ),
            LineChartBarData(
              spots: [
                for (var i = 0; i < len; i++) FlSpot(i.toDouble(), charts.trendPurchase[i]),
              ],
              isCurved: true,
              color: const Color(0xFFEF6C00),
              barWidth: 2.5,
              dotData: const FlDotData(show: false),
            ),
          ],
        ),
      ),
    );
  }
}

class _DailySalesChart extends StatelessWidget {
  const _DailySalesChart({required this.points});

  final List<BusinessSummaryDailyPoint> points;

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) return _emptyChart('No daily sales in this period.');

    final maxY = points.map((p) => p.amount).reduce((a, b) => a > b ? a : b);
    return _ChartCard(
      height: 220,
      child: LineChart(
        LineChartData(
          minY: 0,
          maxY: maxY <= 0 ? 1 : maxY * 1.15,
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
                getTitlesWidget: (v, _) => Text(_fmtMoney(v), style: TextStyle(fontSize: 9, color: Colors.grey.shade600)),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 22,
                interval: points.length > 8 ? (points.length / 4).ceilToDouble() : 1,
                getTitlesWidget: (v, _) {
                  final i = v.round();
                  if (i < 0 || i >= points.length) return const SizedBox.shrink();
                  final d = points[i].date;
                  final short = d.length >= 10 ? d.substring(5) : d;
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(short, style: TextStyle(fontSize: 9, color: Colors.grey.shade600)),
                  );
                },
              ),
            ),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: [for (var i = 0; i < points.length; i++) FlSpot(i.toDouble(), points[i].amount)],
              isCurved: true,
              color: const Color(0xFF1565C0),
              barWidth: 2.5,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(show: true, color: const Color(0xFF1565C0).withValues(alpha: 0.1)),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfitCompareChart extends StatelessWidget {
  const _ProfitCompareChart({required this.charts});

  final BusinessSummaryCharts charts;

  @override
  Widget build(BuildContext context) {
    if (charts.salesVsProfitValues.isEmpty) {
      return _emptyChart('No profit comparison data.');
    }

    final maxY = charts.salesVsProfitValues.reduce((a, b) => a > b ? a : b);
    return _ChartCard(
      height: 200,
      child: BarChart(
        BarChartData(
          maxY: maxY <= 0 ? 1 : maxY * 1.2,
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
                reservedSize: 42,
                getTitlesWidget: (v, _) => Text(_fmtMoney(v), style: TextStyle(fontSize: 9, color: Colors.grey.shade600)),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                getTitlesWidget: (v, _) {
                  final i = v.toInt();
                  if (i < 0 || i >= charts.salesVsProfitLabels.length) return const SizedBox.shrink();
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      charts.salesVsProfitLabels[i],
                      style: TextStyle(fontSize: 10, color: Colors.grey.shade700, fontWeight: FontWeight.w600),
                    ),
                  );
                },
              ),
            ),
          ),
          barGroups: [
            for (var i = 0; i < charts.salesVsProfitValues.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: charts.salesVsProfitValues[i],
                    width: 36,
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
                    color: i == 0 ? const Color(0xFF5B3DF5) : const Color(0xFF2E7D32),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _RankedBars extends StatelessWidget {
  const _RankedBars({required this.items, required this.color, required this.emptyMessage});

  final List<BusinessSummaryEntity> items;
  final Color color;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) return _emptyChart(emptyMessage);

    final maxVal = items.map((e) => e.amount).reduce((a, b) => a > b ? a : b);
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        children: [
          for (var i = 0; i < items.length && i < 8; i++) ...[
            if (i > 0) const SizedBox(height: 10),
            _rankRow(items[i], maxVal, color, i + 1),
          ],
        ],
      ),
    );
  }

  Widget _rankRow(BusinessSummaryEntity item, double maxVal, Color color, int rank) {
    final pct = maxVal > 0 ? (item.amount / maxVal).clamp(0.0, 1.0) : 0.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('$rank.', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.grey.shade600)),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                item.displayName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
              ),
            ),
            Text(_fmtMoneyFull(item.amount), style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: color)),
          ],
        ),
        const SizedBox(height: 4),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: pct,
            minHeight: 6,
            backgroundColor: color.withValues(alpha: 0.1),
            color: color,
          ),
        ),
      ],
    );
  }
}

class _PieBreakdown extends StatelessWidget {
  const _PieBreakdown({required this.items, required this.accent});

  final List<BusinessSummaryEntity> items;
  final Color accent;

  static const _palette = [
    Color(0xFF5B3DF5),
    Color(0xFF1565C0),
    Color(0xFF2E7D32),
    Color(0xFFEF6C00),
    Color(0xFF6A1B9A),
    Color(0xFF00838F),
    Color(0xFFE63946),
    Color(0xFF7B8794),
  ];

  @override
  Widget build(BuildContext context) {
    final total = items.fold<double>(0, (s, e) => s + e.amount);
    if (total <= 0) return _emptyChart('No breakdown data.');

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 120,
            height: 120,
            child: PieChart(
              PieChartData(
                sectionsSpace: 2,
                centerSpaceRadius: 28,
                sections: [
                  for (var i = 0; i < items.length && i < 8; i++)
                    PieChartSectionData(
                      value: items[i].amount,
                      color: _palette[i % _palette.length],
                      radius: 28,
                      title: '',
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              children: [
                for (var i = 0; i < items.length && i < 6; i++) ...[
                  if (i > 0) const SizedBox(height: 6),
                  Row(
                    children: [
                      Container(width: 8, height: 8, decoration: BoxDecoration(color: _palette[i % _palette.length], shape: BoxShape.circle)),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          items[i].displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 11.5),
                        ),
                      ),
                      Text(
                        '${(items[i].amount / total * 100).toStringAsFixed(0)}%',
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: accent),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TransactionList extends StatelessWidget {
  const _TransactionList({required this.rows});

  final List<BusinessSummaryTransactionRow> rows;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return _emptyChart('No transactions in this period.');

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) ...[
            if (i > 0) const Divider(height: 1, indent: 14, endIndent: 14),
            ListTile(
              dense: true,
              title: Text(rows[i].transaction, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
              subtitle: Text('${rows[i].count} txn · ${rows[i].percentage.toStringAsFixed(1)}%'),
              trailing: Text(
                _fmtMoneyFull(rows[i].amount),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: Color(0xFF262C50)),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _FinancialCard extends StatelessWidget {
  const _FinancialCard({required this.financial});

  final BusinessSummaryFinancial financial;

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
        children: [
          _finRow('Net sales', financial.netSales),
          const SizedBox(height: 8),
          _finRow('Gross profit', financial.grossProfit),
          const SizedBox(height: 8),
          _finRow('Gross margin', financial.grossProfitPct, isPercent: true),
          const SizedBox(height: 8),
          _finRow('Net purchases (GRN)', financial.netPurchases),
          const SizedBox(height: 8),
          _finRow('Expenses', financial.expenseTotal),
          const SizedBox(height: 8),
          _finRow('Net profit', financial.netProfit),
        ],
      ),
    );
  }

  Widget _finRow(String label, double value, {bool isPercent = false}) {
    return Row(
      children: [
        Expanded(child: Text(label, style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700))),
        Text(
          isPercent ? '${value.toStringAsFixed(1)}%' : _fmtMoneyFull(value),
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Color(0xFF262C50)),
        ),
      ],
    );
  }
}
