import '../core/network/api_client.dart';

String _str(dynamic v) => '${v ?? ''}'.trim();

int _int(dynamic v) {
  if (v == null) return 0;
  if (v is int) return v;
  if (v is num) return v.round();
  return int.tryParse('$v'.trim()) ?? 0;
}

Map<String, dynamic> _data(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  if (data is Map) return Map<String, dynamic>.from(data);
  return root;
}

class CategoryMasterRow {
  CategoryMasterRow({
    required this.code,
    required this.name,
    required this.flag,
    required this.levelName,
    required this.level,
    this.parentMainCode,
    this.parentCategoryCode,
    this.children = const [],
  });

  final int code;
  final String name;
  final String flag;
  final String levelName;
  final int level;
  final int? parentMainCode;
  final int? parentCategoryCode;
  final List<CategoryMasterRow> children;

  bool get hasChildren => children.isNotEmpty;

  String get nodeKey => '$flag:$code';

  factory CategoryMasterRow.fromJson(Map<String, dynamic> json, {int level = 0}) {
    final pmc = _int(json['parent_main_code']);
    final pcc = _int(json['parent_category_code']);
    final flag = _str(json['flag']).toUpperCase();
    final kids = <CategoryMasterRow>[];
    final rawKids = json['children'];
    if (rawKids is List) {
      for (final c in rawKids) {
        if (c is Map) {
          kids.add(CategoryMasterRow.fromJson(Map<String, dynamic>.from(c), level: level + 1));
        }
      }
    }
    return CategoryMasterRow(
      code: _int(json['code']),
      name: _str(json['name']),
      flag: flag,
      levelName: _str(json['level_name']).isNotEmpty
          ? _str(json['level_name'])
          : (flag == 'M'
              ? 'Main category'
              : flag == 'D'
                  ? 'Category'
                  : 'Micro category'),
      level: level,
      parentMainCode: pmc > 0 ? pmc : null,
      parentCategoryCode: pcc > 0 ? pcc : null,
      children: kids,
    );
  }
}

class CategoryMasterPayload {
  CategoryMasterPayload({required this.tree, required this.rows});

  final List<CategoryMasterRow> tree;
  final List<CategoryMasterRow> rows;
}

class BrandMasterRow {
  BrandMasterRow({
    required this.code,
    required this.name,
    required this.flag,
  });

  final int code;
  final String name;
  final String flag;

  String get typeLabel {
    switch (flag) {
      case 'Z':
        return 'Shelf';
      case 'L':
        return 'Color';
      default:
        return 'Brand';
    }
  }

  factory BrandMasterRow.fromJson(Map<String, dynamic> json) => BrandMasterRow(
        code: _int(json['code']),
        name: _str(json['name']),
        flag: _str(json['flag']).toUpperCase(),
      );
}

class CategoryBrandMasterService {
  CategoryBrandMasterService(this._apiClient);

  final ApiClient _apiClient;

  Future<CategoryMasterPayload> listCategories({String q = ''}) async {
    final response = await _apiClient.dio.get(
      '/api/v1/category-master',
      queryParameters: {if (q.isNotEmpty) 'q': q},
    );
    final data = _data(response.data as Map<String, dynamic>);
    final tree = <CategoryMasterRow>[];
    final rawTree = data['tree'];
    if (rawTree is List) {
      for (final r in rawTree) {
        if (r is Map) tree.add(CategoryMasterRow.fromJson(Map<String, dynamic>.from(r)));
      }
    }
    final rows = <CategoryMasterRow>[];
    final rawRows = data['rows'];
    if (rawRows is List) {
      for (final r in rawRows) {
        if (r is Map) rows.add(CategoryMasterRow.fromJson(Map<String, dynamic>.from(r)));
      }
    }
    // When API returns filtered flat rows only, rebuild a shallow tree from rows.
    if (tree.isEmpty && rows.isNotEmpty) {
      return CategoryMasterPayload(tree: _treeFromFlat(rows), rows: rows);
    }
    if (q.isNotEmpty && tree.isNotEmpty) {
      return CategoryMasterPayload(tree: _filterTree(tree, q.toUpperCase()), rows: rows);
    }
    return CategoryMasterPayload(tree: tree, rows: rows);
  }

