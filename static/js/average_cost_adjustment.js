document.addEventListener('DOMContentLoaded', () => {
  const page = document.getElementById('acaPage');
  if (!page) return;

  const el = (id) => document.getElementById(id);
  const queryMode = page.dataset.queryMode === 'true';
  const saveUrl = page.dataset.saveUrl || '';
  const listUrl = page.dataset.listUrl || '';
  const itemContextUrl = page.dataset.itemContextUrl || '';
  const itemsUrl = page.dataset.itemsUrl || '';
  const negativeUrl = page.dataset.negativeUrl || '';

  let lines = [];
  let selectedIdx = -1;
  let saveInFlight = false;
  let pickTimer = null;
  let pendingItem = null;

  const payload = window.__ACA_PAYLOAD__ || { header: {}, lines: [] };
  (payload.lines || []).forEach((ln) => {
    lines.push({
      itemcode: ln.itemcode,
      itemname: ln.itemname || '',
      uom: ln.uom || '',
      current_qty: Number(ln.current_qty) || 0,
      old_average_cost: Number(ln.old_average_cost) || 0,
      new_average_cost: Number(ln.new_average_cost) || 0,
      value_delta: Number(ln.value_delta) || 0,
      correction_type: ln.correction_type || 'REVALUATION',
      inventory_account: ln.inventory_account || '',
      offset_account: ln.offset_account || '',
      lineremarks: ln.lineremarks || '',
      warehouse_code: ln.warehouse_code || '',
    });
  });

  const fmtNum = (n, dec = 2) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return '—';
    return v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  };

  const showFlash = (msg, ok = true) => {
    const box = el('acaFlash');
    if (!box) return;
    box.textContent = msg;
    box.className = 'aca-flash ' + (ok ? 'aca-flash--ok' : 'aca-flash--err');
    box.hidden = false;
    window.setTimeout(() => { box.hidden = true; }, 7000);
  };

  const whCode = () => (el('acaWarehouse')?.value || '').trim();

  const recalcLine = (ln) => {
    const qty = Number(ln.current_qty) || 0;
    const oldAvg = Number(ln.old_average_cost) || 0;
    const newAvg = Number(ln.new_average_cost) || 0;
    ln.value_delta = Math.round(qty * (newAvg - oldAvg) * 100) / 100;
    if (Math.abs(qty) < 1e-9) ln.correction_type = 'COST_ONLY';
    else if (qty < 0) ln.correction_type = 'COGS_CORRECTION';
    else ln.correction_type = 'REVALUATION';
    return ln;
  };

  const typeTag = (t) => {
    const u = String(t || '').toUpperCase();
    if (u === 'COGS_CORRECTION') return '<span class="aca-tag aca-tag--cogs">COGS correction</span>';
    if (u === 'COST_ONLY') return '<span class="aca-tag aca-tag--cost">Cost only</span>';
    return '<span class="aca-tag aca-tag--reval">Revaluation</span>';
  };

  const syncTotals = () => {
    let total = 0;
    lines.forEach((ln) => { total += Number(ln.value_delta) || 0; });
    if (el('acaLineCount')) el('acaLineCount').textContent = String(lines.length);
    if (el('acaTotalDelta')) el('acaTotalDelta').textContent = fmtNum(total);
  };

  const renderLines = () => {
    const body = el('acaLinesBody');
    if (!body) return;
    const cols = queryMode ? 10 : 11;
    if (!lines.length) {
      body.innerHTML = `<tr class="aca-empty"><td colspan="${cols}">No lines yet.</td></tr>`;
      syncTotals();
      if (el('acaBtnRemoveLine')) el('acaBtnRemoveLine').disabled = true;
      return;
    }
    body.innerHTML = lines.map((ln, idx) => {
      const sel = idx === selectedIdx ? ' is-selected' : '';
      const newAvgCell = queryMode
        ? fmtNum(ln.new_average_cost, 6)
        : `<input type="number" step="0.000001" min="0" class="aca-new-avg" data-idx="${idx}" value="${Number(ln.new_average_cost) || 0}" />`;
      const check = queryMode ? '' : `<td><input type="checkbox" class="aca-row-check" data-idx="${idx}" /></td>`;
      return `<tr class="aca-line${sel}" data-idx="${idx}">
        ${check}
        <td>${ln.itemcode || '—'}</td>
        <td title="${(ln.itemname || '').replace(/"/g, '&quot;')}">${(ln.itemname || '—').slice(0, 40)}</td>
        <td>${ln.uom || '—'}</td>
        <td class="num">${fmtNum(ln.current_qty, 3)}</td>
        <td class="num">${fmtNum(ln.old_average_cost, 6)}</td>
        <td class="num">${newAvgCell}</td>
        <td class="num">${fmtNum(ln.value_delta)}</td>
        <td>${typeTag(ln.correction_type)}</td>
        <td>${ln.inventory_account || '—'}</td>
        <td>${ln.offset_account || '—'}</td>
      </tr>`;
    }).join('');
    syncTotals();
    if (el('acaBtnRemoveLine')) el('acaBtnRemoveLine').disabled = false;
  };

  const fetchItemContext = async (itemCode) => {
    const url = `${itemContextUrl}?item_code=${encodeURIComponent(itemCode)}&warehouse_code=${encodeURIComponent(whCode())}`;
    const res = await fetch(url, { credentials: 'same-origin' });
    return res.json();
  };

  const setPendingFromCtx = (ctx) => {
    pendingItem = {
      itemcode: ctx.itemcode,
      itemname: ctx.itemname || '',
      uom: ctx.uom || '',
      current_qty: Number(ctx.current_qty) || 0,
      old_average_cost: Number(ctx.old_average_cost ?? ctx.current_avg_cost) || 0,
      correction_type: ctx.correction_type || 'REVALUATION',
      inventory_account: ctx.inventory_account || '',
      cogs_account: ctx.cogs_account || '',
      offset_account: '',
    };
    if (el('acaItemCode')) el('acaItemCode').value = String(ctx.itemcode || '');
    if (el('acaItemStock')) el('acaItemStock').value = fmtNum(ctx.current_qty, 3);
    if (el('acaItemOldAvg')) el('acaItemOldAvg').value = fmtNum(pendingItem.old_average_cost, 6);
    if (el('acaItemNewAvg') && !el('acaItemNewAvg').value) {
      el('acaItemNewAvg').value = String(pendingItem.old_average_cost || '');
    }
  };

  const closePick = () => {
    const list = el('acaItemPickList');
    if (list) list.classList.remove('is-open');
  };

  const searchItems = async (q) => {
    if (!itemsUrl || !q || q.length < 1) {
      closePick();
      return;
    }
    const url = `${itemsUrl}?search=${encodeURIComponent(q)}&warehouse_code=${encodeURIComponent(whCode())}&limit=40`;
    const res = await fetch(url, { credentials: 'same-origin' });
    const data = await res.json();
    const list = el('acaItemPickList');
    if (!list) return;
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = '<div class="aca-pick__item">No matches</div>';
      list.classList.add('is-open');
      return;
    }
    list.innerHTML = items.map((it) => `
      <div class="aca-pick__item" data-code="${it.code}">
        <strong>${it.code}</strong> — ${(it.name || '').slice(0, 50)}
        <span style="color:#64748b;font-size:12px;"> · stock ${fmtNum(it.stock, 3)} · avg ${fmtNum(it.averagecost, 4)}</span>
      </div>`).join('');
    list.classList.add('is-open');
  };

  const addLineFromPending = async () => {
    if (!pendingItem) {
      showFlash('Select an item first.', false);
      return;
    }
    const newAvg = Number(el('acaItemNewAvg')?.value);
    if (!Number.isFinite(newAvg) || newAvg < 0) {
      showFlash('Enter a valid new average cost.', false);
      return;
    }
    if (lines.some((l) => Number(l.itemcode) === Number(pendingItem.itemcode))) {
      showFlash('Item already on the journal.', false);
      return;
    }
    // Refresh accounts / qty at add time
    let ctx = pendingItem;
    try {
      const fresh = await fetchItemContext(pendingItem.itemcode);
      if (fresh && fresh.success !== false) ctx = { ...pendingItem, ...fresh };
    } catch (_) { /* keep pending */ }

    const ln = recalcLine({
      itemcode: ctx.itemcode,
      itemname: ctx.itemname || '',
      uom: ctx.uom || '',
      current_qty: Number(ctx.current_qty) || 0,
      old_average_cost: Number(ctx.old_average_cost ?? ctx.current_avg_cost) || 0,
      new_average_cost: newAvg,
      inventory_account: ctx.inventory_account || '',
      offset_account: '',
      warehouse_code: whCode(),
      lineremarks: '',
    });
    if (ln.correction_type === 'COGS_CORRECTION') {
      ln.offset_account = ctx.cogs_account || ctx.offset_account || '5100';
    } else if (ln.correction_type === 'REVALUATION') {
      ln.offset_account = ctx.offset_account || '5199';
    } else {
      ln.offset_account = '';
    }
    // Server will resolve offset precisely on save; keep preview tags
    lines.push(ln);
    selectedIdx = lines.length - 1;
    pendingItem = null;
    if (el('acaItemSearch')) el('acaItemSearch').value = '';
    if (el('acaItemCode')) el('acaItemCode').value = '';
    if (el('acaItemStock')) el('acaItemStock').value = '';
    if (el('acaItemOldAvg')) el('acaItemOldAvg').value = '';
    if (el('acaItemNewAvg')) el('acaItemNewAvg').value = '';
    closePick();
    renderLines();
  };

  const collectHeader = () => ({
    journalname: (el('acaJournalName')?.value || '').trim(),
    journal_date: el('acaJournalDate')?.value || '',
    posting_date: el('acaPostingDate')?.value || '',
    warehouse_code: whCode(),
    adjustment_reason: el('acaReason')?.value || '',
    reference: (el('acaReference')?.value || '').trim(),
    description: (el('acaDescription')?.value || '').trim(),
    notes: '',
  });

  const doSave = async (post) => {
    if (saveInFlight || queryMode) return;
    if (!lines.length) {
      showFlash('Add at least one line.', false);
      return;
    }
    if (post && !window.confirm('Post this adjustment? Average cost will update and GL will post for non-zero stock deltas.')) {
      return;
    }
    saveInFlight = true;
    if (el('acaBtnSave')) el('acaBtnSave').disabled = true;
    if (el('acaBtnPost')) el('acaBtnPost').disabled = true;
    try {
      const jnoRaw = el('acaJournalNo')?.value;
      const journal_no = jnoRaw ? Number(jnoRaw) : null;
      const body = {
        journal_no,
        header: collectHeader(),
        lines: lines.map((ln, i) => ({
          slno: i + 1,
          itemcode: ln.itemcode,
          itemname: ln.itemname,
          uom: ln.uom,
          current_qty: ln.current_qty,
          old_average_cost: ln.old_average_cost,
          new_average_cost: ln.new_average_cost,
          warehouse_code: ln.warehouse_code || whCode(),
          lineremarks: ln.lineremarks || '',
        })),
        post: !!post,
      };
      const res = await fetch(saveUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.success) {
        showFlash(data.error || 'Save failed.', false);
        return;
      }
      showFlash(data.message || 'Saved.', true);
      if (data.journal_no && el('acaJournalNo')) el('acaJournalNo').value = String(data.journal_no);
      if (post && data.view_url) {
        window.setTimeout(() => { window.location.href = data.view_url; }, 600);
      } else if (data.journal_no && !post) {
        // stay on edit with journal no filled
      }
    } catch (err) {
      showFlash(String(err || 'Network error'), false);
    } finally {
      saveInFlight = false;
      if (el('acaBtnSave')) el('acaBtnSave').disabled = false;
      if (el('acaBtnPost')) el('acaBtnPost').disabled = false;
    }
  };

  // Events
  el('acaLinesBody')?.addEventListener('click', (e) => {
    const tr = e.target.closest('tr.aca-line');
    if (!tr) return;
    selectedIdx = Number(tr.dataset.idx);
    renderLines();
  });

  el('acaLinesBody')?.addEventListener('change', (e) => {
    const inp = e.target.closest('.aca-new-avg');
    if (!inp) return;
    const idx = Number(inp.dataset.idx);
    if (!Number.isFinite(idx) || !lines[idx]) return;
    lines[idx].new_average_cost = Number(inp.value) || 0;
    recalcLine(lines[idx]);
    renderLines();
  });

  el('acaBtnAddLine')?.addEventListener('click', () => { addLineFromPending(); });
  el('acaBtnSave')?.addEventListener('click', () => { doSave(false); });
  el('acaBtnPost')?.addEventListener('click', () => { doSave(true); });

  el('acaBtnRemoveLine')?.addEventListener('click', () => {
    const checks = Array.from(document.querySelectorAll('.aca-row-check:checked'));
    if (!checks.length) {
      if (selectedIdx >= 0) lines.splice(selectedIdx, 1);
    } else {
      const remove = new Set(checks.map((c) => Number(c.dataset.idx)));
      lines = lines.filter((_, i) => !remove.has(i));
    }
    selectedIdx = -1;
    renderLines();
  });

  el('acaItemSearch')?.addEventListener('input', (e) => {
    const q = e.target.value || '';
    window.clearTimeout(pickTimer);
    pickTimer = window.setTimeout(() => searchItems(q.trim()), 250);
  });

  el('acaItemPickList')?.addEventListener('click', async (e) => {
    const row = e.target.closest('.aca-pick__item');
    if (!row || !row.dataset.code) return;
    closePick();
    try {
      const ctx = await fetchItemContext(row.dataset.code);
      if (!ctx || ctx.success === false) {
        showFlash(ctx?.error || 'Item not found.', false);
        return;
      }
      setPendingFromCtx(ctx);
      if (el('acaItemSearch')) el('acaItemSearch').value = `${ctx.itemcode} — ${ctx.itemname || ''}`;
    } catch (err) {
      showFlash(String(err), false);
    }
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.aca-pick')) closePick();
  });

  el('acaBtnNegStock')?.addEventListener('click', async () => {
    try {
      const url = `${negativeUrl}?warehouse_code=${encodeURIComponent(whCode())}&limit=100`;
      const res = await fetch(url, { credentials: 'same-origin' });
      const data = await res.json();
      const items = data.items || [];
      if (!items.length) {
        showFlash('No negative-stock items found.', false);
        return;
      }
      let added = 0;
      items.forEach((it) => {
        if (lines.some((l) => Number(l.itemcode) === Number(it.itemcode))) return;
        const oldAvg = Number(it.old_average_cost) || 0;
        const ln = recalcLine({
          itemcode: it.itemcode,
          itemname: it.itemname || '',
          uom: it.uom || '',
          current_qty: Number(it.current_qty) || 0,
          old_average_cost: oldAvg,
          new_average_cost: oldAvg,
          inventory_account: it.inventory_account || '1300',
          offset_account: it.cogs_account || '5100',
          warehouse_code: whCode(),
          lineremarks: 'Minus billing candidate',
        });
        lines.push(ln);
        added += 1;
      });
      renderLines();
      showFlash(`Loaded ${added} negative-stock item(s). Enter new average cost, then Post.`, true);
    } catch (err) {
      showFlash(String(err), false);
    }
  });

  renderLines();
});
