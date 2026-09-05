/**
 * Goods Receipt (GRN) list — Approved PO | Draft GRN | posted GRN | Reversed GRN.
 */
window.bootGrnList = function () {
  const pageRoot = document.querySelector('.grn-list-page');
  if (!pageRoot) return;
  if (pageRoot.dataset.grnListBooted === '1') return;
  pageRoot.dataset.grnListBooted = '1';

  const grnApi = pageRoot.dataset.grnApi || '/purchase/receipt/api/list';
  const poQueryTpl = pageRoot.dataset.poQueryUrlTpl || '';
  const grnQueryTpl = pageRoot.dataset.grnQueryUrlTpl || '';
  const grnPdfTpl = pageRoot.dataset.grnPdfUrlTpl || '';
  const grnNewLpoTpl = pageRoot.dataset.grnNewLpoUrlTpl || '';
  const grnDeleteApi = pageRoot.dataset.grnDeleteApi || '/purchase/receipt/api/delete';
  const grnNonceApi = pageRoot.dataset.grnNonceApi || '/purchase/receipt/api/refresh-save-nonce';
  const lpoPlaceholder = '999999999';

  const table = document.getElementById('grnTable');
  const tbody = document.getElementById('grnBody');
  const countEl = document.getElementById('grnCount');
  const totalEl = document.getElementById('grnTotalAmt');
  const tabPendingPo = document.getElementById('tabPendingPo');
  const tabDraftGrn = document.getElementById('tabDraftGrn');
  const tabPostedGrn = document.getElementById('tabPostedGrn');
  const tabReversedGrn = document.getElementById('tabReversedGrn');
  const btnSummaryPdf = document.getElementById('btnSummaryPdf');
  const searchInput = document.getElementById('grnSearch');
  const dateFromEl = document.getElementById('grnDateFrom');
  const dateToEl = document.getElementById('grnDateTo');
  const paginationEl = document.getElementById('grnPagination');
  const paginationInfo = document.getElementById('grnPaginationInfo');
  const pageLabel = document.getElementById('grnPageLabel');
  const prevBtn = document.getElementById('grnPrevPage');
  const nextBtn = document.getElementById('grnNextPage');
  const loadMoreBtn = document.getElementById('grnLoadMore');

  const VALID_TABS = ['pending', 'draft', 'posted', 'reversed'];
  let activeTab = 'pending';
  try {
    const savedTab = localStorage.getItem('grn_list_active_tab');
    if (savedTab === 'completed') activeTab = 'posted';
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

  window.__activeGrnTab = activeTab;

  function poUrl(lpono) {
    return poQueryTpl.replace(lpoPlaceholder, String(lpono));
  }
  function grnUrl(receiptno, forView) {
    let url = grnQueryTpl.replace('999999999', String(receiptno)).replace(lpoPlaceholder, String(receiptno));
    const sep = url.indexOf('?') >= 0 ? '&' : '?';
    url += sep + (forView ? 'view=1' : 'edit=1');
    return url;
  }
  function grnPdfUrl(receiptno) {
    if (!grnPdfTpl) return '';
    return grnPdfTpl.replace('999999999', String(receiptno)).replace(lpoPlaceholder, String(receiptno));
  }
  function grnNewUrl(lpono) {
    const base = grnNewLpoTpl || '';
    const lpoStr = encodeURIComponent(String(lpono ?? '').trim());
    if (base.indexOf('lpono=') >= 0) return base.replace(/lpono=[^&]*/, 'lpono=' + lpoStr);
    return base + (base.indexOf('?') >= 0 ? '&' : '?') + 'lpono=' + lpoStr;
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
    return grnApi + '?' + params.toString();
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
    tbody.querySelectorAll('tr.grn-row').forEach(function (row) {
      sum += parseFloat(row.getAttribute('data-amount') || 0);
    });
    totalEl.textContent = fmtAmount(sum);
  }

  function reindex() {
    if (!tbody) return;
    let i = 1;
    tbody.querySelectorAll('tr.grn-row').forEach(function (row) {
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

  function statusBadges(row, tabKind) {
    const parts = [];
    if (tabKind === 'reversed' || row.is_reversed) {
      parts.push('<span class="muted" style="font-size:11px;color:#b91c1c;" title="GRN reversed — number reserved">Reversed</span>');
      return parts.length ? ('<div style="margin-top:2px;">' + parts.join(' ') + '</div>') : '';
    }
    if (row.inventory_posted) {
      parts.push('<span class="muted" style="font-size:11px;color:#047857;" title="Stock posted">Inv posted</span>');
    } else {
      parts.push('<span class="muted" style="font-size:11px;color:#b45309;" title="Inventory not posted — open and Save">Not posted</span>');
    }
    if (row.account_posted) {
      parts.push('<span class="muted" style="font-size:11px;margin-left:4px;" title="Purchase Invoice posted">Acct</span>');
    }
    return parts.length ? ('<div style="margin-top:2px;">' + parts.join(' ') + '</div>') : '';
  }

  function createPendingRow(row, absoluteIndex) {
    const tr = document.createElement('tr');
    tr.className = 'grn-row grn-row-clickable';
    tr.dataset.kind = 'pending';
    const lpono = row.lpono;
    tr.dataset.docno = lpono;
    tr.dataset.date = fmtDate(row.lpodate);
    tr.dataset.supplier = row.suppliercode || '';
    tr.dataset.suppliername = row.suppliername || '';
    tr.dataset.discount = row.discount || 0;
    tr.dataset.amount = row.amount || 0;
    const viewPo = escapeHtml(poUrl(lpono));
    const createGrn = escapeHtml(grnNewUrl(lpono));
    tr.innerHTML =
      '<td class="sl-no">' + absoluteIndex + '</td>' +
      '<td><a class="grn-link" href="' + viewPo + '">' + escapeHtml(lpono) + '</a></td>' +
      '<td>' + escapeHtml(fmtDate(row.lpodate)) + '</td>' +
      '<td>-</td>' +
      '<td>' + escapeHtml(row.suppliercode || '-') + '</td>' +
      '<td>' + escapeHtml(row.suppliername || '-') + '</td>' +
      '<td class="num">' + fmtAmount(row.discount) + '</td>' +
      '<td class="num">' + fmtAmount(row.amount) + '</td>' +
      '<td>-</td>' +
      '<td style="text-align:center;"><a class="btn-view" href="' + createGrn + '">Create GRN</a></td>';
    return tr;
  }

  function createGrnRow(row, absoluteIndex, tabKind) {
    const tr = document.createElement('tr');
    tr.className = 'grn-row grn-row-clickable';
    tr.dataset.kind = tabKind;
    const receiptno = row.receiptno;
    tr.dataset.docno = receiptno;
    tr.dataset.date = fmtDate(row.receiptdate);
    tr.dataset.supplier = row.suppliercode || '';
    tr.dataset.suppliername = row.suppliername || '';
    tr.dataset.discount = row.discount || 0;
    tr.dataset.amount = row.amount || 0;
    tr.dataset.invoiceno = row.invoiceno || '';
    const isReversed = tabKind === 'reversed' || !!row.is_reversed;
    const acctPosted = !!(row.account_posted);
    const invPosted = !!(row.inventory_posted);
    const canEdit = !isReversed && row.can_edit !== false && !acctPosted && !invPosted;
    const canDelete = !isReversed && row.can_delete !== false && !acctPosted && !invPosted;
    const viewHref = escapeHtml(grnUrl(receiptno, true));
    const editHref = escapeHtml(grnUrl(receiptno, false));
    let actionHtml = '';
    actionHtml += '<a class="btn-view" href="' + viewHref + '" style="margin-right:6px;">View</a>';
    if (canEdit) {
      actionHtml += '<a class="btn-view" href="' + editHref + '" style="margin-right:6px;">Edit</a>';
    }
    const pdfHref = grnPdfUrl(receiptno);
    if (pdfHref && !isReversed) {
      actionHtml += '<a class="btn-view" href="' + escapeHtml(pdfHref) + '" target="_blank" rel="noopener" style="margin-right:6px;">PDF</a>';
    }
    if (canDelete) {
      const delHint = 'Delete draft GRN ' + receiptno + '?';
      actionHtml += '<button type="button" class="btn-view grn-btn-delete" data-receiptno="' + escapeHtml(receiptno) + '" data-inv-posted="0" style="border:1px solid #dc3545;color:#dc3545;background:#fff;">Delete</button>';
      tr.dataset.deleteHint = delHint;
    } else if (isReversed) {
      actionHtml += '<span class="muted" style="font-size:11px;color:#b91c1c;" title="Reversed GRN">Reversed</span>';
    } else if (acctPosted) {
      actionHtml += '<span class="muted" style="font-size:11px;" title="Posted via Purchase Invoice">Posted</span>';
    }
    tr.innerHTML =
      '<td class="sl-no">' + absoluteIndex + '</td>' +
      '<td><a class="grn-link" href="' + viewHref + '">' + escapeHtml(receiptno) + '</a>' + statusBadges(row, tabKind) + '</td>' +
      '<td>' + escapeHtml(fmtDate(row.receiptdate)) + '</td>' +
      '<td>' + escapeHtml(row.invoiceno || '-') + '</td>' +
      '<td>' + escapeHtml(row.suppliercode || '-') + '</td>' +
      '<td>' + escapeHtml(row.suppliername || '-') + '</td>' +
      '<td class="num">' + fmtAmount(row.discount) + '</td>' +
      '<td class="num">' + fmtAmount(row.amount) + '</td>' +
      '<td>' + escapeHtml(row.createdby || '-') + '</td>' +
      '<td style="text-align:center;">' + actionHtml + '</td>';
    return tr;
  }

  function showNoData() {
    if (!tbody) return;
    const msg = activeTab === 'pending'
      ? 'No approved purchase orders waiting for GRN.'
      : (activeTab === 'draft'
        ? 'No draft GRN found.'
        : (activeTab === 'reversed'
          ? 'No reversed GRN found.'
          : 'No GRN found.'));
    tbody.innerHTML =
      '<tr id="grnNoData"><td colspan="10" style="text-align:center;padding:20px;color:#6b7280;font-style:italic;">' + escapeHtml(msg) + '</td></tr>';
    listLoaded = 0;
    listTotalCount = 0;
    listTotalPages = 1;
    updateCountLabel();
    if (totalEl) totalEl.textContent = '0.00';
    renderPagination();
  }

  function setListLoadingUi(loading) {
    if (!tbody) return;
    tbody.classList.toggle('grn-list-is-loading', !!loading);
    if (table) table.classList.toggle('grn-list-is-loading', !!loading);
  }

  function showLoadingRow() {
    if (!tbody) return;
    tbody.innerHTML =
      '<tr id="grnLoading"><td colspan="10" style="text-align:center;padding:20px;color:#6b7280;">Loading…</td></tr>';
  }

  function openGrnRow(tr) {
    if (!tr) return;
    const kind = tr.dataset.kind || activeTab;
    const docno = tr.dataset.docno;
    if (!docno) return;
    if (kind === 'pending') {
      window.location.href = poUrl(docno);
      return;
    }
    window.location.href = grnUrl(docno, true);
  }

  async function loadGrnPage(page, mode) {
    if (!tbody || listLoading) return;
    const replace = mode !== 'append';
    if (!replace && !hasMorePages()) return;

    listLoading = true;
    if (replace) {
      if (listLoaded === 0) showLoadingRow();
      else setListLoadingUi(true);
    }

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
        let tr;
        if (activeTab === 'pending') {
          tr = createPendingRow(row, baseIndex + idx + 1);
        } else {
          tr = createGrnRow(row, baseIndex + idx + 1, activeTab);
        }
        tbody.appendChild(tr);
      });
      listLoaded += rows.length;

      updateCountLabel();
      reindex();
      updateFooterTotal();
      renderPagination();
    } catch (err) {
      if (replace) {
        tbody.innerHTML =
          '<tr id="grnLoadError"><td colspan="10" style="text-align:center;padding:20px;color:#b91c1c;">' +
          escapeHtml(err && err.message ? err.message : 'Could not load list.') +
          '</td></tr>';
        listLoaded = 0;
      }
      if (paginationEl) paginationEl.style.display = 'none';
    } finally {
      listLoading = false;
      setListLoadingUi(false);
    }
  }

  function reloadList() {
    listPage = 1;
    loadGrnPage(1, 'replace');
  }

  function goToPage(page) {
    loadGrnPage(Math.max(1, Math.min(page, listTotalPages)), 'replace');
  }

  function syncTabUi() {
    if (tabPendingPo) tabPendingPo.classList.toggle('active', activeTab === 'pending');
    if (tabDraftGrn) tabDraftGrn.classList.toggle('active', activeTab === 'draft');
    if (tabPostedGrn) tabPostedGrn.classList.toggle('active', activeTab === 'posted');
    if (tabReversedGrn) tabReversedGrn.classList.toggle('active', activeTab === 'reversed');
    if (btnSummaryPdf) btnSummaryPdf.style.display = activeTab === 'posted' ? '' : 'none';
  }

  window.setGrnTab = function (tab) {
    if (tab === 'completed') tab = 'posted';
    activeTab = VALID_TABS.indexOf(tab) >= 0 ? tab : 'pending';
    window.__activeGrnTab = activeTab;
    try { localStorage.setItem('grn_list_active_tab', activeTab); } catch (eSaveTab) {}
    syncTabUi();
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
      if (hasMorePages() && !listLoading) loadGrnPage(listPage + 1, 'append');
    });
  }

  function refreshSaveNonce() {
    return fetch(grnNonceApi, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && typeof d.save_nonce === 'string' && d.save_nonce) {
          window.__GLOBAL_SAVE_NONCE = d.save_nonce;
          return d.save_nonce;
        }
        return window.__GLOBAL_SAVE_NONCE || '';
      })
      .catch(function () { return window.__GLOBAL_SAVE_NONCE || ''; });
  }

  const grnDeleteModal = document.getElementById('grnDeleteModal');
  const grnDeleteModalOverlay = document.getElementById('grnDeleteModalOverlay');
  const grnDeleteModalClose = document.getElementById('grnDeleteModalClose');
  const grnDeleteModalMessage = document.getElementById('grnDeleteModalMessage');
  const grnDeletePasswordInput = document.getElementById('grnDeletePassword');
  const grnDeletePasswordError = document.getElementById('grnDeletePasswordError');
  const grnDeleteCancel = document.getElementById('grnDeleteCancel');
  const grnDeleteSubmit = document.getElementById('grnDeleteSubmit');
  let grnDeletePendingReceiptNo = 0;
  let grnDeletePendingBtn = null;

  function grnCloseDeleteModal() {
    if (grnDeleteModal) grnDeleteModal.classList.add('hidden');
    if (grnDeletePasswordInput) grnDeletePasswordInput.value = '';
    if (grnDeletePasswordError) {
      grnDeletePasswordError.style.display = 'none';
      grnDeletePasswordError.textContent = '';
    }
    grnDeletePendingReceiptNo = 0;
    grnDeletePendingBtn = null;
    if (grnDeleteSubmit) grnDeleteSubmit.disabled = false;
  }

  function grnOpenDeleteModal(receiptno, hint, delBtn) {
    if (!grnDeleteModal) return;
    grnDeletePendingReceiptNo = receiptno;
    grnDeletePendingBtn = delBtn || null;
    if (grnDeleteModalMessage) grnDeleteModalMessage.textContent = hint || ('Delete GRN ' + receiptno + '?');
    grnDeleteModal.classList.remove('hidden');
    if (grnDeletePasswordInput) {
      grnDeletePasswordInput.value = '';
      window.setTimeout(function () { grnDeletePasswordInput.focus(); }, 0);
    }
  }

  function grnSubmitDelete() {
    const rno = grnDeletePendingReceiptNo;
    if (!rno) return;
    const pwd = (grnDeletePasswordInput && grnDeletePasswordInput.value || '').trim();
    if (!pwd) {
      if (grnDeletePasswordError) {
        grnDeletePasswordError.textContent = 'Enter your password.';
        grnDeletePasswordError.style.display = 'block';
      }
      if (grnDeletePasswordInput) grnDeletePasswordInput.focus();
      return;
    }
    if (grnDeletePasswordError) {
      grnDeletePasswordError.style.display = 'none';
      grnDeletePasswordError.textContent = '';
    }
    if (grnDeleteSubmit) grnDeleteSubmit.disabled = true;
    if (grnDeletePendingBtn) grnDeletePendingBtn.disabled = true;
    refreshSaveNonce().then(function (nonce) {
      return fetch(grnDeleteApi, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receiptno: rno, save_nonce: nonce, password: pwd }),
      });
    }).then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && typeof data.save_nonce === 'string' && data.save_nonce) {
          window.__GLOBAL_SAVE_NONCE = data.save_nonce;
        }
        if (!data || !data.success) {
          const errMsg = (data && data.error) || 'Delete failed.';
          if (grnDeletePasswordError) {
            grnDeletePasswordError.textContent = errMsg;
            grnDeletePasswordError.style.display = 'block';
          } else {
            alert(errMsg);
          }
          if (grnDeleteSubmit) grnDeleteSubmit.disabled = false;
          if (grnDeletePendingBtn) grnDeletePendingBtn.disabled = false;
          return;
        }
        grnCloseDeleteModal();
        reloadList();
      })
      .catch(function () {
        if (grnDeletePasswordError) {
          grnDeletePasswordError.textContent = 'Delete failed.';
          grnDeletePasswordError.style.display = 'block';
        } else {
          alert('Delete failed.');
        }
        if (grnDeleteSubmit) grnDeleteSubmit.disabled = false;
        if (grnDeletePendingBtn) grnDeletePendingBtn.disabled = false;
      });
  }

  if (grnDeleteCancel) grnDeleteCancel.addEventListener('click', grnCloseDeleteModal);
  if (grnDeleteModalClose) grnDeleteModalClose.addEventListener('click', grnCloseDeleteModal);
  if (grnDeleteModalOverlay) grnDeleteModalOverlay.addEventListener('click', grnCloseDeleteModal);
  if (grnDeleteSubmit) grnDeleteSubmit.addEventListener('click', grnSubmitDelete);
  if (grnDeletePasswordInput) {
    grnDeletePasswordInput.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        grnSubmitDelete();
      }
    });
  }

  if (tbody) {
    tbody.addEventListener('click', function (ev) {
      const delBtn = ev.target && ev.target.closest ? ev.target.closest('.grn-btn-delete') : null;
      if (delBtn) {
        ev.preventDefault();
        const rno = String(delBtn.getAttribute('data-receiptno') || '').trim();
        if (!rno) return;
        const tr = delBtn.closest('tr');
        const hint = (tr && tr.dataset.deleteHint) || ('Delete GRN ' + rno + '?');
        grnOpenDeleteModal(rno, hint, delBtn);
        return;
      }
      if (ev.target.closest('a, button')) return;
      const tr = ev.target.closest('tr.grn-row-clickable');
      if (!tr) return;
      openGrnRow(tr);
    });
    tbody.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      const tr = ev.target.closest('tr.grn-row-clickable');
      if (!tr || !tbody.contains(tr)) return;
      if (ev.target.closest('a, button, input, select, textarea')) return;
      ev.preventDefault();
      openGrnRow(tr);
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
        const rows = Array.from(tbody.querySelectorAll('tr.grn-row'));
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
  window.__activeGrnTab = activeTab;
  reloadList();
};

(function () {
  function start() {
    if (typeof window.bootGrnList === 'function') window.bootGrnList();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
