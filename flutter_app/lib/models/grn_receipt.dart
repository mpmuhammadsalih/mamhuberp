class GrnReceipt {
  GrnReceipt({
    required this.receiptNo,
    required this.supplier,
    required this.poNo,
    required this.invoiceNo,
    required this.receiptDate,
    required this.amount,
    required this.remarks,
    required this.totalQty,
    required this.status,
    this.mobileLinesTouched = 0,
    this.mobileLastSavedAt,
    this.canEdit = false,
    this.canDelete = false,
    this.inventoryPosted = false,
  });

  final String receiptNo;
  final String supplier;
  final String poNo;
  final String invoiceNo;
  final String receiptDate;
  final double amount;
  final String remarks;
  final double totalQty;
  /// API keyword; use [grnStatusChipLabel] for display.
  final String status;
  /// From list API (`mobile_lines_touched`).
  final int mobileLinesTouched;
  /// ISO-ish timestamp from ERP optional (`mobile_last_saved_at`).
  final String? mobileLastSavedAt;
  final bool canEdit;
  final bool canDelete;
  final bool inventoryPosted;

  factory GrnReceipt.fromJson(Map<String, dynamic> json) {
    double asDouble(dynamic value) {
      if (value == null) return 0;
      if (value is num) return value.toDouble();
      return double.tryParse(value.toString()) ?? 0;
    }

    int asInt(dynamic value) {
      if (value == null) return 0;
      if (value is int) return value;
      if (value is num) return value.round();
      return int.tryParse(value.toString()) ?? 0;
    }

    String asString(dynamic value) => value?.toString() ?? '';
    bool asBool(dynamic value) => value == true || value == 1 || value == '1' || value == 'Y' || value == 'y';

    final status = asString(json['status']).isEmpty ? 'Pending' : asString(json['status']);
    final isDraft = status.toLowerCase() == 'draft';

    return GrnReceipt(
      receiptNo: asString(json['receipt_no']),
      supplier: asString(json['supplier']),
      poNo: asString(json['po_no']),
      invoiceNo: asString(json['invoice_no']),
      receiptDate: asString(json['receipt_date']),
      amount: asDouble(json['amount']),
      remarks: asString(json['remarks']),
      totalQty: asDouble(json['total_qty']),
      status: status,
      mobileLinesTouched: asInt(json['mobile_lines_touched']),
      mobileLastSavedAt: json['mobile_last_saved_at'] == null ? null : asString(json['mobile_last_saved_at']),
      canEdit: json.containsKey('can_edit') ? asBool(json['can_edit']) : isDraft,
      canDelete: json.containsKey('can_delete') ? asBool(json['can_delete']) : isDraft,
      inventoryPosted: asBool(json['inventory_posted']),
    );
  }
}
