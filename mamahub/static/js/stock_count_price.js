(function () {
  'use strict';
  var root = document.getElementById('scpDetailPage');
  if (!root) return;

  var batchNo = parseInt(root.getAttribute('data-batch-no') || '0', 10);
  var apiLines = root.getAttribute('data-api-lines') || '';
  var apiApply = root.getAttribute('data-api-apply') || '';
  var apiDelete = root.getAttribute('data-api-delete') || '';
  var listUrl = root.getAttribute('data-list-url') || '/';
  var msgEl = document.getElementById('scpMsg');

  function showMsg(t, isErr) {
    if (!msgEl) return;
    msgEl.textContent = t || '';
    msgEl.style.color = isErr ? '#b91c1c' : '#64748b';
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) throw new Error((j && j.error) || r.statusText);
        return j;
      });
    });
  }

  function collectLineEdits() {
    var byLine = {};
    root.querySelectorAll('.scp-edit-new').forEach(function (inp) {
      var ln = parseInt(inp.getAttribute('data-line') || '0', 10);
      var field = inp.getAttribute('data-field') || '';
      if (!ln || !field) return;
      if (!byLine[ln]) byLine[ln] = { line_no: ln };
      var v = inp.value;
      if (v !== '' && v != null) byLine[ln][field] = parseFloat(v);
    });
    return Object.keys(byLine).map(function (k) {
      return byLine[k];
    });
  }

  function saveLineEditsThen(fn) {
    var edits = collectLineEdits();
    if (!edits.length) {
      fn();
      return;
    }
    var items = {};
    edits.forEach(function (e) {
      var ln = e.line_no;
      if (!items[ln]) items[ln] = { itemcode: 0 };
      Object.keys(e).forEach(function (k) {
        if (k !== 'line_no') items[ln][k] = e[k];
      });
    });
    var rows = root.querySelectorAll('#scpLinesBody tr[data-line-no]');
    var lines = [];
    rows.forEach(function (tr) {
      var lno = parseInt(tr.getAttribute('data-line-no') || '0', 10);
      if (!lno || !items[lno]) return;
      var icCell = tr.querySelectorAll('td')[2];
      var ic = parseInt((icCell && icCell.textContent) || '0', 10);
      var payload = { itemcode: ic, uom: 'NOS' };
      Object.assign(payload, items[lno]);
      lines.push(payload);
    });
    if (!lines.length) {
      fn();
      return;
    }
    postJson(apiLines, { batch_no: batchNo, lines: lines })
      .then(fn)
      .catch(function (err) {
        showMsg(err.message || String(err), true);
      });
  }

  var btnAdd = document.getElementById('scpBtnAddLine');
  if (btnAdd) {
    btnAdd.addEventListener('click', function () {
      var ic = parseInt(document.getElementById('scpItemCode').value || '0', 10);
      if (!ic) {
        showMsg('Item code is required.', true);
        return;
      }
      var line = {
        itemcode: ic,
        barcode: (document.getElementById('scpBarcode').value || '').trim(),
        uom: (document.getElementById('scpUom').value || 'NOS').trim(),
      };
      var slno = parseInt(document.getElementById('scpSlno').value || '0', 10);
      if (slno > 0) line.alt_slno = slno;
      ['scpRetail', 'scpCost', 'scpWholesale'].forEach(function (id) {
        var el = document.getElementById(id);
        if (!el || el.value === '') return;
        if (id === 'scpRetail') line.retail_price = parseFloat(el.value);
        if (id === 'scpCost') line.cost_price = parseFloat(el.value);
        if (id === 'scpWholesale') line.wholesale_price = parseFloat(el.value);
      });
      postJson(apiLines, { batch_no: batchNo, lines: [line] })
        .then(function () {
          window.location.reload();
        })
        .catch(function (err) {
          showMsg(err.message || String(err), true);
        });
    });
  }

  var btnJson = document.getElementById('scpBtnJsonImport');
  if (btnJson) {
    btnJson.addEventListener('click', function () {
      var raw = (document.getElementById('scpJsonImport').value || '').trim();
      if (!raw) return;
      var data;
      try {
        data = JSON.parse(raw);
      } catch (e) {
        showMsg('Invalid JSON.', true);
        return;
      }
      var lines = data.lines || data;
      if (!Array.isArray(lines)) {
        showMsg('Expected { "lines": [...] }', true);
        return;
      }
      postJson(apiLines, { batch_no: batchNo, lines: lines })
        .then(function () {
          window.location.reload();
        })
        .catch(function (err) {
          showMsg(err.message || String(err), true);
        });
    });
  }

  function applyPrices(opts) {
    saveLineEditsThen(function () {
      var body = Object.assign({ batch_no: batchNo }, opts || {});
      var altChk = document.getElementById('scpUpdateAllAlts');
      if (altChk && altChk.checked) body.update_all_alternates = true;
      postJson(apiApply, body)
        .then(function (res) {
          showMsg(res.message || 'Applied.');
          setTimeout(function () {
            window.location.reload();
          }, 600);
        })
        .catch(function (err) {
          showMsg(err.message || String(err), true);
        });
    });
  }

  var btnSel = document.getElementById('scpBtnApplySelected');
  if (btnSel) {
    btnSel.addEventListener('click', function () {
      var nos = [];
      root.querySelectorAll('.scp-line-check:checked').forEach(function (c) {
        nos.push(parseInt(c.value, 10));
      });
      if (!nos.length) {
        showMsg('Select at least one pending line.', true);
        return;
      }
      if (!confirm('Update ITEMMASTER and alternate UOM for ' + nos.length + ' selected line(s)?')) return;
      applyPrices({ line_nos: nos });
    });
  }

  var btnBulk = document.getElementById('scpBtnApplyBulk');
  if (btnBulk) {
    btnBulk.addEventListener('click', function () {
      if (!confirm('Bulk update all PENDING lines to ITEMMASTER and alternate UOM?')) return;
      applyPrices({ apply_all_pending: true });
    });
  }

  var chkAll = document.getElementById('scpCheckAll');
  if (chkAll) {
    chkAll.addEventListener('change', function () {
      root.querySelectorAll('.scp-line-check').forEach(function (c) {
        c.checked = chkAll.checked;
      });
    });
  }

  var btnDel = document.getElementById('scpBtnDelete');
  if (btnDel) {
    btnDel.addEventListener('click', function () {
      if (!confirm('Delete this price batch?')) return;
      postJson(apiDelete, { batch_no: batchNo })
        .then(function () {
          window.location.href = listUrl;
        })
        .catch(function (err) {
          showMsg(err.message || String(err), true);
        });
    });
  }
})();
