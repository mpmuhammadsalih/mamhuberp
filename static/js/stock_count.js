(function () {
    const page = document.getElementById('scDetailPage');
    if (!page) return;

    const countNo = parseInt(page.dataset.countNo, 10);
    const status = (page.dataset.status || '').toUpperCase();
    const apiLine = page.dataset.apiLine;
    const apiLineEdit = page.dataset.apiLineEdit;
    const apiLineDelete = page.dataset.apiLineDelete;
    const canEdit = page.dataset.editable === '1';
    const apiPdt = page.dataset.apiPdt;
    const apiPost = page.dataset.apiPost;
    const apiCancel = page.dataset.apiCancel;
    const apiDelete = page.dataset.apiDelete;
    const apiGet = page.dataset.apiGet;

    const scanInput = document.getElementById('scScanInput');
    const qtyInput = document.getElementById('scQtyInput');
    const whInput = document.getElementById('scWhInput');
    const binInput = document.getElementById('scBinInput');
    const linesBody = document.getElementById('scLinesBody');
    const linesFoot = document.getElementById('scLinesFoot');
    const statusBadge = document.getElementById('scStatusBadge');
    const kpiLines = document.getElementById('scKpiLines');
    const kpiVariances = document.getElementById('scKpiVariances');
    const kpiVarianceAmount = document.getElementById('scKpiVarianceAmount');
    const kpiCounted = document.getElementById('scKpiCounted');
    const kpiStockValue = document.getElementById('scKpiStockValue');
    const kpiStockValueSub = document.getElementById('scKpiStockValueSub');
    const lineSearch = document.getElementById('scLineSearch');
    const filterVariance = document.getElementById('scFilterVariance');
    const filterMainCat = document.getElementById('scFilterMainCat');
    const filterCategory = document.getElementById('scFilterCategory');
    const filterMicroCat = document.getElementById('scFilterMicroCat');
    const filterCountEl = document.getElementById('scFilterCount');
    const btnClearFilters = document.getElementById('scBtnClearFilters');
    const btnExportExcel = document.getElementById('scBtnExportExcel');
    const btnExportPdf = document.getElementById('scBtnExportPdf');
    const exportExcelBase = page.dataset.exportExcel || '';
    const exportPdfBase = page.dataset.exportPdf || '';
    const refreshIndicator = document.getElementById('scRefreshIndicator');
    const editModal = document.getElementById('scEditModal');
    const editBackdrop = document.getElementById('scEditBackdrop');
    const editMeta = document.getElementById('scEditMeta');
    const editSystemQty = document.getElementById('scEditSystemQty');
    const editCountedQty = document.getElementById('scEditCountedQty');
    const editStorageId = document.getElementById('scEditStorageId');
    const journalModal = document.getElementById('scJournalModal');
    const journalBackdrop = document.getElementById('scJournalBackdrop');
    const journalMeta = document.getElementById('scJournalMeta');
    const journalBody = document.getElementById('scJournalBody');
    const journalCount = document.getElementById('scJournalCount');
    let editingLineNo = null;
    let selectedLineNo = null;
    let journalModalOpen = false;
    let journalData = [];

    try {
        const journalEl = document.getElementById('scJournalData');
        journalData = journalEl ? JSON.parse(journalEl.textContent || '[]') : [];
    } catch {
        journalData = [];
    }

    const REFRESH_MS = 5000;
    let currentStatus = status;
    let lastLinesFp = '';
    let refreshTimer = null;
    let pauseRefreshUntil = 0;

    function fmt(n) {
        const x = Number(n);
        return Number.isFinite(x) ? x.toFixed(3) : '0.000';
    }

    function linesFingerprint(lines) {
        return JSON.stringify((lines || []).map((ln) => [
            ln.line_no,
            ln.itemcode,
            ln.barcode,
            ln.system_qty,
            ln.counted_qty,
            ln.variance_qty,
            ln.storage_id,
            ln.warehouse_id,
            ln.counted_by,
            ln.average_cost,
            ln.stock_value,
        ]));
    }

    function setRefreshIndicator(mode, label) {
        if (!refreshIndicator) return;
        refreshIndicator.classList.remove('is-live', 'is-paused');
        if (mode) refreshIndicator.classList.add(mode);
        refreshIndicator.innerHTML = '<i class="bi bi-arrow-repeat" aria-hidden="true"></i> ' + (label || 'Auto-refresh');
    }

    function fmtInt(n) {
        const x = Number(n);
        return Number.isFinite(x) ? String(Math.round(x)) : '0';
    }

    function fmtMoney(n) {
        const x = Number(n);
        return Number.isFinite(x) ? x.toFixed(2) : '0.00';
    }

    function roundMoney(n) {
        const x = Number(n);
        return Number.isFinite(x) ? Math.round(x * 100) / 100 : 0;
    }

    function fmtQtyOrDash(v) {
        if (v === null || v === undefined || v === '') return '—';
        return fmt(v);
    }

    function journalActionType(action) {
        const a = String(action || '').toUpperCase();
        if (a.includes('INSERT') || a.includes('ADD')) return 'insert';
        if (a.includes('UPDATE') || a.includes('EDIT')) return 'update';
        return 'other';
    }

    function journalInsertQty(j) {
        if (journalActionType(j.action) === 'insert') return fmtQtyOrDash(j.new_counted_qty);
        return '—';
    }

    function journalUpdateQty(j) {
        if (journalActionType(j.action) === 'update') return fmtQtyOrDash(j.new_counted_qty);
        return '—';
    }

    function escHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function fmtJournalWhen(v) {
        if (!v) return '—';
        const s = String(v);
        if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
            return s.slice(0, 16).replace('T', ' ');
        }
        return s;
    }

    function journalRowsForLine(lineNo, itemcode) {
        const ln = Number(lineNo);
        const ic = String(itemcode || '');
        return (journalData || []).filter((j) => {
            const jLine = j.line_no != null && j.line_no !== '' ? Number(j.line_no) : null;
            if (jLine != null && !Number.isNaN(jLine)) return jLine === ln;
            return ic && String(j.itemcode || '') === ic;
        });
    }

    async function loadJournalData() {
        if (!apiGet) return false;
        try {
            const res = await fetch(apiGet, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) return false;
            if (Array.isArray(data.journal)) {
                journalData = data.journal;
            }
            return true;
        } catch {
            return false;
        }
    }

    function closeJournalModal() {
        journalModalOpen = false;
        selectedLineNo = null;
        if (journalModal) journalModal.hidden = true;
        if (journalBackdrop) journalBackdrop.hidden = true;
        linesBody?.querySelectorAll('tr.sc-row--selected').forEach((tr) => {
            tr.classList.remove('sc-row--selected');
        });
        pauseRefreshUntil = Date.now() + 800;
    }

    function renderJournalContent(tr) {
        if (!journalBody || !tr) return;
        const lineNo = parseInt(tr.dataset.lineNo, 10);
        const itemcode = tr.dataset.itemcode || '';
        const itemName = tr.dataset.itemName || '';
        const barcode = tr.dataset.barcode || '';
        const countedQty = tr.dataset.countedQty || '0';
        const systemQty = tr.dataset.systemQty || '0';
        if (!lineNo) return;

        const rows = journalRowsForLine(lineNo, itemcode);
        const metaParts = [`Line #${lineNo}`];
        if (itemcode) metaParts.push(itemcode);
        if (itemName) metaParts.push(itemName);
        if (barcode) metaParts.push(`Barcode ${barcode}`);
        metaParts.push(`System ${fmt(systemQty)}`, `Counted ${fmt(countedQty)}`);
        if (journalMeta) journalMeta.textContent = metaParts.join(' · ');

        if (journalCount) {
            journalCount.textContent = rows.length
                ? `${rows.length} change${rows.length === 1 ? '' : 's'}`
                : 'No changes recorded';
        }
        if (!rows.length) {
            journalBody.innerHTML = '<tr><td colspan="8" class="sc-empty-cell">No change history for this line.</td></tr>';
            return;
        }
        journalBody.innerHTML = rows.map((j) => `<tr>
              <td>${escHtml(fmtJournalWhen(j.logged_at))}</td>
              <td>${escHtml(j.action || '')}</td>
              <td class="sc-num">${escHtml(journalInsertQty(j))}</td>
              <td class="sc-num">${escHtml(journalUpdateQty(j))}</td>
              <td class="sc-num">${escHtml(fmtQtyOrDash(j.old_counted_qty))}</td>
              <td class="sc-num">${escHtml(fmtQtyOrDash(j.new_counted_qty))}</td>
              <td>${escHtml(j.changed_by || j.counted_by || '—')}</td>
              <td>${escHtml(j.source || 'ERP')}</td>
            </tr>`).join('');
    }

    async function openJournalModal(tr) {
        if (!journalModal || !journalBackdrop || !tr) return;
        const lineNo = parseInt(tr.dataset.lineNo, 10);
        if (!lineNo) return;

        selectedLineNo = lineNo;
        journalModalOpen = true;
        linesBody.querySelectorAll('tr.sc-row--selected').forEach((row) => {
            row.classList.remove('sc-row--selected');
        });
        tr.classList.add('sc-row--selected');

        journalBackdrop.hidden = false;
        journalModal.hidden = false;

        if (journalMeta) journalMeta.textContent = 'Loading change history…';
        if (journalBody) {
            journalBody.innerHTML = '<tr><td colspan="8" class="sc-empty-cell">Loading…</td></tr>';
        }

        await loadJournalData();

        const liveTr = linesBody?.querySelector(`tr[data-line-no="${lineNo}"]`) || tr;
        liveTr.classList.add('sc-row--selected');
        renderJournalContent(liveTr);

        pauseRefreshUntil = Date.now() + 1500;
        document.getElementById('scJournalClose')?.focus();
    }

    function restoreJournalSelection() {
        if (selectedLineNo == null || !linesBody) return;
        const tr = linesBody.querySelector(`tr[data-line-no="${selectedLineNo}"]`);
        if (!tr) {
            if (journalModalOpen) closeJournalModal();
            return;
        }
        tr.classList.add('sc-row--selected');
        if (journalModalOpen) {
            loadJournalData().then(() => renderJournalContent(tr));
        }
    }

    function varianceAmount(ln) {
        const v = Number(ln.variance_qty || 0);
        const avg = Number(ln.average_cost || 0);
        return Number.isFinite(v) && Number.isFinite(avg) ? v * avg : 0;
    }

    function systemValue(ln) {
        const system = Number(ln.system_qty || 0);
        const avg = Number(ln.average_cost || 0);
        return roundMoney(system * avg);
    }

    function countedValue(ln) {
        const counted = Number(ln.counted_qty || 0);
        const avg = Number(ln.average_cost || 0);
        return roundMoney(counted * avg);
    }

    let currentLines = [];

    function lineStatsFromRows(rows) {
        let varianceCount = 0;
        let totalCounted = 0;
        let totalSystem = 0;
        let totalVarianceQty = 0;
        let totalStockValue = 0;
        let totalSystemValue = 0;
        let totalVarianceAmount = 0;
        (rows || []).forEach((ln) => {
            const v = Number(ln.variance_qty || 0);
            if (Math.abs(v) > 0.0005) varianceCount += 1;
            const counted = Number(ln.counted_qty || 0);
            const system = Number(ln.system_qty || 0);
            totalCounted += counted;
            totalSystem += system;
            totalVarianceQty += v;
            totalVarianceAmount += varianceAmount(ln);
            totalStockValue += countedValue(ln);
            totalSystemValue += systemValue(ln);
        });
        return {
            lineCount: (rows || []).length,
            varianceCount,
            totalCounted,
            totalSystem,
            totalVarianceQty,
            totalStockValue,
            totalSystemValue,
            totalVarianceAmount,
        };
    }

    function lineStats(lines) {
        return lineStatsFromRows(lines);
    }

    function bootstrapCurrentLinesFromDom() {
        if (!linesBody || currentLines.length) return;
        const rows = [];
        linesBody.querySelectorAll('tr[data-line-no]').forEach((tr) => {
            rows.push({
                line_no: parseInt(tr.dataset.lineNo, 10),
                system_qty: tr.dataset.systemQty,
                counted_qty: tr.dataset.countedQty,
                variance_qty: tr.dataset.varianceQty,
                average_cost: tr.dataset.averageCost,
            });
        });
        if (rows.length) currentLines = rows;
    }

    function visibleLineStats() {
        if (!linesBody) return lineStatsFromRows([]);
        const rows = [];
        linesBody.querySelectorAll('tr[data-line-no]').forEach((tr) => {
            if (tr.style.display === 'none') return;
            const lineNo = parseInt(tr.dataset.lineNo, 10);
            const ln = (currentLines || []).find((row) => Number(row.line_no) === lineNo);
            if (ln) rows.push(ln);
        });
        return lineStatsFromRows(rows);
    }

    function hasActiveFilters() {
        return Boolean(
            (lineSearch?.value || '').trim()
            || (filterVariance?.value || '').trim()
            || (filterMainCat?.value || '').trim()
            || (filterCategory?.value || '').trim()
            || (filterMicroCat?.value || '').trim()
        );
    }

    function updateLineTotals(lines) {
        const s = hasActiveFilters() ? visibleLineStats() : lineStatsFromRows(lines);
        const showFoot = (lines || []).length > 0;
        if (linesFoot) linesFoot.hidden = !showFoot;
        const set = (id, text) => {
            const el = document.getElementById(id);
            if (el) el.textContent = text;
        };
        set('scTotalSystem', fmt(s.totalSystem));
        set('scTotalCounted', fmt(s.totalCounted));
        set('scTotalVariance', fmt(s.totalVarianceQty));
        set('scTotalSystemValue', fmtMoney(s.totalSystemValue));
        set('scTotalStockValue', fmtMoney(s.totalStockValue));
        set('scTotalVarAmount', fmtMoney(s.totalVarianceAmount));
        const label = document.querySelector('.sc-total-label');
        if (label) {
            label.textContent = hasActiveFilters() ? 'Total (filtered)' : 'Total';
        }
    }

    function updateKpis(lines) {
        const s = lineStats(lines);
        if (kpiLines) kpiLines.textContent = String(s.lineCount);
        if (kpiVariances) kpiVariances.textContent = String(s.varianceCount);
        if (kpiVarianceAmount) kpiVarianceAmount.textContent = 'Amount ' + fmtMoney(s.totalVarianceAmount);
        if (kpiCounted) kpiCounted.textContent = fmtInt(s.totalCounted);
        if (kpiStockValue) kpiStockValue.textContent = fmtMoney(s.totalStockValue);
        if (kpiStockValueSub) kpiStockValueSub.textContent = 'Current stock ' + fmtMoney(s.totalSystemValue);
        updateLineTotals(lines);
    }

    function setStatus(label) {
        const st = String(label || 'PENDING').toUpperCase();
        if (statusBadge) {
            statusBadge.textContent = st;
            statusBadge.className = 'sc-status-badge sc-status-badge--' + st.toLowerCase();
        }
    }

    function rowDataAttrs(ln) {
        const v = Number(ln.variance_qty || 0);
        const hasVar = Math.abs(v) > 0.0005 ? '1' : '0';
        const attrs = [
            `data-line-no="${ln.line_no || ''}"`,
            `data-itemcode="${ln.itemcode || ''}"`,
            `data-item-name="${String(ln.item_name || '').replace(/"/g, '&quot;')}"`,
            `data-system-qty="${ln.system_qty || 0}"`,
            `data-counted-qty="${ln.counted_qty || 0}"`,
            `data-storage-id="${ln.storage_id || ''}"`,
            `data-barcode="${String(ln.barcode || '').replace(/"/g, '&quot;')}"`,
            `data-variance="${hasVar}"`,
            `data-variance-qty="${ln.variance_qty || 0}"`,
            `data-average-cost="${ln.average_cost || 0}"`,
            `data-main-cat="${String(ln.main_category_name || '').replace(/"/g, '&quot;')}"`,
            `data-cat="${String(ln.category_name || '').replace(/"/g, '&quot;')}"`,
            `data-micro-cat="${String(ln.micro_category_name || '').replace(/"/g, '&quot;')}"`,
        ];
        return attrs.join(' ');
    }

    function actionCellHtml() {
        if (!canEdit) return '';
        return `<td class="sc-actions">
              <button type="button" class="sc-btn-icon-only sc-btn-edit" title="Edit line" aria-label="Edit line"><i class="bi bi-pencil-square" aria-hidden="true"></i></button>
            </td>`;
    }

    function emptyColspan() {
        return canEdit ? 18 : 17;
    }

    function renderLines(lines) {
        if (!linesBody) return;
        if (!lines || !lines.length) {
            currentLines = [];
            linesBody.innerHTML = `<tr id="scEmptyRow"><td colspan="${emptyColspan()}" class="sc-empty-cell">No lines yet — scan items above or upload from PDT.</td></tr>`;
            updateKpis([]);
            lastLinesFp = linesFingerprint([]);
            applyLineFilters();
            return;
        }
        currentLines = lines.slice();
        linesBody.innerHTML = lines.map((ln) => {
            const v = Number(ln.variance_qty || 0);
            const cls = Math.abs(v) > 0.0005 ? ' class="sc-row--var"' : '';
            const wh =
                ln.warehouse_code ||
                ln.warehouse_name ||
                (ln.warehouse_id ? `WH ${ln.warehouse_id}` : '');
            const search = [
                ln.itemcode,
                ln.item_name,
                ln.barcode,
                ln.main_category_name,
                ln.category_name,
                ln.micro_category_name,
                ln.counted_by,
            ].filter(Boolean).join(' ');
            const avgCost = Number(ln.average_cost || 0);
            const stockVal = countedValue(ln);
            const sysVal = systemValue(ln);
            const varAmt = varianceAmount(ln);
            return `<tr${cls} data-search="${search.replace(/"/g, '&quot;')}" ${rowDataAttrs(ln)}>
              <td style="text-align:center;">${ln.line_no || ''}</td>
              <td><span class="sc-code">${ln.itemcode || ''}</span></td>
              <td>${ln.item_name || ''}</td>
              <td class="sc-cat" title="${escHtml(ln.main_category_name || '')}">${ln.main_category_name || ''}</td>
              <td class="sc-cat" title="${escHtml(ln.category_name || '')}">${ln.category_name || ''}</td>
              <td class="sc-cat" title="${escHtml(ln.micro_category_name || '')}">${ln.micro_category_name || ''}</td>
              <td>${ln.barcode || ''}</td>
              <td>${wh}</td>
              <td class="sc-user">${ln.counted_by || '—'}</td>
              <td class="sc-num">${avgCost.toFixed(3)}</td>
              <td class="sc-num">${fmt(ln.system_qty)}</td>
              <td class="sc-num">${fmt(ln.counted_qty)}</td>
              <td class="sc-num sc-num--var">${fmt(ln.variance_qty)}</td>
              <td class="sc-num">${sysVal.toFixed(2)}</td>
              <td class="sc-num">${stockVal.toFixed(2)}</td>
              <td class="sc-num sc-num--var">${varAmt.toFixed(2)}</td>
              <td>${ln.storage_id || ''}</td>
              ${actionCellHtml()}
            </tr>`;
        }).join('');
        updateKpis(lines);
        lastLinesFp = linesFingerprint(lines);
        refreshCategoryFilters(lines);
        applyLineFilters();
        restoreJournalSelection();
    }

    function uniqueSorted(values) {
        return Array.from(new Set((values || []).map((v) => String(v || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b));
    }

    function fillCategorySelect(selectEl, placeholder, values, currentValue) {
        if (!selectEl) return;
        const keep = currentValue || selectEl.value || '';
        selectEl.innerHTML = '';
        const first = document.createElement('option');
        first.value = '';
        first.textContent = placeholder;
        selectEl.appendChild(first);
        uniqueSorted(values).forEach((name) => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            selectEl.appendChild(opt);
        });
        if (keep && uniqueSorted(values).includes(keep)) {
            selectEl.value = keep;
        }
    }

    function refreshCategoryFilters(lines) {
        const main = [];
        const cat = [];
        const micro = [];
        (lines || []).forEach((ln) => {
            if (ln.main_category_name) main.push(ln.main_category_name);
            if (ln.category_name) cat.push(ln.category_name);
            if (ln.micro_category_name) micro.push(ln.micro_category_name);
        });
        fillCategorySelect(filterMainCat, 'All main categories', main, filterMainCat?.value);
        fillCategorySelect(filterCategory, 'All categories', cat, filterCategory?.value);
        fillCategorySelect(filterMicroCat, 'All micro categories', micro, filterMicroCat?.value);
    }

    function filterQueryParams() {
        const p = new URLSearchParams();
        const q = (lineSearch?.value || '').trim();
        const variance = (filterVariance?.value || '').trim();
        const mainCat = (filterMainCat?.value || '').trim();
        const category = (filterCategory?.value || '').trim();
        const microCat = (filterMicroCat?.value || '').trim();
        if (q) p.set('q', q);
        if (variance) p.set('variance', variance);
        if (mainCat) p.set('main_category', mainCat);
        if (category) p.set('category', category);
        if (microCat) p.set('micro_category', microCat);
        return p;
    }

    function syncExportLinks() {
        const q = filterQueryParams().toString();
        if (btnExportExcel && exportExcelBase) {
            btnExportExcel.href = exportExcelBase + (q ? `?${q}` : '');
        }
        if (btnExportPdf && exportPdfBase) {
            btnExportPdf.href = exportPdfBase + (q ? `?${q}` : '');
        }
    }

    function applyLineFilters() {
        if (!linesBody) return;
        const q = (lineSearch?.value || '').trim().toLowerCase();
        const variance = (filterVariance?.value || '').trim();
        const mainCat = (filterMainCat?.value || '').trim();
        const category = (filterCategory?.value || '').trim();
        const microCat = (filterMicroCat?.value || '').trim();
        const rows = linesBody.querySelectorAll('tr[data-search]');
        let visible = 0;
        rows.forEach((tr) => {
            let ok = true;
            if (q) {
                ok = (tr.getAttribute('data-search') || '').toLowerCase().indexOf(q) !== -1;
            }
            if (ok && variance === 'variance') {
                ok = tr.dataset.variance === '1';
            } else if (ok && variance === 'match') {
                ok = tr.dataset.variance !== '1';
            }
            if (ok && mainCat) ok = (tr.dataset.mainCat || '') === mainCat;
            if (ok && category) ok = (tr.dataset.cat || '') === category;
            if (ok && microCat) ok = (tr.dataset.microCat || '') === microCat;
            tr.style.display = ok ? '' : 'none';
            if (ok) visible += 1;
        });
        if (filterCountEl) {
            const total = rows.length;
            if (!total) {
                filterCountEl.textContent = '';
            } else if (visible === total) {
                filterCountEl.textContent = `${total} line${total === 1 ? '' : 's'}`;
            } else {
                filterCountEl.textContent = `${visible} of ${total} lines`;
            }
        }
        syncExportLinks();
        if (currentLines.length) updateLineTotals(currentLines);
    }

    function clearLineFilters() {
        if (lineSearch) lineSearch.value = '';
        if (filterVariance) filterVariance.value = '';
        if (filterMainCat) filterMainCat.value = '';
        if (filterCategory) filterCategory.value = '';
        if (filterMicroCat) filterMicroCat.value = '';
        applyLineFilters();
    }

    async function postJson(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            throw new Error(data.error || 'Request failed');
        }
        return data;
    }

    function showPostProgress(current, total, phase) {
        const cur = Number(current) || 0;
        const tot = Number(total) || 1;
        const label = phase || 'Posting';
        if (typeof window.updateLoadingOverlayProgress === 'function') {
            window.updateLoadingOverlayProgress(cur, tot, `${label} stock count…`, label);
        } else if (typeof window.showLoadingOverlay === 'function') {
            window.showLoadingOverlay(`${label} stock count…`);
        }
    }

    function hidePostProgress() {
        if (typeof window.hideLoadingOverlay === 'function') window.hideLoadingOverlay();
    }

    async function postCountWithProgress(onlyVariance) {
        const total = currentLines && currentLines.length ? currentLines.length : 1;
        showPostProgress(0, total, 'Starting post');
        const data = await postJson(apiPost, { count_no: countNo, only_variance: !!onlyVariance });
        const updated = Number(data?.stats?.updated || total || 1);
        showPostProgress(updated, total, 'Complete');
        return data;
    }

    async function addLine() {
        const barcode = (scanInput?.value || '').trim();
        const qty = parseFloat(qtyInput?.value || '0');
        const storageId = binInput?.value?.trim();
        if (!barcode) {
            alert('Enter or scan a barcode.');
            return;
        }
        const payload = {
            count_no: countNo,
            barcode,
            counted_qty: qty,
            qty,
        };
        if (storageId) payload.storage_id = parseInt(storageId, 10);
        const whId = whInput?.value?.trim();
        if (whId) payload.warehouse_id = parseInt(whId, 10);
        const data = await postJson(apiLine, payload);
        renderLines(data.lines);
        setStatus('PENDING');
        currentStatus = 'PENDING';
        pauseRefreshUntil = Date.now() + 2500;
        if (scanInput) {
            scanInput.value = '';
            scanInput.focus();
        }
    }

    document.getElementById('scBtnAddLine')?.addEventListener('click', () => {
        addLine().catch((e) => alert(e.message || e));
    });
    scanInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addLine().catch((err) => alert(err.message || err));
        }
    });

    lineSearch?.addEventListener('input', applyLineFilters);
    filterVariance?.addEventListener('change', applyLineFilters);
    filterMainCat?.addEventListener('change', applyLineFilters);
    filterCategory?.addEventListener('change', applyLineFilters);
    filterMicroCat?.addEventListener('change', applyLineFilters);
    btnClearFilters?.addEventListener('click', clearLineFilters);

    function openEditModal(tr) {
        if (!editModal || !tr) return;
        editingLineNo = parseInt(tr.dataset.lineNo, 10);
        if (!editingLineNo) return;
        const itemcode = tr.dataset.itemcode || '';
        const itemName = tr.dataset.itemName || '';
        const barcode = tr.dataset.barcode || '';
        if (editMeta) {
            editMeta.textContent = `#${editingLineNo} · Item ${itemcode}${itemName ? ' — ' + itemName : ''}${barcode ? ' · ' + barcode : ''}`;
        }
        if (editSystemQty) editSystemQty.value = fmt(tr.dataset.systemQty || 0);
        if (editCountedQty) editCountedQty.value = tr.dataset.countedQty || '0';
        if (editStorageId) editStorageId.value = tr.dataset.storageId || '';
        editModal.hidden = false;
        if (editBackdrop) editBackdrop.hidden = false;
        pauseRefreshUntil = Date.now() + 600000;
        editCountedQty?.focus();
        editCountedQty?.select();
    }

    function closeEditModal() {
        editingLineNo = null;
        if (editModal) editModal.hidden = true;
        if (editBackdrop) editBackdrop.hidden = true;
        pauseRefreshUntil = Date.now() + 2500;
    }

    async function saveEditLine() {
        if (!apiLineEdit || !editingLineNo) return;
        const countedQty = parseFloat(editCountedQty?.value || '0');
        if (!Number.isFinite(countedQty) || countedQty < 0) {
            alert('Enter a valid counted quantity.');
            return;
        }
        const payload = {
            count_no: countNo,
            line_no: editingLineNo,
            counted_qty: countedQty,
        };
        const sidRaw = (editStorageId?.value || '').trim();
        if (sidRaw) payload.storage_id = parseInt(sidRaw, 10);
        else payload.storage_id = null;
        const data = await postJson(apiLineEdit, payload);
        closeEditModal();
        renderLines(data.lines);
        if (data.status) {
            setStatus(data.status);
            currentStatus = String(data.status).toUpperCase();
        }
    }

    async function deleteEditLine() {
        if (!apiLineDelete || !editingLineNo) return;
        if (!confirm(`Remove line #${editingLineNo} from this count?`)) return;
        const data = await postJson(apiLineDelete, { count_no: countNo, line_no: editingLineNo });
        closeEditModal();
        renderLines(data.lines);
    }

    linesBody?.addEventListener('click', (e) => {
        const editBtn = e.target.closest('.sc-btn-edit');
        if (editBtn) {
            const tr = editBtn.closest('tr[data-line-no]');
            if (tr) openEditModal(tr);
            return;
        }
        const tr = e.target.closest('tr[data-line-no]');
        if (tr) openJournalModal(tr).catch(() => {});
    });

    document.getElementById('scJournalClose')?.addEventListener('click', closeJournalModal);
    document.getElementById('scJournalDismiss')?.addEventListener('click', closeJournalModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && journalModalOpen) closeJournalModal();
    });

    document.getElementById('scEditClose')?.addEventListener('click', closeEditModal);
    document.getElementById('scEditCancel')?.addEventListener('click', closeEditModal);
    editBackdrop?.addEventListener('click', closeEditModal);
    document.getElementById('scEditSave')?.addEventListener('click', () => {
        saveEditLine().catch((err) => alert(err.message || err));
    });
    document.getElementById('scEditDelete')?.addEventListener('click', () => {
        deleteEditLine().catch((err) => alert(err.message || err));
    });
    editCountedQty?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveEditLine().catch((err) => alert(err.message || err));
        }
    });

    document.getElementById('scBtnPdtUpload')?.addEventListener('click', async () => {
        const raw = document.getElementById('scPdtJson')?.value?.trim();
        if (!raw) {
            alert('Paste PDT JSON first.');
            return;
        }
        let body;
        try {
            body = JSON.parse(raw);
        } catch {
            alert('Invalid JSON.');
            return;
        }
        body.count_no = body.count_no || countNo;
        const data = await postJson(apiPdt, body);
        alert(`Uploaded ${data.lines_written || 0} line(s).`);
        window.location.reload();
    });

    document.getElementById('scBtnPost')?.addEventListener('click', async () => {
        if (!confirm('Accept this count and update stock to counted quantities?')) return;
        try {
            const data = await postCountWithProgress(false);
            alert(data.message || 'Posted.');
            window.location.reload();
        } catch (e) {
            hidePostProgress();
            alert(e.message || e);
        }
    });

    document.getElementById('scBtnPostVariance')?.addEventListener('click', async () => {
        if (!confirm('Update stock only for lines with a variance?')) return;
        try {
            const data = await postCountWithProgress(true);
            alert(data.message || 'Posted.');
            window.location.reload();
        } catch (e) {
            hidePostProgress();
            alert(e.message || e);
        }
    });

    document.getElementById('scBtnCancel')?.addEventListener('click', async () => {
        if (!confirm('Cancel this stock count?')) return;
        try {
            await postJson(apiCancel, { count_no: countNo });
            window.location.reload();
        } catch (e) {
            alert(e.message || e);
        }
    });

    document.getElementById('scBtnDelete')?.addEventListener('click', async () => {
        if (!confirm('Delete this draft count?')) return;
        try {
            await postJson(apiDelete, { count_no: countNo });
            window.location.href = page.dataset.listUrl || '/warehouse/stock-counting';
        } catch (e) {
            alert(e.message || e);
        }
    });

    if (scanInput && status !== 'POSTED' && status !== 'CANCELLED') {
        scanInput.focus();
    }

    function shouldPauseRefresh() {
        if (Date.now() < pauseRefreshUntil) return true;
        if (document.hidden) return true;
        if (editModal && !editModal.hidden) return true;
        if (scanInput && document.activeElement === scanInput && (scanInput.value || '').trim()) return true;
        const pdt = document.getElementById('scPdtJson');
        if (pdt && document.activeElement === pdt) return true;
        return false;
    }

    async function refreshFromServer() {
        if (!apiGet) return;
        if (shouldPauseRefresh()) {
            setRefreshIndicator('is-paused', 'Paused');
            return;
        }
        setRefreshIndicator('is-live', 'Updating…');
        const res = await fetch(apiGet, {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            setRefreshIndicator('', 'Auto-refresh');
            return;
        }
        const newStatus = String((data.header && data.header.status) || '').toUpperCase();
        if (newStatus && newStatus !== currentStatus) {
            if (newStatus === 'POSTED' || newStatus === 'CANCELLED') {
                window.location.reload();
                return;
            }
            currentStatus = newStatus;
            setStatus(newStatus);
        }
        const fp = linesFingerprint(data.lines);
        if (fp !== lastLinesFp) {
            renderLines(data.lines);
        } else if (journalModalOpen && selectedLineNo != null) {
            await loadJournalData();
            const tr = linesBody?.querySelector(`tr[data-line-no="${selectedLineNo}"]`);
            if (tr) renderJournalContent(tr);
        }
        if (Array.isArray(data.journal) && !journalModalOpen) {
            journalData = data.journal;
        }
        const now = new Date();
        const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        setRefreshIndicator('is-live', 'Live · ' + time);
    }

    function startAutoRefresh() {
        if (!apiGet) return;
        refreshFromServer().catch(() => setRefreshIndicator('', 'Auto-refresh'));
        refreshTimer = setInterval(() => {
            refreshFromServer().catch(() => setRefreshIndicator('', 'Auto-refresh'));
        }, REFRESH_MS);
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                refreshFromServer().catch(() => {});
            }
        });
    }

    bootstrapCurrentLinesFromDom();
    applyLineFilters();
    startAutoRefresh();
})();
