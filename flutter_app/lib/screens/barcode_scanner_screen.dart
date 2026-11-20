import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';

import '../core/utils/barcode_utils.dart';
import '../services/inventory_service.dart';

/// Phone camera barcode scanner — ML Kit on Android, all symbologies enabled.
class BarcodeScannerScreen extends StatefulWidget {
  const BarcodeScannerScreen({
    super.key,
    this.returnOnScan = true,
    this.title = 'Scan barcode',
    this.locationcode,
  });

  final bool returnOnScan;
  final String title;
  final int? locationcode;

  @override
  State<BarcodeScannerScreen> createState() => _BarcodeScannerScreenState();
}

class _BarcodeScannerScreenState extends State<BarcodeScannerScreen> {
  static const _defaultStableReads = 2;

  late final MobileScannerController _controller;

  String _displayCode = '';
  String? _stableCode;
  String? _lastFormat;
  int _stableCount = 0;
  int _requiredStableReads = _defaultStableReads;
  bool _handled = false;
  bool _aiAvailable = false;
  bool _aiBusy = false;

  @override
  void initState() {
    super.initState();
    _controller = MobileScannerController(
      detectionSpeed: DetectionSpeed.normal,
      detectionTimeoutMs: 120,
      facing: CameraFacing.back,
      formats: const [],
      cameraResolution: const Size(1920, 1080),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadAiStatus());
  }

  Rect _scanWindowFor(Size area) {
    return Rect.fromCenter(
      center: area.center(Offset.zero),
      width: area.width * 0.88,
      height: 140,
    );
  }

