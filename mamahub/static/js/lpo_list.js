/**
 * Purchase Order (LPO) list — paginated API load (tabs, search, prev/next, load more).
 */
window.bootLpoList = function () {
  const pageRoot = document.querySelector('.lpo-list-page');
  if (!pageRoot) return;

  const lpoApi = pageRoot.dataset.lpoApi || '/purchase/order/api/list';
  const poQueryTpl = pageRoot.dataset.poQueryUrlTpl || '';
  const poEditTpl = pageRoot.dataset.poEditUrlTpl || '';
  const apiCancelPo = pageRoot.dataset.cancelApi || '';

  const table = document.getElementById('lpoTable');
  const tbody = document.getElementById('lpoBody');
  const countEl = document.getElementById('lpoCount');
  const totalEl = document.getElementById('lpoTotalAmt');
  const tabDraft = document.getElementById('tabDraft');
  const tabApproved = document.getElementById('tabApproved');
  const tabCanceled = document.getElementById('tabCanceled');
  const searchInput = document.getElementById('lpoSearch');
  const dateFromEl = document.getElementById('lpoDateFrom');
  const dateToEl = document.getElementById('lpoDateTo');
  const scrollStatus = document.getElementById('lpoScrollStatus');
  const scrollSentinel = document.getElementById('lpoScrollSentinel');
  const paginationEl = document.getElementById('lpoPagination');
  const paginationInfo = document.getElementById('lpoPaginationInfo');
  const pageLabel = document.getElementById('lpoPageLabel');
  const prevBtn = document.getElementById('lpoPrevPage');
  const nextBtn = document.getElementById('lpoNextPage');
  const loadMoreBtn = document.getElementById('lpoLoadMore');
  const lpoPlaceholder = '999999999';

  let activeTab = 'draft';
  let sortCol = -1;
  let sortAsc = true;
  let listLoading = false;
  let listAppendMode = false;
  let listPage = 1;
  let listTotalPages = Math.max(1, parseInt(pageRoot.dataset.initialTotalPages || '1', 10) || 1);
  let listTotalCount = Math.max(0, parseInt(pageRoot.dataset.initialTotalCount || '0', 10) || 0);
  let listLoaded = 0;
  const perPage = Math.max(20, parseInt(pageRoot.dataset.itemsPerPage || '50', 10) || 50);
  let searchDebounce = null;

  function poUrl(tpl, lpono) {
    if (!tpl) return '#';
    return tpl.replace(lpoPlaceholder, String(lpono));
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function fmtAmount(value) {
    const n = Number(value);
    return (Number.isFinite(n) ? n : 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function hasMorePages() {
    return listPage < listTotalPages;
  }

  function updateScrollStatus(message, isError) {
    if (!scrollStatus) return;
    if (!message) {
      scrollStatus.style.display = 'none';
      scrollStatus.textContent = '';
      scrollStatus.classList.remove('is-error');
      return;
    }
    scrollStatus.textContent = message;
    scrollStatus.classList.toggle('is-error', Boolean(isError));
    scrollStatus.style.display = '';
    scrollStatus.style.cursor = hasMorePages() && !listLoading ? 'pointer' : 'default';
  }

  function renderPagination() {
    if (!paginationEl) return;
    if (listTotalCount <= 0) {
      paginationEl.style.display = 'none';
      return;
    }
    paginationEl.style.display = '';
    let rowStart = 0;
    let rowEnd = listLoaded;
    if (listLoaded > 0) {
      if (listAppendMode) {
        rowStart = 1;
      } else {
        rowStart = (listPage - 1) * perPage + 1;
        rowEnd = rowStart + listLoaded - 1;
      }
    }
    if (paginationInfo) {
      paginationInfo.textContent = listLoaded > 0
        ? ('Showing ' + rowStart + '–' + rowEnd + ' of ' + listTotalCount + ' (page ' + listPage + ' of ' + listTotalPages + ')')
        : '';
    }
    if (pageLabel) pageLabel.textContent = String(listPage);
    if (prevBtn) prevBtn.disabled = listPage <= 1 || listLoading;
    if (nextBtn) nextBtn.disabled = !hasMorePages() || listLoading;
    if (loadMoreBtn) {
      loadMoreBtn.disabled = !hasMorePages() || listLoading;
      loadMoreBtn.style.display = hasMorePages() ? '' : 'none';
    }
    if (hasMorePages()) {
      updateScrollStatus('Showing ' + listLoaded + ' of ' + listTotalCount + '. Click “Load more” or Next, or scroll down.');
    } else {
      updateScrollStatus(listLoaded > 0 ? ('All ' + listTotalCount + ' records loaded.') : '');
    }
  }

  function buildApiUrl(page) {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('per_page', String(perPage));
    params.set('tab', activeTab);
    const q = (searchInput && searchInput.value || '').trim();
    if (q) params.set('search', q);
    if (dateFromEl && dateFromEl.value) params.set('date_from', dateFromEl.value);
    if (dateToEl && dateToEl.value) params.set('date_to', dateToEl.value);
    return lpoApi + '?' + params.toString();
  }

  function updateFooterTotal() {
    if (!totalEl || !tbody) return;
    let sum = 0;
    tbody.querySelectorAll('tr.lpo-row').forEach(function (row) {
      sum += parseFloat(row.getAttribute('data-amount') || 0);
    });
    totalEl.textContent = fmtAmount(sum);
  }

  function reindex() {
    if (!tbody) return;
    let i = 1;
    tbody.querySelectorAll('tr.lpo-row').forEach(function (row) {
      const sl = row.querySelector('.sl-no');
      if (sl) sl.textContent = String(i++);
    });
  }

  function updateCountLabel() {
    if (!countEl) return;
    const q = (searchInput && searchInput.value || '').trim();
    const df = dateFromEl && dateFromEl.value;
    const dt = dateToEl && dateToEl.value;
    countEl.textContent = (q || df || dt)
      ? (listLoaded + ' of ' + listTotalCount + ' shown')
      : (listTotalCount + ' records');
  }

  function createLpoRow(order, absoluteIndex) {
    const row = document.createElement('tr');
    row.className = 'lpo-row';
    const lpono = order.lpono;
    const approval = String(order.approval_status || 'DRAFT').toUpperCase();
    const inReceipt = String(order.in_receipt || 'N').toUpperCase();
    const lpodate = order.lpodate || '';
    row.dataset.lpono = lpono;
    row.dataset.date = lpodate;
    row.dataset.supplier = order.suppliercode || '';
    row.dataset.suppliername = order.suppliername || '';
    row.dataset.amount = order.amount || 0;
    row.dataset.approval = approval;
    row.dataset.inreceipt = inReceipt;

    const viewHref = escapeHtml(poUrl(poQueryTpl, lpono));
    const editHref = escapeHtml(poUrl(poEditTpl, lpono));
    let actions = '<a class="btn-view" href="' + viewHref + '">View</a>';
    if (approval !== 'CANCELLED' && inReceipt !== 'Y') {
      actions +=
        ' <a class="btn-view" href="' + editHref + '" style="margin-left:6px;">Edit</a>' +
        ' <button type="button" class="btn-view btn-cancel-po" data-lpono="' + escapeHtml(lpono) + '" style="margin-left:6px;border-color:#fecaca;color:#b91c1c;">Cancel</button>';
    }

    row.innerHTML =
      '<td class="sl-no">' + absoluteIndex + '</td>' +
      '<td><a class="grn-link" href="' + viewHref + '">' + escapeHtml(lpono) + '</a></td>' +
      '<td>' + escapeHtml(lpodate || '-') + '</td>' +
      '<td>' + escapeHtml(order.createddate || '-') + '</td>' +
      '<td>' + escapeHtml(order.suppliercode || '-') + '</td>' +
      '<td>' + escapeHtml(order.suppliername || '-') + '</td>' +
      '<td class="num">' + fmtAmount(order.amount) + '</td>' +
      '<td>' + escapeHtml(approval) + '</td>' +
      '<td style="text-align:center;">' + actions + '</td>';
    return row;
  }

  function showNoData() {
    if (!tbody) return;
    tbody.innerHTML =
      '<tr id="lpoNoData"><td colspan="9" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">No purchase orders found.</td></tr>';
    listLoaded = 0;
    listPage = 1;
    listTotalPages = 1;
    listTotalCount = 0;
    if (countEl) countEl.textContent = '0 records';
    if (totalEl) totalEl.textContent = '0.00';
    renderPagination();
  }

  function showLoadingRow() {
    if (!tbody) return;
    tbody.innerHTML =
      '<tr id="lpoLoading"><td colspan="9" style="text-align:center;padding:20px;color:#6b7280;">Loading purchase orders…</td></tr>';
  }

  async function loadLpoPage(page, mode) {
    if (!tbody || listLoading) return;
    const append = mode === 'append';
    const replace = mode === 'replace' || !append;

    if (append && !hasMorePages()) return;

    listLoading = true;
    listAppendMode = append;
    if (replace) showLoadingRow();
    if (append) updateScrollStatus('Loading more…', false);

    try {
      const res = await fetch(buildApiUrl(page), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok || !data.success) {
        throw new Error(data.error || data.message || 'Load failed (' + res.status + ')');
      }

      const orders = Array.isArray(data.orders) ? data.orders : [];
      listPage = Number(data.page || page) || page;
      listTotalPages = Math.max(1, Number(data.total_pages || 1) || 1);
      listTotalCount = Number(data.total_count || 0);

      if (replace) {
        tbody.innerHTML = '';
        listLoaded = 0;
      }

      if (!orders.length && listLoaded === 0) {
        showNoData();
        return;
      }

      if (!orders.length && append) {
        renderPagination();
        return;
      }

      const baseIndex = listLoaded;
      orders.forEach(function (order, idx) {
        tbody.appendChild(createLpoRow(order, baseIndex + idx + 1));
      });
      listLoaded += orders.length;

      updateCountLabel();
      reindex();
      updateFooterTotal();
      renderPagination();
    } catch (err) {
      if (replace) {
        tbody.innerHTML =
          '<tr id="lpoLoadError"><td colspan="9" style="text-align:center;padding:20px;color:#b91c1c;">' +
          escapeHtml(err && err.message ? err.message : 'Could not load list.') +
          '</td></tr>';
        listLoaded = 0;
      }
      updateScrollStatus(err && err.message ? err.message : 'Could not load list.', true);
      if (paginationEl) paginationEl.style.display = 'none';
    } finally {
      listLoading = false;
      listAppendMode = false;
    }
  }

  function reloadList() {
    listPage = 1;
    loadLpoPage(1, 'replace');
  }

  function goToPage(page) {
    const p = Math.max(1, Math.min(page, listTotalPages));
    loadLpoPage(p, 'replace');
  }

  function loadNextPage() {
    if (!hasMorePages() || listLoading) return;
    loadLpoPage(listPage + 1, 'append');
  }

  window.setLpoTab = function (tab) {
    if (tab === 'approved') activeTab = 'approved';
    else if (tab === 'canceled') activeTab = 'canceled';
    else activeTab = 'draft';
    if (tabDraft) tabDraft.classList.toggle('active', activeTab === 'draft');
    if (tabApproved) tabApproved.classList.toggle('active', activeTab === 'approved');
    if (tabCanceled) tabCanceled.classList.toggle('active', activeTab === 'canceled');
    reloadList();
  };

  window.filterRows = function () {
    reloadList();
  };

  window.clearFilters = function () {
    if (searchInput) searchInput.value = '';
    if (dateFromEl) dateFromEl.value = '';
    if (dateToEl) dateToEl.value = '';
    reloadList();
  };

  if (tbody) {
    tbody.addEventListener('click', function (ev) {
      const btn = ev.target.closest('.btn-cancel-po');
      if (!btn || !apiCancelPo) return;
      ev.preventDefault();
      const lpono = parseInt(btn.getAttribute('data-lpono') || '0', 10);
      if (!lpono) return;
      if (!window.confirm('Cancel LPO ' + lpono + '? It cannot be edited afterward.')) return;
      const remarks = (window.prompt('Cancellation remark (optional):', '') || '').trim();
      fetch(apiCancelPo, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lpono: lpono, remarks: remarks }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.success) reloadList();
          else alert(d.error || 'Cancel failed');
        })
        .catch(function () { alert('Cancel failed'); });
    });
  }

  if (table) {
    table.querySelectorAll('thead th[data-col]').forEach(function (th) {
      th.addEventListener('click', function () {
        const col = parseInt(this.getAttribute('data-col'), 10);
        if (sortCol === col) sortAsc = !sortAsc;
        else { sortCol = col; sortAsc = true; }
        table.querySelectorAll('thead th').forEach(function (h) {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        this.classList.add(sortAsc ? 'sort-asc' : 'sort-desc');
        const rows = Array.from(tbody.querySelectorAll('tr.lpo-row'));
        rows.sort(function (a, b) {
          const cellsA = a.querySelectorAll('td');
          const cellsB = b.querySelectorAll('td');
          const av = cellsA[col] ? cellsA[col].textContent.trim() : '';
          const bv = cellsB[col] ? cellsB[col].textContent.trim() : '';
          const an = parseFloat(av.replace(/,/g, ''));
          const bn = parseFloat(bv.replace(/,/g, ''));
          const cmp = isNaN(an) || isNaN(bn) ? av.localeCompare(bv) : an - bn;
          return sortAsc ? cmp : -cmp;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
        reindex();
      });
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(reloadList, 350);
    });
  }
  if (dateFromEl) dateFromEl.addEventListener('change', reloadList);
  if (dateToEl) dateToEl.addEventListener('change', reloadList);

  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (listPage > 1) goToPage(listPage - 1);
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      if (hasMorePages()) goToPage(listPage + 1);
    });
  }
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', loadNextPage);
  }
  if (scrollStatus) {
    scrollStatus.addEventListener('click', function () {
      if (hasMorePages() && !listLoading) loadNextPage();
    });
  }

  if (scrollSentinel && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) loadNextPage();
      });
    }, { root: null, rootMargin: '200px 0px', threshold: 0 });
    observer.observe(scrollSentinel);
  }

  listLoaded = tbody ? tbody.querySelectorAll('tr.lpo-row').length : 0;
  if (listLoaded > 0) {
    listPage = 1;
    updateCountLabel();
    updateFooterTotal();
    reindex();
    renderPagination();
    if (listTotalCount <= listLoaded && listLoaded >= perPage) {
      fetch(buildApiUrl(1), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.success) return;
          listTotalCount = Number(data.total_count || 0);
          listTotalPages = Math.max(1, Number(data.total_pages || 1) || 1);
          updateCountLabel();
          renderPagination();
        })
        .catch(function () { /* keep SSR estimate */ });
    }
  } else {
    reloadList();
  }
};

(function () {
  function start() {
    if (typeof window.bootLpoList === 'function') {
      window.bootLpoList();
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
