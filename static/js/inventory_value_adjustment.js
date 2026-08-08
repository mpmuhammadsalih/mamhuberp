document.addEventListener('DOMContentLoaded', () => {
  const page = document.getElementById('ivaPage');
  if (!page) return;

  const el = (id) => document.getElementById(id);
  const queryMode = page.dataset.queryMode === 'true';
  const saveUrl = page.dataset.saveUrl || '';
  const listUrl = page.dataset.listUrl || '';
  const itemContextUrl = page.dataset.itemContextUrl || '';
  const itemsUrl = window.__IVA_ITEMS_URL__ || '';

  let lines = [];
  let selectedIdx = -1;
  let lineIdSeq = 1;
  let saveInFlight = false;

  const fmtNum = (n, dec = 2) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return '—';
    return v.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  };

  const whCode = () => (el('ivaWarehouse')?.value || '').trim();
  const siteCode = () => (el('ivaSite')?.value || '').trim();

  const showFlash = (msg, ok = true) => {
    const box = el('ivaFlash');
    if (!box) return;
    box.textContent = msg;
    box.className = 'iva-flash ' + (ok ? 'iva-flash--ok' : 'iva-flash--err');
    box.hidden = false;
    window.setTimeout(() => { box.hidden = true; }, 6000);
  };

  const calcNewAvg = (curQty, curAvg, adjAmt, dir) => {
    const qty = Number(curQty) || 0;
    const avg = Number(curAvg) || 0;
    let amt = Math.abs(Number(adjAmt) || 0);
    if (String(dir || '').toUpperCase() === 'DECREASE') amt = -amt;
    if (qty <= 0) return avg;
    return Math.round(((qty * avg) + amt) / qty * 1000000) / 1000000;
  };

  const syncTotals = () => {
    let totalQty = 0;
    let totalAdj = 0;
    lines.forEach((ln) => {
      totalQty += Number(ln.quantity) || 0;
      totalAdj += Math.abs(Number(ln.adjustment_amount) || 0);
    });
    if (el('ivaTotalQty')) el('ivaTotalQty').textContent = fmtNum(totalQty);
    if (el('ivaTotalAdj')) el('ivaTotalAdj').textContent = fmtNum(totalAdj);
  };

  const syncDetailPanel = () => {
    const ln = selectedIdx >= 0 ? lines[selectedIdx] : null;
    const set = (id, val) => { const n = el(id); if (n) n.textContent = val; };
    if (!ln) {
      ['ivaDetCurQty', 'ivaDetCurAvg', 'ivaDetCurVal', 'ivaDetAdjVal', 'ivaDetNewQty', 'ivaDetNewAvg', 'ivaDetNewVal'].forEach((id) => set(id, '—'));
      set('ivaDetAdjQty', '0.00');
      return;
    }
    const uom = ln.uom || 'Pcs';
    const curQty = Number(ln.current_qty) || 0;
    const curAvg = Number(ln.current_avg_cost) || 0;
    const curVal = curQty * curAvg;
    const adjAmt = Math.abs(Number(ln.adjustment_amount) || 0);
    const signed = String(ln.adjustment_dir || 'INCREASE').toUpperCase() === 'DECREASE' ? -adjAmt : adjAmt;
    const newAvg = Number(ln.new_average_cost) || calcNewAvg(curQty, curAvg, adjAmt, ln.adjustment_dir);
    const newVal = curQty * newAvg;
    set('ivaDetCurQty', `${fmtNum(curQty)} ${uom}`);
    set('ivaDetCurAvg', fmtNum(curAvg));
    set('ivaDetCurVal', fmtNum(curVal));
    set('ivaDetAdjQty', fmtNum(Number(ln.quantity) || 0));
    set('ivaDetAdjVal', fmtNum(signed));
    set('ivaDetNewQty', `${fmtNum(curQty)} ${uom}`);
    set('ivaDetNewAvg', fmtNum(newAvg));
    set('ivaDetNewVal', fmtNum(newVal));
    if (el('ivaLineNotes') && document.activeElement !== el('ivaLineNotes')) {
      el('ivaLineNotes').value = ln.lineremarks || '';
    }
  };

  const renderLines = () => {
    const body = el('ivaLinesBody');
    if (!body) return;
    if (!lines.length) {
      body.innerHTML = '<tr class="iva-empty"><td colspan="12">No journal lines. Click "+ Add line" to begin.</td></tr>';
      syncTotals();
      syncDetailPanel();
      if (el('ivaBtnRemoveLine')) el('ivaBtnRemoveLine').disabled = true;
      return;
    }
    body.innerHTML = lines.map((ln, idx) => {
      const sel = idx === selectedIdx ? ' is-selected' : '';
      const dir = String(ln.adjustment_dir || 'INCREASE');
      const checked = ln._checked ? ' checked' : '';
      return `<tr class="iva-line${sel}" data-idx="${idx}">
        <td><input type="checkbox" class="iva-row-check" data-idx="${idx}"${checked} /></td>
        <td><a href="#" class="item-link" data-pick="${idx}">${ln.itemcode || '—'}</a></td>
        <td>${ln.itemname || '—'}</td>
        <td>${siteCode() || '—'}</td>
        <td>${ln.warehouse_code || whCode() || '—'}</td>
        <td>${dir === 'DECREASE' ? 'Decrease' : 'Increase'}</td>
        <td class="num">${fmtNum(ln.quantity || 0)}</td>
        <td>${ln.uom || '—'}</td>
        <td class="num">${fmtNum(ln.unit_cost || ln.current_avg_cost || 0)}</td>
        <td class="num"><input type="number" class="iva-adj-amt" data-idx="${idx}" value="${ln.adjustment_amount || 0}" step="0.01" min="0" style="width:90px;text-align:right;border:1px solid #dee2e6;border-radius:3px;padding:2px 4px;" ${queryMode ? 'readonly' : ''} /></td>
        <td class="num">${fmtNum(ln.new_average_cost || 0)}</td>
        <td>${ln.fin_dim || el('ivaFinDim')?.value || '—'}</td>
      </tr>`;
    }).join('');

    body.querySelectorAll('tr.iva-line').forEach((tr) => {
      tr.addEventListener('click', (e) => {
        if (e.target.closest('.iva-row-check') || e.target.closest('.iva-adj-amt') || e.target.closest('[data-pick]')) return;
        selectedIdx = parseInt(tr.dataset.idx, 10);
        renderLines();
        syncDetailPanel();
      });
    });
    body.querySelectorAll('.iva-row-check').forEach((cb) => {
      cb.addEventListener('change', () => {
        const idx = parseInt(cb.dataset.idx, 10);
        if (lines[idx]) lines[idx]._checked = cb.checked;
        if (el('ivaBtnRemoveLine')) {
          el('ivaBtnRemoveLine').disabled = !lines.some((l) => l._checked);
        }
      });
    });
    body.querySelectorAll('.iva-adj-amt').forEach((inp) => {
      inp.addEventListener('change', () => {
        const idx = parseInt(inp.dataset.idx, 10);
        const ln = lines[idx];
        if (!ln) return;
        ln.adjustment_amount = Math.abs(Number(inp.value) || 0);
        ln.new_average_cost = calcNewAvg(ln.current_qty, ln.current_avg_cost, ln.adjustment_amount, ln.adjustment_dir);
        renderLines();
        selectedIdx = idx;
        syncDetailPanel();
        syncTotals();
      });
    });
    body.querySelectorAll('[data-pick]').forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        if (queryMode) return;
        selectedIdx = parseInt(a.dataset.pick, 10);
        openItemModal(selectedIdx);
      });
    });
    syncTotals();
    syncDetailPanel();
  };

  const fetchItemContext = async (itemCode) => {
    const params = new URLSearchParams({ item_code: String(itemCode), warehouse_code: whCode() });
    const res = await fetch(`${itemContextUrl}?${params.toString()}`);
    const data = await res.json();
    if (!data.success && data.error) throw new Error(data.error);
    return data;
  };

  const addLineFromItem = async (item, targetIdx = -1) => {
    try {
      const ctx = await fetchItemContext(item.code);
      const ln = {
        _id: lineIdSeq++,
        itemcode: item.code,
        itemname: item.name || ctx.itemname,
        uom: item.uom || ctx.uom || 'Pcs',
        warehouse_code: whCode() || ctx.warehouse_code || '',
        adjustment_dir: 'INCREASE',
        quantity: 0,
        unit_cost: Number(item.cost || ctx.current_avg_cost || 0),
        adjustment_amount: 0,
        current_qty: Number(ctx.current_qty || item.stock || 0),
        current_avg_cost: Number(ctx.current_avg_cost || item.averagecost || item.cost || 0),
        current_inv_value: Number(ctx.current_inv_value || 0),
        new_average_cost: Number(ctx.current_avg_cost || item.averagecost || item.cost || 0),
        fin_dim: el('ivaFinDim')?.value || '',
        lineremarks: '',
      };
      ln.current_inv_value = ln.current_qty * ln.current_avg_cost;
      if (targetIdx >= 0 && lines[targetIdx]) {
        lines[targetIdx] = { ...lines[targetIdx], ...ln };
        selectedIdx = targetIdx;
      } else {
        lines.push(ln);
        selectedIdx = lines.length - 1;
      }
      renderLines();
    } catch (err) {
      showFlash(err.message || 'Failed to load item context.', false);
    }
  };

  const itemModal = el('itemModal');
  const itemSearch = el('itemSearch');
  const itemPickBody = el('itemPickBody');
  let pickTargetIdx = -1;
  let popupItems = [];

  const renderItemPick = () => {
    if (!itemPickBody) return;
    const q = (itemSearch?.value || '').trim().toUpperCase();
    const filtered = popupItems.filter((it) => {
      if (!q) return true;
      const line = `${it.code} ${it.name || ''}`.toUpperCase();
      return line.includes(q);
    });
    if (!filtered.length) {
      itemPickBody.innerHTML = '<tr><td colspan="4" style="padding:12px;text-align:center;color:#6c757d;">No items found.</td></tr>';
      return;
    }
    itemPickBody.innerHTML = filtered.slice(0, 200).map((it) =>
      `<tr style="cursor:pointer;" data-code="${it.code}">
        <td style="padding:6px 8px;border-bottom:1px solid #eee;">${it.code}</td>
        <td style="padding:6px 8px;border-bottom:1px solid #eee;">${it.name || ''}</td>
        <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">${fmtNum(it.stock || 0, 2)}</td>
        <td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right;">${fmtNum(it.averagecost || it.cost || 0)}</td>
      </tr>`
    ).join('');
    itemPickBody.querySelectorAll('tr[data-code]').forEach((tr) => {
      tr.addEventListener('click', () => {
        const code = tr.dataset.code;
        const hit = popupItems.find((x) => String(x.code) === String(code));
        if (hit) {
          addLineFromItem(hit, pickTargetIdx);
          closeItemModal();
        }
      });
    });
  };

  const loadItems = async () => {
    const res = await fetch(`${itemsUrl}?limit=400`);
    const data = await res.json();
    popupItems = data.items || [];
    renderItemPick();
  };

  const openItemModal = (targetIdx = -1) => {
    pickTargetIdx = targetIdx;
    if (itemModal) itemModal.classList.remove('hidden');
    if (itemSearch) { itemSearch.value = ''; itemSearch.focus(); }
    if (!popupItems.length) loadItems();
    else renderItemPick();
  };

  const closeItemModal = () => {
    if (itemModal) itemModal.classList.add('hidden');
    pickTargetIdx = -1;
  };

  if (itemModal) {
    itemModal.querySelectorAll('[data-close="itemModal"]').forEach((n) => {
      n.addEventListener('click', closeItemModal);
    });
  }
  itemSearch?.addEventListener('input', renderItemPick);

  el('ivaBtnAddLine')?.addEventListener('click', () => {
    lines.push({
      _id: lineIdSeq++,
      itemcode: '',
      itemname: '',
      uom: 'Pcs',
      warehouse_code: whCode(),
      adjustment_dir: 'INCREASE',
      quantity: 0,
      unit_cost: 0,
      adjustment_amount: 0,
      current_qty: 0,
      current_avg_cost: 0,
      new_average_cost: 0,
      fin_dim: el('ivaFinDim')?.value || '',
      lineremarks: '',
    });
    selectedIdx = lines.length - 1;
    renderLines();
    openItemModal(selectedIdx);
  });

  el('ivaBtnRemoveLine')?.addEventListener('click', () => {
    lines = lines.filter((l) => !l._checked);
    selectedIdx = lines.length ? Math.min(selectedIdx, lines.length - 1) : -1;
    renderLines();
  });

  el('ivaSelectAll')?.addEventListener('change', (e) => {
    const on = e.target.checked;
    lines.forEach((l) => { l._checked = on; });
    renderLines();
    if (el('ivaBtnRemoveLine')) el('ivaBtnRemoveLine').disabled = !on || !lines.length;
  });

  el('ivaLineNotes')?.addEventListener('input', () => {
    if (selectedIdx >= 0 && lines[selectedIdx]) {
      lines[selectedIdx].lineremarks = el('ivaLineNotes').value;
    }
  });

  document.querySelectorAll('.iva-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.iva-tab').forEach((t) => t.classList.remove('is-active'));
      tab.classList.add('is-active');
      const key = tab.dataset.tab;
      el('ivaOverviewPanel').style.display = key === 'overview' ? '' : 'none';
      el('ivaOtherPanel').classList.toggle('is-active', key === 'other');
    });
  });

  const buildPayload = () => ({
    journal_no: el('ivaJournalNo')?.value || null,
    post: false,
    header: {
      journalname: el('ivaJournalName')?.value || '',
      description: el('ivaDescription')?.value || '',
      adjustment_type: el('ivaAdjType')?.value || 'VALUE',
      inventory_model: el('ivaInvModel')?.value || 'FIFO',
      journal_date: el('ivaJournalDate')?.value || '',
      posting_date: el('ivaPostingDate')?.value || '',
      warehouse_code: whCode(),
      warehouse_id: el('ivaWarehouse')?.selectedOptions?.[0]?.dataset?.whId || null,
      fin_dim: el('ivaFinDim')?.value || '',
      notes: el('ivaNotes')?.value || '',
      reference: el('ivaReference')?.value || '',
      adjustment_reason: el('ivaAdjReason')?.value || '',
    },
    lines: lines.filter((l) => l.itemcode).map((l, i) => ({
      slno: i + 1,
      itemcode: l.itemcode,
      itemname: l.itemname,
      warehouse_code: l.warehouse_code || whCode(),
      adjustment_dir: l.adjustment_dir || 'INCREASE',
      quantity: l.quantity || 0,
      uom: l.uom,
      unit_cost: l.unit_cost || l.current_avg_cost,
      adjustment_amount: l.adjustment_amount,
      new_average_cost: l.new_average_cost || calcNewAvg(l.current_qty, l.current_avg_cost, l.adjustment_amount, l.adjustment_dir),
      current_qty: l.current_qty,
      current_avg_cost: l.current_avg_cost,
      fin_dim: l.fin_dim || el('ivaFinDim')?.value || '',
      lineremarks: l.lineremarks || '',
    })),
  });

  const doSave = async (post = false) => {
    if (saveInFlight) return;
    const payload = buildPayload();
    if (!payload.lines.length) {
      showFlash('Add at least one line with an item and adjustment amount.', false);
      return;
    }
    const bad = payload.lines.find((l) => !l.adjustment_amount || l.adjustment_amount <= 0);
    if (bad) {
      showFlash('Each line needs an adjustment amount greater than zero.', false);
      return;
    }
    payload.post = post;
    saveInFlight = true;
    try {
      const res = await fetch(saveUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Save failed');
      showFlash(data.message || (post ? 'Posted.' : 'Saved.'));
      if (data.view_url) {
        window.setTimeout(() => { window.location.href = data.view_url; }, post ? 400 : 900);
      }
    } catch (err) {
      showFlash(err.message || 'Save failed.', false);
    } finally {
      saveInFlight = false;
    }
  };

  el('ivaBtnSave')?.addEventListener('click', () => doSave(false));
  el('ivaBtnPost')?.addEventListener('click', () => doSave(true));

  const loadInitial = () => {
    const raw = el('ivaInitialData')?.textContent || '{}';
    let data = {};
    try { data = JSON.parse(raw); } catch (_) { data = {}; }
    const hdr = data.header || {};
    const posted = String(hdr.posted || 'N').toUpperCase() === 'Y';
    if (hdr.journalname && el('ivaJournalName')) el('ivaJournalName').value = hdr.journalname;
    if (hdr.journalno && el('ivaJournalNo')) el('ivaJournalNo').value = hdr.journalno;
    if (hdr.description && el('ivaDescription')) el('ivaDescription').value = hdr.description;
    if (hdr.adjustment_type && el('ivaAdjType')) el('ivaAdjType').value = hdr.adjustment_type;
    if (hdr.inventory_model && el('ivaInvModel')) el('ivaInvModel').value = hdr.inventory_model;
    if (hdr.journal_date && el('ivaJournalDate')) {
      const d = String(hdr.journal_date).slice(0, 10);
      el('ivaJournalDate').value = d;
    }
    if (hdr.posting_date && el('ivaPostingDate')) {
      el('ivaPostingDate').value = String(hdr.posting_date).slice(0, 10);
    }
    if (hdr.warehouse_code && el('ivaWarehouse')) el('ivaWarehouse').value = hdr.warehouse_code;
    if (hdr.fin_dim && el('ivaFinDim')) el('ivaFinDim').value = hdr.fin_dim;
    if (hdr.notes && el('ivaNotes')) el('ivaNotes').value = hdr.notes;
    if (hdr.reference && el('ivaReference')) el('ivaReference').value = hdr.reference;
    if (hdr.adjustment_reason && el('ivaAdjReason')) el('ivaAdjReason').value = hdr.adjustment_reason;
    if (el('ivaStatusLabel')) {
      el('ivaStatusLabel').textContent = posted ? 'Posted' : (hdr.status === 'IN_PROGRESS' ? 'In progress' : (hdr.status || 'In progress'));
    }
    if (el('ivaPostedToggle')) el('ivaPostedToggle').checked = posted;
    lines = (data.lines || []).map((ln) => ({
      _id: lineIdSeq++,
      itemcode: ln.itemcode,
      itemname: ln.itemname,
      uom: ln.uom,
      warehouse_code: ln.warehouse_code,
      adjustment_dir: ln.adjustment_dir || 'INCREASE',
      quantity: ln.quantity || 0,
      unit_cost: ln.unit_cost,
      adjustment_amount: ln.adjustment_amount,
      new_average_cost: ln.new_average_cost,
      current_qty: ln.current_qty,
      current_avg_cost: ln.current_avg_cost,
      current_inv_value: ln.current_inv_value,
      fin_dim: ln.fin_dim,
      lineremarks: ln.lineremarks,
    }));
    if (lines.length) selectedIdx = 0;
    renderLines();
  };

  loadInitial();
});
