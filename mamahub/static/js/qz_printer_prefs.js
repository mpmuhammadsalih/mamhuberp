/**
 * Per-browser QZ Tray printer names for different flows (saved from Printer Setup).
 * Not server-side — each workstation/browser profile has its own values.
 */
(function (global) {
  var KEYS = {
    sales_invoice: 'qz_printer_sales_invoice',
    pos_receipt: 'qz_printer_pos_receipt',
    barcode_label: 'qz_printer_barcode_label',
  };

  /** When true, POS checkout opens receipt preview then user taps Print. When false (default), QZ prints immediately. */
  var STORAGE_POS_PREVIEW = 'qz_pos_receipt_print_preview_enabled';

  function getPosReceiptPreviewEnabled() {
    try {
      var v = global.localStorage.getItem(STORAGE_POS_PREVIEW);
      if (v === null || v === '') return false;
      return v === '1' || v === 'true';
    } catch (e) {
      return false;
    }
  }

  function setPosReceiptPreviewEnabled(on) {
    try {
      global.localStorage.setItem(STORAGE_POS_PREVIEW, on ? '1' : '0');
      return true;
    } catch (e) {
      return false;
    }
  }

  function get(role) {
    var k = KEYS[role];
    if (!k) return '';
    try {
      return String(global.localStorage.getItem(k) || '').trim();
    } catch (e) {
      return '';
    }
  }

  function set(role, name) {
    var k = KEYS[role];
    if (!k) return false;
    try {
      global.localStorage.setItem(k, String(name || '').trim());
      return true;
    } catch (e) {
      return false;
    }
  }

  global.QzPrinterPrefs = {
    KEYS: KEYS,
    roles: function () {
      return Object.keys(KEYS);
    },
    get: get,
    set: set,
    getPosReceiptPreviewEnabled: getPosReceiptPreviewEnabled,
    setPosReceiptPreviewEnabled: setPosReceiptPreviewEnabled,
  };
})(typeof window !== 'undefined' ? window : globalThis);
