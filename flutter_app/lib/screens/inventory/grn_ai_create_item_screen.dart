import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/utils/barcode_utils.dart';
import '../../services/item_master_service.dart';
import '../../services/purchase_order_service.dart';
import '../../services/purchase_service.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

/// Quick-create item for unmatched AI GRN lines — Item Master fields + AI autofill
/// (ERP `#grnQuickItemModal` / AI Mode parity).
class GrnAiCreateItemScreen extends StatefulWidget {
  const GrnAiCreateItemScreen({
    super.key,
    this.barcode = '',
    this.description = '',
    this.uom = '',
    this.rate = 0,
    this.supplierCode = '',
    this.supplierDisplay = '',
  });

  final String barcode;
  final String description;
  final String uom;
  final double rate;
  /// GRN header supplier (ERP quick-item copies this onto the new item).
  final String supplierCode;
  final String supplierDisplay;

  @override
  State<GrnAiCreateItemScreen> createState() => _GrnAiCreateItemScreenState();
}

class _GrnAiCreateItemScreenState extends State<GrnAiCreateItemScreen> {
  static const _accent = Color(0xFF0277BD);

  final _barcode = TextEditingController();
  final _name = TextEditingController();
  final _nameAra = TextEditingController();
  final _description = TextEditingController();
  final _cost = TextEditingController();
  final _retail = TextEditingController();
  final _vat = TextEditingController(text: '0');

  bool _loadingLookups = true;
  bool _aiBusy = false;
  bool _saving = false;
  bool _aiEnabled = true;
  String? _error;
  String? _aiStatus;
  String? _nextCode;

  String? _baseUom;
  String? _mainCategoryCode;
  String? _departmentCode;
  String? _categoryCode;
  String? _brandCode;
  String? _supplierCode;

  List<ItemLookupOption> _uoms = [];
  List<ItemLookupOption> _mainCategories = [];
  List<ItemLookupOption> _departments = [];
  List<ItemLookupOption> _categories = [];
  List<ItemLookupOption> _brands = [];
  List<ItemLookupOption> _suppliers = [];

