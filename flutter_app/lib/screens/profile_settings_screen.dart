import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/storage/printer_storage.dart';
import '../providers/auth_provider.dart';
import 'change_password_screen.dart';
import 'printer_settings_screen.dart';
import '../core/theme/app_theme.dart';

class ProfileSettingsScreen extends StatefulWidget {
  const ProfileSettingsScreen({super.key});

  @override
  State<ProfileSettingsScreen> createState() => _ProfileSettingsScreenState();
}

class _ProfileSettingsScreenState extends State<ProfileSettingsScreen> {
  String? _selectedTenant;
  SavedPrinter? _selectedPrinter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthProvider>().loadTenantOptions();
      _loadPrinter();
    });
  }

  Future<void> _loadPrinter() async {
    final printer = await PrinterStorage.readSelected();
    if (mounted) setState(() => _selectedPrinter = printer);
  }

  Future<void> _openPrinterSettings() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => const PrinterSettingsScreen()),
    );
    await _loadPrinter();
  }

  Future<void> _openChangePassword() async {
    await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(builder: (_) => const ChangePasswordScreen()),
    );
  }

  String _initials(String? username) {
    final name = (username ?? '').trim();
    if (name.isEmpty) return '?';
    final parts = name.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.length >= 2) {
      return '${parts.first[0]}${parts[1][0]}'.toUpperCase();
    }
    return name.length >= 2 ? name.substring(0, 2).toUpperCase() : name[0].toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final currentTenant = auth.user?.tenantId;
    _selectedTenant ??= currentTenant;
    final tenantIds = auth.tenantOptions.map((e) => e.tenantId).toSet();
    final dropdownValue = tenantIds.contains(_selectedTenant) ? _selectedTenant : null;

    final username = auth.user?.username ?? '-';
    final employeeCode = auth.user?.employeeCode ?? '';

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7FC),
      appBar: AppBar(
        backgroundColor: AppTheme.appBarBlue,
        foregroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('Profile', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        centerTitle: true,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFE8EBF3)),
                ),
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 30,
                      backgroundColor: const Color(0xFF5B3DF5).withValues(alpha: 0.12),
                      child: Text(
                        _initials(auth.user?.username),
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF5B3DF5),
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            username,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w800,
                              color: Color(0xFF262C50),
                            ),
                          ),
                          if (employeeCode.isNotEmpty) ...[
                            const SizedBox(height: 2),
                            Text(
                              'Employee: $employeeCode',
                              style: const TextStyle(fontSize: 12, color: Color(0xFF7C8191)),
                            ),
                          ],
                          const SizedBox(height: 4),
                          Text(
                            auth.user?.roleId ?? '-',
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFF5B3DF5),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              _SectionCard(
                title: 'Account',
              child: Column(
                children: [
                  _InfoRow(label: 'Username', value: username),
                  _InfoRow(label: 'Role', value: auth.user?.roleId ?? '-'),
                  _InfoRow(label: 'Tenant', value: auth.user?.tenantId ?? '-'),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _SectionCard(
              title: 'Security',
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF5B3DF5).withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.lock_reset_rounded, color: Color(0xFF5B3DF5)),
                ),
                title: const Text('Change password', style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text(
                  'Update your login password',
                  style: TextStyle(fontSize: 12, color: Color(0xFF7C8191)),
                ),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: _openChangePassword,
              ),
            ),
            const SizedBox(height: 12),
            _SectionCard(
              title: 'Tenant Switching',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF4F1FF),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 28,
                          height: 28,
                          decoration: BoxDecoration(
                            color: const Color(0xFF5B3DF5).withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Icon(Icons.apartment_rounded, size: 17, color: Color(0xFF5B3DF5)),
                        ),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            'Choose tenant database to view corresponding ERP data.',
                            style: TextStyle(
                              fontSize: 11.5,
                              color: Color(0xFF666D80),
                              height: 1.25,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (auth.isTenantLoading) const LinearProgressIndicator(),
                  if (auth.isTenantLoading) const SizedBox(height: 10),
                  DropdownButtonFormField<String>(
                    initialValue: dropdownValue,
                    isExpanded: true,
                    decoration: InputDecoration(
                      labelText: 'Switch Tenant',
                      filled: true,
                      fillColor: const Color(0xFFF5F6FB),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: Color(0xFFE4E7F0)),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: Color(0xFFE4E7F0)),
                      ),
                    ),
                    items: auth.tenantOptions
                        .map(
                          (t) => DropdownMenuItem<String>(
                            value: t.tenantId,
                            child: Text(
                              '${t.displayName} (${t.tenantId})',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 12.2, fontWeight: FontWeight.w500),
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: auth.canSwitchTenant
                        ? (value) => setState(() => _selectedTenant = value)
                        : null,
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF5B3DF5),
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      ),
                      onPressed: (!auth.canSwitchTenant ||
                              auth.isTenantLoading ||
                              _selectedTenant == null ||
                              _selectedTenant == currentTenant)
                          ? null
                          : () async {
                              final ok = await context.read<AuthProvider>().switchTenant(_selectedTenant!);
                              if (!context.mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(
                                    ok ? 'Tenant switched to $_selectedTenant' : (auth.error ?? 'Failed to switch tenant'),
                                  ),
                                ),
                              );
                            },
                      child: const Text('Apply Tenant'),
                    ),
                  ),
                  if (!auth.canSwitchTenant)
                    const Padding(
                      padding: EdgeInsets.only(top: 8),
                      child: Text(
                        'Tenant switching is allowed only for admin or multi-location users.',
                        style: TextStyle(fontSize: 12, color: Color(0xFF7C8191)),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _SectionCard(
              title: 'Printer',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: const Color(0xFF5B3DF5).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(Icons.print_outlined, color: Color(0xFF5B3DF5)),
                    ),
                    title: const Text('Choose printer', style: TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(
                      _selectedPrinter?.label ?? 'No printer selected',
                      style: const TextStyle(fontSize: 12, color: Color(0xFF7C8191)),
                    ),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: _openPrinterSettings,
                  ),
                  const Text(
                    'Select a paired Bluetooth receipt printer for invoices and receipts.',
                    style: TextStyle(fontSize: 12, color: Color(0xFF7C8191), height: 1.35),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _SectionCard(
              title: 'Session',
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.tonalIcon(
                  style: FilledButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  onPressed: () async {
                    final auth = context.read<AuthProvider>();
                    await auth.logout();
                    // MaterialApp auth key rebuilds to Login; no need to pop manually.
                  },
                  icon: const Icon(Icons.logout_rounded),
                  label: const Text('Logout'),
                ),
              ),
            ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFE8EBF3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
              color: Color(0xFF5B3DF5),
            ),
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xFFF5F6FB),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(fontSize: 12, color: Color(0xFF7C8191)),
              ),
            ),
            Text(
              value,
              style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF2D3355)),
            ),
          ],
        ),
      ),
    );
  }
}

