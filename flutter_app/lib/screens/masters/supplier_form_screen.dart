import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../services/supplier_master_service.dart';
import '../../widgets/loading_overlay.dart';
import '../../widgets/master_delete_dialog.dart';
import '../../core/theme/app_theme.dart';

class SupplierFormScreen extends StatefulWidget {
  const SupplierFormScreen({
    super.key,
    this.supplierCode,
    this.prefillName = '',
    this.prefillAddress = '',
    this.prefillMobile = '',
    this.prefillTelephone = '',
    this.prefillEmail = '',
    this.prefillContact = '',
    this.prefillCr = '',
    this.prefillRef = '',
  });

  /// When set, form loads and updates an existing supplier.
  final int? supplierCode;

  /// Optional AI / GRN invoice prefill (ERP supplier create query params).
  final String prefillName;
  final String prefillAddress;
  final String prefillMobile;
  final String prefillTelephone;
  final String prefillEmail;
  final String prefillContact;
  final String prefillCr;
  final String prefillRef;

  @override
  State<SupplierFormScreen> createState() => _SupplierFormScreenState();
}

class _SupplierFormScreenState extends State<SupplierFormScreen> {
  static const _accent = Color(0xFF2E7D32);

  final _name = TextEditingController();
  final _mobile = TextEditingController();
  final _telephone = TextEditingController();
  final _address = TextEditingController();
  final _email = TextEditingController();
  final _contact = TextEditingController();
  final _crno = TextEditingController();
  final _supref = TextEditingController();

  String _supplierType = 'LOCAL';
  String _billingType = 'CASH';
  bool _loadingMeta = true;
  bool _saving = false;
  String? _metaError;
  SupplierOpenContext? _meta;

