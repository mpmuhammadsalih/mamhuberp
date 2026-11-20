class StockCountSummary {
  StockCountSummary({
    required this.locationcode,
    required this.countNo,
    required this.status,
    this.warehouseId,
    this.countDate = '',
    this.remarks = '',
    this.createdBy = '',
    this.assignedTo = '',
    this.lineCount = 0,
    this.isUnassigned = false,
    this.isMine = false,
  });

  final int locationcode;
  final int countNo;
  final int? warehouseId;
  final String status;
  final String countDate;
  final String remarks;
  final String createdBy;
  final String assignedTo;
  final int lineCount;
  final bool isUnassigned;
  final bool isMine;

  /// ERP may use DRAFT, PENDING, OPEN, etc. — anything except POSTED is editable.
  bool get isEditable => status.toUpperCase() != 'POSTED';

  bool get isDraft => isEditable;

  /// Any non-POSTED count may be opened by any permitted user.
  bool get isLockedByOther => false;

  bool get canOpen => isEditable;

  factory StockCountSummary.fromJson(Map<String, dynamic> json) => StockCountSummary(
        locationcode: (json['locationcode'] as num?)?.toInt() ?? 0,
        countNo: (json['count_no'] as num?)?.toInt() ?? 0,
        warehouseId: (json['warehouse_id'] as num?)?.toInt(),
        status: '${json['status'] ?? ''}',
        countDate: '${json['count_date'] ?? ''}',
        remarks: '${json['remarks'] ?? ''}',
        createdBy: '${json['created_by'] ?? ''}',
        assignedTo: '${json['assigned_to'] ?? ''}',
        lineCount: (json['line_count'] as num?)?.toInt() ?? 0,
        isUnassigned: json['is_unassigned'] == true,
        isMine: json['is_mine'] == true,
      );
}

class StockCountLine {
  StockCountLine({
    required this.lineNo,
    required this.itemcodeDisplay,
    required this.countedQty,
    required this.systemQty,
    required this.varianceQty,
    this.uom = '',
    this.barcode = '',
    this.oldRetailPrice,
    this.newRetailPrice,
  });

  final int lineNo;
  final String itemcodeDisplay;
  final double countedQty;
  final double systemQty;
  final double varianceQty;
  final String uom;
  final String barcode;
  final double? oldRetailPrice;
  final double? newRetailPrice;

  factory StockCountLine.fromJson(Map<String, dynamic> json) => StockCountLine(
        lineNo: (json['line_no'] as num?)?.toInt() ?? 0,
        itemcodeDisplay: '${json['itemcode_display'] ?? json['itemcode'] ?? ''}',
        countedQty: ((json['counted_qty'] ?? 0) as num).toDouble(),
        systemQty: ((json['system_qty'] ?? 0) as num).toDouble(),
        varianceQty: ((json['variance_qty'] ?? 0) as num).toDouble(),
        uom: '${json['uom'] ?? ''}',
        barcode: '${json['barcode'] ?? ''}',
        oldRetailPrice: (json['old_retail_price'] as num?)?.toDouble(),
        newRetailPrice: (json['new_retail_price'] as num?)?.toDouble(),
      );
}

class StockCountPriceHeader {
  StockCountPriceHeader({
    required this.status,
    this.lineCount = 0,
    this.warehouseId,
    this.batchNo,
  });

  final String status;
  final int lineCount;
  final int? warehouseId;
  final int? batchNo;

  factory StockCountPriceHeader.fromJson(Map<String, dynamic> json) =>
      StockCountPriceHeader(
        status: '${json['status'] ?? ''}',
        lineCount: (json['line_count'] as num?)?.toInt() ?? 0,
        warehouseId: (json['warehouse_id'] as num?)?.toInt(),
        batchNo: (json['batch_no'] as num?)?.toInt(),
      );
}

class StockCountSession {
  StockCountSession({
    required this.locationcode,
    required this.countNo,
    required this.status,
    this.warehouseId,
    this.countDate = '',
    this.remarks = '',
    this.pdtDeviceId = '',
    this.lines = const [],
    this.priceHeader,
  });

  final int locationcode;
  final int countNo;
  final int? warehouseId;
  final String status;
  final String countDate;
  final String remarks;
  final String pdtDeviceId;
  final List<StockCountLine> lines;
  final StockCountPriceHeader? priceHeader;

  factory StockCountSession.fromJson(Map<String, dynamic> json) {
    final rawLines = json['lines'];
    final lines = rawLines is List
        ? rawLines
            .whereType<Map>()
            .map((e) => StockCountLine.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : <StockCountLine>[];
    final rawPriceHdr = json['price_header'];
    return StockCountSession(
      locationcode: (json['locationcode'] as num?)?.toInt() ?? 0,
      countNo: (json['count_no'] as num?)?.toInt() ?? 0,
      warehouseId: (json['warehouse_id'] as num?)?.toInt(),
      status: '${json['status'] ?? ''}',
      countDate: '${json['count_date'] ?? ''}',
      remarks: '${json['remarks'] ?? ''}',
      pdtDeviceId: '${json['pdt_device_id'] ?? ''}',
      lines: lines,
      priceHeader: rawPriceHdr is Map
          ? StockCountPriceHeader.fromJson(Map<String, dynamic>.from(rawPriceHdr))
          : null,
    );
  }
}