  List<CategoryMasterRow> _filterTree(List<CategoryMasterRow> nodes, String q) {
    final out = <CategoryMasterRow>[];
    for (final n in nodes) {
      final kids = _filterTree(n.children, q);
      final self =
          n.name.toUpperCase().contains(q) || '${n.code}'.contains(q) || n.levelName.toUpperCase().contains(q);
      if (self || kids.isNotEmpty) {
        out.add(
          CategoryMasterRow(
            code: n.code,
            name: n.name,
            flag: n.flag,
            levelName: n.levelName,
            level: n.level,
            parentMainCode: n.parentMainCode,
            parentCategoryCode: n.parentCategoryCode,
            children: kids,
          ),
        );
      }
    }
    return out;
  }

  List<CategoryMasterRow> _treeFromFlat(List<CategoryMasterRow> flat) {
    final mains = <CategoryMasterRow>[];
    final depts = <int, List<CategoryMasterRow>>{};
    final micros = <int, List<CategoryMasterRow>>{};
    for (final r in flat) {
      if (r.flag == 'M') {
        mains.add(r);
      } else if (r.flag == 'D') {
        final key = r.parentMainCode ?? 0;
        depts.putIfAbsent(key, () => []).add(r);
      } else if (r.flag == 'C') {
        final key = r.parentCategoryCode ?? 0;
        micros.putIfAbsent(key, () => []).add(r);
      }
    }
    return [
      for (final m in mains)
        CategoryMasterRow(
          code: m.code,
          name: m.name,
          flag: m.flag,
          levelName: m.levelName,
          level: 0,
          children: [
            for (final d in depts[m.code] ?? const <CategoryMasterRow>[])
              CategoryMasterRow(
                code: d.code,
                name: d.name,
                flag: d.flag,
                levelName: d.levelName,
                level: 1,
                parentMainCode: m.code,
                children: [
                  for (final c in micros[d.code] ?? const <CategoryMasterRow>[])
                    CategoryMasterRow(
                      code: c.code,
                      name: c.name,
                      flag: c.flag,
                      levelName: c.levelName,
                      level: 2,
                      parentMainCode: m.code,
                      parentCategoryCode: d.code,
                    ),
                ],
              ),
          ],
        ),
    ];
  }

  Future<Map<String, dynamic>> createCategory({
    required String flag,
    required String name,
    int? mainCode,
    int? dCode,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/category-master',
      data: {
        'flag': flag,
        'name': name,
        if (mainCode != null && mainCode > 0) 'main_code': mainCode,
        if (dCode != null && dCode > 0) 'd_code': dCode,
      },
    );
    return _data(response.data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> updateCategory({
    required int code,
    required String flag,
    required String name,
  }) async {
    final response = await _apiClient.dio.put(
      '/api/v1/category-master/$code',
      data: {'flag': flag, 'name': name},
    );
    return _data(response.data as Map<String, dynamic>);
  }

  Future<Map<String, List<BrandMasterRow>>> listBrands({
    String flag = 'all',
    String q = '',
  }) async {
    final response = await _apiClient.dio.get(
      '/api/v1/brand-master',
      queryParameters: {
        'flag': flag,
        if (q.isNotEmpty) 'q': q,
      },
    );
    final data = _data(response.data as Map<String, dynamic>);
    List<BrandMasterRow> parse(String key) {
      final raw = data[key];
      final out = <BrandMasterRow>[];
      if (raw is List) {
        for (final r in raw) {
          if (r is Map) out.add(BrandMasterRow.fromJson(Map<String, dynamic>.from(r)));
        }
      }
      return out;
    }

    return {
      'brands': parse('brands'),
      'shelves': parse('shelves'),
      'colors': parse('colors'),
    };
  }

  Future<Map<String, dynamic>> createBrand({
    required String flag,
    required String name,
  }) async {
    final response = await _apiClient.dio.post(
      '/api/v1/brand-master',
      data: {'flag': flag, 'name': name},
    );
    return _data(response.data as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> updateBrand({
    required int code,
    required String flag,
    required String name,
  }) async {
    final response = await _apiClient.dio.put(
      '/api/v1/brand-master/$code',
      data: {'flag': flag, 'name': name},
    );
    return _data(response.data as Map<String, dynamic>);
  }
}