  bool get _isEdit => (widget.supplierCode ?? 0) > 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadMeta());
  }

  @override
  void dispose() {
    _name.dispose();
    _mobile.dispose();
    _telephone.dispose();
    _address.dispose();
    _email.dispose();
    _contact.dispose();
    _crno.dispose();
    _supref.dispose();
    super.dispose();
  }

  Future<void> _loadMeta() async {
    setState(() {
      _loadingMeta = true;
      _metaError = null;
    });
    try {
      final svc = context.read<SupplierMasterService>();
      final meta = await svc.getOpenContext();
      if (!mounted) return;
      setState(() {
        _meta = meta;
        if (!_isEdit && meta.supplierTypes.isNotEmpty) {
          _supplierType = meta.supplierTypes.first;
        }
      });
      if (_isEdit) {
        final detail = await svc.getSupplier(widget.supplierCode!);
        if (!mounted) return;
        _name.text = detail.supplierName;
        _mobile.text = detail.mobile;
        _telephone.text = detail.telephone;
        _address.text = detail.address;
        _email.text = detail.email;
        _contact.text = detail.contactPerson;
        _crno.text = detail.supplierCr;
        _supref.text = detail.supplierRef;
        _supplierType = detail.supplierType.isNotEmpty ? detail.supplierType : 'LOCAL';
        _billingType = detail.billingType == 'CREDIT' ? 'CREDIT' : 'CASH';
      } else {
        // AI GRN / invoice prefill (same fields ERP opens on Create supplier)
        if (widget.prefillName.trim().isNotEmpty) {
          _name.text = widget.prefillName.trim().toUpperCase();
        }
        if (widget.prefillAddress.trim().isNotEmpty) _address.text = widget.prefillAddress.trim();
        if (widget.prefillMobile.trim().isNotEmpty) _mobile.text = widget.prefillMobile.trim();
        if (widget.prefillTelephone.trim().isNotEmpty) _telephone.text = widget.prefillTelephone.trim();
        if (widget.prefillEmail.trim().isNotEmpty) _email.text = widget.prefillEmail.trim();
        if (widget.prefillContact.trim().isNotEmpty) _contact.text = widget.prefillContact.trim();
        if (widget.prefillCr.trim().isNotEmpty) _crno.text = widget.prefillCr.trim();
        if (widget.prefillRef.trim().isNotEmpty) _supref.text = widget.prefillRef.trim();
      }
      if (!mounted) return;
      setState(() => _loadingMeta = false);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _metaError = handleApiError(context, e, authenticatedContext: true);
        _loadingMeta = false;
      });
    }
  }

  Future<void> _delete() async {
    final code = widget.supplierCode ?? 0;
    if (code <= 0) return;
    final label = _name.text.trim().isNotEmpty ? _name.text.trim() : 'supplier $code';
    final password = await showMasterDeletePasswordDialog(
      context,
      title: 'Delete supplier',
      entityLabel: label,
    );
    if (password == null || password.isEmpty || !mounted) return;
    setState(() => _saving = true);
    try {
      final result =
          await context.read<SupplierMasterService>().deleteSupplier(code, password: password);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message.isNotEmpty ? result.message : 'Supplier deleted.')),
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
        const SnackBar(content: Text('Supplier name is required.')),
      );
      return;
    }

    final meta = _meta;
    final payload = <String, dynamic>{
      'suppliername': name,
      'suppliertype': _supplierType,
      'supplier_billing_type': _billingType,
      'mobile': _mobile.text.trim(),
      'telephone': _telephone.text.trim(),
      'address': _address.text.trim(),
      'emailid': _email.text.trim(),
      'contactperson': _contact.text.trim(),
      'suppliercr': _crno.text.trim(),
      'supref': _supref.text.trim(),
      if (meta != null) ...{
        'cashaccount': meta.cashAccount,
        'payableaccount': meta.payableAccount,
        'purchaseaccount': meta.purchaseAccount,
        'vatinputaccount': meta.vatInputAccount,
        'advanceaccount': meta.advanceAccount,
      },
    };

    setState(() => _saving = true);
    try {
      final svc = context.read<SupplierMasterService>();
      final result = _isEdit
          ? await svc.updateSupplier(widget.supplierCode!, payload)
          : await svc.createSupplier(payload);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.message.isNotEmpty
                ? result.message
                : (_isEdit ? 'Supplier updated.' : 'Supplier saved.'),
          ),
        ),
      );
      Navigator.of(context).pop(result);
    } catch (e) {
      if (!mounted) return;
      showApiErrorSnackBar(context, e, authenticatedContext: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final types = _meta?.supplierTypes ?? const ['LOCAL', 'INTERNATIONAL'];
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
          _isEdit ? 'Edit Supplier' : 'New Supplier',
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
                      if (!_isEdit && _meta != null && _meta!.nextSupplierCode > 0)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(
                            'Next code: ${_meta!.nextSupplierCode}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        ),
                      if (_isEdit && (widget.supplierCode ?? 0) > 0)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: Text(
                            'Code: ${widget.supplierCode}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                        ),
                      _card(
                        children: [
                          _label('Supplier Name *'),
                          TextField(
                            controller: _name,
                            textCapitalization: TextCapitalization.characters,
                            maxLength: 40,
                            decoration: _decoration('As in ERP supplier master'),
                          ),
                          const SizedBox(height: 8),
                          _label('Supplier Type'),
                          const SizedBox(height: 6),
                          SegmentedButton<String>(
                            segments: [
                              for (final t in types)
                                ButtonSegment(
                                  value: t,
                                  label: Text(t == 'INTERNATIONAL' ? 'Intl' : 'Local'),
                                ),
                            ],
                            selected: {_supplierType},
                            onSelectionChanged: (s) => setState(() => _supplierType = s.first),
                          ),
                          const SizedBox(height: 14),
                          _label('Billing Type *'),
                          const SizedBox(height: 6),
                          SegmentedButton<String>(
                            segments: const [
                              ButtonSegment(
                                value: 'CASH',
                                label: Text('Cash'),
                                icon: Icon(Icons.payments_outlined, size: 18),
                              ),
                              ButtonSegment(
                                value: 'CREDIT',
                                label: Text('Credit'),
                                icon: Icon(Icons.account_balance_outlined, size: 18),
                              ),
                            ],
                            selected: {_billingType},
                            onSelectionChanged: (s) => setState(() => _billingType = s.first),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            _billingType == 'CASH'
                                ? 'Cash account: ${_meta?.cashAccount ?? 1111}'
                                : 'Accounts payable: ${_meta?.payableAccount ?? 2110}',
                            style: TextStyle(fontSize: 12.5, color: Colors.grey.shade600),
                          ),
                          const SizedBox(height: 12),
                          _label('Contact Person'),
                          TextField(
                            controller: _contact,
                            decoration: _decoration('Optional'),
                          ),
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
                          const SizedBox(height: 12),
                          _label('Supplier Ref'),
                          TextField(
                            controller: _supref,
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
                          _isEdit ? 'Update Supplier' : 'Save Supplier',
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
                          label: const Text('Delete supplier', style: TextStyle(fontWeight: FontWeight.w700)),
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
