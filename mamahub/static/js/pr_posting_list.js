/**
 * Purchase Return Posting — pending (approved + GL) | posted GL.
 */
window.bootPrPostingList = function () {
  const pageRoot = document.querySelector('.pr-posting-page');
  if (!pageRoot) return;

  const apiUrl = pageRoot.dataset.prPostingApi || '/purchase/return/posting/api/list';
  const bulkPostUrl = pageRoot.dataset.bulkPostApi || '';
  const changeDateUrl = pageRoot.dataset.changeDateApi || '';
  const reversePendingUrl = pageRoot.dataset.reversePendingApi || '';
  const orderQueryTpl = pageRoot.dataset.returnOrderQueryUrlTpl || '';
  const returnQueryTpl = pageRoot.dataset.returnQueryUrlTpl || '';
  const prNewTpl = pageRoot.dataset.prNewUrlTpl || '';
  const loginUser = pageRoot.dataset.loginUser || '';
  const placeholder = '999999999';
  function prDocNo(raw) {
    return String(raw || '').trim();
  }

  function prDocNoValid(raw) {
    const s = prDocNo(raw);
    if (!s) return false;
    if (/^PR-/i.test(s)) return true;
    const n = parseInt(s, 10);
    return !isNaN(n) && n > 0;
  }

  const perPage = Math.max(20, parseInt(pageRoot.dataset.itemsPerPage || '50', 10) || 50);

  let closedPeriods = [];
  try {
    closedPeriods = (window.PeriodDateGuard && window.PeriodDateGuard.fromJsonScript)
      ? window.PeriodDateGuard.fromJsonScript('prpClosedPeriodsJson')
      : [];
  } catch (eCp) { closedPeriods = []; }

  const tabPending = document.querySelector('.po-tab[data-tab="pendingTab"]');
  const tabPosted = document.querySelector('.po-tab[data-tab="postedTab"]');
  const pendingPane = document.getElementById('pendingTab');
  const postedPane = document.getElementById('postedTab');
  const approvedBody = document.getElementById('prpApprovedBody');
  const approvedSection = document.getElementById('prpApprovedSection');
  const approvedTitle = document.getElementById('prpApprovedTitle');
  const glBody = document.getElementById('prpGlBody');
  const postedBody = document.getElementById('prpPostedBody');
  const searchInput = document.getElementById('prpSearch');
  const dateFromEl = document.getElementById('prpDateFrom');
  const dateToEl = document.getElementById('prpDateTo');
  const btnPost = document.getElementById('btnPostSelected');
  const selAll = document.getElementById('pendingSelectAll');
  const selInfo = document.getElementById('pendingSelInfo');
  const pendingTotalEl = document.getElementById('pendingTotalAmt');
  const postedTotalEl = document.getElementById('postedTotalAmt');
  const glSectionTitle = document.getElementById('prpGlTitle');
  const glHint = document.getElementById('prpGlHint');
  const paginationEl = document.getElementById('prpPagination');
  const paginationInfo = document.getElementById('prpPaginationInfo');
  const pageLabel = document.getElementById('prpPageLabel');
  const prevBtn = document.getElementById('prpPrevPage');
  const nextBtn = document.getElementById('prpNextPage');
  const postModal = document.getElementById('prpPostModal');
  const postModalTitle = document.getElementById('prpPostModalTitle');
  const postModalMsg = document.getElementById('prpPostModalMsg');
  const postModalActions = document.getElementById('prpPostModalActions');
  const postModalClose = document.getElementById('prpPostModalClose');
  const actionModal = document.getElementById('prpActionModal');
  const actionDateWrap = document.getElementById('prpActionDateWrap');
  const actionNewDate = document.getElementById('prpActionNewDate');
  const actionAlsoReturn = document.getElementById('prpActionAlsoReturn');
  const actionPassword = document.getElementById('prpActionPassword');
  const actionPasswordError = document.getElementById('prpActionPasswordError');
  const actionCancel = document.getElementById('prpActionCancel');
  const actionConfirm = document.getElementById('prpActionConfirm');
  const actionOverlay = document.getElementById('prpActionModalOverlay');

  let activeTab = 'pending';
  let listPage = 1;
  let listTotalPages = 1;
  let listTotalCount = 0;
  let glLoaded = 0;
  let listLoading = false;
  let searchDebounce = null;
  let prpAction = null;
  let pendingSort = { key: '', asc: true };
  let postedSort = { key: '', asc: true };

  function escapeHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function fmtAmount(v) {
    const n = Number(v);
    return (Number.isFinite(n) ? n : 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtDate(v) {
    if (!v) return '—';
    const s = String(v);
    return s.length >= 10 ? s.slice(0, 10) : s;
  }

  function orderUrl(no) {
    return orderQueryTpl.replace(placeholder, String(no));
  }

  function returnUrl(no, view) {
    let url = returnQueryTpl.replace(placeholder, String(no));
    if (view) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'view=1';
    return url;
  }

  function prNewUrl(reqNo) {
    return prNewTpl.replace(placeholder, String(reqNo)).replace(/return_order_no=\d+/, 'return_order_no=' + String(reqNo));
  }

  function buildApiUrl(page) {
    const p = new URLSearchParams();
    p.set('page', String(page));
    p.set('per_page', String(perPage));
    p.set('tab', activeTab);
    const q = (searchInput && searchInput.value || '').trim();
    if (q) p.set('search', q);
    if (dateFromEl && dateFromEl.value) p.set('date_from', dateFromEl.value);
    if (dateToEl && dateToEl.value) p.set('date_to', dateToEl.value);
    return apiUrl + '?' + p.toString();
  }

  function openPostModal(title, message, showActions) {
    if (postModalTitle) postModalTitle.textContent = title || 'Posting Returns';
    if (postModalMsg) postModalMsg.innerHTML = message || '';
    if (postModalActions) postModalActions.style.display = showActions ? '' : 'none';
    if (postModal) { postModal.classList.add('show'); postModal.setAttribute('aria-hidden', 'false'); }
  }

  function closePostModal() {
    if (postModal) { postModal.classList.remove('show'); postModal.setAttribute('aria-hidden', 'true'); }
  }

  function updateSelInfo() {
    const checks = Array.from(document.querySelectorAll('#glPendingTable tbody .pending-check'));
    const selected = checks.filter(function (c) { return c.checked; });
    checks.forEach(function (c) {
      const tr = c.closest('tr');
      if (tr) tr.classList.toggle('row-selected', c.checked);
    });
    if (selInfo) selInfo.textContent = selected.length + ' selected for GL';
    if (selAll) {
      selAll.checked = checks.length > 0 && selected.length === checks.length;
    }
    if (btnPost) btnPost.disabled = checks.length === 0;
  }

  function refreshGlTotal() {
    if (!pendingTotalEl || !glBody) return;
    let sum = 0;
    glBody.querySelectorAll('tr[data-totalamount]').forEach(function (tr) {
      sum += parseFloat(tr.getAttribute('data-totalamount') || '0') || 0;
    });
    pendingTotalEl.textContent = fmtAmount(sum);
  }

  function refreshPostedTotal() {
    if (!postedTotalEl || !postedBody) return;
    let sum = 0;
    postedBody.querySelectorAll('tr[data-totalamount]').forEach(function (tr) {
      sum += parseFloat(tr.getAttribute('data-totalamount') || '0') || 0;
    });
    postedTotalEl.textContent = fmtAmount(sum);
  }

  function renderApprovedRows(rows) {
    if (!approvedBody) return;
    if (!rows || !rows.length) {
      approvedBody.innerHTML = '';
      if (approvedSection) approvedSection.style.display = 'none';
      return;
    }
    if (approvedSection) approvedSection.style.display = '';
    if (approvedTitle) approvedTitle.textContent = 'Step 1 — Approved return requests (' + rows.length + ')';
    approvedBody.innerHTML = rows.map(function (r) {
      const req = r.request_no || r.goodsreturnno;
      return '<tr data-totalamount="' + escapeHtml(r.totalamount || 0) + '">' +
        '<td><a class="pi-link" href="' + escapeHtml(orderUrl(req)) + '">' + escapeHtml(req) + '</a></td>' +
        '<td>' + escapeHtml(fmtDate(r.returndate)) + '</td>' +
        '<td>' + escapeHtml((r.suppliercode || '') + (r.suppliername ? ' — ' + r.suppliername : '')) + '</td>' +
        '<td class="num">' + fmtAmount(r.discount) + '</td>' +
        '<td class="num">' + fmtAmount(r.totalamount) + '</td>' +
        '<td><span class="prp-status-pill prp-status-pill--approved">Approved</span></td>' +
        '<td><a class="page-po__btn-secondary" href="' + escapeHtml(prNewUrl(req)) + '">Post stock</a></td>' +
        '</tr>';
    }).join('');
  }

  function renderGlRows(rows) {
    if (!glBody) return;
    if (!rows || !rows.length) {
      glBody.innerHTML = '<tr class="prp-gl-empty"><td colspan="10" style="text-align:center;padding:16px;color:#6b7280;font-style:italic;">No returns ready for GL posting.</td></tr>';
      refreshGlTotal();
      updateSelInfo();
      return;
    }
    glBody.innerHTML = rows.map(function (r) {
      const gn = r.goodsreturnno;
      const showNo = r.display_return_no || gn;
      const showVoucher = r.voucher_no || showNo;
      const pdata = fmtDate(r.postingdate || r.returndate);
      return '<tr data-goodsreturnno="' + escapeHtml(gn) + '" data-returndate="' + escapeHtml(fmtDate(r.returndate)) + '" data-postingdate="' + escapeHtml(pdata) + '" data-suppliercode="' + escapeHtml(r.suppliercode || '') + '" data-suppliername="' + escapeHtml(r.suppliername || '') + '" data-discount="' + escapeHtml(r.discount || 0) + '" data-totalamount="' + escapeHtml(r.totalamount || 0) + '" data-voucher_no="' + escapeHtml(r.voucher_no || '') + '">' +
        '<td style="text-align:center;"><input type="checkbox" class="pending-check" value="' + escapeHtml(gn) + '"></td>' +
        '<td><a class="pi-link" href="' + escapeHtml(returnUrl(gn, true)) + '">' + escapeHtml(showNo) + '</a></td>' +
        '<td>' + escapeHtml(fmtDate(r.returndate)) + '</td>' +
        '<td>' + escapeHtml(pdata) + '</td>' +
        '<td>' + escapeHtml(r.suppliercode || '—') + '</td>' +
        '<td>' + escapeHtml(r.suppliername || '—') + '</td>' +
        '<td class="num">' + fmtAmount(r.discount) + '</td>' +
        '<td class="num">' + fmtAmount(r.totalamount) + '</td>' +
        '<td>' + escapeHtml(showVoucher || '—') + '</td>' +
        '<td style="white-space:nowrap;">' +
        '<button type="button" class="page-po__btn-secondary prp-btn-reverse-pending" style="padding:3px 8px;font-size:11px;color:#991b1b;border-color:#fecaca;" data-goodsreturnno="' + escapeHtml(gn) + '" data-returndate="' + escapeHtml(fmtDate(r.returndate)) + '" data-postingdate="' + escapeHtml(pdata) + '">Reverse</button> ' +
        '<a class="page-po__btn-secondary" style="padding:3px 8px;font-size:11px;text-decoration:none;display:inline-block;" href="' + escapeHtml(returnUrl(gn, true)) + '">View</a>' +
        '</td></tr>';
    }).join('');
    refreshGlTotal();
    updateSelInfo();
  }

  function renderPostedRows(rows) {
    if (!postedBody) return;
    if (!rows || !rows.length) {
      postedBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:16px;color:#6b7280;font-style:italic;">No posted returns found.</td></tr>';
      refreshPostedTotal();
      return;
    }
    postedBody.innerHTML = rows.map(function (r) {
      const gn = r.goodsreturnno;
      const showNo = r.display_return_no || gn;
      const pdata = fmtDate(r.postingdate || r.voucher_date || r.returndate);
      return '<tr data-goodsreturnno="' + escapeHtml(gn) + '" data-returndate="' + escapeHtml(fmtDate(r.returndate)) + '" data-postingdate="' + escapeHtml(pdata) + '" data-suppliercode="' + escapeHtml(r.suppliercode || '') + '" data-suppliername="' + escapeHtml(r.suppliername || '') + '" data-discount="' + escapeHtml(r.discount || 0) + '" data-totalamount="' + escapeHtml(r.totalamount || 0) + '" data-voucher_no="' + escapeHtml(r.voucher_no || '') + '" data-voucher_date="' + escapeHtml(fmtDate(r.voucher_date)) + '" data-created_by="' + escapeHtml(r.created_by || '') + '">' +
        '<td><a class="pi-link" href="' + escapeHtml(returnUrl(gn, false)) + '">' + escapeHtml(showNo) + '</a></td>' +
        '<td>' + escapeHtml(fmtDate(r.returndate)) + '</td>' +
        '<td>' + escapeHtml(pdata) + '</td>' +
        '<td>' + escapeHtml(r.suppliercode || '—') + '</td>' +
        '<td>' + escapeHtml(r.suppliername || '—') + '</td>' +
        '<td class="num">' + fmtAmount(r.discount) + '</td>' +
        '<td class="num">' + fmtAmount(r.totalamount) + '</td>' +
        '<td>' + escapeHtml(r.voucher_no || '—') + '</td>' +
        '<td>' + escapeHtml(fmtDate(r.voucher_date)) + '</td>' +
        '<td>' + escapeHtml(r.created_by || '—') + '</td></tr>';
    }).join('');
    refreshPostedTotal();
  }

  function renderPagination() {
    if (!paginationEl) return;
    if (listTotalCount <= 0) {
      paginationEl.style.display = 'none';
      return;
    }
    paginationEl.style.display = '';
    const rowStart = glLoaded > 0 ? (listPage - 1) * perPage + 1 : 0;
    const rowEnd = glLoaded > 0 ? rowStart + glLoaded - 1 : 0;
    if (paginationInfo) {
      paginationInfo.textContent = activeTab === 'posted'
        ? (glLoaded > 0 ? ('Showing ' + rowStart + '–' + rowEnd + ' of ' + listTotalCount + ' (page ' + listPage + ' of ' + listTotalPages + ')') : '')
        : (glLoaded > 0 ? ('GL pending: ' + rowStart + '–' + rowEnd + ' of ' + listTotalCount) : '');
    }
    if (pageLabel) pageLabel.textContent = String(listPage);
    if (prevBtn) prevBtn.disabled = listPage <= 1 || listLoading;
    if (nextBtn) nextBtn.disabled = listPage >= listTotalPages || listLoading;
  }

  function showLoading() {
    if (activeTab === 'posted' && postedBody) {
      postedBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:20px;color:#6b7280;">Loading…</td></tr>';
    } else {
      if (glBody) glBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:20px;color:#6b7280;">Loading…</td></tr>';
    }
  }

  async function loadPage(page) {
    if (listLoading) return;
    listLoading = true;
    showLoading();
    try {
      const res = await fetch(buildApiUrl(page), {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok || !data.success) throw new Error(data.error || 'Load failed');
      listPage = Number(data.page || page) || page;
      if (activeTab === 'posted') {
        listTotalCount = Number(data.total_count || 0);
        listTotalPages = Math.max(1, Number(data.total_pages || 1));
        glLoaded = (data.rows || []).length;
        renderPostedRows(data.rows || []);
        if (tabPosted) tabPosted.textContent = 'Posted Returns (' + listTotalCount + ')';
      } else {
        renderApprovedRows(data.approved_rows || []);
        listTotalCount = Number(data.gl_total_count || 0);
        listTotalPages = Math.max(1, Number(data.total_pages || 1));
        glLoaded = (data.gl_pending_rows || []).length;
        renderGlRows(data.gl_pending_rows || []);
        const approvedN = Number(data.approved_total || (data.approved_rows || []).length);
        const pendingN = approvedN + listTotalCount;
        if (tabPending) tabPending.textContent = 'Posting Pending (' + pendingN + ')';
        if (glSectionTitle) glSectionTitle.textContent = 'Step 2 — GL posting pending (' + listTotalCount + ')';
        if (glHint) {
          glHint.textContent = listTotalCount === 0
            ? 'No saved purchase returns are waiting for accounts posting. Complete Step 1 (Post stock) or save a return from the Purchase Return screen.'
            : 'Select rows below, then click Post Selected (GL) in the toolbar.';
        }
      }
      renderPagination();
    } catch (err) {
      const msg = escapeHtml(err && err.message ? err.message : 'Could not load list.');
      if (activeTab === 'posted' && postedBody) {
        postedBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:20px;color:#b91c1c;">' + msg + '</td></tr>';
      } else if (glBody) {
        glBody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:20px;color:#b91c1c;">' + msg + '</td></tr>';
      }
      if (paginationEl) paginationEl.style.display = 'none';
    } finally {
      listLoading = false;
    }
  }

  function reloadList() {
    listPage = 1;
    loadPage(1);
  }

  function syncTabs() {
    document.querySelectorAll('.po-tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.tab === (activeTab === 'posted' ? 'postedTab' : 'pendingTab'));
    });
    if (pendingPane) pendingPane.classList.toggle('active', activeTab === 'pending');
    if (postedPane) postedPane.classList.toggle('active', activeTab === 'posted');
    if (paginationEl) paginationEl.style.display = activeTab === 'pending' && listTotalCount <= 0 ? 'none' : paginationEl.style.display;
  }

  document.querySelectorAll('.po-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      activeTab = btn.dataset.tab === 'postedTab' ? 'posted' : 'pending';
      syncTabs();
      reloadList();
    });
  });

  if (selAll) {
    selAll.addEventListener('change', function () {
      document.querySelectorAll('#glPendingTable tbody .pending-check').forEach(function (c) {
        c.checked = selAll.checked;
      });
      updateSelInfo();
    });
  }

  document.addEventListener('change', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('pending-check')) updateSelInfo();
  });

  document.addEventListener('click', function (e) {
    const revBtn = e.target.closest('.prp-btn-reverse-pending');
    if (revBtn) {
      e.preventDefault();
      prpAction = {
        type: 'reverse-pending',
        goodsReturnNo: prDocNo(revBtn.getAttribute('data-goodsreturnno') || ''),
        currentDate: revBtn.getAttribute('data-postingdate') || revBtn.getAttribute('data-returndate') || '',
      };
      openPrpActionModal();
    }
  });

  function openPrpActionModal() {
    if (!prpAction || !actionModal) return;
    const titleEl = document.getElementById('prpActionModalTitle');
    const msgEl = document.getElementById('prpActionModalMsg');
    const isRev = prpAction.type === 'reverse-pending';
    if (titleEl) titleEl.textContent = isRev ? ('Reverse Return — #' + prpAction.goodsReturnNo) : ('Change posting date — Return #' + prpAction.goodsReturnNo);
    if (msgEl) {
      msgEl.textContent = isRev
        ? 'Undo stock for this purchase return. ITEMJOURNAL keeps original + reverse entries. This return number is reserved — the next return gets a new number.'
        : 'Updates Posting Date used for Purchase Return / GL.';
    }
    if (actionDateWrap) actionDateWrap.style.display = isRev ? 'none' : '';
    if (actionNewDate) actionNewDate.value = prpAction.currentDate || '';
    if (actionPassword) actionPassword.value = '';
    if (actionPasswordError) { actionPasswordError.style.display = 'none'; actionPasswordError.textContent = ''; }
    if (actionConfirm) actionConfirm.textContent = isRev ? 'Reverse' : 'Update';
    actionModal.classList.remove('hidden');
  }

  function closePrpActionModal() {
    prpAction = null;
    if (actionModal) actionModal.classList.add('hidden');
  }

  async function submitPrpAction() {
    if (!prpAction || !prpAction.goodsReturnNo) return;
    const pwd = actionPassword ? actionPassword.value : '';
    const isRev = prpAction.type === 'reverse-pending';
    let newDate = '';
    if (!isRev) {
      newDate = actionNewDate ? (actionNewDate.value || '').trim() : '';
      if (!newDate) {
        if (actionPasswordError) { actionPasswordError.textContent = 'New posting date is required.'; actionPasswordError.style.display = ''; }
        return;
      }
      if (window.PeriodDateGuard) {
        const msg = window.PeriodDateGuard.messageForDate(newDate, closedPeriods);
        if (msg) {
          if (actionPasswordError) { actionPasswordError.textContent = msg; actionPasswordError.style.display = ''; }
          return;
        }
      }
    }
    if (!pwd) {
      if (actionPasswordError) { actionPasswordError.textContent = 'Password is required.'; actionPasswordError.style.display = ''; }
      return;
    }
    if (actionConfirm) actionConfirm.disabled = true;
    const payload = { goods_return_no: prpAction.goodsReturnNo, password: pwd };
    if (!isRev) {
      payload.new_date = newDate;
      payload.also_change_return_date = !!(actionAlsoReturn && actionAlsoReturn.checked);
    }
    if (typeof window.__GLOBAL_SAVE_NONCE === 'string' && window.__GLOBAL_SAVE_NONCE) payload.save_nonce = window.__GLOBAL_SAVE_NONCE;
    const url = isRev ? reversePendingUrl : changeDateUrl;
    closePrpActionModal();
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(function () { return {}; });
      if (data.save_nonce) window.__GLOBAL_SAVE_NONCE = data.save_nonce;
      if (!res.ok || !data.success) {
        openPostModal('Error', data.error || 'Request failed.', true);
        return;
      }
      openPostModal(isRev ? 'Return Reversed' : 'Date Updated', (data.message || 'Done.') + ' Refreshing…', false);
      setTimeout(reloadList, 900);
    } catch (e) {
      openPostModal('Error', 'Request failed.', true);
    } finally {
      if (actionConfirm) actionConfirm.disabled = false;
    }
  }

  async function postSelected() {
    const selected = Array.from(document.querySelectorAll('#glPendingTable tbody .pending-check:checked'))
      .map(function (c) { return prDocNo(c.value); })
      .filter(function (n) { return prDocNoValid(n); });
    if (!selected.length) {
      openPostModal('No Selection', 'In Step 2 (GL posting pending), tick one or more checkboxes. Approved requests in Step 1 must use Post stock first.', true);
      return;
    }
    if (window.PeriodDateGuard) {
      const closedRows = [];
      selected.forEach(function (gn) {
        const tr = document.querySelector('#glPendingTable tr[data-goodsreturnno="' + gn + '"]');
        const rd = tr ? (tr.getAttribute('data-postingdate') || tr.getAttribute('data-returndate') || '') : '';
        const msg = window.PeriodDateGuard.messageForDate(rd, closedPeriods);
        if (msg) closedRows.push('Return ' + gn + ': ' + msg);
      });
      if (closedRows.length) {
        openPostModal('Closed Period', closedRows.slice(0, 8).join('<br>'), true);
        return;
      }
    }
    if (!confirm('Post ' + selected.length + ' selected return(s)?')) return;
    if (btnPost) btnPost.disabled = true;
    openPostModal('Posting Returns', '<span class="prp-spinner"></span>Posting ' + selected.length + ' return(s)…', false);
    try {
      const res = await fetch(bulkPostUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goods_return_nos: selected }),
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok || (!data.success && !data.posted_count)) {
        openPostModal('Posting Failed', data.error || data.message || 'Posting failed', true);
        if (btnPost) btnPost.disabled = false;
        return;
      }
      openPostModal('Posting Completed', (data.message || 'Posted successfully.') + ' Refreshing…', false);
      setTimeout(reloadList, 900);
    } catch (e) {
      openPostModal('Posting Failed', 'Network error.', true);
    } finally {
      if (btnPost) btnPost.disabled = false;
    }
  }

  if (btnPost) btnPost.addEventListener('click', function () { postSelected().catch(function () {}); });
  if (postModalClose) postModalClose.addEventListener('click', closePostModal);
  if (actionCancel) actionCancel.addEventListener('click', closePrpActionModal);
  if (actionOverlay) actionOverlay.addEventListener('click', closePrpActionModal);
  if (actionConfirm) actionConfirm.addEventListener('click', submitPrpAction);
  if (prevBtn) prevBtn.addEventListener('click', function () { if (listPage > 1) loadPage(listPage - 1); });
  if (nextBtn) nextBtn.addEventListener('click', function () { if (listPage < listTotalPages) loadPage(listPage + 1); });

  if (searchInput) {
    if (window.NexaListSearchAutofillGuard) {
      window.NexaListSearchAutofillGuard.armSearchInput(searchInput, reloadList, loginUser);
    }
    searchInput.removeAttribute('readonly');
    searchInput.addEventListener('input', function () {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(reloadList, 350);
    });
  }
  if (dateFromEl) dateFromEl.addEventListener('change', reloadList);
  if (dateToEl) dateToEl.addEventListener('change', reloadList);
  const clearBtn = document.getElementById('prpSearchClear');
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      if (searchInput) searchInput.value = '';
      if (dateFromEl) dateFromEl.value = '';
      if (dateToEl) dateToEl.value = '';
      reloadList();
    });
  }

  window.addEventListener('pageshow', function () {
    if (typeof window.hideLoadingOverlay === 'function') window.hideLoadingOverlay();
  });

  syncTabs();
  reloadList();
};

document.addEventListener('DOMContentLoaded', function () {
  if (typeof window.bootPrPostingList === 'function') window.bootPrPostingList();
});
