import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/network/api_error_handler.dart';
import '../../core/ui/app_snackbar.dart';
import '../../services/sales_service.dart';
import '../../widgets/api_error_banner.dart';
import 'sales_ai_mode_screen.dart';
import 'sales_ai_session_header.dart';
import 'sales_customer_picker_sheet.dart';
import '../../core/theme/app_theme.dart';

/// Same header as Sales Invoice — shown before AI voice shopping.
class SalesAiModeSetupScreen extends StatefulWidget {
  const SalesAiModeSetupScreen({super.key});

  @override
  State<SalesAiModeSetupScreen> createState() => _SalesAiModeSetupScreenState();
}

class _SalesAiModeSetupScreenState extends State<SalesAiModeSetupScreen> {
  static const _accent = Color(0xFF1565C0);
  static const _bg = Color(0xFFF4F5F8);
  static const _border = Color(0xFFDDE1EA);

  bool _loading = true;
  String? _loadError;
  Object? _loadCause;

  String _billno = '';
  String _billDate = '';
  String _billTime = '';
  String _locationName = '';
  SalesInvoiceFeatures _features = const SalesInvoiceFeatures();

  String _billingType = 'CASH';
  bool _walkIn = true;
  SalesCustomerOption? _customer;
  SalesWarehouseOption? _headerWarehouse;
  final _address = TextEditingController();
  final _orderNo = TextEditingController();
  final _remarks = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _address.dispose();
    _orderNo.dispose();
    _remarks.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _loadError = null;
      _loadCause = null;
    });
    try {
      final svc = context.read<SalesService>();
      final ctx = await svc.getInvoiceOpen(peek: true);
      if (!mounted) return;
      setState(() {
        _billno = ctx.billno;
        _billDate = ctx.billDate;
        _billTime = ctx.billTime;
        _locationName = ctx.locationName;
        _features = ctx.features;
        if (ctx.defaultWarehouseId != null && ctx.defaultWarehouseId! > 0) {
          _headerWarehouse = SalesWarehouseOption(
            warehouseId: '${ctx.defaultWarehouseId}',
            warehouseCode: ctx.defaultWarehouseCode,
            warehouseName: ctx.defaultWarehouseName,
            label: ctx.defaultWarehouseLabel.isNotEmpty
                ? ctx.defaultWarehouseLabel
                : ctx.defaultWarehouseName,
          );
        }
        _loading = false;
      });
      if (_features.warehouseEnabled &&
          (_headerWarehouse == null || _headerWarehouse!.warehouseId.isEmpty)) {
        final sole = await svc.soleWarehouseIfOnlyOne();
        if (!mounted) return;
        if (sole != null) {
          setState(() => _headerWarehouse = sole);
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loadCause = e;
        _loadError = handleApiError(context, e, authenticatedContext: true);
        _loading = false;
      });
    }
  }

  void _setBillingType(String type) {
    setState(() {
      _billingType = type;
      if (type == 'CREDIT') {
        _walkIn = false;
      }
    });
  }

  void _setWalkIn(bool value) {
    setState(() {
      _walkIn = value;
      if (value) {
        _customer = null;
        _billingType = 'CASH';
        _address.clear();
      }
    });
  }

  String? _validateHeader() {
    if (_features.orderNoMandatory && !_walkIn && _orderNo.text.trim().isEmpty) {
      return 'Order No is required.';
    }
    if (_billingType == 'CREDIT' && _customer == null) {
      return 'Credit sale requires a customer.';
    }
    if (!_walkIn && _customer == null) {
      return 'Select a customer or choose walk-in cash sale.';
    }
    if (_features.warehouseEnabled && (_headerWarehouse == null || _headerWarehouse!.warehouseId.isEmpty)) {
      return 'Select a warehouse.';
    }
    return null;
  }

  Future<void> _pickCustomer() async {
    final svc = context.read<SalesService>();
    final picked = await SalesCustomerPickerSheet.open(
      context,
      service: svc,
      billingType: _billingType,
    );
    if (picked == null || !mounted) return;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    SalesCustomerOption customer = picked;
    try {
      customer = await svc.fetchCustomerOutstanding(picked.code);
    } catch (_) {}

    if (mounted) Navigator.of(context, rootNavigator: true).pop();
    if (!mounted) return;
    setState(() {
      _walkIn = false;
      _customer = customer;
      if (customer.address.isNotEmpty) _address.text = customer.address;
    });
  }

  Future<void> _pickWarehouse() async {
    final svc = context.read<SalesService>();
    final picked = await showModalBottomSheet<SalesWarehouseOption>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => _AiWarehousePickerSheet(service: svc),
    );
    if (picked == null || !mounted) return;
    setState(() => _headerWarehouse = picked);
  }

  void _goNext() {
    final err = _validateHeader();
    if (err != null) {
      showAppSnackBar(context, err);
      return;
    }
    final header = SalesAiSessionHeader(
      billingType: _billingType,
      walkIn: _walkIn,
      customer: _customer,
      warehouse: _headerWarehouse,
      address: _address.text.trim(),
      orderNo: _orderNo.text.trim(),
      remarks: _remarks.text.trim(),
      billno: _billno,
      billDate: _billDate,
      billTime: _billTime,
      locationName: _locationName,
      features: _features,
    );
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => SalesAiModeScreen(header: header),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('AI Sales Mode', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _accent))
          : Column(
              children: [
                if (_loadError != null) ApiErrorBanner(message: _loadError!, error: _loadCause),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                    child: _headerForm(),
                  ),
                ),
                Container(
                  color: Colors.white,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Divider(height: 1, color: Color(0xFFE8EBF3)),
                      SafeArea(
                        top: false,
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
                          child: Row(
                            children: [
                              Expanded(
                                child: OutlinedButton(
                                  onPressed: () => Navigator.of(context).maybePop(),
                                  child: const Text('Cancel'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                flex: 2,
                                child: FilledButton.icon(
                                  style: FilledButton.styleFrom(backgroundColor: _accent),
                                  onPressed: _loadError != null ? null : _goNext,
                                  icon: const Icon(Icons.arrow_forward_rounded),
                                  label: const Text('Next'),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }

  Widget _card({required Widget child, EdgeInsetsGeometry? padding}) => Container(
        width: double.infinity,
        padding: padding ?? const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: _border),
        ),
        child: child,
      );

  Widget _headerForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _docHeader(),
        const SizedBox(height: 12),
        _card(child: _billingTypeSelector()),
        const SizedBox(height: 12),
        _card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (!_walkIn)
                _pickerField(
                  label: _billingType == 'CREDIT' ? 'Customer *' : 'Customer',
                  value: _customer?.name ?? '',
                  hint: _billingType == 'CREDIT' ? 'Select credit customer' : 'Select customer (optional for cash)',
                  subtitle: _customer == null
                      ? null
                      : 'Code ${_customer!.code} • Master: ${_customer!.billingType}',
                  icon: Icons.person_search_outlined,
                  iconColor: const Color(0xFF1565C0),
                  onTap: _pickCustomer,
                )
              else
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const CircleAvatar(
                    backgroundColor: Color(0xFFE8F5E9),
                    child: Icon(Icons.storefront_outlined, color: Color(0xFF2E7D32)),
                  ),
                  title: const Text('Walk-in customer', style: TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: const Text('Customer code 0 • Cash invoice'),
                  trailing: TextButton(
                    onPressed: () => _setWalkIn(false),
                    child: const Text('Change'),
                  ),
                ),
              if (_customer != null && !_walkIn) ...[
                const Divider(height: 1),
                Padding(padding: const EdgeInsets.only(top: 10), child: _creditBanner()),
              ],
              if (!_walkIn) ...[
                const Divider(height: 24),
                TextField(
                  controller: _address,
                  decoration: _fieldDec('Delivery address'),
                  maxLines: 2,
                ),
              ],
            ],
          ),
        ),
        if (_features.warehouseEnabled) ...[
          const SizedBox(height: 12),
          _card(
            child: _pickerField(
              label: 'Warehouse *',
              value: _headerWarehouse?.label.isNotEmpty == true
                  ? _headerWarehouse!.label
                  : (_headerWarehouse?.warehouseName ?? ''),
              hint: 'Select warehouse',
              subtitle: _headerWarehouse == null ? 'Required for stock allocation' : 'ID ${_headerWarehouse!.warehouseId}',
              icon: Icons.warehouse_outlined,
              iconColor: const Color(0xFFE65100),
              onTap: _pickWarehouse,
            ),
          ),
        ],
        const SizedBox(height: 12),
        _card(
          child: Column(
            children: [
              TextField(
                controller: _orderNo,
                decoration: _fieldDec(
                  (_features.orderNoMandatory && !_walkIn) ? 'Order No. *' : 'Order No. (optional)',
                  hint: _walkIn
                      ? 'Leave blank for walk-in'
                      : (_features.orderNoMandatory ? 'Customer PO / reference' : 'Optional PO / reference'),
                ),
              ),
              const SizedBox(height: 12),
              TextField(controller: _remarks, decoration: _fieldDec('Remarks'), maxLines: 2),
            ],
          ),
        ),
      ],
    );
  }

  Widget _docHeader() => _card(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _locationName.isNotEmpty ? _locationName : 'AI Sales Mode',
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Color(0xFF262C50)),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _walkIn
                        ? 'Walk-in cash sale'
                        : (_billingType == 'CREDIT' ? 'Credit sale' : 'Cash sale'),
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('Bill No.', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
                Text(_billno.isEmpty ? '—' : _billno, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                const SizedBox(height: 6),
                Text(
                  _billDate.isEmpty ? '—' : '$_billDate  ${_billTime.isNotEmpty ? _billTime : ''}'.trim(),
                  style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
                ),
              ],
            ),
          ],
        ),
      );

  Widget _billingTypeSelector() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Billing type', style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'CASH', label: Text('Cash'), icon: Icon(Icons.payments_outlined, size: 18)),
            ButtonSegment(value: 'CREDIT', label: Text('Credit'), icon: Icon(Icons.credit_score_outlined, size: 18)),
          ],
          selected: {_billingType},
          onSelectionChanged: (s) => _setBillingType(s.first),
        ),
        const SizedBox(height: 10),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _walkIn,
          onChanged: _billingType == 'CREDIT' ? null : _setWalkIn,
          title: const Text('Walk-in cash sale', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
          subtitle: Text(
            _walkIn
                ? 'No customer — same as POS walk-in (customer code 0, bill type C).'
                : 'Enable for counter / walk-in customers without a customer master record.',
            style: TextStyle(fontSize: 12, color: Colors.grey.shade600, height: 1.3),
          ),
        ),
      ],
    );
  }

  Widget _creditBanner() {
    if (_customer == null) return const SizedBox.shrink();
    final c = _customer!;
    final isCredit = c.billingType == 'CREDIT';
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFF0F7FF),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFBBDEFB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            isCredit ? 'Credit customer' : 'Cash customer',
            style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF1565C0)),
          ),
          const SizedBox(height: 4),
          Text(
            isCredit
                ? '${c.creditLimitLabel} • GL outstanding ${c.currentCredit.toStringAsFixed(2)}'
                : 'GL outstanding ${c.displayOutstanding.toStringAsFixed(2)}',
            style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
          ),
        ],
      ),
    );
  }

  Widget _pickerField({
    required String label,
    required String value,
    required String hint,
    required IconData icon,
    required VoidCallback onTap,
    String? subtitle,
    Color iconColor = const Color(0xFF1565C0),
  }) =>
      InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(10),
                  color: Color.lerp(iconColor, Colors.white, 0.88)!,
                ),
                child: Icon(icon, size: 22, color: iconColor),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(label, style: TextStyle(fontSize: 11, color: iconColor.withValues(alpha: 0.75))),
                    const SizedBox(height: 2),
                    Text(
                      value.isNotEmpty ? value : hint,
                      style: TextStyle(
                        fontWeight: value.isNotEmpty ? FontWeight.w600 : FontWeight.w400,
                        color: value.isNotEmpty ? iconColor : Colors.grey.shade500,
                      ),
                    ),
                    if (subtitle != null && subtitle.isNotEmpty)
                      Text(subtitle, style: TextStyle(fontSize: 11, color: iconColor.withValues(alpha: 0.65))),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, size: 20, color: iconColor.withValues(alpha: 0.45)),
            ],
          ),
        ),
      );

  InputDecoration _fieldDec(String label, {String? hint}) => InputDecoration(
        labelText: label,
        hintText: hint,
        border: const OutlineInputBorder(),
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      );
}

