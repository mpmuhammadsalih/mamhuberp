import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/customer_master_service.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/master_delete_dialog.dart';
import '../../widgets/numeric_text_field.dart';
import '../../core/theme/app_theme.dart';

class CustomerFormScreen extends StatefulWidget {
  const CustomerFormScreen({
    super.key,
    this.customerCode,
    this.initialBillingType,
  });

  /// When set, form loads and updates an existing customer.
  final int? customerCode;

  /// Prefill Cash/Credit when creating from Sales.
  final String? initialBillingType;

  @override
  State<CustomerFormScreen> createState() => _CustomerFormScreenState();
}

class _CustomerFormScreenState extends State<CustomerFormScreen> {
  static const _accent = Color(0xFF1565C0);

  final _name = TextEditingController();
  final _mobile = TextEditingController();
  final _telephone = TextEditingController();
  final _address = TextEditingController();
  final _email = TextEditingController();
  final _whatsapp = TextEditingController();
  final _crno = TextEditingController();
  final _creditLimit = TextEditingController();
  final _creditTerm = TextEditingController(text: '2');

  String _billingType = 'CASH';
  String? _categoryCode;
  bool _loadingMeta = true;
  bool _saving = false;
  String? _metaError;
  CustomerOpenContext? _meta;

  bool get _isEdit => (widget.customerCode ?? 0) > 0;

  @override
  void initState() {
    super.initState();
    final bt = (widget.initialBillingType ?? '').trim().toUpperCase();
    if (bt == 'CREDIT' || bt == 'CASH') {
      _billingType = bt;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadMeta());
  }

  @override
  void dispose() {
    _name.dispose();
    _mobile.dispose();
    _telephone.dispose();
    _address.dispose();
    _email.dispose();
    _whatsapp.dispose();
    _crno.dispose();
    _creditLimit.dispose();
    _creditTerm.dispose();
    super.dispose();
  }

