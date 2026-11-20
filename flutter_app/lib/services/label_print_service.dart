import 'dart:io';

import 'package:blue_thermal_printer/blue_thermal_printer.dart';

import '../core/storage/printer_storage.dart';
import '../models/inventory_item.dart';
import '../models/storage_location.dart';

/// Bluetooth thermal label printing for product / shelf barcodes.
class LabelPrintService {
  LabelPrintService();

  final BlueThermalPrinter _bluetooth = BlueThermalPrinter.instance;

  Future<SavedPrinter> requirePrinter() async {
    if (!Platform.isAndroid) {
      throw Exception('Bluetooth label printing is available on Android only.');
    }
    final selected = await PrinterStorage.readSelected();
    if (selected == null || selected.isEmpty) {
      throw Exception('No printer selected. Open Settings → Choose printer.');
    }
    final on = await _bluetooth.isOn;
    if (on != true) {
      throw Exception('Turn on Bluetooth to print.');
    }
    return selected;
  }

  Future<void> _connect(SavedPrinter printer) async {
    final devices = await _bluetooth.getBondedDevices();
    BluetoothDevice? device;
    for (final d in devices) {
      if ((d.address ?? '').trim() == printer.address.trim()) {
        device = d;
        break;
      }
    }
    if (device == null) {
      throw Exception(
        'Printer "${printer.label}" is not in paired devices. Pair it in Bluetooth settings.',
      );
    }
    final connected = await _bluetooth.isConnected;
    if (connected != true) {
      await _bluetooth.connect(device);
    }
  }

  Future<void> printProductLabel(InventoryItem item, {int copies = 1}) async {
    final printer = await requirePrinter();
    await _connect(printer);
    final n = copies.clamp(1, 20);
    final code = item.barcode.trim().isNotEmpty ? item.barcode.trim() : item.itemCode.trim();
    final name = item.itemName.trim();
    final price = item.retailPrice;
    final priceText = price > 0
        ? (price == price.roundToDouble()
            ? price.round().toString()
            : price.toStringAsFixed(2))
        : '';

    for (var i = 0; i < n; i++) {
      await _bluetooth.printNewLine();
      await _bluetooth.printCustom('PRODUCT', 0, 1);
      if (name.isNotEmpty) {
        await _bluetooth.printCustom(_clip(name, 28), 1, 1);
      }
      await _bluetooth.printCustom('Code: ${item.itemCode}', 0, 1);
      if (item.unit.trim().isNotEmpty) {
        await _bluetooth.printCustom('UOM: ${item.unit}', 0, 1);
      }
      if (priceText.isNotEmpty) {
        await _bluetooth.printCustom('Price: $priceText', 0, 1);
      }
      if (code.isNotEmpty) {
        await _bluetooth.printQRcode(code, 180, 180, 1);
        await _bluetooth.printCustom(code, 1, 1);
      }
      await _bluetooth.printNewLine();
      await _bluetooth.printNewLine();
    }
  }

  Future<void> printShelfLabel(StorageLocation storage, {int copies = 1}) async {
    final printer = await requirePrinter();
    await _connect(printer);
    final n = copies.clamp(1, 20);
    final code = storage.printValue;
    final title = storage.name.trim().isNotEmpty ? storage.name.trim() : storage.code;

    for (var i = 0; i < n; i++) {
      await _bluetooth.printNewLine();
      await _bluetooth.printCustom('SHELF / BIN', 0, 1);
      await _bluetooth.printCustom(_clip(title, 28), 1, 1);
      await _bluetooth.printCustom(storage.typeLabel, 0, 1);
      if (storage.path.trim().isNotEmpty) {
        await _bluetooth.printCustom(_clip(storage.path, 32), 0, 1);
      }
      if (storage.code.trim().isNotEmpty && storage.code.trim() != code) {
        await _bluetooth.printCustom('Code: ${storage.code}', 0, 1);
      }
      if (code.isNotEmpty) {
        await _bluetooth.printQRcode(code, 180, 180, 1);
        await _bluetooth.printCustom(code, 1, 1);
      }
      await _bluetooth.printNewLine();
      await _bluetooth.printNewLine();
    }
  }

  static String _clip(String s, int max) {
    final t = s.trim();
    if (t.length <= max) return t;
    return '${t.substring(0, max - 1)}…';
  }
}
