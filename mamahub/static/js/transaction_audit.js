/**
 * Transaction accounts audit — GL vouchers & affected accounts (all sources).
 */
(function () {
  'use strict';

  const page = document.getElementById('taPage');
  if (!page) return;

  const apiList = page.dataset.apiList || '/accounts/api/transaction-audit/vouchers';
  const apiDetail = page.dataset.apiDetail || '/accounts/api/transaction-audit/detail';
  const exportBase = page.dataset.exportUrl || '/accounts/transaction-audit/export.csv';
  const voucherViewTpl = page.dataset.voucherView || '';

  const form = document.getElementById('taFilterForm');
  const tbody = document.getElementById('taTableBody');
  const scrollStatus = document.getElementById('taScrollStatus');
  const listMeta = document.getElementById('taListMeta');
  const msgEl = document.getElementById('taMessage');
  const btnExport = document.getElementById('taBtnExport');
  const sourceSel = document.getElementById('taSource');
  const drawer = document.getElementById('taPreviewDrawer');
  const drawerClose = document.getElementById('taPreviewClose');
  const openVoucherLink = document.getElementById('taOpenVoucherLink');

  let loading = false;
  let lastRows = [];
  let selectedIdx = -1;
  let detailCache = {};

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function fmt2(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toFixed(2);
  }

  function statusLabel(st) {
    if (st === 'err') return 'Unbalanced';
    if (st === 'warn') return 'Review';
    return 'OK';
  }

  function statusClass(st) {
    if (st === 'err') return 'co-status co-status--err';
    if (st === 'warn') return 'co-status co-status--warn';
    return 'co-status co-status--ok';
  }

  function rowClass(st) {
    if (st === 'err') return 'ta-row ta-row--err';
    return 'ta-row';
  }

  function voucherViewUrl(vno) {
    if (!voucherViewTpl || !vno) return '#';
    return voucherViewTpl.replace('__VNO__', encodeURIComponent(vno));
  }

  function filterParams() {
    const p = new URLSearchParams();
    const src = sourceSel ? sourceSel.value : 'ALL';
    const df = document.getElementById('taDateFrom').value;
    const dtTo = document.getElementById('taDateTo').value;
    const q = document.getElementById('taSearch').value.trim();
    const ub = document.getElementById('taUnbalanced').checked;
    if (src && src !== 'ALL') p.set('source', src);
    if (df) p.set('date_from', df);
    if (dtTo) p.set('date_to', dtTo);
    if (q) p.set('search', q);
    if (ub) p.set('unbalanced', '1');
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
    document.getElementById('taKpiTotal').textContent = s.total != null ? String(s.total) : '—';
    document.getElementById('taKpiOk').textContent = s.ok != null ? String(s.ok) : '—';
    document.getElementById('taKpiErr').textContent = s.err != null ? String(s.err) : '—';
    document.getElementById('taKpiTotalSub').textContent = (s.warn || 0) > 0 ? `${s.warn} need review` : 'Listed';
  }

  function populateSources(sources) {
    if (!sourceSel || !sources || !sources.length) return;
    const cur = sourceSel.value;
    sourceSel.innerHTML = sources.map(function (o) {
      return '<option value="' + escapeHtml(o.value) + '">' + escapeHtml(o.label) + '</option>';
    }).join('');
    if (cur) sourceSel.value = cur;
  }

  function renderTable(rows) {
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:#6b7280;">No vouchers match filters.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(function (r, idx) {
      const st = r.balanced === false ? 'err' : (r.status || 'ok');
      const docLbl = (r.doc_type && r.doc_no) ? (r.doc_type + ' ' + r.doc_no) : '—';
      return '<tr class="' + rowClass(st) + (selectedIdx === idx ? ' is-selected' : '') + '" data-idx="' + idx + '">'
        + '<td>' + (idx + 1) + '</td>'
        + '<td><strong>' + escapeHtml(r.voucher_no) + '</strong></td>'
        + '<td>' + escapeHtml(r.voucher_date || '') + '</td>'
        + '<td>' + escapeHtml(r.source_label || r.source || '') + '</td>'
        + '<td>' + escapeHtml(docLbl) + '</td>'
        + '<td class="num">' + fmt2(r.total_debit) + '</td>'
        + '<td class="num">' + fmt2(r.total_credit) + '</td>'
        + '<td><span class="' + statusClass(st) + '">' + statusLabel(st) + '</span></td>'
        + '</tr>';
    }).join('');
  }

  function setActiveTab(panel) {
    document.querySelectorAll('.ta-tab').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.panel === panel);
    });
    ['summary', 'accounts', 'gl', 'staging', 'issues'].forEach(function (p) {
      const el = document.getElementById('taPanel' + p.charAt(0).toUpperCase() + p.slice(1));
      if (el) el.classList.toggle('is-active', p === panel);
    });
  }

  function renderDetail(data) {
    const gl = data.gl || {};
    const sum = data.summary || {};
    const lines = gl.lines || [];
    const acc = data.accounts_affected || [];
    const staging = data.staging_lines || [];
    const issues = data.issues || [];
    const vno = data.voucher_no || '';

    document.getElementById('taPreviewTitle').textContent = vno;
    document.getElementById('taPreviewSubtitle').textContent = [
      data.source_label || data.source || '',
      gl.voucher_date || '',
      gl.reference_no ? 'Ref: ' + gl.reference_no : '',
    ].filter(Boolean).join(' · ');

    if (openVoucherLink) {
      openVoucherLink.href = voucherViewUrl(vno);
    }

    document.getElementById('taPanelSummary').innerHTML = ''
      + '<p><strong>Narration:</strong> ' + escapeHtml(gl.narration || '—') + '</p>'
      + '<p><strong>Created by:</strong> ' + escapeHtml(gl.created_by || '—') + '</p>'
      + '<p><strong>Lines:</strong> ' + (sum.line_count || lines.length) + ' · '
      + '<strong>Accounts:</strong> ' + (sum.account_count || acc.length) + '</p>'
      + '<p><strong>Total debit:</strong> ' + fmt2(sum.total_debit) + ' · '
      + '<strong>Total credit:</strong> ' + fmt2(sum.total_credit) + '</p>'
      + '<p><strong>Balanced:</strong> ' + (sum.balanced ? 'Yes' : 'No') + '</p>';

    document.getElementById('taPanelAccounts').innerHTML = acc.length
      ? acc.map(function (a) {
        return '<span class="ta-acc-chip">' + escapeHtml(a.account_code) + ' — ' + escapeHtml(a.account_name) + '</span>';
      }).join('')
      : '<p style="color:#64748b;">No account lines.</p>';

    let glHtml = '<table class="ta-mini-table"><thead><tr><th>#</th><th>Account</th><th class="num">Dr</th><th class="num">Cr</th><th>Remarks</th></tr></thead><tbody>';
    lines.forEach(function (ln) {
      glHtml += '<tr><td>' + escapeHtml(ln.line_no) + '</td>'
        + '<td>' + escapeHtml(ln.account_code) + '<br><small>' + escapeHtml(ln.account_name) + '</small></td>'
        + '<td class="num">' + fmt2(ln.debit) + '</td>'
        + '<td class="num">' + fmt2(ln.credit) + '</td>'
        + '<td>' + escapeHtml(ln.remarks) + '</td></tr>';
    });
    glHtml += '</tbody></table>';
    document.getElementById('taPanelGl').innerHTML = glHtml;

    if (staging.length) {
      let stHtml = '<table class="ta-mini-table"><thead><tr><th>Account</th><th class="num">Dr</th><th class="num">Cr</th><th>Narration</th></tr></thead><tbody>';
      staging.forEach(function (ln) {
        stHtml += '<tr><td>' + escapeHtml(ln.account_code) + '</td>'
          + '<td class="num">' + fmt2(ln.debit) + '</td>'
          + '<td class="num">' + fmt2(ln.credit) + '</td>'
          + '<td>' + escapeHtml(ln.narration) + '</td></tr>';
      });
      stHtml += '</tbody></table>';
      document.getElementById('taPanelStaging').innerHTML = '<p><em>GRN/PR posting staging table</em></p>' + stHtml;
    } else {
      document.getElementById('taPanelStaging').innerHTML = '<p style="color:#64748b;">No staging posting lines (not GRN/PR or not stored in TBL*POSTING).</p>';
    }

    if (issues.length) {
      document.getElementById('taPanelIssues').innerHTML = '<ul class="sv-preview-issues" style="list-style:disc;padding-left:18px;">'
        + issues.map(function (i) {
          return '<li>[' + escapeHtml(i.severity || '') + '] ' + escapeHtml(i.message) + '</li>';
        }).join('') + '</ul>';
    } else {
      document.getElementById('taPanelIssues').innerHTML = '<p style="color:#166534;">No issues detected.</p>';
    }

    if (drawer) drawer.classList.add('has-row');
    setActiveTab('summary');
  }

  function loadDetail(row) {
    const vno = row.voucher_no;
    if (!vno) return;
    if (detailCache[vno]) {
      renderDetail(detailCache[vno]);
      return;
    }
    const p = new URLSearchParams({ voucher_no: vno });
    fetch(apiDetail + '?' + p.toString(), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) {
          showBanner((data && data.error) || 'Detail load failed.', true);
          return;
        }
        detailCache[vno] = data;
        renderDetail(data);
      })
      .catch(function (e) {
        showBanner(String(e), true);
      });
  }

  function runScan() {
    if (loading) return;
    loading = true;
    showBanner('');
    if (scrollStatus) scrollStatus.textContent = 'Loading…';
    updateExportLink();
    const qs = filterParams().toString();
    fetch(apiList + (qs ? '?' + qs : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        loading = false;
        if (!data || !data.success) {
          showBanner((data && data.error) || 'Load failed.', true);
          if (scrollStatus) scrollStatus.textContent = 'Error.';
          return;
        }
        if (data.sources) populateSources(data.sources);
        lastRows = data.rows || [];
        selectedIdx = -1;
        detailCache = {};
        if (drawer) drawer.classList.remove('has-row');
        renderTable(lastRows);
        setKpis(data.summary);
        if (listMeta) listMeta.textContent = lastRows.length + ' voucher(s)';
        if (scrollStatus) scrollStatus.textContent = 'Loaded ' + lastRows.length + ' voucher(s). Click a row for account detail.';
      })
      .catch(function (e) {
        loading = false;
        showBanner(String(e), true);
        if (scrollStatus) scrollStatus.textContent = 'Error.';
      });
  }

  if (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      runScan();
    });
  }
  document.getElementById('taBtnRunTop')?.addEventListener('click', runScan);

  if (tbody) {
    tbody.addEventListener('click', function (ev) {
      const tr = ev.target.closest('tr.ta-row');
      if (!tr) return;
      const idx = parseInt(tr.dataset.idx, 10);
      if (!Number.isFinite(idx) || !lastRows[idx]) return;
      selectedIdx = idx;
      renderTable(lastRows);
      loadDetail(lastRows[idx]);
    });
  }

  document.querySelectorAll('.ta-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setActiveTab(btn.dataset.panel || 'summary');
    });
  });

  if (drawerClose) {
    drawerClose.addEventListener('click', function () {
      selectedIdx = -1;
      if (drawer) drawer.classList.remove('has-row');
      renderTable(lastRows);
    });
  }

  const today = new Date();
  const ago = new Date(today);
  ago.setDate(ago.getDate() - 30);
  const df = document.getElementById('taDateFrom');
  const dt = document.getElementById('taDateTo');
  if (df && !df.value) df.value = ago.toISOString().slice(0, 10);
  if (dt && !dt.value) dt.value = today.toISOString().slice(0, 10);
  updateExportLink();
})();
