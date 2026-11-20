class AppCatalogInfo {
  AppCatalogInfo({
    required this.connected,
    this.username = '',
    this.dsn = '',
    this.error,
  });

  final bool connected;
  final String username;
  final String dsn;
  final String? error;

  factory AppCatalogInfo.fromJson(Map<String, dynamic> json) => AppCatalogInfo(
        connected: json['connected'] == true,
        username: '${json['username'] ?? ''}',
        dsn: '${json['dsn'] ?? ''}',
        error: json['error']?.toString(),
      );
}

class AppTenantOption {
  AppTenantOption({
    required this.tenantId,
    required this.displayName,
    this.erpDsn = '',
    this.erpUsername = '',
    this.ip = '',
    this.port = 1521,
    this.serviceName = '',
    this.active = true,
  });

  final String tenantId;
  final String displayName;
  final String erpDsn;
  final String erpUsername;
  final String ip;
  final int port;
  final String serviceName;
  final bool active;

  factory AppTenantOption.fromJson(Map<String, dynamic> json) => AppTenantOption(
        tenantId: '${json['tenant_id'] ?? ''}'.trim(),
        displayName: '${json['display_name'] ?? json['tenant_id'] ?? ''}'.trim(),
        erpDsn: '${json['erp_dsn'] ?? ''}',
        erpUsername: '${json['erp_username'] ?? ''}',
        ip: '${json['ip'] ?? ''}',
        port: (json['port'] as num?)?.toInt() ?? 1521,
        serviceName: '${json['service_name'] ?? ''}',
        active: json['active'] != false,
      );
}

class AppConfig {
  AppConfig({
    required this.authCatalog,
    required this.tenants,
  });

  final AppCatalogInfo authCatalog;
  final List<AppTenantOption> tenants;

  factory AppConfig.fromJson(Map<String, dynamic> json) {
    final data = json;
    final catalogRaw = data['auth_catalog'];
    final catalog = catalogRaw is Map<String, dynamic>
        ? AppCatalogInfo.fromJson(catalogRaw)
        : AppCatalogInfo(connected: false);
    final list = (data['tenants'] as List<dynamic>? ?? [])
        .whereType<Map>()
        .map((e) => AppTenantOption.fromJson(Map<String, dynamic>.from(e)))
        .where((t) => t.tenantId.isNotEmpty)
        .toList();
    return AppConfig(authCatalog: catalog, tenants: list);
  }
}
