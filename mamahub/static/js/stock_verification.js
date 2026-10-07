/**
 * Stock verification — Item Master list-style UI with infinite scroll.
 */
(function () {
  'use strict';

  const page = document.getElementById('svPage');
  if (!page) return;

  const apiUrl = page.dataset.apiUrl || '/warehouse/api/stock-verification';
  const exportBase = page.dataset.exportUrl || '/warehouse/stock-verification/export.csv';

  const form = document.getElementById('svFilterForm');
  const tbody = document.getElementById('svTableBody');
  const scrollStatus = document.getElementById('svScrollStatus');
  const scrollSentinel = document.getElementById('svScrollSentinel');
  const listMeta = document.getElementById('svListMeta');
  const msgEl = document.getElementById('svMessage');
  const btnRun = document.getElementById('svBtnRun');
  const btnRunTop = document.getElementById('svBtnRunTop');
  const btnClear = document.getElementById('svBtnClear');
  const btnExport = document.getElementById('svBtnExport');
  const kpiRows = document.getElementById('svKpiRows');
  const kpiMismatch = document.getElementById('svKpiMismatch');
  const kpiScanned = document.getElementById('svKpiScanned');
  const kpiRowsSub = document.getElementById('svKpiRowsSub');
  const kpiScope = document.getElementById('svKpiScope');
  const pageSubtitle = document.getElementById('svPageSubtitle');
  const filterExtra = document.getElementById('svFilterExtra');
  const toggleFilters = document.getElementById('svToggleFilters');
  const drawer = document.getElementById('svPreviewDrawer');
  const drawerClose = document.getElementById('svPreviewClose');
  const warehouseHidden = document.getElementById('svWarehouse');
  const warehouseDisplay = document.getElementById('svWarehouseDisplay');
  const warehousePicker = document.getElementById('svWarehousePicker');
  const warehouseClear = document.getElementById('svWarehouseClear');
  const warehouseModal = document.getElementById('svWarehouseModal');
  const warehouseModalSearch = document.getElementById('svWarehouseModalSearch');
  const warehouseModalSearchClear = document.getElementById('svWarehouseModalSearchClear');
  const warehouseModalBody = document.getElementById('svWarehouseModalBody');
  const warehousePopupShell = document.querySelector('.sv-warehouse-popup');

  let warehouseList = [];
  try {
    const jsonEl = document.getElementById('svWarehousesJson');
    warehouseList = jsonEl ? JSON.parse(jsonEl.textContent || '[]') : [];
  } catch (e) {
    warehouseList = [];
  }

  function warehouseLabel(id) {
    if (!id) return '';
    const hit = warehouseList.find((w) => String(w.warehouse_id) === String(id));
    if (!hit) return String(id);
    const code = hit.warehouse_code || '';
    const name = hit.warehouse_name || '';
    return code && name ? `${code} — ${name}` : (code || name || String(id));
  }

  function syncWarehouseClear() {
    if (!warehouseClear) return;
    warehouseClear.style.display = warehouseHidden && warehouseHidden.value ? 'block' : 'none';
  }

  function setWarehouse(id, label) {
    if (warehouseHidden) warehouseHidden.value = id ? String(id) : '';
    if (warehouseDisplay) {
      warehouseDisplay.value = label || (id ? warehouseLabel(id) : '');
      warehouseDisplay.placeholder = id ? '' : 'All warehouses (branch Σ)';
    }
    syncWarehouseClear();
    updateExportLink();
  }

  function openWarehouseModal() {
    if (!warehouseModal) return;
    warehouseModal.classList.remove('hidden');
    warehouseModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('sv-wh-modal-open');
    if (warehouseModalSearch) {
      warehouseModalSearch.value = '';
      filterWarehouseModalRows('');
      warehouseModalSearch.focus();
    }
    if (warehouseModalSearchClear) warehouseModalSearchClear.style.display = 'none';
  }

  function closeWarehouseModal() {
    if (!warehouseModal) return;
    warehouseModal.classList.add('hidden');
    warehouseModal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('sv-wh-modal-open');
  }

  function filterWarehouseModalRows(term) {
    if (!warehouseModalBody) return;
    const q = String(term || '').trim().toLowerCase();
    warehouseModalBody.querySelectorAll('.sv-wh-pick-row').forEach((tr) => {
      const code = String(tr.dataset.code || '').toLowerCase();
      const name = String(tr.dataset.name || '').toLowerCase();
      const isAll = !tr.dataset.id;
      const show = !q || isAll || code.includes(q) || name.includes(q);
      tr.style.display = show ? '' : 'none';
    });
    if (warehouseModalSearchClear) {
      warehouseModalSearchClear.style.display = q ? 'block' : 'none';
    }
  }

  function selectWarehouseRow(tr) {
    if (!tr) return;
    const id = tr.dataset.id || '';
    const code = tr.dataset.code || '';
    const name = tr.dataset.name || '';
    const label = id ? (code && name ? `${code} — ${name}` : (code || name || id)) : '';
    setWarehouse(id, label);
    closeWarehouseModal();
    if (warehouseDisplay) warehouseDisplay.focus();
  }

  const scrollPerPage = 200;
  let loading = false;
  let scrollLoading = false;
  let scrollDone = false;
  let scrollLoaded = 0;
  let scrollPage = 0;
  let scrollTotalPages = 1;
  let scrollTotalCount = 0;
  let lastRows = [];
  let lastPayload = null;
  let selectedIdx = -1;

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function fmt4(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toFixed(4);
  }

  function deltaClass(v) {
    const x = Math.abs(Number(v) || 0);
    if (x < 0.001) return 'sv-delta-ok';
    if (x < 1) return 'sv-delta-warn';
    return 'sv-delta-err';
  }

  function statusLabel(st) {
    if (st === 'err') return 'Mismatch';
    if (st === 'warn') return 'Review';
    return 'OK';
  }

  function statusCoClass(st) {
    if (st === 'err') return 'co-status co-status--err';
    if (st === 'warn') return 'co-status co-status--warn';
    return 'co-status co-status--ok';
  }

  function filterParams() {
    const wh = document.getElementById('svWarehouse').value.trim();
    const item = document.getElementById('svItem').value.trim();
    const q = document.getElementById('svSearch').value.trim();
    const mismatch = document.getElementById('svMismatch').checked;
    const includeZero = document.getElementById('svIncludeZero').checked;
    const p = new URLSearchParams();
    if (wh) p.set('warehouse_id', wh);
    if (item) p.set('item', item);
    if (q) p.set('q', q);
    if (mismatch) p.set('mismatch', '1');
    if (includeZero) p.set('include_zero', '1');
    return p;
  }

  function buildApiUrl(nextPage) {
    const p = filterParams();
    p.set('page', String(nextPage));
    p.set('per_page', String(scrollPerPage));
    return `${apiUrl}?${p.toString()}`;
  }

  function updateExportLink() {
    const p = filterParams();
    const qs = p.toString();
    if (btnExport) btnExport.href = qs ? `${exportBase}?${qs}` : exportBase;
  }

  function showBanner(text, isError) {
    if (!msgEl) return;
    if (!text) {
      msgEl.style.display = 'none';
      msgEl.className = 'sv-scroll-status';
      msgEl.textContent = '';
      return;
    }
    msgEl.style.display = 'block';
    msgEl.className = isError ? 'sv-scroll-status is-error' : 'sv-scroll-status';
    msgEl.textContent = text;
  }

  function setScrollStatus(text, isError) {
    if (!scrollStatus) return;
    scrollStatus.className = isError ? 'sv-scroll-status is-error' : 'sv-scroll-status';
    scrollStatus.textContent = '';
    scrollStatus.innerHTML = text || '';
  }

  function updateScrollStatus(message, isError) {
    if (!scrollStatus) return;
    scrollStatus.className = isError ? 'sv-scroll-status is-error' : 'sv-scroll-status';
    scrollStatus.textContent = message || `Showing ${scrollLoaded} of ${scrollTotalCount} rows.`;
    scrollStatus.style.cursor = (!scrollDone && !scrollLoading && !loading) ? 'pointer' : 'default';
  }

  function setLoading(on) {
    loading = on;
    if (btnRun) btnRun.disabled = on;
    if (btnRunTop) btnRunTop.disabled = on;
    if (on) {
      tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;padding:20px;color:#6b7280;">Loading verification report…</td></tr>';
      updateScrollStatus('Loading…');
    }
  }

  function resetScrollState() {
    scrollLoading = false;
    scrollDone = false;
    scrollLoaded = 0;
    scrollPage = 0;
    scrollTotalPages = 1;
    scrollTotalCount = 0;
    lastRows = [];
    selectedIdx = -1;
    if (drawer) drawer.classList.remove('has-row');
  }

  function applyColumnGates(payload) {
    const ve = (payload && payload.verification_enabled) || {};
    const gates = (payload && payload.branch_gates) || {};
    page.classList.toggle('sv-bin-enabled', !!ve.warehouse_vs_bin);
    page.classList.toggle('sv-lot-enabled', !!ve.lot_balance_vs_bins || !!ve.warehouse_vs_lot);
    const hint = document.getElementById('svRulesHint');
    if (!hint || !payload) return;
    const rules = Array.isArray(payload.rules) ? payload.rules : [];
    const skipped = [];
    if (!gates.bin_tracking) skipped.push('WH≠bin (BIN_TRACKING off)');
    if (!gates.batch_tracking) skipped.push('lot rules (BATCH_TRACKING off)');
    if (!rules.length && !skipped.length) {
      hint.textContent = 'No warehouse/bin/lot rules apply for this branch.';
      return;
    }
    const tags = [];
    if (ve.warehouse_vs_bin) tags.push('WH=bin');
    if (ve.warehouse_vs_lot) tags.push('WH=lot');
    if (ve.lot_balance_vs_bins) tags.push('lot=bin');
    const tagTxt = tags.length ? ` [${tags.join(' · ')}]` : '';
    const activeTxt = rules.length ? `Active${tagTxt}: ${rules.join(' ')}` : 'No WH/bin/lot comparison rules active.';
    const skipTxt = skipped.length ? ` Skipped: ${skipped.join('; ')}.` : '';
    hint.textContent = activeTxt + skipTxt;
  }

  function renderKpis(summary, payload) {
    const s = summary || {};
    applyColumnGates(payload);
    const totalRows = Number(s.rows ?? scrollTotalCount ?? 0);
    if (kpiRows) kpiRows.textContent = totalRows.toLocaleString();
    if (kpiMismatch) kpiMismatch.textContent = (s.mismatch_count ?? 0).toLocaleString();
    if (kpiScanned) kpiScanned.textContent = (s.items_scanned ?? 0).toLocaleString();
    if (kpiRowsSub) kpiRowsSub.textContent = totalRows ? 'Matching filters' : 'Run verification';
    if (listMeta) {
      if (scrollTotalCount > 0) {
        listMeta.textContent = `${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()} rows · ${(s.items_scanned ?? 0).toLocaleString()} scanned`;
      } else {
        listMeta.textContent = `${totalRows.toLocaleString()} row(s) · ${(s.items_scanned ?? 0).toLocaleString()} scanned`;
      }
    }
    const whSel = document.getElementById('svWarehouse');
    const whText = warehouseDisplay && warehouseDisplay.value
      ? warehouseDisplay.value
      : (whSel && whSel.value ? warehouseLabel(whSel.value) : 'All warehouses');
    if (kpiScope) kpiScope.textContent = payload && payload.warehouse_label ? payload.warehouse_label : (whSel && whSel.value ? whText : 'All warehouses');
    if (pageSubtitle && payload) {
      const loc = page.dataset.location || '';
      const scope = payload.warehouse_label
        ? `Warehouse <strong>${escapeHtml(payload.warehouse_label)}</strong> (branch ${escapeHtml(loc)})`
        : `Branch <strong>${escapeHtml(loc)}</strong> — all warehouses`;
      pageSubtitle.innerHTML = `Compare item master, warehouse, bin, and lot quantities for ${scope}.`;
    }
  }

  function openDrawer(row) {
    if (!drawer || !row) return;
    drawer.classList.add('has-row');
    const st = row.status || 'ok';
    document.getElementById('svPreviewName').textContent = row.itemname || '—';
    document.getElementById('svPreviewSubtitle').textContent = 'Stock verification detail';
    document.getElementById('svPreviewCode').textContent = String(row.itemcode ?? '—');
    const stEl = document.getElementById('svPreviewStatus');
    stEl.className = statusCoClass(st);
    stEl.textContent = statusLabel(st);
    document.getElementById('svPvIm').textContent = fmt4(row.itemmaster_qty);
    document.getElementById('svPvWhBranch').textContent = fmt4(row.warehouse_branch_total);
    document.getElementById('svPvWh').textContent = fmt4(row.warehouse_qty);
    document.getElementById('svPvBin').textContent = fmt4(row.bin_qty);
    document.getElementById('svPvLot').textContent = fmt4(row.lot_qty);
    document.getElementById('svPvLotWh').textContent = fmt4(row.lot_at_warehouse_qty);
    document.getElementById('svPvLotBin').textContent = fmt4(row.lot_bin_qty);
    document.getElementById('svPvLotUn').textContent = fmt4(row.lot_unalloc_qty);
    const jEl = document.getElementById('svPvJournal');
    const jbEl = document.getElementById('svPvJournalBranch');
    if (jEl) jEl.textContent = fmt4(row.itemjournal_qty);
    if (jbEl) jbEl.textContent = fmt4(row.itemjournal_branch_qty);
    const d1 = document.getElementById('svPvD1');
    const d2 = document.getElementById('svPvD2');
    const d3 = document.getElementById('svPvD3');
    const d4 = document.getElementById('svPvD4');
    const d5 = document.getElementById('svPvD5');
    d1.textContent = fmt4(row.delta_im_wh);
    d2.textContent = fmt4(row.delta_wh_bin);
    d3.textContent = fmt4(row.delta_wh_lot);
    if (d4) {
      d4.textContent = fmt4(row.delta_im_ij);
      d4.className = deltaClass(row.delta_im_ij);
    }
    if (d5) {
      const dwij = row.delta_wh_ij;
      d5.textContent = dwij == null || dwij === '' ? '—' : fmt4(dwij);
      d5.className = dwij == null || dwij === '' ? '' : deltaClass(dwij);
    }
    d1.className = deltaClass(row.delta_im_wh);
    d2.className = deltaClass(row.delta_wh_bin);
    d3.className = deltaClass(row.delta_wh_lot);
    const issues = (row.issues || []).join('; ');
    const issEl = document.getElementById('svPreviewIssues');
    if (issues) {
      issEl.textContent = issues;
      issEl.style.display = 'block';
    } else {
      issEl.textContent = '';
      issEl.style.display = 'none';
    }
  }

  function closeDrawer() {
    if (drawer) drawer.classList.remove('has-row');
    selectedIdx = -1;
    tbody.querySelectorAll('tr.sv-row.is-selected').forEach((tr) => tr.classList.remove('is-selected'));
  }

  function selectRow(idx) {
    selectedIdx = idx;
    tbody.querySelectorAll('tr.sv-row').forEach((tr, i) => {
      tr.classList.toggle('is-selected', i === idx);
    });
    if (idx >= 0 && lastRows[idx]) openDrawer(lastRows[idx]);
    else closeDrawer();
  }

  function rowHtml(r, idx) {
    const issues = (r.issues || []).join('; ');
    const st = r.status || 'ok';
    return `<tr class="sv-row sv-row--${escapeHtml(st)}" data-idx="${idx}" role="button" tabindex="0" title="Preview row">
      <td class="sl-no" style="text-align:center;">${idx + 1}</td>
      <td><span class="${statusCoClass(st)}">${escapeHtml(statusLabel(st))}</span></td>
      <td><a class="sv-item-link" href="/itemmaster?item_code=${encodeURIComponent(r.itemcode ?? '')}" target="_blank" rel="noopener" title="Open item master">${escapeHtml(r.itemcode)}</a></td>
      <td title="${escapeHtml(r.itemname)}">${escapeHtml((r.itemname || '').slice(0, 48))}</td>
      <td class="num">${fmt4(r.itemmaster_qty)}</td>
      <td class="num">${fmt4(r.warehouse_branch_total)}</td>
      <td class="num">${fmt4(r.warehouse_qty)}</td>
      <td class="num sv-col-bin">${r.bin_qty == null ? '—' : fmt4(r.bin_qty)}</td>
      <td class="num sv-col-lot">${r.lot_qty == null ? '—' : fmt4(r.lot_qty)}</td>
      <td class="num sv-col-lot">${r.lot_bin_qty == null ? '—' : fmt4(r.lot_bin_qty)}</td>
      <td class="num">${fmt4(r.itemjournal_qty)}</td>
      <td class="num ${deltaClass(r.delta_im_wh)}">${fmt4(r.delta_im_wh)}</td>
      <td class="num ${deltaClass(r.delta_im_ij)}">${fmt4(r.delta_im_ij)}</td>
      <td class="num sv-col-bin ${r.delta_wh_bin == null ? '' : deltaClass(r.delta_wh_bin)}">${r.delta_wh_bin == null ? '—' : fmt4(r.delta_wh_bin)}</td>
      <td class="sv-issues">${issues ? escapeHtml(issues) : '—'}</td>
    </tr>`;
  }

  function bindRowEvents() {
    tbody.querySelectorAll('tr.sv-row:not([data-bound])').forEach((tr) => {
      tr.dataset.bound = '1';
      tr.addEventListener('click', (ev) => {
        if (ev.target.closest('a.sv-item-link')) return;
        selectRow(parseInt(tr.dataset.idx, 10));
      });
      tr.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault();
          selectRow(parseInt(tr.dataset.idx, 10));
        }
      });
    });
  }

  function appendRows(rows) {
    const batch = rows || [];
    if (!batch.length) return;
    const startIdx = lastRows.length;
    const html = batch.map((r, i) => rowHtml(r, startIdx + i)).join('');
    tbody.insertAdjacentHTML('beforeend', html);
    lastRows = lastRows.concat(batch);
    bindRowEvents();
  }

  function showEmptyTable(message) {
    tbody.innerHTML = `<tr><td colspan="15" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">${message}</td></tr>`;
  }

  function applyReportPayload(data, isFirstPage) {
    lastPayload = data;
    scrollPage = Number(data.page || scrollPage || 1);
    scrollTotalPages = Number(data.total_pages || data.pagination?.total_pages || 1) || 1;
    scrollTotalCount = Number(data.total_count || data.pagination?.total_count || data.summary?.rows || 0) || 0;
    const rows = Array.isArray(data.rows) ? data.rows : [];

    if (isFirstPage) {
      renderKpis(data.summary, data);
      tbody.innerHTML = '';
      closeDrawer();
      if (!rows.length) {
        showEmptyTable('No rows — relax filters or include zero-qty items.');
        scrollDone = true;
        updateScrollStatus('No matching rows for the current filters.');
        scrollLoaded = 0;
        return;
      }
    }

    appendRows(rows);
    scrollLoaded = lastRows.length;

    if (listMeta && data.summary) {
      listMeta.textContent = `${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()} rows · ${(data.summary.items_scanned ?? 0).toLocaleString()} scanned`;
    }

    if (scrollPage >= scrollTotalPages || rows.length === 0 || scrollLoaded >= scrollTotalCount) {
      scrollDone = true;
      updateScrollStatus(`All ${scrollLoaded.toLocaleString()} rows loaded. Click a row for detail preview.`);
    } else {
      updateScrollStatus(`Showing ${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()} rows. Scroll down or click here to load more.`);
    }
  }

  async function fetchReportPage(nextPage, isFirstPage) {
    const res = await fetch(buildApiUrl(nextPage), { credentials: 'same-origin' });
    const data = await res.json();
    if (!data.ok) {
      throw new Error(data.error || 'Verification failed');
    }
    applyReportPayload(data, isFirstPage);
    if (isFirstPage) {
      const qs = filterParams().toString();
      const url = new URL(window.location.href);
      url.search = qs;
      window.history.replaceState({}, '', url.pathname + (qs ? `?${qs}` : ''));
    }
    return data;
  }

  async function runVerification() {
    if (loading) return;
    showBanner('');
    resetScrollState();
    setLoading(true);
    updateExportLink();
    try {
      await fetchReportPage(1, true);
    } catch (ex) {
      showBanner(String(ex.message || ex), true);
      tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;padding:20px;color:#b91c1c;">Could not load report.</td></tr>';
      updateScrollStatus('Load failed.', true);
    } finally {
      if (btnRun) btnRun.disabled = false;
      if (btnRunTop) btnRunTop.disabled = false;
      loading = false;
    }
  }

  async function loadNextPage() {
    if (!tbody || scrollLoading || scrollDone || loading) return;
    if (scrollPage >= scrollTotalPages || scrollLoaded >= scrollTotalCount) {
      scrollDone = true;
      updateScrollStatus(`All ${scrollLoaded.toLocaleString()} rows loaded. Click a row for detail preview.`);
      return;
    }

    scrollLoading = true;
    const nextPage = scrollPage + 1;
    updateScrollStatus(`Loading more rows… (${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()})`);
    try {
      await fetchReportPage(nextPage, false);
    } catch (ex) {
      updateScrollStatus(ex && ex.message ? ex.message : 'Could not load more rows.', true);
    } finally {
      scrollLoading = false;
    }
  }

  function initializeInfiniteScroll() {
    if (!scrollSentinel) return;
    updateScrollStatus('No report loaded. Click Run verification to compare stock sources.');
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) loadNextPage();
        });
      }, { rootMargin: '500px 0px' });
      observer.observe(scrollSentinel);
    } else {
      window.addEventListener('scroll', () => {
        const remaining = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
        if (remaining < 500) loadNextPage();
      }, { passive: true });
    }
    if (scrollStatus) {
      scrollStatus.addEventListener('click', () => {
        if (!scrollDone && !scrollLoading && !loading) loadNextPage();
      });
    }
  }

  function clearFilters() {
    setWarehouse('', '');
    document.getElementById('svItem').value = '';
    document.getElementById('svSearch').value = '';
    document.getElementById('svMismatch').checked = false;
    document.getElementById('svIncludeZero').checked = false;
    updateExportLink();
    window.history.replaceState({}, '', window.location.pathname);
    lastPayload = null;
    resetScrollState();
    page.classList.remove('sv-bin-enabled', 'sv-lot-enabled');
    closeDrawer();
    tbody.innerHTML = '<tr><td colspan="15" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">Choose filters and click <strong>Run verification</strong>.</td></tr>';
    if (kpiRows) kpiRows.textContent = '—';
    if (kpiMismatch) kpiMismatch.textContent = '—';
    if (kpiScanned) kpiScanned.textContent = '—';
    if (listMeta) listMeta.textContent = '—';
    const hint = document.getElementById('svRulesHint');
    if (hint) {
      hint.textContent = 'Run verification to see which rules apply (branch WAREHOUSE_ENABLE / BIN_TRACKING / BATCH_TRACKING).';
    }
    updateScrollStatus('No report loaded. Click Run verification to compare stock sources.');
    showBanner('');
  }

  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    runVerification();
  });

  if (btnRunTop) btnRunTop.addEventListener('click', runVerification);
  if (btnClear) btnClear.addEventListener('click', clearFilters);
  if (drawerClose) drawerClose.addEventListener('click', closeDrawer);

  if (warehousePicker) warehousePicker.addEventListener('click', (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    openWarehouseModal();
  });
  if (warehousePopupShell) {
    warehousePopupShell.addEventListener('click', (ev) => {
      if (ev.target.closest('.search-clear') || ev.target.closest('.search-picker')) return;
      openWarehouseModal();
    });
  }
  if (warehouseDisplay) {
    warehouseDisplay.addEventListener('keydown', (ev) => {
      if (ev.key === 'F1') {
        ev.preventDefault();
        openWarehouseModal();
      }
    });
  }
  if (warehouseClear) {
    warehouseClear.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      setWarehouse('', '');
    });
  }
  if (warehouseModal) {
    warehouseModal.addEventListener('click', (ev) => {
      if (ev.target.dataset.close === 'svWarehouseModal'
        || ev.target.classList.contains('modal__overlay')
        || ev.target.classList.contains('modal__close')) {
        closeWarehouseModal();
      }
    });
  }
  if (warehouseModalBody) {
    warehouseModalBody.addEventListener('click', (ev) => {
      const row = ev.target.closest('.sv-wh-pick-row');
      if (row) selectWarehouseRow(row);
    });
    warehouseModalBody.addEventListener('dblclick', (ev) => {
      const row = ev.target.closest('.sv-wh-pick-row');
      if (row) selectWarehouseRow(row);
    });
  }
  if (warehouseModalSearch) {
    warehouseModalSearch.addEventListener('input', () => {
      filterWarehouseModalRows(warehouseModalSearch.value);
    });
  }
  if (warehouseModalSearchClear && warehouseModalSearch) {
    warehouseModalSearchClear.addEventListener('click', (ev) => {
      ev.preventDefault();
      warehouseModalSearch.value = '';
      filterWarehouseModalRows('');
      warehouseModalSearch.focus();
    });
  }
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && warehouseModal && !warehouseModal.classList.contains('hidden')) {
      closeWarehouseModal();
    }
  });

  if (toggleFilters && filterExtra) {
    toggleFilters.addEventListener('click', () => {
      filterExtra.classList.toggle('is-open');
      toggleFilters.textContent = filterExtra.classList.contains('is-open') ? 'Fewer filters' : 'More filters';
    });
    if (document.getElementById('svMismatch').checked || document.getElementById('svIncludeZero').checked) {
      filterExtra.classList.add('is-open');
      toggleFilters.textContent = 'Fewer filters';
    }
  }

  ['svItem', 'svSearch', 'svMismatch', 'svIncludeZero'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', updateExportLink);
    if (el && el.tagName === 'INPUT' && el.type === 'text') {
      el.addEventListener('input', updateExportLink);
    }
  });
  if (warehouseHidden) warehouseHidden.addEventListener('change', updateExportLink);

  syncWarehouseClear();
  if (warehouseHidden && warehouseHidden.value) {
    setWarehouse(warehouseHidden.value, warehouseLabel(warehouseHidden.value));
  }

  const listRefreshBtn = document.getElementById('listRefreshNow');
  if (listRefreshBtn) {
    listRefreshBtn.addEventListener('click', (ev) => {
      ev.preventDefault();
      runVerification();
    });
  }

  updateExportLink();
  initializeInfiniteScroll();

  const initQs = new URLSearchParams(window.location.search);
  if (initQs.has('warehouse_id') || initQs.has('item') || initQs.has('q') || initQs.has('mismatch') || initQs.has('include_zero')) {
    runVerification();
  }
})();

