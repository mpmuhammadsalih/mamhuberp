class StorageLocation {
  StorageLocation({
    required this.storageId,
    required this.storageType,
    required this.code,
    required this.name,
    this.status = '',
    this.barcode = '',
    this.path = '',
    this.warehouseId,
    this.locationCode,
  });

  final int storageId;
  final String storageType;
  final String code;
  final String name;
  final String status;
  final String barcode;
  final String path;
  final int? warehouseId;
  final int? locationCode;

  String get printValue {
    final bc = barcode.trim();
    if (bc.isNotEmpty) return bc;
    return code.trim();
  }

  String get typeLabel {
    final t = storageType.trim().toUpperCase();
    if (t.isEmpty) return 'Storage';
    return t[0] + t.substring(1).toLowerCase();
  }

  factory StorageLocation.fromJson(Map<String, dynamic> json) {
    String asString(dynamic v) => v == null ? '' : v.toString();
    int? asInt(dynamic v) {
      if (v == null) return null;
      if (v is num) return v.toInt();
      return int.tryParse(v.toString());
    }

    final barcode = asString(json['barcode']);
    final printValue = asString(json['print_value']);
    return StorageLocation(
      storageId: asInt(json['storage_id']) ?? 0,
      storageType: asString(json['storage_type']),
      code: asString(json['code']),
      name: asString(json['name']),
      status: asString(json['status']),
      barcode: barcode.isNotEmpty ? barcode : printValue,
      path: asString(json['path']),
      warehouseId: asInt(json['warehouse_id']),
      locationCode: asInt(json['location_code'] ?? json['locationcode']),
    );
  }
}
