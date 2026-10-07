/**
 * Purchase Return list — Draft | Approved | All (GRN list style).
 */
window.bootPrList = function () {
  const pageRoot = document.querySelector('.pr-list-page');
  if (!pageRoot) return;

  const prApi = pageRoot.dataset.prApi || '/purchase/return/api/list';
  const orderQueryTpl = pageRoot.dataset.returnOrderQueryUrlTpl || '';
  const returnQueryTpl = pageRoot.dataset.returnQueryUrlTpl || '';
  const orderPdfTpl = pageRoot.dataset.returnOrderPdfUrlTpl || '';
  const returnPdfTpl = pageRoot.dataset.returnPdfUrlTpl || '';
  const requestApproveApi = pageRoot.dataset.requestApproveApi || '';
  const requestCancelApi = pageRoot.dataset.requestCancelApi || '';
  const requestPostStockApi = pageRoot.dataset.requestPostStockApi || '';
  const prDeleteApi = pageRoot.dataset.prDeleteApi || '';
  const prNonceApi = pageRoot.dataset.prRefreshNonceApi || '';
  const placeholder = 'PR-000001';

  const table = document.getElementById('prTable');
  const tbody = document.getElementById('prBody');
  const countEl = document.getElementById('prCount');
  const totalEl = document.getElementById('prTotalAmt');
  const tabDraft = document.getElementById('tabPrDraft');
  const tabPosted = document.getElementById('tabPrPosted');
  const tabPending = document.getElementById('tabPrPending');
  const btnSummaryPdf = document.getElementById('btnPrSummaryPdf');
  const searchInput = document.getElementById('prSearch');
  const dateFromEl = document.getElementById('prDateFrom');
  const dateToEl = document.getElementById('prDateTo');
  const paginationEl = document.getElementById('prPagination');
  const paginationInfo = document.getElementById('prPaginationInfo');
  const pageLabel = document.getElementById('prPageLabel');
  const prevBtn = document.getElementById('prPrevPage');
  const nextBtn = document.getElementById('prNextPage');
  const loadMoreBtn = document.getElementById('prLoadMore');

  const VALID_TABS = ['pending', 'draft', 'posted'];
  let activeTab = 'draft';
  try {
    const savedTab = localStorage.getItem('pr_list_active_tab');
    if (savedTab === 'all') activeTab = 'draft';
    else if (VALID_TABS.indexOf(savedTab) >= 0) activeTab = savedTab;
  } catch (eTab) {}

  let sortCol = -1;
  let sortAsc = true;
  let listLoading = false;
  let listPage = 1;
  let listTotalPages = 1;
  let listTotalCount = 0;
  let listLoaded = 0;
  const perPage = Math.max(20, parseInt(pageRoot.dataset.itemsPerPage || '50', 10) || 50);
  let searchDebounce = null;

  window.__activePrTab = activeTab;

  function tplUrl(tpl, docNo) {
    if (!tpl) return '';
    const s = String(docNo ?? '').trim();
    return tpl.replace(placeholder, encodeURIComponent(s)).replace('999999999', encodeURIComponent(s));
  }

  function orderUrl(no, forView) {
    let url = tplUrl(orderQueryTpl, no);
    if (!url) return '#';
    const sep = url.indexOf('?') >= 0 ? '&' : '?';
    url += sep + (forView ? 'view=1' : 'edit=1');
    return url;
  }

  function returnUrl(no, forView) {
    let url = tplUrl(returnQueryTpl, no);
    if (!url) return '#';
    if (forView) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'view=1';
    return url;
  }

  function orderPdfUrl(no) {
    return tplUrl(orderPdfTpl, no);
  }

  function returnPdfUrl(no) {
    return tplUrl(returnPdfTpl, no);
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

  function fmtDate(val) {
    if (!val) return '-';
    const s = String(val);
    return s.length >= 10 ? s.slice(0, 10) : s;
  }

  function primaryDocNo(row) {
    return row.posted_stock_no || row.pr_doc_no || row.goodsreturnno || '';
  }

  function displayDocNo(row) {
    return row.display_return_no || primaryDocNo(row) || '';
  }

  function docHref(row, forView) {
    const kind = row.row_kind || '';
    const prNo = row.posted_stock_no || row.pr_doc_no;
    const req = row.goodsreturnno;
    if (prNo && (kind === 'pr_draft' || kind === 'pr_posted' || kind === 'posted_linked')) {
      return returnUrl(prNo, forView);
    }
    if (req) return orderUrl(req, forView);
    if (prNo) return returnUrl(prNo, forView);
    return '#';
  }

  function hasMorePages() {
    return listPage < listTotalPages;
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
    return prApi + '?' + params.toString();
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

  function updateFooterTotal() {
    if (!totalEl || !tbody) return;
    let sum = 0;
    tbody.querySelectorAll('tr.pr-row').forEach(function (row) {
      sum += parseFloat(row.getAttribute('data-amount') || 0);
    });
    totalEl.textContent = fmtAmount(sum);
  }

  function reindex() {
    if (!tbody) return;
    let i = 1;
    tbody.querySelectorAll('tr.pr-row').forEach(function (row) {
      const sl = row.querySelector('.sl-no');
      if (sl) sl.textContent = String(i++);
    });
  }

  function renderPagination() {
    if (!paginationEl) return;
    if (listTotalCount <= 0) {
      paginationEl.style.display = 'none';
      return;
    }
    paginationEl.style.display = '';
    const rowStart = listLoaded > 0 ? (listPage - 1) * perPage + 1 : 0;
    const rowEnd = listLoaded > 0 ? rowStart + listLoaded - 1 : 0;
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
  }

  function statusBadges(row) {
    const kind = row.row_kind || '';
    const parts = [];
    if (kind === 'request_draft' || kind === 'pr_draft') {
      parts.push('<span class="muted" style="font-size:11px;color:#4338ca;" title="Draft">Draft</span>');
    } else if (kind === 'request_approved') {
      parts.push('<span class="muted" style="font-size:11px;color:#b45309;" title="Approved — stock pending">Approved</span>');
    } else if (kind === 'posted_linked' || kind === 'pr_posted') {
      parts.push('<span class="muted" style="font-size:11px;color:#047857;" title="Stock posted">Inv posted</span>');
      if (row.accounts_posted) {
        parts.push('<span class="muted" style="font-size:11px;margin-left:4px;" title="Accounts posted">Acct</span>');
      } else {
        parts.push('<span class="muted" style="font-size:11px;margin-left:4px;color:#b45309;" title="GL pending">GL pending</span>');
      }
    }
    return parts.length ? ('<div style="margin-top:2px;">' + parts.join(' ') + '</div>') : '';
  }

  function actionHtml(row) {
    const kind = row.row_kind || '';
    const req = row.goodsreturnno;
    const prNo = row.posted_stock_no || row.pr_doc_no;
    const bits = [];
    const viewHref = escapeHtml(docHref(row, true));
    const editHref = escapeHtml(docHref(row, false));
    const docNo = primaryDocNo(row);
    const showNo = displayDocNo(row);

    bits.push('<a class="btn-view" href="' + viewHref + '" style="margin-right:6px;">View</a>');

    if (kind === 'request_draft' || kind === 'pr_draft') {
      bits.push('<a class="btn-view" href="' + editHref + '" style="margin-right:6px;">Edit</a>');
    }

    const pdf = (prNo && kind !== 'request_draft' && kind !== 'request_approved')
      ? returnPdfUrl(prNo)
      : (req ? orderPdfUrl(req) : '');
    if (pdf) {
      bits.push('<a class="btn-view" href="' + escapeHtml(pdf) + '" target="_blank" rel="noopener" style="margin-right:6px;">PDF</a>');
    }

    if (kind === 'request_draft' && activeTab === 'draft' && req) {
      bits.push('<button type="button" class="btn-view btn-approve-return-request" data-goodsreturnno="' + escapeHtml(String(req)) + '" style="margin-right:6px;border-color:#bbf7d0;color:#15803d;">Approve</button>');
      bits.push('<button type="button" class="btn-view btn-cancel-return-request" data-goodsreturnno="' + escapeHtml(String(req)) + '" style="border-color:#fecaca;color:#b91c1c;">Cancel</button>');
    }

    if (kind === 'request_approved' && activeTab === 'draft' && req) {
      bits.push('<button type="button" class="btn-view btn-post-stock-return-request" data-goodsreturnno="' + escapeHtml(String(req)) + '">Post stock</button>');
    }

    if (kind === 'pr_draft' && prNo) {
      bits.push('<button type="button" class="btn-view pr-btn-delete" data-goodsreturnno="' + escapeHtml(String(prNo)) + '" style="border:1px solid #dc3545;color:#dc3545;background:#fff;margin-left:6px;">Delete</button>');
    }

    return bits.join('');
  }

  function createRow(row, absoluteIndex) {
    const tr = document.createElement('tr');
    tr.className = 'pr-row';
    const docNo = primaryDocNo(row);
    const showNo = displayDocNo(row);
    tr.dataset.docno = String(docNo || '');
    tr.dataset.date = fmtDate(row.returndate);
    tr.dataset.supplier = row.suppliercode || '';
    tr.dataset.suppliername = row.suppliername || '';
    tr.dataset.discount = row.discount || 0;
    tr.dataset.amount = row.returnamount || 0;
    tr.dataset.grnref = row.receiptno || '';
    const viewHref = escapeHtml(docHref(row, true));
    tr.innerHTML =
      '<td class="sl-no">' + absoluteIndex + '</td>' +
      '<td><a class="grn-link" href="' + viewHref + '">' + escapeHtml(showNo || '-') + '</a>' + statusBadges(row) + '</td>' +
      '<td>' + escapeHtml(fmtDate(row.returndate)) + '</td>' +
      '<td>' + escapeHtml(row.receiptno || '-') + '</td>' +
      '<td>' + escapeHtml(row.suppliercode || '-') + '</td>' +
      '<td>' + escapeHtml(row.suppliername || '-') + '</td>' +
      '<td class="num">' + fmtAmount(row.discount) + '</td>' +
      '<td class="num">' + fmtAmount(row.returnamount) + '</td>' +
      '<td>' + escapeHtml(row.createdby || '-') + '</td>' +
      '<td style="text-align:center;">' + actionHtml(row) + '</td>';
    return tr;
  }

  function showNoData() {
    if (!tbody) return;
    const msg = activeTab === 'draft'
      ? 'No draft or approved return requests waiting for stock post found.'
      : (activeTab === 'pending'
        ? 'No purchase returns with inventory posted and accounts pending found.'
        : 'No posted purchase returns found.');
    tbody.innerHTML =
      '<tr id="prNoData"><td colspan="10" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">' + escapeHtml(msg) + '</td></tr>';
    listLoaded = 0;
    listTotalCount = 0;
    listTotalPages = 1;
    updateCountLabel();
    if (totalEl) totalEl.textContent = '0.00';
    renderPagination();
  }

  function showLoadingRow() {
    if (!tbody) return;
    tbody.innerHTML =
      '<tr id="prLoading"><td colspan="10" style="text-align:center;padding:20px;color:#6b7280;">Loading…</td></tr>';
    if (countEl) countEl.textContent = 'Loading…';
  }

  async function loadPrPage(page, mode) {
    if (!tbody || listLoading) return;
    const replace = mode !== 'append';
    if (!replace && !hasMorePages()) return;

    listLoading = true;
    if (replace) showLoadingRow();

    try {
      const res = await fetch(buildApiUrl(page), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok || !data.success) {
        throw new Error(data.error || data.message || 'Load failed (' + res.status + ')');
      }

      const rows = Array.isArray(data.rows) ? data.rows : [];
      listPage = Number(data.page || page) || page;
      listTotalPages = Math.max(1, Number(data.total_pages || 1) || 1);
      listTotalCount = Number(data.total_count || 0);

      if (replace) {
        tbody.innerHTML = '';
        listLoaded = 0;
      }

      if (!rows.length && listLoaded === 0) {
        showNoData();
        return;
      }

      const baseIndex = listLoaded;
      rows.forEach(function (row, idx) {
        tbody.appendChild(createRow(row, baseIndex + idx + 1));
      });
      listLoaded += rows.length;

      updateCountLabel();
      reindex();
      updateFooterTotal();
      renderPagination();
    } catch (err) {
      if (replace) {
        tbody.innerHTML =
          '<tr id="prLoadError"><td colspan="10" style="text-align:center;padding:20px;color:#b91c1c;">' +
          escapeHtml(err && err.message ? err.message : 'Could not load list.') +
          '</td></tr>';
        listLoaded = 0;
      }
      if (paginationEl) paginationEl.style.display = 'none';
    } finally {
      listLoading = false;
    }
  }

  function reloadList() {
    listPage = 1;
    loadPrPage(1, 'replace');
  }

  function goToPage(page) {
    loadPrPage(Math.max(1, Math.min(page, listTotalPages)), 'replace');
  }

  function syncTabUi() {
    if (tabDraft) tabDraft.classList.toggle('active', activeTab === 'draft');
    if (tabPosted) tabPosted.classList.toggle('active', activeTab === 'posted');
    if (tabPending) tabPending.classList.toggle('active', activeTab === 'pending');
    if (btnSummaryPdf) btnSummaryPdf.style.display = activeTab === 'posted' ? '' : 'none';
  }

  window.setPrTab = function (tab) {
    activeTab = VALID_TABS.indexOf(tab) >= 0 ? tab : 'draft';
    window.__activePrTab = activeTab;
    try { localStorage.setItem('pr_list_active_tab', activeTab); } catch (eSave) {}
    syncTabUi();
    reloadList();
  };

  window.clearPrFilters = function () {
    if (searchInput) searchInput.value = '';
    if (dateFromEl) dateFromEl.value = '';
    if (dateToEl) dateToEl.value = '';
    reloadList();
  };

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
    loadMoreBtn.addEventListener('click', function () {
      if (hasMorePages() && !listLoading) loadPrPage(listPage + 1, 'append');
    });
  }

  document.addEventListener('click', function (e) {
    const postStockBtn = e.target.closest('.btn-post-stock-return-request');
    if (postStockBtn && requestPostStockApi) {
      e.preventDefault();
      const grn = String(postStockBtn.getAttribute('data-goodsreturnno') || '').trim();
      if (!grn || !window.confirm('Post inventory for return request ' + grn + '?')) return;
      fetch(requestPostStockApi, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goodsreturnno: grn }),
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.success) {
            alert(d.message || ('Posted as Purchase Return #' + (d.posted_return_no || '')));
            reloadList();
          } else alert(d.error || 'Stock post failed');
        })
        .catch(function () { alert('Stock post failed'); });
      return;
    }
    const approveBtn = e.target.closest('.btn-approve-return-request');
    const cancelBtn = e.target.closest('.btn-cancel-return-request');
    const btn = approveBtn || cancelBtn;
    if (!btn) return;
    e.preventDefault();
    const goodsreturnno = String(btn.getAttribute('data-goodsreturnno') || '').trim();
    if (!goodsreturnno) return;
    const isCancel = !!cancelBtn;
    const apiUrl = isCancel ? requestCancelApi : requestApproveApi;
    if (!apiUrl) return;
    const approveMsg = 'Approve purchase return ' + goodsreturnno + ' and post inventory to stock?\n\nThis creates the Purchase Return document and deducts stock.';
    if (!window.confirm(isCancel ? ('Cancel purchase return ' + goodsreturnno + '?') : approveMsg)) return;
    const remarks = (window.prompt('Remark (optional):', '') || '').trim();
    fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goodsreturnno: goodsreturnno, remarks: remarks }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.success) {
          if (!isCancel && d.message) alert(d.message);
          reloadList();
        } else alert(d.error || ('Unable to ' + (isCancel ? 'cancel' : 'approve') + ' return'));
      })
      .catch(function () { alert('Request failed'); });
  });

  function prListRefreshNonce() {
    if (!prNonceApi) return Promise.resolve(window.__GLOBAL_SAVE_NONCE || '');
    return fetch(prNonceApi, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.save_nonce) window.__GLOBAL_SAVE_NONCE = d.save_nonce;
        return window.__GLOBAL_SAVE_NONCE || '';
      })
      .catch(function () { return window.__GLOBAL_SAVE_NONCE || ''; });
  }

  const prDeleteModal = document.getElementById('prDeleteModal');
  const prDeleteModalOverlay = document.getElementById('prDeleteModalOverlay');
  const prDeleteModalClose = document.getElementById('prDeleteModalClose');
  const prDeleteModalMessage = document.getElementById('prDeleteModalMessage');
  const prDeletePasswordInput = document.getElementById('prDeletePassword');
  const prDeletePasswordError = document.getElementById('prDeletePasswordError');
  const prDeleteCancel = document.getElementById('prDeleteCancel');
  const prDeleteSubmit = document.getElementById('prDeleteSubmit');
  let prDeletePendingNo = '';
  let prDeletePendingBtn = null;

  function prListCloseDeleteModal() {
    if (prDeleteModal) prDeleteModal.classList.add('hidden');
    if (prDeletePasswordInput) prDeletePasswordInput.value = '';
    if (prDeletePasswordError) {
      prDeletePasswordError.style.display = 'none';
      prDeletePasswordError.textContent = '';
    }
    prDeletePendingNo = '';
    prDeletePendingBtn = null;
    if (prDeleteSubmit) prDeleteSubmit.disabled = false;
  }

  function prListOpenDeleteModal(goodsreturnno, delBtn) {
    if (!prDeleteModal) return;
    prDeletePendingNo = String(goodsreturnno || '').trim();
    prDeletePendingBtn = delBtn || null;
    if (prDeleteModalMessage) {
      prDeleteModalMessage.textContent = 'Delete draft Purchase Return ' + prDeletePendingNo + '?';
    }
    prDeleteModal.classList.remove('hidden');
    if (prDeletePasswordInput) {
      prDeletePasswordInput.value = '';
      setTimeout(function () { prDeletePasswordInput.focus(); }, 0);
    }
  }

  function prListSubmitDelete() {
    const rno = prDeletePendingNo;
    if (!rno) return;
    const pwd = (prDeletePasswordInput && prDeletePasswordInput.value || '').trim();
    if (!pwd) {
      if (prDeletePasswordError) {
        prDeletePasswordError.textContent = 'Enter your password.';
        prDeletePasswordError.style.display = 'block';
      }
      return;
    }
    if (prDeleteSubmit) prDeleteSubmit.disabled = true;
    if (prDeletePendingBtn) prDeletePendingBtn.disabled = true;
    prListRefreshNonce().then(function (nonce) {
      return fetch(prDeleteApi, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goodsreturnno: rno, save_nonce: nonce, password: pwd }),
      });
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.save_nonce) window.__GLOBAL_SAVE_NONCE = data.save_nonce;
        if (!data || !data.success) {
          if (prDeletePasswordError) {
            prDeletePasswordError.textContent = (data && data.error) || 'Delete failed.';
            prDeletePasswordError.style.display = 'block';
          }
          if (prDeleteSubmit) prDeleteSubmit.disabled = false;
          if (prDeletePendingBtn) prDeletePendingBtn.disabled = false;
          return;
        }
        prListCloseDeleteModal();
        reloadList();
      })
      .catch(function () {
        if (prDeletePasswordError) {
          prDeletePasswordError.textContent = 'Delete failed.';
          prDeletePasswordError.style.display = 'block';
        }
        if (prDeleteSubmit) prDeleteSubmit.disabled = false;
        if (prDeletePendingBtn) prDeletePendingBtn.disabled = false;
      });
  }

  if (prDeleteApi && tbody) {
    tbody.addEventListener('click', function (e) {
      const delBtn = e.target.closest('.pr-btn-delete');
      if (!delBtn) return;
      e.preventDefault();
      const grn = String(delBtn.getAttribute('data-goodsreturnno') || '').trim();
      if (grn) prListOpenDeleteModal(grn, delBtn);
    });
    if (prDeleteCancel) prDeleteCancel.addEventListener('click', prListCloseDeleteModal);
    if (prDeleteModalClose) prDeleteModalClose.addEventListener('click', prListCloseDeleteModal);
    if (prDeleteModalOverlay) prDeleteModalOverlay.addEventListener('click', prListCloseDeleteModal);
    if (prDeleteSubmit) prDeleteSubmit.addEventListener('click', prListSubmitDelete);
    if (prDeletePasswordInput) {
      prDeletePasswordInput.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); prListSubmitDelete(); }
      });
    }
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
        const rows = Array.from(tbody.querySelectorAll('tr.pr-row'));
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

  listTotalPages = 1;
  listTotalCount = 0;
  syncTabUi();
  window.__activePrTab = activeTab;
  reloadList();
};

(function () {
  function start() {
    if (typeof window.bootPrList === 'function') window.bootPrList();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
