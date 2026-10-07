/**
 * AI Reports — AI-first temporary invoice reports; Advanced manual builder & pivot.
 */
(function () {
  'use strict';

  var urls = {};
  var maxColumns = 48;
  var catalogDefaults = [];
  var groups = [];
  var labelById = {};
  var selectedOrder = [];
  var lastRun = null;
  var saResizing = false;
  var saAiLastIds = [];
  var saAiReportOpts = null;
  var catalogReady = false;
  var aiBusy = false;

  var filterAliases = [];
  var columnsByAlias = {};
  var filterRows = [];
  var filterSeq = 0;
  var SA_OPS = ['=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT LIKE', 'IN', 'IS NULL', 'IS NOT NULL'];

  var GROUP_BADGE = {
    hdr: 'h',
    dtl: 'd',
    cust: 'c',
    im: 'im',
    sch_hdr: 'ch',
    sch_cust: 'cc',
  };

  function $(id) {
    return document.getElementById(id);
  }

  function readUrls() {
    var el = document.getElementById('saUrls');
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return {};
    }
  }

  function indexCatalog(glist) {
    labelById = {};
    (glist || []).forEach(function (g) {
      (g.fields || []).forEach(function (f) {
        labelById[f.id] = f.label || f.id;
      });
    });
  }

  function groupKeyForColumnId(fieldId) {
    var k = '';
    groups.forEach(function (g) {
      (g.fields || []).forEach(function (f) {
        if (f.id === fieldId) k = g.key || '';
      });
    });
    return k;
  }

  function selectedIds() {
    return selectedOrder.map(function (x) {
      return x.id;
    });
  }

  function selectionHas(id) {
    return selectedOrder.some(function (x) {
      return x.id === id;
    });
  }

  function showCatalogErr(msg) {
    var el = $('saCatalogErr');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('visible', !!msg);
  }

  function showResultErr(msg) {
    var el = $('saResultError');
    if (el) el.textContent = msg || '';
    if (msg && String(msg).trim()) {
      var rp = $('saResultsPanel');
      try {
        if (rp) rp.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch (ignore) {}
    }
  }

  function catalogHasFields() {
    return groups.some(function (g) {
      return (g.fields || []).length > 0;
    });
  }

  /** Run is allowed with no picked columns: server applies defaults when the catalog is loaded. */
  function setRunEnabled() {
    var hasPick = selectedOrder.length > 0;
    var hasSavedDefaults = !!(catalogDefaults && catalogDefaults.length);
    var dis = !hasPick && !hasSavedDefaults && !catalogHasFields();
    var btn = $('saRunBtn');
    if (btn) btn.disabled = dis;
  }

  function updateBadges() {
    var badge = $('saFieldBadge');
    if (badge) {
      badge.textContent = String(selectedOrder.length);
      badge.style.display = selectedOrder.length ? '' : 'none';
    }
    var expOk = !!(lastRun && lastRun.rows && lastRun.rows.length);
    var exp = $('saExportBtn');
    if (exp) exp.disabled = !expOk;
  }

  function syncOrderTblOptions() {
    var sel = $('saOrderTbl');
    if (!sel) return;
    var cur = sel.value;
    sel.innerHTML = (filterAliases || [])
      .map(function (a) {
        return (
          '<option value="' +
          escapeHtml(a.key) +
          '">' +
          escapeHtml(a.label) +
          '</option>'
        );
      })
      .join('');
    if (cur && filterAliases.some(function (a) { return a.key === cur; })) {
      sel.value = cur;
    } else if (filterAliases.length) {
      sel.value = filterAliases[0].key;
    }
  }

  function syncOrderColOptions() {
    var tblEl = $('saOrderTbl');
    var sel = $('saOrderCol');
    if (!tblEl || !sel) return;
    var alias =
      tblEl.value || (filterAliases[0] && filterAliases[0].key) || 'h';
    var cur = sel.value;
    var cols = columnsByAlias[alias] || [];
    sel.innerHTML =
      '<option value="">— None —</option>' +
      cols
        .map(function (c) {
          return (
            '<option value="' +
            escapeHtml(c) +
            '">' +
            escapeHtml(c) +
            '</option>'
          );
        })
        .join('');
    if (cur && cols.indexOf(cur) !== -1) sel.value = cur;
  }

  function syncFilterRowsFromDom() {
    var host = $('saFilterList');
    if (!host) return;
    filterRows.forEach(function (r) {
      var row = host.querySelector('[data-fid="' + r.id + '"]');
      if (!row) return;
      var tSel = row.querySelector('.sl-filter-tbl');
      var cSel = row.querySelector('.sl-filter-col');
      var oSel = row.querySelector('.sl-filter-op');
      var vInp = row.querySelector('.sl-filter-val');
      if (tSel) r.alias = tSel.value;
      if (cSel) r.column = cSel.value;
      if (oSel) r.operator = oSel.value;
      if (vInp) r.value = vInp.value;
    });
  }

  function collectFiltersPayload() {
    syncFilterRowsFromDom();
    return filterRows
      .filter(function (r) {
        return r.column;
      })
      .map(function (r) {
        return {
          alias: r.alias,
          column: r.column,
          operator: r.operator,
          value: r.value,
        };
      });
  }

  function orderByPayload() {
    var tbl = $('saOrderTbl');
    var col = $('saOrderCol');
    var dir = $('saOrderDir');
    var c = col && col.value ? col.value : '';
    if (!c) return null;
    return {
      alias: (tbl && tbl.value) || 'h',
      column: c,
      direction: (dir && dir.value) || 'ASC',
    };
  }

  function renderFilterList() {
    var host = $('saFilterList');
    if (!host) return;

    if (!filterRows.length) {
      host.innerHTML =
        '<div style="color:#94a3b8;font-size:.75rem;">No extra filters — base WHERE still applies (bill types C/R/T, bill date range, your location).</div>';
      return;
    }

    host.innerHTML = filterRows
      .map(function (r) {
        var ops = SA_OPS.map(function (o) {
          return (
            '<option' +
            (r.operator === o ? ' selected' : '') +
            '>' +
            escapeHtml(o) +
            '</option>'
          );
        }).join('');
        var aliasOpts = filterAliases
          .map(function (a) {
            return (
              '<option value="' +
              escapeHtml(a.key) +
              '"' +
              (r.alias === a.key ? ' selected' : '') +
              '>' +
              escapeHtml(a.label) +
              '</option>'
            );
          })
          .join('');
        var cols = columnsByAlias[r.alias] || [];
        var colOpts =
          '<option value="">— Col —</option>' +
          cols
            .map(function (c) {
              return (
                '<option value="' +
                escapeHtml(c) +
                '"' +
                (r.column === c ? ' selected' : '') +
                '>' +
                escapeHtml(c) +
                '</option>'
              );
            })
            .join('');
        var noVal = r.operator === 'IS NULL' || r.operator === 'IS NOT NULL';
        return (
          '<div class="sl-filter-row" data-fid="' +
          r.id +
          '">' +
          '<select class="sl-filter-tbl">' +
          aliasOpts +
          '</select>' +
          '<select class="sl-filter-col">' +
          colOpts +
          '</select>' +
          '<select class="sl-filter-op">' +
          ops +
          '</select>' +
          '<input class="sl-filter-val" type="text" placeholder="Value"' +
          (noVal ? ' style="display:none;"' : '') +
          ' value="' +
          escapeHtml(r.value || '') +
          '">' +
          '<button type="button" class="sl-btn-icon" data-rm="' +
          r.id +
          '">&#10005;</button>' +
          '</div>'
        );
      })
      .join('');

    filterRows.forEach(function (r) {
      var row = host.querySelector('[data-fid="' + r.id + '"]');
      if (!row) return;
      var tSel = row.querySelector('.sl-filter-tbl');
      var oSel = row.querySelector('.sl-filter-op');
      var cSel = row.querySelector('.sl-filter-col');
      var vInp = row.querySelector('.sl-filter-val');
      if (tSel) {
        tSel.value = r.alias;
        tSel.addEventListener('change', function () {
          r.alias = tSel.value;
          r.column = '';
          renderFilterList();
        });
      }
      if (cSel) {
        cSel.addEventListener('change', function () {
          r.column = cSel.value;
        });
      }
      if (oSel) {
        oSel.value = r.operator;
        oSel.addEventListener('change', function () {
          r.operator = oSel.value;
          renderFilterList();
        });
      }
      if (vInp) {
        vInp.addEventListener('input', function () {
          r.value = vInp.value;
        });
      }
      var rm = row.querySelector('[data-rm]');
      if (rm) {
        rm.addEventListener('click', function () {
          filterRows = filterRows.filter(function (x) {
            return x.id !== r.id;
          });
          renderFilterList();
        });
      }
    });
  }

  function addFilterRow() {
    if (!filterAliases.length) return;
    filterSeq++;
    filterRows.push({
      id: filterSeq,
      alias: filterAliases[0].key,
      column: '',
      operator: '=',
      value: '',
    });
    renderFilterList();
  }

  function payloadFilters() {
    return {
      date_from: ($('saDateFrom') && $('saDateFrom').value) || '',
      date_to: ($('saDateTo') && $('saDateTo').value) || '',
      filters: collectFiltersPayload(),
      order_by: orderByPayload(),
    };
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function renderAvailCols() {
    var host = $('saColList');
    var countEl = $('saColCount');
    if (!host) return;
    var q = (($('saColSearch') && $('saColSearch').value) || '').trim().toLowerCase();
    var total = 0;
    var html = '';
    groups.forEach(function (g) {
      var cols = (g.fields || []).filter(function (f) {
        var lab = (f.label || f.id || '').toLowerCase();
        return !q || lab.indexOf(q) !== -1;
      });
      if (!cols.length) return;
      total += cols.length;
      var badge = GROUP_BADGE[g.key] || String(g.key || '').slice(0, 3);
      html += '<div class="sl-tbl-group-avail">';
      html +=
        '<div class="sl-tbl-group-avail-label"><span class="sl-tbl-alias-badge">' +
        escapeHtml(badge) +
        '</span> ' +
        escapeHtml(g.title || g.key) +
        '</div>';
      cols.forEach(function (f) {
        var added = selectionHas(f.id) ? ' added' : '';
        html +=
          '<div class="sl-col-item' +
          added +
          '" data-field-id="' +
          escapeHtml(f.id) +
          '" data-group="' +
          escapeHtml(g.key) +
          '">';
        html += '<span>&#128206;</span><span>' + escapeHtml(f.label || f.id) + '</span>';
        html += '</div>';
      });
      html += '</div>';
    });
    host.innerHTML =
      html || '<div style="padding:14px;color:#94a3b8;font-size:.78rem;text-align:center;">No columns</div>';
    if (countEl) countEl.textContent = total ? total + ' cols' : '';

    host.querySelectorAll('.sl-col-item').forEach(function (node) {
      node.addEventListener('click', function () {
        if (node.classList.contains('added')) return;
        var id = node.getAttribute('data-field-id');
        if (!id || selectionHas(id)) return;
        if (selectedOrder.length >= maxColumns) return;
        selectedOrder.push({
          id: id,
          label: labelById[id] || id,
          groupKey: node.getAttribute('data-group') || '',
        });
        renderAvailCols();
        renderFieldList();
        setRunEnabled();
        updateBadges();
      });
    });
  }

  function renderFieldList() {
    var host = $('saFieldList');
    if (!host) return;
    host.innerHTML = '';
    if (!selectedOrder.length) {
      var hint = document.createElement('div');
      hint.className = 'sl-drop-hint';
      hint.textContent = 'Use AI above or pick fields from the catalog';
      host.appendChild(hint);
      setRunEnabled();
      updateBadges();
      return;
    }

    selectedOrder.forEach(function (item) {
      var row = document.createElement('div');
      row.className = 'sl-field-row';
      row.setAttribute('data-field-id', item.id);
      row.draggable = true;

      row.addEventListener('dragstart', function (e) {
        row.classList.add('dragging');
        e.dataTransfer.setData(
          'application/json',
          JSON.stringify({ src: 'fld', id: item.id })
        );
        e.dataTransfer.effectAllowed = 'move';
      });
      row.addEventListener('dragend', function () {
        row.classList.remove('dragging');
      });
      row.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
      });
      row.addEventListener('drop', function (e) {
        e.preventDefault();
        var raw = e.dataTransfer.getData('application/json');
        if (!raw) return;
        var data = JSON.parse(raw);
        if (data.src !== 'fld' || data.id === item.id) return;
        var iFrom = selectedOrder.findIndex(function (x) {
          return x.id === data.id;
        });
        var iTo = selectedOrder.findIndex(function (x) {
          return x.id === item.id;
        });
        if (iFrom < 0 || iTo < 0) return;
        var mv = selectedOrder.splice(iFrom, 1)[0];
        iTo = selectedOrder.findIndex(function (x) {
          return x.id === item.id;
        });
        selectedOrder.splice(iTo, 0, mv);
        renderAvailCols();
        renderFieldList();
      });

      var grip = document.createElement('span');
      grip.className = 'sl-drag-handle';
      grip.textContent = '⠿';

      var tag = document.createElement('span');
      tag.className = 'sl-field-alias-tag';
      tag.textContent = GROUP_BADGE[item.groupKey] || (item.groupKey || '').slice(0, 3) || '?';

      var col = document.createElement('span');
      col.className = 'sl-field-col';
      col.textContent = item.label || item.id;

      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'sl-field-rm';
      rm.setAttribute('aria-label', 'Remove');
      rm.textContent = '×';
      rm.addEventListener('click', function () {
        selectedOrder = selectedOrder.filter(function (x) {
          return x.id !== item.id;
        });
        renderAvailCols();
        renderFieldList();
      });

      row.appendChild(grip);
      row.appendChild(tag);
      row.appendChild(col);
      row.appendChild(rm);
      host.appendChild(row);
    });

    setRunEnabled();
    updateBadges();
  }

  function applyDefaults() {
    selectedOrder = [];
    (catalogDefaults || []).forEach(function (id) {
      var sid = id == null ? '' : String(id).trim();
      if (!sid || selectionHas(sid)) return;
      if (selectedOrder.length >= maxColumns) return;
      var gKey = '';
      groups.forEach(function (g) {
        (g.fields || []).forEach(function (f) {
          if (f.id === sid) gKey = g.key || '';
        });
      });
      selectedOrder.push({
        id: sid,
        label: labelById[sid] || sid,
        groupKey: gKey,
      });
    });
    renderAvailCols();
    renderFieldList();
  }

  function setSpinner(on) {
    var sp = $('saSpinner');
    if (sp) sp.classList.toggle('running', !!on);
    var btn = $('saRunBtn');
    if (!btn) return;
    if (on) btn.disabled = true;
    else setRunEnabled();
  }

  function runReport() {
    showResultErr('');
    if (!urls || !urls.run) {
      showResultErr('Report API URL is missing. Reload the page.');
      return Promise.resolve(false);
    }
    var cols = selectedIds();
    var payload = Object.assign({ columns: cols.length ? cols : catalogDefaults }, payloadFilters());
    setSpinner(true);
    lastRun = null;
    updateBadges();

    return fetch(urls.run, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.text().then(function (text) {
          var j = null;
          if (text) {
            try {
              j = JSON.parse(text);
            } catch (ignore) {}
          }
          return { ok: r.ok, status: r.status, json: j, text: text };
        });
      })
      .then(function (res) {
        setSpinner(false);
        var j = res.json;
        if (!j || typeof j.success === 'undefined') {
          var hint = (res.text || '').replace(/\s+/g, ' ').trim().slice(0, 280);
          showResultErr(
            hint || 'Invalid server response (HTTP ' + (res.status || '?') + ').'
          );
          var rb = $('saResultBody');
          if (rb) {
            rb.innerHTML =
              '<div class="sl-no-result"><span style="font-size:2rem;">&#9888;</span>Error — check message above</div>';
          }
          return false;
        }
        if (!res.ok || !j.success) {
          showResultErr(j.error || 'Run failed');
          var rbod = $('saResultBody');
          if (rbod) {
            rbod.innerHTML =
              '<div class="sl-no-result"><span style="font-size:2rem;">&#9888;</span>Error — check message above</div>';
          }
          return false;
        }
        lastRun = j;
        var cnt = $('saResultCount');
        if (cnt) {
          cnt.textContent =
            (j.rows || []).length + ' row(s)' + (j.truncated_hint ? ' (truncated at limit)' : '');
        }
        showResultErr('');
        renderResultsTable(j);
        return true;
      })
      .catch(function (e) {
        setSpinner(false);
        var msg =
          e && e.message && /failed to fetch|networkerror|load failed/i.test(String(e.message))
            ? 'Could not reach the server — same checks as AI (timeout, proxy, VPN).'
            : 'Network error';
        showResultErr(msg);
        return false;
      });
  }

  function renderResultsTable(data) {
    var body = $('saResultBody');
    if (!body || !data) return;
    if (!data.columns || !data.columns.length) {
      showResultErr('Report returned no columns.');
      body.innerHTML =
        '<div class="sl-no-result"><span style="font-size:2rem;">&#9888;</span>No columns in response</div>';
      return;
    }
    var table = document.createElement('table');
    table.className = 'sl-result-table';
    var thead = document.createElement('thead');
    var thr = document.createElement('tr');
    data.columns.forEach(function (c, i) {
      var th = document.createElement('th');
      th.textContent = (data.column_labels && data.column_labels[i]) || c;
      thr.appendChild(th);
    });
    thead.appendChild(thr);
    var tbody = document.createElement('tbody');
    var rowList = data.rows || [];
    if (!rowList.length) {
      var trE = document.createElement('tr');
      var tdE = document.createElement('td');
      tdE.colSpan = Math.max(data.columns.length, 1);
      tdE.style.cssText = 'padding:18px;color:#64748b;font-size:.82rem;text-align:center;line-height:1.45;';
      tdE.textContent =
        data.empty_hint ||
        'No rows for this bill date range, location, and filters (bill types C, R, T only).';
      trE.appendChild(tdE);
      tbody.appendChild(trE);
    } else {
      rowList.forEach(function (row) {
        var tr = document.createElement('tr');
        data.columns.forEach(function (c) {
          var td = document.createElement('td');
          var v = row[c];
          td.textContent = v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }
    table.appendChild(thead);
    table.appendChild(tbody);
    body.innerHTML = '';
    body.appendChild(table);
    populatePivotSelectors(data);
    switchResultView('table');
    updateBadges();
  }

  var PIVOT_MAX_DIM = 42;

  function switchResultView(mode) {
    var tableBtn = $('saTabResultTable');
    var pivotBtn = $('saTabResultPivot');
    var paneTable = $('saPaneTable');
    var panePivot = $('saPivotPane');
    if (!paneTable || !panePivot) return;
    var isPivot = mode === 'pivot';
    if (tableBtn) {
      tableBtn.classList.toggle('active', !isPivot);
      tableBtn.setAttribute('aria-selected', !isPivot ? 'true' : 'false');
    }
    if (pivotBtn) {
      pivotBtn.classList.toggle('active', isPivot);
      pivotBtn.setAttribute('aria-selected', isPivot ? 'true' : 'false');
    }
    paneTable.style.display = isPivot ? 'none' : '';
    panePivot.classList.toggle('visible', isPivot);
    panePivot.setAttribute('aria-hidden', isPivot ? 'false' : 'true');
  }

  function pivotOptHtml(cols) {
    return (
      '<option value="">— Pick column —</option>' +
      (cols || [])
        .map(function (c) {
          return '<option value="' + escapeHtml(c) + '">' + escapeHtml(c) + '</option>';
        })
        .join('')
    );
  }

  function populatePivotSelectors(data) {
    var cols = (data && data.columns) || [];
    var pr = $('saPivotRow');
    var pc = $('saPivotCol');
    var pv = $('saPivotVal');
    if (!pr || !pc || !pv) return;
    var html = pivotOptHtml(cols);
    pr.innerHTML = html;
    pc.innerHTML = html;
    pv.innerHTML = html;
    if (cols.length >= 1) pr.value = cols[0];
    if (cols.length >= 2) pc.value = cols[1];
    else if (cols.length >= 1) pc.value = cols[0];
    if (cols.length >= 3) pv.value = cols[2];
    else if (cols.length >= 1) pv.value = cols[0];
    if (cols.length >= 2 && pr.value === pc.value) {
      pc.value = cols[1];
    }
  }

  function parsePivotNum(v) {
    if (v == null || v === '') return NaN;
    if (typeof v === 'number' && !isNaN(v)) return v;
    var s = String(v).replace(/,/g, '').trim();
    var n = parseFloat(s);
    return isNaN(n) ? NaN : n;
  }

  function renderPivotMatrix() {
    var grid = $('saPivotGrid');
    if (!grid) return;
    if (!lastRun || !lastRun.rows || !lastRun.columns || !lastRun.rows.length) {
      grid.innerHTML =
        '<div class="sap-pivot-msg">No data — run a report with at least one row.</div>';
      return;
    }
    var rowKey = $('saPivotRow') && $('saPivotRow').value;
    var colKey = $('saPivotCol') && $('saPivotCol').value;
    var valKey = $('saPivotVal') && $('saPivotVal').value;
    var agg = ($('saPivotAgg') && $('saPivotAgg').value) || 'SUM';
    if (!rowKey || !colKey) {
      grid.innerHTML = '<div class="sap-pivot-msg">Choose both row and column dimensions.</div>';
      return;
    }
    if (rowKey === colKey) {
      grid.innerHTML = '<div class="sap-pivot-msg">Row and column must be different fields.</div>';
      return;
    }
    if (!valKey) {
      grid.innerHTML = '<div class="sap-pivot-msg">Choose a values column.</div>';
      return;
    }
    var rows = lastRun.rows;
    var cellMap = {};
    var rowSet = {};
    var colSet = {};
    rows.forEach(function (r) {
      var rk = r[rowKey] == null ? '' : String(r[rowKey]);
      var ck = r[colKey] == null ? '' : String(r[colKey]);
      rowSet[rk] = true;
      colSet[ck] = true;
      var key = rk + '\0' + ck;
      if (!cellMap[key]) {
        cellMap[key] = { sum: 0, n: 0, rc: 0, min: Infinity, max: -Infinity };
      }
      var o = cellMap[key];
      o.rc++;
      var vn = parsePivotNum(r[valKey]);
      if (!isNaN(vn)) {
        o.sum += vn;
        o.n++;
        o.min = Math.min(o.min, vn);
        o.max = Math.max(o.max, vn);
      }
    });
    function cellVal(o) {
      if (!o || o.rc === 0) return '';
      if (agg === 'COUNT') return String(o.rc);
      if (o.n === 0) return '';
      switch (agg) {
        case 'SUM':
          return String(o.sum);
        case 'AVG':
          return String(Math.round((o.sum / o.n) * 1e6) / 1e6);
        case 'MIN':
          return o.min === Infinity ? '' : String(o.min);
        case 'MAX':
          return o.max === -Infinity ? '' : String(o.max);
        default:
          return String(o.sum);
      }
    }
    var rowLabels = Object.keys(rowSet).sort();
    var colLabels = Object.keys(colSet).sort();
    if (rowLabels.length > PIVOT_MAX_DIM || colLabels.length > PIVOT_MAX_DIM) {
      grid.innerHTML =
        '<div class="sap-pivot-msg">Too many unique row/column keys (' +
        rowLabels.length +
        ' × ' +
        colLabels.length +
        '). Narrow filters or dates (display limit ' +
        PIVOT_MAX_DIM +
        ' per axis).</div>';
      return;
    }
    var table = document.createElement('table');
    table.className = 'sap-pivot-table';
    var thead = document.createElement('thead');
    var hr = document.createElement('tr');
    var th0 = document.createElement('th');
    th0.textContent = rowKey + ' \\ ' + colKey;
    hr.appendChild(th0);
    colLabels.forEach(function (cl) {
      var th = document.createElement('th');
      th.textContent = cl === '' ? '(blank)' : cl;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    var tbody = document.createElement('tbody');
    rowLabels.forEach(function (rl) {
      var tr = document.createElement('tr');
      var td0 = document.createElement('td');
      td0.textContent = rl === '' ? '(blank)' : rl;
      tr.appendChild(td0);
      colLabels.forEach(function (cl) {
        var td = document.createElement('td');
        td.textContent = cellVal(cellMap[rl + '\0' + cl]);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    grid.innerHTML = '';
    grid.appendChild(table);
  }

  function exportCsv() {
    if (!lastRun || !lastRun.columns || !lastRun.rows || !lastRun.rows.length) return;
    var cols = lastRun.columns;
    var labels = lastRun.column_labels || cols;
    function escCell(v) {
      var s = v == null ? '' : String(v);
      if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
      return s;
    }
    var lines = [labels.map(escCell).join(',')];
    lastRun.rows.forEach(function (row) {
      lines.push(
        cols.map(function (c) {
          return escCell(row[c]);
        }).join(',')
      );
    });
    var blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'salesanalysis_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function wireResize() {
    var handle = $('saResizeHandle');
    var panel = $('saResultsPanel');
    var page = document.querySelector('.air-page');
    if (!handle || !panel || !page) return;
    handle.addEventListener('mousedown', function (e) {
      saResizing = true;
      e.preventDefault();
    });
    document.addEventListener('mousemove', function (e) {
      if (!saResizing) return;
      var rect = page.getBoundingClientRect();
      var h = rect.bottom - e.clientY;
      h = Math.max(80, Math.min(rect.height * 0.65, h));
      panel.style.height = h + 'px';
      panel.style.flexShrink = '0';
    });
    document.addEventListener('mouseup', function () {
      saResizing = false;
    });
  }

  function syncAiButtons() {
    var genBtn = $('saAiGenerateBtn');
    var previewBtn = $('saAiPreviewBtn');
    if (!genBtn || !previewBtn) return;
    var dis = aiBusy || !catalogReady;
    genBtn.disabled = dis;
    previewBtn.disabled = dis;
  }

  function loadCatalog() {
    catalogReady = false;
    syncAiButtons();
    showCatalogErr('');
    urls = readUrls();
    var colHost = $('saColList');
    if (colHost) {
      colHost.innerHTML =
        '<div style="padding:14px;color:#94a3b8;font-size:.78rem;text-align:center;">Loading…</div>';
    }

    if (!urls || !urls.columns) {
      showCatalogErr('Missing columns API URL. Reload the page.');
      return;
    }

    fetch(urls.columns, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.success) {
          showCatalogErr(data.error || 'Could not load columns.');
          if (colHost) {
            colHost.innerHTML =
              '<div style="padding:14px;color:#f38ba8;font-size:.78rem;text-align:center;">Failed</div>';
          }
          return;
        }
        maxColumns = data.max_columns || 48;
        catalogDefaults = data.defaults || [];
        groups = data.groups || [];
        filterAliases = data.filter_aliases || [];
        columnsByAlias = data.columns_by_alias || {};
        indexCatalog(groups);
        var cfgBadge = $('saCfgBadge');
        if (cfgBadge) {
          cfgBadge.textContent = data.column_allowlist_active
            ? 'Configured catalog'
            : 'Full discovery';
          cfgBadge.title = data.column_allowlist_active
            ? 'Only columns saved under Data configuration are listed.'
            : 'All safe columns from detected tables are available.';
        }
        filterRows = [];
        filterSeq = 0;
        renderFilterList();
        syncOrderTblOptions();
        syncOrderColOptions();
        renderAvailCols();
        applyDefaults();
        catalogReady = true;
        syncAiButtons();
      })
      .catch(function () {
        catalogReady = false;
        syncAiButtons();
        showCatalogErr('Could not load columns.');
      });
  }

  function applyAiReportOptions(opts) {
    if (!opts || typeof opts !== 'object') return;
    var dfEl = $('saDateFrom');
    var dtEl = $('saDateTo');
    if (opts.date_from && dfEl) dfEl.value = opts.date_from;
    if (opts.date_to && dtEl) dtEl.value = opts.date_to;
    if (Array.isArray(opts.filters) && opts.filters.length) {
      filterRows = [];
      filterSeq = 0;
      opts.filters.forEach(function (f) {
        if (!f || !f.column) return;
        filterSeq++;
        var alias = String(f.alias || '').trim();
        if (!filterAliases.some(function (a) { return a.key === alias; })) {
          alias = (filterAliases[0] && filterAliases[0].key) || 'h';
        }
        filterRows.push({
          id: filterSeq,
          alias: alias,
          column: String(f.column),
          operator: String(f.operator || '='),
          value: f.value != null ? String(f.value) : '',
        });
      });
      renderFilterList();
    }
    var ob = opts.order_by;
    if (ob && ob.alias && ob.column) {
      var ot = $('saOrderTbl');
      if (
        ot &&
        filterAliases.some(function (a) {
          return a.key === ob.alias;
        })
      ) {
        ot.value = ob.alias;
        syncOrderColOptions();
        var oc = $('saOrderCol');
        var od = $('saOrderDir');
        if (oc) {
          var cols = columnsByAlias[ob.alias] || [];
          if (cols.indexOf(ob.column) !== -1) oc.value = ob.column;
        }
        if (od && ob.direction) od.value = ob.direction;
      }
    }
  }

  function applyAiColumns(ids) {
    selectedOrder = [];
    var src =
      ids && ids.length ? ids.slice() : (catalogDefaults || []).slice();
    src.forEach(function (id) {
      var sid = id == null ? '' : String(id).trim();
      if (!sid || selectionHas(sid)) return;
      if (selectedOrder.length >= maxColumns) return;
      selectedOrder.push({
        id: sid,
        label: labelById[sid] || sid,
        groupKey: groupKeyForColumnId(sid),
      });
    });
  }

  function setAiStatus(msg, isErr) {
    var el = $('saAiStatus');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('err', !!isErr);
  }

  function formatAiReply(j) {
    var lines = [];
    if (j.notes) lines.push(j.notes);
    var opts = j.report_options && typeof j.report_options === 'object' ? j.report_options : null;
    if (opts) {
      lines.push('');
      lines.push('Dates: ' + opts.date_from + ' → ' + opts.date_to);
      var nf = (opts.filters || []).length;
      if (nf) lines.push('Extra filters: ' + nf);
      if (opts.order_by)
        lines.push(
          'Order: ' +
            opts.order_by.alias +
            '.' +
            opts.order_by.column +
            ' ' +
            (opts.order_by.direction || '')
        );
    }
    var ids = Array.isArray(j.column_ids) ? j.column_ids : [];
    if (ids.length) {
      lines.push('');
      lines.push('Columns (' + ids.length + '):');
      ids.forEach(function (id, ix) {
        lines.push(String(ix + 1) + '. ' + id + ' — ' + (labelById[id] || id));
      });
    } else {
      lines.push('');
      lines.push('(No AI column match — defaults applied where available.)');
    }
    return lines.join('\n');
  }

  function applyAiPayload(j) {
    saAiLastIds = Array.isArray(j.column_ids) ? j.column_ids.slice() : [];
    saAiReportOpts =
      j.report_options && typeof j.report_options === 'object' ? j.report_options : null;
    applyAiReportOptions(saAiReportOpts);
    applyAiColumns(saAiLastIds);
    renderAvailCols();
    renderFieldList();
    syncOrderColOptions();
    setRunEnabled();
    updateBadges();
  }

  function requestAiSuggest(prompt) {
    var u = urls && urls.ai_suggest;
    if (!u) {
      return Promise.resolve({
        fetchErr: null,
        ok: false,
        status: 0,
        json: null,
        text: '',
      });
    }
    return fetch(u, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt }),
    })
      .then(function (r) {
        return r.text().then(function (text) {
          var j = null;
          if (text) {
            try {
              j = JSON.parse(text);
            } catch (ignore) {}
          }
          return {
            fetchErr: null,
            ok: r.ok,
            status: r.status,
            json: j,
            text: text,
          };
        });
      })
      .catch(function (e) {
        var msg = e && e.message ? String(e.message) : 'Connection failed';
        return {
          fetchErr: msg,
          ok: false,
          status: 0,
          json: null,
          text: '',
        };
      });
  }

  function interpretAiSuggestResult(res) {
    if (res.fetchErr) {
      var fe = res.fetchErr;
      var human =
        /failed to fetch|networkerror|load failed|network request failed/i.test(fe)
          ? 'Could not reach the server — connection interrupted, timeout, or blocked. Open DevTools → Network, retry Generate, and inspect POST …/analysis-ai-suggest (VPN, HTTPS, reverse-proxy timeouts).'
          : 'Request failed: ' + fe;
      return { ok: false, statusLine: human, reply: human };
    }
    var j = res.json;
    if (!res.ok) {
      var serverErr = j && typeof j.error === 'string' && j.error ? j.error : '';
      var fallback =
        res.status === 401
          ? 'Not logged in — reload the page and sign in again.'
          : res.status === 403
            ? 'Forbidden — your role may lack AI Reports permissions, or session expired.'
            : res.status === 502
              ? 'Bad gateway — server/proxy gave up (often OpenAI call timeout). Retry or ask ops to raise worker/proxy timeouts.'
              : res.status === 503
                ? 'Server unavailable — e.g. OPENAI_API_KEY missing or backend overloaded.'
                : 'HTTP ' + (res.status || '?');
      var line = serverErr || fallback;
      return { ok: false, statusLine: line, reply: line };
    }
    if (!j || typeof j.success === 'undefined') {
      var clip = (res.text || '').replace(/\s+/g, ' ').trim().slice(0, 420);
      var hint =
        clip ||
        'Expected JSON from AI endpoint — got HTML or empty body (check reverse proxy / route URL).';
      return {
        ok: false,
        statusLine: 'Invalid response from server (HTTP ' + (res.status || '?') + ').',
        reply: hint,
      };
    }
    if (!j.success) {
      var er = j.error || 'Suggestion failed.';
      return { ok: false, statusLine: er, reply: er };
    }
    return { ok: true, data: j };
  }

  function wireAiReports() {
    var genBtn = $('saAiGenerateBtn');
    var previewBtn = $('saAiPreviewBtn');
    var replyEl = $('saAiReply');
    var promptEl = $('saAiPrompt');
    if (!genBtn || !previewBtn || !replyEl) return;

    function checkPrompt() {
      var prompt = ((promptEl && promptEl.value) || '').trim();
      if (prompt.length < 3) {
        replyEl.textContent = 'Type at least 3 characters describing the report you want.';
        setAiStatus('', false);
        return '';
      }
      return prompt;
    }

    genBtn.addEventListener('click', function () {
      replyEl.textContent = '';
      saAiLastIds = [];
      saAiReportOpts = null;
      var prompt = checkPrompt();
      if (!prompt) return;
      if (!catalogReady) {
        setAiStatus('Still loading catalog…', true);
        return;
      }
      if (!(urls && urls.ai_suggest)) {
        setAiStatus('AI URL missing — reload the page.', true);
        replyEl.textContent = 'AI URL missing — reload the page.';
        return;
      }
      aiBusy = true;
      syncAiButtons();
      setAiStatus('Asking AI…');
      requestAiSuggest(prompt)
        .then(function (res) {
          var interp = interpretAiSuggestResult(res);
          if (!interp.ok) {
            setAiStatus(interp.statusLine, true);
            replyEl.textContent = interp.reply;
            return Promise.reject({ handled: true });
          }
          var j = interp.data;
          applyAiPayload(j);
          replyEl.textContent = formatAiReply(j);
          setAiStatus('Running report…');
          return runReport();
        })
        .then(function (ranOk) {
          aiBusy = false;
          syncAiButtons();
          if (ranOk === true) setAiStatus('Report ready — see Results below.');
          else if (ranOk === false) setAiStatus('Report finished with errors — check Results.', true);
        })
        .catch(function (err) {
          aiBusy = false;
          syncAiButtons();
          if (err && err.handled) return;
          var detail =
            err && err.message ? String(err.message) : 'Unexpected error — check browser console.';
          setAiStatus(detail, true);
          replyEl.textContent = detail;
        });
    });

    previewBtn.addEventListener('click', function () {
      replyEl.textContent = '';
      saAiLastIds = [];
      saAiReportOpts = null;
      var prompt = checkPrompt();
      if (!prompt) return;
      if (!catalogReady) {
        setAiStatus('Still loading catalog…', true);
        return;
      }
      if (!(urls && urls.ai_suggest)) {
        setAiStatus('AI URL missing — reload the page.', true);
        replyEl.textContent = 'AI URL missing — reload the page.';
        return;
      }
      aiBusy = true;
      syncAiButtons();
      setAiStatus('Asking AI…');
      requestAiSuggest(prompt)
        .then(function (res) {
          var interp = interpretAiSuggestResult(res);
          if (!interp.ok) {
            setAiStatus(interp.statusLine, true);
            replyEl.textContent = interp.reply;
            return;
          }
          applyAiPayload(interp.data);
          replyEl.textContent = formatAiReply(interp.data);
          setAiStatus('Setup applied — expand Advanced to tweak, then Run report.');
        })
        .catch(function (err) {
          var detail =
            err && err.message ? String(err.message) : 'Unexpected error — check browser console.';
          setAiStatus(detail, true);
          replyEl.textContent = detail;
        })
        .then(function () {
          aiBusy = false;
          syncAiButtons();
        });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    loadCatalog();

    var cs = $('saColSearch');
    if (cs) cs.addEventListener('input', renderAvailCols);

    var rb = $('saRunBtn');
    if (rb) rb.addEventListener('click', runReport);
    var eb = $('saExportBtn');
    if (eb) eb.addEventListener('click', exportCsv);

    var af = $('saAddFilterBtn');
    if (af) af.addEventListener('click', addFilterRow);
    var ot = $('saOrderTbl');
    if (ot) ot.addEventListener('change', syncOrderColOptions);

    var cb = $('saClearBtn');
    if (cb) {
      cb.addEventListener('click', function () {
        selectedOrder = [];
        lastRun = null;
        saAiLastIds = [];
        saAiReportOpts = null;
        aiBusy = false;
        syncAiButtons();
        var ar = $('saAiReply');
        if (ar) ar.textContent = '';
        setAiStatus('');
        filterRows = [];
        filterSeq = 0;
        renderFilterList();
        syncOrderColOptions();
        renderAvailCols();
        renderFieldList();
        showResultErr('');
        var rc = $('saResultCount');
        if (rc) rc.textContent = '';
        var rbod = $('saResultBody');
        if (rbod) {
          rbod.innerHTML =
            '<div class="sl-no-result"><span style="font-size:2rem;">&#128202;</span>Generate a report or expand Advanced and run manually</div>';
        }
        var pg = $('saPivotGrid');
        if (pg) {
          pg.innerHTML =
            '<div class="sap-pivot-msg">Run a report first. Then choose row/column dimensions and a value column.</div>';
        }
        ;['saPivotRow', 'saPivotCol', 'saPivotVal'].forEach(function (pid) {
          var el = $(pid);
          if (el) el.innerHTML = '<option value="">— Pick column —</option>';
        });
        switchResultView('table');
        updateBadges();
      });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || !e.ctrlKey) return;
      if (e.target && e.target.id === 'saAiPrompt') {
        e.preventDefault();
        var gb = $('saAiGenerateBtn');
        if (gb && !gb.disabled) gb.click();
        return;
      }
      var tag = e.target && e.target.tagName;
      if (tag === 'TEXTAREA' || tag === 'SELECT') return;
      var rb = $('saRunBtn');
      if (!rb || rb.disabled) return;
      e.preventDefault();
      runReport();
    });

    wireResize();

    var trt = $('saTabResultTable');
    var trp = $('saTabResultPivot');
    if (trt) trt.addEventListener('click', function () { switchResultView('table'); });
    if (trp)
      trp.addEventListener('click', function () {
        switchResultView('pivot');
      });
    var pa = $('saPivotApply');
    if (pa) pa.addEventListener('click', renderPivotMatrix);

    document.querySelectorAll('[data-air-prompt]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var p = btn.getAttribute('data-air-prompt');
        var ta = $('saAiPrompt');
        if (ta && p) ta.value = p;
      });
    });

    wireAiReports();
  });
})();
