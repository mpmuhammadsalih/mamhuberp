/**
 * Purchase verification — GRN & Purchase Return audit UI.
 */
(function () {
  'use strict';

  const page = document.getElementById('pvPage');
  if (!page) return;

  const apiList = page.dataset.apiList || '/purchase/api/verification/documents';
  const apiDetail = page.dataset.apiDetail || '/purchase/api/verification/detail';
  const exportBase = page.dataset.exportUrl || '/purchase/verification/export.csv';
  const grnQueryTpl = page.dataset.grnQuery || '';

  const form = document.getElementById('pvFilterForm');
  const tbody = document.getElementById('pvTableBody');
  const scrollStatus = document.getElementById('pvScrollStatus');
  const listMeta = document.getElementById('pvListMeta');
  const msgEl = document.getElementById('pvMessage');
  const btnExport = document.getElementById('pvBtnExport');
  const drawer = document.getElementById('pvPreviewDrawer');
  const drawerClose = document.getElementById('pvPreviewClose');
  const openDocLink = document.getElementById('pvOpenDocLink');

  let loading = false;
  let lastRows = [];
  let selectedIdx = -1;
  let detailCache = {};

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function fmt3(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toFixed(3);
  }

  function fmt2(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toFixed(2);
  }

  function statusLabel(st) {
    if (st === 'err') return 'Error';
    if (st === 'warn') return 'Review';
    return 'OK';
  }

  function statusClass(st) {
    if (st === 'err') return 'co-status co-status--err';
    if (st === 'warn') return 'co-status co-status--warn';
    return 'co-status co-status--ok';
  }

  function rowClass(st) {
    if (st === 'err') return 'pv-row pv-row--err';
    if (st === 'warn') return 'pv-row pv-row--warn';
    return 'pv-row';
  }

  function filterParams() {
    const p = new URLSearchParams();
    const dt = document.getElementById('pvDocType').value;
    const df = document.getElementById('pvDateFrom').value;
    const dtTo = document.getElementById('pvDateTo').value;
    const q = document.getElementById('pvSearch').value.trim();
    const mm = document.getElementById('pvMismatch').checked;
    if (dt) p.set('doc_type', dt);
    if (df) p.set('date_from', df);
    if (dtTo) p.set('date_to', dtTo);
    if (q) p.set('search', q);
    if (mm) p.set('mismatch', '1');
    return p;
  }

  function updateExportLink() {
    const qs = filterParams().toString();
    if (btnExport) btnExport.href = qs ? `${exportBase}?${qs}` : exportBase;
  }

  function showBanner(text, isError) {
    if (!msgEl) return;
    if (!text) {
      msgEl.style.display = 'none';
      msgEl.textContent = '';
      return;
    }
    msgEl.style.display = 'block';
    msgEl.className = isError ? 'sv-scroll-status is-error' : 'sv-scroll-status';
    msgEl.textContent = text;
  }

  function setKpis(summary) {
    const s = summary || {};
    document.getElementById('pvKpiTotal').textContent = s.total != null ? String(s.total) : '—';
    document.getElementById('pvKpiOk').textContent = s.ok != null ? String(s.ok) : '—';
    document.getElementById('pvKpiErr').textContent = s.err != null ? String(s.err) : '—';
    document.getElementById('pvKpiTotalSub').textContent = (s.warn || 0) > 0 ? `${s.warn} need review` : 'Scanned';
  }

  function renderTable(rows) {
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:20px;color:#6b7280;">No documents match filters.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (r, idx) {
      const st = r.status || 'ok';
      return '<tr class="' + rowClass(st) + (selectedIdx === idx ? ' is-selected' : '') + '" data-idx="' + idx + '">'
        + '<td>' + (idx + 1) + '</td>'
        + '<td>' + escapeHtml(r.doc_type) + '</td>'
        + '<td><strong>' + escapeHtml(r.doc_no) + '</strong></td>'
        + '<td>' + escapeHtml(r.doc_date || '') + '</td>'
        + '<td>' + escapeHtml(r.suppliercode || '') + '</td>'
        + '<td class="num">' + fmt2(r.amount) + '</td>'
        + '<td>' + escapeHtml(r.reference || '') + '</td>'
        + '<td><span class="' + statusClass(st) + '">' + statusLabel(st) + '</span></td>'
        + '<td style="font-size:11px;color:#b91c1c;">' + escapeHtml(r.issue_summary || (r.issue_count ? r.issue_count + ' issue(s)' : '')) + '</td>'
        + '</tr>';
    }).join('');
    tbody.querySelectorAll('tr.pv-row').forEach(function (tr) {
      tr.addEventListener('click', function () {
        const idx = parseInt(tr.getAttribute('data-idx'), 10);
        selectRow(idx);
      });
    });
  }

  function docOpenUrl(row) {
    if (!row) return '#';
    if (row.doc_type === 'GRN' && grnQueryTpl) {
      return grnQueryTpl.replace(/999999999/, String(row.doc_no));
    }
    return '#';
  }

  function activatePanel(name) {
    document.querySelectorAll('.pv-tab').forEach(function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-panel') === name);
    });
    document.querySelectorAll('.pv-panel').forEach(function (p) {
      p.classList.toggle('is-active', p.id === 'pvPanel' + name.charAt(0).toUpperCase() + name.slice(1));
    });
  }

  document.querySelectorAll('.pv-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      activatePanel(btn.getAttribute('data-panel'));
    });
  });

  function renderDetail(d) {
    if (!d) return;
    const hdr = d.header || {};
    const sum = d.summary || {};
    document.getElementById('pvPreviewTitle').textContent = (d.doc_type || '') + ' #' + (d.doc_no || '');
    document.getElementById('pvPreviewSubtitle').textContent = (hdr.receiptdate || hdr.returndate || '') + ' · Supplier ' + (hdr.suppliercode || '—');

    document.getElementById('pvPanelSummary').innerHTML =
      '<p><span class="' + statusClass(d.status) + '">' + statusLabel(d.status) + '</span></p>'
      + '<p>Lines: <strong>' + (sum.line_count || 0) + '</strong> · Journal rows: <strong>' + (sum.journal_count || 0) + '</strong></p>'
      + '<p>Issues: <strong>' + (sum.issue_count || 0) + '</strong> (' + (sum.error_count || 0) + ' errors, ' + (sum.warn_count || 0) + ' warnings)</p>';

    const lines = d.lines || [];
    let linesHtml = '<table class="pv-mini-table"><thead><tr><th>#</th><th>Item</th><th class="num">Base qty</th><th class="num">Rate</th><th class="num">Landing</th><th>FOC</th></tr></thead><tbody>';
    lines.forEach(function (ln) {
      linesHtml += '<tr><td>' + escapeHtml(ln.lineno) + '</td><td>' + escapeHtml(ln.itemcode) + '</td>'
        + '<td class="num">' + fmt3(ln.baseqty) + '</td><td class="num">' + fmt2(ln.rate) + '</td>'
        + '<td class="num">' + fmt3(ln.landingcost) + '</td><td>' + (ln.foc ? 'Y' : '') + '</td></tr>';
    });
    linesHtml += '</tbody></table>';
    document.getElementById('pvPanelLines').innerHTML = linesHtml || '<p>No lines.</p>';

    const audits = d.item_audits || [];
    let costHtml = '<p class="pv-cost-hint" style="font-size:12px;color:#64748b;margin:0 0 8px;">Stock before = on-hand qty when GRN was posted (saved on receipt line). Negative usually means sales ran before goods were received.</p>';
    costHtml += '<table class="pv-mini-table"><thead><tr><th>Item</th><th class="num">Stock before</th><th class="num">Receipt qty</th><th class="num">Stock now</th><th class="num">Prev avg</th><th class="num">Expected avg</th><th class="num">Current avg</th></tr></thead><tbody>';
    audits.forEach(function (a) {
      const sb = a.stock_before_receipt;
      const sbNum = sb != null && sb !== '' ? Number(sb) : null;
      const sbTitle = a.stock_before_from_snapshot
        ? 'Recorded when this GRN was posted'
        : (a.stock_before_derived != null ? ('Estimated: stock now − receipt qty (' + fmt3(a.stock_before_derived) + ')') : '');
      const sbStyle = sbNum != null && sbNum < -0.0005 ? ' color:#b45309;font-weight:600;' : '';
      costHtml += '<tr><td>' + escapeHtml(a.itemcode) + '</td>'
        + '<td class="num"' + (sbTitle ? ' title="' + escapeHtml(sbTitle) + '"' : '') + ' style="' + sbStyle + '">'
        + fmt3(sb != null ? sb : '—') + '</td>'
        + '<td class="num">' + fmt3(a.receipt_base_qty != null ? a.receipt_base_qty : a.return_base_qty) + '</td>'
        + '<td class="num">' + fmt3(a.stock_after_receipt != null ? a.stock_after_receipt : a.current_stock) + '</td>'
        + '<td class="num">' + fmt3(a.previous_avgcost) + '</td>'
        + '<td class="num">' + fmt3(a.expected_avgcost) + '</td>'
        + '<td class="num">' + fmt3(a.current_avgcost) + '</td></tr>';
    });
    costHtml += '</tbody></table>';
    document.getElementById('pvPanelCost').innerHTML = costHtml || '<p>No item cost audit.</p>';

    const journal = d.journal || [];
    let jHtml = '<table class="pv-mini-table"><thead><tr><th>#</th><th>Item</th><th class="num">Qty</th><th class="num">Rate</th><th>WH</th><th>Batch</th></tr></thead><tbody>';
    journal.forEach(function (j) {
      jHtml += '<tr><td>' + escapeHtml(j.lineno) + '</td><td>' + escapeHtml(j.itemcode) + '</td>'
        + '<td class="num">' + fmt3(j.qty) + '</td><td class="num">' + fmt2(j.rate) + '</td>'
        + '<td>' + escapeHtml(j.warehouse_id || '') + '</td><td>' + escapeHtml(j.batch_no || '') + '</td></tr>';
    });
    jHtml += '</tbody></table>';
    document.getElementById('pvPanelJournal').innerHTML = jHtml || '<p>No journal rows.</p>';

    const issues = d.issues || [];
    if (issues.length) {
      document.getElementById('pvPanelIssues').innerHTML = '<ul class="sv-preview-issues" style="background:#fef2f2;padding:10px 10px 10px 24px;">'
        + issues.map(function (i) {
          return '<li><strong>' + escapeHtml(i.code) + '</strong>: ' + escapeHtml(i.message) + '</li>';
        }).join('') + '</ul>';
    } else {
      document.getElementById('pvPanelIssues').innerHTML = '<p style="color:#16a34a;">No issues detected.</p>';
    }

    activatePanel('summary');
  }

  function selectRow(idx) {
    if (idx < 0 || idx >= lastRows.length) return;
    selectedIdx = idx;
    renderTable(lastRows);
    const row = lastRows[idx];
    if (drawer) drawer.classList.add('has-row');
    if (openDocLink) {
      openDocLink.href = docOpenUrl(row);
      openDocLink.style.display = row.doc_type === 'GRN' ? '' : 'none';
    }
    const cacheKey = row.doc_type + ':' + row.doc_no;
    if (detailCache[cacheKey]) {
      renderDetail(detailCache[cacheKey]);
      return;
    }
    document.getElementById('pvPreviewTitle').textContent = 'Loading…';
    const p = new URLSearchParams({ doc_type: row.doc_type, doc_no: String(row.doc_no) });
    fetch(apiDetail + '?' + p.toString(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || d.success === false) {
          showBanner((d && d.error) || 'Could not load detail.', true);
          return;
        }
        detailCache[cacheKey] = d;
        renderDetail(d);
      })
      .catch(function () {
        showBanner('Network error loading document detail.', true);
      });
  }

  function loadList() {
    if (loading) return;
    loading = true;
    showBanner('');
    if (scrollStatus) scrollStatus.textContent = 'Loading…';
    detailCache = {};
    selectedIdx = -1;
    if (drawer) drawer.classList.remove('has-row');
    updateExportLink();

    const p = filterParams();
    fetch(apiList + '?' + p.toString(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        loading = false;
        if (!d || d.success === false) {
          showBanner((d && d.error) || 'Verification failed.', true);
          if (scrollStatus) scrollStatus.textContent = 'Error loading report.';
          return;
        }
        lastRows = d.rows || [];
        setKpis(d.summary);
        renderTable(lastRows);
        if (listMeta) listMeta.textContent = lastRows.length + ' document(s)';
        if (scrollStatus) scrollStatus.textContent = 'Loaded ' + lastRows.length + ' document(s). Click a row for full audit.';
      })
      .catch(function () {
        loading = false;
        showBanner('Network error.', true);
        if (scrollStatus) scrollStatus.textContent = 'Request failed.';
      });
  }

  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      loadList();
    });
  }
  ['pvBtnRun', 'pvBtnRunTop'].forEach(function (id) {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', function (e) { e.preventDefault(); loadList(); });
  });
  if (drawerClose) {
    drawerClose.addEventListener('click', function () {
      selectedIdx = -1;
      if (drawer) drawer.classList.remove('has-row');
      renderTable(lastRows);
    });
  }
  updateExportLink();
})();
