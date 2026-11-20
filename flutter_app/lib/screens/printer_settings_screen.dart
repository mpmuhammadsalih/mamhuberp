import 'dart:io';

import 'package:blue_thermal_printer/blue_thermal_printer.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/storage/printer_storage.dart';
import '../core/theme/app_theme.dart';

class PrinterSettingsScreen extends StatefulWidget {
  const PrinterSettingsScreen({super.key});

  @override
  State<PrinterSettingsScreen> createState() => _PrinterSettingsScreenState();
}

class _PrinterSettingsScreenState extends State<PrinterSettingsScreen> {
  static const _accent = Color(0xFF5B3DF5);

  final _bluetooth = BlueThermalPrinter.instance;
  SavedPrinter? _selected;
  List<BluetoothDevice> _devices = [];
  bool _loading = true;
  bool _connecting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    _selected = await PrinterStorage.readSelected();
    if (!Platform.isAndroid) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = 'Bluetooth printer setup is available on Android only.';
        });
      }
      return;
    }
    try {
      final isOn = await _bluetooth.isOn;
      if (isOn != true) {
        if (mounted) {
          setState(() {
            _loading = false;
            _error = 'Turn on Bluetooth to choose a paired printer.';
          });
        }
        return;
      }
      final devices = await _bluetooth.getBondedDevices();
      if (!mounted) return;
      setState(() {
        _devices = devices;
        _loading = false;
      });
    } on PlatformException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.message ?? 'Could not load paired Bluetooth devices.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  Future<void> _selectDevice(BluetoothDevice device) async {
    final address = device.address?.trim() ?? '';
    if (address.isEmpty) return;
    setState(() => _connecting = true);
    try {
      final printer = SavedPrinter(
        name: device.name?.trim() ?? '',
        address: address,
      );
      await PrinterStorage.saveSelected(printer);
      await _bluetooth.connect(device);
      if (!mounted) return;
      setState(() {
        _selected = printer;
        _connecting = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Printer set to ${printer.label}')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _connecting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not connect: $e')),
      );
    }
  }

  Future<void> _clearSelection() async {
    await PrinterStorage.clearSelected();
    try {
      await _bluetooth.disconnect();
    } catch (_) {}
    if (!mounted) return;
    setState(() => _selected = null);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Printer selection cleared')),
    );
  }

  Future<void> _testPrint() async {
    if (_selected == null) return;
    BluetoothDevice? device;
    for (final d in _devices) {
      if (d.address == _selected!.address) {
        device = d;
        break;
      }
    }
    if (device == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Selected printer is not in paired devices list.')),
      );
      return;
    }
    setState(() => _connecting = true);
    try {
      await _bluetooth.connect(device);
      await _bluetooth.printNewLine();
      await _bluetooth.printCustom('Nexus Erp', 1, 1);
      await _bluetooth.printCustom('Printer test OK', 0, 1);
      await _bluetooth.printNewLine();
      await _bluetooth.printNewLine();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Test print sent')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Test print failed: $e')),
      );
    } finally {
      if (mounted) setState(() => _connecting = false);
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
        title: const Text('Choose printer', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: _loading || _connecting ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(14, 8, 14, 24),
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFF4F1FF),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFE4E7F0)),
            ),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: _accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.print_outlined, color: _accent),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _selected?.label ?? 'No printer selected',
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        _selected == null
                            ? 'Pick a paired Bluetooth receipt printer below.'
                            : _selected!.address,
                        style: const TextStyle(fontSize: 12, color: Color(0xFF7C8191)),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_selected != null) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _connecting ? null : _testPrint,
                    icon: const Icon(Icons.receipt_long_outlined, size: 18),
                    label: const Text('Test print'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _connecting ? null : _clearSelection,
                    icon: const Icon(Icons.clear_rounded, size: 18),
                    label: const Text('Clear'),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 16),
          const Text(
            'Paired Bluetooth printers',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: Color(0xFF2D3355)),
          ),
          const SizedBox(height: 6),
          const Text(
            'Pair the printer in Android Bluetooth settings first, then refresh this list.',
            style: TextStyle(fontSize: 12, color: Color(0xFF7C8191), height: 1.35),
          ),
          const SizedBox(height: 12),
          if (_loading)
            const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator(color: _accent)))
          else if (_error != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE8EBF3)),
              ),
              child: Column(
                children: [
                  Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Color(0xFFC23D4B))),
                  const SizedBox(height: 12),
                  if (Platform.isAndroid)
                    OutlinedButton(onPressed: _load, child: const Text('Retry')),
                ],
              ),
            )
          else if (_devices.isEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE8EBF3)),
              ),
              child: const Text(
                'No paired printers found.\nOpen Android Settings → Bluetooth and pair your receipt printer.',
                style: TextStyle(color: Color(0xFF7C8191), height: 1.4),
              ),
            )
          else
            ..._devices.map((device) {
              final address = device.address ?? '';
              final name = device.name?.trim().isNotEmpty == true ? device.name!.trim() : address;
              final selected = _selected?.address == address;
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Material(
                  color: selected ? const Color(0xFFF4F1FF) : Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: _connecting ? null : () => _selectDevice(device),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: selected ? _accent : const Color(0xFFE8EBF3)),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            Icons.bluetooth_connected_rounded,
                            color: selected ? _accent : const Color(0xFF9CA3AF),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                                if (address.isNotEmpty)
                                  Text(address, style: const TextStyle(fontSize: 12, color: Color(0xFF7C8191))),
                              ],
                            ),
                          ),
                          if (selected)
                            const Icon(Icons.check_circle_rounded, color: _accent)
                          else if (_connecting)
                            const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: _accent),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            }),
        ],
      ),
    );
  }
}
