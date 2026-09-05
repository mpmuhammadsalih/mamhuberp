/**
 * QZ Tray helpers for sales invoice: prints GRN-style PDF (ReportLab) via QZ `{ type: 'pdf', format: 'base64' }`.
 * Loads qz-tray.js lazily (inject script) so the Sales Invoice page never blocks on CDN/QZ Tray.
 * Optional: window.__SALES_QZ_SCRIPT_URL__ overrides script URL (default: jsDelivr).
 */
(function (global) {
  const DEFAULT_QZ_SCRIPT = 'https://cdn.jsdelivr.net/npm/qz-tray/qz-tray.js';
  const QZ_SCRIPT_TIMEOUT_MS = 20000;

  let securityConfigured = false;
  let qzScriptInflight = null;

  /**
   * Inject qz-tray.js once; WebSocket connection only happens in ensureQzSecurity.
   */
  function injectQzTrayScriptOnce() {
    const src = String(global.__SALES_QZ_SCRIPT_URL__ || DEFAULT_QZ_SCRIPT).trim() || DEFAULT_QZ_SCRIPT;

    return new Promise((resolve, reject) => {
      if (global.qz && global.qz.websocket) {
        resolve();
        return;
      }

      let el = document.querySelector('script[data-sales-qz-tray="1"]');
      if (!el) {
        el = document.createElement('script');
        el.async = true;
        el.dataset.salesQzTray = '1';
        el.src = src;
        (document.head || document.documentElement).appendChild(el);
        if (global.qz && global.qz.websocket) {
          resolve();
          return;
        }
      }

      const timer = setTimeout(() => {
        reject(new Error(`QZ Tray script timed out (${QZ_SCRIPT_TIMEOUT_MS / 1000}s). Check CDN/firewall or host qz-tray.js locally.`));
      }, QZ_SCRIPT_TIMEOUT_MS);

      const ok = () => {
        clearTimeout(timer);
        if (global.qz && global.qz.websocket) resolve();
        else reject(new Error('QZ script ran but window.qz is not available.'));
      };

      const bad = () => {
        clearTimeout(timer);
        reject(new Error(`Could not load QZ Tray script (${src}).`));
      };

      el.addEventListener('load', ok, { once: true });
      el.addEventListener('error', bad, { once: true });

      if (global.qz && global.qz.websocket) {
        clearTimeout(timer);
        resolve();
      }
    });
  }

  async function loadQzTrayLibrary() {
    if (global.qz && global.qz.websocket) {
      return;
    }
    if (!qzScriptInflight) {
      qzScriptInflight = injectQzTrayScriptOnce().catch((err) => {
        qzScriptInflight = null;
        throw err;
      });
    }
    await qzScriptInflight;
  }

  function formatQzConnectError(err) {
    const raw = String((err && (err.message || err)) || err || 'Unknown error');
    if (/establish connection|connection refused|ECONNREFUSED|WebSocket|websocket|closed before/i.test(raw)) {
      return (
        'Cannot connect to QZ Tray on this PC.\n\n' +
        'Checklist:\n' +
        '• QZ Tray is installed (https://qz.io/download/) and running (system tray icon visible)\n' +
        '• You use Chrome or Edge on the same PC where QZ Tray runs (not a remote desktop session on another machine)\n' +
        '• From Reports → Printer Setup: download the QZ certificate and trust/allow it in QZ Tray\n' +
        '• Windows firewall/antivirus is not blocking localhost ports 8181/8182\n\n' +
        'Technical detail: ' + raw
      );
    }
    if (/Certificate HTTP|Signature failed|Sign HTTP|certificate/i.test(raw)) {
      return (
        'QZ security setup failed (certificate or signing).\n\n' +
        '• Stay logged in to Nova in this browser tab\n' +
        '• Open Reports → Printer Setup and download/trust the QZ certificate\n' +
        '• On cloud hosting: ensure the server keeps the same QZ cert files across restarts\n\n' +
        'Technical detail: ' + raw
      );
    }
    return raw;
  }

  /**
   * Open WebSocket to local QZ Tray (localhost — works with cloud-hosted Nova too).
   */
  async function connectQzWebsocket() {
    if (!global.qz || !global.qz.websocket) {
      throw new Error('QZ Tray library not loaded.');
    }
    if (global.qz.websocket.isActive()) {
      return;
    }
    const connectOpts = { retries: 3, delay: 1 };
    try {
      await global.qz.websocket.connect(connectOpts);
    } catch (err) {
      throw new Error(formatQzConnectError(err));
    }
  }

  /**
   * @param {{ certificate: string, sign: string }} urls
   */
  async function ensureQzSecurity(urls) {
    await loadQzTrayLibrary();
    if (!urls || !urls.certificate || !urls.sign) {
      throw new Error('QZ URLs missing on page.');
    }
    if (!global.qz || !qz.security) {
      throw new Error('QZ Tray library not loaded.');
    }
    if (!securityConfigured) {
      qz.security.setCertificatePromise((resolve, reject) => {
        fetch(urls.certificate, { credentials: 'same-origin' })
          .then((res) => {
            if (!res.ok) throw new Error(`Certificate HTTP ${res.status}`);
            return res.text();
          })
          .then((txt) => resolve(txt))
          .catch((err) => reject(err));
      });
      qz.security.setSignatureAlgorithm('SHA512');
      qz.security.setSignaturePromise(
        (toSign) => (resolve, reject) => {
          fetch(urls.sign, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ request: toSign }),
          })
            .then(async (res) => {
              const data = await res.json().catch(() => ({}));
              if (!res.ok || !data.success || !data.signature) {
                throw new Error((data && (data.error || data.message)) || `Sign HTTP ${res.status}`);
              }
              resolve(data.signature);
            })
            .catch((err) => reject(err));
        }
      );
      securityConfigured = true;
    }
    await connectQzWebsocket();
  }

  /**
   * Fetch GRN-style invoice PDF (base64) and send to QZ (saved invoice printer, else QZ default).
   * @param {string|number} billno
   * @param {{ certificate: string, sign: string, pdfQz?: string }} urls — pdfQz = full URL for JSON with pdf_base64 (GET ?billno=)
   */
  async function printCashBillToDefaultPrinter(billno, urls) {
    const bn = String(billno || '').trim();
    if (!bn) throw new Error('Missing bill number');
    await ensureQzSecurity(urls);

    let pdfUrl = String((urls && urls.pdfQz) || '').trim();
    if (!pdfUrl) {
      throw new Error('pdfQz URL missing on page (reports cashbilldup qz-pdf).');
    }
    try {
      const u = new URL(pdfUrl, window.location.origin);
      if (!u.searchParams.get('billno')) u.searchParams.set('billno', bn);
      pdfUrl = u.pathname + u.search;
    } catch (_e) {
      const sep = pdfUrl.indexOf('?') >= 0 ? '&' : '?';
      pdfUrl = `${pdfUrl}${sep}billno=${encodeURIComponent(bn)}`;
    }

    const res = await fetch(pdfUrl, { credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.success || !data.pdf_base64) {
      throw new Error((data && data.error) || `QZ PDF payload HTTP ${res.status}`);
    }

    let printerName = '';
    try {
      if (global.QzPrinterPrefs && typeof global.QzPrinterPrefs.get === 'function') {
        printerName = String(global.QzPrinterPrefs.get('sales_invoice') || '').trim();
      }
    } catch (e) {
      printerName = '';
    }
    if (!printerName) {
      try {
        printerName = String((await qz.printers.getDefault()) || '').trim();
      } catch (e2) {
        printerName = '';
      }
    }
    if (!printerName) {
      throw new Error(
        'No invoice printer saved and no QZ default printer. Open Sales → Printer Setup, choose Sales invoice printer, and Save.'
      );
    }
    const config = qz.configs.create(printerName);
    const b64 = String(data.pdf_base64 || '').replace(/\s/g, '');
    const payload = [{ type: 'pdf', format: 'base64', data: b64 }];
    await qz.print(config, payload);
    return true;
  }

  function posReceiptBranchLogoUrl(receipt) {
    if (!receipt) return '';
    const loc = receipt.location_details || {};
    let rel = String(loc.logo_url || loc.logo_path || '').trim();
    if (!rel) return '';
    if (/^https?:\/\//i.test(rel)) return rel;
    const path = rel.startsWith('/') ? rel : '/static/' + rel.replace(/^\/+/, '');
    return global.location.origin + path;
  }

  function posReceiptHasArabicText(text) {
    return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/.test(String(text || ''));
  }

  function posReceiptEscapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function posReceiptEscapeHtmlWithArabicFont(text) {
    let out = '';
    let inArabic = false;
    String(text || '').split('').forEach((ch) => {
      const isArabic = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/.test(ch);
      if (isArabic && !inArabic) {
        out += '<span class="ar">';
        inArabic = true;
      } else if (!isArabic && inArabic) {
        out += '</span>';
        inArabic = false;
      }
      out += posReceiptEscapeHtml(ch);
    });
    if (inArabic) out += '</span>';
    return out;
  }

  function buildPosReceiptHtml(text, logoUrl) {
    const logoBlock = logoUrl
      ? '<div class="logo-wrap"><img class="logo" src="' + posReceiptEscapeHtml(logoUrl) + '" alt=""></div>'
      : '';
    return '<!doctype html><html><head><meta charset="utf-8">'
      + '<style>@page{margin:0;}body{margin:0;padding:0;background:#fff;color:#000;display:flex;justify-content:center;}'
      + '.wrap{box-sizing:border-box;width:72mm;margin:0 auto;padding:2mm;}'
      + '.logo-wrap{text-align:center;margin:0 auto 2mm;}'
      + '.logo{max-width:60mm;max-height:20mm;height:auto;display:block;margin:0 auto;}'
      + 'pre{margin:0;font:11px Consolas,"Courier New",monospace;white-space:pre;unicode-bidi:plaintext;}'
      + '.ar{font-family:Tahoma,Arial,sans-serif;}</style>'
      + '</head><body><div class="wrap">' + logoBlock
      + '<pre>' + posReceiptEscapeHtmlWithArabicFont(text) + '</pre></div></body></html>';
  }

  /**
   * Print POS receipt text via QZ Tray (same printer as POS checkout: Printer Setup → POS receipt).
   * @param {string} text — plain receipt text (may include COPY banner)
   * @param {object|null} receiptData — receipt JSON for logo / return copy count
   * @param {{ certificate: string, sign: string }} urls
   */
  async function printPosReceiptViaQz(text, receiptData, urls) {
    const receiptText = String(text || '').trimEnd();
    if (!receiptText) throw new Error('No receipt to print.');
    await ensureQzSecurity(urls || {});

    let printerName = '';
    try {
      if (global.QzPrinterPrefs && typeof global.QzPrinterPrefs.get === 'function') {
        printerName = String(global.QzPrinterPrefs.get('pos_receipt') || '').trim();
      }
    } catch (e) {
      printerName = '';
    }
    if (!printerName) {
      throw new Error(
        'No POS receipt printer selected. Open Sales → Printer Setup, choose POS receipt printer, and Save.'
      );
    }

    const config = qz.configs.create(printerName);
    const escInit = '\x1B@';
    const smallFont = '\x1BM\x01\x1B!\x01';
    const leftMargin = '\x1DL\x30\x00';
    const cut = '\x1DV\x01';
    const logoUrl = posReceiptBranchLogoUrl(receiptData);
    const netForCopy = Number(receiptData && receiptData.footer && receiptData.footer.net_total);
    const copies = Number.isFinite(netForCopy) && netForCopy <= 0 ? 2 : 1;

    const printHtmlBatch = async (html) => {
      for (let c = 0; c < copies; c++) {
        await qz.print(config, [{ type: 'pixel', format: 'html', flavor: 'plain', data: html }]);
      }
    };
    const printRawBatch = async (rawData) => {
      for (let c = 0; c < copies; c++) {
        await qz.print(config, [{ type: 'raw', format: 'plain', data: rawData }]);
      }
    };

    if (logoUrl || posReceiptHasArabicText(receiptText)) {
      const html = buildPosReceiptHtml(receiptText, logoUrl);
      await printHtmlBatch(html);
      return copies;
    }
    const raw = escInit + leftMargin + smallFont + receiptText + '\n\n\n' + cut;
    try {
      await printRawBatch(raw);
    } catch (rawErr) {
      const html = buildPosReceiptHtml(receiptText, logoUrl);
      await printHtmlBatch(html);
    }
    return copies;
  }

  global.SalesQzPrint = {
    loadQzTrayLibrary,
    connectQzWebsocket,
    ensureQzSecurity,
    printCashBillToDefaultPrinter,
    printPosReceiptViaQz,
  };
})(typeof window !== 'undefined' ? window : globalThis);
