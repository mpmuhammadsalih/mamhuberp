(function () {
  'use strict';

  var cfg = window.OS_PAGE || {};
  var batchNo = cfg.batchNo;
  var urls = cfg.urls || {};

  function $(id) { return document.getElementById(id); }
  function msg(text, ok) {
    var el = $('osMessage');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'os-msg ' + (ok ? 'ok' : 'error');
    if (!text) el.style.display = 'none';
    else el.style.display = 'block';
  }
  function fmt(n) {
    var x = parseFloat(n);
    if (isNaN(x)) return '—';
    return x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function pillClass(st) {
    if (st === 'Matched') return 'os-pill os-pill--matched';
    if (st === 'Posted') return 'os-pill os-pill--posted';
    if (['Validation Error', 'Order Not Found', 'Amount Mismatch', 'Post Failed', 'Duplicate Order ID'].indexOf(st) >= 0) return 'os-pill os-pill--error';
    if (['Manual Review Required', 'Already Settled'].indexOf(st) >= 0) return 'os-pill os-pill--warn';
    return 'os-pill os-pill--neutral';
  }
  function setBusy(btn, on) {
    if (!btn) return;
    btn.disabled = !!on;
  }
  var postInFlight = false;

  function applySaveNonce(data) {
    if (!data || typeof data.save_nonce !== 'string' || !data.save_nonce) return;
    window.__GLOBAL_SAVE_NONCE = data.save_nonce;
    var h = document.querySelector('input[name="save_nonce"]');
    if (h) h.value = data.save_nonce;
  }

  function lockPostButtons(on) {
    ['osBtnPostAll', 'osBtnPostSel', 'osBtnValidate', 'osBtnMatch'].forEach(function (id) {
      setBusy($(id), on);
    });
  }

  function markAuditPending() {
    var postAll = $('osBtnPostAll');
    if (postAll) postAll.dataset.traPendingComplete = '1';
  }

  function apiPostRaw(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body || {}),
      credentials: 'same-origin',
      loadingMessage: 'Posting settlement…',
    }).then(function (r) {
      return r.json().then(function (data) {
        return { ok: r.ok, status: r.status, data: data || {} };
      });
    });
  }

  function postSettlement(body, confirmMsg) {
    if (!batchNo) return Promise.resolve();
    if (postInFlight) {
      msg('A post is already in progress. Please wait.', false);
      return Promise.resolve();
    }
    if (confirmMsg && !confirm(confirmMsg)) return Promise.resolve();
    postInFlight = true;
    lockPostButtons(true);
    markAuditPending();
    return apiPostRaw(urls.post, body).then(function (res) {
      var data = res.data || {};
      applySaveNonce(data);
      postInFlight = false;
      lockPostButtons(false);
      var postAll = $('osBtnPostAll');
      if (postAll) postAll.dataset.traPendingComplete = '0';
      if (res.status === 423 || data.save_session_locked) {
        msg(data.error || 'Post already in progress in this session.', false);
        window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: data }));
        return;
      }
      if (data.replay_blocked || res.status === 409) {
        msg((data.error || 'Duplicate submit.') + ' Reload the page and try again.', false);
        window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: data }));
        return;
      }
      if (!data.success) {
        msg(data.error || 'Posting failed', false);
        window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: data }));
        return;
      }
      renderGrid(data.lines || []);
      msg('Posted: ' + (data.posted || 0) + ', Failed: ' + (data.failed || 0), true);
      window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data }));
    }).catch(function () {
      postInFlight = false;
      lockPostButtons(false);
      msg('Posting failed', false);
      window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed'));
    });
  }
  function apiPost(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body || {}),
      credentials: 'same-origin'
    }).then(function (r) { return r.json(); });
  }
  function apiPatch(lineId, body) {
    return fetch(urls.line + '/' + lineId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body || {}),
      credentials: 'same-origin'
    }).then(function (r) { return r.json(); });
  }

  function lookupValue(name) {
    var el = document.querySelector('input[name="' + name + '"]');
    return el ? String(el.value || '').trim() : '';
  }

  function setLookupField(fieldId, code, label) {
    var display = document.getElementById(fieldId + 'Display');
    var root = display && display.closest('.global-lookup, .odoo-lookup');
    var hidden = root && root.querySelector('.global-lookup__value, .odoo-lookup__value');
    if (display) display.value = label || code || '';
    if (hidden) hidden.value = code || '';
    var clearBtn = root && root.querySelector('.global-lookup__clear, .odoo-lookup__clear');
    if (clearBtn) clearBtn.hidden = !(code || (display && display.value));
  }

  function numVal(v) {
    var x = parseFloat(v);
    return isNaN(x) ? 0 : x;
  }

  function computePostingTotals(lines) {
    var t = { bank: 0, receivable: 0, pm: 0, sc: 0, sp: 0, oc: 0, count: 0 };
    (lines || []).forEach(function (ln) {
      if (String(ln.excluded || 'N').toUpperCase() === 'Y') return;
      t.count++;
      t.bank += numVal(ln.net_amount_received != null ? ln.net_amount_received : ln.total_amount);
      t.receivable += numVal(ln.upload_invoice_amount);
      t.pm += Math.abs(numVal(ln.pm_commission));
      t.sc += Math.abs(numVal(ln.sales_commission));
      t.sp += Math.abs(numVal(ln.splus_amount));
      t.oc += Math.abs(numVal(ln.other_charges));
    });
    return t;
  }

  function setAcctAmt(id, tag, amount, hasRows) {
    var el = $(id);
    if (!el) return;
    if (!hasRows) {
      el.innerHTML = '<span class="os-acct-amt__tag">' + tag + '</span> ' + (batchNo ? fmt(0) : '—');
      el.className = 'os-acct-amt' + (batchNo ? '' : ' is-empty');
      return;
    }
    el.innerHTML = '<span class="os-acct-amt__tag">' + tag + '</span> ' + fmt(amount);
    el.className = 'os-acct-amt';
  }

  function updateAccountTotals(lines) {
    var hasLines = lines && lines.length;
    var t = hasLines ? computePostingTotals(lines) : null;
    setAcctAmt('osAmtCustomer', 'Cr', t ? t.receivable : 0, hasLines);
    setAcctAmt('osAmtBank', 'Dr', t ? t.bank : 0, hasLines);
    setAcctAmt('osAmtPm', 'Dr', t ? t.pm : 0, hasLines);
    setAcctAmt('osAmtSc', 'Dr', t ? t.sc : 0, hasLines);
    setAcctAmt('osAmtSplus', 'Dr', t ? t.sp : 0, hasLines);
    setAcctAmt('osAmtOther', 'Dr', t ? t.oc : 0, hasLines);
  }

  function computeLineTotals(lines) {
    var t = { upload: 0, erp: 0, net: 0, pm: 0, sc: 0, sp: 0, oc: 0, diff: 0, count: 0 };
    (lines || []).forEach(function (ln) {
      if (String(ln.excluded || 'N').toUpperCase() === 'Y') return;
      t.count++;
      t.upload += numVal(ln.upload_invoice_amount);
      if (ln.erp_invoice_amount != null) t.erp += numVal(ln.erp_invoice_amount);
      t.net += numVal(ln.net_amount_received != null ? ln.net_amount_received : ln.total_amount);
      t.pm += numVal(ln.pm_commission);
      t.sc += numVal(ln.sales_commission);
      t.sp += numVal(ln.splus_amount);
      t.oc += numVal(ln.other_charges);
      if (ln.difference != null) t.diff += numVal(ln.difference);
    });
    return t;
  }

  function updateGridTotals(lines) {
    var foot = $('osGridFoot');
    if (!foot) return;
    if (!lines || !lines.length) {
      foot.style.display = 'none';
      updateAccountTotals([]);
      return;
    }
    foot.style.display = '';
    var t = computeLineTotals(lines);
    function setTot(id, val, always) {
      var el = $(id);
      if (!el) return;
      el.textContent = (always || t.count) ? fmt(val) : '—';
    }
    setTot('osTotUpload', t.upload, true);
    setTot('osTotErp', t.erp, t.erp !== 0);
    setTot('osTotNet', t.net, true);
    setTot('osTotPm', t.pm, true);
    setTot('osTotSc', t.sc, true);
    setTot('osTotSplus', t.sp, true);
    setTot('osTotOther', t.oc, true);
    setTot('osTotDiff', t.diff, t.diff !== 0);
    updateAccountTotals(lines);
  }

  function linesFromDom() {
    var out = [];
    document.querySelectorAll('#osGridBody tr[data-line-id]').forEach(function (tr) {
      var cells = tr.querySelectorAll('td');
      if (cells.length < 12) return;
      out.push({
        excluded: tr.dataset.excluded || 'N',
        upload_invoice_amount: cells[4].textContent.replace(/,/g, ''),
        erp_invoice_amount: cells[5].textContent.trim() === '—' ? null : cells[5].textContent.replace(/,/g, ''),
        net_amount_received: cells[6].textContent.replace(/,/g, ''),
        pm_commission: cells[7].textContent.replace(/,/g, ''),
        sales_commission: cells[8].textContent.replace(/,/g, ''),
        splus_amount: cells[9].textContent.replace(/,/g, ''),
        other_charges: cells[10].textContent.replace(/,/g, ''),
        difference: cells[11].textContent.trim() === '—' ? null : cells[11].textContent.replace(/,/g, ''),
      });
    });
    return out;
  }

  function renderGrid(lines) {
    var tbody = $('osGridBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!lines || !lines.length) {
      tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;padding:24px;color:#64748b;">No rows.</td></tr>';
      updateKpi([]);
      updateGridTotals([]);
      updateAccountTotals([]);
      return;
    }
    lines.forEach(function (ln) {
      var tr = document.createElement('tr');
      tr.dataset.lineId = ln.line_id;
      tr.dataset.status = ln.status || '';
      tr.dataset.excluded = ln.excluded || 'N';
      if (ln.status === 'Posted') tr.classList.add('posted');
      var chkDisabled = ln.status !== 'Matched' ? ' disabled' : '';
      tr.innerHTML =
        '<td style="text-align:center;"><input type="checkbox" class="os-row-check" value="' + ln.line_id + '"' + chkDisabled + ' /></td>' +
        '<td>' + (ln.order_id || '—') + '</td>' +
        '<td>' + (ln.erp_invoice_no || '—') + '</td>' +
        '<td>' + (ln.erp_invoice_date || '—') + '</td>' +
        '<td class="num">' + fmt(ln.upload_invoice_amount) + '</td>' +
        '<td class="num">' + fmt(ln.erp_invoice_amount) + '</td>' +
        '<td class="num">' + fmt(ln.net_amount_received != null ? ln.net_amount_received : ln.total_amount) + '</td>' +
        '<td class="num">' + fmt(ln.pm_commission) + '</td>' +
        '<td class="num">' + fmt(ln.sales_commission) + '</td>' +
        '<td class="num">' + fmt(ln.splus_amount) + '</td>' +
        '<td class="num">' + fmt(ln.other_charges) + '</td>' +
        '<td class="num">' + fmt(ln.difference) + '</td>' +
        '<td><input type="text" class="os-manual" data-line-id="' + ln.line_id + '" value="' + (ln.manual_invoice_voucher || '') + '" placeholder="SI-…"' + (ln.status === 'Posted' ? ' disabled' : '') + ' /></td>' +
        '<td>' + (ln.status !== 'Posted' && (ln.excluded || 'N') !== 'Y'
          ? '<button type="button" class="os-exclude" data-line-id="' + ln.line_id + '" style="font-size:11px;padding:2px 6px;">Exclude</button>'
          : ((ln.excluded || 'N') === 'Y' ? '<span style="font-size:11px;color:#94a3b8;">Excluded</span>' : '')) + '</td>' +
        '<td><span class="' + pillClass(ln.status) + '">' + (ln.status || '—') + '</span></td>';
      tbody.appendChild(tr);
    });
    bindManualInputs();
    bindExcludeButtons();
    updateKpi(lines);
    updateGridTotals(lines);
  }

  function bindExcludeButtons() {
    document.querySelectorAll('.os-exclude').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var lid = parseInt(btn.dataset.lineId, 10);
        if (!lid || !confirm('Exclude this row from posting?')) return;
        apiPatch(lid, { excluded: true }).then(function (res) {
          if (!res.success) msg(res.error || 'Exclude failed', false);
          else reloadBatch();
        });
      });
    });
  }

  function updateKpi(lines) {
    var total = lines.length;
    var matched = 0, posted = 0, exc = 0;
    var bad = ['Order Not Found', 'Amount Mismatch', 'Already Settled', 'Duplicate Order ID', 'Validation Error', 'Manual Review Required', 'Post Failed'];
    lines.forEach(function (ln) {
      if (ln.status === 'Matched') matched++;
      if (ln.status === 'Posted') posted++;
      if (bad.indexOf(ln.status) >= 0) exc++;
    });
    $('osKpiTotal').textContent = total;
    $('osKpiMatched').textContent = matched;
    $('osKpiPosted').textContent = posted;
    $('osKpiExc').textContent = exc;
  }

  function reloadBatch() {
    if (!batchNo) return Promise.resolve();
    return fetch(urls.batch + encodeURIComponent(batchNo), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) renderGrid(data.lines || []);
        else msg(data.error || 'Load failed', false);
      });
  }

  function bindManualInputs() {
    document.querySelectorAll('.os-manual').forEach(function (inp) {
      inp.addEventListener('change', function () {
        var lid = parseInt(inp.dataset.lineId, 10);
        if (!lid) return;
        apiPatch(lid, { manual_invoice_voucher: inp.value.trim() }).then(function (res) {
          if (!res.success) msg(res.error || 'Update failed', false);
          else msg('Manual invoice saved — run Auto Match again.', true);
        });
      });
    });
  }

  function saveConfigFromForm() {
    var cc = lookupValue('customer_code');
    if (!cc) return;
    fetch(urls.config, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_code: cc,
        marketplace_name: ($('osMarketplace') || {}).value,
        bank_account: lookupValue('bank_account'),
        pm_commission_account: lookupValue('pm_commission_account'),
        sales_commission_account: lookupValue('sales_commission_account'),
        splus_account: lookupValue('splus_account'),
        other_charges_account: lookupValue('other_charges_account')
      }),
      credentials: 'same-origin'
    });
  }

  function loadConfigForCustomer(cc) {
    if (!cc) return;
    fetch(urls.config + '?customer_code=' + encodeURIComponent(cc), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success || !data.config) return;
        var c = data.config;
        if ($('osMarketplace') && c.marketplace_name) $('osMarketplace').value = c.marketplace_name;
        setLookupField('osBank', c.bank_account || '', c.bank_label || c.bank_account || '');
        setLookupField('osPm', c.pm_commission_account || '', c.pm_label || c.pm_commission_account || '');
        setLookupField('osSc', c.sales_commission_account || '', c.sc_label || c.sales_commission_account || '');
        setLookupField('osSplus', c.splus_account || '', c.sp_label || c.splus_account || '');
        setLookupField('osOther', c.other_charges_account || '', c.oc_label || c.other_charges_account || '');
      });
  }

  var osPeriodGuard = null;
  if (!batchNo && window.PeriodDateGuard && window.PeriodDateGuard.bind) {
    osPeriodGuard = window.PeriodDateGuard.bind(
      $('osSettlementDate'),
      window.PeriodDateGuard.fromJsonScript('osClosedPeriodsJson'),
      { hintEl: $('osSettlementDateHint') }
    );
  } else if (window.PeriodDateGuard && batchNo) {
    var hintOnly = $('osSettlementDateHint');
    var dateEl = $('osSettlementDate');
    var periods = window.PeriodDateGuard.fromJsonScript('osClosedPeriodsJson');
    if (hintOnly && dateEl) {
      var lockedMsg = window.PeriodDateGuard.messageForDate(dateEl.value, periods);
      hintOnly.textContent = lockedMsg || window.PeriodDateGuard.defaultHint(periods);
      if (lockedMsg) hintOnly.style.color = '#b91c1c';
    }
  }

  var uploadForm = $('osUploadForm');
  if (uploadForm) {
    uploadForm.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (batchNo) {
        msg('Batch already loaded. Open History for a new upload.', false);
        return;
      }
      if (osPeriodGuard) {
        var closedMsg = osPeriodGuard.message();
        if (closedMsg) {
          osPeriodGuard.refresh();
          msg(closedMsg, false);
          return;
        }
      }
      if (!lookupValue('customer_code')) {
        msg('Marketplace customer is required.', false);
        return;
      }
      if (!lookupValue('bank_account')) {
        msg('Bank / clearing account is required.', false);
        return;
      }
      if (!lookupValue('pm_commission_account') || !lookupValue('sales_commission_account')
          || !lookupValue('splus_account') || !lookupValue('other_charges_account')) {
        msg('All expense accounts are required (PM, Sales, SPlus, Other charges).', false);
        return;
      }
      var fd = new FormData(uploadForm);
      var btn = $('osBtnUpload');
      setBusy(btn, true);
      msg('Uploading…', true);
      fetch(urls.upload, { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          setBusy(btn, false);
          if (!data.success) {
            msg(data.error || 'Upload failed', false);
            return;
          }
          saveConfigFromForm();
          window.location.href = urls.page + '?batch=' + encodeURIComponent(data.batch_no);
        })
        .catch(function () {
          setBusy(btn, false);
          msg('Upload failed', false);
        });
    });
  }

  var custDisplay = $('osCustomerDisplay');
  if (custDisplay) {
    custDisplay.addEventListener('global-lookup:select', function (ev) {
      var code = ev.detail && ev.detail.code;
      loadConfigForCustomer(code || lookupValue('customer_code'));
      if ($('osMarketplace') && ev.detail && ev.detail.label && !($('osMarketplace').value || '').trim()) {
        var parts = String(ev.detail.label).split(' — ');
        $('osMarketplace').value = parts.length > 1 ? parts.slice(1).join(' — ') : '';
      }
    });
    custDisplay.addEventListener('change', function () {
      loadConfigForCustomer(lookupValue('customer_code'));
    });
  }

  $('osBtnValidate') && $('osBtnValidate').addEventListener('click', function () {
    if (!batchNo) return;
    setBusy(this, true);
    apiPost(urls.validate, { batch_no: batchNo }).then(function (data) {
      setBusy($('osBtnValidate'), false);
      if (!data.success) { msg(data.error || 'Validation failed', false); return; }
      renderGrid(data.lines || []);
      msg('Validation complete.', true);
    });
  });

  $('osBtnMatch') && $('osBtnMatch').addEventListener('click', function () {
    if (!batchNo) return;
    setBusy(this, true);
    apiPost(urls.match, { batch_no: batchNo }).then(function (data) {
      setBusy($('osBtnMatch'), false);
      if (!data.success) { msg(data.error || 'Auto match failed', false); return; }
      renderGrid(data.lines || []);
      msg('Auto match complete. Matched: ' + (data.matched || 0), true);
    });
  });

  $('osBtnPostAll') && $('osBtnPostAll').addEventListener('click', function () {
    postSettlement(
      { batch_no: batchNo, post_all_matched: true },
      'Post all matched rows? Unmatched rows will be skipped.'
    );
  });

  $('osBtnPostSel') && $('osBtnPostSel').addEventListener('click', function () {
    var ids = [];
    document.querySelectorAll('.os-row-check:checked').forEach(function (c) {
      ids.push(parseInt(c.value, 10));
    });
    if (!ids.length) { msg('Select matched rows to post.', false); return; }
    postSettlement({ batch_no: batchNo, line_ids: ids }, null);
  });

  $('osBtnExport') && $('osBtnExport').addEventListener('click', function () {
    if (!batchNo) return;
    window.location.href = urls.exportExc + '?batch_no=' + encodeURIComponent(batchNo);
  });

  $('osBtnReload') && $('osBtnReload').addEventListener('click', function () {
    reloadBatch().then(function () { msg('Grid refreshed.', true); });
  });

  $('osSelectAll') && $('osSelectAll').addEventListener('change', function () {
    var on = this.checked;
    document.querySelectorAll('.os-row-check:not(:disabled)').forEach(function (c) { c.checked = on; });
  });

  bindManualInputs();
  if (batchNo && !document.querySelector('#osGridBody tr[data-line-id]')) {
    reloadBatch();
  } else if (document.querySelector('#osGridBody tr[data-line-id]')) {
    updateGridTotals(linesFromDom());
  }
})();
