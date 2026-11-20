class StockTransferStore {
  const StockTransferStore({required this.code, required this.description});

  final String code;
  final String description;

  String get label => description.isNotEmpty ? '$code — $description' : code;

  factory StockTransferStore.fromJson(Map<String, dynamic> json) => StockTransferStore(
        code: '${json['code'] ?? ''}'.trim(),
        description: '${json['description'] ?? ''}'.trim(),
      );
}

class StockTransferSummary {
  StockTransferSummary({
    required this.transferNo,
    required this.transferDate,
    required this.fromStore,
    required this.toStore,
    required this.status,
    required this.statusLabel,
    this.createdBy = '',
    this.remarks = '',
  });

  final String transferNo;
  final String transferDate;
  final String fromStore;
  final String toStore;
  final String status;
  final String statusLabel;
  final String createdBy;
  final String remarks;

  bool get isCreated => status.toUpperCase() == 'C';
  bool get isInTransit => {'T', 'P'}.contains(status.toUpperCase());
  bool get isApproved => status.toUpperCase() == 'A';

  factory StockTransferSummary.fromJson(Map<String, dynamic> json) => StockTransferSummary(
        transferNo: _asDocNo(json['transferno'] ?? json['transfer_no']),
        transferDate: '${json['transferdate'] ?? ''}',
        fromStore: '${json['fromstore'] ?? ''}',
        toStore: '${json['tostore'] ?? ''}',
        status: '${json['status'] ?? ''}',
        statusLabel: '${json['status_label'] ?? json['status'] ?? ''}',
        createdBy: '${json['createdby'] ?? ''}',
        remarks: '${json['remarks'] ?? ''}',
      );
}

class StockTransferLine {
  StockTransferLine({
    required this.slNo,
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.availableQty,
    required this.transferQty,
    this.remarks = '',
  });

  final int slNo;
  final int itemCode;
  final String itemName;
  final String uom;
  final double availableQty;
  final double transferQty;
  final String remarks;

  Map<String, dynamic> toSaveJson() => {
        'item_code': itemCode,
        'item_name': itemName,
        'uom': uom,
        'available_qty': availableQty,
        'transfer_qty': transferQty,
        'remarks': remarks,
      };

  factory StockTransferLine.fromJson(Map<String, dynamic> json) => StockTransferLine(
        slNo: (json['slno'] as num?)?.toInt() ?? 0,
        itemCode: (json['itemcode'] as num?)?.toInt() ?? 0,
        itemName: '${json['itemname'] ?? ''}',
        uom: '${json['uom'] ?? 'NOS'}',
        availableQty: (json['availableqty'] as num?)?.toDouble() ?? 0,
        transferQty: (json['transferqty'] as num?)?.toDouble() ?? 0,
        remarks: '${json['lineremarks'] ?? json['remarks'] ?? ''}',
      );
}

class StockTransferItemOption {
  StockTransferItemOption({
    required this.itemCode,
    required this.itemName,
    required this.uom,
    required this.availableQty,
    this.barcode = '',
    this.actualQty = 0,
    this.pendingQty = 0,
  });

  final int itemCode;
  final String itemName;
  final String uom;
  final double availableQty;
  final String barcode;
  final double actualQty;
  final double pendingQty;

  factory StockTransferItemOption.fromJson(Map<String, dynamic> json) => StockTransferItemOption(
        itemCode: _asInt(json['itemcode'] ?? json['item_code'] ?? json['ITEMCODE']),
        itemName: '${json['itemname'] ?? json['item_name'] ?? json['ITEMNAME'] ?? ''}',
        uom: '${json['uom'] ?? json['UOM'] ?? 'NOS'}',
        availableQty: _asDouble(json['availableqty'] ?? json['available_qty'] ?? json['AVAILABLEQTY']),
        barcode: '${json['barcode'] ?? json['BARCODE'] ?? ''}',
        actualQty: _asDouble(json['actualqty'] ?? json['actual_qty'] ?? json['ACTUALQTY']),
        pendingQty: _asDouble(json['pendingqty'] ?? json['pending_qty'] ?? json['PENDINGQTY']),
      );
}

class StockTransferItemStock {
  const StockTransferItemStock({
    required this.currentQty,
    required this.actualQty,
    required this.pendingQty,
  });

  final double currentQty;
  final double actualQty;
  final double pendingQty;

  factory StockTransferItemStock.fromJson(Map<String, dynamic> json) => StockTransferItemStock(
        currentQty: _asDouble(json['current_qty']),
        actualQty: _asDouble(json['actual_qty']),
        pendingQty: _asDouble(json['pending_qty']),
      );
}

String _asDocNo(dynamic value) {
  if (value == null) return '';
  final s = '$value'.trim();
  if (s.isEmpty || s == '0' || s == 'null') return '';
  return s;
}

int _asInt(dynamic value) {
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value.trim()) ?? 0;
  return 0;
}

double _asDouble(dynamic value) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value.trim()) ?? 0;
  return 0;
}

class StockTransferDetail {
  StockTransferDetail({
    required this.header,
    required this.lines,
  });

  final Map<String, dynamic> header;
  final List<StockTransferLine> lines;

  String get transferNo => _asDocNo(header['transferno'] ?? header['transfer_no']);
  String get status => '${header['status'] ?? ''}'.toUpperCase();
  String get statusLabel => '${header['status_label'] ?? status}';
  String get fromStore => '${header['fromstore'] ?? ''}';
  String get toStore => '${header['tostore'] ?? ''}';
  String get transferDate => '${header['transferdate'] ?? ''}';
  String get remarks => '${header['remarks'] ?? ''}';

  bool get isCreated => status == 'C';
  bool get isInTransit => status == 'T' || status == 'P';
  bool get isApproved => status == 'A';
  bool get canEdit => isCreated;

  factory StockTransferDetail.fromJson(Map<String, dynamic> json) {
    final hdr = Map<String, dynamic>.from(json['header'] as Map? ?? {});
    final rawLines = (json['lines'] as List<dynamic>? ?? [])
        .whereType<Map>()
        .map((e) => StockTransferLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return StockTransferDetail(header: hdr, lines: rawLines);
  }
}
