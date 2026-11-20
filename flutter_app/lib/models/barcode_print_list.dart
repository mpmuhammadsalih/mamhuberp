class BarcodePrintListSummary {
  BarcodePrintListSummary({
    required this.printNo,
    required this.locationcode,
    this.printDate,
    this.listType = 'PRODUCT',
    this.status = 'READY',
    this.remarks = '',
    this.lineCount = 0,
    this.labelCount = 0,
    this.createdBy = '',
  });

  final int printNo;
  final int locationcode;
  final String? printDate;
  final String listType;
  final String status;
  final String remarks;
  final int lineCount;
  final int labelCount;
  final String createdBy;

  factory BarcodePrintListSummary.fromJson(Map<String, dynamic> json) {
    String asString(dynamic v) => v == null ? '' : v.toString();
    int asInt(dynamic v) {
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? 0;
    }

    return BarcodePrintListSummary(
      printNo: asInt(json['print_no']),
      locationcode: asInt(json['locationcode']),
      printDate: asString(json['print_date']).isEmpty ? null : asString(json['print_date']),
      listType: asString(json['list_type']).isEmpty ? 'PRODUCT' : asString(json['list_type']),
      status: asString(json['status']).isEmpty ? 'READY' : asString(json['status']),
      remarks: asString(json['remarks']),
      lineCount: asInt(json['line_count']),
      labelCount: asInt(json['label_count']),
      createdBy: asString(json['created_by']),
    );
  }
}

class BarcodePrintListLine {
  BarcodePrintListLine({
    this.lineNo = 0,
    this.itemCode = '',
    this.itemName = '',
    required this.barcode,
    this.uom = 'PCS',
    this.retailPrice = 0,
    this.printQty = 1,
    this.storageId,
    this.storageType = '',
    this.storageCode = '',
    this.storageName = '',
    this.pathText = '',
  });

  final int lineNo;
  final String itemCode;
  final String itemName;
  final String barcode;
  final String uom;
  final double retailPrice;
  int printQty;
  final int? storageId;
  final String storageType;
  final String storageCode;
  final String storageName;
  final String pathText;

  String get displayName {
    if (itemName.trim().isNotEmpty) return itemName.trim();
    if (storageName.trim().isNotEmpty) return storageName.trim();
    if (storageCode.trim().isNotEmpty) return storageCode.trim();
    return barcode;
  }

  Map<String, dynamic> toJson() => {
        'itemcode': itemCode.trim().isEmpty ? null : itemCode.trim(),
        'itemname': itemName,
        'barcode': barcode,
        'uom': uom,
        'retail_price': retailPrice,
        'print_qty': printQty,
        if (storageId != null) 'storage_id': storageId,
        'storage_type': storageType,
        'storage_code': storageCode,
        'storage_name': storageName,
        'path_text': pathText,
      };

  factory BarcodePrintListLine.fromJson(Map<String, dynamic> json) {
    String asString(dynamic v) => v == null ? '' : v.toString();
    int asInt(dynamic v) {
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? 0;
    }

    double asDouble(dynamic v) {
      if (v is num) return v.toDouble();
      return double.tryParse('$v') ?? 0;
    }

    final sid = asInt(json['storage_id']);
    return BarcodePrintListLine(
      lineNo: asInt(json['line_no']),
      itemCode: asString(json['itemcode']),
      itemName: asString(json['itemname']),
      barcode: asString(json['barcode']),
      uom: asString(json['uom']).isEmpty ? 'PCS' : asString(json['uom']),
      retailPrice: asDouble(json['retail_price'] ?? json['retailprice']),
      printQty: (() {
        final q = asInt(json['print_qty'] ?? json['print_count']);
        return q <= 0 ? 1 : q;
      })(),
      storageId: sid > 0 ? sid : null,
      storageType: asString(json['storage_type']),
      storageCode: asString(json['storage_code']),
      storageName: asString(json['storage_name']),
      pathText: asString(json['path_text'] ?? json['path']),
    );
  }
}

class BarcodePrintListDocument {
  BarcodePrintListDocument({
    required this.printNo,
    required this.locationcode,
    this.printDate,
    this.listType = 'PRODUCT',
    this.status = 'READY',
    this.remarks = '',
    this.lines = const [],
  });

  final int printNo;
  final int locationcode;
  final String? printDate;
  final String listType;
  final String status;
  final String remarks;
  final List<BarcodePrintListLine> lines;

  factory BarcodePrintListDocument.fromJson(Map<String, dynamic> json) {
    String asString(dynamic v) => v == null ? '' : v.toString();
    int asInt(dynamic v) {
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? 0;
    }

    final rawLines = (json['lines'] as List<dynamic>? ?? [])
        .whereType<Map>()
        .map((e) => BarcodePrintListLine.fromJson(Map<String, dynamic>.from(e)))
        .toList();

    return BarcodePrintListDocument(
      printNo: asInt(json['print_no']),
      locationcode: asInt(json['locationcode']),
      printDate: asString(json['print_date']).isEmpty ? null : asString(json['print_date']),
      listType: asString(json['list_type']).isEmpty ? 'PRODUCT' : asString(json['list_type']),
      status: asString(json['status']).isEmpty ? 'READY' : asString(json['status']),
      remarks: asString(json['remarks']),
      lines: rawLines,
    );
  }
}
