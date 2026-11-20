import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/utils/barcode_utils.dart';
import '../../services/item_master_service.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/master_delete_dialog.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

class _AltUomRow {
  _AltUomRow()
      : factor = TextEditingController(text: '1'),
        cost = TextEditingController(),
        barcode = TextEditingController(),
        retail = TextEditingController();

  String? uomCode;
  final TextEditingController factor;
  /// Read-only: factor × master COSTPRICE (ERP Alt Cost Price).
  final TextEditingController cost;
  final TextEditingController barcode;
  final TextEditingController retail;
  VoidCallback onFactorChanged = () {};

  void dispose() {
    factor.dispose();
    cost.dispose();
    barcode.dispose();
    retail.dispose();
  }
}

class ItemFormScreen extends StatefulWidget {
  const ItemFormScreen({super.key, this.itemCode});

  final int? itemCode;

  @override
  State<ItemFormScreen> createState() => _ItemFormScreenState();
}

class _ItemFormScreenState extends State<ItemFormScreen> {
  static const _accent = Color(0xFF5E35B1);

  final _name = TextEditingController();
  final _barcode = TextEditingController();
  final _cost = TextEditingController();
  final _retail = TextEditingController();
  final _vat = TextEditingController(text: '0');

  String? _baseUom;
  String? _categoryCode;
  String? _brandCode;
  String? _mainCategoryCode;
  String? _departmentCode;
  String? _supplierCode;
  final List<_AltUomRow> _altRows = [];
  bool _loadingMeta = true;
  bool _saving = false;
  String? _metaError;
  ItemOpenContext? _meta;
  ItemDetail? _detail;
  Uint8List? _imageBytes;
  String _imageMime = 'image/jpeg';
  bool _removeImage = false;
  bool _hasExistingImage = false;
  bool _imageDirty = false;

  bool get _isEdit => (widget.itemCode ?? 0) > 0;

