class DashboardRecentReceipt {
  DashboardRecentReceipt({
    required this.receiptNo,
    required this.poNo,
    required this.supplier,
    required this.invoiceNo,
    required this.receiptDate,
    required this.amount,
    required this.status,
  });

  final String receiptNo;
  final String poNo;
  final String supplier;
  final String invoiceNo;
  final String receiptDate;
  final double amount;
  final String status;

  factory DashboardRecentReceipt.fromJson(Map<String, dynamic> json) => DashboardRecentReceipt(
        receiptNo: '${json['receipt_no'] ?? ''}',
        poNo: '${json['po_no'] ?? ''}',
        supplier: '${json['supplier'] ?? ''}',
        invoiceNo: '${json['invoice_no'] ?? ''}',
        receiptDate: '${json['receipt_date'] ?? ''}',
        amount: _numToDouble(json['amount']),
        status: '${json['status'] ?? ''}',
      );
}

class DashboardTopCustomer {
  DashboardTopCustomer({
    required this.code,
    required this.name,
    required this.sales,
    this.invoices = 0,
  });

  final String code;
  final String name;
  final double sales;
  final int invoices;

  factory DashboardTopCustomer.fromJson(Map<String, dynamic> json) => DashboardTopCustomer(
        code: '${json['code'] ?? ''}'.trim(),
        name: '${json['name'] ?? 'Customer'}'.trim(),
        sales: _numToDouble(json['sales'] ?? json['amount'] ?? json['today_amount']),
        invoices: _numToInt(json['invoices'] ?? json['count']),
      );
}

class DashboardActivityItem {
  DashboardActivityItem({
    required this.type,
    required this.title,
    required this.subtitle,
    required this.amount,
    this.ref = '',
    this.time = '',
    this.signed = 1,
  });

  final String type;
  final String title;
  final String subtitle;
  final String ref;
  final String time;
  final double amount;
  final int signed;

  factory DashboardActivityItem.fromJson(Map<String, dynamic> json) => DashboardActivityItem(
        type: '${json['type'] ?? ''}'.trim(),
        title: '${json['title'] ?? ''}'.trim(),
        subtitle: '${json['subtitle'] ?? ''}'.trim(),
        ref: '${json['ref'] ?? ''}'.trim(),
        time: '${json['time'] ?? ''}'.trim(),
        amount: _numToDouble(json['amount']),
        signed: _numToInt(json['signed']) == 0 ? 1 : _numToInt(json['signed']),
      );
}

class DashboardAlertItem {
  DashboardAlertItem({
    required this.severity,
    required this.title,
    this.subtitle = '',
  });

  final String severity;
  final String title;
  final String subtitle;

  factory DashboardAlertItem.fromJson(Map<String, dynamic> json) => DashboardAlertItem(
        severity: '${json['severity'] ?? 'info'}'.trim().toLowerCase(),
        title: '${json['title'] ?? ''}'.trim(),
        subtitle: '${json['subtitle'] ?? ''}'.trim(),
      );
}

double _numToDouble(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? 0;
}

int _numToInt(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? 0;
}

class DashboardSummary {
  DashboardSummary({
    required this.totalItems,
    required this.todaySales,
    required this.customerCount,
    required this.totalStockQty,
    required this.outOfStockItems,
    required this.lowStockItems,
    required this.stockValue,
    required this.recentReceipts,
    this.billHdrRowsToday = 0,
    this.branchName = '',
    this.periodLabel = 'Today',
    this.dateFrom = '',
    this.dateTo = '',
    this.yesterdaySales = 0,
    this.salesTrendPct = 0,
    this.invoiceCount = 0,
    this.invoiceTrendPct = 0,
    this.cashSales = 0,
    this.creditSales = 0,
    this.amountCollected = 0,
    this.outstandingAmount = 0,
    this.collectionPct = 0,
    this.salesReturn = 0,
    this.returnCount = 0,
    this.salesOrdersToday = 0,
    this.newCustomersToday = 0,
    this.topCustomers = const [],
    this.purchases = 0,
    this.expenses = 0,
    this.grossProfit = 0,
    this.netProfit = 0,
    this.purchasesTrendPct = 0,
    this.expensesTrendPct = 0,
    this.grossProfitTrendPct = 0,
    this.netProfitTrendPct = 0,
    this.inventoryValue = 0,
    this.itemsInStock = 0,
    this.receivablesOverdue = 0,
    this.receivablesNotDue = 0,
    this.payablesTotal = 0,
    this.payablesOverdue = 0,
    this.payablesNotDue = 0,
    this.cashBalance = 0,
    this.bankBalance = 0,
    this.cashBankTotal = 0,
    this.recentActivity = const [],
    this.alerts = const [],
    this.visitsToday = 0,
  });

