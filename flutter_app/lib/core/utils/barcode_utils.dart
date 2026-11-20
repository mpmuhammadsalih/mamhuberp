// Retail / warehouse barcode helpers (EAN-13, UPC-A, Code 128).

/// ERP Item Master internal barcode: prefix ``12`` + zero pad + item code (13 digits).
/// Example: item ``1000`` → ``1200000001000``.
const String kInternalItemBarcodePrefix = '12';
const int kInternalItemBarcodeDigits = 13;

/// Build 13-digit barcode ``12`` + zeros + [itemCode] (same as ERP Generate).
String? formatInternalItemBarcode(dynamic itemCode) {
  final raw = '$itemCode'.trim();
  if (raw.isEmpty) return null;
  final n = num.tryParse(raw);
  if (n == null || n <= 0) return null;
  final ic = n == n.roundToDouble() ? '${n.round()}' : raw.replaceAll(RegExp(r'\D'), '');
  if (ic.isEmpty || !RegExp(r'^\d+$').hasMatch(ic)) return null;
  const prefixLen = kInternalItemBarcodePrefix.length;
  const maxItemDigits = kInternalItemBarcodeDigits - prefixLen;
  if (ic.length > maxItemDigits) return null;
  final pad = kInternalItemBarcodeDigits - prefixLen - ic.length;
  return '$kInternalItemBarcodePrefix${'0' * pad}$ic';
}

class ScannedBarcodeCandidate {
  const ScannedBarcodeCandidate({required this.raw, this.format});

  final String raw;
  final String? format;
}

/// Normalize raw scanner output (Code 39 *…*, spaces, dashes).
String normalizeBarcode(String raw) {
  var t = raw.trim().toUpperCase();
  if (t.isEmpty) return t;
  if (t.startsWith('*') && t.endsWith('*') && t.length >= 2) {
    t = t.substring(1, t.length - 1).trim();
  }
  return t.replaceAll(RegExp(r'[\s\-]'), '');
}

int _formatPriority(String? format) {
  switch (format?.toLowerCase()) {
    case 'ean13':
      return 0;
    case 'upca':
      return 1;
    case 'ean8':
      return 2;
    case 'upce':
      return 3;
    case 'code128':
      return 4;
    case 'itf':
      return 5;
    case 'code93':
      return 6;
    case 'codabar':
    case 'codebar':
      return 7;
    case 'pdf417':
      return 8;
    case 'datamatrix':
      return 9;
    case 'aztec':
      return 10;
    case 'qrcode':
      return 30;
    case 'code39':
      return 50;
    default:
      return 20;
  }
}

bool isValidEan13(String digits) {
  if (digits.length != 13 || !RegExp(r'^\d+$').hasMatch(digits)) return false;
  var sum = 0;
  for (var i = 0; i < 12; i++) {
    final d = int.parse(digits[i]);
    sum += d * (i.isEven ? 1 : 3);
  }
  final check = (10 - (sum % 10)) % 10;
  return check == int.parse(digits[12]);
}

bool isValidUpcA(String digits) {
  if (digits.length != 12 || !RegExp(r'^\d+$').hasMatch(digits)) return false;
  return isValidEan13('0$digits');
}

bool isValidEan8(String digits) {
  if (digits.length != 8 || !RegExp(r'^\d+$').hasMatch(digits)) return false;
  var sum = 0;
  for (var i = 0; i < 7; i++) {
    final d = int.parse(digits[i]);
    sum += d * (i.isEven ? 3 : 1);
  }
  final check = (10 - (sum % 10)) % 10;
  return check == int.parse(digits[7]);
}

/// Best-effort canonical value from a single raw scan string.
String? canonicalizeRetailBarcode(String raw) {
  final norm = normalizeBarcode(raw);
  if (norm.isEmpty) return null;

  final digits = norm.replaceAll(RegExp(r'\D'), '');
  if (digits.length == 13 && isValidEan13(digits)) return digits;
  if (digits.length == 12 && isValidUpcA(digits)) return digits;
  if (digits.length == 8 && isValidEan8(digits)) return digits;

  // Numeric retail label without valid check digit — still use full digit string.
  if (digits.length >= 8 && digits.length <= 14) return digits;

  if (RegExp(r'^\d+$').hasMatch(norm)) return norm;
  if (norm.isNotEmpty) return norm;
  return null;
}

/// Pick the best decode when the camera reports multiple symbologies at once.
String? pickBestBarcodeCandidate(List<ScannedBarcodeCandidate> candidates) {
  if (candidates.isEmpty) return null;

  final sorted = [...candidates]..sort(
      (a, b) => _formatPriority(a.format).compareTo(_formatPriority(b.format)),
    );

  String? fallback;

  for (final c in sorted) {
    final canon = canonicalizeRetailBarcode(c.raw);
    if (canon == null || canon.isEmpty) continue;

    final digits = canon.replaceAll(RegExp(r'\D'), '');
    if (digits.length == 13 && isValidEan13(digits)) return digits;
    if (digits.length == 12 && isValidUpcA(digits)) return digits;
    if (digits.length == 8 && isValidEan8(digits)) return digits;

    if (_formatPriority(c.format) <= 4) {
      fallback ??= canon;
    }
  }

  if (fallback != null) return fallback;

  for (final c in sorted) {
    final canon = canonicalizeRetailBarcode(c.raw);
    if (canon != null && canon.isNotEmpty) return canon;
  }
  return null;
}

