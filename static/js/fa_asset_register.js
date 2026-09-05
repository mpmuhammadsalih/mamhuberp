(function () {
    const form = document.getElementById('faRegisterForm');
    const body = document.getElementById('farLinesBody');
    const hidden = document.getElementById('farHiddenLines');
    const entryName = document.getElementById('farEntryName');
    const entryCategory = document.getElementById('farEntryCategory');
    const entryCost = document.getElementById('farEntryCost');
    const entrySalvage = document.getElementById('farEntrySalvage');
    const entrySerial = document.getElementById('farEntrySerial');
    const entryCustodian = document.getElementById('farEntryCustodian');
    const defaultLocation = document.getElementById('default_location_code');
    const btnAdd = document.getElementById('farBtnAddLine');
    const btnSaveDraft = document.getElementById('farBtnSaveDraft');
    const btnSavePost = document.getElementById('farBtnSavePost');

    const categories = window.__FA_REGISTER_CATEGORIES__ || {};

    const lookup = document.querySelector('#faCreditLookupDisplay')
        && document.querySelector('#faCreditLookupDisplay').closest('.global-lookup, .odoo-lookup');
    const partyType = document.getElementById('faCreditPartyType');
    const partyCode = document.getElementById('faCreditPartyCode');
    const acqDate = document.getElementById('acquisition_date');
    const remarks = document.getElementById('remarks');
    const creditDisplay = document.getElementById('faCreditLookupDisplay');

    const HEADER_INPUTS = [acqDate, defaultLocation, remarks, creditDisplay];
    const ENTRY_INPUTS = [
        entryName, entryCategory, entryCost, entrySalvage, entrySerial, entryCustodian,
    ];

    function lookupDropdownOpen() {
        if (!lookup) return false;
        const dd = lookup.querySelector('.global-lookup__dropdown, .odoo-lookup__dropdown');
        if (!dd) return false;
        const opts = dd.querySelectorAll('.global-lookup__option, .odoo-lookup__option');
        return opts.length > 0 && dd.offsetParent !== null;
    }

    function isNavField(el) {
        if (!el) return false;
        return HEADER_INPUTS.includes(el)
            || ENTRY_INPUTS.includes(el)
            || el === btnAdd
            || el === btnSaveDraft
            || el === btnSavePost;
    }

    function buildFocusChain() {
        const chain = [];
        const push = (el) => {
            if (!el || el.disabled) return;
            if (el.offsetParent === null && el !== document.activeElement) return;
            chain.push(el);
        };
        HEADER_INPUTS.forEach(push);
        ENTRY_INPUTS.forEach(push);
        push(btnAdd);
        return chain;
    }

    function focusTarget(el) {
        if (!el || typeof el.focus !== 'function') return;
        el.focus();
        try {
            if (el.select && el.tagName !== 'SELECT' && el.type !== 'checkbox') el.select();
        } catch (_) { /* ignore */ }
    }

    function moveFocus(dir) {
        const chain = buildFocusChain();
        if (!chain.length) return;
        const active = document.activeElement;
        let idx = chain.indexOf(active);
        if (idx < 0) return;
        let next = idx + dir;
        if (next < 0) next = chain.length - 1;
        if (next >= chain.length) next = 0;
        focusTarget(chain[next]);
    }

    function handleEnterNav(e) {
        if (e.key !== 'Enter' || e.ctrlKey || e.altKey || e.metaKey) return;
        if (lookupDropdownOpen()) return;
        const active = document.activeElement;
        if (!isNavField(active)) return;

        if (e.shiftKey) {
            e.preventDefault();
            moveFocus(-1);
            return;
        }

        e.preventDefault();
        if (active === btnAdd) {
            addLine();
            return;
        }
        moveFocus(1);
    }

    function money(n) {
        const x = Number(n);
        return Number.isFinite(x) ? x.toFixed(2) : '0.00';
    }

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function lineRows() {
        return Array.from(body.querySelectorAll('tr[data-category-id]'));
    }

    function catLabel(id) {
        return categories[String(id)] || String(id || '');
    }

    function syncTotals() {
        const rows = lineRows();
        let cost = 0;
        let salvage = 0;
        rows.forEach((tr) => {
            cost += Number(tr.dataset.cost || 0);
            salvage += Number(tr.dataset.salvage || 0);
        });
        const set = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.value = v;
        };
        set('farLineCount', String(rows.length));
        set('farTotalCost', money(cost));
        set('farTotalSalvage', money(salvage));
        rows.forEach((tr, i) => {
            const sl = tr.querySelector('.far-sl');
            if (sl) sl.textContent = String(i + 1);
        });
    }

    function clearEmpty() {
        const empty = body.querySelector('.far-empty-row');
        if (empty) empty.remove();
    }

    function ensureEmpty() {
        if (lineRows().length) return;
        body.innerHTML = '<tr class="far-empty-row"><td colspan="8" style="text-align:center;color:#64748b;padding:16px;">No asset lines yet. Fill the entry row above and click + Add line.</td></tr>';
    }

    function clearEntry() {
        if (entryName) entryName.value = '';
        if (entryCategory) entryCategory.value = '';
        if (entryCost) entryCost.value = '';
        if (entrySalvage) entrySalvage.value = '0';
        if (entrySerial) entrySerial.value = '';
        if (entryCustodian) entryCustodian.value = '';
    }

    function addLine() {
        const name = String(entryName?.value || '').trim();
        const catId = String(entryCategory?.value || '').trim();
        const cost = Number(entryCost?.value || 0);
        const salvage = Number(entrySalvage?.value || 0);
        const serial = String(entrySerial?.value || '').trim();
        const custodian = String(entryCustodian?.value || '').trim();

        if (!name) {
            alert('Description is required.');
            entryName?.focus();
            return;
        }
        if (!catId) {
            alert('Category is required.');
            entryCategory?.focus();
            return;
        }
        if (!(cost > 0)) {
            alert('Cost must be greater than zero.');
            entryCost?.focus();
            return;
        }
        if (salvage < 0 || salvage >= cost) {
            alert('Salvage must be zero or less than cost.');
            entrySalvage?.focus();
            return;
        }

        clearEmpty();
        const tr = document.createElement('tr');
        tr.dataset.categoryId = catId;
        tr.dataset.name = name;
        tr.dataset.cost = String(cost);
        tr.dataset.salvage = String(salvage);
        tr.dataset.serial = serial;
        tr.dataset.custodian = custodian;
        tr.innerHTML = `
            <td class="far-sl"></td>
            <td class="far-name">${esc(name)}</td>
            <td class="far-cat-label">${esc(catLabel(catId))}</td>
            <td class="far-num far-cost">${money(cost)}</td>
            <td class="far-num far-salvage">${money(salvage)}</td>
            <td class="far-serial">${esc(serial)}</td>
            <td class="far-custodian">${esc(custodian)}</td>
            <td style="text-align:center;"><button type="button" class="im-link far-remove-line" title="Remove">×</button></td>
        `;
        body.appendChild(tr);
        clearEntry();
        syncTotals();
        entryName?.focus();
    }

    function buildHiddenFields() {
        if (!hidden) return;
        hidden.innerHTML = '';
        lineRows().forEach((tr) => {
            const fields = [
                ['line_name[]', tr.dataset.name || ''],
                ['line_category_id[]', tr.dataset.categoryId || ''],
                ['line_cost[]', tr.dataset.cost || '0'],
                ['line_salvage[]', tr.dataset.salvage || '0'],
                ['line_serial[]', tr.dataset.serial || ''],
                ['line_custodian[]', tr.dataset.custodian || ''],
            ];
            fields.forEach(([n, v]) => {
                const inp = document.createElement('input');
                inp.type = 'hidden';
                inp.name = n;
                inp.value = v;
                hidden.appendChild(inp);
            });
        });
    }

    if (btnAdd) btnAdd.addEventListener('click', addLine);

    if (form) {
        form.addEventListener('keydown', handleEnterNav);
    }

    if (body) {
        body.addEventListener('click', (e) => {
            const btn = e.target.closest('.far-remove-line');
            if (!btn) return;
            btn.closest('tr')?.remove();
            ensureEmpty();
            syncTotals();
        });
    }

    if (form) {
        let submitting = false;
        const lockSubmit = () => {
            if (submitting) return true;
            submitting = true;
            document.querySelectorAll('[form="faRegisterForm"], #faRegisterForm button[type="submit"]').forEach((btn) => {
                btn.disabled = true;
            });
            return false;
        };
        form.addEventListener('submit', (e) => {
            if (submitting) {
                e.preventDefault();
                return;
            }
            buildHiddenFields();
            if (!lineRows().length) {
                e.preventDefault();
                alert('Add at least one asset line.');
                return;
            }
            const submitter = e.submitter;
            if (submitter && submitter.name === 'save_action' && submitter.value === 'post') {
                const n = lineRows().length;
                const msg = n === 1
                    ? 'Save and post acquisition to GL for 1 asset?'
                    : `Save and post acquisition to GL for ${n} assets? All lines are saved in one transaction.`;
                if (!window.confirm(msg)) {
                    e.preventDefault();
                    return;
                }
            }
            lockSubmit();
        });
    }

    if (lookup && partyType && partyCode) {
        lookup.addEventListener('global-lookup:select', (e) => {
            const row = (e.detail && e.detail.row) || {};
            partyType.value = row.party_type || '';
            partyCode.value = row.party_code || '';
        });
        lookup.addEventListener('change', () => {
            const h = lookup.querySelector('.global-lookup__value, .odoo-lookup__value');
            if (h && !h.value) {
                partyType.value = '';
                partyCode.value = '';
            }
        });
    }

    syncTotals();
})();
