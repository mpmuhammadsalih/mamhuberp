/**
 * QZ Tray — 48×30 mm barcode labels (Barcode management).
 * Builds HTML from #bcPrintArea contents and prints via pixel/html.
 */
(function (global) {
  var LABEL_CSS =
    '@page{margin:0;size:48mm 30mm;}' +
    'html,body{margin:0;padding:0;background:#fff;color:#000;}' +
    /* Block layout — flex-wrap caused multi-label jobs to shrink or sit side-by-side. */
    'body{display:block;width:48mm;}' +
    '.bc-print-page{box-sizing:border-box;width:48mm;height:30mm;min-height:30mm;max-height:30mm;' +
    'margin:0;padding:0;overflow:hidden;page-break-inside:avoid;break-inside:avoid;' +
    'page-break-after:always;break-after:page;}' +
    '.bc-print-page:last-child{page-break-after:auto;break-after:auto;}' +
    '.bc-print-label{box-sizing:border-box;width:48mm;height:30mm;min-height:30mm;max-height:30mm;' +
    'padding:1mm 2mm;margin:0;border:none;outline:none;text-align:center;page-break-inside:avoid;' +
    'overflow:hidden;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;}' +
    '.bc-print-names{width:100%;max-height:11mm;overflow:hidden;flex:0 0 auto;margin:0 0 0.4mm;}' +
    '.bc-print-loc{font-size:5.5pt;font-weight:600;color:#000;margin:0 0 0.15mm;line-height:1.1;' +
    'max-height:3mm;overflow:hidden;width:100%;text-align:center;word-break:break-word;}' +
    '.bc-print-cap{font-size:6.5pt;font-weight:700;color:#000;margin:0;line-height:1.05;' +
    'max-height:3.8mm;overflow:hidden;width:100%;text-align:center;word-break:break-word;}' +
    '.bc-print-cap-ar{font-size:6pt;font-weight:600;color:#000;margin:0.2mm 0 0;line-height:1.1;' +
    'max-height:4mm;overflow:hidden;width:100%;text-align:center;direction:rtl;unicode-bidi:embed;' +
    'word-break:break-word;font-family:Tahoma,\"Segoe UI\",Arial,sans-serif;}' +
    '.bc-print-meta{font-size:5.5pt;color:#000;margin:0 0 0.4mm;line-height:1.1;text-align:center;' +
    'max-height:3.5mm;overflow:hidden;width:100%;}' +
    '.bc-print-info-row{display:flex;flex-direction:row;align-items:center;justify-content:center;' +
    'width:100%;gap:2mm;margin:0.3mm 0 0;flex:0 0 auto;max-height:11mm;overflow:hidden;text-align:center;}' +
    '.bc-print-info-right{text-align:center;flex:0 0 auto;line-height:1.12;}' +
    '.bc-print-uom{font-size:5.5pt;font-weight:600;color:#000;}' +
    '.bc-print-prices{display:flex;flex-direction:row;align-items:center;justify-content:center;' +
    'flex:0 0 auto;text-align:center;margin:0;line-height:1.05;max-height:10mm;overflow:hidden;gap:1mm;}' +
    '.bc-print-price-text{display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.05;}' +
    '.bc-print-ean{width:100%;text-align:center;font-size:6pt;font-weight:600;color:#000;' +
    'letter-spacing:0.04em;margin-top:0.25mm;max-height:3mm;overflow:hidden;flex:0 0 auto;}' +
    '.bc-print-price{font-size:11pt;font-weight:800;color:#000;letter-spacing:0.02em;}' +
    '.bc-print-price-ar{font-size:9pt;font-weight:700;color:#000;direction:rtl;unicode-bidi:embed;' +
    'font-family:Tahoma,\"Segoe UI\",Arial,sans-serif;margin-top:0.2mm;}' +
    '.bc-print-bar-wrap{flex:0 0 auto;width:100%;max-width:44mm;display:flex;justify-content:center;' +
    'align-items:center;margin:0 auto;line-height:0;}' +
    '.bc-print-bar-wrap svg{max-width:100%!important;width:auto!important;height:auto!important;' +
    'display:block;margin:0 auto!important;}' +
    '.bc-print-sub{font-size:6pt;color:#000;margin:0.5mm 0 0;line-height:1.1;width:100%;' +
    'text-align:center;max-height:4mm;overflow:hidden;}';

  function buildLabelDocument(innerHtml) {
    return (
      '<!doctype html><html><head><meta charset="utf-8"><style>' +
      LABEL_CSS +
      '</style></head><body>' +
      String(innerHtml || '') +
      '</body></html>'
    );
  }

  /** QZ scales HTML to page by default — disable so each 48×30 mm label stays full size. */
  function createLabelPrintConfig(printerName) {
    return global.qz.configs.create(printerName, {
      scaleContent: false,
      size: { width: 48, height: 30 },
      units: 'mm',
    });
  }

  function wrapLabelPage(labelHtml) {
    return '<div class="bc-print-page">' + String(labelHtml || '') + '</div>';
  }

  function getBarcodePrinterName() {
    try {
      if (global.QzPrinterPrefs && typeof global.QzPrinterPrefs.get === 'function') {
        return String(global.QzPrinterPrefs.get('barcode_label') || '').trim();
      }
    } catch (e) {
      return '';
    }
    return '';
  }

  async function ensureQz() {
    if (!global.SalesQzPrint || typeof global.SalesQzPrint.ensureQzSecurity !== 'function') {
      throw new Error('QZ helper script not loaded.');
    }
    var urls = global.__BC_QZ_URLS__ || global.__POS_QZ_URLS__ || global.__SALES_QZ_URLS__ || {};
    await global.SalesQzPrint.ensureQzSecurity(urls);
    if (!global.qz) {
      throw new Error('QZ Tray library not loaded.');
    }
  }

  /** Delay between separate QZ jobs (ms) so label printers advance one sticker each. */
  var BETWEEN_LABEL_MS = 250;

  /** Prevents two print runs (e.g. Print all + a row Print) from interleaving jobs. */
  var _printing = false;

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  /**
   * Print every .bc-print-label child IN ORDER.
   *
   * Labels are sent as ONE QZ job (one page per label, page-break between them)
   * so the spooler cannot reorder or interleave them — each barcode finishes
   * before the next one prints, and a second print run waits for this one.
   *
   * @param {HTMLElement} areaEl
   * @param {{ betweenMs?: number, perLabelJob?: boolean }} [opts]
   */
  async function printLabelsFromArea(areaEl, opts) {
    if (!areaEl || !areaEl.children || !areaEl.children.length) {
      throw new Error('No labels to print.');
    }
    var printerName = getBarcodePrinterName();
    if (!printerName) {
      throw new Error(
        'No barcode label printer selected. On Barcode management (or Sales → Printer configuration), pick the barcode printer and Save.'
      );
    }
    if (_printing) {
      throw new Error('A barcode print job is still running. Please wait for it to finish before printing again.');
    }
    _printing = true;
    try {
      await ensureQz();
      var config = createLabelPrintConfig(printerName);
      var labels = [];
      for (var i = 0; i < areaEl.children.length; i++) {
        labels.push(areaEl.children[i]);
      }

      // Default: single ordered job (one page per label). Most reliable for order.
      if (!opts || !opts.perLabelJob) {
        var parts = [];
        for (var k = 0; k < labels.length; k++) {
          var el = labels[k].cloneNode(true);
          parts.push(wrapLabelPage(el.outerHTML));
        }
        var combinedHtml = buildLabelDocument(parts.join(''));
        await global.qz.print(config, [{
          type: 'pixel',
          format: 'html',
          flavor: 'plain',
          data: combinedHtml,
          options: { pageWidth: 48, pageHeight: 30 },
        }]);
        return labels.length;
      }

      // Fallback: one job per label, strictly sequential (await each before the next).
      var gap = opts && opts.betweenMs != null ? opts.betweenMs : BETWEEN_LABEL_MS;
      for (var j = 0; j < labels.length; j++) {
        var html = buildLabelDocument(wrapLabelPage(labels[j].outerHTML));
        await global.qz.print(config, [{
          type: 'pixel',
          format: 'html',
          flavor: 'plain',
          data: html,
          options: { pageWidth: 48, pageHeight: 30 },
        }]);
        if (j < labels.length - 1 && gap > 0) {
          await sleep(gap);
        }
      }
      return labels.length;
    } finally {
      _printing = false;
    }
  }

  /** Test print — single sample label (Printer Setup). */
  async function printTestLabel() {
    var printerName = getBarcodePrinterName();
    if (!printerName) {
      throw new Error(
        'No barcode label printer selected. Pick a printer, Save, then run Test print.'
      );
    }
    await ensureQz();
    var sample =
      '<div class="bc-print-label">' +
      '<div class="bc-print-cap">QZ barcode test</div>' +
      '<div class="bc-print-meta">Printer configuration · Nexa</div>' +
      '<div class="bc-print-sub">CODE128 TEST-LABEL</div>' +
      '</div>';
    var html = buildLabelDocument(wrapLabelPage(sample));
    var config = createLabelPrintConfig(printerName);
    await global.qz.print(config, [{
      type: 'pixel',
      format: 'html',
      flavor: 'plain',
      data: html,
      options: { pageWidth: 48, pageHeight: 30 },
    }]);
    return true;
  }

  global.BcQzPrint = {
    buildLabelDocument: buildLabelDocument,
    getBarcodePrinterName: getBarcodePrinterName,
    printLabelsFromArea: printLabelsFromArea,
    printTestLabel: printTestLabel,
  };
})(typeof window !== 'undefined' ? window : globalThis);
