import 'mobile_menu_item.dart';

class UserModel {
  UserModel({
    required this.username,
    required this.roleId,
    required this.employeeCode,
    this.tenantId,
    this.permissions = const [],
    this.mobileMenus = const [],
    this.allowAllPermissions = false,
  });

  final String username;
  final String roleId;
  final String employeeCode;
  final String? tenantId;
  final List<String> permissions;
  final List<MobileMenuSection> mobileMenus;
  final bool allowAllPermissions;

  bool hasMenuPath(String path) {
    if (allowAllPermissions) return true;
    final key = path.trim();
    if (key.isEmpty) return true;
    return permissions.contains(key);
  }

  bool get canAccessTransactionDateSetup {
    if (allowAllPermissions) return true;
    return hasMenuPath('setup.transaction_date_setup') ||
        hasMenuPath('mobile.transaction_date_setup');
  }

  bool canNavigate(String navLabel) {
    if (allowAllPermissions) return true;
    if (navLabel == 'Settings' || navLabel == 'Transaction Date Setup') return true;
    for (final section in mobileMenus) {
      for (final item in section.items) {
        if (item.nav == navLabel) return true;
      }
    }
    return false;
  }

  static String _str(dynamic v) {
    if (v == null) return '';
    if (v is String) return v;
    return v.toString();
  }

  static String? _strOrNull(dynamic v) {
    if (v == null) return null;
    final s = _str(v);
    return s.isEmpty ? null : s;
  }

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
        username: _str(json['username']),
        roleId: _str(json['role_id']),
        employeeCode: _str(json['employeecode']),
        tenantId: _strOrNull(json['tenant_id']),
        permissions: ((json['permissions'] ?? []) as List<dynamic>)
            .map((e) => e.toString())
            .where((e) => e.isNotEmpty)
            .toList(),
        mobileMenus: ((json['mobile_menus'] ?? []) as List<dynamic>)
            .whereType<Map>()
            .map((e) => MobileMenuSection.fromJson(Map<String, dynamic>.from(e)))
            .where((s) => s.items.isNotEmpty)
            .toList(),
        allowAllPermissions: json['allow_all_permissions'] == true,
      );

  Map<String, dynamic> toJson() => {
        'username': username,
        'role_id': roleId,
        'employeecode': employeeCode,
        'tenant_id': tenantId,
        'permissions': permissions,
        'mobile_menus': mobileMenus.map((e) => e.toJson()).toList(),
        'allow_all_permissions': allowAllPermissions,
      };

  UserModel copyWith({
    String? username,
    String? roleId,
    String? employeeCode,
    String? tenantId,
    List<String>? permissions,
    List<MobileMenuSection>? mobileMenus,
    bool? allowAllPermissions,
  }) {
    return UserModel(
      username: username ?? this.username,
      roleId: roleId ?? this.roleId,
      employeeCode: employeeCode ?? this.employeeCode,
      tenantId: tenantId ?? this.tenantId,
      permissions: permissions ?? this.permissions,
      mobileMenus: mobileMenus ?? this.mobileMenus,
      allowAllPermissions: allowAllPermissions ?? this.allowAllPermissions,
    );
  }
}