/// Search keys for API lookup — avoid shortened cores that match wrong items.
List<String> barcodeLookupVariants(String raw) {
  final out = <String>{};
  final trimmed = raw.trim();
  if (trimmed.isNotEmpty) out.add(trimmed);

  final canon = canonicalizeRetailBarcode(raw) ?? normalizeBarcode(raw);
  if (canon.isNotEmpty) out.add(canon);

  final digits = canon.replaceAll(RegExp(r'\D'), '');
  if (digits.isNotEmpty && digits != canon) out.add(digits);

  // EAN-13 ↔ UPC-A (leading zero) — some ERP rows store either form.
  if (digits.length == 13 && digits.startsWith('0')) {
    out.add(digits.substring(1));
  } else if (digits.length == 12) {
    out.add('0$digits');
  }

  return out.toList();
}

/// All lookup keys for a scan (raw + normalized variants).
List<String> barcodeLookupQueries(String raw) {
  final ordered = <String>[];
  final seen = <String>{};
  void add(String? value) {
    final v = (value ?? '').trim();
    if (v.isEmpty || !seen.add(v.toUpperCase())) return;
    ordered.add(v);
  }

  add(raw);
  for (final v in barcodeLookupVariants(raw)) {
    add(v);
  }
  final norm = normalizeBarcode(raw);
  if (norm != raw.trim()) {
    for (final v in barcodeLookupVariants(norm)) {
      add(v);
    }
  }
  return ordered;
}

bool barcodesMatch(String scanned, String stored) {
  final a = canonicalizeRetailBarcode(scanned) ?? normalizeBarcode(scanned);
  final b = canonicalizeRetailBarcode(stored) ?? normalizeBarcode(stored);
  if (a.isEmpty || b.isEmpty) return false;
  if (a == b) return true;

  final da = a.replaceAll(RegExp(r'\D'), '');
  final db = b.replaceAll(RegExp(r'\D'), '');
  if (da.isNotEmpty && da == db) return true;

  // EAN-13 vs UPC-A (leading 0).
  if (da.length == 13 && db.length == 12 && da.startsWith('0') && da.substring(1) == db) {
    return true;
  }
  if (db.length == 13 && da.length == 12 && db.startsWith('0') && db.substring(1) == da) {
    return true;
  }
  return false;
}

String? itemCodeDigitCore(String code) {
  var t = code.trim();
  if (t.contains('.')) {
    t = t.replaceAll(RegExp(r'\.0+$'), '');
  }
  if (!RegExp(r'^\d+$').hasMatch(t)) return null;
  final stripped = t.replaceFirst(RegExp(r'^0+'), '');
  return stripped.isEmpty ? '0' : stripped;
}

bool itemCodeMatchesScan(String itemCode, String scanned) {
  final code = itemCode.trim();
  final raw = scanned.trim();
  if (code == raw) return true;
  final canon = canonicalizeRetailBarcode(scanned) ?? normalizeBarcode(scanned);
  if (code == canon) return true;
  return false;
}

/// Strict match: exact item code or exact barcode only.
bool inventoryItemMatchesScan({
  required String itemCode,
  required String itemBarcode,
  required String scanned,
}) {
  if (itemCodeMatchesScan(itemCode, scanned)) return true;
  final bc = itemBarcode.trim();
  if (bc.isNotEmpty && barcodesMatch(scanned, bc)) return true;
  return false;
}

/// Phone camera: accept first read when check digit or symbology is trustworthy.
bool scanAcceptsImmediately(String value, {String? format}) {
  final digits = value.replaceAll(RegExp(r'\D'), '');
  if (digits.length == 13 && isValidEan13(digits)) return true;
  if (digits.length == 12 && isValidUpcA(digits)) return true;
  if (digits.length == 8 && isValidEan8(digits)) return true;
  final f = format?.toLowerCase();
  if (f == 'code128' || f == 'itf' || f == 'ean13' || f == 'upca' || f == 'ean8' || f == 'upce') {
    return digits.length >= 8;
  }
  return false;
}

/// True when input is likely from a barcode scanner (not a name search).
bool looksLikeBarcodeScan(String raw) {
  final trimmed = raw.trim();
  if (trimmed.length < 4) return false;
  if (trimmed.startsWith('*') && trimmed.endsWith('*') && trimmed.length >= 3) {
    return true;
  }
  final norm = normalizeBarcode(trimmed);
  if (norm.isEmpty) return false;
  if (RegExp(r'^\d{4,}$').hasMatch(norm)) return true;
  if (norm.length >= 6 && RegExp(r'^[A-Z0-9]+$').hasMatch(norm)) return true;
  return false;
}