  @override
  void initState() {
    super.initState();
    _barcode.text = widget.barcode.trim();
    _name.text = widget.description.trim().toUpperCase();
    _description.text = widget.description.trim();
    _baseUom = widget.uom.trim().isEmpty ? null : widget.uom.trim().toUpperCase();
    _cost.text = widget.rate > 0 ? widget.rate.toStringAsFixed(2) : '';
    _retail.text = widget.rate > 0 ? widget.rate.toStringAsFixed(2) : '';
    final sc = widget.supplierCode.trim();
    _supplierCode = sc.isEmpty ? null : sc;
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadLookups());
  }

  bool get _hasGrnSupplier => (widget.supplierCode.trim().isNotEmpty);

  @override
  void dispose() {
    _barcode.dispose();
    _name.dispose();
    _nameAra.dispose();
    _description.dispose();
    _cost.dispose();
    _retail.dispose();
    _vat.dispose();
    super.dispose();
  }

  List<ItemLookupOption> _parseOpts(dynamic raw) {
    String norm(dynamic v) {
      final s = '$v'.trim();
      if (s.isEmpty) return '';
      final n = num.tryParse(s);
      if (n == null) return s;
      return n == n.roundToDouble() ? '${n.round()}' : s;
    }

    return (raw as List<dynamic>? ?? const [])
        .whereType<Map>()
        .map((e) {
          final m = Map<String, dynamic>.from(e);
          return ItemLookupOption(
            code: norm(m['code']),
            name: '${m['name'] ?? ''}'.trim(),
            parentId: norm(m['parent_id'] ?? m['id']),
          );
        })
        .where((e) => e.code.isNotEmpty)
        .toList(growable: false);
  }

  void _ensureInternalBarcode({bool force = false}) {
    if (!force && _barcode.text.trim().isNotEmpty) return;
    final suggested = formatInternalItemBarcode(_nextCode);
    if (suggested != null && suggested.isNotEmpty) {
      _barcode.text = suggested;
    }
  }

  Future<void> _loadLookups() async {
    setState(() {
      _loadingLookups = true;
      _error = null;
    });
    try {
      final purchase = context.read<PurchaseService>();
      final itemMaster = context.read<ItemMasterService>();
      final data = await purchase.grnAiQuickItemLookups();
      if (!mounted) return;

      var units = _parseOpts(data['units']);
      // GRN lookups: categories = departments, micro_categories = leaf categories
      var mains = _parseOpts(data['main_categories']);
      var depts = _parseOpts(data['categories']);
      var cats = _parseOpts(data['micro_categories']);
      var brands = _parseOpts(data['brands']);
      var suppliers = _parseOpts(data['suppliers']);
      var nextCode = '${data['next_item_code'] ?? ''}'.trim();
      var suggestedBc = '${data['suggested_barcode'] ?? ''}'.trim();

      // Same pickers as Item Master when GRN quick-item lookups are thin
      if (mains.isEmpty || depts.isEmpty || cats.isEmpty || brands.isEmpty || units.isEmpty) {
        try {
          final meta = await itemMaster.getOpenContext();
          if (!mounted) return;
          if (nextCode.isEmpty && meta.nextItemCode > 0) nextCode = '${meta.nextItemCode}';
          if (suggestedBc.isEmpty) suggestedBc = meta.suggestedBarcode.trim();
          if (units.isEmpty) units = meta.uoms;
          if (mains.isEmpty) mains = meta.mainCategories;
          if (depts.isEmpty) depts = meta.departments;
          if (cats.isEmpty) cats = meta.categories;
          if (brands.isEmpty) brands = meta.brands;
          if (suppliers.isEmpty) suppliers = meta.suppliers;
        } catch (_) {
          // Keep GRN lookups only
        }
      }
      if (suggestedBc.isEmpty) {
        suggestedBc = formatInternalItemBarcode(nextCode) ?? '';
      }

      var uom = _baseUom;
      if ((uom ?? '').isEmpty && units.isNotEmpty) {
        uom = units.first.code;
      } else if ((uom ?? '').isNotEmpty && units.isNotEmpty) {
        final hit = units.where((u) => u.code.toUpperCase() == uom!.toUpperCase());
        if (hit.isNotEmpty) uom = hit.first.code;
      }

      // Prefill barcode from invoice only when present; else 12…itemcode like Item Master
      if (_barcode.text.trim().isEmpty) {
        if (widget.barcode.trim().isNotEmpty) {
          _barcode.text = widget.barcode.trim();
        } else if (suggestedBc.isNotEmpty) {
          _barcode.text = suggestedBc;
        }
      }

      setState(() {
        _nextCode = nextCode;
        _uoms = units;
        _mainCategories = mains;
        _departments = depts;
        _categories = cats;
        _brands = brands;
        _suppliers = suppliers;
        _baseUom = uom;
        _loadingLookups = false;
      });

      if (_aiEnabled) {
        await _runAiFill(auto: true);
      } else {
        _ensureInternalBarcode();
        if (mounted) setState(() {});
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadingLookups = false;
        _error = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  bool _fieldEmpty(TextEditingController c) => c.text.trim().isEmpty;

  String _codeStr(dynamic v) {
    if (v == null) return '';
    final s = '$v'.trim();
    if (s.isEmpty || s == '0' || s == '0.0') return '';
    final asInt = int.tryParse(s.split('.').first);
    return asInt != null ? '$asInt' : s;
  }

  void _applyGeneral(Map<String, dynamic> g, {Map<String, dynamic>? product}) {
    final prodName = '${product?['item_name'] ?? ''}'.trim();
    final prodDesc = '${product?['description'] ?? ''}'.trim();
    final prodAra = '${product?['item_name_ara'] ?? ''}'.trim();

    if (_fieldEmpty(_name) && prodName.isNotEmpty) {
      _name.text = prodName.toUpperCase();
    }
    final ara = '${g['item_name_ara'] ?? ''}'.trim().isNotEmpty
        ? '${g['item_name_ara']}'.trim()
        : prodAra;
    if (_fieldEmpty(_nameAra) && ara.isNotEmpty) {
      _nameAra.text = ara;
    }
    final desc = '${g['description'] ?? ''}'.trim().isNotEmpty
        ? '${g['description']}'.trim()
        : (prodDesc.isNotEmpty ? prodDesc : '');
    if (_fieldEmpty(_description) && desc.isNotEmpty) {
      _description.text = desc;
    } else if (_fieldEmpty(_description) && _name.text.trim().isNotEmpty) {
      _description.text = _name.text.trim();
    }

    final uomRaw = '${g['base_uom'] ?? ''}'.trim();
    if ((_baseUom ?? '').isEmpty && uomRaw.isNotEmpty) {
      final hit = _uoms.where((u) => u.code.toUpperCase() == uomRaw.toUpperCase());
      _baseUom = hit.isNotEmpty ? hit.first.code : uomRaw.toUpperCase();
    }

    final mc = _codeStr(g['main_category']);
    final dc = _codeStr(g['department_code']);
    final cc = _codeStr(g['category_code'] ?? g['micro_category']);
    final br = _codeStr(g['brand_code']);
    final sup = _codeStr(g['sup_code']);

    if ((_mainCategoryCode ?? '').isEmpty && mc.isNotEmpty) _mainCategoryCode = mc;
    if ((_departmentCode ?? '').isEmpty && dc.isNotEmpty) _departmentCode = dc;
    if ((_categoryCode ?? '').isEmpty && cc.isNotEmpty) _categoryCode = cc;
    if ((_brandCode ?? '').isEmpty && br.isNotEmpty) _brandCode = br;
    // ERP quick-item supplier comes from GRN header, not AI template.
    if (!_hasGrnSupplier && (_supplierCode ?? '').isEmpty && sup.isNotEmpty) {
      _supplierCode = sup;
    }
  }

  Future<void> _runAiFill({bool auto = false}) async {
    if (!_aiEnabled || _aiBusy) return;
    final barcode = _barcode.text.trim();
    final name = _name.text.trim();
    if (barcode.isEmpty && name.isEmpty) {
      if (!auto) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Enter barcode or item name for AI fill')),
        );
      }
      return;
    }

    setState(() {
      _aiBusy = true;
      _aiStatus = barcode.isNotEmpty
          ? 'Looking up barcode / similar items…'
          : 'Matching similar items…';
    });
    try {
      final data = await context.read<PurchaseService>().suggestGrnAiQuickItem(
            barcode: barcode,
            itemName: name,
          );
      if (!mounted) return;

      if (data['already_exists'] == true && data['already_in_master'] == true) {
        final code = '${data['matched_item_code'] ?? ''}'.trim();
        final nm = '${data['matched_item_name'] ?? ''}'.trim();
        setState(() {
          _aiBusy = false;
          _aiStatus = code.isNotEmpty
              ? 'Barcode already in Item Master: $code${nm.isNotEmpty ? ' — $nm' : ''}'
              : '${data['message'] ?? 'Barcode already exists.'}';
        });
        return;
      }

      final general = data['general'];
      final product = data['product'];
      final g = general is Map ? Map<String, dynamic>.from(general) : <String, dynamic>{};
      final p = product is Map ? Map<String, dynamic>.from(product) : <String, dynamic>{};

      // Web product name when form name still empty / from invoice line
      final webName = '${p['item_name'] ?? ''}'.trim();
      if (webName.isNotEmpty && (_fieldEmpty(_name) || auto)) {
        // Only overwrite name from web when user hasn't typed a different name
        if (_fieldEmpty(_name) || _name.text.trim().toUpperCase() == widget.description.trim().toUpperCase()) {
          if (webName.isNotEmpty) _name.text = webName.toUpperCase();
        }
      }

      if (data['found'] == true && g.isNotEmpty) {
        _applyGeneral(g, product: p);
        final matched = '${data['matched_item_name'] ?? ''}'.trim();
        final score = data['match_score'];
        final pct = score is num ? ' (${(score * 100).round()}%)' : '';
        _ensureInternalBarcode();
        setState(() {
          _aiBusy = false;
          _aiStatus = matched.isNotEmpty
              ? 'AI filled from similar item: $matched$pct'
              : '${data['message'] ?? 'AI suggestions applied.'}';
        });
      } else {
        if (g.isNotEmpty) _applyGeneral(g, product: p);
        _ensureInternalBarcode();
        setState(() {
          _aiBusy = false;
          _aiStatus = '${data['message'] ?? 'No similar item found.'}';
        });
      }
    } catch (e) {
      if (!mounted) return;
      _ensureInternalBarcode();
      setState(() {
        _aiBusy = false;
        _aiStatus = handleApiError(context, e, authenticatedContext: true);
      });
    }
  }

  List<ItemLookupOption> _departmentsForMain() {
    final main = (_mainCategoryCode ?? '').trim();
    if (main.isEmpty) return _departments;
    final filtered = _departments.where((d) => d.parentId == main).toList(growable: false);
    return filtered.isNotEmpty ? filtered : _departments;
  }

  List<ItemLookupOption> _categoriesForDepartment() {
    final dept = (_departmentCode ?? '').trim();
    if (dept.isEmpty) return _categories;
    final filtered = _categories.where((c) => c.parentId == dept).toList(growable: false);
    return filtered.isNotEmpty ? filtered : _categories;
  }

  String _lookupLabel(String? code, List<ItemLookupOption> options) {
    if ((code ?? '').isEmpty) return '';
    for (final o in options) {
      if (o.code == code) return o.label;
    }
    return code!;
  }

  Future<ItemLookupOption?> _pickLookup({
    required String title,
    required List<ItemLookupOption> options,
    String? selectedCode,
    bool allowClear = false,
  }) {
    if (options.isEmpty && !allowClear) return Future.value(null);
    return showModalBottomSheet<ItemLookupOption>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _LookupPickerSheet(
        title: title,
        options: options,
        selectedCode: selectedCode,
        allowClear: allowClear,
      ),
    );
  }

  Future<void> _pickBaseUom() async {
    final picked = await _pickLookup(title: 'Select base UOM', options: _uoms, selectedCode: _baseUom);
    if (picked == null || !mounted) return;
    setState(() => _baseUom = picked.code);
  }

  Future<void> _pickMainCategory() async {
    final picked = await _pickLookup(
      title: 'Select main category',
      options: _mainCategories,
      selectedCode: _mainCategoryCode,
      allowClear: true,
    );
    if (!mounted || picked == null) return;
    setState(() {
      _mainCategoryCode = picked.code.isEmpty ? null : picked.code;
      final depts = _departmentsForMain();
      if (_departmentCode != null && !depts.any((d) => d.code == _departmentCode)) {
        _departmentCode = null;
        _categoryCode = null;
      }
    });
  }

  Future<void> _pickDepartment() async {
    final picked = await _pickLookup(
      title: 'Select department',
      options: _departmentsForMain(),
      selectedCode: _departmentCode,
      allowClear: true,
    );
    if (!mounted || picked == null) return;
    setState(() {
      _departmentCode = picked.code.isEmpty ? null : picked.code;
      final cats = _categoriesForDepartment();
      if (_categoryCode != null && !cats.any((c) => c.code == _categoryCode)) {
        _categoryCode = null;
      }
    });
  }

  Future<void> _pickCategory() async {
    final picked = await _pickLookup(
      title: 'Select category',
      options: _categoriesForDepartment(),
      selectedCode: _categoryCode,
    );
    if (picked == null || !mounted) return;
    setState(() => _categoryCode = picked.code);
  }

  Future<void> _pickBrand() async {
    final picked = await _pickLookup(
      title: 'Select brand',
      options: _brands,
      selectedCode: _brandCode,
      allowClear: true,
    );
    if (!mounted || picked == null) return;
    setState(() => _brandCode = picked.code.isEmpty ? null : picked.code);
  }

  Future<void> _pickSupplier() async {
    if (_suppliers.isNotEmpty) {
      final picked = await _pickLookup(
        title: 'Select supplier',
        options: _suppliers,
        selectedCode: _supplierCode,
        allowClear: true,
      );
      if (!mounted || picked == null) return;
      setState(() => _supplierCode = picked.code.isEmpty ? null : picked.code);
      return;
    }
    // Fallback: purchase supplier search (same list as GRN header)
    try {
      final rows = await context.read<PurchaseOrderService>().searchSuppliers(q: '');
      if (!mounted) return;
      final opts = rows
          .map((s) => ItemLookupOption(code: s.code, name: s.name))
          .where((e) => e.code.isNotEmpty)
          .toList(growable: false);
      final picked = await _pickLookup(
        title: 'Select supplier',
        options: opts,
        selectedCode: _supplierCode,
        allowClear: true,
      );
      if (!mounted || picked == null) return;
      setState(() {
        _suppliers = opts;
        _supplierCode = picked.code.isEmpty ? null : picked.code;
      });
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  Future<void> _save() async {
    _ensureInternalBarcode();
    final barcode = _barcode.text.trim();
    final name = _name.text.trim();
    final retail = double.tryParse(_retail.text.trim().replaceAll(',', '')) ?? 0;
    if (barcode.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Barcode is required')));
      return;
    }
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Item name is required')));
      return;
    }
    if ((_baseUom ?? '').trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Base UOM is required')));
      return;
    }
    if ((_categoryCode ?? '').trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Category is required')));
      return;
    }
    if (retail <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please set retail price')));
      return;
    }
    setState(() => _saving = true);
    try {
      final created = await context.read<PurchaseService>().createGrnAiQuickItem({
        'barcode': barcode,
        'item_name': name,
        'item_name_ara': _nameAra.text.trim(),
        'description': _description.text.trim().isEmpty ? name : _description.text.trim(),
        'base_uom': _baseUom!.trim(),
        'cost_price': double.tryParse(_cost.text.trim().replaceAll(',', '')) ?? 0,
        'retail_price': retail,
        'vat_percent': double.tryParse(_vat.text.trim().replaceAll(',', '')) ?? 0,
        'main_category': int.tryParse(_mainCategoryCode ?? '') ?? 0,
        'department_code': int.tryParse(_departmentCode ?? '') ?? 0,
        'category_code': int.tryParse(_categoryCode ?? '') ?? 0,
        'brand_code': int.tryParse(_brandCode ?? '') ?? 0,
        'sup_code': int.tryParse(_supplierCode ?? '') ?? 0,
      });
      if (!mounted) return;
      Navigator.of(context).pop(created);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final uomLabel = _lookupLabel(_baseUom, _uoms);
    final mainLabel = _lookupLabel(_mainCategoryCode, _mainCategories);
    final deptLabel = _lookupLabel(_departmentCode, _departments);
    final catLabel = _lookupLabel(_categoryCode, _categories);
    final brandLabel = _lookupLabel(_brandCode, _brands);
    var supplierLabel = _lookupLabel(_supplierCode, _suppliers);
    if (supplierLabel.isEmpty && widget.supplierDisplay.trim().isNotEmpty) {
      supplierLabel = widget.supplierDisplay.trim();
    } else if (supplierLabel.isEmpty && (_supplierCode ?? '').isNotEmpty) {
      supplierLabel = _supplierCode!;
    }

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        title: const Text('Create item', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          TextButton(
            onPressed: _saving || _loadingLookups || _aiBusy ? null : _save,
            child: Text(
              'Save',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: _saving || _loadingLookups || _aiBusy ? Colors.grey : _accent,
              ),
            ),
          ),
        ],
      ),
      body: LoadingOverlay(
        loading: _saving || _aiBusy,
        message: _aiBusy ? (_aiStatus ?? 'AI filling…') : 'Saving item…',
        child: _loadingLookups
            ? const Center(child: CircularProgressIndicator(color: _accent))
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                children: [
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(_error!, style: const TextStyle(color: Color(0xFFC62828))),
                    ),
                  _card(
                    children: [
                      Row(
                        children: [
                          const Expanded(
                            child: Text(
                              'AI Mode',
                              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                            ),
                          ),
                          Switch.adaptive(
                            value: _aiEnabled,
                            activeTrackColor: _accent.withValues(alpha: 0.5),
                            activeThumbColor: _accent,
                            onChanged: _aiBusy
                                ? null
                                : (v) {
                                    setState(() => _aiEnabled = v);
                                    if (v) _runAiFill();
                                  },
                          ),
                          TextButton(
                            onPressed: !_aiEnabled || _aiBusy ? null : () => _runAiFill(),
                            child: const Text('Fill'),
                          ),
                        ],
                      ),
                      if ((_aiStatus ?? '').isNotEmpty)
                        Text(
                          _aiStatus!,
                          style: TextStyle(fontSize: 12.5, color: Colors.grey.shade700),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if ((_nextCode ?? '').isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Text(
                        'Next item code: $_nextCode',
                        style: TextStyle(color: Colors.grey.shade700, fontSize: 12.5),
                      ),
                    ),
                  _card(
                    children: [
                      _label('Barcode *'),
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _barcode,
                              decoration: _decoration('12 + zeros + item code'),
                              onSubmitted: (_) {
                                if (_aiEnabled) _runAiFill();
                              },
                            ),
                          ),
                          const SizedBox(width: 8),
                          Padding(
                            padding: const EdgeInsets.only(top: 2),
                            child: OutlinedButton(
                              onPressed: _saving
                                  ? null
                                  : () {
                                      _ensureInternalBarcode(force: true);
                                      setState(() {});
                                    },
                              child: const Text('Generate'),
                            ),
                          ),
                        ],
                      ),
                      if ((_nextCode ?? '').isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            '13-digit: starts with 12, ends with item code $_nextCode',
                            style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                          ),
                        ),
                      const SizedBox(height: 12),
                      _label('Item name *'),
                      TextField(
                        controller: _name,
                        textCapitalization: TextCapitalization.characters,
                        maxLength: 50,
                        decoration: _decoration('As in ERP item master'),
                        onSubmitted: (_) {
                          if (_aiEnabled) _runAiFill();
                        },
                      ),
                      const SizedBox(height: 8),
                      _label('Arabic name'),
                      TextField(
                        controller: _nameAra,
                        textDirection: TextDirection.rtl,
                        decoration: _decoration('Optional'),
                      ),
                      const SizedBox(height: 12),
                      _label('Description'),
                      TextField(
                        controller: _description,
                        maxLines: 2,
                        decoration: _decoration('Description'),
                      ),
                      const SizedBox(height: 12),
                      _label('Base UOM *'),
                      _searchField(value: uomLabel, hint: 'Search UOM', onTap: _pickBaseUom),
                      const SizedBox(height: 12),
                      _label('Main Category'),
                      _searchField(
                        value: mainLabel,
                        hint: 'Search main category',
                        onTap: _pickMainCategory,
                      ),
                      const SizedBox(height: 12),
                      _label('Department'),
                      _searchField(
                        value: deptLabel,
                        hint: 'Search department',
                        onTap: _pickDepartment,
                      ),
                      const SizedBox(height: 12),
                      _label('Category *'),
                      _searchField(
                        value: catLabel,
                        hint: 'Search micro category',
                        onTap: _pickCategory,
                      ),
                      const SizedBox(height: 12),
                      _label('Brand'),
                      _searchField(
                        value: brandLabel,
                        hint: 'Search brand (optional)',
                        onTap: _pickBrand,
                      ),
                      const SizedBox(height: 12),
                      _label('Supplier'),
                      _searchField(
                        value: supplierLabel,
                        hint: _hasGrnSupplier
                            ? 'From GRN header'
                            : (_suppliers.isEmpty ? 'No suppliers loaded' : 'Search supplier'),
                        onTap: _pickSupplier,
                      ),
                      if (_hasGrnSupplier)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            'Copied from AI GRN supplier (same as ERP)',
                            style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _card(
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                _label('Cost (invoice)'),
                                NumericTextField(controller: _cost, decoration: _decoration('0.00')),
                              ],
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                _label('Retail *'),
                                NumericTextField(controller: _retail, decoration: _decoration('0.00')),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      _label('VAT %'),
                      NumericTextField(controller: _vat, decoration: _decoration('0')),
                    ],
                  ),
                  const SizedBox(height: 18),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: _accent,
                      minimumSize: const Size(double.infinity, 48),
                    ),
                    onPressed: _saving || _aiBusy ? null : _save,
                    child: const Text('Save item', style: TextStyle(fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _card({required List<Widget> children}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(
          text,
          style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: Color(0xFF3D4477)),
        ),
      );

  InputDecoration _decoration(String hint) => InputDecoration(
        hintText: hint,
        isDense: true,
        filled: true,
        fillColor: const Color(0xFFF7F8FC),
        counterText: '',
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: Color(0xFFE0E4F0)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: Color(0xFFE0E4F0)),
        ),
      );

  Widget _searchField({
    required String value,
    required String hint,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: _saving ? null : onTap,
      borderRadius: BorderRadius.circular(10),
      child: InputDecorator(
        decoration: _decoration(hint),
        child: Row(
          children: [
            Expanded(
              child: Text(
                value.isEmpty ? hint : value,
                style: TextStyle(
                  color: value.isEmpty ? Colors.grey.shade500 : const Color(0xFF262C50),
                  fontWeight: value.isEmpty ? FontWeight.w400 : FontWeight.w600,
                ),
              ),
            ),
            Icon(Icons.search, size: 18, color: Colors.grey.shade600),
          ],
        ),
      ),
    );
  }
}