  Future<void> _loadMeta() async {
    setState(() {
      _loadingMeta = true;
      _metaError = null;
    });
    try {
      final svc = context.read<CustomerMasterService>();
      final meta = await svc.getOpenContext();
      CustomerDetail? detail;
      if (_isEdit) {
        detail = await svc.getCustomer(widget.customerCode!);
      }
      if (!mounted) return;
      if (detail != null) {
        _name.text = detail.customerName;
        _mobile.text = detail.mobile;
        _telephone.text = detail.telephone;
        _address.text = detail.address;
        _email.text = detail.email;
        _whatsapp.text = detail.whatsapp;
        _crno.text = detail.crno;
        _billingType = detail.billingType == 'CREDIT' ? 'CREDIT' : 'CASH';
        _categoryCode = detail.categoryCode > 0 ? '${detail.categoryCode}' : null;
        _creditLimit.text = detail.creditLimit > 0
            ? (detail.creditLimit == detail.creditLimit.roundToDouble()
                ? detail.creditLimit.round().toString()
                : detail.creditLimit.toStringAsFixed(2))
            : '';
        _creditTerm.text = detail.creditTerm > 0
            ? (detail.creditTerm == detail.creditTerm.roundToDouble()
                ? detail.creditTerm.round().toString()
                : detail.creditTerm.toStringAsFixed(0))
            : (meta.defaultCreditTerm == meta.defaultCreditTerm.roundToDouble()
                ? meta.defaultCreditTerm.round().toString()
                : meta.defaultCreditTerm.toStringAsFixed(0));
        // Ensure category from detail appears in picker even if open-context list is incomplete.
        if (_categoryCode != null &&
            detail.categoryName.isNotEmpty &&
            !meta.categories.any((c) => c.code == _categoryCode)) {
          _meta = CustomerOpenContext(
            nextCustomerCode: meta.nextCustomerCode,
            defaultCreditTerm: meta.defaultCreditTerm,
            receivableAccount: meta.receivableAccount,
            salesAccount: meta.salesAccount,
            vatOutputAccount: meta.vatOutputAccount,
            advanceAccount: meta.advanceAccount,
            categories: [
              ...meta.categories,
              CustomerCategoryOption(code: _categoryCode!, name: detail.categoryName),
            ],
          );
        } else {
          _meta = meta;
        }
      } else {
        _meta = meta;
        _creditTerm.text = meta.defaultCreditTerm == meta.defaultCreditTerm.roundToDouble()
            ? meta.defaultCreditTerm.round().toString()
            : meta.defaultCreditTerm.toStringAsFixed(0);
      }
      setState(() => _loadingMeta = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _metaError = handleApiError(context, e, authenticatedContext: true);
        _loadingMeta = false;
      });
    }
  }

  String _categoryLabel() {
    final code = _categoryCode;
    if (code == null || code.isEmpty) return '';
    for (final c in _meta?.categories ?? const <CustomerCategoryOption>[]) {
      if (c.code == code) return c.label;
    }
    return code;
  }

  Future<void> _pickCategory() async {
    final cats = List<CustomerCategoryOption>.from(_meta?.categories ?? const []);
    final picked = await showModalBottomSheet<CustomerCategoryOption>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => _CustomerCategoryPickerSheet(
        categories: cats,
        selectedCode: _categoryCode,
        onCreateCategory: (name) => context.read<CustomerMasterService>().createCategory(name: name),
      ),
    );
    if (!mounted || picked == null) return;
    // Refresh open context so the new category stays in the local list.
    try {
      final meta = await context.read<CustomerMasterService>().getOpenContext();
      if (mounted) setState(() => _meta = meta);
    } catch (_) {
      if (picked.code.isNotEmpty && mounted) {
        final existing = _meta?.categories ?? const <CustomerCategoryOption>[];
        if (!existing.any((c) => c.code == picked.code)) {
          setState(() {
            _meta = CustomerOpenContext(
              nextCustomerCode: _meta?.nextCustomerCode ?? 0,
              defaultCreditTerm: _meta?.defaultCreditTerm ?? 2,
              receivableAccount: _meta?.receivableAccount ?? 1200,
              salesAccount: _meta?.salesAccount ?? 4100,
              vatOutputAccount: _meta?.vatOutputAccount ?? 2200,
              advanceAccount: _meta?.advanceAccount ?? 2130,
              categories: [...existing, picked],
            );
          });
        }
      }
    }
    if (!mounted) return;
    setState(() => _categoryCode = picked.code.isEmpty ? null : picked.code);
  }

  Future<void> _delete() async {
    final code = widget.customerCode ?? 0;
    if (code <= 0) return;
    final label = _name.text.trim().isNotEmpty ? _name.text.trim() : 'customer $code';
    final password = await showMasterDeletePasswordDialog(
      context,
      title: 'Delete customer',
      entityLabel: label,
    );
    if (password == null || password.isEmpty || !mounted) return;
    setState(() => _saving = true);
    try {
      final result =
          await context.read<CustomerMasterService>().deleteCustomer(code, password: password);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Customer deleted.')),
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
        const SnackBar(content: Text('Customer name is required.')),
      );
      return;
    }
    final mobile = _mobile.text.trim();
    final telephone = _telephone.text.trim();
    if (mobile.isEmpty && telephone.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Mobile No or Telephone is required.')),
      );
      return;
    }
    if (_billingType == 'CREDIT') {
      final limit = double.tryParse(_creditLimit.text.trim().replaceAll(',', '')) ?? 0;
      final term = double.tryParse(_creditTerm.text.trim().replaceAll(',', '')) ?? 0;
      if (limit <= 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Credit Limit is required for Credit customers.')),
        );
        return;
      }
      if (term <= 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Credit Term (Days) is required for Credit customers.')),
        );
        return;
      }
    }

    final meta = _meta;
    final payload = <String, dynamic>{
      'customername': name,
      'customer_billing_type': _billingType,
      'customercategory': int.tryParse(_categoryCode ?? '') ?? 0,
      'mobile': mobile,
      'telephone': telephone,
      'address': _address.text.trim(),
      'email': _email.text.trim(),
      'whatsapp': _whatsapp.text.trim(),
      'crno': _crno.text.trim(),
      'creditlimit': double.tryParse(_creditLimit.text.trim().replaceAll(',', '')) ?? 0,
      'creditterm': double.tryParse(_creditTerm.text.trim().replaceAll(',', '')) ?? 2,
      if (!_isEdit && meta != null) ...{
        'receivableaccount': meta.receivableAccount,
        'salesaccount': meta.salesAccount,
        'vatoutputaccount': meta.vatOutputAccount,
        'advanceaccount': meta.advanceAccount,
      },
    };
    setState(() => _saving = true);
    try {
      final svc = context.read<CustomerMasterService>();
      final result = _isEdit
          ? await svc.updateCustomer(widget.customerCode!, payload)
          : await svc.createCustomer(payload);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.message.isNotEmpty
                ? result.message
                : (_isEdit ? 'Customer updated.' : 'Customer saved.'),
          ),
        ),
      );
      // Return save payload so Sales pickers can select the new customer.
      // Masters list/detail treat any non-null result as success.
      Navigator.of(context).pop(
        CustomerSaveResult(
          customerCode: result.customerCode > 0
              ? result.customerCode
              : (widget.customerCode ?? 0),
          customerName: result.customerName.isNotEmpty ? result.customerName : name,
          message: result.message,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
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
          _isEdit ? 'Edit Customer' : 'New Customer',
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
                      if (_isEdit && (widget.customerCode ?? 0) > 0)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(
                            'Customer code: ${widget.customerCode}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        )
                      else if (_meta != null && _meta!.nextCustomerCode > 0)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(
                            'Next code: ${_meta!.nextCustomerCode}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        ),
                      _card(
                        children: [
                          _label('Customer Name *'),
                          TextField(
                            controller: _name,
                            textCapitalization: TextCapitalization.characters,
                            decoration: _decoration('As in ERP customer master'),
                          ),
                          const SizedBox(height: 14),
                          _label('Customer Type *'),
                          const SizedBox(height: 6),
                          SegmentedButton<String>(
                            segments: const [
                              ButtonSegment(value: 'CASH', label: Text('Cash'), icon: Icon(Icons.payments_outlined, size: 18)),
                              ButtonSegment(value: 'CREDIT', label: Text('Credit'), icon: Icon(Icons.credit_card_rounded, size: 18)),
                            ],
                            selected: {_billingType},
                            onSelectionChanged: (s) => setState(() => _billingType = s.first),
                          ),
                          const SizedBox(height: 14),
                          _label('Customer Category'),
                          Builder(
                            builder: (context) {
                              final catLabel = _categoryLabel();
                              return InkWell(
                                onTap: _pickCategory,
                                borderRadius: BorderRadius.circular(10),
                                child: InputDecorator(
                                  decoration: _decoration('Select or add category').copyWith(
                                    suffixIcon: Icon(Icons.search_rounded, size: 20, color: Colors.grey.shade600),
                                  ),
                                  child: Text(
                                    catLabel.isNotEmpty ? catLabel : 'Optional — tap to select or add',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 15,
                                      color: catLabel.isNotEmpty
                                          ? const Color(0xFF262C50)
                                          : Colors.grey.shade500,
                                    ),
                                  ),
                                ),
                              );
                            },
                          ),
                          if (_billingType == 'CREDIT') ...[
                            const SizedBox(height: 14),
                            Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      _label('Credit Limit *'),
                                      NumericTextField(
                                        controller: _creditLimit,
                                        decoration: _decoration('0.00'),
                                      ),
                                    ],
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      _label('Credit Term (Days) *'),
                                      NumericTextField(
                                        controller: _creditTerm,
                                        decoration: _decoration('Days'),
                                        maxDecimalPlaces: 0,
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 12),
                      _card(
                        children: [
                          _label('Mobile'),
                          TextField(
                            controller: _mobile,
                            keyboardType: TextInputType.phone,
                            inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9+\-\s]'))],
                            decoration: _decoration('Mobile number'),
                          ),
                          const SizedBox(height: 12),
                          _label('Telephone'),
                          TextField(
                            controller: _telephone,
                            keyboardType: TextInputType.phone,
                            inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9+\-\s]'))],
                            decoration: _decoration('Telephone'),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Mobile or Telephone is required.',
                            style: TextStyle(fontSize: 11.5, color: Colors.grey.shade600),
                          ),
                          const SizedBox(height: 12),
                          _label('WhatsApp'),
                          TextField(
                            controller: _whatsapp,
                            keyboardType: TextInputType.phone,
                            decoration: _decoration('Optional'),
                          ),
                          const SizedBox(height: 12),
                          _label('Email'),
                          TextField(
                            controller: _email,
                            keyboardType: TextInputType.emailAddress,
                            decoration: _decoration('Optional'),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      _card(
                        children: [
                          _label('Address'),
                          TextField(
                            controller: _address,
                            maxLines: 3,
                            decoration: _decoration('Street / area'),
                          ),
                          const SizedBox(height: 12),
                          _label('CR No'),
                          TextField(
                            controller: _crno,
                            decoration: _decoration('Optional'),
                          ),
                        ],
                      ),
                      const SizedBox(height: 18),
                      FilledButton(
                        onPressed: _saving ? null : _save,
                        style: FilledButton.styleFrom(
                          backgroundColor: _accent,
                          minimumSize: const Size.fromHeight(48),
                        ),
                        child: Text(
                          _isEdit ? 'Update Customer' : 'Save Customer',
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
                          label: const Text('Delete customer', style: TextStyle(fontWeight: FontWeight.w700)),
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
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

class _CustomerCategoryPickerSheet extends StatefulWidget {
  const _CustomerCategoryPickerSheet({
    required this.categories,
    this.selectedCode,
    required this.onCreateCategory,
  });

  final List<CustomerCategoryOption> categories;
  final String? selectedCode;
  final Future<CustomerCategoryOption> Function(String name) onCreateCategory;

  @override
  State<_CustomerCategoryPickerSheet> createState() => _CustomerCategoryPickerSheetState();
}

class _CustomerCategoryPickerSheetState extends State<_CustomerCategoryPickerSheet> {
  static const _accent = Color(0xFF1565C0);

  final _search = TextEditingController();
  late List<CustomerCategoryOption> _categories;
  late List<CustomerCategoryOption> _filtered;
  bool _creating = false;

  @override
  void initState() {
    super.initState();
    _categories = List<CustomerCategoryOption>.from(widget.categories);
    _filtered = _categories;
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
        _filtered = _categories;
        return;
      }
      _filtered = _categories
          .where((c) => c.code.toLowerCase().contains(q) || c.name.toLowerCase().contains(q))
          .toList(growable: false);
    });
  }

  Future<void> _addCategory() async {
    final nameCtrl = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add customer category'),
        content: TextField(
          controller: nameCtrl,
          autofocus: true,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(
            labelText: 'Category name *',
            hintText: 'As in ERP customer category',
          ),
          onSubmitted: (v) => Navigator.of(ctx).pop(v.trim()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(nameCtrl.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    final trimmed = (name ?? '').trim();
    if (trimmed.isEmpty || !mounted) return;

    setState(() => _creating = true);
    try {
      final created = await widget.onCreateCategory(trimmed);
      if (!mounted) return;
      setState(() {
        _categories = [..._categories.where((c) => c.code != created.code), created];
        final q = _search.text.trim().toLowerCase();
        _filtered = q.isEmpty
            ? _categories
            : _categories
                .where((c) => c.code.toLowerCase().contains(q) || c.name.toLowerCase().contains(q))
                .toList(growable: false);
        _creating = false;
      });
      Navigator.pop(context, created);
    } catch (e) {
      if (!mounted) return;
      setState(() => _creating = false);
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    }
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
          Row(
            children: [
              const Expanded(
                child: Text('Customer category', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17)),
              ),
              TextButton.icon(
                onPressed: _creating ? null : _addCategory,
                icon: _creating
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.add_rounded, size: 20),
                label: const Text('Add'),
              ),
            ],
          ),
          const SizedBox(height: 8),
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
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: _creating ? null : () => Navigator.pop(context, CustomerCategoryOption(code: '', name: '')),
              child: const Text('Clear selection'),
            ),
          ),
          if (_filtered.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: Text(
                  _categories.isEmpty ? 'No categories yet. Tap Add to create one.' : 'No matches.',
                  style: TextStyle(color: Colors.grey.shade600),
                  textAlign: TextAlign.center,
                ),
              ),
            )
          else
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.45),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _filtered.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final c = _filtered[i];
                  final selected = c.code == widget.selectedCode;
                  return ListTile(
                    onTap: _creating ? null : () => Navigator.pop(context, c),
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
