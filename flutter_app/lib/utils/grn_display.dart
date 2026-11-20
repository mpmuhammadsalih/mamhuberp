/// ERP returns `Progressing`; keep API enums while rendering friendlier chips.

String grnStatusChipLabel(String apiStatus) => switch (apiStatus) {
      'Progressing' => 'In progress',
      'Posted' => 'Posted',
      'Draft' => 'Draft',
      'Approved' => 'Approved',
      _ => apiStatus,
    };

String progressingCardSubtitle({
  required String apiStatus,
  required int linesTouched,
}) {
  if (apiStatus != 'Progressing') return '';
  if (linesTouched > 0) {
    final unit = linesTouched == 1 ? 'line' : 'lines';
    return 'Started receiving • $linesTouched $unit';
  }
  return 'Started receiving • continue wizard';
}

String formatPoBannerLabel(String storedReceiptNo) {
  final s = storedReceiptNo.trim();
  if (s.isEmpty) return '';
  final isNumeric = RegExp(r'^\d+$').hasMatch(s);
  return isNumeric ? 'Continue PO-$s' : 'Continue PO $s';
}
