document.addEventListener('DOMContentLoaded', () => {
    const el = (id) => document.getElementById(id);
    const adjNo = el('adjNo');
    const adjDate = el('adjDate');
    const adjRemarks = el('adjRemarks');
    const btnSave = el('btnSaveAdjustment');
    const body = el('adjBody');

    const entryBarcode = el('entryBarcode');
    const entryItemCode = el('entryItemCode');
    const entryItemName = el('entryItemName');
    const entryUom = el('entryUom');
    const entryStore = el('entryStore');
    const entryLotId = el('entryLotId');
    const entryCurrentQty = el('entryCurrentQty');
    const entryAdjustQty = el('entryAdjustQty');
    const entryNewQty = el('entryNewQty');
    const btnAddLine = el('btnAddLine');
    const btnItemPicker = el('btnItemPicker');
    const btnStorePicker = el('btnStorePicker');

    const itemModal = el('itemModal');
    const warehouseModal = el('warehouseModal');
    const warehouseSearch = el('warehouseSearch');
    const warehouseTableBody = el('warehouseTableBody');
    const itemSearch = el('itemSearch');
    const itemTableBody = el('itemTableBody');
    const itemSortBy = el('itemSortBy');
    const itemSortDir = el('itemSortDir');
    const itemCount = el('itemCount');
    const itemTable = el('itemTable');
    const btnImportExcel = el('btnImportExcel');
    const btnImportPostJob = el('btnImportPostJob');
    const stkAdjExcelFile = el('stkAdjExcelFile');
    const stkAdjLargeExcelFile = el('stkAdjLargeExcelFile');
    const importExcelUrl = window.__STK_ADJ_IMPORT_URL__ || '/purchase/stock-adjustment/api/import-excel';
    const importPostJobUrl = window.__STK_ADJ_IMPORT_POST_JOB_URL__ || '/purchase/stock-adjustment/api/import-post-job';
    const warehousesApiUrl = window.__STK_ADJ_WAREHOUSES_URL__ || '/purchase/stock-adjustment/api/warehouses';
    const listUrl = window.__STK_ADJ_LIST_URL__ || '/purchase/stock-adjustment/list';
    const queryMode = window.__STK_ADJ_QUERY_MODE__ === true
        || window.__STK_ADJ_QUERY_MODE__ === 'true';
    const canEdit = window.__STK_ADJ_CAN_EDIT__ !== false
        && window.__STK_ADJ_CAN_EDIT__ !== 'false';
    const warehouseEnabled = window.__STK_ADJ_WAREHOUSE_ENABLED__ === true
        || window.__STK_ADJ_WAREHOUSE_ENABLED__ === 'true';

    let currentItem = null;
    let popupItems = [];
    let popupWarehouses = [];
    let popupSortKey = 'itemcode';
    let popupSortDir = 'asc';
    let warehousesLoaded = false;
    let saveInFlight = false;
    let saveCompleted = false;
    let addLineInFlight = false;
    let suppressAddLineClick = false;
    let inlinePickRow = null;
    let inlinePickStoreRow = null;
    const uomFactorCache = {};
    const uomCostCache = {};
    const storeListCache = {};

    const SA_INLINE_COLS = {
        'sa-col-barcode': { ds: 'barcode', type: 'text' },
        'sa-col-itemcode': { ds: 'itemCode', type: 'text' },
        'sa-col-lot': { ds: 'lotId', type: 'text' },
        'sa-col-adjustqty': { ds: 'adjustQty', type: 'number' },
    };
    const SA_INLINE_ORDER = ['sa-col-barcode', 'sa-col-itemcode', 'sa-col-lot', 'sa-col-adjustqty'];
    const SA_FIELD_TO_COL = {
        item_code: 'sa-col-itemcode',
        uom: 'sa-col-uom',
        store: 'sa-col-store',
        lot_id: 'sa-col-lot',
        adjust_qty: 'sa-col-adjustqty',
    };
    const ENTRY_INPUTS = [entryBarcode, entryItemCode, entryStore, entryLotId, entryAdjustQty];
    const HEADER_INPUTS = [adjDate, adjRemarks];
    const ENTRY_FIELD_TO_COL = {
        item_code: 'sa-col-itemcode',
        uom: 'sa-col-uom',
        store: 'sa-col-store',
        adjust_qty: 'sa-col-adjustqty',
    };
    const ENTRY_FIELD_INPUTS = {
        item_code: entryItemCode,
        uom: entryUom,
        store: entryStore,
        adjust_qty: entryAdjustQty,
    };
    const ENTRY_INVALID_FOCUS_ORDER = ['item_code', 'uom', 'store', 'adjust_qty'];
    let inlineEditFinish = null;

    const getEntryRow = () => body.querySelector('tr.sa-line-entry');
    const ensureEntryRow = () => {
        const entry = getEntryRow();
        if (entry && body.lastElementChild !== entry) body.appendChild(entry);
        return entry;
    };
    const insertLineBeforeEntry = (row) => {
        const entry = ensureEntryRow();
        const empty = body.querySelector('.empty-row');
        if (empty) empty.remove();
        if (entry) body.insertBefore(row, entry);
        else body.appendChild(row);
    };
    const syncEntryRowActive = () => {
        const entry = getEntryRow();
        if (!entry) return;
        const hasCode = !!String(entryItemCode?.value || '').trim();
        entry.classList.toggle('sa-line-entry--active', hasCode);
    };
    const markEntryFieldInvalid = (fieldKey, bad, msg) => {
        const col = ENTRY_FIELD_TO_COL[fieldKey];
        const entry = getEntryRow();
        if (!col || !entry) return;
        const td = entry.querySelector(`.${col}`);
        if (!td) return;
        td.classList.remove('sa-cell-checking');
        if (bad) {
            td.classList.add('sa-cell-invalid');
            td.title = msg || 'Invalid';
        } else {
            td.classList.remove('sa-cell-invalid');
            td.removeAttribute('title');
        }
    };
    const clearEntryValidation = () => {
        Object.values(ENTRY_FIELD_TO_COL).forEach((col) => {
            const entry = getEntryRow();
            const td = entry && entry.querySelector(`.${col}`);
            if (td) {
                td.classList.remove('sa-cell-invalid', 'sa-cell-checking');
                td.removeAttribute('title');
            }
        });
    };
    const entryHasInvalid = () => !!getEntryRow()?.querySelector('td.sa-cell-invalid');
    const focusFirstEntryInvalid = () => {
        const entry = getEntryRow();
        if (!entry) return;
        for (const field of ENTRY_INVALID_FOCUS_ORDER) {
            const col = ENTRY_FIELD_TO_COL[field];
            const td = col && entry.querySelector(`.${col}`);
            if (!td || !td.classList.contains('sa-cell-invalid')) continue;
            const inp = ENTRY_FIELD_INPUTS[field];
            if (inp && !inp.disabled && !inp.readOnly) {
                window.setTimeout(() => {
                    inp.focus();
                    try { inp.select(); } catch (_) { /* ignore */ }
                }, 0);
            }
            return;
        }
    };
    const entryHasContent = () => {
        if (String(entryItemCode?.value || '').trim()) return true;
        if (String(entryUom?.value || '').trim()) return true;
        if (String(entryStore?.value || '').trim()) return true;
        if (String(entryLotId?.value || '').trim()) return true;
        return !!Number(entryAdjustQty?.value || 0);
    };

    const isItemModalOpen = () => itemModal && !itemModal.classList.contains('hidden');
    const isWarehouseModalOpen = () => warehouseModal && !warehouseModal.classList.contains('hidden');
    const isPickerModalOpen = () => isItemModalOpen() || isWarehouseModalOpen();

    const buildFocusChain = () => {
        const chain = [];
        const pushInput = (inp) => {
            if (!inp || inp.disabled) return;
            if (inp.readOnly && inp !== entryStore) return;
            chain.push({ kind: 'input', el: inp });
        };
        const pushButton = (btn) => {
            if (btn && !btn.disabled && btn.offsetParent !== null) chain.push({ kind: 'button', el: btn });
        };
        pushInput(adjDate);
        pushInput(adjRemarks);
        ENTRY_INPUTS.forEach(pushInput);
        pushButton(btnAddLine);
        body.querySelectorAll('tr.sa-data-row[data-line]').forEach((tr) => {
            SA_INLINE_ORDER.forEach((key) => {
                const td = tr.querySelector(`.${key}`);
                if (td) chain.push({ kind: 'cell', td, tr, key });
            });
        });
        return chain;
    };

    const focusChainTarget = (target) => {
        if (!target) return;
        if (target.kind === 'input') {
            target.el.focus();
            try { target.el.select(); } catch (_) { /* ignore */ }
            return;
        }
        if (target.kind === 'button') {
            target.el.focus();
            return;
        }
        if (target.kind === 'cell') beginInlineEdit(target.td, target.tr, target.key);
    };

    const resolveChainIndex = (chain, activeEl) => {
        const active = activeEl || document.activeElement;
        if (!active) return -1;
        if (active.classList && active.classList.contains('sa-inline-input')) {
            const td = active.closest('td');
            const tr = active.closest('tr.sa-data-row');
            const key = inlineColKey(td);
            return chain.findIndex((t) => t.kind === 'cell' && t.tr === tr && t.key === key);
        }
        if (active === btnAddLine) {
            return chain.findIndex((t) => t.kind === 'button' && t.el === btnAddLine);
        }
        return chain.findIndex((t) => t.kind === 'input' && t.el === active);
    };

    const commitInlineEdit = (commit = true) => {
        if (typeof inlineEditFinish === 'function') {
            const fn = inlineEditFinish;
            inlineEditFinish = null;
            fn(commit);
        }
    };

    const moveFocus = async (dir, opts = {}) => {
        if (isPickerModalOpen()) return;
        const active = document.activeElement;
        const wasInline = !!(active && active.classList && active.classList.contains('sa-inline-input'));
        let anchorTr = null;
        let anchorKey = null;
        if (wasInline) {
            anchorTr = active.closest('tr.sa-data-row');
            anchorKey = inlineColKey(active.closest('td'));
        }

        if (dir < 0 && wasInline) {
            const chain = buildFocusChain();
            const cellIdx = chain.findIndex((t) => t.kind === 'cell' && t.tr === anchorTr && t.key === anchorKey);
            commitInlineEdit(false);
            const prevIdx = cellIdx > 0 ? cellIdx - 1 : chain.length - 1;
            focusChainTarget(chain[prevIdx]);
            return;
        }

        if (dir > 0 && active === entryBarcode && !opts.skipBarcodeLoad) {
            const bc = String(entryBarcode?.value || '').trim();
            if (bc) {
                const ok = await applyItemByBarcode(bc, 'entry');
                if (ok) {
                    if (entryStore) entryStore.focus();
                    else if (entryLotId) entryLotId.focus();
                    return;
                }
            }
        } else if (dir > 0 && active === entryItemCode && !opts.skipItemLoad) {
            const code = String(entryItemCode.value || '').trim();
            if (code) await validateEntryItemCode();
        } else if (dir > 0 && active === entryStore) {
            await validateEntryStore();
        } else if (dir > 0 && active === entryAdjustQty) {
            validateEntryAdjustQty();
        }

        let fromIdx = -1;
        if (wasInline && anchorTr && anchorKey) {
            const chainBefore = buildFocusChain();
            fromIdx = chainBefore.findIndex((t) => t.kind === 'cell' && t.tr === anchorTr && t.key === anchorKey);
        } else {
            fromIdx = resolveChainIndex(buildFocusChain(), active);
        }

        commitInlineEdit(true);

        const chain = buildFocusChain();
        if (!chain.length) return;
        let nextIdx;
        if (fromIdx < 0) {
            nextIdx = dir > 0 ? 0 : chain.length - 1;
        } else {
            nextIdx = fromIdx + dir;
            if (nextIdx < 0) nextIdx = chain.length - 1;
            if (nextIdx >= chain.length) nextIdx = 0;
        }
        focusChainTarget(chain[nextIdx]);
    };

    const isFormNavTarget = (el) => {
        if (!el) return false;
        if (el.classList && el.classList.contains('sa-inline-input')) return true;
        return HEADER_INPUTS.includes(el) || ENTRY_INPUTS.includes(el) || el === btnAddLine;
    };

    const normalizeItem = (r) => ({
        itemcode: r?.itemcode ?? r?.code ?? '',
        itemname: r?.itemname ?? r?.name ?? '',
        baseuom: r?.baseuom ?? r?.uom ?? 'NOS',
        barcode: String(r?.barcode ?? '').trim(),
        currentstock: Number(r?.currentstock ?? r?.stock ?? 0),
        costprice: Number(r?.costprice ?? r?.cost ?? 0),
        best_store: r?.best_store ?? r?.store ?? '',
    });

    const barcodeCmp = (s) => String(s || '').trim().toUpperCase();

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
    const sortItems = (rows) => {
        const arr = [...rows];
        arr.sort((a, b) => {
            const k = popupSortKey;
            const avRaw = a?.[k];
            const bvRaw = b?.[k];
            const isNum = (k === 'currentstock' || k === 'itemcode');
            const av = isNum ? Number(avRaw || 0) : String(avRaw || '').toUpperCase();
            const bv = isNum ? Number(bvRaw || 0) : String(bvRaw || '').toUpperCase();
            if (av < bv) return popupSortDir === 'asc' ? -1 : 1;
            if (av > bv) return popupSortDir === 'asc' ? 1 : -1;
            return 0;
        });
        return arr;
    };
    const renderPopupItems = () => {
        const rows = sortItems(popupItems);
        itemCount.textContent = `${rows.length} item(s)`;
        itemSortDir.textContent = popupSortDir === 'asc' ? '↑' : '↓';
        const esc = (s) => String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
        itemTableBody.innerHTML = rows.map((r, idx) => `
            <tr tabindex="0" data-code="${esc(r.itemcode || '')}" data-name="${esc(r.itemname || '')}" data-uom="${esc(r.baseuom || '')}" data-barcode="${esc(r.barcode || '')}" data-cost="${r.costprice || 0}">
                <td class="col-sl">${idx + 1}</td>
                <td class="col-code">${esc(r.itemcode || '')}</td>
                <td class="col-barcode">${esc(r.barcode || '')}</td>
                <td class="col-name">${esc(r.itemname || '')}</td>
                <td class="col-uom">${esc(r.baseuom || '')}</td>
                <td class="col-stock">${fmt(r.currentstock || 0)}</td>
            </tr>
        `).join('') || '<tr><td colspan="6" class="muted">No items found.</td></tr>';
    };

    const clearEntry = () => {
        if (entryBarcode) entryBarcode.value = '';
        entryItemCode.value = '';
        entryItemName.value = '';
        entryUom.value = '';
        entryStore.value = '';
        entryLotId.value = '';
        entryCurrentQty.value = '';
        entryAdjustQty.value = '';
        entryNewQty.value = '';
        currentItem = null;
        clearEntryValidation();
        syncEntryRowActive();
    };

    const updateNewQty = () => {
        const cur = Number(entryCurrentQty.value || 0);
        const adj = Number(entryAdjustQty.value || 0);
        entryNewQty.value = fmt(cur + adj);
    };

    const escCell = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    const lotDisplay = (data) => (data.lot_id != null && String(data.lot_id).trim() !== '' ? data.lot_id : '—');

    const inlineColKey = (td) => {
        if (!td || !td.classList) return null;
        return Object.keys(SA_INLINE_COLS).find((k) => td.classList.contains(k)) || null;
    };

    const markCellInvalid = (tr, colKey, bad, msg) => {
        const td = tr && tr.querySelector(`.${colKey}`);
        if (!td) return;
        td.classList.remove('sa-cell-checking');
        if (bad) {
            td.classList.add('sa-cell-invalid');
            td.title = msg || 'Invalid';
        } else {
            td.classList.remove('sa-cell-invalid');
            td.removeAttribute('title');
        }
    };

    const refreshRowDom = (tr) => {
        if (!tr) return;
        const lot = (tr.dataset.lotId && String(tr.dataset.lotId).trim()) ? tr.dataset.lotId : '—';
        const set = (cls, val) => {
            const el = tr.querySelector(cls);
            if (el) el.textContent = val;
        };
        set('.sa-col-barcode', tr.dataset.barcode || '');
        set('.sa-col-itemcode', tr.dataset.itemCode || '');
        set('.sa-col-itemname', tr.dataset.itemName || '');
        set('.sa-col-uom', tr.dataset.uom || '');
        set('.sa-col-store', tr.dataset.store || '');
        set('.sa-col-lot', lot);
        set('.sa-col-currentqty', fmt(tr.dataset.currentQty || 0));
        set('.sa-col-adjustqty', fmt(tr.dataset.adjustQty || 0));
        set('.sa-col-newqty', fmt(tr.dataset.newQty || 0));
    };

    const recalcDataRow = (tr) => {
        if (!tr) return;
        const cur = Number(tr.dataset.currentQty || 0);
        const adj = Number(tr.dataset.adjustQty || 0);
        tr.dataset.newQty = String(cur + adj);
        const factor = getUomFactor(tr.dataset.itemCode, tr.dataset.uom);
        tr.dataset.baseQty = String(factor != null ? adj * factor : adj);
        refreshRowDom(tr);
        validateNegativeStockRows();
    };

    const cacheUomFactors = (itemCode, uoms) => {
        const code = String(itemCode || '').trim();
        if (!code) return;
        const m = {};
        const costs = {};
        (uoms || []).forEach((u) => {
            const key = String(u.uom || '').trim().toUpperCase();
            if (!key) return;
            m[key] = Number(u.factor != null ? u.factor : 1) || 1;
            const c = Number(u.cost != null ? u.cost : (u.costprice != null ? u.costprice : 0));
            if (c > 0) costs[key] = c;
        });
        uomFactorCache[code] = m;
        uomCostCache[code] = costs;
    };

    const getUomFactor = (itemCode, uom) => {
        const code = String(itemCode || '').trim();
        const key = String(uom || '').trim().toUpperCase();
        const m = uomFactorCache[code] || {};
        return Object.prototype.hasOwnProperty.call(m, key) ? m[key] : null;
    };

    const getUomPackCost = (itemCode, uom) => {
        const code = String(itemCode || '').trim();
        const key = String(uom || '').trim().toUpperCase();
        const m = uomCostCache[code] || {};
        return Object.prototype.hasOwnProperty.call(m, key) ? m[key] : null;
    };

    const applyFieldErrorsToRow = (tr, fieldErrors) => {
        if (!tr) return;
        Object.keys(SA_FIELD_TO_COL).forEach((field) => {
            const col = SA_FIELD_TO_COL[field];
            const msg = fieldErrors && fieldErrors[field];
            markCellInvalid(tr, col, !!msg, msg || '');
        });
    };

    const validateRowAdjustQty = (tr) => {
        const adj = Number(tr.dataset.adjustQty || 0);
        markCellInvalid(tr, 'sa-col-adjustqty', !adj, adj ? '' : 'Adjust qty cannot be zero.');
    };

    const isWarehouseMasterCode = (storeCode) => {
        const u = String(storeCode || '').trim().toUpperCase();
        if (!u) return false;
        if (!popupWarehouses.length) return true;
        return popupWarehouses.some((w) => w.code === u);
    };

    const refreshRowStock = async (tr) => {
        if (queryMode) return;
        const code = String(tr.dataset.itemCode || '').trim();
        const store = String(tr.dataset.store || '').trim();
        if (!code) return;
        const td = tr.querySelector('.sa-col-store');
        if (td) td.classList.add('sa-cell-checking');
        try {
            const data = await fetchItemStock(code, store);
            const stores = Array.isArray(data.stores) ? data.stores : [];
            storeListCache[code] = stores.map((r) => String(r.store || r.itemlocation || '').trim().toUpperCase()).filter(Boolean);
            if (data.store) tr.dataset.store = data.store;
            tr.dataset.currentQty = String(data.current_qty || 0);
            recalcDataRow(tr);
            const storeU = String(tr.dataset.store || '').trim().toUpperCase();
            if (!storeU) {
                markCellInvalid(tr, 'sa-col-store', true, 'Warehouse is required.');
            } else if (popupWarehouses.length && !isWarehouseMasterCode(storeU)) {
                markCellInvalid(tr, 'sa-col-store', true, `Warehouse "${storeU}" is not in warehouse master.`);
            } else {
                markCellInvalid(tr, 'sa-col-store', false);
            }
            validateNegativeStockRows();
        } catch (_) {
            if (td) td.classList.remove('sa-cell-checking');
        }
    };

    const validateRowUom = (tr) => {
        const code = String(tr.dataset.itemCode || '').trim();
        const uom = String(tr.dataset.uom || '').trim();
        if (!code || !uom) {
            markCellInvalid(tr, 'sa-col-uom', false);
            return;
        }
        const check = () => {
            const m = uomFactorCache[code] || {};
            const ok = Object.prototype.hasOwnProperty.call(m, uom.toUpperCase());
            markCellInvalid(
                tr,
                'sa-col-uom',
                !ok,
                ok ? '' : (`UOM "${uom}" is not defined for item ${code}. Allowed: ${Object.keys(m).join(', ') || 'none'}`),
            );
            if (ok) {
                const pack = getUomPackCost(code, uom);
                if (pack != null && pack > 0) tr.dataset.cost = String(pack);
                recalcDataRow(tr);
            }
        };
        if (uomFactorCache[code]) {
            check();
            return;
        }
        const uTd = tr.querySelector('.sa-col-uom');
        if (uTd) uTd.classList.add('sa-cell-checking');
        fetch(`/purchase/stock-adjustment/api/item-uoms/${encodeURIComponent(code)}`)
            .then((r) => r.json())
            .then((d) => {
                if (d && d.success && d.uoms) cacheUomFactors(code, d.uoms);
                check();
            })
            .catch(() => { if (uTd) uTd.classList.remove('sa-cell-checking'); });
    };

    const validateRowItemCode = (tr) => {
        const code = String(tr.dataset.itemCode || '').trim();
        if (!code) {
            markCellInvalid(tr, 'sa-col-itemcode', true, 'Item code is required.');
            tr.dataset.itemName = '';
            refreshRowDom(tr);
            return;
        }
        const icTd = tr.querySelector('.sa-col-itemcode');
        if (icTd) icTd.classList.add('sa-cell-checking');
        fetch(`/purchase/stock-adjustment/api/items?search=${encodeURIComponent(code)}&limit=50`)
            .then((r) => r.json())
            .then((d) => {
                const list = Array.isArray(d.items) ? d.items : [];
                const it = list.find((i) => String(i.code) === String(code));
                if (!it) {
                    markCellInvalid(tr, 'sa-col-itemcode', true, `Item code "${code}" not found in item master.`);
                    return;
                }
                markCellInvalid(tr, 'sa-col-itemcode', false);
                tr.dataset.itemName = String(it.name || '').trim();
                tr.dataset.barcode = String(it.barcode || '').trim();
                if (!tr.dataset.uom) tr.dataset.uom = String(it.uom || 'NOS').trim() || 'NOS';
                tr.dataset.cost = String(it.cost || 0);
                refreshRowDom(tr);
                validateRowUom(tr);
                refreshRowStock(tr);
            })
            .catch(() => { if (icTd) icTd.classList.remove('sa-cell-checking'); });
    };

    const validateRowAll = (tr) => {
        if (!tr || queryMode) return;
        validateRowAdjustQty(tr);
        validateRowItemCode(tr);
    };

    const validateEntryAdjustQty = () => {
        const adj = Number(entryAdjustQty?.value || 0);
        markEntryFieldInvalid('adjust_qty', !adj, adj ? '' : 'Adjust qty cannot be zero.');
        return !!adj;
    };

    const validateEntryItemCode = () => {
        const code = String(entryItemCode?.value || '').trim();
        if (!code) {
            markEntryFieldInvalid('item_code', true, 'Item code is required.');
            entryItemName.value = '';
            syncEntryRowActive();
            return Promise.resolve(false);
        }
        const td = getEntryRow()?.querySelector('.sa-col-itemcode');
        if (td) td.classList.add('sa-cell-checking');
        return fetch(`/purchase/stock-adjustment/api/items?search=${encodeURIComponent(code)}&limit=50`)
            .then((r) => r.json())
            .then((d) => {
                const list = Array.isArray(d.items) ? d.items : [];
                const it = list.find((i) => String(i.code) === String(code));
                if (!it) {
                    markEntryFieldInvalid('item_code', true, `Item code "${code}" not found in item master.`);
                    syncEntryRowActive();
                    return false;
                }
                markEntryFieldInvalid('item_code', false);
                entryItemName.value = String(it.name || '').trim();
                if (entryBarcode) entryBarcode.value = String(it.barcode || '').trim();
                if (!entryUom.value) entryUom.value = String(it.uom || 'NOS').trim() || 'NOS';
                currentItem = normalizeItem({ code: it.code, name: it.name, uom: it.uom, cost: it.cost, barcode: it.barcode });
                syncEntryRowActive();
                return true;
            })
            .catch(() => {
                if (td) td.classList.remove('sa-cell-checking');
                return false;
            });
    };

    const validateEntryUom = () => {
        const code = String(entryItemCode?.value || '').trim();
        const uom = String(entryUom?.value || '').trim();
        if (!code || !uom) {
            markEntryFieldInvalid('uom', false);
            return Promise.resolve(true);
        }
        const check = () => {
            const m = uomFactorCache[code] || {};
            const ok = Object.prototype.hasOwnProperty.call(m, uom.toUpperCase());
            markEntryFieldInvalid(
                'uom',
                !ok,
                ok ? '' : (`UOM "${uom}" is not defined for item ${code}. Allowed: ${Object.keys(m).join(', ') || 'none'}`),
            );
            return ok;
        };
        if (uomFactorCache[code]) return Promise.resolve(check());
        const uTd = getEntryRow()?.querySelector('.sa-col-uom');
        if (uTd) uTd.classList.add('sa-cell-checking');
        return fetch(`/purchase/stock-adjustment/api/item-uoms/${encodeURIComponent(code)}`)
            .then((r) => r.json())
            .then((d) => {
                if (d && d.success && d.uoms) cacheUomFactors(code, d.uoms);
                return check();
            })
            .catch(() => {
                if (uTd) uTd.classList.remove('sa-cell-checking');
                return false;
            });
    };

    const ensureWarehousesForValidation = async () => {
        if (warehousesLoaded && popupWarehouses.length) return;
        try {
            await loadWarehouses();
        } catch (_) { /* ignore */ }
    };

    const saRequireEntryWarehouse = () => {
        if (!warehouseEnabled) return true;
        const store = String(entryStore?.value || '').trim();
        if (store) return true;
        alert('Please select warehouse (F1) before adding a line.');
        markEntryFieldInvalid('store', true, 'Warehouse is required.');
        if (entryStore) {
            entryStore.focus();
        } else if (btnStorePicker) {
            btnStorePicker.click();
        }
        return false;
    };

    const validateEntryStore = async () => {
        const code = String(entryItemCode?.value || '').trim();
        const store = String(entryStore?.value || '').trim();
        if (!code) {
            markEntryFieldInvalid('store', false);
            return true;
        }
        if (!store) {
            markEntryFieldInvalid('store', true, 'Warehouse is required.');
            return false;
        }
        await ensureWarehousesForValidation();
        const storeU = store.toUpperCase();
        if (popupWarehouses.length && !isWarehouseMasterCode(storeU)) {
            markEntryFieldInvalid('store', true, `Warehouse "${storeU}" is not in warehouse master.`);
            return false;
        }
        const sTd = getEntryRow()?.querySelector('.sa-col-store');
        if (sTd) sTd.classList.add('sa-cell-checking');
        try {
            const data = await fetchItemStock(code, storeU);
            const stores = Array.isArray(data.stores) ? data.stores : [];
            storeListCache[code] = stores
                .map((r) => String(r.store || r.itemlocation || '').trim().toUpperCase())
                .filter(Boolean);
            entryStore.value = storeU;
            entryCurrentQty.value = fmt(data.current_qty || 0);
            updateNewQty();
            markEntryFieldInvalid('store', false);
            return true;
        } catch (_) {
            if (sTd) sTd.classList.remove('sa-cell-checking');
            markEntryFieldInvalid('store', true, 'Could not load stock for this warehouse.');
            return false;
        }
    };

    const validateEntryAll = async () => {
        validateEntryAdjustQty();
        const icOk = await validateEntryItemCode();
        const uomOk = await validateEntryUom();
        const storeOk = await validateEntryStore();
        const adjOk = validateEntryAdjustQty();
        return icOk && uomOk && storeOk && adjOk && !entryHasInvalid();
    };

    const applyItemToDataRow = async (tr, rawItem) => {
        const item = normalizeItem(rawItem || {});
        tr.dataset.itemCode = String(item.itemcode || '');
        tr.dataset.itemName = String(item.itemname || '');
        tr.dataset.barcode = String(item.barcode || '');
        tr.dataset.uom = String(item.baseuom || 'NOS').trim() || 'NOS';
        tr.dataset.cost = String(item.costprice || 0);
        if (!tr.dataset.store && item.best_store) tr.dataset.store = item.best_store;
        refreshRowDom(tr);
        markCellInvalid(tr, 'sa-col-itemcode', false);
        validateRowUom(tr);
        await refreshRowStock(tr);
        validateRowAdjustQty(tr);
    };

    const renderRow = (idx, data) => `
        <td class="sa-col-sl">${idx}</td>
        <td class="sa-col-barcode">${escCell(data.barcode || '')}</td>
        <td class="sa-col-itemcode">${escCell(data.item_code || '')}</td>
        <td class="sa-col-itemname">${escCell(data.item_name || '')}</td>
        <td class="sa-col-uom">${escCell(data.uom || '')}</td>
        <td class="sa-col-store">${escCell(data.store || '')}</td>
        <td class="sa-col-lot">${escCell(lotDisplay(data))}</td>
        <td class="sa-col-currentqty num">${fmt(data.current_qty)}</td>
        <td class="sa-col-adjustqty num">${fmt(data.adjust_qty)}</td>
        <td class="sa-col-newqty num">${fmt(data.new_qty)}</td>
        <td class="sa-col-action"><div class="line-action"><button type="button" class="icon-btn btn-remove" title="Remove">×</button></div></td>
    `;

    const mountDataRow = (lineNo, ln) => {
        const row = document.createElement('tr');
        row.className = 'sa-data-row';
        row.setAttribute('data-line', String(lineNo));
        row.dataset.itemCode = String(ln.item_code || '');
        row.dataset.barcode = ln.barcode != null ? String(ln.barcode) : '';
        row.dataset.itemName = ln.item_name || '';
        row.dataset.uom = ln.uom || '';
        row.dataset.store = ln.store || '';
        row.dataset.currentQty = String(ln.current_qty || 0);
        row.dataset.adjustQty = String(ln.adjust_qty || 0);
        row.dataset.newQty = String(ln.new_qty || 0);
        row.dataset.baseQty = String(ln.base_qty != null ? ln.base_qty : ln.adjust_qty || 0);
        row.dataset.cost = String(ln.cost || 0);
        row.dataset.lotId = ln.lot_id != null ? String(ln.lot_id) : '';
        row.innerHTML = renderRow(lineNo, ln);
        if (ln.field_errors) applyFieldErrorsToRow(row, ln.field_errors);
        else if (!queryMode) validateRowAll(row);
        return row;
    };

    const reindex = () => {
        ensureEntryRow();
        const rows = Array.from(body.querySelectorAll('tr.sa-data-row[data-line]'));
        rows.forEach((r, i) => {
            r.dataset.line = String(i + 1);
            const sl = r.querySelector('.sa-col-sl');
            if (sl) sl.textContent = String(i + 1);
        });
        let empty = body.querySelector('.empty-row');
        const entry = getEntryRow();
        if (!rows.length) {
            if (!empty) {
                empty = document.createElement('tr');
                empty.className = 'empty-row';
                empty.innerHTML = '<td colspan="11" class="muted">No lines added.</td>';
                if (entry) body.insertBefore(empty, entry);
                else body.appendChild(empty);
            }
        } else if (empty) {
            empty.remove();
        }
    };

    const lineMergeKey = (ln) => [
        String(ln.item_code || ''),
        String(ln.store || '').trim().toUpperCase(),
        String(ln.uom || '').trim().toUpperCase(),
        String(ln.lot_id != null ? ln.lot_id : '').trim(),
    ].join('|');

    const appendImportedLines = (incoming) => {
        const linesIn = Array.isArray(incoming) ? incoming : [];
        if (!linesIn.length) return 0;
        const existing = Array.from(body.querySelectorAll('tr.sa-data-row[data-line]'));
        const mergeMap = new Map();
        existing.forEach((tr) => {
            mergeMap.set(lineMergeKey({
                item_code: tr.dataset.itemCode,
                store: tr.dataset.store,
                uom: tr.dataset.uom,
                lot_id: tr.dataset.lotId,
            }), tr);
        });
        let added = 0;
        linesIn.forEach((ln) => {
            const key = lineMergeKey(ln);
            const hit = mergeMap.get(key);
            if (hit) {
                const adj = Number(hit.dataset.adjustQty || 0) + Number(ln.adjust_qty || 0);
                const base = Number(hit.dataset.baseQty || 0) + Number(ln.base_qty || ln.adjust_qty || 0);
                hit.dataset.adjustQty = String(adj);
                hit.dataset.baseQty = String(base);
                recalcDataRow(hit);
                validateRowAll(hit);
                if (ln.field_errors) applyFieldErrorsToRow(hit, ln.field_errors);
                return;
            }
            const lineNo = body.querySelectorAll('tr.sa-data-row[data-line]').length + 1;
            const row = mountDataRow(lineNo, ln);
            insertLineBeforeEntry(row);
            mergeMap.set(key, row);
            added += 1;
        });
        reindex();
        validateNegativeStockRows();
        return added;
    };

    const importExcelFile = async (file) => {
        if (!file) return;
        const fd = new FormData();
        fd.append('excel_file', file);
        const res = await fetch(importExcelUrl, {
            method: 'POST',
            credentials: 'same-origin',
            body: fd,
            loadingMessage: 'Importing stock adjustment lines…',
        });
        let data = {};
        try { data = await res.json(); } catch (_) { data = {}; }
        if (!res.ok || !data.success) {
            const errLines = Array.isArray(data.errors) ? data.errors.slice(0, 8).join('\n') : '';
            let msg = data.error || `Import failed (${res.status})`;
            if (res.status === 524 || res.status === 504) {
                msg += '\n\nThe server took too long to process the file. Try fewer rows (max 1000) or split the file.';
            }
            throw new Error(msg + (errLines ? `\n\n${errLines}` : ''));
        }
        const added = appendImportedLines(data.lines || []);
        const errCount = Number(data.error_count || 0);
        const validCount = Number(data.valid_count != null ? data.valid_count : (data.imported || added));
        let msg = `Imported ${data.imported || added} line(s) (${validCount} valid).`;
        if (errCount) msg += ` ${errCount} row(s) have validation issues — fix red cells.`;
        if (Array.isArray(data.errors) && data.errors.length) {
            msg += `\n\n${data.errors.slice(0, 12).join('\n')}`;
            if (data.errors.length > 12) msg += `\n… and ${data.errors.length - 12} more.`;
        }
        alert(msg);
    };

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const pollImportPostJob = async (jobId) => {
        const url = `${importPostJobUrl}/${encodeURIComponent(jobId)}`;
        while (true) {
            const res = await fetch(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                throw new Error(data.error || `Import job status failed (${res.status})`);
            }
            const total = Number(data.total || 0);
            const processed = Number(data.processed || 0);
            const phase = String(data.phase || data.status || 'Processing');
            showSaveProgress(processed, total || processed || 1, phase);
            if (data.status === 'DONE') {
                return data;
            }
            if (data.status === 'FAILED') {
                let msg = data.error || 'Import/post job failed.';
                if (data.error_url) msg += `\n\nDownload error file:\n${data.error_url}`;
                throw new Error(msg);
            }
            await sleep(1500);
        }
    };

    const importAndPostLargeExcel = async (file) => {
        if (!file) return;
        if (!adjNo.value || !adjDate.value) {
            alert('Adjustment No and Date are required.');
            return;
        }
        if (!confirm('This will import and post the Excel file in the background. Continue?')) return;
        const fd = new FormData();
        fd.append('excel_file', file);
        fd.append('adj_no', String(adjNo.value || ''));
        fd.append('adj_date', String(adjDate.value || ''));
        fd.append('remarks', String(adjRemarks.value || ''));
        showSaveProgress(0, 1, 'Uploading file');
        const res = await fetch(importPostJobUrl, {
            method: 'POST',
            credentials: 'same-origin',
            body: fd,
        });
        const start = await res.json().catch(() => ({}));
        if (!res.ok || !start.success || !start.job_id) {
            throw new Error(start.error || `Could not start import job (${res.status})`);
        }
        const done = await pollImportPostJob(start.job_id);
        if (done.pdf_url) {
            window.open(done.pdf_url, '_blank', 'noopener,noreferrer');
        }
        finishSaveSuccess({
            adj_no: done.adj_no || adjNo.value,
            message: done.message || 'Large Excel import posted.',
            list_url: done.list_url || listUrl,
            pdf_url: done.pdf_url,
            gl_voucher_no: done.gl_voucher_no,
        });
    };

    const fetchItemStock = async (itemCode, store) => {
        const q = new URLSearchParams({ item_code: String(itemCode || ''), store: String(store || '') }).toString();
        const res = await fetch(`/purchase/stock-adjustment/api/item-stock?${q}`);
        const data = await readJson(res);
        if (!data.success) throw new Error(data.error || 'Stock lookup failed');
        return data;
    };

    const applyItem = async (rawItem) => {
        const item = normalizeItem(rawItem || {});
        currentItem = item;
        if (entryBarcode) entryBarcode.value = item.barcode || '';
        entryItemCode.value = item.itemcode || '';
        entryItemName.value = item.itemname || '';
        entryUom.value = item.baseuom || 'NOS';
        if (!entryStore.value && item.best_store) entryStore.value = item.best_store;
        const stock = await fetchItemStock(entryItemCode.value, entryStore.value);
        if (stock.store && !entryStore.value) entryStore.value = stock.store;
        entryCurrentQty.value = fmt(stock.current_qty || 0);
        updateNewQty();
        markEntryFieldInvalid('item_code', false);
        syncEntryRowActive();
        validateEntryUom();
        validateEntryStore();
    };

    const searchItems = async (term = '') => {
        const q = new URLSearchParams({ search: term, limit: '300' }).toString();
        const res = await fetch(`/purchase/stock-adjustment/api/items?${q}`);
        const data = await readJson(res);
        popupItems = Array.isArray(data.items) ? data.items.map(normalizeItem) : [];
        renderPopupItems();
    };

    const openItemModal = (pickRow = null) => {
        inlinePickRow = pickRow;
        itemModal?.classList.remove('hidden');
        if (itemSearch) {
            itemSearch.value = '';
            itemSearch.focus();
        }
        searchItems('').catch(() => {});
    };

    const selectItemFromPopup = (row) => {
        if (!row || !row.dataset.code) return;
        const pick = {
            itemcode: row.dataset.code,
            itemname: row.dataset.name || '',
            baseuom: row.dataset.uom || 'NOS',
            barcode: row.dataset.barcode || '',
            costprice: Number(row.dataset.cost || 0),
        };
        if (inlinePickRow) {
            applyItemToDataRow(inlinePickRow, pick).then(() => {
                inlinePickRow = null;
                itemModal.classList.add('hidden');
            }).catch((err) => alert(err.message || 'Failed to set item'));
            return;
        }
        applyItem(pick).then(() => {
            itemModal.classList.add('hidden');
            if (entryStore) entryStore.focus();
            else if (entryLotId) entryLotId.focus();
        }).catch((err) => alert(err.message || 'Failed to set item'));
    };

    const distinctItemCodes = (list) => {
        const seen = new Set();
        (list || []).forEach((it) => {
            const c = String(it.itemcode ?? it.code ?? '').trim();
            if (c) seen.add(c);
        });
        return seen;
    };

    const applyItemByBarcode = async (bcRaw, target = 'entry') => {
        const bc = String(bcRaw || '').trim();
        if (!bc) return false;
        const bcCmp = barcodeCmp(bc);
        const finishEntry = (it) => {
            if (!it) return false;
            return applyItem(it).then(() => true).catch(() => false);
        };
        const finishRow = (tr, it) => {
            if (!it || !tr) return false;
            return applyItemToDataRow(tr, it).then(() => true).catch(() => false);
        };
        const cached = popupItems.filter((i) => barcodeCmp(i.barcode) === bcCmp);
        if (cached.length >= 1 && distinctItemCodes(cached).size === 1) {
            const it = cached[0];
            if (target === 'entry') return finishEntry(it);
            return finishRow(target, it);
        }
        if (cached.length > 1 && distinctItemCodes(cached).size > 1) {
            alert(`Multiple items match barcode "${bc}". Enter item code or use F1 item list.`);
            return false;
        }
        try {
            const res = await fetch(`/purchase/stock-adjustment/api/items?search=${encodeURIComponent(bc)}&limit=50`);
            const data = await readJson(res);
            const list = Array.isArray(data.items) ? data.items.map(normalizeItem) : [];
            const match = list.filter((i) => barcodeCmp(i.barcode) === bcCmp);
            if (!match.length) {
                alert(`Barcode "${bc}" was not found in item master.`);
                return false;
            }
            if (match.length > 1 && distinctItemCodes(match).size > 1) {
                alert(`Multiple items match barcode "${bc}". Enter item code or use F1 item list.`);
                return false;
            }
            const it = match[0];
            if (target === 'entry') return finishEntry(it);
            return finishRow(target, it);
        } catch (_) {
            alert('Could not look up barcode. Check your connection and try again.');
            return false;
        }
    };

    const normalizeWarehouseRow = (r) => ({
        code: String(r?.code || r?.warehouse_code || '').trim().toUpperCase(),
        name: String(r?.name || r?.description || '').trim(),
        allow_negative_stock: r?.allow_negative_stock === true
            || String(r?.allow_negative_stock || '').trim().toUpperCase() === 'Y',
    });

    const warehouseAllowsNegative = (storeCode) => {
        const code = String(storeCode || '').trim().toUpperCase();
        if (!code) return false;
        const wh = popupWarehouses.find((w) => w.code === code);
        return !!(wh && wh.allow_negative_stock);
    };

    const negativeStockGroupKey = (itemCode, store) => [
        String(itemCode || '').trim(),
        String(store || '').trim().toUpperCase(),
    ].join('|');

    const clearNegativeStockHighlights = () => {
        body.querySelectorAll('tr.sa-data-row.sa-row-negative-stock').forEach((tr) => {
            tr.classList.remove('sa-row-negative-stock');
            tr.removeAttribute('title');
            markCellInvalid(tr, 'sa-col-adjustqty', false);
        });
    };

    const applyNegativeStockHighlights = (issues) => {
        clearNegativeStockHighlights();
        const list = Array.isArray(issues) ? issues : [];
        if (!list.length) return;
        const rows = Array.from(body.querySelectorAll('tr.sa-data-row[data-line]'));
        list.forEach((issue) => {
            const lineNo = Number(issue?.line_no || 0);
            const tr = rows.find((r) => Number(r.dataset.line || 0) === lineNo)
                || rows[lineNo - 1];
            if (!tr) return;
            tr.classList.add('sa-row-negative-stock');
            const cur = Number(issue?.current_qty ?? tr.dataset.currentQty ?? 0);
            const delta = Number(issue?.delta ?? tr.dataset.baseQty ?? tr.dataset.adjustQty ?? 0);
            const res = Number(issue?.resulting_qty ?? (cur + delta));
            const store = String(issue?.store || tr.dataset.store || '').trim();
            const msg = store
                ? `Warehouse ${store}: on-hand ${fmt(cur)}, net change ${fmt(delta)}, would become ${fmt(res)}.`
                : `Would reduce warehouse stock below zero (on-hand ${fmt(cur)}, change ${fmt(delta)}).`;
            tr.title = msg;
            markCellInvalid(tr, 'sa-col-adjustqty', true, msg);
        });
        const first = body.querySelector('tr.sa-data-row.sa-row-negative-stock');
        if (first) {
            first.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    };

    const validateNegativeStockRows = () => {
        if (queryMode || !warehouseEnabled) {
            clearNegativeStockHighlights();
            return false;
        }
        const groups = new Map();
        body.querySelectorAll('tr.sa-data-row[data-line]').forEach((tr) => {
            const itemCode = String(tr.dataset.itemCode || '').trim();
            const store = String(tr.dataset.store || '').trim().toUpperCase();
            if (!itemCode || !store) return;
            const key = negativeStockGroupKey(itemCode, store);
            if (!groups.has(key)) {
                groups.set(key, { itemCode, store, rows: [], baseSum: 0, currentQty: 0 });
            }
            const g = groups.get(key);
            g.rows.push(tr);
            g.baseSum += Number(tr.dataset.baseQty || tr.dataset.adjustQty || 0);
            g.currentQty = Math.max(g.currentQty, Number(tr.dataset.currentQty || 0));
        });
        const issues = [];
        groups.forEach((g) => {
            if (warehouseAllowsNegative(g.store)) return;
            const resulting = g.currentQty + g.baseSum;
            if (resulting >= -1e-6) return;
            g.rows.forEach((tr) => {
                issues.push({
                    line_no: Number(tr.dataset.line || 0),
                    item_code: g.itemCode,
                    store: g.store,
                    current_qty: g.currentQty,
                    delta: g.baseSum,
                    resulting_qty: resulting,
                });
            });
        });
        applyNegativeStockHighlights(issues);
        return issues.length > 0;
    };

    const renderPopupWarehouses = () => {
        if (!warehouseTableBody) return;
        const q = String(warehouseSearch?.value || '').trim().toLowerCase();
        const itemCode = inlinePickStoreRow
            ? String(inlinePickStoreRow.dataset.itemCode || '').trim()
            : String(entryItemCode?.value || '').trim();
        const allowed = itemCode ? (storeListCache[itemCode] || []) : [];
        let rows = popupWarehouses.slice();
        if (allowed.length) {
            const allowedSet = new Set(allowed.map((s) => String(s).trim().toUpperCase()));
            const preferred = rows.filter((w) => allowedSet.has(w.code));
            const rest = rows.filter((w) => !allowedSet.has(w.code));
            rows = preferred.length ? preferred.concat(rest) : rows;
        }
        const filtered = rows.filter((w) => {
            if (!q) return true;
            return w.code.toLowerCase().includes(q) || w.name.toLowerCase().includes(q);
        });
        const esc = (s) => String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
        warehouseTableBody.innerHTML = filtered.length
            ? filtered.map((w) => `
                <tr data-code="${esc(w.code)}" data-name="${esc(w.name)}">
                    <td>${esc(w.code)}</td>
                    <td>${esc(w.name)}</td>
                </tr>
            `).join('')
            : '<tr><td colspan="2" class="muted">No warehouses found.</td></tr>';
    };

    const loadWarehouses = async () => {
        if (warehousesLoaded && popupWarehouses.length) {
            renderPopupWarehouses();
            return;
        }
        if (warehouseTableBody) warehouseTableBody.innerHTML = '<tr><td colspan="2" class="muted">Loading…</td></tr>';
        const res = await fetch(warehousesApiUrl);
        const data = await readJson(res);
        popupWarehouses = Array.isArray(data.warehouses)
            ? data.warehouses.map(normalizeWarehouseRow).filter((w) => w.code)
            : [];
        warehousesLoaded = true;
        renderPopupWarehouses();
    };

    const openWarehouseModal = async () => {
        const itemCode = inlinePickStoreRow
            ? String(inlinePickStoreRow.dataset.itemCode || '').trim()
            : String(entryItemCode?.value || '').trim();
        if (itemCode && !storeListCache[itemCode]) {
            try {
                const data = await fetchItemStock(itemCode, entryStore?.value || '');
                const stores = Array.isArray(data.stores) ? data.stores : [];
                storeListCache[itemCode] = stores
                    .map((r) => String(r.store || r.itemlocation || '').trim().toUpperCase())
                    .filter(Boolean);
            } catch (_) { /* ignore */ }
        }
        warehouseModal?.classList.remove('hidden');
        if (warehouseSearch) {
            warehouseSearch.value = '';
            warehouseSearch.focus();
        }
        await loadWarehouses();
    };

    const closeWarehouseModal = () => {
        warehouseModal?.classList.add('hidden');
        inlinePickStoreRow = null;
    };

    const applyWarehouseToEntry = async (code) => {
        entryStore.value = String(code || '').trim().toUpperCase();
        markEntryFieldInvalid('store', false);
        await validateEntryStore();
    };

    const applyWarehouseToDataRow = async (tr, code) => {
        if (!tr) return;
        tr.dataset.store = String(code || '').trim().toUpperCase();
        refreshRowDom(tr);
        markCellInvalid(tr, 'sa-col-store', false);
        await refreshRowStock(tr);
    };

    const selectWarehouseRow = (row) => {
        if (!row || !row.dataset.code) return;
        const code = row.dataset.code;
        if (inlinePickStoreRow) {
            applyWarehouseToDataRow(inlinePickStoreRow, code).then(() => {
                closeWarehouseModal();
            }).catch((err) => alert(err.message || 'Failed to set warehouse'));
            return;
        }
        applyWarehouseToEntry(code).then(() => {
            closeWarehouseModal();
            entryLotId?.focus();
        }).catch((err) => alert(err.message || 'Failed to set warehouse'));
    };

    const gatherLines = () => Array.from(body.querySelectorAll('tr.sa-data-row[data-line]')).map((r) => {
        const adjustQty = Number(r.dataset.adjustQty || 0);
        let baseQty = Number(r.dataset.baseQty || 0);
        const factor = getUomFactor(r.dataset.itemCode, r.dataset.uom);
        const resolvedFactor = factor != null ? (Number(factor) || 1) : (
            Math.abs(adjustQty) > 1e-12 ? Math.abs(baseQty) / Math.abs(adjustQty) : 1
        );
        if (!(Math.abs(baseQty) > 1e-12) && Math.abs(adjustQty) > 1e-12) {
            baseQty = adjustQty * resolvedFactor;
        }
        return {
            item_code: Number(r.dataset.itemCode || 0),
            item_name: r.dataset.itemName || '',
            uom: r.dataset.uom || '',
            store: r.dataset.store || '',
            current_qty: Number(r.dataset.currentQty || 0),
            adjust_qty: adjustQty,
            new_qty: Number(r.dataset.newQty || 0),
            base_qty: baseQty,
            conversionfactor: resolvedFactor,
            conversion_factor: resolvedFactor,
            factor: resolvedFactor,
            cost: Number(r.dataset.cost || 0),
            lot_id: (r.dataset.lotId && String(r.dataset.lotId).trim()) ? r.dataset.lotId : undefined,
        };
    });

    const addLine = async () => {
        if (queryMode) return;
        if (!saRequireEntryWarehouse()) return;
        if (addLineInFlight) return;
        addLineInFlight = true;
        try {
            const valid = await validateEntryAll();
            if (!valid || entryHasInvalid()) {
                alert('Fix highlighted (red) fields in the entry row before adding the line.');
                focusFirstEntryInvalid();
                return;
            }
        const itemCode = Number(entryItemCode.value || 0);
        const uom = (entryUom.value || '').trim() || 'NOS';
        const store = (entryStore.value || '').trim();
        const currentQty = Number(entryCurrentQty.value || 0);
        const adjustQty = Number(entryAdjustQty.value || 0);
        const newQty = Number(entryNewQty.value || 0);
        const stock = await fetchItemStock(itemCode, store);
        const cost = Number((currentItem && currentItem.costprice) || 0);
        // Ensure UOM factors are cached before computing base qty.
        if (!uomFactorCache[String(itemCode)]) {
            try {
                const ur = await fetch(`/purchase/stock-adjustment/api/item-uoms/${encodeURIComponent(itemCode)}`);
                const ud = await ur.json();
                if (ud && ud.success && ud.uoms) cacheUomFactors(itemCode, ud.uoms);
            } catch (e) { /* ignore */ }
        }
        const factor = getUomFactor(itemCode, uom);
        const resolvedFactor = factor != null ? (Number(factor) || 1) : 1;
        const baseQty = adjustQty * resolvedFactor;
        const lotRaw = (entryLotId && entryLotId.value || '').trim();

        const ln = {
            item_code: itemCode,
            item_name: entryItemName.value || '',
            barcode: (entryBarcode && entryBarcode.value || '').trim(),
            uom,
            store: stock.store || store,
            current_qty: currentQty,
            adjust_qty: adjustQty,
            new_qty: newQty,
            base_qty: baseQty,
            conversionfactor: resolvedFactor,
            cost,
            lot_id: lotRaw || undefined,
        };
        const row = mountDataRow(body.querySelectorAll('tr.sa-data-row[data-line]').length + 1, ln);
        insertLineBeforeEntry(row);
        reindex();
        clearEntry();
        if (entryBarcode) entryBarcode.focus();
        else entryItemCode.focus();
        } finally {
            addLineInFlight = false;
        }
    };

    const beginInlineEdit = (td, tr, key) => {
        if (queryMode) return;
        if (!td || td._editing) return;
        const cfg = SA_INLINE_COLS[key];
        if (!cfg) return;
        let cur = cfg.type === 'number'
            ? String(Number(tr.dataset[cfg.ds] || 0) || 0)
            : String(tr.dataset[cfg.ds] || '');
        if (key === 'sa-col-lot' && (cur === '—' || !cur)) cur = '';
        const input = document.createElement('input');
        input.className = 'sa-inline-input';
        input.type = cfg.type === 'number' ? 'number' : 'text';
        if (cfg.type === 'number') input.step = 'any';
        input.value = cur;
        td._editing = true;
        td.textContent = '';
        td.appendChild(input);
        input.focus();
        try { input.select(); } catch (_) { /* ignore */ }
        let done = false;
        inlineEditFinish = null;
        const finish = (commit) => {
            if (done) return;
            done = true;
            td._editing = false;
            inlineEditFinish = null;
            if (commit) {
                if (cfg.type === 'number') {
                    let n = parseFloat(input.value);
                    if (Number.isNaN(n)) n = 0;
                    tr.dataset[cfg.ds] = String(n);
                } else {
                    let tv = String(input.value || '').trim();
                    if (key === 'sa-col-uom' || key === 'sa-col-store') tv = tv.toUpperCase();
                    tr.dataset[cfg.ds] = tv;
                }
            }
            refreshRowDom(tr);
            recalcDataRow(tr);
            if (commit) {
                if (key === 'sa-col-barcode') {
                    const bc = String(tr.dataset.barcode || '').trim();
                    if (bc) applyItemByBarcode(bc, tr);
                } else if (key === 'sa-col-itemcode') validateRowItemCode(tr);
                else if (key === 'sa-col-uom') validateRowUom(tr);
                else if (key === 'sa-col-store') refreshRowStock(tr);
                else if (key === 'sa-col-adjustqty') validateRowAdjustQty(tr);
            }
        };
        inlineEditFinish = finish;
        input.addEventListener('blur', () => finish(true));
        input.addEventListener('keydown', (e) => {
            if (e.key === 'F1' || e.keyCode === 112) {
                if (key === 'sa-col-barcode' || key === 'sa-col-itemcode') {
                    e.preventDefault();
                    e.stopPropagation();
                    finish(false);
                    openItemModal(tr);
                    return;
                }
                return;
            }
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                e.stopPropagation();
                finish(true);
                moveFocus(1, { skipItemLoad: true }).catch(() => {});
            } else if (e.key === 'Tab') {
                e.preventDefault();
                e.stopPropagation();
                finish(true);
                moveFocus(e.shiftKey ? -1 : 1, { skipItemLoad: true }).catch(() => {});
            } else if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                moveFocus(-1).catch(() => {});
            }
        });
    };

    const SAVE_BATCH_SIZE = 75;

    const formatFetchError = (e, res) => {
        if (e && e.message && e.message !== 'Failed to fetch') return e.message;
        if (res && (res.status === 524 || res.status === 504 || res.status === 502)) {
            return 'Server timeout while saving. Wait a minute, check Stock Adjustment List, then retry if needed.';
        }
        return 'Network error or server timeout. Wait, check Stock Adjustment List, then retry if the save did not complete.';
    };

    const showSaveProgress = (current, total, phase) => {
        const cur = Number(current) || 0;
        const tot = Number(total) || 0;
        if (typeof window.updateLoadingOverlayProgress === 'function') {
            window.updateLoadingOverlayProgress(cur, tot, `${phase || 'Saving'} stock adjustment…`, phase || 'Saving');
        } else if (typeof window.showLoadingOverlay === 'function') {
            window.showLoadingOverlay(`${phase || 'Saving'} ${cur} of ${tot} items…`);
        }
    };

    const hideSaveProgress = () => {
        if (typeof window.hideLoadingOverlay === 'function') window.hideLoadingOverlay();
    };

    const finishSaveSuccess = (data) => {
        const adjNo = data && data.adj_no != null ? String(data.adj_no) : '';
        const msg = (data && data.message)
            ? String(data.message)
            : (data && data.needs_approval
                ? (adjNo ? `Adjustment #${adjNo} submitted for approval.` : 'Submitted for approval.')
                : (adjNo ? `Adjustment #${adjNo} posted.` : 'Stock adjustment posted.'));
        try {
            sessionStorage.setItem('stk_adj_save_flash', msg);
        } catch (_) { /* ignore */ }
        window.location.href = (data && data.list_url) || listUrl;
    };

    const postSaveBatch = async (body) => {
        const payload = { ...body };
        if (typeof window.__GLOBAL_SAVE_NONCE === 'string' && window.__GLOBAL_SAVE_NONCE) {
            payload.save_nonce = window.__GLOBAL_SAVE_NONCE;
        }
        let res;
        try {
            res = await fetch('/purchase/stock-adjustment/api/save-batch', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify(payload),
            });
        } catch (e) {
            throw new Error(formatFetchError(e, null));
        }
        return parseSaveResponse(res);
    };

    const saveInBatches = async (payload) => {
        const lines = payload.lines || [];
        const total = lines.length;
        const batchCount = Math.max(1, Math.ceil(total / SAVE_BATCH_SIZE));
        let saveToken = '';
        let lastData = null;
        showSaveProgress(0, total, 'Uploading lines');
        for (let i = 0; i < batchCount; i += 1) {
            const chunk = lines.slice(i * SAVE_BATCH_SIZE, (i + 1) * SAVE_BATCH_SIZE);
            const isFinal = i === batchCount - 1;
            const uploaded = Math.min((i + 1) * SAVE_BATCH_SIZE, total);
            showSaveProgress(
                uploaded,
                total,
                isFinal ? 'Posting inventory & GL' : 'Uploading lines',
            );
            const data = await postSaveBatch({
                adj_no: payload.adj_no,
                adj_date: payload.adj_date,
                remarks: payload.remarks,
                opening_stock: payload.opening_stock,
                lines: chunk,
                batch_index: i,
                batch_count: batchCount,
                is_final_batch: isFinal,
                lines_total: total,
                save_token: saveToken || undefined,
            });
            if (typeof data.save_nonce === 'string' && data.save_nonce) {
                window.__GLOBAL_SAVE_NONCE = data.save_nonce;
            }
            if (data.save_token) saveToken = data.save_token;
            if (!data.success) throw new Error(data.error || 'Save failed');
            if (data.staged) {
                const saved = Number(data.lines_saved || uploaded);
                showSaveProgress(saved, total, 'Uploading lines');
                continue;
            }
            lastData = data;
            showSaveProgress(total, total, 'Complete');
            break;
        }
        if (!lastData) throw new Error('Save did not complete.');
        return lastData;
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
            let msg = data.error || `Save failed (${res.status})`;
            if (res.status === 524 || res.status === 504) {
                msg += '\n\nThe server took too long to save. Try saving in smaller batches (e.g. split into 2–3 adjustments).';
            }
            const err = new Error(msg);
            if (Array.isArray(data.negative_stock_lines) && data.negative_stock_lines.length) {
                err.negativeStockLines = data.negative_stock_lines;
            }
            throw err;
        }
        return data;
    };

    const save = async () => {
        // Save button only exists on New form (not View). Never block New saves on canEdit.
        if (queryMode) return;
        if (saveInFlight || saveCompleted) return;
        if (entryHasContent()) {
            const entryOk = await validateEntryAll();
            if (!entryOk || entryHasInvalid()) {
                return alert('Complete or clear the entry row (fix red fields) before saving.');
            }
        }
        if (body.querySelector('tr.sa-data-row .sa-cell-invalid') || entryHasInvalid()) {
            return alert('Fix highlighted (red) cells before saving.');
        }
        if (validateNegativeStockRows()) {
            return alert(
                'One or more lines would reduce warehouse stock below zero. '
                + 'Fix the highlighted (red) rows or choose a warehouse that allows negative stock.',
            );
        }
        const lines = gatherLines();
        if (!lines.length) return alert('No lines to save.');
        const adjNoVal = String(adjNo.value || '').trim();
        if (!adjNoVal || !adjDate.value) {
            return alert('Adjustment No and Date are required.');
        }
        const payload = {
            adj_no: adjNoVal,
            adj_date: adjDate.value,
            remarks: adjRemarks.value || '',
            opening_stock: !!window.__STK_ADJ_OPENING_MODE__,
            lines,
        };
        saveInFlight = true;
        const prevLabel = btnSave ? btnSave.textContent : 'Save';
        if (btnSave) {
            btnSave.disabled = true;
            btnSave.textContent = 'Saving…';
        }
        try {
            let data;
            if (lines.length > SAVE_BATCH_SIZE) {
                data = await saveInBatches(payload);
            } else {
                showSaveProgress(0, lines.length, 'Saving');
                if (typeof window.__GLOBAL_SAVE_NONCE === 'string' && window.__GLOBAL_SAVE_NONCE) {
                    payload.save_nonce = window.__GLOBAL_SAVE_NONCE;
                }
                let res;
                try {
                    res = await fetch('/purchase/stock-adjustment/api/save', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                        body: JSON.stringify(payload),
                    });
                } catch (e) {
                    throw new Error(formatFetchError(e, null));
                }
                data = await parseSaveResponse(res);
                showSaveProgress(lines.length, lines.length, 'Complete');
            }
            saveCompleted = true;
            window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data }));
            finishSaveSuccess(data);
        } catch (e) {
            if (e && Array.isArray(e.negativeStockLines) && e.negativeStockLines.length) {
                applyNegativeStockHighlights(e.negativeStockLines);
            }
            alert(e.message || 'Save failed');
            window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: { error: e.message } }));
        } finally {
            hideSaveProgress();
            saveInFlight = false;
            if (!saveCompleted && btnSave) {
                btnSave.disabled = false;
                btnSave.textContent = prevLabel;
            }
        }
    };

    btnAddLine?.addEventListener('click', () => {
        if (suppressAddLineClick) {
            suppressAddLineClick = false;
            return;
        }
        addLine().catch((e) => alert(e.message || 'Failed to add line'));
    });
    btnSave?.addEventListener('click', () => { save().catch((e) => alert(e.message || 'Save failed')); });
    btnImportExcel?.addEventListener('click', () => stkAdjExcelFile?.click());
    btnImportPostJob?.addEventListener('click', () => stkAdjLargeExcelFile?.click());
    stkAdjExcelFile?.addEventListener('change', () => {
        const file = stkAdjExcelFile.files && stkAdjExcelFile.files[0];
        stkAdjExcelFile.value = '';
        if (!file) return;
        importExcelFile(file).catch((e) => alert(e.message || 'Import failed'));
    });
    stkAdjLargeExcelFile?.addEventListener('change', () => {
        const file = stkAdjLargeExcelFile.files && stkAdjLargeExcelFile.files[0];
        stkAdjLargeExcelFile.value = '';
        if (!file) return;
        importAndPostLargeExcel(file)
            .catch((e) => alert(e.message || 'Large import failed'))
            .finally(() => hideSaveProgress());
    });
    entryAdjustQty?.addEventListener('input', () => {
        updateNewQty();
        validateEntryAdjustQty();
    });
    entryItemCode?.addEventListener('input', syncEntryRowActive);
    entryBarcode?.addEventListener('keydown', (e) => {
        if (e.key === 'F1' || e.keyCode === 112) {
            e.preventDefault();
            openItemModal(null);
            return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            e.stopPropagation();
            const bc = String(entryBarcode.value || '').trim();
            if (bc) {
                applyItemByBarcode(bc, 'entry').then((ok) => {
                    if (ok && entryStore) entryStore.focus();
                    else if (ok && entryLotId) entryLotId.focus();
                    else moveFocus(1, { skipBarcodeLoad: true }).catch(() => {});
                });
            } else {
                moveFocus(1, { skipBarcodeLoad: true }).catch(() => {});
            }
        }
    });
    entryBarcode?.addEventListener('blur', () => {
        const bc = String(entryBarcode?.value || '').trim();
        const code = String(entryItemCode?.value || '').trim();
        if (bc && !code) applyItemByBarcode(bc, 'entry');
    });
    entryItemCode?.addEventListener('keydown', (e) => {
        if (e.key === 'F1' || e.keyCode === 112) {
            e.preventDefault();
            openItemModal(null);
        }
    });
    entryStore?.addEventListener('keydown', (e) => {
        if (e.key === 'F1') {
            e.preventDefault();
            inlinePickStoreRow = null;
            openWarehouseModal().catch((err) => alert(err.message || 'Failed to open warehouse list'));
            return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            moveFocus(1).catch(() => {});
        } else if (e.key === 'Escape') {
            e.preventDefault();
            moveFocus(-1).catch(() => {});
        }
    });
    entryItemCode?.addEventListener('blur', () => {
        const code = String(entryItemCode.value || '').trim();
        if (!code) {
            markEntryFieldInvalid('item_code', false);
            syncEntryRowActive();
            return;
        }
        if (String(currentItem?.itemcode || '') === code) {
            markEntryFieldInvalid('item_code', false);
            return;
        }
        validateEntryItemCode();
    });
    document.addEventListener('keydown', (e) => {
        if (isWarehouseModalOpen()) {
            if (e.key === 'Escape') {
                e.preventDefault();
                closeWarehouseModal();
                moveFocus(-1).catch(() => {});
            }
            return;
        }
        if (isItemModalOpen()) {
            if (e.key === 'Escape') {
                e.preventDefault();
                inlinePickRow = null;
                itemModal.classList.add('hidden');
                moveFocus(-1).catch(() => {});
            }
            return;
        }
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            addLine().catch((err) => alert(err.message || 'Failed to add line'));
            return;
        }
        if (!isFormNavTarget(e.target)) return;
        if (e.key === 'Enter' && !e.shiftKey) {
            if (e.target.classList && e.target.classList.contains('sa-inline-input')) return;
            if (e.target === btnAddLine) {
                e.preventDefault();
                e.stopPropagation();
                suppressAddLineClick = true;
                addLine().catch((err) => alert(err.message || 'Failed to add line'));
                return;
            }
            e.preventDefault();
            moveFocus(1).catch(() => {});
        } else if (e.key === 'Escape') {
            if (e.target.classList && e.target.classList.contains('sa-inline-input')) return;
            e.preventDefault();
            moveFocus(-1).catch(() => {});
        }
    });

    btnItemPicker?.addEventListener('click', () => {
        openItemModal(null);
    });
    btnStorePicker?.addEventListener('click', () => {
        inlinePickStoreRow = null;
        openWarehouseModal().catch((e) => alert(e.message || 'Failed to open warehouse list'));
    });
    warehouseModal?.addEventListener('click', (e) => {
        if (e.target.dataset.close === 'warehouseModal' || e.target.classList.contains('modal-close') || e.target.classList.contains('modal__close')) {
            closeWarehouseModal();
        }
    });
    warehouseSearch?.addEventListener('input', () => renderPopupWarehouses());
    warehouseTableBody?.addEventListener('click', (e) => {
        const row = e.target.closest('tr[data-code]');
        if (!row) return;
        selectWarehouseRow(row);
    });
    itemModal?.addEventListener('click', (e) => {
        if (e.target.dataset.close === 'itemModal' || e.target.classList.contains('modal-close') || e.target.classList.contains('modal__close')) {
            inlinePickRow = null;
            itemModal.classList.add('hidden');
        }
    });
    itemSearch?.addEventListener('input', () => searchItems(itemSearch.value).catch(() => {}));
    itemSearch?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const firstRow = itemTableBody?.querySelector('tr[data-code]');
            if (firstRow) firstRow.focus();
        }
    });
    itemSortBy?.addEventListener('change', () => {
        popupSortKey = itemSortBy.value || 'itemcode';
        renderPopupItems();
    });
    itemSortDir?.addEventListener('click', () => {
        popupSortDir = popupSortDir === 'asc' ? 'desc' : 'asc';
        renderPopupItems();
    });
    itemTable?.querySelector('thead')?.addEventListener('click', (e) => {
        const btn = e.target.closest('.sort-th[data-sort]');
        if (!btn) return;
        const key = btn.dataset.sort || 'itemcode';
        if (popupSortKey === key) {
            popupSortDir = popupSortDir === 'asc' ? 'desc' : 'asc';
        } else {
            popupSortKey = key;
            popupSortDir = 'asc';
            if (itemSortBy) itemSortBy.value = key;
        }
        renderPopupItems();
    });
    itemTableBody?.addEventListener('click', (e) => {
        const row = e.target.closest('tr[data-code]');
        if (!row) return;
        selectItemFromPopup(row);
    });
    itemTableBody?.addEventListener('keydown', (e) => {
        const row = e.target.closest('tr[data-code]');
        if (e.key === 'Enter') {
            if (row && row.dataset.code) {
                e.preventDefault();
                selectItemFromPopup(row);
            }
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!row || !row.dataset.code) return;
            const rows = Array.from(itemTableBody.querySelectorAll('tr[data-code]'));
            const idx = rows.indexOf(row);
            if (idx === -1) return;
            e.preventDefault();
            if (e.key === 'ArrowDown' && idx < rows.length - 1) rows[idx + 1].focus();
            if (e.key === 'ArrowUp' && idx > 0) rows[idx - 1].focus();
        }
    });

    body?.addEventListener('click', (e) => {
        const row = e.target.closest('tr.sa-data-row[data-line]');
        if (!row) return;
        if (e.target.closest('.btn-remove')) {
            row.remove();
            reindex();
            validateNegativeStockRows();
            return;
        }
        const td = e.target.closest('td');
        if (!td || td.querySelector('input, select')) return;
        const key = inlineColKey(td);
        if (key) beginInlineEdit(td, row, key);
    });

    const initial = window.__STOCK_ADJ_INITIAL__;
    if (initial && initial.header) {
        adjNo.value = initial.header.adj_no || adjNo.value;
        if (initial.header.adj_date) adjDate.value = initial.header.adj_date;
        adjRemarks.value = initial.header.remarks || '';
        const lines = Array.isArray(initial.lines) ? initial.lines : [];
        if (lines.length) {
            const entry = ensureEntryRow();
            body.querySelectorAll('tr.sa-data-row, tr.empty-row').forEach((r) => r.remove());
            lines.forEach((ln, idx) => {
                insertLineBeforeEntry(mountDataRow(idx + 1, ln));
            });
            if (entry && body.lastElementChild !== entry) body.appendChild(entry);
            reindex();
        } else {
            ensureEntryRow();
            reindex();
        }
    } else {
        ensureEntryRow();
        reindex();
    }
    loadWarehouses().catch(() => {}).finally(() => {
        validateNegativeStockRows();
    });

    if (queryMode) {
        body.querySelectorAll('.btn-remove').forEach((btn) => {
            const cell = btn.closest('.sa-col-action');
            if (cell) cell.textContent = '';
        });
    }
});
