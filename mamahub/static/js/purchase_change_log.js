/**

 * Purchase change log — edited / deleted GRN, LPO, and purchase returns.

 */

(function () {

  'use strict';



  const page = document.getElementById('pclPage');

  if (!page) return;



  const apiList = page.dataset.apiList || '/purchase/api/change-log/list';

  const grnQueryTpl = page.dataset.grnQueryTpl || '';

  const lpoQueryTpl = page.dataset.lpoQueryTpl || '';

  const prQueryTpl = page.dataset.prQueryTpl || '';

  const prReqQueryTpl = page.dataset.prReqQueryTpl || '';



  const form = document.getElementById('pclFilterForm');

  const tbody = document.getElementById('pclTableBody');

  const listMeta = document.getElementById('pclListMeta');

  const scrollStatus = document.getElementById('pclScrollStatus');

  const msgEl = document.getElementById('pclMessage');

  const tabBtns = page.querySelectorAll('.po-tab[data-tab]');



  let activeTab = 'all';

  let loading = false;



  function escapeHtml(v) {

    return String(v ?? '').replace(/[&<>"']/g, (ch) => (

      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]

    ));

  }



  function docUrl(row) {

    const no = Number(row.doc_no) || 0;

    if (no <= 0) return '';

    const t = String(row.doc_type || '').toUpperCase();

    if (t === 'GRN' && grnQueryTpl) {

      return grnQueryTpl.replace('999999999', String(no));

    }

    if (t === 'LPO' && lpoQueryTpl) {

      return lpoQueryTpl.replace('999999999', String(no));

    }

    if (t === 'PR' && prQueryTpl) {

      return prQueryTpl.replace('999999999', String(no));

    }

    if (t === 'PR_REQ' && prReqQueryTpl) {

      return prReqQueryTpl.replace('999999999', String(no));

    }

    return '';

  }



  function actionLabel(action) {

    const a = String(action || '').toUpperCase();

    if (a === 'EDIT') return 'Edited';

    if (a === 'DELETE') return 'Deleted';

    if (a === 'CANCEL') return 'Canceled';

    if (a === 'POST_INVENTORY') return 'Inventory posted';

    return a || '—';

  }



  function actionClass(action) {

    const a = String(action || '').toUpperCase();

    if (a === 'EDIT' || a === 'POST_INVENTORY') return 'pcl-action pcl-action--edit';

    if (a === 'DELETE') return 'pcl-action pcl-action--delete';

    if (a === 'CANCEL') return 'pcl-action pcl-action--cancel';

    return 'pcl-action';

  }



  function docTypeLabel(t) {

    const u = String(t || '').toUpperCase();

    if (u === 'GRN') return 'GRN';

    if (u === 'LPO') return 'Purchase order';

    if (u === 'PR') return 'Purchase return';

    if (u === 'PR_REQ') return 'Return request';

    return u || '—';

  }



  function fmtVal(v) {

    if (v === null || v === undefined || v === '') return '—';

    if (typeof v === 'number') {

      return Number.isInteger(v) ? String(v) : Number(v).toFixed(3).replace(/\.?0+$/, '');

    }

    if (typeof v === 'object') return fmtLineSnap(v);

    return String(v);

  }



  function fmtLineSnap(ln) {

    if (!ln || typeof ln !== 'object') return '—';

    const parts = [

      'Item ' + (ln.item || '—'),

      ln.uom ? ln.uom : null,

      ln.qty != null ? ('Qty ' + fmtVal(ln.qty)) : null,

      ln.rate != null ? ('Rate ' + fmtVal(ln.rate)) : null,

      ln.store ? ('Store ' + ln.store) : null,

      ln.lot_id ? ('Lot ' + ln.lot_id) : null,

    ].filter(Boolean);

    return parts.join(' · ');

  }



  function fieldLabel(change) {

    const fld = String(change.field || '');

    if (fld === 'line_added') return 'Line added';

    if (fld === 'line_removed') return 'Line removed';

    if (fld === 'qty') return 'Qty';

    if (fld === 'rate') return 'Rate';

    if (fld === 'amount') return 'Amount';

    if (fld === 'discount') return 'Discount';

    if (fld === 'store') return 'Store';

    if (fld === 'lot_id') return 'Lot';

    if (fld === 'uom') return 'UOM';

    return change.label || fld.replace(/_/g, ' ');

  }



  function renderChangeRow(change) {

    const label = escapeHtml(change.label || fieldLabel(change));

    const field = change.field && !/^line_/.test(String(change.field || '')) && change.scope === 'line'

      ? ' · ' + escapeHtml(fieldLabel(change))

      : '';

    return '<div class="pcl-change">'

      + '<span class="pcl-change-label">' + label + field + '</span>: '

      + '<span class="pcl-before">' + escapeHtml(fmtVal(change.before)) + '</span>'

      + '<span class="pcl-arrow">→</span>'

      + '<span class="pcl-after">' + escapeHtml(fmtVal(change.after)) + '</span>'

      + '</div>';

  }



  function renderSnapshotBox(title, snap) {

    if (!snap) return '<div class="pcl-snap-box"><div class="pcl-snap-title">' + escapeHtml(title) + '</div><div class="pcl-snap-line">—</div></div>';

    const hdr = snap.header || {};

    const lines = snap.lines || [];

    const hdrBits = Object.keys(hdr).map(function (k) {

      if (hdr[k] === null || hdr[k] === undefined || hdr[k] === '') return '';

      return escapeHtml(k.replace(/_/g, ' ') + ': ' + fmtVal(hdr[k]));

    }).filter(Boolean);

    const lineBits = lines.map(function (ln) {

      return '<div class="pcl-snap-line">' + escapeHtml(fmtLineSnap(ln)) + '</div>';

    }).join('');

    return '<div class="pcl-snap-box">'

      + '<div class="pcl-snap-title">' + escapeHtml(title) + '</div>'

      + (hdrBits.length ? ('<div class="pcl-snap-line">' + hdrBits.join(' · ') + '</div>') : '')

      + lineBits

      + '</div>';

  }



  function renderDetailCell(row, rowIdx) {

    const m = row.meta || {};

    const changes = Array.isArray(m.changes) ? m.changes : [];

    const remarks = String(row.remarks || '').trim();

    const parts = [];

    if (remarks) {

      parts.push('<div class="pcl-meta">' + escapeHtml(remarks) + '</div>');

    }

    if (changes.length) {

      parts.push('<div class="pcl-detail">' + changes.map(renderChangeRow).join('') + '</div>');

    } else {

      const summary = [];

      if (m.invoice_no) summary.push('Inv: ' + m.invoice_no);

      if (m.supplier_code) summary.push('Sup: ' + m.supplier_code);

      if (m.line_count != null) summary.push('Lines: ' + m.line_count);

      if (m.invoice_amount != null) summary.push('Amt: ' + Number(m.invoice_amount).toFixed(2));

      if (m.return_amount != null) summary.push('Amt: ' + Number(m.return_amount).toFixed(2));

      if (m.amount != null && m.return_amount == null && m.invoice_amount == null) {

        summary.push('Amt: ' + Number(m.amount).toFixed(2));

      }

      if (summary.length) {

        parts.push('<div class="pcl-meta">' + escapeHtml(summary.join(' · ')) + '</div>');

      } else if (!remarks) {

        parts.push('<span style="color:#94a3b8;">—</span>');

      }

    }

    if (m.before || m.after) {

      const panelId = 'pclSnap' + rowIdx;

      parts.push('<button type="button" class="pcl-snap-toggle" data-target="' + panelId + '">Show full before / after snapshot</button>');

      parts.push('<div class="pcl-snap-panel" id="' + panelId + '"><div class="pcl-snap-grid">'

        + renderSnapshotBox('Before', m.before)

        + renderSnapshotBox('After', m.after)

        + '</div></div>');

    }

    return parts.join('');

  }



  function setTab(tab) {

    activeTab = tab || 'all';

    tabBtns.forEach(function (btn) {

      btn.classList.toggle('active', btn.dataset.tab === activeTab);

    });

    loadList();

  }



  function filterParams() {

    const p = new URLSearchParams();

    p.set('action', activeTab);

    const dt = document.getElementById('pclDocType').value;

    const df = document.getElementById('pclDateFrom').value;

    const dtTo = document.getElementById('pclDateTo').value;

    const q = document.getElementById('pclSearch').value.trim();

    if (dt && dt !== 'all') p.set('doc_type', dt);

    if (df) p.set('date_from', df);

    if (dtTo) p.set('date_to', dtTo);

    if (q) p.set('search', q);

    p.set('limit', '200');

    return p;

  }



  function showMessage(text, isError) {

    if (!msgEl) return;

    if (!text) {

      msgEl.style.display = 'none';

      msgEl.textContent = '';

      msgEl.classList.remove('is-error');

      return;

    }

    msgEl.style.display = 'block';

    msgEl.textContent = text;

    msgEl.classList.toggle('is-error', !!isError);

  }



  function bindSnapshotToggles() {

    if (!tbody) return;

    tbody.querySelectorAll('.pcl-snap-toggle').forEach(function (btn) {

      btn.addEventListener('click', function () {

        const target = document.getElementById(btn.getAttribute('data-target') || '');

        if (!target) return;

        const open = target.classList.toggle('is-open');

        btn.textContent = open ? 'Hide full before / after snapshot' : 'Show full before / after snapshot';

      });

    });

  }



  function renderRows(rows, total) {

    if (!tbody) return;

    if (!rows.length) {

      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">No matching change log entries.</td></tr>';

      if (listMeta) listMeta.textContent = '0 records';

      if (scrollStatus) scrollStatus.textContent = 'No records for the current filters.';

      return;

    }

    const html = rows.map(function (row, idx) {

      const url = docUrl(row);

      const openCell = url

        ? '<a href="' + escapeHtml(url) + '" class="page-po__btn-secondary" style="padding:3px 8px;font-size:11px;">View</a>'

        : '<span style="color:#94a3b8;font-size:11px;">—</span>';

      const action = String(row.action || '').toUpperCase();

      const canOpen = url && action !== 'DELETE' && action !== 'CANCEL';

      return '<tr class="pcl-row">'

        + '<td style="text-align:center;">' + (idx + 1) + '</td>'

        + '<td>' + escapeHtml(row.action_at || '') + '</td>'

        + '<td><span class="' + actionClass(row.action) + '">' + escapeHtml(actionLabel(row.action)) + '</span></td>'

        + '<td>' + escapeHtml(docTypeLabel(row.doc_type)) + '</td>'

        + '<td><strong>' + escapeHtml(row.doc_no) + '</strong></td>'

        + '<td>' + escapeHtml(row.action_by || '') + '</td>'

        + '<td>' + renderDetailCell(row, idx) + '</td>'

        + '<td style="text-align:center;">' + (canOpen ? openCell : '<span style="color:#94a3b8;font-size:11px;" title="Document removed or canceled">N/A</span>') + '</td>'

        + '</tr>';

    }).join('');

    tbody.innerHTML = html;

    bindSnapshotToggles();

    if (listMeta) listMeta.textContent = rows.length + ' shown' + (total > rows.length ? ' of ' + total : '') + ' record' + (total === 1 ? '' : 's');

    if (scrollStatus) {

      scrollStatus.textContent = 'Branch ' + (page.dataset.location || '') + ' — newest changes first. Deleted or canceled documents cannot be reopened from here.';

    }

  }



  function loadList() {

    if (loading) return;

    loading = true;

    showMessage('');

    if (scrollStatus) scrollStatus.textContent = 'Loading…';

    const url = apiList + '?' + filterParams().toString();

    fetch(url, { credentials: 'same-origin' })

      .then(function (r) { return r.json(); })

      .then(function (d) {

        loading = false;

        if (!d || d.success !== true) {

          showMessage((d && d.error) ? String(d.error) : 'Could not load change log.', true);

          renderRows([], 0);

          return;

        }

        renderRows(d.rows || [], Number(d.total) || 0);

      })

      .catch(function () {

        loading = false;

        showMessage('Network error while loading change log.', true);

        renderRows([], 0);

      });

  }



  tabBtns.forEach(function (btn) {

    btn.addEventListener('click', function () {

      setTab(btn.dataset.tab || 'all');

    });

  });



  if (form) {

    form.addEventListener('submit', function (e) {

      e.preventDefault();

      loadList();

    });

  }



  const btnClear = document.getElementById('pclBtnClear');

  if (btnClear) {

    btnClear.addEventListener('click', function () {

      document.getElementById('pclDocType').value = 'all';

      document.getElementById('pclDateFrom').value = '';

      document.getElementById('pclDateTo').value = '';

      document.getElementById('pclSearch').value = '';

      setTab('all');

    });

  }



  const refreshBtn = page.querySelector('[data-list-refresh]');

  if (refreshBtn) {

    refreshBtn.addEventListener('click', function () { loadList(); });

  }



  loadList();

})();