class _LookupPickerSheet extends StatefulWidget {
  const _LookupPickerSheet({
    required this.title,
    required this.options,
    this.selectedCode,
    this.allowClear = false,
  });

  final String title;
  final List<ItemLookupOption> options;
  final String? selectedCode;
  final bool allowClear;

  @override
  State<_LookupPickerSheet> createState() => _LookupPickerSheetState();
}

class _LookupPickerSheetState extends State<_LookupPickerSheet> {
  final _search = TextEditingController();
  late List<ItemLookupOption> _filtered;

  @override
  void initState() {
    super.initState();
    _filtered = widget.options;
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _applyFilter(String raw) {
    final q = raw.trim().toLowerCase();
    setState(() {
      if (q.isEmpty) {
        _filtered = widget.options;
        return;
      }
      _filtered = widget.options
          .where((c) => c.code.toLowerCase().contains(q) || c.name.toLowerCase().contains(q))
          .toList(growable: false);
    });
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 8, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 12),
          Text(widget.title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
          const SizedBox(height: 12),
          TextField(
            controller: _search,
            autofocus: true,
            decoration: InputDecoration(
              hintText: 'Search name or code',
              prefixIcon: const Icon(Icons.search, size: 20),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              isDense: true,
            ),
            onChanged: _applyFilter,
          ),
          if (widget.allowClear) ...[
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: () => Navigator.pop(context, ItemLookupOption(code: '', name: '')),
                child: const Text('Clear selection'),
              ),
            ),
          ],
          const SizedBox(height: 8),
          if (_filtered.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(child: Text('No matches.', style: TextStyle(color: Colors.grey.shade600))),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.5),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _filtered.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final c = _filtered[i];
                  final selected = c.code == widget.selectedCode;
                  return ListTile(
                    onTap: () => Navigator.pop(context, c),
                    selected: selected,
                    selectedColor: _GrnAiCreateItemScreenState._accent,
                    title: Text(
                      c.name.isNotEmpty ? c.name : c.code,
                      style: TextStyle(fontWeight: selected ? FontWeight.w700 : FontWeight.w600),
                    ),
                    subtitle: Text('Code ${c.code}'),
                    trailing: selected
                        ? const Icon(Icons.check_circle_rounded, color: _GrnAiCreateItemScreenState._accent)
                        : const Icon(Icons.chevron_right_rounded),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