class _AiWarehousePickerSheet extends StatefulWidget {
  const _AiWarehousePickerSheet({required this.service});
  final SalesService service;

  @override
  State<_AiWarehousePickerSheet> createState() => _AiWarehousePickerSheetState();
}

class _AiWarehousePickerSheetState extends State<_AiWarehousePickerSheet> {
  final _search = TextEditingController();
  List<SalesWarehouseOption> _rows = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _fetch('');
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _fetch(String q) async {
    setState(() => _loading = true);
    try {
      final rows = await widget.service.searchWarehouses(q: q);
      if (mounted) setState(() => _rows = rows);
    } catch (_) {
      if (mounted) setState(() => _rows = []);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final h = MediaQuery.of(context).size.height * 0.6;
    return SizedBox(
      height: h,
      child: Column(
        children: [
          const SizedBox(height: 8),
          Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.grey.shade300, borderRadius: BorderRadius.circular(2))),
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search warehouse',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              ),
              onSubmitted: _fetch,
              onChanged: _fetch,
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView.separated(
                    itemCount: _rows.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final w = _rows[i];
                      return ListTile(
                        title: Text(w.label.isNotEmpty ? w.label : w.warehouseName),
                        subtitle: Text('ID ${w.warehouseId}${w.warehouseCode.isNotEmpty ? ' • ${w.warehouseCode}' : ''}'),
                        onTap: () => Navigator.of(context).pop(w),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
