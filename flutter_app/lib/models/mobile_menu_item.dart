class MobileMenuItem {
  const MobileMenuItem({
    required this.id,
    required this.label,
    required this.nav,
  });

  final String id;
  final String label;
  final String nav;

  factory MobileMenuItem.fromJson(Map<String, dynamic> json) => MobileMenuItem(
        id: '${json['id'] ?? ''}',
        label: '${json['label'] ?? ''}',
        nav: '${json['nav'] ?? json['label'] ?? ''}',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'label': label,
        'nav': nav,
      };
}

class MobileMenuSection {
  const MobileMenuSection({
    this.section,
    required this.items,
  });

  final String? section;
  final List<MobileMenuItem> items;

  factory MobileMenuSection.fromJson(Map<String, dynamic> json) => MobileMenuSection(
        section: json['section'] as String?,
        items: ((json['items'] ?? []) as List<dynamic>)
            .whereType<Map>()
            .map((e) => MobileMenuItem.fromJson(Map<String, dynamic>.from(e)))
            .where((e) => e.label.isNotEmpty)
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        if (section != null) 'section': section,
        'items': items.map((e) => e.toJson()).toList(),
      };
}
