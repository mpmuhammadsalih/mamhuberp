class TenantOption {
  TenantOption({
    required this.tenantId,
    required this.displayName,
  });

  final String tenantId;
  final String displayName;

  factory TenantOption.fromJson(Map<String, dynamic> json) {
    String s(dynamic v) => v == null ? '' : (v is String ? v : v.toString());
    final id = s(json['tenant_id']);
    final name = s(json['display_name']);
    return TenantOption(
      tenantId: id,
      displayName: name.isNotEmpty ? name : id,
    );
  }
}