  Future<void> _loadAiStatus() async {
    try {
      final ok = await context.read<InventoryService>().isLabelAiAvailable();
      if (mounted) setState(() => _aiAvailable = ok);
    } catch (_) {
      if (mounted) setState(() => _aiAvailable = false);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _acceptCode(String code) {
    if (_handled) return;
    _handled = true;
    Navigator.of(context).pop(code);
  }

  Future<void> _readLabelWithAi() async {
    if (_handled || _aiBusy) return;

    final picker = ImagePicker();
    final photo = await picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 90,
      preferredCameraDevice: CameraDevice.rear,
    );
    if (photo == null || !mounted) return;

    setState(() => _aiBusy = true);
    final inventory = context.read<InventoryService>();
    try {
      final bytes = await photo.readAsBytes();
      final ext = photo.path.split('.').last.toLowerCase();
      final mime = ext == 'png' ? 'image/png' : 'image/jpeg';
      final loc = widget.locationcode;
      final result = await inventory.labelScan(
        imageBase64: base64Encode(bytes),
        mime: mime,
        locationcode: loc != null && loc > 0 ? loc : null,
      );
      if (!mounted) return;

      final code = canonicalizeRetailBarcode(result.barcode) ??
          normalizeBarcode(result.barcode);
      if (code.isEmpty) {
        final tried = result.queriesTried;
        final msg = tried.isEmpty
            ? 'No barcode found on label. Try better lighting or enter manually.'
            : 'Read ${tried.join(", ")} but no matching item in ERP.';
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
        return;
      }

      if (!result.matched) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('AI read $code — searching item master…')),
        );
      }
      _acceptCode(code);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Label scan failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _aiBusy = false);
    }
  }

  String? _resolveScanValue(List<ScannedBarcodeCandidate> candidates) {
    if (candidates.isEmpty) return null;

    final best = pickBestBarcodeCandidate(candidates);
    if (best != null && best.isNotEmpty) return best;

    for (final c in candidates) {
      final raw = c.raw.trim();
      if (raw.isEmpty) continue;
      final norm = normalizeBarcode(raw);
      if (norm.isNotEmpty) return norm;
      return raw;
    }
    return null;
  }

  void _onDetect(BarcodeCapture capture) {
    if (_aiBusy || capture.barcodes.isEmpty) return;

    final candidates = capture.barcodes
        .map(
          (b) => ScannedBarcodeCandidate(
            raw: (b.rawValue ?? b.displayValue ?? '').trim(),
            format: b.format.name,
          ),
        )
        .where((c) => c.raw.isNotEmpty)
        .toList();
    if (candidates.isEmpty) return;

    final value = _resolveScanValue(candidates);
    if (value == null || value.isEmpty) return;

    final format = candidates.firstWhere(
      (c) {
        final norm = normalizeBarcode(c.raw);
        return norm == value || c.raw.trim() == value;
      },
      orElse: () => candidates.first,
    ).format;

    final requiredReads = scanAcceptsImmediately(value, format: format) ? 1 : _defaultStableReads;

    if (value == _stableCode) {
      _stableCount++;
    } else {
      _stableCode = value;
      _stableCount = 1;
      _lastFormat = format;
    }
    _requiredStableReads = requiredReads;

    final ready = _stableCount >= _requiredStableReads;
    setState(() {
      if (ready) {
        _displayCode = value;
      } else if (_requiredStableReads == 1) {
        _displayCode = value;
      } else {
        _displayCode = '$value  ($_stableCount/$_requiredStableReads)';
      }
    });

    if (widget.returnOnScan && ready) {
      _acceptCode(value);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ready = _stableCode != null && _stableCount >= _requiredStableReads;
    final controlsLocked = _aiBusy;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: Text(widget.title),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            tooltip: 'Torch',
            onPressed: controlsLocked ? null : () => _controller.toggleTorch(),
            icon: ValueListenableBuilder(
              valueListenable: _controller,
              builder: (context, state, child) {
                switch (state.torchState) {
                  case TorchState.on:
                    return const Icon(Icons.flash_on_rounded);
                  default:
                    return const Icon(Icons.flash_off_rounded);
                }
              },
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final scanWindow = _scanWindowFor(constraints.biggest);
                return Stack(
                  fit: StackFit.expand,
                  children: [
                    MobileScanner(
                      controller: _controller,
                      fit: BoxFit.cover,
                      scanWindow: scanWindow,
                      onDetect: _onDetect,
                    ),
                    if (controlsLocked)
                      const ColoredBox(
                        color: Color(0x99000000),
                        child: Center(child: CircularProgressIndicator(color: Colors.white)),
                      ),
                    Center(
                      child: Container(
                        width: scanWindow.width,
                        height: scanWindow.height,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.greenAccent, width: 2),
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
          Container(
            width: double.infinity,
            color: Colors.black87,
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            child: Column(
              children: [
                Text(
                  'Point phone camera at barcode. EAN / UPC reads instantly; use torch in dim light.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.55), fontSize: 11),
                ),
                if (_aiAvailable) ...[
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: controlsLocked ? null : _readLabelWithAi,
                    icon: _aiBusy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                          )
                        : const Icon(Icons.document_scanner_outlined, size: 20),
                    label: Text(_aiBusy ? 'Reading label…' : 'Read label (AI)'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: BorderSide(color: Colors.white.withValues(alpha: 0.45)),
                    ),
                  ),
                  Text(
                    'Wrinkled or glossy label? Take a photo instead.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 11),
                  ),
                ],
                const SizedBox(height: 10),
                Text(
                  _displayCode.isEmpty
                      ? 'Fill the green frame with the barcode.\nHold steady for one second.'
                      : _displayCode,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: ready ? Colors.greenAccent : Colors.white,
                    fontSize: ready ? 18 : 15,
                    fontWeight: ready ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
                if (_lastFormat != null && _displayCode.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text(
                    _lastFormat!.toUpperCase(),
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 11),
                  ),
                ],
                if (_stableCode != null && widget.returnOnScan) ...[
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: controlsLocked ? null : () => _acceptCode(_stableCode!),
                    child: Text(ready ? 'Use $_stableCode' : 'Use now'),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
