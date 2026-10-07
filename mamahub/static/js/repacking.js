document.addEventListener('DOMContentLoaded', () => {
  const el = (id) => document.getElementById(id);
  const fmt = (n, d = 3) => {
    const v = Number(n || 0);
    return Number.isFinite(v) ? v.toFixed(d) : (0).toFixed(d);
  };
  const readJson = async (res) => {
    let data = {};
    try { data = await res.json(); } catch (_) { data = {}; }
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  };
  const normalizeItem = (r) => ({
    itemcode: r?.itemcode ?? r?.code ?? '',
    itemname: r?.itemname ?? r?.name ?? '',
    baseuom: r?.baseuom ?? r?.uom ?? 'NOS',
    currentstock: Number(r?.currentstock ?? r?.stock ?? 0),
    costprice: Number(r?.costprice ?? r?.cost ?? 0),
    best_store: r?.best_store ?? r?.store ?? '',
  });

  const normalizeWarehouseItem = (r) => ({
    itemcode: r?.itemcode ?? r?.code ?? '',
    itemname: r?.itemname ?? r?.name ?? '',
    baseuom: r?.uom ?? r?.baseuom ?? 'NOS',
    currentstock: Number(r?.availableqty ?? r?.currentstock ?? r?.stock ?? 0),
    costprice: Number(r?.costprice ?? r?.cost ?? 0),
    best_store: normStore(ids.store?.value || ''),
    barcode: r?.barcode ?? '',
  });

  const RP_BATCH_ENABLED = !!window.RP_BATCH_ENABLED;
  const RP_BIN_ENABLED = !!window.RP_BIN_ENABLED;
  const queryMode = window.RP_QUERY_MODE === true || window.RP_QUERY_MODE === 'true';
  const listUrl = window.RP_LIST_URL || '/purchase/repacking/list';

  const state = {
    pickTarget: 'src', items: [], src: null, dst: null, warehouses: [],
    srcTracking: { batch: false, bin: false },
    dstTracking: { batch: false, bin: false },
    saveInFlight: false,
    saveCompleted: false,
  };
  const itemModal = el('rpItemModal');
  const itemSearch = el('rpItemSearch');
  const itemBody = el('rpItemBody');
  const whModalBg = el('rpWhModalBg');
  const whSearch = el('rpWhSearch');
  const whList = el('rpWhList');
  const storeHint = el('rpStoreHint');

  const normStore = (v) => String(v || '').trim().toUpperCase();

  const ids = {
    docNo: el('rpDocNo'), date: el('rpDate'), store: el('rpStore'), remarks: el('rpRemarks'),
    srcCode: el('rpSrcCode'), srcName: el('rpSrcName'), srcUom: el('rpSrcUom'), srcCurrent: el('rpSrcCurrent'), srcQty: el('rpSrcQty'), srcAfter: el('rpSrcAfter'),
    dstCode: el('rpDstCode'), dstName: el('rpDstName'), dstUom: el('rpDstUom'), dstCurrent: el('rpDstCurrent'), dstQty: el('rpDstQty'), dstAfter: el('rpDstAfter'),
    srcMove: el('rpSrcMove'), dstMove: el('rpDstMove'), storeView: el('rpStoreView'), save: el('rpSave'),
    srcLot: el('rpSrcLot'), srcBin: el('rpSrcBin'), dstBin: el('rpDstBin'),
    srcLotWrap: el('rpSrcLotWrap'), srcBinWrap: el('rpSrcBinWrap'),
    dstBatchWrap: el('rpDstBatchWrap'), dstBinWrap: el('rpDstBinWrap'),
  };

  const fetchStock = async (itemCode, store) => {
    const q = new URLSearchParams({ item_code: String(itemCode || ''), store: String(store || '') }).toString();
    const data = await readJson(await fetch(`/purchase/stock-adjustment/api/item-stock?${q}`));
    if (!data.success) throw new Error(data.error || 'Stock lookup failed');
    return data;
  };

  const updateTotals = () => {
    const srcCur = Number(ids.srcCurrent.value || 0);
    const srcQty = Number(ids.srcQty.value || 0);
    const dstCur = Number(ids.dstCurrent.value || 0);
    const dstQty = Number(ids.dstQty.value || 0);
    ids.srcAfter.value = fmt(srcCur - srcQty);
    ids.dstAfter.value = fmt(dstCur + dstQty);
    ids.srcMove.textContent = fmt(-Math.abs(srcQty));
    ids.dstMove.textContent = fmt(Math.abs(dstQty));
    ids.storeView.textContent = (ids.store.value || '-').trim() || '-';
  };

  const itemModalTitle = itemModal?.querySelector('.modal__header h3');

  const selectedWarehouse = () => normStore(ids.store?.value || '');

  const setTrackingVisible = (wrap, show) => {
    if (!wrap) return;
    wrap.classList.toggle('rp-tracking-hidden', !show);
    wrap.classList.toggle('rp-tracking-visible', !!show);
  };

  const clearTracking = (target) => {
    const prefix = target === 'src' ? 'src' : 'dst';
    state[`${prefix}Tracking`] = { batch: false, bin: false };
    if (target === 'src') {
      if (ids.srcLot) ids.srcLot.innerHTML = '<option value="">— FEFO / auto —</option>';
      if (ids.srcBin) ids.srcBin.innerHTML = '<option value="">—</option>';
      setTrackingVisible(ids.srcLotWrap, false);
      setTrackingVisible(ids.srcBinWrap, false);
    } else {
      setTrackingVisible(ids.dstBatchWrap, false);
      if (ids.dstBin) ids.dstBin.innerHTML = '<option value="">—</option>';
      setTrackingVisible(ids.dstBinWrap, false);
    }
  };

  const loadBinsForWarehouse = async (storeCode, selectEl) => {
    if (!RP_BIN_ENABLED || !selectEl) return;
    selectEl.innerHTML = '<option value="">—</option>';
    const sc = String(storeCode || '').trim();
    if (!sc) return;
    try {
      const data = await readJson(await fetch(`/purchase/stock-transfer/api/warehouse-bins?wh=${encodeURIComponent(sc)}`));
      (Array.isArray(data.bins) ? data.bins : []).forEach((b) => {
        const sid = b.storage_id;
        const code = String(b.code || '').trim();
        if (sid == null || !code) return;
        const opt = document.createElement('option');
        opt.value = String(sid);
        opt.textContent = code + (b.name ? ` — ${b.name}` : '');
        selectEl.appendChild(opt);
      });
    } catch (_) { /* ignore */ }
  };

  const refreshSourceLots = async (itemCode) => {
    if (!RP_BATCH_ENABLED || !ids.srcLot) return;
    ids.srcLot.innerHTML = '<option value="">— FEFO / auto —</option>';
    const ic = parseInt(String(itemCode || '0'), 10) || 0;
    if (!ic) return;
    try {
      const data = await readJson(await fetch(`/purchase/stock-transfer/api/lots?item_code=${encodeURIComponent(String(ic))}`));
      (Array.isArray(data.lots) ? data.lots : []).forEach((lot) => {
        if (lot.lot_blocked) return;
        const opt = document.createElement('option');
        opt.value = String(lot.lot_id);
        const exp = lot.expiry_date ? ` exp:${lot.expiry_date}` : '';
        opt.textContent = `${lot.batch_no || 'LOT'} (${Number(lot.qty || 0).toFixed(3)})${exp}`;
        ids.srcLot.appendChild(opt);
      });
    } catch (_) { /* ignore */ }
  };

  const refreshItemTracking = async (target, itemCode) => {
    const prefix = target === 'src' ? 'src' : 'dst';
    state[`${prefix}Tracking`] = { batch: false, bin: false };
    const ic = parseInt(String(itemCode || '0'), 10) || 0;
    if (!ic) {
      clearTracking(target);
      return;
    }
    try {
      const data = await readJson(await fetch(`/purchase/stock-transfer/api/item-batch-tracked/${ic}`));
      if (RP_BATCH_ENABLED) {
        state[`${prefix}Tracking`].batch = !!(data.batch_tracked && data.batch_branch_enabled);
      }
      if (RP_BIN_ENABLED) {
        state[`${prefix}Tracking`].bin = !!(data.bin_configured && data.bin_branch_enabled);
      }
    } catch (_) { /* ignore */ }

    const store = selectedWarehouse();
    if (target === 'src') {
      setTrackingVisible(ids.srcLotWrap, RP_BATCH_ENABLED && state.srcTracking.batch);
      setTrackingVisible(ids.srcBinWrap, RP_BIN_ENABLED && state.srcTracking.bin);
      if (RP_BATCH_ENABLED && state.srcTracking.batch) await refreshSourceLots(ic);
      if (RP_BIN_ENABLED && state.srcTracking.bin) await loadBinsForWarehouse(store, ids.srcBin);
    } else {
      setTrackingVisible(ids.dstBatchWrap, RP_BATCH_ENABLED && state.dstTracking.batch);
      setTrackingVisible(ids.dstBinWrap, RP_BIN_ENABLED && state.dstTracking.bin);
      if (RP_BIN_ENABLED && state.dstTracking.bin) await loadBinsForWarehouse(store, ids.dstBin);
    }
  };

  const reloadWarehouseBins = async () => {
    const store = selectedWarehouse();
    if (state.src?.itemcode && state.srcTracking.bin) await loadBinsForWarehouse(store, ids.srcBin);
    if (state.dst?.itemcode && state.dstTracking.bin) await loadBinsForWarehouse(store, ids.dstBin);
  };

  const renderItems = () => {
    const rows = state.items || [];
    const emptyMsg = state.pickTarget === 'src'
      ? 'No items with stock in the selected warehouse.'
      : 'No items found.';
    itemBody.innerHTML = rows.map((r) => `
      <tr data-code="${String(r.itemcode || '').replace(/"/g, '&quot;')}">
        <td style="font-family:ui-monospace,monospace;font-weight:700;">${r.itemcode || ''}</td>
        <td>${r.itemname || ''}</td>
        <td>${r.baseuom || 'NOS'}</td>
        <td class="num">${fmt(r.currentstock || 0)}</td>
        <td>${r.best_store || selectedWarehouse() || ''}</td>
      </tr>
    `).join('') || `<tr><td colspan="5" style="text-align:center;color:#64748b;padding:18px;">${emptyMsg}</td></tr>`;
  };

  const searchSourceItems = async (term = '') => {
    const store = selectedWarehouse();
    if (!store) throw new Error('Select a warehouse first.');
    const q = new URLSearchParams({ from_store: store, search: term, limit: '300' }).toString();
    const data = await readJson(await fetch(`/purchase/stock-transfer/api/items?${q}`));
    state.items = (Array.isArray(data.items) ? data.items : [])
      .map(normalizeWarehouseItem)
      .filter((r) => Number(r.currentstock) > 0);
    renderItems();
  };

  const searchOutputItems = async (term = '') => {
    const q = new URLSearchParams({ search: term, limit: '300' }).toString();
    const data = await readJson(await fetch(`/purchase/stock-adjustment/api/items?${q}`));
    state.items = Array.isArray(data.items) ? data.items.map(normalizeItem) : [];
    renderItems();
  };

  const searchItems = async (term = '') => {
    if (state.pickTarget === 'src') await searchSourceItems(term);
    else await searchOutputItems(term);
  };

  const applyItem = async (target, item) => {
    const it = target === 'src' ? normalizeWarehouseItem(item) : normalizeItem(item);
    const prefix = target === 'src' ? 'src' : 'dst';
    if (target === 'src') {
      const store = selectedWarehouse();
      if (!store) throw new Error('Select a warehouse first.');
      if (!(Number(it.currentstock) > 0)) {
        throw new Error('Source item must have stock greater than zero in the selected warehouse.');
      }
    }
    state[prefix] = it;
    ids[`${prefix}Code`].value = it.itemcode || '';
    ids[`${prefix}Name`].value = it.itemname || '';
    ids[`${prefix}Uom`].value = it.baseuom || 'NOS';
    if (target === 'src') {
      ids[`${prefix}Current`].value = fmt(it.currentstock || 0);
    } else {
      const store = selectedWarehouse();
      if (!store) throw new Error('Select a warehouse first.');
      const stock = await fetchStock(it.itemcode, store);
      ids[`${prefix}Current`].value = fmt(stock.current_qty || 0);
    }
    await refreshItemTracking(target, it.itemcode);
    if (target === 'src' && !ids.dstQty.value && ids.srcQty.value) ids.dstQty.value = ids.srcQty.value;
    updateTotals();
  };

  const loadSourceItemByCode = async (code) => {
    const c = String(code || '').trim();
    if (!c) return;
    const store = selectedWarehouse();
    if (!store) throw new Error('Select a warehouse first.');
    const q = new URLSearchParams({ from_store: store, exact_item_code: c, limit: '10' }).toString();
    const data = await readJson(await fetch(`/purchase/stock-transfer/api/items?${q}`));
    const rows = (Array.isArray(data.items) ? data.items : [])
      .map(normalizeWarehouseItem)
      .filter((r) => Number(r.currentstock) > 0);
    const item = rows.find((r) => String(r.itemcode || '') === c) || rows[0];
    if (!item) throw new Error('Item not found or has no stock in the selected warehouse.');
    await applyItem('src', item);
  };

  const loadItemByCode = async (target, code) => {
    if (target === 'src') {
      await loadSourceItemByCode(code);
      return;
    }
    const c = String(code || '').trim();
    if (!c) return;
    const q = new URLSearchParams({ search: c, limit: '100' }).toString();
    const data = await readJson(await fetch(`/purchase/stock-adjustment/api/items?${q}`));
    const rows = Array.isArray(data.items) ? data.items.map(normalizeItem) : [];
    const item = rows.find((r) => String(r.itemcode || '') === c) || rows[0];
    if (!item) throw new Error('Item not found');
    await applyItem(target, item);
  };

  const openPicker = (target) => {
    state.pickTarget = target;
    if (target === 'src' && !selectedWarehouse()) {
      alert('Select a warehouse first.');
      openWhModal();
      return;
    }
    if (itemModalTitle) {
      itemModalTitle.textContent = target === 'src'
        ? 'Select source item (stock > 0 in warehouse)'
        : 'Select output item';
    }
    if (itemSearch) {
      itemSearch.placeholder = target === 'src'
        ? 'Search items with stock in selected warehouse…'
        : 'Search item code/name…';
    }
    itemSearch.value = '';
    itemModal.classList.remove('hidden');
    searchItems().catch((e) => alert(e.message || 'Item search failed'));
    setTimeout(() => itemSearch.focus(), 50);
  };

  const parseSaveResponse = async (res) => {
    let data = {};
    try { data = await res.json(); } catch (_) { data = {}; }
    if (typeof data.save_nonce === 'string' && data.save_nonce) {
      window.__GLOBAL_SAVE_NONCE = data.save_nonce;
    }
    if (res.status === 423 || data.save_session_locked) {
      throw new Error(data.error || 'A save is already in progress. Please wait.');
    }
    if (res.status === 409 || data.replay_blocked) {
      throw new Error((data.error || 'Duplicate save request.') + ' Try Save again.');
    }
    if (!res.ok || !data.success) {
      throw new Error(data.error || `Save failed (${res.status})`);
    }
    return data;
  };

  const setSaveButtonsDisabled = (disabled, label) => {
    if (!ids.save) return;
    ids.save.disabled = disabled;
    if (label) ids.save.textContent = label;
  };

  const save = async () => {
    if (queryMode) return;
    if (state.saveInFlight || state.saveCompleted) return;
    const docNo = Number(ids.docNo.value || 0);
    const store = (ids.store.value || '').trim();
    const srcCode = Number(ids.srcCode.value || 0);
    const dstCode = Number(ids.dstCode.value || 0);
    const srcQty = Number(ids.srcQty.value || 0);
    const dstQty = Number(ids.dstQty.value || 0);
    const srcCur = Number(ids.srcCurrent.value || 0);
    const dstCur = Number(ids.dstCurrent.value || 0);
    if (!docNo || !ids.date.value) return alert('Document no and date are required.');
    if (!store) return alert('Warehouse is required.');
    if (!srcCode || !dstCode) return alert('Choose source and output items.');
    if (srcCode === dstCode) return alert('Source and output item must be different.');
    if (!(srcQty > 0) || !(dstQty > 0)) return alert('Source qty and output qty must be greater than zero.');
    if (srcCur + 0.000001 < srcQty) return alert('Source item has insufficient stock in this warehouse.');
    if (RP_BIN_ENABLED && state.srcTracking.bin && !(ids.srcBin?.value || '').trim()) {
      return alert('Select from bin for the source item.');
    }
    if (RP_BIN_ENABLED && state.dstTracking.bin && !(ids.dstBin?.value || '').trim()) {
      return alert('Select to bin for the output item in the same warehouse.');
    }
    const srcName = ids.srcName.value || '';
    const dstName = ids.dstName.value || '';
    const lines = [
      {
        item_code: srcCode, item_name: srcName, uom: ids.srcUom.value || 'NOS', store,
        current_qty: srcCur, adjust_qty: -Math.abs(srcQty), new_qty: srcCur - srcQty,
        base_qty: -Math.abs(srcQty), cost: Number(state.src?.costprice || 0),
        remarks: `Repack OUT to ${dstCode}`,
      },
      {
        item_code: dstCode, item_name: dstName, uom: ids.dstUom.value || 'NOS', store,
        current_qty: dstCur, adjust_qty: Math.abs(dstQty), new_qty: dstCur + dstQty,
        base_qty: Math.abs(dstQty), cost: Number(state.dst?.costprice || 0),
        remarks: `Repack IN from ${srcCode}`,
      },
    ];
    const srcLotId = String(ids.srcLot?.value || '').trim();
    if (srcLotId) lines[0].lot_id = srcLotId;
    const srcBinId = String(ids.srcBin?.value || '').trim();
    if (srcBinId) lines[0].from_storage_id = srcBinId;
    const dstBinId = String(ids.dstBin?.value || '').trim();
    if (dstBinId) lines[1].to_storage_id = dstBinId;
    const payload = {
      repack_no: docNo,
      repack_date: ids.date.value,
      warehouse: store,
      remarks: ids.remarks.value || `Repack ${srcCode} -> ${dstCode}`,
      lines,
    };
    state.saveInFlight = true;
    const prevTopLabel = ids.save?.textContent || 'Save Repacking';
    setSaveButtonsDisabled(true, 'Saving…');
    try {
      const res = await fetch('/purchase/repacking/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        loadingMessage: 'Saving repacking…',
      });
      const data = await parseSaveResponse(res);
      state.saveCompleted = true;
      window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data }));
      if (data.pdf_url) {
        const pdfQs = data.gl_voucher_no
          ? `gl_voucher_no=${encodeURIComponent(data.gl_voucher_no)}`
          : '';
        const pdfOpenUrl = pdfQs ? `${data.pdf_url}?${pdfQs}` : data.pdf_url;
        window.open(pdfOpenUrl, '_blank', 'noopener,noreferrer');
      }
      window.location.href = data.list_url || listUrl;
    } catch (e) {
      alert(e.message || 'Save failed');
      window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: { error: e.message } }));
    } finally {
      state.saveInFlight = false;
      if (!state.saveCompleted) {
        if (ids.save) {
          ids.save.disabled = false;
          ids.save.textContent = prevTopLabel;
        }
      }
    }
  };

  const closeWhModal = () => {
    if (!whModalBg) return;
    whModalBg.classList.remove('show');
    whModalBg.setAttribute('aria-hidden', 'true');
    if (whSearch) whSearch.value = '';
  };

  const renderWhList = () => {
    if (!whList) return;
    const q = normStore(whSearch?.value || '');
    const rows = (state.warehouses || []).filter((s) => {
      const code = normStore(s.code);
      const desc = String(s.description || '').trim().toUpperCase();
      if (!code || code === 'TRANSIT') return false;
      if (q && !code.includes(q) && !desc.includes(q)) return false;
      return true;
    });
    if (!rows.length) {
      whList.innerHTML = '<div style="padding:10px;color:#6c757d;font-size:13px;">No warehouses found.</div>';
      return;
    }
    whList.innerHTML = rows.map((s) => {
      const code = normStore(s.code);
      const desc = String(s.description || '').trim();
      const label = desc ? `${code} — ${desc}` : code;
      return `<button type="button" class="rp-wh-btn" data-wh="${code.replace(/"/g, '&quot;')}">${label}</button>`;
    }).join('');
    whList.querySelectorAll('.rp-wh-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const val = normStore(btn.getAttribute('data-wh'));
        if (!val) return;
        ids.store.value = val;
        closeWhModal();
        updateTotals();
        reloadWarehouseBins().catch(() => {});
        if (ids.srcCode.value) await loadSourceItemByCode(ids.srcCode.value).catch(clearSourceIfNoStock);
        if (ids.dstCode.value) await loadItemByCode('dst', ids.dstCode.value).catch(() => {});
        ids.store.focus();
      });
    });
  };

  const openWhModal = () => {
    if (!whModalBg) return;
    if (!state.warehouses.length) {
      alert('No warehouses loaded for this branch.');
      return;
    }
    whModalBg.classList.add('show');
    whModalBg.setAttribute('aria-hidden', 'false');
    renderWhList();
    setTimeout(() => whSearch?.focus(), 50);
  };

  const clearSourceIfNoStock = () => {
    state.src = null;
    ids.srcCode.value = '';
    ids.srcName.value = '';
    ids.srcUom.value = 'NOS';
    ids.srcCurrent.value = '';
    ids.srcQty.value = '';
    ids.srcAfter.value = '';
    clearTracking('src');
    updateTotals();
  };

  const loadWarehouses = async () => {
    if (storeHint) storeHint.textContent = 'Loading warehouses…';
    try {
      const data = await readJson(await fetch('/purchase/stock-transfer/api/stores'));
      const rows = Array.isArray(data.stores) ? data.stores : [];
      state.warehouses = rows.map((s) => {
        if (typeof s === 'string') return { code: s, description: '' };
        return {
          code: s.code ?? s.warehouse_code ?? s.store ?? '',
          description: s.description ?? s.name ?? s.warehouse_name ?? '',
        };
      }).filter((s) => normStore(s.code));
      if (storeHint) {
        storeHint.textContent = state.warehouses.length
          ? `${state.warehouses.length} warehouse(s) — F1 or ▾ to pick`
          : 'No warehouses for this branch';
      }
      if (!ids.store.value && state.warehouses.length) {
        const first = state.warehouses.find((s) => normStore(s.code) !== 'TRANSIT') || state.warehouses[0];
        if (first) ids.store.value = normStore(first.code);
        updateTotals();
      }
    } catch (e) {
      if (storeHint) storeHint.textContent = e.message || 'Could not load warehouses';
    }
  };

  document.querySelectorAll('[data-rp-pick]').forEach((btn) => btn.addEventListener('click', () => openPicker(btn.getAttribute('data-rp-pick'))));
  el('rpStorePick')?.addEventListener('click', openWhModal);
  whModalBg?.addEventListener('click', (e) => {
    if (e.target === whModalBg) closeWhModal();
  });
  el('rpWhModalClose')?.addEventListener('click', closeWhModal);
  whSearch?.addEventListener('input', renderWhList);
  ids.store?.addEventListener('keydown', (e) => {
    if (e.key === 'F1') {
      e.preventDefault();
      openWhModal();
    }
  });
  itemModal?.addEventListener('click', (e) => {
    if (e.target.getAttribute('data-close') === 'rpItemModal' || e.target.classList.contains('modal__overlay') || e.target.classList.contains('modal__close')) {
      itemModal.classList.add('hidden');
    }
  });
  itemBody?.addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-code]');
    if (!tr) return;
    const item = state.items.find((r) => String(r.itemcode || '') === String(tr.getAttribute('data-code') || ''));
    if (!item) return;
    applyItem(state.pickTarget, item).then(() => itemModal.classList.add('hidden')).catch((err) => alert(err.message || 'Failed to apply item'));
  });
  itemSearch?.addEventListener('input', () => {
    clearTimeout(itemSearch._rpTimer);
    itemSearch._rpTimer = setTimeout(() => searchItems(itemSearch.value).catch((e) => alert(e.message || 'Search failed')), 250);
  });
  ids.srcCode?.addEventListener('keydown', (e) => {
    if (e.key === 'F1') { e.preventDefault(); openPicker('src'); }
    if (e.key === 'Enter') loadItemByCode('src', ids.srcCode.value).catch((err) => alert(err.message || 'Item not found'));
  });
  ids.dstCode?.addEventListener('keydown', (e) => {
    if (e.key === 'F1') { e.preventDefault(); openPicker('dst'); }
    if (e.key === 'Enter') loadItemByCode('dst', ids.dstCode.value).catch((err) => alert(err.message || 'Item not found'));
  });
  ids.srcCode?.addEventListener('change', () => loadSourceItemByCode(ids.srcCode.value).catch(clearSourceIfNoStock));
  ids.dstCode?.addEventListener('change', () => loadItemByCode('dst', ids.dstCode.value).catch(() => {}));
  ids.store?.addEventListener('change', () => {
    reloadWarehouseBins().catch(() => {});
    if (ids.srcCode.value) loadSourceItemByCode(ids.srcCode.value).catch(clearSourceIfNoStock);
    if (ids.dstCode.value) loadItemByCode('dst', ids.dstCode.value).catch(() => {});
    updateTotals();
  });
  ids.srcQty?.addEventListener('input', () => {
    if (!ids.dstQty.value) ids.dstQty.value = ids.srcQty.value;
    updateTotals();
  });
  ids.dstQty?.addEventListener('input', updateTotals);
  ids.save?.addEventListener('click', () => save().catch((e) => alert(e.message || 'Save failed')));

  const loadInitialData = async () => {
    const init = window.RP_INITIAL_DATA;
    if (!init || !init.header) return;
    const h = init.header;
    if (h.repack_no != null) ids.docNo.value = String(h.repack_no);
    if (h.repack_date) ids.date.value = String(h.repack_date).slice(0, 10);
    if (h.warehouse) ids.store.value = normStore(h.warehouse);
    if (h.remarks) ids.remarks.value = h.remarks;
    const lines = Array.isArray(init.lines) ? init.lines : [];
    if (lines[0]) {
      await applyItem('src', {
        itemcode: lines[0].item_code,
        itemname: lines[0].item_name,
        baseuom: lines[0].uom,
        currentstock: lines[0].current_qty,
        costprice: lines[0].cost,
      });
      ids.srcQty.value = fmt(Math.abs(Number(lines[0].adjust_qty || lines[0].base_qty || 0)));
      if (lines[0].lot_id && ids.srcLot) ids.srcLot.value = String(lines[0].lot_id);
      if (lines[0].from_storage_id && ids.srcBin) ids.srcBin.value = String(lines[0].from_storage_id);
    }
    if (lines[1]) {
      await applyItem('dst', {
        itemcode: lines[1].item_code,
        itemname: lines[1].item_name,
        baseuom: lines[1].uom,
        currentstock: lines[1].current_qty,
        costprice: lines[1].cost,
      });
      ids.dstQty.value = fmt(Math.abs(Number(lines[1].adjust_qty || lines[1].base_qty || 0)));
      if (lines[1].to_storage_id && ids.dstBin) ids.dstBin.value = String(lines[1].to_storage_id);
    }
    updateTotals();
  };

  const applyQueryMode = () => {
    if (!queryMode) return;
    [
      ids.srcCode, ids.dstCode, ids.srcUom, ids.dstUom, ids.srcQty, ids.dstQty,
      ids.srcLot, ids.srcBin, ids.dstBin, ids.storePick,
    ].filter(Boolean).forEach((node) => {
      if (node.tagName === 'SELECT') node.disabled = true;
      else node.readOnly = true;
    });
    document.querySelectorAll('[data-rp-pick]').forEach((btn) => { btn.disabled = true; });
    if (ids.save) ids.save.style.display = 'none';
  };

  loadWarehouses()
    .then(() => loadInitialData())
    .then(updateTotals)
    .then(applyQueryMode)
    .catch(() => { updateTotals(); applyQueryMode(); });
});
