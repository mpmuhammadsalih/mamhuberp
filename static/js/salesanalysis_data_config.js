/**
 * Salesanalysis data configuration — 3-panel: drawer / selected columns / calculations.
 */
(function () {
  'use strict';

  var urls = {};
  var state = {
    resolved: {},
    sources: {},
    dbObjects: [],
    drawerCols: {},
    drawerFilter: '',
    selectedFields: [],
    calculations: [],
    expandedTbls: {},
    dragReorderIdx: null,
    calcFocusKey: null,
  };

  var SOURCE_ROLES = ['hdr', 'dtl', 'im', 'cust', 'sch'];

  var SRC_LABELS = {
    hdr: 'Bill header',
    dtl: 'Bill detail',
    im: 'Item master',
    cust: 'Customer',
    sch: 'Sales channel dict',
  };

  function $(id) {
    return document.getElementById(id);
  }

  function readUrls() {
    var el = $('sdcUrls');
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return {};
    }
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /** Safe for double-quoted HTML attributes (JSON quotes must use this, not escapeHtml). */
  function escapeAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;');
  }

  function columnNameFromRow(col) {
    if (!col || typeof col !== 'object') return '';
    return (
      col.name ||
      col.NAME ||
      col.column_name ||
      col.COLUMN_NAME ||
      col.Column_Name ||
      ''
    );
  }

  /** Read chip identity from data-* (avoids broken data-payload HTML when JSON contains "). */
  function readChipTriple(chip) {
    var rk = (chip.getAttribute('data-role-key') || '').trim();
    var col = (chip.getAttribute('data-column') || '').trim();
    var tbl = (chip.getAttribute('data-table') || '').trim();
    return { role_key: rk, column: col, table: tbl };
  }

  function chipMarkup(tblName, colRow, roleKey) {
    var nm = columnNameFromRow(colRow);
    if (!nm) return '';
    var tnEsc = escapeHtml(tblName);
    return (
      '<div class="sdc-drag-chip" draggable="true" data-table="' +
      escapeAttr(tblName) +
      '" data-column="' +
      escapeAttr(nm) +
      '" data-role-key="' +
      escapeAttr(roleKey) +
      '"><small>' +
      escapeHtml(roleKey) +
      '</small>' +
      tnEsc +
      '.' +
      escapeHtml(nm) +
      '<span class="sdc-chip-plus" aria-hidden="true">+</span></div>'
    );
  }

  function showMsg(ok, text) {
    var el = $('sdcMsg');
    if (!el) return;
    el.style.display = text ? 'block' : 'none';
    el.className = 'sdc-msg ' + (ok ? 'ok' : 'err');
    el.textContent = text || '';
  }

  /** Blocks UI while Apply is in progress; disables Apply / Reload. */
  function setApplyBusy(active, opts) {
    opts = opts || {};
    var ov = $('sdcApplyOverlay');
    var spin = $('sdcApplyOverlaySpinner');
    var tx = $('sdcApplyOverlayText');
    var sub = $('sdcApplyOverlaySub');
    var btnSave = $('sdcSaveBtn');
    var btnReload = $('sdcReloadBtn');
    if (!ov) return;
    if (active) {
      ov.removeAttribute('hidden');
      ov.setAttribute('aria-hidden', 'false');
      document.documentElement.style.overflow = 'hidden';
      if (spin) spin.style.display = opts.hideSpinner ? 'none' : '';
      if (tx) tx.textContent = opts.title || 'Applying to Salesanalysis…';
      if (sub) {
        sub.textContent = opts.sub || 'Saving your configuration. Please wait.';
        sub.style.display = opts.hideSub ? 'none' : '';
      }
      if (btnSave) btnSave.disabled = true;
      if (btnReload) btnReload.disabled = true;
    } else {
      ov.setAttribute('hidden', '');
      ov.setAttribute('aria-hidden', 'true');
      document.documentElement.style.overflow = '';
      if (btnSave) btnSave.disabled = false;
      if (btnReload) btnReload.disabled = false;
      if (spin) spin.style.display = '';
      if (sub) {
        sub.style.display = '';
      }
    }
  }

  function newCalcKey() {
    return 'c' + Date.now() + '_' + Math.floor(Math.random() * 1e9);
  }

  function renderAdvInputs() {
    var grid = $('sdcAdvGrid');
    if (!grid) return;
    var src = state.sources || {};
    var html = '';
    SOURCE_ROLES.forEach(function (rk) {
      var pkg = src[rk] || {};
      html += '<div class="sdc-src-field">';
      html += '<label for="sdc_src_' + rk + '">' + escapeHtml(SRC_LABELS[rk] || rk) + ' · override</label>';
      html +=
        '<input type="text" id="sdc_src_' +
        rk +
        '" placeholder="auto-detected" value="' +
        escapeHtml(pkg.object_name || '') +
        '" autocomplete="off" /></div>';
      html += '<div class="sdc-src-field"><label for="sdc_kind_' + rk + '">Kind</label>';
      html +=
        '<select id="sdc_kind_' +
        rk +
        '"><option value="TABLE"' +
        ((pkg.object_kind || '').toUpperCase() === 'VIEW' ? '' : ' selected') +
        '>TABLE</option><option value="VIEW"' +
        ((pkg.object_kind || '').toUpperCase() === 'VIEW' ? ' selected' : '') +
        '>VIEW</option></select></div>';
    });
    grid.innerHTML = html;
  }

  function collectSourcesPayload() {
    var sources = {};
    SOURCE_ROLES.forEach(function (rk) {
      var nmEl = document.getElementById('sdc_src_' + rk);
      var kdEl = document.getElementById('sdc_kind_' + rk);
      sources[rk] = {
        object_name: nmEl ? nmEl.value.trim() : '',
        object_kind: kdEl ? kdEl.value : 'TABLE',
      };
    });
    return sources;
  }

  /** Roles tied to a physical table name for Salesanalysis joins. */
  function rolesForPhysicalTable(tableName) {
    var r = state.resolved || {};
    var tu = String(tableName || '').toUpperCase();
    var roles = [];
    function eq(a, b) {
      return a && b && String(a).toUpperCase() === String(b).toUpperCase();
    }
    if (eq(r.hdr_tbl, tu)) roles.push('hdr');
    if (eq(r.dtl_tbl, tu)) roles.push('dtl');
    if (r.im_tbl && eq(r.im_tbl, tu)) roles.push('im');
    if (r.customer_tbl && eq(r.customer_tbl, tu)) roles.push('cust');
    if (r.sch_tbl && eq(r.sch_tbl, tu)) {
      return ['sch_hdr', 'sch_cust'];
    }
    return roles;
  }

  function tableLinked(tblName) {
    return rolesForPhysicalTable(tblName).length > 0;
  }

  function drawerFilteredObjects() {
    var q = (state.drawerFilter || '').trim().toUpperCase();
    var items = state.dbObjects || [];
    if (!q) return items.slice();
    return items.filter(function (it) {
      return String(it.name || '').toUpperCase().indexOf(q) >= 0;
    });
  }

  function fetchCols(tbl, cb) {
    var cacheKey = String(tbl || '').toUpperCase();
    if (state.drawerCols[cacheKey]) {
      cb(null, state.drawerCols[cacheKey]);
      return;
    }
    if (!urls.columns) {
      cb('missing url');
      return;
    }
    var u =
      urls.columns +
      (urls.columns.indexOf('?') >= 0 ? '&' : '?') +
      'table=' +
      encodeURIComponent(cacheKey);
    fetch(u, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d.success || !d.columns) {
          cb(d.error || 'columns failed');
          return;
        }
        state.drawerCols[cacheKey] = d.columns;
        cb(null, d.columns);
      })
      .catch(function () {
        cb('network');
      });
  }

  /** Legacy: JSON blob if present (older markup). */
  function parseChipPayloadJson(chip) {
    var raw = chip.getAttribute('data-payload');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch (e1) {
      try {
        var tex = document.createElement('textarea');
        tex.innerHTML = raw;
        return JSON.parse(tex.value);
      } catch (e2) {
        return null;
      }
    }
  }

  function applyChipPayload(chip) {
    var t = readChipTriple(chip);
    if (t.role_key && t.column) {
      addSelectedField(t.role_key, t.column, t.table);
      return;
    }
    var p = parseChipPayloadJson(chip);
    if (p && p.role_key && p.column) addSelectedField(p.role_key, p.column, p.table);
  }

  function renderDrawerChips(tblName, columns, rolesHint) {
    var chips = '';
    if (!rolesHint.length) {
      chips +=
        '<div style="padding:8px;font-size:.72rem;color:#94a3b8;">Not linked to Salesanalysis joins · choose detected tables only.</div>';
      return chips;
    }
    if (rolesHint.length === 2 && rolesHint[0] === 'sch_hdr' && rolesHint[1] === 'sch_cust') {
      chips += '<div class="sdc-subhd">Sales channel · header alias</div>';
      columns.forEach(function (col) {
        chips += chipMarkup(tblName, col, 'sch_hdr');
      });
      chips += '<div class="sdc-subhd">Sales channel · customer alias</div>';
      columns.forEach(function (col) {
        chips += chipMarkup(tblName, col, 'sch_cust');
      });
      return chips;
    }
    var rk = rolesHint[0];
    columns.forEach(function (col) {
      chips += chipMarkup(tblName, col, rk);
    });
    return chips;
  }

  function drawAccordion(tblIt) {
    var tblName = tblIt.name || '';
    var isOpen = !!state.expandedTbls[tblName.toUpperCase()];
    var rolesHint = rolesForPhysicalTable(tblName);
    var linked = rolesHint.length > 0;
    var orphanCls = linked ? '' : ' sdc-orphan';
    var html = '';
    html +=
      '<div class="sdc-tbl-acc' +
      (isOpen ? ' open' : '') +
      orphanCls +
      '" data-table="' +
      escapeAttr(tblName) +
      '">';
    html +=
      '<div class="sdc-tbl-head"><span>' +
      escapeHtml(tblName) +
      '</span><span class="sdc-tbl-meta">' +
      escapeHtml(tblIt.type || tblIt.obj_type || '') +
      '</span></div>';
    html += '<div class="sdc-tbl-body">';
    if (state.drawerCols[tblName.toUpperCase()]) {
      html += renderDrawerChips(tblName, state.drawerCols[tblName.toUpperCase()], rolesHint);
    } else if (isOpen) {
      html += '<div style="padding:8px;color:#64748b;font-size:.74rem;">Loading columns…</div>';
    }
    html += '</div></div>';
    return html;
  }

  function renderDrawer() {
    var scroll = $('sdcDrawerScroll');
    if (!scroll) return;
    var items = drawerFilteredObjects();
    if (!items.length) {
      scroll.innerHTML = '<div class="sdc-drop-hint">No tables/views visible · expand USER_OBJECTS access.</div>';
      return;
    }
    items.sort(function (a, b) {
      var na = String(a.name || '');
      var nb = String(b.name || '');
      var la = tableLinked(na);
      var lb = tableLinked(nb);
      if (la !== lb) return la ? -1 : 1;
      return na.localeCompare(nb);
    });
    scroll.innerHTML = items.map(drawAccordion).join('');
    scroll.querySelectorAll('.sdc-tbl-head').forEach(function (head) {
      head.addEventListener('click', function () {
        var acc = head.closest('.sdc-tbl-acc');
        if (!acc) return;
        var tn = acc.getAttribute('data-table');
        var uk = String(tn || '').toUpperCase();
        state.expandedTbls[uk] = !state.expandedTbls[uk];
        acc.classList.toggle('open', !!state.expandedTbls[uk]);
        if (state.expandedTbls[uk] && !state.drawerCols[uk]) {
          fetchCols(tn, function (_err, cols) {
            var body = acc.querySelector('.sdc-tbl-body');
            if (!body) return;
            var rh = rolesForPhysicalTable(tn);
            body.innerHTML = renderDrawerChips(tn, cols || [], rh);
            bindChipInteractions(body);
          });
        }
      });
    });
    bindChipInteractions(scroll);
  }

  function bindChipInteractions(host) {
    if (!host) return;
    host.querySelectorAll('.sdc-drag-chip[draggable="true"]').forEach(function (chip) {
      chip.setAttribute('role', 'button');
      chip.setAttribute('tabindex', '0');
      chip.setAttribute(
        'title',
        'Click to add to Selected columns, or drag into the panel on the right',
      );

      chip.addEventListener('dragstart', function (e) {
        var t = readChipTriple(chip);
        if (!t.role_key || !t.column || !e.dataTransfer) return;
        var raw = JSON.stringify({
          table: t.table,
          column: t.column,
          role_key: t.role_key,
        });
        e.dataTransfer.setData('application/json', raw);
        e.dataTransfer.setData('text/plain', raw);
        e.dataTransfer.effectAllowed = 'copy';
      });

      chip.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        applyChipPayload(chip);
      });

      chip.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          applyChipPayload(chip);
        }
      });
    });
  }

  function addSelectedField(role_key, column_name, _table_name) {
    var cn = String(column_name || '').toUpperCase();
    var rk = String(role_key || '').trim().toLowerCase();
    if (!rk || !cn) return;
    var dup = state.selectedFields.some(function (x) {
      return x.role_key === rk && String(x.column_name).toUpperCase() === cn;
    });
    if (dup) return;
    state.selectedFields.push({
      role_key: rk,
      column_name: cn,
      display_label: '',
    });
    renderSelectedPanel();
    renderCalculations();
  }

  function renderSelectedPanel() {
    var list = $('sdcSelectedList');
    var hint = $('sdcSelectedHint');
    if (!list || !hint) return;
    if (!state.selectedFields.length) {
      list.innerHTML = '';
      hint.style.display = 'block';
      return;
    }
    hint.style.display = 'none';
    list.innerHTML = state.selectedFields
      .map(function (row, idx) {
        var refTok = '@' + row.role_key + ':' + row.column_name + '@';
        return (
          '<div class="sdc-sel-row" draggable="true" data-sel-idx="' +
          idx +
          '">' +
          '<span class="sdc-handle" title="Drag to reorder">⠿</span>' +
          '<div class="sdc-field-main">' +
          '<div><span class="sdc-role-tag">' +
          escapeHtml(row.role_key) +
          '</span> · <span class="sdc-col-name">' +
          escapeHtml(row.column_name) +
          '</span></div>' +
          '<div style="font-size:.62rem;color:#94a3b8;margin-top:2px;">Token: <code>' +
          escapeHtml(refTok) +
          '</code></div>' +
          '<input type="text" class="sdc-inp-alias sdc-alias-inp" data-sel-idx="' +
          idx +
          '" placeholder="Optional label (alias)" value="' +
          escapeHtml(row.display_label || '') +
          '" /></div>' +
          '<button type="button" class="sdc-rm" data-del-idx="' +
          idx +
          '">✕</button></div>'
        );
      })
      .join('');

    list.querySelectorAll('.sdc-alias-inp').forEach(function (inp) {
      inp.addEventListener('input', function () {
        var i = parseInt(inp.getAttribute('data-sel-idx'), 10);
        if (!isNaN(i) && state.selectedFields[i]) {
          state.selectedFields[i].display_label = inp.value;
        }
      });
    });
    list.querySelectorAll('[data-del-idx]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var i = parseInt(btn.getAttribute('data-del-idx'), 10);
        if (!isNaN(i)) {
          state.selectedFields.splice(i, 1);
          renderSelectedPanel();
          renderCalculations();
        }
      });
    });
    list.querySelectorAll('.sdc-sel-row[draggable="true"]').forEach(function (row) {
      row.addEventListener('dragstart', function (e) {
        state.dragReorderIdx = parseInt(row.getAttribute('data-sel-idx'), 10);
        if (e.dataTransfer) {
          e.dataTransfer.setData('application/x-sdc-reorder', String(state.dragReorderIdx));
          e.dataTransfer.effectAllowed = 'move';
        }
      });
      row.addEventListener('dragover', function (e) {
        e.preventDefault();
        if (!e.dataTransfer) return;
        /* Drawer chips use JSON; row reorder uses x-sdc-reorder */
        var types = e.dataTransfer.types || [];
        var i,
          hasJson = false,
          hasReorder = false;
        for (i = 0; i < types.length; i++) {
          if (types[i] === 'application/json' || types[i] === 'text/plain') hasJson = true;
          if (types[i] === 'application/x-sdc-reorder') hasReorder = true;
        }
        e.dataTransfer.dropEffect = hasJson && !hasReorder ? 'copy' : 'move';
      });
      row.addEventListener('drop', function (e) {
        e.preventDefault();
        var raw =
          (e.dataTransfer && e.dataTransfer.getData('application/json')) ||
          (e.dataTransfer && e.dataTransfer.getData('text/plain')) ||
          '';
        if (raw) {
          try {
            var p = JSON.parse(raw);
            if (p.role_key && p.column) {
              addSelectedField(p.role_key, p.column, p.table);
              return;
            }
          } catch (err1) {
            void err1;
          }
        }
        var fromStr = e.dataTransfer ? e.dataTransfer.getData('application/x-sdc-reorder') : '';
        var from = parseInt(fromStr, 10);
        var to = parseInt(row.getAttribute('data-sel-idx'), 10);
        if (isNaN(from) || isNaN(to)) return;
        if (from === to) return;
        var item = state.selectedFields.splice(from, 1)[0];
        state.selectedFields.splice(to, 0, item);
        renderSelectedPanel();
      });
    });
  }

  function refOptionsHtml() {
    if (!state.selectedFields.length) {
      return '<option value="">— Add columns to panel 2 first —</option>';
    }
    var opts =
      '<option value="">Insert reference…</option>' +
      state.selectedFields
        .map(function (r) {
          var tok = '@' + r.role_key + ':' + r.column_name + '@';
          return '<option value="' + escapeHtml(tok) + '">' + escapeHtml(tok + ' ' + (r.display_label || '')) + '</option>';
        })
        .join('');
    return opts;
  }

  function insertIntoCalcExpr(calcKey, chunk) {
    var selEsc = String(calcKey).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    var sel = 'textarea[data-calc-key="' + selEsc + '"]';
    state.calculations.forEach(function (c) {
      if (String(c.calc_key) !== String(calcKey)) return;
      var ta = document.querySelector(sel);
      if (ta) {
        var start = ta.selectionStart || 0;
        var end = ta.selectionEnd || 0;
        var v = ta.value || '';
        ta.value = v.slice(0, start) + chunk + v.slice(end);
        c.expression = ta.value;
        ta.focus();
        ta.selectionStart = ta.selectionEnd = start + chunk.length;
      } else {
        c.expression = (c.expression || '') + chunk;
      }
    });
    renderCalculations();
    var ta2 = document.querySelector(sel);
    if (ta2) ta2.focus();
  }

  function renderCalculations() {
    var host = $('sdcCalcList');
    if (!host) return;
    if (!state.calculations.length) {
      host.innerHTML = '<div class="sdc-drop-hint" style="padding:10px;">No calculations (optional) · use + Add calculation when you need formulas.</div>';
      return;
    }
    host.innerHTML = state.calculations
      .map(function (c) {
        var ckRaw = String(c.calc_key || '').replace(/"/g, '');
        var ckAttr = ckRaw;
        return (
          '<div class="sdc-calc-row">' +
          '<div class="sdc-field-main">' +
          '<label style="font-size:.62rem;color:#64748b;font-weight:700;">OUTPUT NAME</label>' +
          '<input type="text" class="sdc-inp-alias sdc-calc-alias" data-calc-key="' +
          ckAttr +
          '" value="' +
          escapeHtml(c.output_alias || '') +
          '" placeholder="e.g. LINE_TOTAL" />' +
          '<label style="font-size:.62rem;color:#64748b;font-weight:700;margin-top:6px;display:block;">EXPRESSION</label>' +
          '<textarea class="sdc-ta-expr" data-calc-key="' +
          ckAttr +
          '" placeholder="@dtl:QTY@ * @dtl:RATE@">' +
          escapeHtml(c.expression || '') +
          '</textarea>' +
          '<div class="sdc-calc-tools">' +
          '<select class="sdc-ref-sel" data-calc-key="' +
          ckAttr +
          '" aria-label="Insert reference">' +
          refOptionsHtml() +
          '</select>' +
          '<button type="button" class="sdc-mini" data-ins-op="' +
          ckAttr +
          '" data-chunk="+">+</button>' +
          '<button type="button" class="sdc-mini" data-ins-op="' +
          ckAttr +
          '" data-chunk="-">−</button>' +
          '<button type="button" class="sdc-mini" data-ins-op="' +
          ckAttr +
          '" data-chunk="*">×</button>' +
          '<button type="button" class="sdc-mini" data-ins-op="' +
          ckAttr +
          '" data-chunk="/">/</button>' +
          '<button type="button" class="sdc-mini" data-ins-op="' +
          ckAttr +
          '" data-chunk="(">(</button>' +
          '<button type="button" class="sdc-mini" data-ins-op="' +
          ckAttr +
          '" data-chunk=")">)</button>' +
          '</div></div>' +
          '<button type="button" class="sdc-rm" data-del-calc="' +
          ckAttr +
          '">✕</button></div>'
        );
      })
      .join('');

    host.querySelectorAll('.sdc-calc-alias').forEach(function (inp) {
      inp.addEventListener('input', function () {
        var k = inp.getAttribute('data-calc-key');
        state.calculations.forEach(function (c) {
          if (String(c.calc_key) === String(k)) c.output_alias = inp.value;
        });
      });
    });
    host.querySelectorAll('textarea.sdc-ta-expr').forEach(function (ta) {
      ta.addEventListener('input', function () {
        var k = ta.getAttribute('data-calc-key');
        state.calculations.forEach(function (c) {
          if (String(c.calc_key) === String(k)) c.expression = ta.value;
        });
      });
      ta.addEventListener('focus', function () {
        state.calcFocusKey = ta.getAttribute('data-calc-key');
      });
    });
    host.querySelectorAll('.sdc-ref-sel').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var k = sel.getAttribute('data-calc-key');
        var v = sel.value;
        sel.selectedIndex = 0;
        if (v && k) insertIntoCalcExpr(k, v);
      });
    });
    host.querySelectorAll('[data-ins-op]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var k = btn.getAttribute('data-ins-op');
        var chunk = btn.getAttribute('data-chunk') || '';
        if (k) insertIntoCalcExpr(k, chunk);
      });
    });
    host.querySelectorAll('[data-del-calc]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var k = btn.getAttribute('data-del-calc');
        state.calculations = state.calculations.filter(function (c) {
          return String(c.calc_key) !== String(k);
        });
        renderCalculations();
      });
    });
  }

  function wireDropZones() {
    var zone = $('sdcSelectedDrop');
    if (!zone) return;

    function allowDrop(e) {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      zone.classList.add('sdc-drag-hover');
    }

    /* capture: drop does not bubble — listen before inner targets (hint, list, rows) */
    zone.addEventListener('dragenter', allowDrop, true);
    zone.addEventListener('dragover', allowDrop, true);

    zone.addEventListener(
      'dragleave',
      function (e) {
        var rel = e.relatedTarget;
        if (rel && zone.contains(rel)) return;
        zone.classList.remove('sdc-drag-hover');
      },
      true,
    );

    zone.addEventListener(
      'drop',
      function (e) {
        var raw =
          (e.dataTransfer && e.dataTransfer.getData('application/json')) ||
          (e.dataTransfer && e.dataTransfer.getData('text/plain')) ||
          '';
        if (!raw) return;
        e.preventDefault();
        e.stopPropagation();
        zone.classList.remove('sdc-drag-hover');
        try {
          var p = JSON.parse(raw);
          if (p.role_key && p.column) addSelectedField(p.role_key, p.column, p.table);
        } catch (err) {
          void err;
        }
      },
      true,
    );
  }

  function collectPayload() {
    var selected_fields = state.selectedFields.map(function (r, i) {
      return {
        role_key: r.role_key,
        column_name: r.column_name,
        display_label: r.display_label || '',
        sort_ord: i,
      };
    });
    var calculations = state.calculations
      .filter(function (c) {
        return (
          String(c.calc_key || '').trim() &&
          String(c.output_alias || '').trim() &&
          String(c.expression || '').trim()
        );
      })
      .map(function (c, i) {
        return {
          calc_key: c.calc_key,
          output_alias: c.output_alias || '',
          expression: c.expression || '',
          sort_ord: i,
        };
      });
    return {
      sources: collectSourcesPayload(),
      selected_fields: selected_fields,
      calculations: calculations,
    };
  }

  function ingestServer(d) {
    state.resolved = d.resolved || {};
    state.sources = d.sources || {};
    renderAdvInputs();

    state.selectedFields = (d.selected_fields || []).map(function (sf) {
      return {
        role_key: String(sf.role_key || '').toLowerCase(),
        column_name: String(sf.column_name || '').toUpperCase(),
        display_label: String(sf.display_label || ''),
      };
    });
    if (!state.selectedFields.length && d.columns_saved) {
      var cs = d.columns_saved || {};
      ['hdr', 'dtl', 'im', 'cust', 'sch_hdr', 'sch_cust'].forEach(function (rk) {
        var lst = cs[rk] || [];
        lst.forEach(function (cn) {
          state.selectedFields.push({
            role_key: rk,
            column_name: String(cn || '').toUpperCase(),
            display_label: '',
          });
        });
      });
    }

    state.calculations = (d.calculations || []).map(function (c) {
      return {
        calc_key: String(c.calc_key || newCalcKey()),
        output_alias: String(c.output_alias || ''),
        expression: String(c.expression || ''),
      };
    });
    renderSelectedPanel();
    renderCalculations();
  }

  function loadDrawerCatalog() {
    if (!urls.objects) return;
    fetch(urls.objects, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d.success || !d.items) {
          $('sdcDrawerScroll').innerHTML =
            '<div class="sdc-msg err">' + escapeHtml(d.error || 'Could not load objects') + '</div>';
          return;
        }
        state.dbObjects = d.items || [];
        renderDrawer();
      })
      .catch(function () {
        $('sdcDrawerScroll').innerHTML = '<div class="sdc-msg err">Network error loading tables.</div>';
      });
  }

  function configUrlWithTenant() {
    var cfgUrl = urls.config;
    if (!cfgUrl || typeof window.APP_DBKEY === 'undefined') return cfgUrl;
    var sep = cfgUrl.indexOf('?') >= 0 ? '&' : '?';
    return (
      cfgUrl +
      sep +
      'dbkey=' +
      encodeURIComponent(window.APP_DBKEY || '') +
      '&locationcode=' +
      encodeURIComponent(
        String(
          window.APP_LOCATION_CODE !== undefined && window.APP_LOCATION_CODE !== null
            ? window.APP_LOCATION_CODE
            : '',
        ),
      )
    );
  }

  function load() {
    showMsg(true, '');
    var cfg = configUrlWithTenant();
    if (!cfg) return;
    fetch(cfg, { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (!d.success) {
          showMsg(false, d.error || 'Failed to load');
          return;
        }
        ingestServer(d);
        loadDrawerCatalog();
      })
      .catch(function () {
        showMsg(false, 'Network error');
      });
  }

  function save() {
    var cfgUrl = configUrlWithTenant();
    if (!cfgUrl) {
      window.alert('Cannot apply: configuration is missing. Reload the page and try again.');
      return;
    }
    showMsg(true, '');
    setApplyBusy(true, {
      title: 'Applying to Salesanalysis…',
      sub: 'Saving your columns and settings to the database.',
    });
    fetch(cfgUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectPayload()),
    })
      .then(function (r) {
        var ct = (r.headers && r.headers.get && r.headers.get('Content-Type')) || '';
        if ((ct || '').indexOf('application/json') >= 0) {
          return r.json().then(function (j) {
            return { ok: r.ok, json: j || {}, status: r.status };
          });
        }
        return r.text().then(function (t) {
          return {
            ok: r.ok,
            json: {
              success: false,
              error: t ? t.slice(0, 400) : 'HTTP ' + r.status + ' (non-JSON response)',
            },
            status: r.status,
          };
        });
      })
      .then(function (res) {
        setApplyBusy(false);
        if (!res.ok || !res.json || !res.json.success) {
          var msg =
            (res.json && res.json.error) ||
            ('Save failed' + (res.status ? ' (' + res.status + ')' : ''));
          showMsg(false, msg);
          window.alert('Apply to Salesanalysis failed:\n\n' + msg);
          return;
        }
        showMsg(true, 'Saved. Salesanalysis will use these columns and calculations.');
        load();
      })
      .catch(function (err) {
        setApplyBusy(false);
        var msg = err && err.message ? err.message : 'Network error';
        showMsg(false, msg);
        window.alert('Apply to Salesanalysis failed:\n\n' + msg);
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    urls = readUrls();
    renderAdvInputs();
    wireDropZones();
    $('sdcDrawerSearch').addEventListener('input', function () {
      state.drawerFilter = $('sdcDrawerSearch').value || '';
      renderDrawer();
    });
    $('sdcSaveBtn').addEventListener('click', save);
    $('sdcReloadBtn').addEventListener('click', load);
    $('sdcAddCalcBtn').addEventListener('click', function () {
      state.calculations.push({
        calc_key: newCalcKey(),
        output_alias: '',
        expression: '',
      });
      renderCalculations();
    });
    load();
  });
})();