  @override
  void initState() {
    super.initState();
    _cost.addListener(_recalcAllAltCosts);
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadMeta());
  }

  @override
  void dispose() {
    _cost.removeListener(_recalcAllAltCosts);
    _name.dispose();
    _barcode.dispose();
    _cost.dispose();
    _retail.dispose();
    _vat.dispose();
    for (final r in _altRows) {
      r.factor.removeListener(r.onFactorChanged);
      r.dispose();
    }
    super.dispose();
  }

  double get _masterCost =>
      double.tryParse(_cost.text.trim().replaceAll(',', '')) ?? 0;

  void _syncAltCost(_AltUomRow row) {
    final factor = double.tryParse(row.factor.text.trim().replaceAll(',', '')) ?? 0;
    final altCost = (factor > 0 ? factor : 0) * _masterCost;
    final text = altCost == 0 ? '' : altCost.toStringAsFixed(3);
    if (row.cost.text != text) {
      row.cost.text = text;
    }
  }

  void _recalcAllAltCosts() {
    for (final r in _altRows) {
      _syncAltCost(r);
    }
  }

  void _wireAltRow(_AltUomRow row) {
    row.onFactorChanged = () => _syncAltCost(row);
    row.factor.addListener(row.onFactorChanged);
    _syncAltCost(row);
  }

  Future<void> _loadMeta() async {
    setState(() {
      _loadingMeta = true;
      _metaError = null;
    });
    try {
      final svc = context.read<ItemMasterService>();
      final meta = await svc.getOpenContext();
      ItemDetail? detail;
      if (_isEdit) {
        detail = await svc.getItem(widget.itemCode!);
      }
      if (!mounted) return;
      Uint8List? existingImage;
      if (detail != null && detail.hasImage) {
        existingImage = await svc.fetchItemImageBytes(detail.itemCode);
      }
      if (!mounted) return;
      setState(() {
        _meta = meta;
        _detail = detail;
        _imageBytes = existingImage;
        _hasExistingImage = existingImage != null;
        _removeImage = false;
        _imageDirty = false;
        if (detail != null) {
          _applyDetail(detail);
        } else {
          final suggested = meta.suggestedBarcode.trim().isNotEmpty
              ? meta.suggestedBarcode.trim()
              : (formatInternalItemBarcode(meta.nextItemCode) ?? '');
          _barcode.text = suggested;
          if (meta.uoms.isNotEmpty) {
            _baseUom = meta.uoms.first.code;
          }
        }
        _loadingMeta = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _metaError = handleApiError(context, e, authenticatedContext: true);
        _loadingMeta = false;
      });
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(
      source: source,
      imageQuality: 85,
      maxWidth: 1600,
    );
    if (file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    final ext = file.path.split('.').last.toLowerCase();
    final mime = switch (ext) {
      'png' => 'image/png',
      'webp' => 'image/webp',
      'gif' => 'image/gif',
      _ => 'image/jpeg',
    };
    setState(() {
      _imageBytes = bytes;
      _imageMime = mime;
      _removeImage = false;
      _imageDirty = true;
    });
  }

  Future<void> _chooseImageSource() async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Camera'),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Gallery'),
              onTap: () => Navigator.pop(ctx, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source == null || !mounted) return;
    await _pickImage(source);
  }

  void _clearImage() {
    setState(() {
      _imageBytes = null;
      _removeImage = _hasExistingImage;
      _imageDirty = true;
    });
  }

  void _applyDetail(ItemDetail d) {
    _name.text = d.itemName;
    _barcode.text = d.barcode;
    _cost.text = d.costPrice == 0 ? '' : d.costPrice.toString();
    _retail.text = d.retailPrice == 0 ? '' : d.retailPrice.toString();
    _vat.text = d.vatPercent.toString();
    _baseUom = d.baseUom.isNotEmpty ? d.baseUom : null;
    _categoryCode = d.categoryCode > 0 ? '${d.categoryCode}' : null;
    _brandCode = d.brandCode > 0 ? '${d.brandCode}' : null;
    _mainCategoryCode = d.mainCategory > 0 ? '${d.mainCategory}' : null;
    _departmentCode = d.departmentCode > 0 ? '${d.departmentCode}' : null;
    _supplierCode = d.supCode > 0 ? '${d.supCode}' : null;
    for (final r in _altRows) {
      r.dispose();
    }
    _altRows.clear();
    for (final a in d.alternateUoms) {
      final row = _AltUomRow();
      row.uomCode = a.uomCode;
      row.factor.text = a.conversionFactor == 0 ? '1' : a.conversionFactor.toString();
      row.barcode.text = a.barcode;
      row.retail.text = a.retailPrice == 0 ? '' : a.retailPrice.toString();
      _wireAltRow(row);
      _altRows.add(row);
    }
  }

  String _lookupLabel(String? code, List<ItemLookupOption> options) {
    if (code == null || code.isEmpty) return '';
    for (final o in options) {
      if (o.code == code) return o.label;
    }
    return code;
  }

  List<ItemLookupOption> _departmentsForMain() {
    final all = _meta?.departments ?? const <ItemLookupOption>[];
    final main = (_mainCategoryCode ?? '').trim();
    if (main.isEmpty) return all;
    final filtered = all.where((d) => d.parentId == main).toList(growable: false);
    return filtered.isNotEmpty ? filtered : all;
  }

  List<ItemLookupOption> _categoriesForDepartment() {
    final all = _meta?.categories ?? const <ItemLookupOption>[];
    final dept = (_departmentCode ?? '').trim();
    if (dept.isEmpty) return all;
    final filtered = all.where((c) => c.parentId == dept).toList(growable: false);
    return filtered.isNotEmpty ? filtered : all;
  }

  Future<ItemLookupOption?> _pickLookup({
    required String title,
    required List<ItemLookupOption> options,
    String? selectedCode,
    bool allowClear = false,
  }) {
    if (options.isEmpty && !allowClear) {
      return Future.value(null);
    }
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
    final picked = await _pickLookup(
      title: 'Select base UOM',
      options: _meta?.uoms ?? const [],
      selectedCode: _baseUom,
    );
    if (picked == null || !mounted) return;
    setState(() => _baseUom = picked.code);
  }

  Future<void> _pickMainCategory() async {
    final picked = await _pickLookup(
      title: 'Select main category',
      options: _meta?.mainCategories ?? const [],
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
      options: _meta?.brands ?? const [],
      selectedCode: _brandCode,
      allowClear: true,
    );
    if (!mounted || picked == null) return;
    setState(() => _brandCode = picked.code.isEmpty ? null : picked.code);
  }

  Future<void> _pickSupplier() async {
    final picked = await _pickLookup(
      title: 'Select supplier',
      options: _meta?.suppliers ?? const [],
      selectedCode: _supplierCode,
      allowClear: true,
    );
    if (!mounted || picked == null) return;
    setState(() => _supplierCode = picked.code.isEmpty ? null : picked.code);
  }

  Future<void> _pickAltUom(_AltUomRow row) async {
    final picked = await _pickLookup(
      title: 'Select alternate UOM',
      options: _meta?.uoms ?? const [],
      selectedCode: row.uomCode,
    );
    if (picked == null || !mounted) return;
    setState(() => row.uomCode = picked.code);
  }

  void _addAltRow() {
    final row = _AltUomRow();
    _wireAltRow(row);
    setState(() => _altRows.add(row));
  }

  void _removeAltRow(int index) {
    setState(() {
      final row = _altRows[index];
      row.factor.removeListener(row.onFactorChanged);
      row.dispose();
      _altRows.removeAt(index);
    });
  }

  List<Map<String, dynamic>>? _buildAltPayload() {
    final base = (_baseUom ?? '').trim().toUpperCase();
    final seen = <String>{};
    final out = <Map<String, dynamic>>[];
    for (var i = 0; i < _altRows.length; i++) {
      final row = _altRows[i];
      final uom = (row.uomCode ?? '').trim();
      if (uom.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Alternate UOM #${i + 1}: select a UOM.')),
        );
        return null;
      }
      final key = uom.toUpperCase();
      if (key == base) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Alternate UOM #${i + 1} cannot match base UOM.')),
        );
        return null;
      }
      if (seen.contains(key)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Duplicate alternate UOM: $uom')),
        );
        return null;
      }
      seen.add(key);
      final factor = double.tryParse(row.factor.text.trim().replaceAll(',', '')) ?? 0;
      if (factor <= 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Alternate UOM #${i + 1}: conversion factor must be > 0.')),
        );
        return null;
      }
      final altCost = factor * _masterCost;
      out.add({
        'alternate_uom_code': uom,
        'conversion_factor': factor,
        'cost_price': double.parse(altCost.toStringAsFixed(3)),
        'manufacturer_id': row.barcode.text.trim(),
        'retail_price': double.tryParse(row.retail.text.trim().replaceAll(',', '')) ?? 0,
        'slno': '${i + 1}',
      });
    }
    return out;
  }

  void _generateInternalBarcode() {
    final code = _isEdit ? (widget.itemCode ?? _detail?.itemCode ?? 0) : (_meta?.nextItemCode ?? 0);
    final bc = formatInternalItemBarcode(code);
    if (bc == null || bc.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not generate barcode for this item code.')),
      );
      return;
    }
    setState(() => _barcode.text = bc);
  }

  Future<void> _delete() async {
    final code = widget.itemCode ?? _detail?.itemCode ?? 0;
    if (code <= 0) return;
    final label = _name.text.trim().isNotEmpty ? _name.text.trim() : 'item $code';
    final password = await showMasterDeletePasswordDialog(
      context,
      title: 'Delete item',
      entityLabel: label,
    );
    if (password == null || password.isEmpty || !mounted) return;
    setState(() => _saving = true);
    try {
      final result = await context.read<ItemMasterService>().deleteItem(code, password: password);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Item deleted.')),
      );
      Navigator.of(context).pop('deleted');
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Item name is required.')),
      );
      return;
    }
    if (_barcode.text.trim().isEmpty && !_isEdit) {
      final bc = formatInternalItemBarcode(_meta?.nextItemCode);
      if (bc != null) _barcode.text = bc;
    }
    if ((_baseUom ?? '').isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Base UOM is required.')),
      );
      return;
    }
    if ((_categoryCode ?? '').isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Category is required.')),
      );
      return;
    }

    final altPayload = _buildAltPayload();
    if (altPayload == null) return;

    final meta = _meta;
    final detail = _detail;
    final payload = <String, dynamic>{
      'item_name': name,
      'manufacturer_id': _barcode.text.trim(),
      'base_uom': _baseUom,
      'category_code': int.tryParse(_categoryCode ?? '') ?? 0,
      'brand_code': int.tryParse(_brandCode ?? '') ?? 0,
      'main_category': int.tryParse(_mainCategoryCode ?? '') ?? 0,
      'department_code': int.tryParse(_departmentCode ?? '') ?? 0,
      'sup_code': int.tryParse(_supplierCode ?? '') ?? 0,
      'cost_price': double.tryParse(_cost.text.trim().replaceAll(',', '')) ?? 0,
      'retail_price': double.tryParse(_retail.text.trim().replaceAll(',', '')) ?? 0,
      'vat_percent': double.tryParse(_vat.text.trim().replaceAll(',', '')) ?? 0,
      'alternate_uoms': altPayload,
      'sales_account': detail?.salesAccount.isNotEmpty == true
          ? detail!.salesAccount
          : (meta?.salesAccount ?? '4100'),
      'purchase_account': detail?.purchaseAccount.isNotEmpty == true
          ? detail!.purchaseAccount
          : (meta?.purchaseAccount ?? '5001'),
      'inventory_account': detail?.inventoryAccount.isNotEmpty == true
          ? detail!.inventoryAccount
          : (meta?.inventoryAccount ?? '1300'),
      'cogs_account': detail?.cogsAccount.isNotEmpty == true
          ? detail!.cogsAccount
          : (meta?.cogsAccount ?? '5100'),
      if (_imageDirty && _removeImage && _imageBytes == null) 'remove_image': true,
      if (_imageDirty && _imageBytes != null) ...{
        'image_base64': base64Encode(_imageBytes!),
        'image_mime': _imageMime,
      },
    };

    setState(() => _saving = true);
    try {
      final svc = context.read<ItemMasterService>();
      final result = _isEdit
          ? await svc.updateItem(widget.itemCode!, payload)
          : await svc.createItem(payload);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Item saved.')),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _searchField({
    required String value,
    required String hint,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: InputDecorator(
        decoration: _decoration(hint).copyWith(
          suffixIcon: Icon(Icons.search_rounded, size: 20, color: Colors.grey.shade600),
        ),
        child: Text(
          value.isNotEmpty ? value : hint,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: 15,
            color: value.isNotEmpty ? const Color(0xFF262C50) : Colors.grey.shade500,
          ),
        ),
      ),
    );
  }

  Widget _altUomCard() {
    return _card(
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                'Alternate UOMs',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: Color(0xFF3D4477)),
              ),
            ),
            TextButton.icon(
              onPressed: _saving ? null : _addAltRow,
              icon: const Icon(Icons.add_rounded, size: 18),
              label: const Text('Add'),
              style: TextButton.styleFrom(foregroundColor: _accent),
            ),
          ],
        ),
        Text(
          'Maps to ITEMALTERNATEUOMMAP. Alt cost = factor × master cost price.',
          style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
        ),
        if (_altRows.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 4),
            child: Text(
              'No alternate UOMs. Tap Add to create pack/case variants.',
              style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
            ),
          )
        else
          for (var i = 0; i < _altRows.length; i++) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.fromLTRB(10, 10, 10, 12),
              decoration: BoxDecoration(
                color: const Color(0xFFF7F8FC),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFE0E4F0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Text(
                        'Variant ${i + 1}',
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                      ),
                      const Spacer(),
                      IconButton(
                        visualDensity: VisualDensity.compact,
                        onPressed: _saving ? null : () => _removeAltRow(i),
                        icon: Icon(Icons.delete_outline_rounded, color: Colors.red.shade400, size: 20),
                      ),
                    ],
                  ),
                  _label('UOM *'),
                  _searchField(
                    value: _lookupLabel(_altRows[i].uomCode, _meta?.uoms ?? const []),
                    hint: 'Search UOM',
                    onTap: () => _pickAltUom(_altRows[i]),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _label('Factor *'),
                            NumericTextField(
                              controller: _altRows[i].factor,
                              decoration: _decoration('e.g. 12'),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _label('Alt cost'),
                            TextField(
                              controller: _altRows[i].cost,
                              readOnly: true,
                              enableInteractiveSelection: false,
                              decoration: _decoration('factor × cost').copyWith(
                                filled: true,
                                fillColor: const Color(0xFFEEF1F6),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  _label('Retail'),
                  NumericTextField(
                    controller: _altRows[i].retail,
                    decoration: _decoration('0.00'),
                  ),
                  const SizedBox(height: 10),
                  _label('Barcode'),
                  TextField(
                    controller: _altRows[i].barcode,
                    decoration: _decoration('Auto if blank'),
                  ),
                ],
              ),
            ),
          ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final meta = _meta;
    final uomLabel = _lookupLabel(_baseUom, meta?.uoms ?? const []);
    final mainLabel = _lookupLabel(_mainCategoryCode, meta?.mainCategories ?? const []);
    final deptLabel = _lookupLabel(_departmentCode, meta?.departments ?? const []);
    final catLabel = _lookupLabel(_categoryCode, meta?.categories ?? const []);
    final brandLabel = _lookupLabel(_brandCode, meta?.brands ?? const []);
    final supplierLabel = _lookupLabel(_supplierCode, meta?.suppliers ?? const []);

    return Scaffold(
      backgroundColor: const Color(0xFFF4F5F8),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: _saving ? null : () => Navigator.of(context).maybePop(),
        ),
        title: Text(
          _isEdit ? 'Edit Item' : 'New Item',
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17),
        ),
        centerTitle: true,
        actions: [
          if (_isEdit)
            IconButton(
              tooltip: 'Delete',
              onPressed: _saving || _loadingMeta ? null : _delete,
              icon: Icon(Icons.delete_outline_rounded, color: Colors.red.shade700),
            ),
          TextButton(
            onPressed: _saving || _loadingMeta ? null : _save,
            child: Text(
              'Save',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: _saving || _loadingMeta ? Colors.grey : _accent,
              ),
            ),
          ),
        ],
      ),
      body: LoadingOverlay(
        loading: _saving,
        message: 'Please wait…',
        child: _loadingMeta
            ? const Center(child: CircularProgressIndicator())
            : _metaError != null
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(_metaError!, textAlign: TextAlign.center),
                          const SizedBox(height: 12),
                          FilledButton(onPressed: _loadMeta, child: const Text('Retry')),
                        ],
                      ),
                    ),
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                    children: [
                      if (_isEdit && (_detail?.itemCode ?? 0) > 0)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(
                            'Item code: ${_detail!.itemCode}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        )
                      else if (!_isEdit && meta != null && meta.nextItemCode > 0)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(
                            'Next code: ${meta.nextItemCode}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        ),
                      _card(
                        children: [
                          _label('Item Image'),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              ClipRRect(
                                borderRadius: BorderRadius.circular(10),
                                child: Container(
                                  width: 88,
                                  height: 88,
                                  color: const Color(0xFFF0F2FA),
                                  child: _imageBytes != null
                                      ? Image.memory(_imageBytes!, fit: BoxFit.cover)
                                      : Icon(Icons.image_outlined, color: Colors.grey.shade400, size: 32),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.stretch,
                                  children: [
                                    OutlinedButton.icon(
                                      onPressed: _saving ? null : _chooseImageSource,
                                      icon: const Icon(Icons.add_a_photo_outlined, size: 18),
                                      label: Text(_imageBytes == null ? 'Add image' : 'Change image'),
                                    ),
                                    if (_imageBytes != null || _hasExistingImage)
                                      TextButton(
                                        onPressed: _saving ? null : _clearImage,
                                        child: Text(
                                          'Remove image',
                                          style: TextStyle(color: Colors.red.shade600),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          _label('Item Name *'),
                          TextField(
                            controller: _name,
                            textCapitalization: TextCapitalization.characters,
                            maxLength: 50,
                            decoration: _decoration('As in ERP item master'),
                          ),
                          const SizedBox(height: 8),
                          _label('Barcode'),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: _barcode,
                                  decoration: _decoration('12 + zeros + item code'),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Padding(
                                padding: const EdgeInsets.only(top: 2),
                                child: OutlinedButton(
                                  onPressed: _saving ? null : _generateInternalBarcode,
                                  child: const Text('Generate'),
                                ),
                              ),
                            ],
                          ),
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text(
                              '13-digit: starts with 12, ends with item code'
                              '${(!_isEdit && (_meta?.nextItemCode ?? 0) > 0) ? ' ${_meta!.nextItemCode}' : ''}',
                              style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                            ),
                          ),
                          const SizedBox(height: 12),
                          _label('Base UOM *'),
                          _searchField(
                            value: uomLabel,
                            hint: 'Search UOM',
                            onTap: _pickBaseUom,
                          ),
                          if ((meta?.mainCategories ?? const []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            _label('Main Category'),
                            _searchField(
                              value: mainLabel,
                              hint: 'Search main category',
                              onTap: _pickMainCategory,
                            ),
                          ],
                          if ((meta?.departments ?? const []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            _label('Department'),
                            _searchField(
                              value: deptLabel,
                              hint: 'Search department',
                              onTap: _pickDepartment,
                            ),
                          ],
                          const SizedBox(height: 12),
                          _label('Category *'),
                          _searchField(
                            value: catLabel,
                            hint: 'Search micro category',
                            onTap: _pickCategory,
                          ),
                          if ((meta?.brands ?? const []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            _label('Brand'),
                            _searchField(
                              value: brandLabel,
                              hint: 'Search brand (optional)',
                              onTap: _pickBrand,
                            ),
                          ],
                          if ((meta?.suppliers ?? const []).isNotEmpty) ...[
                            const SizedBox(height: 12),
                            _label('Supplier'),
                            _searchField(
                              value: supplierLabel,
                              hint: 'Search supplier (optional)',
                              onTap: _pickSupplier,
                            ),
                          ],
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
                                    _label('Cost Price'),
                                    NumericTextField(controller: _cost, decoration: _decoration('0.00')),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    _label('Retail Price'),
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
                      const SizedBox(height: 12),
                      _altUomCard(),
                      const SizedBox(height: 18),
                      FilledButton(
                        onPressed: _saving ? null : _save,
                        style: FilledButton.styleFrom(
                          backgroundColor: _accent,
                          minimumSize: const Size.fromHeight(48),
                        ),
                        child: Text(
                          _isEdit ? 'Update Item' : 'Save Item',
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                      ),
                      if (_isEdit) ...[
                        const SizedBox(height: 10),
                        OutlinedButton.icon(
                          onPressed: _saving ? null : _delete,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.red.shade700,
                            side: BorderSide(color: Colors.red.shade300),
                            minimumSize: const Size.fromHeight(46),
                          ),
                          icon: const Icon(Icons.delete_outline_rounded, size: 18),
                          label: const Text('Delete item', style: TextStyle(fontWeight: FontWeight.w700)),
                        ),
                      ],
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
        child: Text(text, style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: Color(0xFF3D4477))),
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
  static const _accent = Color(0xFF5E35B1);

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
                    selectedColor: _accent,
                    title: Text(
                      c.name.isNotEmpty ? c.name : c.code,
                      style: TextStyle(fontWeight: selected ? FontWeight.w700 : FontWeight.w600),
                    ),
                    subtitle: Text('Code ${c.code}'),
                    trailing: selected
                        ? const Icon(Icons.check_circle_rounded, color: _accent)
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
