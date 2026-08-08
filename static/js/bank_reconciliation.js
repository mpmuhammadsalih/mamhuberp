(function () {
  'use strict';

  const cfg = window.BANK_RECON_CONFIG || {};
  const urls = cfg.urls || {};

  const state = {
    reconNo: 0,
    isNew: true,
    bankAccount: '',
    dateFrom: '',
    dateTo: '',
    description: '',
    notes: '',
    status: 'IN_PROGRESS',
    erpLines: [],
    bankLines: [],
    matches: [],
    erpTotals: { opening: 0, receipts: 0, payments: 0, closing: 0 },
    bankTotals: { opening: 0, credits: 0, debits: 0, closing: 0 },
    summary: { matched_amount: 0, unmatched_erp: 0, unmatched_bank: 0, difference: 0 },
    difference: 0,
    selErpKey: '',
    selBankLine: 0,
    activeTab: 'recon',
    header: null,
  };

  const $ = (id) => document.getElementById(id);

  function fmt(n) {
    const x = Number(n) || 0;
    return x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtDate(iso) {
    if (!iso) return '';
    const p = String(iso).slice(0, 10);
    if (p.length < 10) return p;
    const [y, m, d] = p.split('-');
    return `${d}/${m}/${y}`;
  }

  function showMsg(text, ok) {
    const el = $('brMessage');
    if (!el) return;
    if (!text) {
      el.className = 'br-msg';
      el.textContent = '';
      return;
    }
    el.className = ok ? 'br-msg ok' : 'br-msg error';
    el.textContent = text;
  }

  function setDefaultDates() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    if (!$('brDateFrom').value) $('brDateFrom').value = `${y}-${m}-01`;
    if (!$('brDateTo').value) $('brDateTo').value = now.toISOString().slice(0, 10);
  }

  function recalcBankClosing() {
    const op = parseFloat($('brBankOpening').value) || 0;
    state.bankTotals.opening = op;
    const credits = state.bankLines.reduce((s, b) => s + (Number(b.deposit) || 0), 0);
    const debits = state.bankLines.reduce((s, b) => s + (Number(b.payment) || 0), 0);
    state.bankTotals.credits = Math.round(credits * 100) / 100;
    state.bankTotals.debits = Math.round(debits * 100) / 100;
    state.bankTotals.closing = Math.round((op + credits - debits) * 100) / 100;
    let run = op;
    state.bankLines.forEach((b) => {
      run = Math.round((run + (Number(b.deposit) || 0) - (Number(b.payment) || 0)) * 100) / 100;
      b.balance = run;
    });
  }

  function updateCounts() {
    const matchedErp = new Set(state.matches.map((m) => m.erp_key));
    const matchedBank = new Set(state.matches.map((m) => m.bank_line_no));
    const unErp = state.erpLines.filter((e) => !matchedErp.has(e.erp_key)).length;
    const unBank = state.bankLines.filter((b) => !matchedBank.has(b.line_no)).length;
    $('brCntErp').textContent = String(unErp);
    $('brCntBank').textContent = String(unBank);
    $('brCntMatched').textContent = String(state.matches.length);
  }

  function paintBalances() {
    $('brErpOpening').textContent = fmt(state.erpTotals.opening);
    $('brErpReceipts').textContent = fmt(state.erpTotals.receipts);
    $('brErpPayments').textContent = fmt(state.erpTotals.payments);
    $('brErpClosing').textContent = fmt(state.erpTotals.closing);
    $('brBankCredits').textContent = fmt(state.bankTotals.credits);
    $('brBankDebits').textContent = fmt(state.bankTotals.debits);
    $('brBankClosing').textContent = fmt(state.bankTotals.closing);
    const diff = (Number(state.erpTotals.closing) || 0) - (Number(state.bankTotals.closing) || 0);
    state.difference = Math.round(diff * 100) / 100;
    $('brDifference').textContent = fmt(state.difference);
    $('brDifference').style.color = Math.abs(state.difference) < 0.02 ? '#059669' : '#dc2626';
    const st = (state.status || 'IN_PROGRESS').replace(/_/g, ' ');
    $('brStatus').textContent = st;
    $('brSumMatched').textContent = fmt(state.summary.matched_amount);
    $('brSumUnErp').textContent = fmt(state.summary.unmatched_erp);
    $('brSumUnBank').textContent = fmt(state.summary.unmatched_bank);
    $('brSumDiff').textContent = fmt(state.summary.difference);
    updateCounts();
  }

  function erpRowHtml(e, selectable) {
    const cls = [e.matched ? 'matched-row' : '', state.selErpKey === e.erp_key ? 'selected' : ''].filter(Boolean).join(' ');
    const chk = selectable
      ? `<input type="checkbox" data-erp="${e.erp_key}" ${state.selErpKey === e.erp_key ? 'checked' : ''} />`
      : '';
    let ledgerHref = '';
    const sel = $('brBankAccount');
    const opt = sel && sel.selectedOptions && sel.selectedOptions[0];
    const aid = opt && opt.dataset.accountId;
    if (aid && urls.ledger) {
      ledgerHref = `${urls.ledger}?account_id=${encodeURIComponent(aid)}&date_from=${encodeURIComponent(state.dateFrom || '')}&date_to=${encodeURIComponent(state.dateTo || '')}`;
    }
    const ref = e.voucher_no && ledgerHref
      ? `<a href="${ledgerHref}" target="_blank" rel="noopener">${e.reference_no || e.voucher_no}</a>`
      : (e.reference_no || e.voucher_no || '');
    return `<tr class="${cls}" data-erp-key="${e.erp_key}">
      <td>${chk}</td>
      <td>${fmtDate(e.txn_date)}</td>
      <td>${ref}</td>
      <td>${(e.description || '').slice(0, 60)}</td>
      <td class="num">${fmt(e.deposit)}</td>
      <td class="num">${fmt(e.payment)}</td>
      <td class="num">${fmt(e.balance)}</td>
    </tr>`;
  }

  function bankRowHtml(b, selectable) {
    const matched = state.matches.some((m) => m.bank_line_no === b.line_no);
    const cls = [matched ? 'matched-row' : '', state.selBankLine === b.line_no ? 'selected' : ''].filter(Boolean).join(' ');
    const chk = selectable
      ? `<input type="checkbox" data-bank="${b.line_no}" ${state.selBankLine === b.line_no ? 'checked' : ''} />`
      : '';
    return `<tr class="${cls}" data-bank-line="${b.line_no}">
      <td>${chk}</td>
      <td>${fmtDate(b.txn_date)}</td>
      <td>${b.reference_no || ''}</td>
      <td>${(b.description || '').slice(0, 60)}</td>
      <td class="num">${fmt(b.deposit)}</td>
      <td class="num">${fmt(b.payment)}</td>
      <td class="num">${fmt(b.balance)}</td>
    </tr>`;
  }

  function filterLines(tab) {
    const matchedErp = new Set(state.matches.map((m) => m.erp_key));
    const matchedBank = new Set(state.matches.map((m) => m.bank_line_no));
    if (tab === 'unmatched-erp') return state.erpLines.filter((e) => !matchedErp.has(e.erp_key));
    if (tab === 'unmatched-bank') return state.bankLines.filter((b) => !matchedBank.has(b.line_no));
    if (tab === 'matched') {
      return state.matches.map((m) => {
        const e = state.erpLines.find((x) => x.erp_key === m.erp_key);
        const b = state.bankLines.find((x) => x.line_no === m.bank_line_no);
        return { m, e, b };
      });
    }
    return null;
  }

  function renderTables() {
    const tab = state.activeTab;
    const panelRecon = $('brPanelRecon');
    const panelSingle = $('brPanelSingle');
    if (tab === 'recon') {
      panelRecon.hidden = false;
      panelSingle.hidden = true;
      const erpBody = $('brErpTable').querySelector('tbody');
      const bankBody = $('brBankTable').querySelector('tbody');
      erpBody.innerHTML = state.erpLines.map((e) => erpRowHtml(e, true)).join('') || '<tr><td colspan="7">Load a bank account and date range.</td></tr>';
      bankBody.innerHTML = state.bankLines.map((b) => bankRowHtml(b, true)).join('') || '<tr><td colspan="7">Import a statement or add lines via CSV.</td></tr>';
      bindTableClicks(erpBody, bankBody);
    } else {
      panelRecon.hidden = true;
      panelSingle.hidden = false;
      const tbl = $('brSingleTable');
      const head = tbl.querySelector('thead tr');
      const body = tbl.querySelector('tbody');
      if (tab === 'matched') {
        head.innerHTML = '<th>ERP ref</th><th>ERP date</th><th>Bank ref</th><th>Bank date</th><th class="num">Amount</th><th>Type</th><th></th>';
        body.innerHTML = filterLines('matched').map(({ m, e, b }) => `
          <tr>
            <td>${e ? (e.reference_no || e.voucher_no) : m.erp_key}</td>
            <td>${e ? fmtDate(e.txn_date) : ''}</td>
            <td>${b ? b.reference_no : ''}</td>
            <td>${b ? fmtDate(b.txn_date) : ''}</td>
            <td class="num">${fmt(m.match_amount)}</td>
            <td>${m.match_type || ''}</td>
            <td><button type="button" class="br-unmatch-btn" data-erp="${m.erp_key}">Unmatch</button></td>
          </tr>`).join('') || '<tr><td colspan="7">No matches yet.</td></tr>';
        body.querySelectorAll('.br-unmatch-btn').forEach((btn) => {
          btn.addEventListener('click', () => doUnmatch(btn.dataset.erp, 0));
        });
      } else if (tab === 'unmatched-erp') {
        head.innerHTML = '<th></th><th>Date</th><th>Reference</th><th>Description</th><th class="num">Deposit</th><th class="num">Payment</th><th class="num">Balance</th>';
        const lines = filterLines('unmatched-erp');
        body.innerHTML = lines.map((e) => erpRowHtml(e, true)).join('') || '<tr><td colspan="7">All ERP lines matched.</td></tr>';
        bindTableClicks(body, null);
      } else {
        head.innerHTML = '<th></th><th>Date</th><th>Reference</th><th>Description</th><th class="num">Deposit</th><th class="num">Payment</th><th class="num">Balance</th>';
        const lines = filterLines('unmatched-bank');
        body.innerHTML = lines.map((b) => bankRowHtml(b, true)).join('') || '<tr><td colspan="7">All bank lines matched.</td></tr>';
        bindTableClicks(null, body);
      }
    }
    paintMatchDetail();
    paintBalances();
  }

  function bindTableClicks(erpBody, bankBody) {
    if (erpBody) {
      erpBody.querySelectorAll('input[data-erp]').forEach((inp) => {
        inp.addEventListener('change', () => {
          state.selErpKey = inp.checked ? inp.dataset.erp : '';
          renderTables();
        });
      });
      erpBody.querySelectorAll('tr[data-erp-key]').forEach((tr) => {
        tr.addEventListener('click', (ev) => {
          if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'A') return;
          state.selErpKey = tr.dataset.erpKey;
          renderTables();
        });
      });
    }
    if (bankBody) {
      bankBody.querySelectorAll('input[data-bank]').forEach((inp) => {
        inp.addEventListener('change', () => {
          state.selBankLine = inp.checked ? parseInt(inp.dataset.bank, 10) : 0;
          renderTables();
        });
      });
      bankBody.querySelectorAll('tr[data-bank-line]').forEach((tr) => {
        tr.addEventListener('click', (ev) => {
          if (ev.target.tagName === 'INPUT') return;
          state.selBankLine = parseInt(tr.dataset.bankLine, 10);
          renderTables();
        });
      });
    }
  }

  function paintMatchDetail() {
    const e = state.erpLines.find((x) => x.erp_key === state.selErpKey);
    const b = state.bankLines.find((x) => x.line_no === state.selBankLine);
    const det = $('brMatchDetail');
    const st = $('brMatchStatus');
    if (!e && !b) {
      det.textContent = 'Select ERP and bank lines, then Match.';
      st.textContent = '';
      return;
    }
    let html = '';
    if (e) {
      html += `<div><strong>ERP:</strong> ${e.reference_no || e.voucher_no} · ${fmtDate(e.txn_date)} · Dr ${fmt(e.deposit)} / Cr ${fmt(e.payment)}</div>`;
    }
    if (b) {
      html += `<div><strong>Bank:</strong> ${b.reference_no || '—'} · ${fmtDate(b.txn_date)} · Cr ${fmt(b.deposit)} / Dr ${fmt(b.payment)}</div>`;
    }
    det.innerHTML = html;
    if (e && b) {
      const edr = Number(e.deposit) || 0;
      const ecr = Number(e.payment) || 0;
      const bdep = Number(b.deposit) || 0;
      const bpay = Number(b.payment) || 0;
      const ok = (edr > 0 && Math.abs(edr - bdep) < 0.02) || (ecr > 0 && Math.abs(ecr - bpay) < 0.02);
      st.textContent = ok ? 'Fully matched (amounts align)' : 'Amounts differ — review before matching';
      st.style.color = ok ? '#059669' : '#d97706';
    } else {
      st.textContent = '';
    }
  }

  function paintAudit(hdr) {
    const el = $('brAudit');
    if (!hdr || !hdr.created_by) {
      el.textContent = '';
      return;
    }
    el.innerHTML = `
      <span>Created by ${hdr.created_by || '—'} on ${fmtDate(hdr.created_date) || '—'}</span>
      <span>Modified by ${hdr.modified_by || '—'} on ${fmtDate(hdr.modified_date) || '—'}</span>
    `;
  }

  async function apiGet(url, params) {
    const qs = new URLSearchParams(params || {}).toString();
    const res = await fetch(qs ? `${url}?${qs}` : url, { credentials: 'same-origin' });
    return res.json();
  }

  async function apiPost(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  function applyPayload(data) {
    const hdr = data.header || {};
    state.header = hdr;
    state.reconNo = parseInt(hdr.recon_no, 10) || 0;
    state.isNew = state.reconNo <= 0 || !data.matches?.length && !state.bankLines.length;
    state.bankAccount = hdr.bank_account_code || state.bankAccount;
    state.dateFrom = hdr.date_from || state.dateFrom;
    state.dateTo = hdr.date_to || state.dateTo;
    state.description = hdr.description || '';
    state.notes = hdr.notes || '';
    state.status = hdr.status || 'IN_PROGRESS';
    state.erpLines = data.erp_lines || [];
    state.bankLines = data.bank_lines || [];
    state.matches = data.matches || [];
    state.erpTotals = data.erp_totals || state.erpTotals;
    state.bankTotals = data.bank_totals || state.bankTotals;
    state.summary = data.summary || state.summary;
    state.difference = data.difference != null ? data.difference : state.difference;

    $('brReconNo').value = state.reconNo || '';
    $('brBankAccount').value = state.bankAccount;
    $('brDateFrom').value = state.dateFrom || '';
    $('brDateTo').value = state.dateTo || '';
    $('brDescription').value = state.description;
    $('brNotes').value = state.notes;
    $('brBankOpening').value = state.bankTotals.opening || 0;
    paintAudit(hdr);
    renderTables();
  }

  async function loadData() {
    state.bankAccount = $('brBankAccount').value;
    state.dateFrom = $('brDateFrom').value;
    state.dateTo = $('brDateTo').value;
    if (!state.bankAccount) {
      showMsg('Select a bank account.', false);
      return;
    }
    showMsg('Loading…', true);
    try {
      const data = await apiGet(urls.load, {
        recon_no: $('brReconNo').value || 0,
        bank_account_code: state.bankAccount,
        date_from: state.dateFrom,
        date_to: state.dateTo,
      });
      if (!data.success) {
        showMsg(data.error || 'Load failed', false);
        return;
      }
      showMsg('');
      state.isNew = !(parseInt($('brReconNo').value, 10) > 0);
      applyPayload(data);
    } catch (ex) {
      showMsg(String(ex), false);
    }
  }

  async function saveData() {
    recalcBankClosing();
    const payload = {
      recon_no: parseInt($('brReconNo').value, 10) || 0,
      bank_account_code: $('brBankAccount').value,
      date_from: $('brDateFrom').value,
      date_to: $('brDateTo').value,
      description: $('brDescription').value,
      notes: $('brNotes').value,
      status: state.status || 'IN_PROGRESS',
      erp_totals: state.erpTotals,
      bank_totals: state.bankTotals,
      bank_lines: state.bankLines,
      matches: state.matches,
    };
    showMsg('Saving…', true);
    try {
      const data = await apiPost(urls.save, payload);
      if (!data.success) {
        showMsg(data.error || 'Save failed', false);
        return;
      }
      $('brReconNo').value = data.recon_no;
      state.isNew = false;
      showMsg('Saved.', true);
      await loadData();
    } catch (ex) {
      showMsg(String(ex), false);
    }
  }

  async function doAutoMatch() {
    const data = await apiPost(urls.autoMatch, {
      erp_lines: state.erpLines,
      bank_lines: state.bankLines,
      matches: state.matches,
    });
    if (!data.success) {
      showMsg(data.error || 'Auto match failed', false);
      return;
    }
    state.matches = data.matches || [];
    state.erpLines = data.erp_lines || state.erpLines;
    state.summary = data.summary || state.summary;
    showMsg('Auto match complete.', true);
    renderTables();
  }

  async function doMatch() {
    if (!state.selErpKey || !state.selBankLine) {
      showMsg('Select one ERP line and one bank line.', false);
      return;
    }
    const e = state.erpLines.find((x) => x.erp_key === state.selErpKey);
    const amt = Math.max(Number(e?.deposit) || 0, Number(e?.payment) || 0);
    const data = await apiPost(urls.match, {
      erp_key: state.selErpKey,
      bank_line_no: state.selBankLine,
      match_amount: amt,
      matches: state.matches,
      erp_lines: state.erpLines,
      bank_lines: state.bankLines,
    });
    if (!data.success) {
      showMsg(data.error || 'Match failed', false);
      return;
    }
    state.matches = data.matches;
    state.erpLines = data.erp_lines;
    state.summary = data.summary;
    showMsg('Matched.', true);
    renderTables();
  }

  async function doUnmatch(erpKey, bankLine) {
    const data = await apiPost(urls.unmatch, {
      erp_key: erpKey || state.selErpKey,
      bank_line_no: bankLine || state.selBankLine,
      matches: state.matches,
      erp_lines: state.erpLines,
      bank_lines: state.bankLines,
    });
    if (!data.success) {
      showMsg(data.error || 'Unmatch failed', false);
      return;
    }
    state.matches = data.matches;
    state.erpLines = data.erp_lines;
    state.summary = data.summary;
    showMsg('Unmatched.', true);
    renderTables();
  }

  async function importCsv(file) {
    const text = await file.text();
    const res = await fetch(urls.import, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'text/csv' },
      body: text,
    });
    const json = await res.json();
    if (!json.success) {
      showMsg(json.error || 'Import failed', false);
      return;
    }
    state.bankLines = json.bank_lines || [];
    state.bankTotals = json.bank_totals || state.bankTotals;
    recalcBankClosing();
    showMsg(`Imported ${state.bankLines.length} line(s).`, true);
    renderTables();
  }

  function resetNew() {
    state.reconNo = 0;
    state.isNew = true;
    state.matches = [];
    state.bankLines = [];
    state.erpLines = [];
    state.selErpKey = '';
    state.selBankLine = 0;
    $('brReconNo').value = '';
    $('brDescription').value = '';
    $('brNotes').value = '';
    $('brBankOpening').value = '0';
    showMsg('New reconciliation — select account and dates, then Refresh.', true);
    renderTables();
  }

  async function browseList() {
    const data = await apiGet(urls.list);
    const body = $('brBrowseTable').querySelector('tbody');
    if (!data.success) {
      body.innerHTML = '<tr><td colspan="4">Could not load list.</td></tr>';
    } else {
      body.innerHTML = (data.rows || []).map((r) => `
        <tr style="cursor:pointer" data-rno="${r.recon_no}">
          <td>${r.recon_no}</td>
          <td>${r.bank_account_code}</td>
          <td>${fmtDate(r.date_from)} – ${fmtDate(r.date_to)}</td>
          <td>${r.status}</td>
        </tr>`).join('') || '<tr><td colspan="4">No saved reconciliations.</td></tr>';
      body.querySelectorAll('tr[data-rno]').forEach((tr) => {
        tr.addEventListener('click', () => {
          $('brReconNo').value = tr.dataset.rno;
          $('brBrowseDialog').close();
          loadData();
        });
      });
    }
    $('brBrowseDialog').showModal();
  }

  function init() {
    setDefaultDates();
    $('brBtnNew').addEventListener('click', resetNew);
    $('brBtnSave').addEventListener('click', saveData);
    $('brBtnDelete').addEventListener('click', async () => {
      const rno = parseInt($('brReconNo').value, 10);
      if (!rno || !confirm('Delete this reconciliation?')) return;
      const data = await apiPost(urls.delete, { recon_no: rno });
      if (data.success) {
        showMsg('Deleted.', true);
        resetNew();
      } else showMsg(data.error, false);
    });
    $('brBtnRefresh').addEventListener('click', loadData);
    $('brBtnAutoMatch').addEventListener('click', doAutoMatch);
    $('brBtnMatch').addEventListener('click', doMatch);
    $('brBtnUnmatch').addEventListener('click', () => doUnmatch('', 0));
    $('brImportFile').addEventListener('change', (ev) => {
      const f = ev.target.files && ev.target.files[0];
      if (f) importCsv(f);
      ev.target.value = '';
    });
    $('brBankOpening').addEventListener('input', () => {
      recalcBankClosing();
      paintBalances();
      renderTables();
    });
    $('brReconBrowse').addEventListener('click', browseList);
    $('brBrowseClose').addEventListener('click', () => $('brBrowseDialog').close());
    document.querySelectorAll('.br-tabs button').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.br-tabs button').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        state.activeTab = btn.dataset.tab;
        renderTables();
      });
    });

    if (cfg.initialReconNo > 0) {
      $('brReconNo').value = cfg.initialReconNo;
      loadData();
    } else {
      renderTables();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
