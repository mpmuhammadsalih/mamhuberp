/**
 * QZ Tray printer list modal + save to QzPrinterPrefs (Printer configuration pages).
 * Requires: qz-tray (or SalesQzPrint.loadQzTrayLibrary), SalesQzPrint.ensureQzSecurity, QzPrinterPrefs.
 */
(function (global) {
  function flashBadge(el) {
    if (!el) return;
    el.classList.add('visible');
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.classList.remove('visible');
    }, 2000);
  }

  /**
   * @param {{
   *   urls: { certificate: string, sign: string },
   *   inputEl: HTMLInputElement|null,
   *   modalEl: HTMLElement|null,
   *   modalOverlayEl: HTMLElement|null,
   *   modalCloseEl: HTMLElement|null,
   *   modalTitleEl: HTMLElement|null,
   *   searchEl: HTMLInputElement|null,
   *   listBodyEl: HTMLElement|null,
   *   saveBadgeEl?: HTMLElement|null,
   *   prefRole: string,
   *   popupTitle?: string
   * }} cfg
   */
  function initQzPrinterPicker(cfg) {
    var urls = cfg.urls || {};
    var inputEl = cfg.inputEl || null;
    var modalEl = cfg.modalEl || null;
    var modalOverlayEl = cfg.modalOverlayEl || null;
    var modalCloseEl = cfg.modalCloseEl || null;
    var modalTitleEl = cfg.modalTitleEl || null;
    var searchEl = cfg.searchEl || null;
    var listBodyEl = cfg.listBodyEl || null;
    var saveBadgeEl = cfg.saveBadgeEl || null;
    var prefRole = String(cfg.prefRole || '').trim();
    var popupTitle = cfg.popupTitle || 'Select printer';

    var printerRows = [];
    var qzSecurityConfigured = false;

    function applySaved() {
      if (!prefRole || !global.QzPrinterPrefs || !inputEl) return;
      var name = String(global.QzPrinterPrefs.get(prefRole) || '').trim();
      if (name) inputEl.value = name;
    }
    applySaved();

    function closeModal() {
      if (modalEl) modalEl.classList.add('hidden');
      if (searchEl) searchEl.value = '';
    }

    function renderRows(query) {
      if (!listBodyEl) return;
      var q = String(query || '')
        .trim()
        .toLowerCase();
      var filtered = printerRows.filter(function (p) {
        return !q || String(p).toLowerCase().indexOf(q) >= 0;
      });
      if (!filtered.length) {
        listBodyEl.innerHTML = '<tr><td>No printers found.</td></tr>';
        return;
      }
      listBodyEl.innerHTML = filtered
        .map(function (p) {
          var s = String(p);
          return (
            '<tr class="qz-printer-row" data-printer="' +
            s.replace(/"/g, '&quot;').replace(/&/g, '&amp;') +
            '"><td>' +
            s.replace(/</g, '&lt;').replace(/&/g, '&amp;') +
            '</td></tr>'
          );
        })
        .join('');
      listBodyEl.querySelectorAll('.qz-printer-row').forEach(function (row) {
        row.addEventListener('click', function () {
          var printer = String(row.getAttribute('data-printer') || '').trim();
          if (printer && inputEl) inputEl.value = printer;
          closeModal();
        });
      });
    }

    function openModal() {
      if (modalTitleEl) modalTitleEl.textContent = popupTitle;
      renderRows('');
      if (modalEl) modalEl.classList.remove('hidden');
      if (searchEl) {
        searchEl.value = '';
        setTimeout(function () {
          searchEl.focus();
        }, 0);
      }
    }

    async function ensureQzConnected() {
      if (global.SalesQzPrint && typeof global.SalesQzPrint.ensureQzSecurity === 'function') {
        await global.SalesQzPrint.ensureQzSecurity(urls);
        if (!global.qz) throw new Error('QZ Tray library not loaded.');
        return;
      }
      if (!global.qz) {
        throw new Error('QZ Tray library not loaded. Check network/CDN or install QZ Tray.');
      }
      if (!global.qz.security) {
        throw new Error('QZ security API unavailable.');
      }
      if (!qzSecurityConfigured) {
        global.qz.security.setCertificatePromise(function (resolve, reject) {
          fetch(urls.certificate, { credentials: 'same-origin' })
            .then(function (res) {
              if (!res.ok) throw new Error('Certificate HTTP ' + res.status);
              return res.text();
            })
            .then(resolve)
            .catch(reject);
        });
        global.qz.security.setSignatureAlgorithm('SHA512');
        global.qz.security.setSignaturePromise(function (toSign) {
          return function (resolve, reject) {
            fetch(urls.sign, {
              method: 'POST',
              credentials: 'same-origin',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ request: toSign }),
            })
              .then(function (res) {
                return res.json().then(function (data) {
                  if (!res.ok || !data.success || !data.signature) {
                    throw new Error(
                      (data && (data.error || data.message)) || 'Sign HTTP ' + res.status
                    );
                  }
                  resolve(data.signature);
                });
              })
              .catch(reject);
          };
        });
        qzSecurityConfigured = true;
      }
      if (!global.qz.websocket.isActive()) {
        await global.qz.websocket.connect();
      }
    }

    async function loadPrinters() {
      await ensureQzConnected();
      var found = [];
      try {
        var res = await global.qz.printers.find();
        if (Array.isArray(res)) {
          found = res
            .map(function (x) {
              return String(x || '').trim();
            })
            .filter(function (x) {
              return !!x;
            });
        } else if (res != null) {
          found = [String(res).trim()].filter(function (x) {
            return !!x;
          });
        }
      } catch (e) {
        throw new Error('QZ Tray printer fetch failed: ' + (e.message || e));
      }
      found = Array.from(new Set(found)).sort(function (a, b) {
        return a.localeCompare(b);
      });
      if (!found.length) throw new Error('No printers returned by QZ Tray.');
      printerRows = found;
      return found;
    }

    function savePref() {
      if (!global.QzPrinterPrefs || !prefRole) {
        alert('Printer prefs script missing.');
        return false;
      }
      global.QzPrinterPrefs.set(prefRole, inputEl ? inputEl.value : '');
      flashBadge(saveBadgeEl);
      return true;
    }

    if (modalOverlayEl) modalOverlayEl.addEventListener('click', closeModal);
    if (modalCloseEl) modalCloseEl.addEventListener('click', closeModal);
    if (searchEl) {
      searchEl.addEventListener('input', function () {
        renderRows(searchEl.value);
      });
      searchEl.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          closeModal();
        }
      });
    }

    return {
      applySaved: applySaved,
      closeModal: closeModal,
      openModal: openModal,
      loadPrinters: loadPrinters,
      savePref: savePref,
      ensureQzConnected: ensureQzConnected,
    };
  }

  global.QzPrinterPicker = { init: initQzPrinterPicker };
})(typeof window !== 'undefined' ? window : globalThis);
