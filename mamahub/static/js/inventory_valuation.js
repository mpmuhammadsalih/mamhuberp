/**
 * Inventory Valuation — single list with store qty columns (pivot layout).
 */
(function () {
  'use strict';

  const page = document.getElementById('ivPage');
  if (!page) return;

  const apiUrl = page.dataset.apiUrl || '/purchase/api/inventory-valuation';
  const exportBase = page.dataset.exportUrl || '/purchase/inventory-valuation/export.csv';
  const exportPdfBase = page.dataset.exportPdfUrl || '/purchase/inventory-valuation/export.pdf';

  const form = document.getElementById('ivFilterForm');
  const thead = document.getElementById('ivTableHead');
  const tbody = document.getElementById('ivTableBody');
  const tfoot = document.getElementById('ivTableFoot');
  const scrollStatus = document.getElementById('ivScrollStatus');
  const scrollSentinel = document.getElementById('ivScrollSentinel');
  const listMeta = document.getElementById('ivListMeta');
  const msgEl = document.getElementById('ivMessage');
  const btnRun = document.getElementById('ivBtnRun');
  const btnRunTop = document.getElementById('ivBtnRunTop');
  const btnClear = document.getElementById('ivBtnClear');
  const btnExportCsv = document.getElementById('ivBtnExportCsv');
  const btnExportPdf = document.getElementById('ivBtnExportPdf');
  const toggleFilters = document.getElementById('ivToggleFilters');
  const filterExtra = document.getElementById('ivFilterExtra');
  const whFilterEl = document.getElementById('ivWarehouse');
  const whDisplayEl = document.getElementById('ivWarehouseDisplay');
  const costMethodEl = document.getElementById('ivCostMethod');
  const costMethodDisplayEl = document.getElementById('ivCostMethodDisplay');
  const categoryEl = document.getElementById('ivCategory');
  const categoryDisplayEl = document.getElementById('ivCategoryDisplay');

  const pickModal = document.getElementById('ivPickModal');
  const pickTitle = document.getElementById('ivPickModalTitle');
  const pickSearch = document.getElementById('ivPickModalSearch');
  const pickClearBtn = document.getElementById('ivPickModalClear');
  const pickHead = document.getElementById('ivPickModalHead');
  const pickBody = document.getElementById('ivPickModalBody');
  let pickTargetField = null;
  let ivFilterOptions = { warehouses: [], categories: [] };

  try {
    const optJson = document.getElementById('ivFilterOptionsJson');
    if (optJson && optJson.textContent) {
      ivFilterOptions = JSON.parse(optJson.textContent) || ivFilterOptions;
    }
  } catch (parseErr) {
    ivFilterOptions = { warehouses: [], categories: [] };
  }

  const IV_PICK_LABELS = {
    warehouse: 'Store / warehouse',
    category: 'Category',
    cost_method: 'Cost basis',
  };

  const IV_WH_ALL_LABEL = 'All stores (branch total)';
  const IV_CAT_ALL_LABEL = 'All categories';

  const scrollPerPage = 200;
  let loading = false;
  let scrollLoading = false;
  let scrollDone = false;
  let scrollLoaded = 0;
  let scrollPage = 0;
  let scrollTotalPages = 1;
  let scrollTotalCount = 0;
  let lastRows = [];
  let pivotColumns = [];
  let pageTotalQty = 0;
  let pageTotalValue = 0;
  let pageStoreTotals = {};

  const costLabels = {
    average: 'Average cost',
    cost: 'Cost price',
    landing: 'Landing cost',
  };

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, (ch) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
    ));
  }

  function fmtQty(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  }

  function fmtCost(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }

  function fmtValue(n) {
    const x = Number(n);
    return (Number.isFinite(x) ? x : 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function costLabelText() {
    return costLabels[costMethodEl?.value || 'average'] || 'Unit cost';
  }

  function setPickValue(field, value, displayText) {
    if (field === 'warehouse' && whFilterEl) {
      whFilterEl.value = value || '';
      if (whDisplayEl) whDisplayEl.value = displayText || (value ? '' : IV_WH_ALL_LABEL);
      return;
    }
    if (field === 'category' && categoryEl) {
      categoryEl.value = value || '';
      if (categoryDisplayEl) categoryDisplayEl.value = displayText || '';
      return;
    }
    if (field === 'cost_method' && costMethodEl) {
      const v = value || 'average';
      costMethodEl.value = v;
      if (costMethodDisplayEl) costMethodDisplayEl.value = displayText || costLabels[v] || v;
    }
  }

  function closeIvPick() {
    if (!pickModal) return;
    pickModal.classList.add('hidden');
    pickModal.setAttribute('aria-hidden', 'true');
    pickTargetField = null;
  }

  function filterIvPickRows(needleRaw) {
    if (!pickBody) return;
    const needle = String(needleRaw || '').toLowerCase().trim();
    pickBody.querySelectorAll('tr').forEach((tr) => {
      const t = (tr.getAttribute('data-text') || tr.textContent || '').toLowerCase();
      tr.style.display = (!needle || t.includes(needle)) ? '' : 'none';
    });
  }

  function buildIvPickRows(fieldName) {
    const rows = [];
    if (fieldName === 'warehouse') {
      rows.push({ value: '', text: IV_WH_ALL_LABEL, sub: '' });
      (ivFilterOptions.warehouses || []).forEach((w) => {
        const id = String(w.warehouse_id || '').trim();
        if (!id) return;
        rows.push({
          value: id,
          text: String(w.label || w.warehouse_code || id).trim(),
          sub: String(w.warehouse_name || '').trim(),
          code: String(w.warehouse_code || '').trim(),
        });
      });
      return rows;
    }
    if (fieldName === 'category') {
      rows.push({ value: '', text: IV_CAT_ALL_LABEL, sub: '' });
      (ivFilterOptions.categories || []).forEach((c) => {
        const code = String(c.code || '').trim();
        if (!code) return;
        rows.push({
          value: code,
          text: String(c.label || code).trim(),
          sub: String(c.name || '').trim(),
          code,
        });
      });
      return rows;
    }
    if (fieldName === 'cost_method') {
      Object.keys(costLabels).forEach((key) => {
        rows.push({ value: key, text: costLabels[key], sub: '' });
      });
    }
    return rows;
  }

  function openIvPick(fieldName) {
    if (!pickModal || !pickBody || !pickTitle) return;
    pickTargetField = fieldName;
    const title = IV_PICK_LABELS[fieldName] || fieldName;
    pickTitle.textContent = title;
    const vals = buildIvPickRows(fieldName);
    const twoCol = fieldName === 'warehouse' || fieldName === 'category';
    if (pickHead) {
      pickHead.innerHTML = twoCol
        ? '<tr><th>Code</th><th>Name</th></tr>'
        : `<tr><th>${escapeHtml(title)}</th></tr>`;
    }
    pickBody.innerHTML = '';
    vals.forEach((row) => {
      const tr = document.createElement('tr');
      tr.setAttribute('data-text', `${row.text} ${row.sub || ''} ${row.code || row.value}`.toLowerCase());
      if (twoCol) {
        const tdCode = document.createElement('td');
        tdCode.textContent = row.code || (row.value ? row.value : '—');
        const tdName = document.createElement('td');
        tdName.textContent = row.sub || row.text;
        tr.appendChild(tdCode);
        tr.appendChild(tdName);
      } else {
        const td = document.createElement('td');
        td.textContent = row.text;
        tr.appendChild(td);
      }
      tr.addEventListener('click', () => {
        setPickValue(fieldName, row.value, row.text);
        closeIvPick();
        updateExportLinks();
      });
      pickBody.appendChild(tr);
    });
    if (!vals.length) {
      const tr0 = document.createElement('tr');
      const td0 = document.createElement('td');
      td0.colSpan = twoCol ? 2 : 1;
      td0.style.color = '#6c757d';
      td0.style.fontStyle = 'italic';
      td0.textContent = 'No options available.';
      tr0.appendChild(td0);
      pickBody.appendChild(tr0);
    }
    if (pickSearch) {
      pickSearch.value = '';
      filterIvPickRows('');
      setTimeout(() => pickSearch.focus(), 0);
    }
    pickModal.classList.remove('hidden');
    pickModal.setAttribute('aria-hidden', 'false');
  }

  function clearIvPickField(fieldName) {
    if (fieldName === 'warehouse') {
      setPickValue('warehouse', '', IV_WH_ALL_LABEL);
    } else if (fieldName === 'category') {
      setPickValue('category', '', '');
    }
    updateExportLinks();
  }

  function initIvPickers() {
    document.querySelectorAll('[data-iv-pick]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const field = btn.getAttribute('data-iv-pick');
        if (field) openIvPick(field);
      });
    });
    document.querySelectorAll('[data-iv-clear]').forEach((btn) => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const field = btn.getAttribute('data-iv-clear');
        if (field) clearIvPickField(field);
      });
    });
    document.querySelectorAll('.js-iv-pick').forEach((inp) => {
      inp.addEventListener('click', () => {
        const field = inp.getAttribute('data-iv-pick');
        if (field) openIvPick(field);
      });
      inp.addEventListener('keydown', (ev) => {
        if (ev.key === 'F1') {
          ev.preventDefault();
          const field = inp.getAttribute('data-iv-pick');
          if (field) openIvPick(field);
        }
      });
    });
    if (pickSearch) {
      pickSearch.addEventListener('input', () => filterIvPickRows(pickSearch.value));
      pickSearch.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') {
          ev.preventDefault();
          closeIvPick();
        }
      });
    }
    if (pickClearBtn) {
      pickClearBtn.addEventListener('click', () => {
        if (pickSearch) {
          pickSearch.value = '';
          filterIvPickRows('');
          pickSearch.focus();
        }
      });
    }
    if (pickModal) {
      pickModal.addEventListener('click', (ev) => {
        if (ev.target.getAttribute('data-close') === 'ivPickModal' || ev.target.classList.contains('modal__close')) {
          closeIvPick();
        }
      });
    }
    window.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && pickModal && !pickModal.classList.contains('hidden')) {
        closeIvPick();
      }
    });
  }

  function filterParams() {
    const p = new URLSearchParams();
    p.set('view', 'pivot');
    if (whFilterEl && whFilterEl.value) p.set('warehouse_id', whFilterEl.value);
    p.set('cost_method', costMethodEl?.value || 'average');
    const item = document.getElementById('ivItem').value.trim();
    const barcode = document.getElementById('ivBarcode').value.trim();
    const q = document.getElementById('ivSearch').value.trim();
    if (item) p.set('item', item);
    if (barcode) p.set('barcode', barcode);
    if (q) p.set('q', q);
    if (categoryEl && categoryEl.value) p.set('category', categoryEl.value);
    if (document.getElementById('ivIncludeZero').checked) p.set('include_zero', '1');
    return p;
  }

  function buildApiUrl(nextPage) {
    const p = filterParams();
    p.set('page', String(nextPage));
    p.set('per_page', String(scrollPerPage));
    return `${apiUrl}?${p.toString()}`;
  }

  function updateExportLinks() {
    const qs = filterParams().toString();
    if (btnExportCsv) btnExportCsv.href = qs ? `${exportBase}?${qs}` : exportBase;
    if (btnExportPdf) btnExportPdf.href = qs ? `${exportPdfBase}?${qs}` : exportPdfBase;
  }

  function showBanner(text, isError) {
    if (!msgEl) return;
    if (!text) {
      msgEl.style.display = 'none';
      msgEl.textContent = '';
      return;
    }
    msgEl.style.display = 'block';
    msgEl.className = isError ? 'iv-scroll-status is-error' : 'iv-scroll-status';
    msgEl.textContent = text;
  }

  function updateScrollStatus(message, isError) {
    if (!scrollStatus) return;
    scrollStatus.className = isError ? 'iv-scroll-status is-error' : 'iv-scroll-status';
    scrollStatus.textContent = message || `Showing ${scrollLoaded} of ${scrollTotalCount} items.`;
    scrollStatus.style.cursor = (!scrollDone && !scrollLoading && !loading) ? 'pointer' : 'default';
  }

  function resetScrollState() {
    scrollLoading = false;
    scrollDone = false;
    scrollLoaded = 0;
    scrollPage = 0;
    scrollTotalPages = 1;
    scrollTotalCount = 0;
    lastRows = [];
    pivotColumns = [];
    pageTotalQty = 0;
    pageTotalValue = 0;
    pageStoreTotals = {};
  }

  function tableColSpan() {
    return 5 + pivotColumns.length + 3;
  }

  function buildHeader(columns) {
    if (!thead) return;
    const storeHeaders = (columns || []).map((col) => {
      const code = escapeHtml(col.code || col.label || '');
      const title = escapeHtml(col.name || code);
      return `<th class="num iv-col-store" title="${title}">${code}</th>`;
    }).join('');
    thead.innerHTML = `<tr>
      <th style="text-align:center; width:48px;">#</th>
      <th>Item</th>
      <th>Item name</th>
      <th>Category</th>
      <th>UOM</th>
      ${storeHeaders}
      <th class="num iv-col-total">Total qty</th>
      <th class="num iv-col-total">${escapeHtml(costLabelText())}</th>
      <th class="num iv-col-total">Total value</th>
    </tr>`;
  }

  function setLoading(on) {
    loading = on;
    if (btnRun) btnRun.disabled = on;
    if (btnRunTop) btnRunTop.disabled = on;
    if (on) {
      tbody.innerHTML = `<tr><td colspan="${Math.max(tableColSpan(), 8)}" style="text-align:center;padding:20px;color:#6b7280;">Loading inventory valuation…</td></tr>`;
      updateScrollStatus('Loading…');
      if (tfoot) tfoot.style.display = 'none';
    }
  }

  function renderKpis(summary, payload) {
    const s = summary || {};
    const method = (payload && payload.cost_method) || costMethodEl?.value || 'average';
    const elItems = document.getElementById('ivKpiItems');
    const elQty = document.getElementById('ivKpiQty');
    const elValue = document.getElementById('ivKpiValue');
    const elMethod = document.getElementById('ivKpiCostMethod');
    const elScope = document.getElementById('ivKpiScope');
    const elItemsSub = document.getElementById('ivKpiItemsSub');
    if (elItems) elItems.textContent = Number(s.item_count || 0).toLocaleString();
    if (elQty) elQty.textContent = fmtQty(s.total_qty || 0);
    if (elValue) elValue.textContent = fmtValue(s.total_value || 0);
    if (elMethod) {
      const label = costLabels[method] || 'Average cost';
      elMethod.textContent = method === 'average'
        ? label
        : `${label} basis (not Item Master average cost)`;
    }
    if (elItemsSub) elItemsSub.textContent = s.item_count ? 'Matching filters' : 'Run report';
    if (elScope) {
      elScope.textContent = (payload && payload.warehouse_label) ? payload.warehouse_label : 'All stores';
    }
    if (listMeta) {
      listMeta.textContent = scrollTotalCount
        ? `${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()} items`
        : `${Number(s.item_count || 0).toLocaleString()} items`;
    }
  }

  function updatePageFooter() {
    if (!tfoot) return;
    if (!lastRows.length) {
      tfoot.style.display = 'none';
      return;
    }
    const storeCells = pivotColumns.map((col) => {
      const code = col.code || col.label || '';
      const val = pageStoreTotals[code] || 0;
      return `<td class="num iv-col-store">${fmtQty(val)}</td>`;
    }).join('');
    tfoot.innerHTML = `<tr>
      <td colspan="5" class="num" style="font-weight:700; text-align:right;">Loaded rows total</td>
      ${storeCells}
      <td class="num iv-col-total">${fmtQty(pageTotalQty)}</td>
      <td class="num iv-col-total"></td>
      <td class="num iv-col-total">${fmtValue(pageTotalValue)}</td>
    </tr>`;
    tfoot.style.display = '';
  }

  function rowHtml(r, idx) {
    const cat = r.categoryname
      ? escapeHtml(r.categoryname)
      : (r.categorycode != null && r.categorycode !== '' ? escapeHtml(r.categorycode) : '—');
    const sq = r.store_qty || {};
    const storeCells = pivotColumns.map((col) => {
      const code = col.code || col.label || '';
      const q = Number(sq[code]) || 0;
      const cls = Math.abs(q) < 0.0001 ? 'num iv-col-store iv-zero' : 'num iv-col-store';
      return `<td class="${cls}">${fmtQty(q)}</td>`;
    }).join('');
    return `<tr>
      <td style="text-align:center;">${idx + 1}</td>
      <td>${escapeHtml(r.itemcode)}</td>
      <td title="${escapeHtml(r.itemname)}">${escapeHtml((r.itemname || '').slice(0, 48))}</td>
      <td>${cat}</td>
      <td>${escapeHtml(r.baseuom || '—')}</td>
      ${storeCells}
      <td class="num iv-col-total">${fmtQty(r.total_qty)}</td>
      <td class="num iv-col-total">${fmtCost(r.unitcost)}</td>
      <td class="num iv-col-total">${fmtValue(r.total_value)}</td>
    </tr>`;
  }

  function accumulateRowTotals(r) {
    pageTotalQty += Number(r.total_qty) || 0;
    pageTotalValue += Number(r.total_value) || 0;
    const sq = r.store_qty || {};
    pivotColumns.forEach((col) => {
      const code = col.code || col.label || '';
      pageStoreTotals[code] = (pageStoreTotals[code] || 0) + (Number(sq[code]) || 0);
    });
  }

  function appendRows(rows) {
    const batch = rows || [];
    if (!batch.length) return;
    if (!lastRows.length && tbody.rows.length === 1) {
      const only = tbody.rows[0].querySelector('td[colspan]');
      if (only) tbody.innerHTML = '';
    }
    const startIdx = lastRows.length;
    tbody.insertAdjacentHTML('beforeend', batch.map((r, i) => rowHtml(r, startIdx + i)).join(''));
    batch.forEach(accumulateRowTotals);
    lastRows = lastRows.concat(batch);
    updatePageFooter();
  }

  function applyReportPayload(data, isFirstPage) {
    scrollPage = Number(data.page || scrollPage || 1);
    scrollTotalPages = Number(data.total_pages || data.pagination?.total_pages || 1) || 1;
    scrollTotalCount = Number(data.total_count || data.pagination?.total_count || data.summary?.item_count || 0) || 0;
    const rows = Array.isArray(data.rows) ? data.rows : [];

    if (isFirstPage) {
      pivotColumns = Array.isArray(data.pivot_columns) ? data.pivot_columns : [];
      buildHeader(pivotColumns);
      renderKpis(data.summary, data);
      tbody.innerHTML = '';
      pageTotalQty = 0;
      pageTotalValue = 0;
      pageStoreTotals = {};
      lastRows = [];

      if (!rows.length) {
        const msg = !pivotColumns.length
          ? 'No warehouse/store columns found for this branch.'
          : 'No items match the current filters.';
        tbody.innerHTML = `<tr><td colspan="${Math.max(tableColSpan(), 8)}" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">${msg}</td></tr>`;
        scrollDone = true;
        updateScrollStatus('No matching items.');
        scrollLoaded = 0;
        if (tfoot) tfoot.style.display = 'none';
        return;
      }
    }

    appendRows(rows);
    scrollLoaded = lastRows.length;
    if (listMeta) {
      listMeta.textContent = `${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()} items`;
    }

    if (scrollPage >= scrollTotalPages || rows.length === 0 || scrollLoaded >= scrollTotalCount) {
      scrollDone = true;
      updateScrollStatus(`All ${scrollLoaded.toLocaleString()} items loaded.`);
    } else {
      updateScrollStatus(`Showing ${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()} items. Scroll down or click here to load more.`);
    }
  }

  async function fetchReportPage(nextPage, isFirstPage) {
    const res = await fetch(buildApiUrl(nextPage), { credentials: 'same-origin' });
    let data = {};
    try {
      data = await res.json();
    } catch (parseErr) {
      throw new Error(res.ok ? 'Invalid server response' : `Report failed (${res.status})`);
    }
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.message || `Report failed (${res.status})`);
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

  async function runReport() {
    if (loading) return;
    showBanner('');
    resetScrollState();
    setLoading(true);
    updateExportLinks();
    try {
      await fetchReportPage(1, true);
    } catch (ex) {
      showBanner(String(ex.message || ex), true);
      tbody.innerHTML = `<tr><td colspan="${Math.max(tableColSpan(), 8)}" style="text-align:center;padding:20px;color:#b91c1c;">Could not load report.</td></tr>`;
      updateScrollStatus('Load failed.', true);
    } finally {
      if (btnRun) btnRun.disabled = false;
      if (btnRunTop) btnRunTop.disabled = false;
      loading = false;
    }
  }

  async function loadNextPage() {
    if (scrollLoading || scrollDone || loading) return;
    if (scrollPage >= scrollTotalPages || scrollLoaded >= scrollTotalCount) {
      scrollDone = true;
      updateScrollStatus(`All ${scrollLoaded.toLocaleString()} items loaded.`);
      return;
    }
    scrollLoading = true;
    updateScrollStatus(`Loading more… (${scrollLoaded.toLocaleString()} of ${scrollTotalCount.toLocaleString()})`);
    try {
      await fetchReportPage(scrollPage + 1, false);
    } catch (ex) {
      updateScrollStatus(ex && ex.message ? ex.message : 'Could not load more rows.', true);
    } finally {
      scrollLoading = false;
    }
  }

  function initializeInfiniteScroll() {
    if (!scrollSentinel) return;
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
    scrollStatus?.addEventListener('click', () => {
      if (!scrollDone && !scrollLoading && !loading) loadNextPage();
    });
  }

  function clearFilters() {
    if (whFilterEl) setPickValue('warehouse', '', IV_WH_ALL_LABEL);
    setPickValue('cost_method', 'average', costLabels.average);
    document.getElementById('ivItem').value = '';
    document.getElementById('ivBarcode').value = '';
    document.getElementById('ivSearch').value = '';
    setPickValue('category', '', '');
    document.getElementById('ivIncludeZero').checked = false;
    updateExportLinks();
    window.history.replaceState({}, '', window.location.pathname);
    resetScrollState();
    buildHeader([]);
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">Set filters and click <strong>Run report</strong>.</td></tr>`;
    if (tfoot) tfoot.style.display = 'none';
    ['ivKpiItems', 'ivKpiQty', 'ivKpiValue'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
    const elScope = document.getElementById('ivKpiScope');
    if (elScope) elScope.textContent = 'All stores';
    if (listMeta) listMeta.textContent = '—';
    updateScrollStatus('No report loaded. Click Run report to calculate inventory value.');
    showBanner('');
  }

  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    runReport();
  });
  if (btnRunTop) btnRunTop.addEventListener('click', runReport);
  if (btnClear) btnClear.addEventListener('click', clearFilters);

  if (toggleFilters && filterExtra) {
    toggleFilters.addEventListener('click', () => {
      filterExtra.classList.toggle('is-open');
      toggleFilters.textContent = filterExtra.classList.contains('is-open') ? 'Fewer filters' : 'More filters';
    });
    if (document.getElementById('ivIncludeZero').checked || (categoryEl && categoryEl.value)) {
      filterExtra.classList.add('is-open');
      toggleFilters.textContent = 'Fewer filters';
    }
  }

  ['ivWarehouse', 'ivCostMethod', 'ivItem', 'ivBarcode', 'ivSearch', 'ivCategory', 'ivIncludeZero'].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', updateExportLinks);
    if (el.tagName === 'INPUT' && (el.type === 'text' || el.type === 'hidden')) {
      el.addEventListener('input', updateExportLinks);
    }
  });

  initIvPickers();

  const listRefreshBtn = document.getElementById('listRefreshNow');
  if (listRefreshBtn) {
    listRefreshBtn.addEventListener('click', (ev) => {
      ev.preventDefault();
      runReport();
    });
  }

  buildHeader([]);
  updateExportLinks();
  initializeInfiniteScroll();

  const initQs = new URLSearchParams(window.location.search);
  if (initQs.has('warehouse_id') || initQs.has('q') || initQs.has('item') || initQs.has('barcode')
      || initQs.has('category') || initQs.has('cost_method') || initQs.has('include_zero')) {
    runReport();
  } else {
    // Default run: Average cost + all stores so KPI matches Item Master (qty × average cost).
    runReport();
  }
})();