  final int totalItems;
  final double todaySales;
  final int customerCount;
  final double totalStockQty;
  final int outOfStockItems;
  final int lowStockItems;
  final double stockValue;
  final List<DashboardRecentReceipt> recentReceipts;
  final int billHdrRowsToday;
  final String branchName;
  final String periodLabel;
  final String dateFrom;
  final String dateTo;
  final double yesterdaySales;
  final double salesTrendPct;
  final int invoiceCount;
  final double invoiceTrendPct;
  final double cashSales;
  final double creditSales;
  final double amountCollected;
  final double outstandingAmount;
  final double collectionPct;
  final double salesReturn;
  final int returnCount;
  final int salesOrdersToday;
  final int newCustomersToday;
  final List<DashboardTopCustomer> topCustomers;

  final double purchases;
  final double expenses;
  final double grossProfit;
  final double netProfit;
  final double purchasesTrendPct;
  final double expensesTrendPct;
  final double grossProfitTrendPct;
  final double netProfitTrendPct;
  final double inventoryValue;
  final int itemsInStock;
  final double receivablesOverdue;
  final double receivablesNotDue;
  final double payablesTotal;
  final double payablesOverdue;
  final double payablesNotDue;
  final double cashBalance;
  final double bankBalance;
  final double cashBankTotal;
  final List<DashboardActivityItem> recentActivity;
  final List<DashboardAlertItem> alerts;
  final int visitsToday;

  factory DashboardSummary.fromJson(Map<String, dynamic> json) => DashboardSummary(
        totalItems: _numToInt(json['total_items']),
        todaySales: _numToDouble(json['today_sales']),
        customerCount: _numToInt(json['customer_count'] ?? json['active_customers']),
        totalStockQty: _numToDouble(json['total_stock_qty']),
        outOfStockItems: _numToInt(json['out_of_stock_items']),
        lowStockItems: _numToInt(json['low_stock_items']),
        stockValue: _numToDouble(json['stock_value']),
        billHdrRowsToday: _numToInt(json['billhdr_rows_today']),
        branchName: '${json['branch_name'] ?? json['location_name'] ?? ''}'.trim(),
        periodLabel: '${json['period_label'] ?? 'Today'}'.trim().isEmpty
            ? 'Today'
            : '${json['period_label']}'.trim(),
        dateFrom: '${json['date_from'] ?? ''}'.trim(),
        dateTo: '${json['date_to'] ?? ''}'.trim(),
        yesterdaySales: _numToDouble(json['yesterday_sales']),
        salesTrendPct: _numToDouble(json['sales_trend_pct']),
        invoiceCount: _numToInt(json['invoice_count'] ?? json['billhdr_rows_today']),
        invoiceTrendPct: _numToDouble(json['invoice_trend_pct']),
        cashSales: _numToDouble(json['cash_sales']),
        creditSales: _numToDouble(json['credit_sales']),
        amountCollected: _numToDouble(json['amount_collected']),
        outstandingAmount: _numToDouble(json['outstanding_amount']),
        collectionPct: _numToDouble(json['collection_pct']),
        salesReturn: _numToDouble(json['sales_return']),
        returnCount: _numToInt(json['return_count']),
        salesOrdersToday: _numToInt(json['sales_orders_today']),
        newCustomersToday: _numToInt(json['new_customers_today']),
        purchases: _numToDouble(json['purchases']),
        expenses: _numToDouble(json['expenses']),
        grossProfit: _numToDouble(json['gross_profit']),
        netProfit: _numToDouble(json['net_profit']),
        purchasesTrendPct: _numToDouble(json['purchases_trend_pct']),
        expensesTrendPct: _numToDouble(json['expenses_trend_pct']),
        grossProfitTrendPct: _numToDouble(json['gross_profit_trend_pct']),
        netProfitTrendPct: _numToDouble(json['net_profit_trend_pct']),
        inventoryValue: _numToDouble(json['inventory_value'] ?? json['stock_value']),
        itemsInStock: _numToInt(json['items_in_stock']),
        receivablesOverdue: _numToDouble(json['receivables_overdue']),
        receivablesNotDue: _numToDouble(json['receivables_not_due'] ?? json['outstanding_amount']),
        payablesTotal: _numToDouble(json['payables_total']),
        payablesOverdue: _numToDouble(json['payables_overdue']),
        payablesNotDue: _numToDouble(json['payables_not_due'] ?? json['payables_total']),
        cashBalance: _numToDouble(json['cash_balance']),
        bankBalance: _numToDouble(json['bank_balance']),
        cashBankTotal: _numToDouble(json['cash_bank_total']),
        visitsToday: _numToInt(json['visits_today']),
        recentReceipts: (json['recent_receipts'] as List<dynamic>?)
                ?.map((e) => DashboardRecentReceipt.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        topCustomers: (json['top_customers'] as List<dynamic>?)
                ?.whereType<Map>()
                .map((e) => DashboardTopCustomer.fromJson(Map<String, dynamic>.from(e)))
                .toList() ??
            const [],
        recentActivity: (json['recent_activity'] as List<dynamic>?)
                ?.whereType<Map>()
                .map((e) => DashboardActivityItem.fromJson(Map<String, dynamic>.from(e)))
                .toList() ??
            const [],
        alerts: (json['alerts'] as List<dynamic>?)
                ?.whereType<Map>()
                .map((e) => DashboardAlertItem.fromJson(Map<String, dynamic>.from(e)))
                .toList() ??
            const [],
      );
}
