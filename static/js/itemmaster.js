// Item Master JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('itemMasterForm');
    const viewUrl = (form && form.dataset && form.dataset.viewUrl) ? form.dataset.viewUrl : '/itemmaster';
    const listUrl = (form && form.dataset && form.dataset.listUrl) ? form.dataset.listUrl : '';
    const nextCodeUrl = (form && form.dataset && form.dataset.nextCodeUrl) ? form.dataset.nextCodeUrl : '/itemmaster/next-code';
    const suggestBarcodeUrl = (form && form.dataset && form.dataset.suggestBarcodeUrl)
        ? form.dataset.suggestBarcodeUrl
        : '/itemmaster/api/suggest-barcode';
    const requireTargetDb = !!(form && form.dataset && form.dataset.requireTargetDb === '1');
    const fromItemRequestConvert = !!(form && form.dataset && form.dataset.fromItemRequest === '1');
    const isItemRequestMode = !!(form && form.dataset && form.dataset.itemRequestMode === '1');
    const accountsLocked = !!(form && form.dataset && form.dataset.accountsLocked === '1');
    const itemRequestRejectedUrl = (
        form && form.dataset && String(form.dataset.itemRequestRejectedUrl || '').trim()
    )
        ? String(form.dataset.itemRequestRejectedUrl).trim()
        : '';
    const defaultDbocode = (form && form.dataset && form.dataset.defaultDbocode) ? String(form.dataset.defaultDbocode) : '';
    const defaultBranch = (form && form.dataset && form.dataset.defaultBranch) ? String(form.dataset.defaultBranch) : '';
    const remapUrl = (form && form.dataset && form.dataset.hoRemapUrl) ? String(form.dataset.hoRemapUrl) : '';
    const deleteItemUrl = (form && form.dataset && form.dataset.hoDeleteItemUrl) ? String(form.dataset.hoDeleteItemUrl) : '';
    const arabicSuggestUrl = (form && form.dataset && form.dataset.arabicSuggestUrl) ? String(form.dataset.arabicSuggestUrl) : '/itemmaster/ai-arabic-name';
    const aiGeneralFillUrl = (form && form.dataset && form.dataset.aiGeneralFillUrl) ? String(form.dataset.aiGeneralFillUrl) : '/itemmaster/ai-general-fill';
    const aiBarcodeWebUrl = (form && form.dataset && form.dataset.aiBarcodeWebUrl) ? String(form.dataset.aiBarcodeWebUrl) : '/itemmaster/ai-barcode-web';
    const viewOnly = !!(form && form.dataset && form.dataset.viewOnly === '1');
    const itemActiveSwitch = document.getElementById('item_active');
    const itemActiveSwitchText = document.getElementById('itemActiveSwitchText');
    function refreshItemActiveSwitchText() {
        if (itemActiveSwitchText && itemActiveSwitch) {
            itemActiveSwitchText.textContent = itemActiveSwitch.checked ? 'Active' : 'Locked';
        }
    }
    if (itemActiveSwitch) {
        itemActiveSwitch.addEventListener('change', refreshItemActiveSwitchText);
        refreshItemActiveSwitchText();
    }
    const viewPathForNav = (function() {
        const raw = (form && form.dataset && form.dataset.viewUrl) ? String(form.dataset.viewUrl).trim() : '/itemmaster';
        try {
            return new URL(raw, window.location.origin).pathname;
        } catch (e) {
            return raw.split('?')[0] || '/itemmaster';
        }
    })();
    if (viewOnly && form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        });
    }
    const hoSourceLocation = (form && form.dataset && form.dataset.hoSourceLocation) ? String(form.dataset.hoSourceLocation) : '';
    const existingTargets = new Set(
        String((form && form.dataset && form.dataset.existingTargets) ? form.dataset.existingTargets : '')
            .split(',')
            .map((v) => String(v || '').trim())
            .filter((v) => !!v)
    );
    const hoTargetTenantChecks = () => Array.from(document.querySelectorAll('.ho-target-tenant-check'));
    const btnNew = document.getElementById('btnNew');
    const btnQuery = document.getElementById('btnQuery');
    const btnSave = document.getElementById('btnSave');
    const btnRemap = document.getElementById('btnRemap');
    const btnDeleteItem = document.getElementById('btnDeleteItem');
    const btnCancel = document.getElementById('btnCancel');
    const btnRejectItemRequest = document.getElementById('btnRejectItemRequest');
    const btnDelete = document.getElementById('btnDelete');
    const isNewInput = document.getElementById('isNew');
    const itemCodeInput = document.getElementById('item_code');
    const manufacturerIdInput = document.getElementById('manufacturer_id');
    const itemNameInput = document.getElementById('item_name');
    const descriptionInput = document.getElementById('description');
    const itemNameAraInput = document.getElementById('item_name_ara');
    const aiModeToggle = document.getElementById('ai_mode_toggle');
    const aiExplainSection = document.getElementById('aiExplainSection');
    const aiFetchDetails = document.getElementById('aiFetchDetails');
    const aiArabicExplainRow = document.getElementById('aiArabicExplainRow');
    const aiArabicPreview = document.getElementById('aiArabicPreview');
    const aiExplainTableWrap = document.getElementById('aiExplainTableWrap');
    const aiExplainTableBody = document.getElementById('aiExplainTableBody');
    const btnCopySuggestedData = document.getElementById('btnCopySuggestedData');
    const itemStatus = document.getElementById('itemStatus');
    let selectedVariantRow = null;
    let latestAiSuggestions = null;
    let variantsLoaded = !!document.querySelector('.alt-variant-row');
    let inventoryDetailsLoaded = !!document.querySelector('#storeInventoryBody tr:not(#storeInventoryEmptyRow), #binStockBody tr');
    const getIsNewMode = () => String(isNewInput?.value || '').toLowerCase() === 'true';
    const getSaveVerb = () => (getIsNewMode() ? 'Save' : 'Update');

    // Opened with item lookup / prefill (including GRN): we skip resetForNewItem(), so default GL must be applied here.
    const hasLookupParams = () => {
        try {
            const qs = new URLSearchParams(window.location.search || '');
            if ((qs.get('item_code') || '').trim()
                || (qs.get('manufacturer_id') || '').trim()
                || (qs.get('rawabicode') || '').trim()
                || (qs.get('temp_item_code') || '').trim()) {
                return true;
            }
            if ((qs.get('from_grn_ai') || '').trim()) return true;
            if ((qs.get('prefill_itemname') || '').trim()) return true;
            for (const k of qs.keys()) {
                if (String(k || '').toLowerCase().startsWith('prefill_')) return true;
            }
            return false;
        } catch (e) {
            return false;
        }
    };

    const applyGrnOrPrefillDefaultGlIfEmpty = () => {
        if (!form) return;
        if (!hasLookupParams() && String(form.dataset.grnPrefillAi || '') !== '1') return;
        if (isItemRequestMode || accountsLocked) return;
        if (!getIsNewMode()) return;
        if ((document.getElementById('sales_account')?.value || '').trim()) return;
        const setF = (id, v) => {
            const el = document.getElementById(id);
            if (el) el.value = v;
        };
        const showClr = (id) => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'block';
        };
        setF('sales_account_display', '4100 - Sales Revenue');
        setF('sales_account', '4100');
        showClr('salesAccountClear');
        setF('purchase_account_display', '5001 - Purchase Expense');
        setF('purchase_account', '5001');
        showClr('purchaseAccountClear');
        setF('inventory_account_display', '1300 - Inventory');
        setF('inventory_account', '1300');
        showClr('inventoryAccountClear');
        setF('cogs_account_display', '5100 - Cost of Goods Sold');
        setF('cogs_account', '5100');
        showClr('cogsAccountClear');
    };

    const categoryPricePctUrl =
        (form && form.dataset && form.dataset.categoryPricePctApi) || '';

    /** New item: from micro-category (FLAG='C') PRICEPERCENTAGE, set retail/wholesale/third = cost * (1 + pct/100). */
    function applyCategoryPriceMarkupFromCost() {
        if (!getIsNewMode() || isItemRequestMode) return;
        if (fromItemRequestConvert) return;
        if (!categoryPricePctUrl) return;
        const catEl = document.getElementById('category_code_hidden');
        const costEl = document.getElementById('cost_price');
        if (!catEl || !costEl) return;
        const cc = parseInt(String(catEl.value || '').trim(), 10);
        if (!Number.isFinite(cc) || cc <= 0) return;
        const cost = parseFloat(String(costEl.value || '').replace(/,/g, '.').trim());
        if (!Number.isFinite(cost) || cost < 0) return;
        const sep = categoryPricePctUrl.indexOf('?') >= 0 ? '&' : '?';
        const url = `${categoryPricePctUrl}${sep}code=${encodeURIComponent(cc)}`;
        fetch(url, { credentials: 'same-origin' })
            .then((r) => {
                if (!r.ok) return Promise.reject(new Error('HTTP ' + r.status));
                return r.json();
            })
            .then((d) => {
                if (!d || !d.success) return;
                const pct = parseFloat(String(d.pricepercentage != null ? d.pricepercentage : ''));
                if (!Number.isFinite(pct) || pct < 0) return;
                const mult = 1 + pct / 100;
                const sell = cost * mult;
                const f2 = (n) => (Math.round(n * 100) / 100).toFixed(2);
                const sp = f2(sell);
                const rp = document.getElementById('retail_price');
                const wp = document.getElementById('wholesale_price');
                const tp = document.getElementById('third_price');
                if (rp) rp.value = sp;
                if (wp) wp.value = sp;
                if (tp) tp.value = sp;
                const cpi = document.getElementById('cost_price');
                const rpi = document.getElementById('retail_price');
                if (cpi) cpi.dispatchEvent(new Event('input', { bubbles: true }));
                if (rpi) rpi.dispatchEvent(new Event('input', { bubbles: true }));
            })
            .catch(() => {});
    }

    const normalizeNoneLike = (value) => {
        if (value === null || value === undefined) return '';
        const txt = String(value).trim();
        if (!txt) return '';
        const low = txt.toLowerCase();
        return (low === 'none' || low === 'null' || low === 'undefined' || low === 'nan') ? '' : txt;
    };

    function resolveEditCodeLabelsInBackground() {
        if (!form || getIsNewMode()) return;
        if (String(form.dataset.codeLabelsReady || '') === '1') return;
        const url = String(form.dataset.codeLabelsUrl || '').trim();
        if (!url) return;
        const params = new URLSearchParams();
        const codeFields = {
            maincategory: 'main_category_code',
            departmentcode: 'department_code_hidden',
            categorycode: 'category_code_hidden',
            brandcode: 'brand_code_hidden',
            baseuom: 'base_uom_hidden',
            property: 'property_code',
            origin: 'origin_code',
            supcode: 'sup_code_hidden',
            sales_account: 'sales_account',
            purchase_account: 'purchase_account',
            inventory_account: 'inventory_account',
            cogs_account: 'cogs_account',
        };
        Object.keys(codeFields).forEach((paramName) => {
            const el = document.getElementById(codeFields[paramName]);
            const value = String(el?.value || '').trim();
            if (value && value !== '0') params.set(paramName, value);
        });
        if (!params.toString()) return;
        const sep = url.indexOf('?') >= 0 ? '&' : '?';
        fetch(`${url}${sep}${params.toString()}`, { credentials: 'same-origin' })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.success || !data.labels) return;
                const map = {
                    main_category: 'main_category',
                    department: 'department_code',
                    category: 'category_code',
                    brand: 'brand_code',
                    supplier: 'sup_code',
                    base_uom: 'base_uom',
                    property: 'property',
                    origin: 'origin',
                    sales_account: 'sales_account_display',
                    purchase_account: 'purchase_account_display',
                    inventory_account: 'inventory_account_display',
                    cogs_account: 'cogs_account_display',
                };
                Object.keys(map).forEach((labelKey) => {
                    const label = normalizeNoneLike(data.labels[labelKey]);
                    if (!label) return;
                    const input = document.getElementById(map[labelKey]);
                    if (!input) return;
                    input.value = label;
                });
            })
            .catch(() => {});
    }

    // Disable browser suggestion/autocomplete dropdowns on Item Master fields.
    if (form) {
        form.setAttribute('autocomplete', 'off');
        form.querySelectorAll('input, textarea, select').forEach((el) => {
            el.setAttribute('autocomplete', 'off');
        });
    }
    setTimeout(resolveEditCodeLabelsInBackground, 0);
    
    // View mode displays saved Item Master codes/labels directly; dependent lookup rows are only needed for editing.
    if (!viewOnly) {
        setTimeout(() => {
            const mainCategoryCode = document.getElementById('main_category_code')?.value;
            const departmentCode = document.getElementById('department_code_hidden')?.value;
            
            // When loading an item, use CODE values directly for filtering
            // Main Category CODE -> Filter Departments where MAINCATEGORY = CODE
            if (mainCategoryCode && mainCategoryCode !== '0') {
                updateDepartments(mainCategoryCode, true); // preserveSelection = true, pass CODE
            }
            
            // Department CODE -> Filter Categories where DEPARTMENTCODE = CODE
            if (departmentCode && departmentCode !== '0' && departmentCode !== '') {
                updateCategories(departmentCode, true); // preserveSelection = true, pass CODE
            }
        }, 500); // Increased timeout to ensure modals are populated
    }

    function currentItemCodeForLazyLoad() {
        return String(itemCodeInput?.value || '').trim();
    }

    const variantRowIsBase = (row) => !!(row && (row.dataset.mirrorBase === '1' || row.dataset.isBase === '1'));

    const readItemDescriptionForBaseVariant = () => String(document.getElementById('description')?.value || document.getElementById('item_name')?.value || '').trim();

    function renderLazyVariantRows(rows) {
        const tbody = document.getElementById('variantRowsBody') || document.querySelector('#tab-variant .scroll-table table tbody');
        if (!tbody) return;
        const data = Array.isArray(rows) ? rows : [];
        const baseUomCode = (document.getElementById('base_uom_hidden')?.value || '').trim().toUpperCase();
        const mainBarcode = ((manufacturerIdInput && manufacturerIdInput.value) ? manufacturerIdInput.value : (itemCodeInput?.value || '')).trim().toUpperCase();
        if (!data.length) {
            tbody.innerHTML = '<tr id="variantEmptyRow"><td colspan="12" class="muted">No alternate variants added.</td></tr>';
            variantsLoaded = true;
            seedDefaultMirrorVariantRow();
            return;
        }
        tbody.innerHTML = data.map((alt) => {
            const slno = escapeHtml(alt.slno ?? alt.SLNO ?? '');
            const desc = escapeHtml(alt.description ?? alt.DESCRIPTION ?? '');
            const barcode = escapeHtml(alt.manufacturerid ?? alt.MANUFACTURERID ?? '');
            const uom = escapeHtml(alt.alternateuomcode ?? alt.ALTERNATEUOMCODE ?? '');
            const factor = escapeHtml(alt.conversionfactor ?? alt.CONVERSIONFACTOR ?? '0');
            const cost = escapeHtml(alt.costprice ?? alt.COSTPRICE ?? '0');
            const wholesale = escapeHtml(alt.wholesaleprice ?? alt.WHOLESALEPRICE ?? '0');
            const retail = escapeHtml(alt.retailprice ?? alt.RETAILPRICE ?? '0');
            const third = escapeHtml(alt.thirdprice ?? alt.THIRDPRICE ?? '0');
            const branch = escapeHtml(alt.branchprice ?? alt.BRANCHPRICE ?? '0');
            const isBaseFlag = String(alt.is_base ?? alt.IS_BASE ?? '').trim().toUpperCase() === 'Y';
            const uomUp = String(alt.alternateuomcode ?? alt.ALTERNATEUOMCODE ?? '').trim().toUpperCase();
            const bcUp = String(alt.manufacturerid ?? alt.MANUFACTURERID ?? '').trim().toUpperCase();
            const facNum = parseFloat(String(alt.conversionfactor ?? alt.CONVERSIONFACTOR ?? '0'));
            const isBase = isBaseFlag || (baseUomCode && uomUp === baseUomCode && Math.abs(facNum - 1) < 1e-6 && mainBarcode && bcUp === mainBarcode);
            const baseAttrs = isBase ? ' data-mirror-base="1" data-is-base="1" class="alt-variant-row alt-variant-row--base"' : ' class="alt-variant-row"';
            const baseCell = isBase
                ? '<span class="status-badge status-badge--active" title="Linked to Item Master">Base</span>'
                : '-';
            const actionCell = isBase
                ? '<span class="muted" style="font-size:12px;" title="Edit Base UOM / barcode / prices on General and Pricing tabs">Linked</span>'
                : '<button type="button" class="im-link alt-variant-edit">Edit</button>';
            return `<tr${baseAttrs} data-slno="${slno}" data-description="${desc}" data-barcode="${barcode}" data-uom="${uom}" data-factor="${factor}" data-cost="${cost}" data-wholesale="${wholesale}" data-retail="${retail}" data-third="${third}" data-branch="${branch}">
                <td>${baseCell}</td><td>${slno || '-'}</td><td>${desc || '-'}</td><td>${barcode || '-'}</td><td>${uom || '-'}</td><td>${factor || '0'}</td><td>${cost || '0'}</td><td>${wholesale || '0'}</td><td>${retail || '0'}</td><td>${third || '0'}</td><td>${branch || '0'}</td><td>${actionCell}</td>
            </tr>`;
        }).join('');
        tbody.querySelectorAll('.alt-variant-row').forEach((row) => {
            const btn = row.querySelector('.alt-variant-edit');
            if (btn) btn.addEventListener('click', () => loadVariantRowToEditor(row));
        });
        variantsLoaded = true;
        syncMirrorVariantRowFromItemmaster();
        seedDefaultMirrorVariantRow();
    }

    function ensureVariantsLoaded() {
        if (variantsLoaded || getIsNewMode()) return Promise.resolve();
        const url = form?.dataset?.variantsUrl || '';
        const itemCode = currentItemCodeForLazyLoad();
        if (!url || !itemCode) return Promise.resolve();
        const tbody = document.getElementById('variantRowsBody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="12" class="muted">Loading variants...</td></tr>';
        return fetch(`${url}?item_code=${encodeURIComponent(itemCode)}`, { credentials: 'same-origin' })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.success) throw new Error((data && data.error) || 'Failed to load variants');
                renderLazyVariantRows(data.rows || []);
            })
            .catch((err) => {
                if (tbody) tbody.innerHTML = `<tr id="variantEmptyRow"><td colspan="12" class="muted">${escapeHtml(err.message || err)}</td></tr>`;
            });
    }

    function renderStoreInventoryRows(rows) {
        const tbody = document.getElementById('storeInventoryBody');
        if (!tbody) return;
        const data = Array.isArray(rows) ? rows : [];
        if (!data.length) {
            tbody.innerHTML = '<tr id="storeInventoryEmptyRow"><td colspan="4" class="muted">No store inventory rows found.</td></tr>';
            return;
        }
        tbody.innerHTML = data.map((row) => {
            const code = escapeHtml(row.code ?? '');
            const store = escapeHtml(row.store ?? '');
            const desc = escapeHtml(row.description ?? '');
            const stock = escapeHtml(row.stock ?? 0);
            return `<tr><td>${code || '-'}</td><td>${store || '-'}</td><td>${desc || '-'}</td><td style="text-align:right;">${stock || 0}</td></tr>`;
        }).join('');
    }

    function renderBinStockRows(rows) {
        const tbody = document.getElementById('binStockBody');
        if (!tbody) return;
        const data = Array.isArray(rows) ? rows : [];
        if (!data.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="muted">No BIN_STOCK lines for this item at this site.</td></tr>';
            return;
        }
        tbody.innerHTML = data.map((row) => {
            const bin = escapeHtml(row.bin_code ?? '');
            const item = escapeHtml(row.itemcode ?? '');
            const name = escapeHtml(row.itemname ?? '');
            const qty = escapeHtml(row.qty ?? 0);
            return `<tr><td>${bin || '-'}</td><td>${item || '-'}</td><td>${name || '-'}</td><td style="text-align:right;">${qty || 0}</td></tr>`;
        }).join('');
    }

    function ensureInventoryDetailsLoaded() {
        if (inventoryDetailsLoaded || getIsNewMode()) return Promise.resolve();
        const url = form?.dataset?.inventoryDetailsUrl || '';
        const itemCode = currentItemCodeForLazyLoad();
        if (!url || !itemCode) return Promise.resolve();
        const storeBody = document.getElementById('storeInventoryBody');
        const binBody = document.getElementById('binStockBody');
        if (storeBody) storeBody.innerHTML = '<tr><td colspan="4" class="muted">Loading store inventory...</td></tr>';
        if (binBody) binBody.innerHTML = '<tr><td colspan="4" class="muted">Loading bin quantities...</td></tr>';
        return fetch(`${url}?item_code=${encodeURIComponent(itemCode)}`, { credentials: 'same-origin' })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.success) throw new Error((data && data.error) || 'Failed to load inventory');
                renderStoreInventoryRows(data.store_inventory_rows || []);
                renderBinStockRows(data.bin_stock_rows || []);
                inventoryDetailsLoaded = true;
            })
            .catch((err) => {
                if (storeBody) storeBody.innerHTML = `<tr id="storeInventoryEmptyRow"><td colspan="4" class="muted">${escapeHtml(err.message || err)}</td></tr>`;
                if (binBody) binBody.innerHTML = `<tr><td colspan="4" class="muted">${escapeHtml(err.message || err)}</td></tr>`;
            });
    }

    function loadLazyTabData(targetTab) {
        if (targetTab === 'variant') return ensureVariantsLoaded();
        if (targetTab === 'inventory') return ensureInventoryDetailsLoaded();
        return Promise.resolve();
    }

    // Sections are stacked (no tab bar); optional legacy tabs still supported if present in markup.
    const tabs = document.querySelectorAll('.itemmaster-tabs .tab');
    const tabContents = document.querySelectorAll('.tab-content');
    let itemmasterActiveSection = 'general';

    tabs.forEach((tab) => {
        tab.addEventListener('click', function() {
            const targetTab = this.dataset.tab;
            tabs.forEach((t) => t.classList.remove('tab--active'));
            tabContents.forEach((tc) => tc.classList.remove('tab-content--active'));
            this.classList.add('tab--active');
            const targetContent = document.getElementById(`tab-${targetTab}`);
            if (targetContent) targetContent.classList.add('tab-content--active');
            loadLazyTabData(targetTab);
            itemmasterActiveSection = targetTab || itemmasterActiveSection;
            targetContent?.scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'nearest' });
        });
    });

    /** @param {string} targetTab @param {{ scroll?: boolean }} [opts] set scroll:false when focus should not jump (e.g. barcode field). */
    const setActiveTabByName = (targetTab, opts = {}) => {
        if (!targetTab) return;
        const allowScroll = opts.scroll !== false;
        itemmasterActiveSection = targetTab;
        const targetContent = document.getElementById(`tab-${targetTab}`);
        if (tabs.length) {
            tabs.forEach((t) => t.classList.remove('tab--active'));
            tabContents.forEach((tc) => tc.classList.remove('tab-content--active'));
            const targetButton = document.querySelector(`.itemmaster-tabs .tab[data-tab="${targetTab}"]`);
            if (targetButton) targetButton.classList.add('tab--active');
            if (targetContent) targetContent.classList.add('tab-content--active');
        }
        if (allowScroll && targetContent) {
            targetContent.scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'nearest' });
        }
        loadLazyTabData(targetTab);
    };

    const getItemmasterTabOrder = () => {
        const fromDom = Array.from(document.querySelectorAll('.itemmaster-tabs .tab[data-tab]'))
            .map((b) => b.getAttribute('data-tab'))
            .filter(Boolean);
        if (fromDom.length) return fromDom;
        return ['general', 'pricing', 'variant', 'inventory', 'additional', 'accounts'];
    };

    if (form) {
        form.addEventListener('focusin', (e) => {
            const t = e.target;
            if (!t || !t.closest) return;
            const panel = t.closest('.im-form-panel[id^="tab-"]');
            if (panel && panel.id && panel.id.startsWith('tab-')) {
                itemmasterActiveSection = panel.id.slice(4);
            }
        });
    }

    const shouldBlockArrowTabNav = (el) => {
        if (!el || el.nodeType !== 1) return false;
        if (el.isContentEditable) return true;
        const tag = String(el.tagName || '').toUpperCase();
        if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
        if (tag !== 'INPUT') return false;
        const type = String(el.getAttribute('type') || 'text').toLowerCase();
        return ['text', 'search', 'password', 'email', 'url', 'tel', 'number', 'date', 'time', 'month', 'week', 'datetime-local', 'range', 'color'].includes(type);
    };

    document.addEventListener('keydown', (e) => {
        const k = e.key || '';
        if (k !== 'ArrowLeft' && k !== 'ArrowRight') return;
        if (e.defaultPrevented) return;
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        if (document.querySelector('.modal:not(.hidden)')) return;
        if (shouldBlockArrowTabNav(e.target)) return;
        const order = getItemmasterTabOrder();
        if (order.length < 2) return;
        const idx = order.indexOf(itemmasterActiveSection);
        const curIdx = idx >= 0 ? idx : 0;
        const nextIdx = k === 'ArrowRight' ? (curIdx + 1) % order.length : (curIdx - 1 + order.length) % order.length;
        e.preventDefault();
        setActiveTabByName(order[nextIdx]);
    });

    if (!getIsNewMode()) {
        const variantSection = document.getElementById('tab-variant');
        if (variantSection && 'IntersectionObserver' in window) {
            const variantObserver = new IntersectionObserver((entries) => {
                if (!entries.some((entry) => entry.isIntersecting)) return;
                variantObserver.disconnect();
                ensureVariantsLoaded();
            }, { rootMargin: '160px 0px' });
            variantObserver.observe(variantSection);
        }
        variantSection?.addEventListener('focusin', () => ensureVariantsLoaded(), { once: true });
        variantSection?.addEventListener('pointerenter', () => ensureVariantsLoaded(), { once: true });

        const inventorySection = document.getElementById('tab-inventory');
        if (inventorySection && 'IntersectionObserver' in window) {
            const inventoryObserver = new IntersectionObserver((entries) => {
                if (!entries.some((entry) => entry.isIntersecting)) return;
                inventoryObserver.disconnect();
                ensureInventoryDetailsLoaded();
            }, { rootMargin: '40px 0px' });
            inventoryObserver.observe(inventorySection);
        }
        inventorySection?.addEventListener('focusin', () => ensureInventoryDetailsLoaded(), { once: true });
        inventorySection?.addEventListener('pointerenter', () => ensureInventoryDetailsLoaded(), { once: true });
    }

    const focusBarcodeField = () => {
        if (!manufacturerIdInput || manufacturerIdInput.disabled) return;
        setActiveTabByName('general', { scroll: false });
        manufacturerIdInput.focus({ preventScroll: true });
        manufacturerIdInput.select?.();
    };
    const updateSaveButtonLabel = () => {
        if (!btnSave) return;
        const verb = getSaveVerb();
        btnSave.textContent = verb;
    };
    updateSaveButtonLabel();

    const fetchArabicSuggestion = async () => {
        if (!itemNameInput) return '';
        const itemName = String(itemNameInput.value || '').trim();
        if (!itemName) {
            return '';
        }
        try {
            const response = await fetch(arabicSuggestUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ item_name: itemName }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                return '';
            }
            return String(data.arabic_name || '').trim();
        } catch (err) {
            return '';
        }
    };

    const AI_MODE_LS_KEY = 'itemmaster_ai_mode_enabled';
    const setAiFetchDetails = (message = '', isError = false) => {
        if (!aiFetchDetails) return;
        const text = String(message || '').trim();
        aiFetchDetails.textContent = text;
        if (aiExplainSection) {
            aiExplainSection.classList.toggle('im-ai-explain--error', !!isError);
        }
    };
    const escapeHtml = (s) => String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    const renderAiExplainTable = (rows = []) => {
        if (!aiExplainTableWrap || !aiExplainTableBody) return;
        if (!Array.isArray(rows) || !rows.length) {
            aiExplainTableBody.innerHTML = '';
            aiExplainTableWrap.style.display = 'none';
            return;
        }
        const normalized = rows.map((r) => ({
            label: escapeHtml(r.label || ''),
            value: escapeHtml(r.value || ''),
        }));
        const chunks = [];
        for (let i = 0; i < normalized.length; i += 10) {
            chunks.push(normalized.slice(i, i + 10));
        }
        aiExplainTableBody.innerHTML = chunks.map((group) => {
            const tds = group.map((cell) =>
                `<td><span class="im-ai-cell__label">${cell.label}</span><span class="im-ai-cell__value">${cell.value}</span></td>`
            );
            while (tds.length < 10) {
                tds.push('<td></td>');
            }
            return `<tr>${tds.join('')}</tr>`;
        }).join('');
        aiExplainTableWrap.style.display = 'block';
    };
    const setAiArabicPreview = (arabicText = '', sourceLabel = '') => {
        const txt = String(arabicText || '').trim();
        if (!aiArabicExplainRow || !aiArabicPreview) return;
        if (!txt) {
            aiArabicExplainRow.style.display = 'none';
            aiArabicPreview.textContent = '';
            return;
        }
        aiArabicExplainRow.style.display = 'flex';
        aiArabicPreview.textContent = sourceLabel ? `${txt} (${sourceLabel}, auto-filled)` : txt;
    };
    const toggleCopySuggestedButton = (visible) => {
        if (!btnCopySuggestedData) return;
        btnCopySuggestedData.style.display = visible ? 'inline-block' : 'none';
    };
    /** AI Explain panel is only visible while AI Mode toggle is ON (hidden in view-only / no toggle). */
    const syncAiExplainSectionVisibility = () => {
        if (!aiExplainSection) return;
        const show = !!(aiModeToggle && aiModeToggle.checked);
        aiExplainSection.classList.toggle('im-ai-explain--active', show);
    };
    const normalizeLookupCode = (code) => {
        const c = normalizeNoneLike(code);
        if (!c || c === '0') return '';
        const n = Number(c);
        if (Number.isFinite(n) && Math.trunc(n) === n) return String(Math.trunc(n));
        return c;
    };
    const lookupCodesMatch = (a, b) => normalizeLookupCode(a) === normalizeLookupCode(b);
    const formatCodeFromTable = (code, tableId, codeOnly = false) => {
        const c = normalizeLookupCode(code);
        if (!c) return '';
        const table = document.getElementById(tableId);
        if (!table) return c;
        const row = Array.from(table.querySelectorAll('tbody tr')).find((r) => lookupCodesMatch(r.dataset.code, c));
        if (!row) return c;
        const name = String(row.dataset.name || '').trim();
        return codeOnly ? c : (name ? `${c} - ${name}` : c);
    };
    const formatPopupDisplay = (code, tableId, apiDisplay, codeOnly = false) => {
        const c = normalizeLookupCode(code);
        if (!c) return '';
        const label = String(apiDisplay || '').trim();
        if (label && !codeOnly) return label;
        return formatCodeFromTable(c, tableId, codeOnly);
    };
    const formatWarehouseDisplayFromTable = (warehouseId, tableId) => {
        const c = String(warehouseId ?? '').trim();
        if (!c) return '';
        const table = document.getElementById(tableId);
        if (!table) return c;
        const row = Array.from(table.querySelectorAll('tbody tr')).find((r) => String(r.dataset.code || '').trim() === c);
        if (!row) return c;
        const whCode = String(row.dataset.whCode || '').trim();
        const name = String(row.dataset.name || '').trim();
        if (whCode && name) return `${whCode} — ${name}`;
        if (whCode) return whCode;
        if (name) return `${c} — ${name}`;
        return c;
    };
    const setPopupByCode = (inputId, hiddenId, clearId, code, modalTableId, codeOnly = false, displayOverride = '') => {
        const input = document.getElementById(inputId);
        const hidden = document.getElementById(hiddenId);
        const clear = document.getElementById(clearId);
        const c = normalizeLookupCode(code);
        if (!input || !hidden) return;
        if (!c) {
            hidden.value = hiddenId === 'main_category_code' ? '0' : '';
            input.value = '';
            if (clear) clear.style.display = 'none';
            return;
        }
        hidden.value = c;
        input.value = formatPopupDisplay(c, modalTableId, displayOverride, codeOnly);
        if (clear) clear.style.display = 'block';
    };

    /** For Copy Data: true if this text/number input is still empty (AI may fill). */
    const isTextFieldEmptyForCopy = (el) => !el || String(el.value ?? '').trim() === '';
    /** For Copy Data: true if hidden popup has no user selection (0 / empty = empty). */
    const isPopupHiddenEmptyForCopy = (hiddenId) => {
        const h = document.getElementById(hiddenId);
        if (!h) return true;
        const v = String(h.value ?? '').trim();
        if (!v) return true;
        if (v === '0' && [
            'main_category_code', 'category_code_hidden', 'brand_code_hidden',
            'property_code', 'origin_code', 'sup_code_hidden',
        ].includes(hiddenId)) return true;
        return false;
    };

    if (aiModeToggle) {
        aiModeToggle.checked = localStorage.getItem(AI_MODE_LS_KEY) === '1';
        if (aiModeToggle.checked) {
            setAiFetchDetails('AI Mode is ON. Barcode + Enter: fetch product from web. Item name + Enter: match similar items.');
        } else {
            setAiFetchDetails('AI Mode is OFF.');
        }
        syncAiExplainSectionVisibility();
        aiModeToggle.addEventListener('change', () => {
            localStorage.setItem(AI_MODE_LS_KEY, aiModeToggle.checked ? '1' : '0');
            if (aiModeToggle.checked) {
                setAiFetchDetails('AI Mode is ON. Barcode + Enter: fetch product from web. Item name + Enter: match similar items.');
            } else {
                setAiFetchDetails('AI Mode is OFF.');
                setAiArabicPreview('');
                renderAiExplainTable([]);
                latestAiSuggestions = null;
                toggleCopySuggestedButton(false);
            }
            syncAiExplainSectionVisibility();
        });
    } else {
        syncAiExplainSectionVisibility();
    }

    if (btnCopySuggestedData) {
        btnCopySuggestedData.addEventListener('keydown', (e) => {
            if ((e.key || '') !== 'Enter') return;
            e.preventDefault();
            btnCopySuggestedData.click();
        });
        btnCopySuggestedData.addEventListener('click', async () => {
            const pack = latestAiSuggestions || {};
            const g = pack.general || {};
            const a = pack.additional || {};
            if (!Object.keys(g).length && !Object.keys(a).length) {
                alert('No AI suggested data available to copy.');
                return;
            }
            if (descriptionInput && String(g.description || '').trim() && isTextFieldEmptyForCopy(descriptionInput)) {
                descriptionInput.value = String(g.description || '').trim();
            }
            const mainCategoryCode = normalizeLookupCode(g.main_category);
            if (mainCategoryCode && isPopupHiddenEmptyForCopy('main_category_code')) {
                setPopupByCode('main_category', 'main_category_code', 'mainCategoryClear', mainCategoryCode, 'mainCategoryModalTable', false, g.main_category_display);
                await updateDepartments(mainCategoryCode, true);
            }
            const deptCode = normalizeLookupCode(g.department_code);
            if (deptCode && isPopupHiddenEmptyForCopy('department_code_hidden')) {
                setPopupByCode('department_code', 'department_code_hidden', 'departmentClear', deptCode, 'departmentModalTable', false, g.department_display);
                await updateCategories(deptCode, true);
            }
            const categoryCode = normalizeLookupCode(g.category_code);
            if (categoryCode && isPopupHiddenEmptyForCopy('category_code_hidden')) {
                setPopupByCode('category_code', 'category_code_hidden', 'categoryClear', categoryCode, 'categoryModalTable', false, g.category_display);
            }
            const brandCode = normalizeLookupCode(g.brand_code);
            if (brandCode && isPopupHiddenEmptyForCopy('brand_code_hidden')) {
                setPopupByCode('brand_code', 'brand_code_hidden', 'brandClear', brandCode, 'brandModalTable', false, g.brand_display);
            }
            const supplierCode = normalizeLookupCode(g.sup_code);
            if (supplierCode && isPopupHiddenEmptyForCopy('sup_code_hidden')) {
                setPopupByCode('sup_code', 'sup_code_hidden', 'supplierClear', supplierCode, 'supplierModalTable', false, g.supplier_display);
            }
            const baseUomCode = String(g.base_uom || '').trim();
            if (baseUomCode && isPopupHiddenEmptyForCopy('base_uom_hidden')) {
                setPopupByCode('base_uom', 'base_uom_hidden', 'baseUomClear', baseUomCode, 'baseUomModalTable');
            }
            if (!isItemRequestMode) {
                const whId = String(g.default_warehouse_id ?? '').trim();
                if (whId) {
                    const whHidden = document.getElementById('default_warehouse_id');
                    const whVal = String(whHidden && whHidden.value || '').trim();
                    const userPickedWh = !!whVal;
                    if (!userPickedWh) {
                        setPopupByCode('default_warehouse_display', 'default_warehouse_id', 'defaultWarehouseClear', whId, 'storeModalTable');
                        const whDisplay = document.getElementById('default_warehouse_display');
                        if (whDisplay) whDisplay.value = formatWarehouseDisplayFromTable(whId, 'storeModalTable');
                    }
                }
            }
            const rebateInput = document.getElementById('rebate');
            const packingInput = document.getElementById('packing');
            const ministryFactorInput = document.getElementById('ministry_factor');
            const propertyCodeVal = String(a.property || '').trim();
            if (propertyCodeVal && propertyCodeVal !== '0' && isPopupHiddenEmptyForCopy('property_code')) {
                setPopupByCode('property', 'property_code', 'propertyClear', propertyCodeVal, 'propertyModalTable');
            }
            const originCodeVal = String(a.origin || '').trim();
            if (originCodeVal && originCodeVal !== '0' && isPopupHiddenEmptyForCopy('origin_code')) {
                setPopupByCode('origin', 'origin_code', 'originClear', originCodeVal, 'originModalTable');
            }
            if (rebateInput && String(a.rebate ?? '').trim() !== '' && isTextFieldEmptyForCopy(rebateInput)) {
                rebateInput.value = String(a.rebate ?? '').trim();
            }
            if (packingInput && String(a.packing ?? '').trim() !== '' && isTextFieldEmptyForCopy(packingInput)) {
                packingInput.value = String(a.packing ?? '').trim();
            }
            if (ministryFactorInput && String(a.ministry_factor ?? '').trim() !== '' && isTextFieldEmptyForCopy(ministryFactorInput)) {
                ministryFactorInput.value = String(a.ministry_factor ?? '').trim();
            }
            const colorCodeVal = String(a.color_code || '').trim();
            if (colorCodeVal && colorCodeVal !== '0' && isPopupHiddenEmptyForCopy('color_code_hidden')) {
                const colorHidden = document.getElementById('color_code_hidden');
                if (colorHidden) colorHidden.value = colorCodeVal;
            }
            const ministryUnitVal = String(a.ministry_unit || '').trim();
            if (ministryUnitVal && isPopupHiddenEmptyForCopy('ministry_unit')) {
                const mu = document.getElementById('ministry_unit');
                if (mu) mu.value = ministryUnitVal;
            }
            const brandInput = document.getElementById('brand_code');
            if (brandInput) {
                setActiveTabByName('general');
                brandInput.focus();
                brandInput.select?.();
            }
            // GRN prefill usually has cost; copy may set micro-category — apply CATEGORY FLAG='C' PRICEPERCENTAGE to selling prices.
            setTimeout(() => applyCategoryPriceMarkupFromCost(), 0);
        });
    }

    const fillFromWebBarcode = async () => {
        if (!aiModeToggle || !aiModeToggle.checked || !manufacturerIdInput) return;
        const barcode = String(manufacturerIdInput.value || '').trim();
        if (!barcode) return;
        if (!getIsNewMode() || viewOnly) {
            setAiFetchDetails('Web barcode lookup works in New item mode only.', true);
            return;
        }
        const prevLabel = aiModeToggle.title || '';
        try {
            aiModeToggle.disabled = true;
            aiModeToggle.title = 'Looking up barcode…';
            setAiFetchDetails('Looking up product on the web…');
            renderAiExplainTable([]);
            toggleCopySuggestedButton(false);
            const response = await fetch(aiBarcodeWebUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ barcode }),
            });
            let data = {};
            try {
                data = await response.json();
            } catch (parseErr) {
                data = {};
            }
            if (!response.ok) {
                const hint = data.hint ? ' ' + data.hint : '';
                throw new Error(
                    (data.error || data.message || 'Web lookup failed')
                    + ` (HTTP ${response.status}).${hint}`
                );
            }
            if (!data.success) {
                throw new Error((data.error || data.message || 'Web lookup failed') + (data.hint ? ' ' + data.hint : ''));
            }
            if (!data.found || !data.product) {
                if (data.already_exists) {
                    const ic0 = String(data.item_code || '').trim();
                    const nm0 = String(data.item_name || '').trim();
                    setAiFetchDetails(
                        ic0
                            ? `Barcode in Item Master: ${ic0}${nm0 ? ': ' + nm0 : ''} (restart app to load full details).`
                            : 'Barcode already exists in Item Master.',
                        true,
                    );
                    return;
                }
                setAiFetchDetails(String(data.message || 'No product found on the web for this barcode.'), true);
                return;
            }
            const p = data.product || {};
            const g = data.general || {};
            const webName = String(p.item_name || '').trim();
            const webDesc = String(p.description || '').trim();
            if (itemNameInput && webName && isTextFieldEmptyForCopy(itemNameInput)) {
                itemNameInput.value = webName.toUpperCase();
            }
            if (descriptionInput && webDesc && isTextFieldEmptyForCopy(descriptionInput)) {
                descriptionInput.value = webDesc;
            } else if (descriptionInput && itemNameInput && isTextFieldEmptyForCopy(descriptionInput)) {
                descriptionInput.value = String(itemNameInput.value || '').trim();
            }
            const araFromMaster = String(p.item_name_ara || g.item_name_ara || '').trim();
            let suggestedArabic = araFromMaster;
            if (!suggestedArabic) {
                suggestedArabic = await fetchArabicSuggestion();
            }
            if (itemNameAraInput && suggestedArabic && isTextFieldEmptyForCopy(itemNameAraInput)) {
                itemNameAraInput.value = suggestedArabic;
            }
            setAiArabicPreview(suggestedArabic, suggestedArabic ? (araFromMaster ? 'from Item Master' : 'from item name') : '');
            const src = String(data.source || p.source || 'web');
            renderAiExplainTable([
                { label: 'Barcode', value: String(p.barcode || barcode) },
                { label: 'Product', value: webName || '—' },
                { label: 'Item code', value: data.already_in_master ? String(data.item_code || '—') : '—' },
                { label: 'Source', value: src },
            ]);
            if (data.already_in_master) {
                latestAiSuggestions = g && Object.keys(g).length ? { general: g, additional: {} } : null;
                toggleCopySuggestedButton(!!latestAiSuggestions);
                if (latestAiSuggestions && btnCopySuggestedData) {
                    btnCopySuggestedData.click();
                }
                setAiFetchDetails(String(data.message || 'Loaded from Item Master.'));
                return;
            }
            setAiFetchDetails(`Loaded from ${src}. Matching similar items in your database…`);
            if (itemNameInput && String(itemNameInput.value || '').trim()) {
                await fillGeneralFromAiTemplate();
            } else if (itemNameInput) {
                setActiveTabByName('general');
                itemNameInput.focus();
            }
        } catch (err) {
            setAiFetchDetails((err && err.message) ? err.message : 'Web barcode lookup failed', true);
        } finally {
            if (aiModeToggle) {
                aiModeToggle.disabled = false;
                aiModeToggle.title = prevLabel;
            }
        }
    };

    const fillGeneralFromAiTemplate = async () => {
        if (!aiModeToggle || !aiModeToggle.checked || !itemNameInput) return;
        const itemName = String(itemNameInput.value || '').trim();
        if (!itemName) return;
        const isNew = String(isNewInput?.value || '').toLowerCase() === 'true';
        if (!isNew) {
            setAiFetchDetails('AI Mode works in New item mode only.', true);
            return;
        }

        const prevLabel = aiModeToggle.title || '';
        try {
            aiModeToggle.disabled = true;
            aiModeToggle.title = 'Loading...';
            const response = await fetch(aiGeneralFillUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ item_name: itemName }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.success) {
                throw new Error((data && (data.error || data.message)) || `AI fill failed (HTTP ${response.status})`);
            }
            const gFound = !!(data.found && data.general);
            const g = gFound ? data.general : {};
            const templateArabic = String(g.item_name_ara || '').trim();
            const suggestedArabic = await fetchArabicSuggestion();
            const arabicCandidate = suggestedArabic || templateArabic;
            const arabicSource = suggestedArabic
                ? 'from item name'
                : (templateArabic ? 'from matched item' : '');
            if (itemNameAraInput && arabicCandidate) {
                itemNameAraInput.value = arabicCandidate;
            }
            setAiArabicPreview(arabicCandidate, arabicSource);

            if (!data.found || !data.general) {
                const scoreRaw = Number(data.match_score);
                const scorePct = Number.isFinite(scoreRaw) ? `${Math.round(scoreRaw * 100)}%` : '';
                const wm = Number(data.word_match_count ?? 0);
                const iw = Number(data.input_word_count ?? 0);
                const detail = data.message ? String(data.message) : `No similar previous item found for "${itemName}".`;
                const suffix = scorePct ? ` (best: ${scorePct}${iw > 0 ? `, words ${wm}/${iw}` : ''})` : '';
                setAiFetchDetails(`AI Mode: ${detail}${suffix}`, true);
                renderAiExplainTable([]);
                latestAiSuggestions = null;
                toggleCopySuggestedButton(false);
                if (itemNameAraInput) {
                    setActiveTabByName('general');
                    itemNameAraInput.focus();
                    itemNameAraInput.select?.();
                }
                return;
            }
            const a = data.additional || {};
            latestAiSuggestions = { general: g, additional: a };
            toggleCopySuggestedButton(true);
            const suggestedRows = [];
            const addSuggestion = (label, value) => {
                const v = normalizeNoneLike(value);
                if (!v || v === '0') return;
                suggestedRows.push({ label, value: v });
            };
            addSuggestion('Description', g.description);
            addSuggestion('Main Category', formatPopupDisplay(g.main_category, 'mainCategoryModalTable', g.main_category_display));
            addSuggestion('Category', formatPopupDisplay(g.department_code, 'departmentModalTable', g.department_display));
            addSuggestion('Micro Category', formatPopupDisplay(g.category_code, 'categoryModalTable', g.category_display));
            addSuggestion('Brand', formatPopupDisplay(g.brand_code, 'brandModalTable', g.brand_display));
            addSuggestion('Supplier', formatPopupDisplay(g.sup_code, 'supplierModalTable', g.supplier_display));
            addSuggestion('Base UOM', formatCodeFromTable(g.base_uom, 'baseUomModalTable'));
            if (!isItemRequestMode) addSuggestion('Default warehouse', formatWarehouseDisplayFromTable(g.default_warehouse_id, 'storeModalTable'));
            addSuggestion('Property', formatCodeFromTable(a.property, 'propertyModalTable'));
            addSuggestion('Origin', formatCodeFromTable(a.origin, 'originModalTable'));
            addSuggestion('Packing', a.packing);

            const matchedCode = String(data.matched_item_code ?? '').trim();
            const matchedName = String(data.matched_item_name ?? '').trim();
            const scoreRaw = Number(data.match_score);
            const scorePct = Number.isFinite(scoreRaw) ? `${Math.round(scoreRaw * 100)}%` : '-';
            const wordMatchCount = Number(data.word_match_count ?? 0);
            const inputWordCount = Number(data.input_word_count ?? 0);
            const matchedWords = Array.isArray(data.matched_words) ? data.matched_words.filter(Boolean) : [];
            const wordPart = (inputWordCount > 0)
                ? `Word match: ${wordMatchCount}/${inputWordCount}`
                : 'Word match: -';
            const wordsText = matchedWords.length ? matchedWords.join(', ') : '-';
            const tableRows = [
                { label: 'Matched Item Code', value: matchedCode || '-' },
                { label: 'Matched Item Name', value: matchedName || '-' },
                { label: 'Word Match', value: wordPart.replace('Word match: ', '') },
                { label: 'Match Score', value: scorePct },
                { label: 'Matched Words', value: wordsText },
                { label: 'Arabic Fill', value: 'Auto-filled to General tab' },
                ...suggestedRows,
            ];
            renderAiExplainTable(tableRows);
            setAiFetchDetails('');
            if (btnCopySuggestedData && btnCopySuggestedData.style.display !== 'none') {
                btnCopySuggestedData.focus();
            }
        } catch (err) {
            setAiFetchDetails((err && err.message) ? err.message : 'AI mode fill failed', true);
            renderAiExplainTable([]);
            latestAiSuggestions = null;
            toggleCopySuggestedButton(false);
            alert((err && err.message) ? err.message : 'AI mode fill failed');
        } finally {
            if (aiModeToggle) {
                aiModeToggle.disabled = false;
                aiModeToggle.title = prevLabel;
            }
            applyGrnOrPrefillDefaultGlIfEmpty();
            applyCategoryPriceMarkupFromCost();
        }
    };

    // Opened from GRN "Create item" with from_grn_ai=1: server pre-filled; enable AI mode and run similar-item match.
    const grnPrefillAi = !!(form && form.dataset && String(form.dataset.grnPrefillAi || '') === '1');
    if (grnPrefillAi && aiModeToggle && itemNameInput && String(itemNameInput.value || '').trim()) {
        aiModeToggle.checked = true;
        localStorage.setItem(AI_MODE_LS_KEY, '1');
        syncAiExplainSectionVisibility();
        setAiFetchDetails('AI Mode ON — fields from GRN invoice line. Running AI match to similar items…');
        setTimeout(function() {
            fillGeneralFromAiTemplate().catch(function() {});
        }, 450);
    }

    const resetForNewItem = () => {
            if (!form) {
                window.location.href = viewUrl;
                return;
            }

            form.reset();

            // Clear text/number fields that might retain old values
            const preserveIds = new Set(['item_code', 'isNew', 'location_code']);
            form.querySelectorAll('input, textarea').forEach((el) => {
                if (preserveIds.has(el.id)) return;
                if (el.type === 'hidden') return;
                if (el.type === 'checkbox' || el.type === 'radio') {
                    el.checked = false;
                    return;
                }
                if (el.tagName === 'TEXTAREA') {
                    el.value = '';
                    return;
                }
                if (el.type === 'number') {
                    el.value = '';
                    return;
                }
                if (el.type === 'text') {
                    el.value = '';
                }
            });
            if (isNewInput) {
                isNewInput.value = 'true';
            }
            updateSaveButtonLabel();

            itemmasterActiveSection = 'general';
            if (tabs.length) {
                tabs.forEach((t) => t.classList.remove('tab--active'));
                tabContents.forEach((tc) => tc.classList.remove('tab-content--active'));
                const generalTab = document.querySelector('.itemmaster-tabs .tab[data-tab="general"]');
                const generalContent = document.getElementById('tab-general');
                if (generalTab) generalTab.classList.add('tab--active');
                if (generalContent) generalContent.classList.add('tab-content--active');
            }
            document.getElementById('tab-general')?.scrollIntoView({ behavior: 'auto', block: 'nearest', inline: 'nearest' });

            if (itemStatus) {
                itemStatus.innerHTML = '<span class="status-badge status-badge--new">New</span>';
            }
            if (btnDelete) {
                btnDelete.style.display = 'none';
            }

            // Clear dependent selections
            clearDependentFields('department', 'category');

            const setField = (id, value = '') => {
                const el = document.getElementById(id);
                if (el) el.value = value;
            };
            const setClear = (id, show) => {
                const el = document.getElementById(id);
                if (el) el.style.display = show ? 'block' : 'none';
            };

            // Reset popup display + hidden code fields
            setField('main_category', '');
            setField('main_category_code', '0');
            setClear('mainCategoryClear', false);

            setField('department_code', '');
            setField('department_code_hidden', '');
            setClear('departmentClear', false);

            setField('category_code', '');
            setField('category_code_hidden', '0');
            setClear('categoryClear', false);

            setField('brand_code', '');
            setField('brand_code_hidden', '0');
            setClear('brandClear', false);

            setField('property', '');
            setField('property_code', '0');
            setClear('propertyClear', false);

            setField('origin', '');
            setField('origin_code', '0');
            setClear('originClear', false);

            setField('rebate', '0');
            setField('size_code_hidden', '0');

            setField('color_code_hidden', '0');

            setField('base_uom', '');
            setField('base_uom_hidden', '');
            setClear('baseUomClear', false);

            setField('sup_code', '');
            setField('sup_code_hidden', '0');
            setClear('supplierClear', false);
            if (isItemRequestMode) {
                setField('dbocode_display', defaultDbocode);
                setField('dbocode_hidden', defaultDbocode);
                setField('branch_display', defaultBranch);
                setField('branch_hidden', defaultBranch);
                setClear('dbocodeClear', !!defaultDbocode);
            } else {
                setField('default_warehouse_display', '');
                setField('default_warehouse_id', '');
                setClear('defaultWarehouseClear', false);
            }

            setField('ministry_factor', '');
            setField('ministry_unit', '');

            // Reset variant fields
            setField('alternate_barcode', '');
            setField('alternate_uom_display', '');
            setField('alternate_uom_code', '');
            setClear('alternateUomClear', false);
            setField('alternate_conversion_factor', '');
            setField('alternate_cost_price', '');
            setField('alternate_wholesale_price', '');
            setField('alternate_retail_price', '');
            setField('alternate_third_price', '');
            setField('alternate_branch_price', '');
            const variantTbody = getVariantTableBody();
            if (variantTbody) {
                variantTbody.innerHTML = `
                    <tr id="variantEmptyRow">
                        <td colspan="12" class="muted">Default variant will appear when Base UOM is set (same as item master).</td>
                    </tr>
                `;
            }
            variantsLoaded = false;
            const storeInventoryBody = document.getElementById('storeInventoryBody');
            if (storeInventoryBody) {
                storeInventoryBody.innerHTML = `
                    <tr id="storeInventoryEmptyRow">
                        <td colspan="4" class="muted">No store inventory rows found.</td>
                    </tr>
                `;
            }
            selectedVariantRow = null;
            setField('sales_account_display', '');
            setField('sales_account', '');
            setField('purchase_account_display', '');
            setField('purchase_account', '');
            setField('inventory_account_display', '');
            setField('inventory_account', '');
            setField('cogs_account_display', '');
            setField('cogs_account', '');

            // Default account mapping for new items
            setField('sales_account_display', '4100 - Sales Revenue');
            setField('sales_account', '4100');
            setField('purchase_account_display', '5001 - Purchase Expense');
            setField('purchase_account', '5001');
            setField('inventory_account_display', '1300 - Inventory');
            setField('inventory_account', '1300');
            setField('cogs_account_display', '5100 - Cost of Goods Sold');
            setField('cogs_account', '5100');
            setField('temp_item_code_hidden', '');
            setField('tempitemcode_display', '');

            fetch(nextCodeUrl)
                .then(response => response.json())
                .then(data => {
                    if (data.success && itemCodeInput) {
                        itemCodeInput.value = data.item_code;
                        focusBarcodeField();
                    } else if (!data.success) {
                        alert('Error: ' + (data.error || 'Failed to get next item code'));
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred while getting next item code');
                })
                .finally(() => {
                    focusBarcodeField();
                    seedDefaultMirrorVariantRow();
                });

            // Keep URL clean so refresh stays on new-item mode.
            try {
                if (window.history && typeof window.history.replaceState === 'function') {
                    window.history.replaceState({}, '', viewUrl);
                }
            } catch (e) {}
            // New flow: start typing from barcode first.
            setTimeout(focusBarcodeField, 0);
    };

    // HO Itemmaster Central: select all enabled target DB checkboxes (new item / remap aid).
    const btnHoTargetAll = document.getElementById('btnHoTargetAll');
    const btnHoTargetNone = document.getElementById('btnHoTargetNone');
    const HO_TARGET_STORAGE_KEY = 'ho_central_target_tenant_ids';
    const persistHoTargetChecks = () => {
        if (!requireTargetDb) return;
        try {
            const ids = hoTargetTenantChecks().filter((cb) => cb.checked).map((cb) => cb.value);
            sessionStorage.setItem(HO_TARGET_STORAGE_KEY, JSON.stringify(ids));
        } catch (e) { /* ignore */ }
    };
    const setHoTargetChecks = (checked) => {
        hoTargetTenantChecks().forEach((cb) => {
            if (cb.disabled) return;
            cb.checked = !!checked;
        });
        persistHoTargetChecks();
    };
    if (requireTargetDb) {
        try {
            const raw = sessionStorage.getItem(HO_TARGET_STORAGE_KEY);
            if (raw) {
                const ids = JSON.parse(raw);
                if (Array.isArray(ids) && ids.length) {
                    const isNewEl = document.getElementById('isNew');
                    const isNew = isNewEl && String(isNewEl.value).toLowerCase() === 'true';
                    const enabled = hoTargetTenantChecks().filter((cb) => !cb.disabled);
                    const anyChecked = enabled.some((cb) => cb.checked);
                    if (isNew || !anyChecked) {
                        const set = new Set(ids.map(String));
                        enabled.forEach((cb) => { cb.checked = set.has(String(cb.value)); });
                    }
                }
            }
        } catch (e) { /* ignore */ }
        hoTargetTenantChecks().forEach((cb) => cb.addEventListener('change', persistHoTargetChecks));
    }
    if (btnHoTargetAll && requireTargetDb) {
        btnHoTargetAll.addEventListener('click', () => setHoTargetChecks(true));
    }
    if (btnHoTargetNone && requireTargetDb) {
        btnHoTargetNone.addEventListener('click', () => setHoTargetChecks(false));
    }

    // New button - reset to new item form
    if (btnNew) {
        btnNew.addEventListener('click', function() {
            // New item: load full edit context (dropdowns, COA, etc.).
            window.location.href = `${viewPathForNav}?edit=1&_r=${Date.now()}`;
        });
    }

    // Page-load behavior: same as pressing New, unless explicitly opened with lookup params.
    const applyNewModeOnLoad = () => {
        if (!hasLookupParams()) {
            resetForNewItem();
        }
    };
    setTimeout(applyNewModeOnLoad, 0);

    if (viewOnly && form) {
        setTimeout(function() {
            form.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select').forEach(function(el) {
                const tag = (el.tagName || '').toLowerCase();
                if (tag === 'select') {
                    el.disabled = true;
                    return;
                }
                if (el.type === 'checkbox' || el.type === 'radio') {
                    el.disabled = true;
                    return;
                }
                el.readOnly = true;
            });
            document.querySelectorAll('.alt-variant-edit, #variantAddBtn').forEach(function(b) {
                if (b) {
                    b.disabled = true;
                }
            });
        }, 0);
    }

    // resetForNewItem() fetches the next item code; when GRN/prefill params skip reset, fetch it here.
    const shouldFetchNextItemCodeAfterPrefill = () => {
        if (!itemCodeInput || !nextCodeUrl) return false;
        const isNew = String(isNewInput?.value || '').toLowerCase() === 'true';
        if (!isNew) return false;
        if (String(itemCodeInput.value || '').trim()) return false;
        try {
            const qs = new URLSearchParams(window.location.search || '');
            if ((qs.get('from_grn_ai') || '').trim()) return true;
            if ((qs.get('prefill_itemname') || '').trim()) return true;
            for (const k of qs.keys()) {
                if (String(k || '').toLowerCase().startsWith('prefill_')) return true;
            }
        } catch (e) {
            return false;
        }
        return false;
    };
    setTimeout(function() {
        if (!shouldFetchNextItemCodeAfterPrefill()) return;
        fetch(nextCodeUrl)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data && data.success && itemCodeInput) {
                    itemCodeInput.value = data.item_code;
                } else if (data && !data.success) {
                    console.warn('Next item code:', data.error || 'failed');
                }
            })
            .catch(function(err) {
                console.warn('Next item code fetch failed', err);
            });
    }, 0);

    // GRN / prefill skips resetForNewItem(); AI fill runs ~450ms later — retry a few times so GL defaults stick.
    [0, 300, 800].forEach((ms) => setTimeout(applyGrnOrPrefillDefaultGlIfEmpty, ms));
    // After cost/category prefill or AI match, apply micro-category PRICEPERCENTAGE markup to selling prices.
    [900, 1600].forEach((ms) => setTimeout(applyCategoryPriceMarkupFromCost, ms));
    // Handle browser back/forward cache to keep load behavior consistent.
    window.addEventListener('pageshow', () => {
        setTimeout(applyNewModeOnLoad, 0);
    });

    // Fresh load (new mode): keep focus on barcode after initial render.
    setTimeout(() => {
        const isNewMode = String(isNewInput?.value || '').toLowerCase() === 'true';
        if (!hasLookupParams() && isNewMode) {
            focusBarcodeField();
        }
    }, 120);

    // In HO mode, refreshing page should reset form to create-new state.
    if (requireTargetDb) {
        let isReload = false;
        try {
            const navEntries = (performance && typeof performance.getEntriesByType === 'function')
                ? performance.getEntriesByType('navigation')
                : [];
            if (navEntries && navEntries.length) {
                isReload = String(navEntries[0].type || '').toLowerCase() === 'reload';
            } else if (performance && performance.navigation) {
                isReload = Number(performance.navigation.type) === 1;
            }
        } catch (e) {}
        if (isReload && !hasLookupParams()) {
            setTimeout(resetForNewItem, 0);
        }
    }

    // Query button - Item Code / Master Code (rawabicode) / Barcode
    if (btnQuery) {
        btnQuery.addEventListener('click', function() {
            const modeInput = (prompt('Query by:\n1) Item Code\n2) Master Code\n3) Barcode', '3') || '').trim().toLowerCase();
            if (!modeInput) return;
            let mode = 'barcode';
            if (modeInput === '1' || modeInput === 'item' || modeInput === 'itemcode' || modeInput === 'item code') {
                mode = 'item_code';
            } else if (modeInput === '2' || modeInput === 'rawabi' || modeInput === 'rawabicode' || modeInput === 'rawabi code' || modeInput === 'master code' || modeInput === 'master') {
                mode = 'rawabicode';
            } else {
                mode = 'barcode';
            }
            const label = mode === 'item_code' ? 'Item Code' : (mode === 'rawabicode' ? 'Master Code' : 'Barcode');
            const value = (prompt(`Enter ${label}:`) || '').trim();
            if (!value) return;
            if (mode === 'item_code') {
                window.location.href = `${viewUrl}?item_code=${encodeURIComponent(value)}`;
            } else if (mode === 'rawabicode') {
                window.location.href = `${viewUrl}?rawabicode=${encodeURIComponent(value)}`;
            } else {
                window.location.href = `${viewUrl}?manufacturer_id=${encodeURIComponent(value)}`;
            }
        });
    }

    // Delete button
    if (btnDelete) {
        btnDelete.addEventListener('click', function() {
            const itemCode = itemCodeInput.value;
            if (!itemCode) {
                alert('No item selected to delete');
                return;
            }
            
            if (confirm(`Are you sure you want to delete Item Code: ${itemCode}?`)) {
                // TODO: Implement delete functionality
                alert('Delete functionality to be implemented');
            }
        });
    }

    if (btnRejectItemRequest) {
        const rejectUrl = (btnRejectItemRequest.dataset.rejectUrl || '').trim();
        if (rejectUrl) {
            btnRejectItemRequest.addEventListener('click', async function() {
                if (!confirm('Reject this item request? It will move to the Rejected tab.')) return;
                const reason = prompt('Optional reason for rejection (leave blank if none):', '') || '';
                const oldText = btnRejectItemRequest.textContent;
                btnRejectItemRequest.disabled = true;
                btnRejectItemRequest.textContent = 'Rejecting\u2026';
                try {
                    const res = await fetch(rejectUrl, {
                        method: 'POST',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ reason: (reason || '').trim().slice(0, 500) }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok || !data.success) {
                        throw new Error((data && (data.error || data.message)) || `Reject failed (HTTP ${res.status})`);
                    }
                    alert(data.message || 'Item request rejected.');
                    if (itemRequestRejectedUrl) {
                        window.location.href = itemRequestRejectedUrl;
                    } else {
                        try {
                            const u = new URL(listUrl || '/ho/item-request', window.location.href);
                            u.searchParams.set('tab', 'rejected');
                            window.location.href = u.pathname + u.search;
                        } catch (e2) {
                            window.location.href = '/ho/item-request?tab=rejected';
                        }
                    }
                } catch (e) {
                    alert(`Error: ${e.message || e}`);
                } finally {
                    btnRejectItemRequest.disabled = false;
                    btnRejectItemRequest.textContent = oldText;
                }
            });
        }
    }

    // Cancel button
    if (btnCancel) {
        btnCancel.addEventListener('click', function() {
            if (viewOnly) {
                if (listUrl) {
                    window.location.href = listUrl;
                } else {
                    window.location.href = viewPathForNav;
                }
                return;
            }
            if (confirm('Reset this item form?')) {
                form.reset();
                window.location.href = viewUrl;
            }
        });
    }

    const setVariantValue = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.value = value || '';
    };
    const setVariantClear = (id, show) => {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? 'block' : 'none';
    };
    const updateVariantUomDisplay = (uomCode) => {
        const input = document.getElementById('alternate_uom_display');
        if (!input) return;
        if (!uomCode) {
            input.value = '';
            return;
        }
        const row = document.querySelector(`#alternateUomModalTable tr[data-code="${uomCode}"]`);
        if (row && row.dataset.name) {
            input.value = `${uomCode} - ${row.dataset.name}`;
        } else {
            input.value = uomCode;
        }
    };
    const clearVariantEditorFields = () => {
        setVariantValue('alternate_slno', '');
        setVariantValue('alternate_description', '');
        setVariantValue('alternate_barcode', '');
        setVariantValue('alternate_uom_code', '');
        updateVariantUomDisplay('');
        setVariantClear('alternateUomClear', false);
        setVariantValue('alternate_conversion_factor', '');
        setVariantValue('alternate_cost_price', '');
        setVariantValue('alternate_wholesale_price', '');
        setVariantValue('alternate_retail_price', '');
        setVariantValue('alternate_third_price', '');
        setVariantValue('alternate_branch_price', '');
        setVariantEditorLocked(false);
        selectedVariantRow = null;
    };

    const setVariantEditorLocked = (locked) => {
        const lockIds = [
            'alternate_description', 'alternate_barcode', 'alternate_uom_display',
            'alternate_conversion_factor', 'alternate_wholesale_price', 'alternate_retail_price',
            'alternate_third_price', 'alternate_branch_price',
        ];
        lockIds.forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.readOnly = !!locked;
            if (locked) el.classList.add('input-readonly');
            else el.classList.remove('input-readonly');
        });
        const uomPicker = document.getElementById('alternateUomPicker');
        const uomClear = document.getElementById('alternateUomClear');
        if (uomPicker) uomPicker.disabled = !!locked;
        if (uomClear) uomClear.style.pointerEvents = locked ? 'none' : '';
        const addBtn = document.getElementById('variantAddBtn');
        if (addBtn && locked) addBtn.disabled = true;
        else if (addBtn && !viewOnly) addBtn.disabled = false;
    };

    const loadVariantRowToEditor = (row) => {
        if (!row) return;
        if (variantRowIsBase(row)) {
            syncMirrorVariantRowFromItemmaster();
            alert('This is the base variant linked to Item Master. Change Base UOM, barcode, description, or prices on the General and Pricing tabs — the base row updates automatically.');
            return;
        }
        setVariantEditorLocked(false);
        selectedVariantRow = row;
        setVariantValue('alternate_slno', row.dataset.slno || '');
        setVariantValue('alternate_description', row.dataset.description || '');
        setVariantValue('alternate_barcode', row.dataset.barcode || '');
        setVariantValue('alternate_uom_code', row.dataset.uom || '');
        updateVariantUomDisplay(row.dataset.uom || '');
        setVariantClear('alternateUomClear', !!(row.dataset.uom || ''));
        setVariantValue('alternate_conversion_factor', row.dataset.factor || '');
        setVariantValue('alternate_cost_price', row.dataset.cost || '');
        setVariantValue('alternate_wholesale_price', row.dataset.wholesale || '');
        setVariantValue('alternate_retail_price', row.dataset.retail || '');
        setVariantValue('alternate_third_price', row.dataset.third || '');
        setVariantValue('alternate_branch_price', row.dataset.branch || '');
    };

    // Variant list edit button -> load into edit fields
    const variantRows = document.querySelectorAll('.alt-variant-row');
    if (variantRows.length) {
        variantRows.forEach((row) => {
            const btn = row.querySelector('.alt-variant-edit');
            if (!btn) return;
            btn.addEventListener('click', () => loadVariantRowToEditor(row));
        });
    }
    // Edit existing item: keep variant editor empty until user clicks Edit on a grid row.
    if (!getIsNewMode() && !viewOnly) {
        clearVariantEditorFields();
    } else if (variantRows.length) {
        clearVariantEditorFields();
    }

    const variantAddBtn = document.getElementById('variantAddBtn');

    const formatNum = (val, digits) => {
        const n = parseFloat(val);
        if (!isFinite(n)) return '0';
        return n.toFixed(digits);
    };

    const findCurrentVariantRow = () => {
        const slno = (document.getElementById('alternate_slno')?.value || '').trim();
        const uom = (document.getElementById('alternate_uom_code')?.value || '').trim();
        if (slno) {
            const bySl = document.querySelector(`.alt-variant-row[data-slno="${slno}"]`);
            if (bySl) return bySl;
        }
        if (uom) {
            const byUom = document.querySelector(`.alt-variant-row[data-uom="${uom}"]`);
            if (byUom) return byUom;
        }
        return null;
    };

    const getVariantTableBody = () => {
        return document.querySelector('#tab-variant .scroll-table table tbody');
    };

    const getNextVariantSlno = () => {
        const rows = document.querySelectorAll('.alt-variant-row');
        let maxSl = 0;
        rows.forEach((r) => {
            const n = parseInt((r.dataset.slno || '').trim(), 10);
            if (!Number.isNaN(n) && n > maxSl) maxSl = n;
        });
        return String(maxSl + 1);
    };

    const readMirrorVariantPricing = () => ({
        cost: formatNum(document.getElementById('cost_price')?.value || 0, 3),
        wholesale: formatNum(document.getElementById('wholesale_price')?.value || 0, 2),
        retail: formatNum(document.getElementById('retail_price')?.value || 0, 2),
        third: formatNum(document.getElementById('third_price')?.value || 0, 2),
        branch: formatNum(document.getElementById('branch_price')?.value || 0, 2),
    });

    const syncMirrorVariantRowFromItemmaster = () => {
        const row = document.querySelector('.alt-variant-row[data-mirror-base="1"]');
        if (!row) return;
        const itemCode = (itemCodeInput?.value || '').trim();
        const barcode = ((manufacturerIdInput && manufacturerIdInput.value) ? manufacturerIdInput.value : itemCode || '').trim();
        const uom = (document.getElementById('base_uom_hidden')?.value || document.getElementById('base_uom')?.value || '').trim();
        if (!uom) return;
        const prices = readMirrorVariantPricing();
        const desc = readItemDescriptionForBaseVariant();
        row.dataset.slno = row.dataset.slno || '1';
        row.dataset.barcode = barcode;
        row.dataset.uom = uom;
        row.dataset.factor = '1.000';
        row.dataset.description = desc;
        row.dataset.cost = prices.cost;
        row.dataset.wholesale = prices.wholesale;
        row.dataset.retail = prices.retail;
        row.dataset.third = prices.third;
        row.dataset.branch = prices.branch;
        const cells = row.querySelectorAll('td');
        if (cells.length >= 11) {
            cells[1].textContent = row.dataset.slno;
            cells[2].textContent = desc || '-';
            cells[3].textContent = barcode || '-';
            cells[4].textContent = uom || '-';
            cells[5].textContent = row.dataset.factor;
            cells[6].textContent = prices.cost;
            cells[7].textContent = prices.wholesale;
            cells[8].textContent = prices.retail;
            cells[9].textContent = prices.third;
            cells[10].textContent = prices.branch;
        }
    };

    const generateTenDigitBarcode = async ({ silent = false } = {}) => {
        if (viewOnly) return false;
        const itemCode = String(itemCodeInput?.value || '').trim();
        if (!itemCode) {
            if (!silent) alert('Item code is required to generate barcode.');
            return false;
        }
        const isNew = String(isNewInput?.value || '').toLowerCase() === 'true';
        const qs = new URLSearchParams({ item_code: itemCode });
        if (!isNew) qs.set('exclude_item_code', itemCode);
        const locHint = String(hoSourceLocation || '').trim();
        if (locHint && /^\d+$/.test(locHint)) {
            qs.set('location_code', locHint);
        }
        try {
            const res = await fetch(`${suggestBarcodeUrl}?${qs.toString()}`);
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success || !data.barcode) {
                if (!silent) alert(data.error || 'Could not generate barcode.');
                return false;
            }
            if (manufacturerIdInput) manufacturerIdInput.value = String(data.barcode);
            syncMirrorVariantRowFromItemmaster();
            return true;
        } catch (err) {
            if (!silent) alert(err?.message || 'Could not generate barcode.');
            return false;
        }
    };

    const btnGenerateBarcode = document.getElementById('btnGenerateBarcode');
    if (btnGenerateBarcode && !viewOnly) {
        btnGenerateBarcode.addEventListener('click', () => {
            generateTenDigitBarcode({ silent: false }).catch(() => {});
        });
    }

    const seedDefaultMirrorVariantRow = () => {
        const tbody = getVariantTableBody();
        if (!tbody) return;
        const uom = (document.getElementById('base_uom_hidden')?.value || document.getElementById('base_uom')?.value || '').trim();
        if (!uom) return;
        const itemCode = (itemCodeInput?.value || '').trim();
        const barcode = ((manufacturerIdInput && manufacturerIdInput.value) ? manufacturerIdInput.value : itemCode || '').trim();
        const prices = readMirrorVariantPricing();
        const existingMirror = tbody.querySelector('.alt-variant-row[data-mirror-base="1"]');
        if (existingMirror) {
            syncMirrorVariantRowFromItemmaster();
            return;
        }
        const emptyRow = document.getElementById('variantEmptyRow');
        if (emptyRow) emptyRow.remove();

        const tr = document.createElement('tr');
        const desc = readItemDescriptionForBaseVariant();
        tr.dataset.mirrorBase = '1';
        tr.dataset.isBase = '1';
        tr.className = 'alt-variant-row alt-variant-row--base';
        tr.dataset.slno = '1';
        tr.dataset.description = desc;
        tr.dataset.barcode = barcode;
        tr.dataset.uom = uom;
        tr.dataset.factor = '1.000';
        tr.dataset.cost = prices.cost;
        tr.dataset.wholesale = prices.wholesale;
        tr.dataset.retail = prices.retail;
        tr.dataset.third = prices.third;
        tr.dataset.branch = prices.branch;
        tr.innerHTML = `
            <td><span class="status-badge status-badge--active" title="Linked to Item Master">Base</span></td>
            <td>1</td>
            <td>${escapeHtml(desc || '-')}</td>
            <td>${escapeHtml(barcode || '-')}</td>
            <td>${escapeHtml(uom || '-')}</td>
            <td>1.000</td>
            <td>${prices.cost}</td>
            <td>${prices.wholesale}</td>
            <td>${prices.retail}</td>
            <td>${prices.third}</td>
            <td>${prices.branch}</td>
            <td><span class="muted" style="font-size:12px;">Linked</span></td>
        `;
        const editBtn = tr.querySelector('.alt-variant-edit');
        if (editBtn) editBtn.addEventListener('click', () => loadVariantRowToEditor(tr));
        tbody.appendChild(tr);
        variantsLoaded = true;
    };

    const applyVariantRowValues = (row) => {
        if (!row || variantRowIsBase(row)) return;
        const slno = (document.getElementById('alternate_slno')?.value || row.dataset.slno || '').trim();
        const barcode = (document.getElementById('alternate_barcode')?.value || '').trim();
        const uom = (document.getElementById('alternate_uom_code')?.value || '').trim();
        const factor = formatNum(document.getElementById('alternate_conversion_factor')?.value || 0, 3);
        const cost = formatNum(document.getElementById('alternate_cost_price')?.value || 0, 3);
        const wholesale = formatNum(document.getElementById('alternate_wholesale_price')?.value || 0, 2);
        const retail = formatNum(document.getElementById('alternate_retail_price')?.value || 0, 2);
        const third = formatNum(document.getElementById('alternate_third_price')?.value || 0, 2);
        const branch = formatNum(document.getElementById('alternate_branch_price')?.value || 0, 2);

        row.dataset.slno = slno;
        row.dataset.description = (document.getElementById('alternate_description')?.value || row.dataset.description || '').trim();
        row.dataset.barcode = barcode;
        row.dataset.uom = uom;
        row.dataset.factor = factor;
        row.dataset.cost = cost;
        row.dataset.wholesale = wholesale;
        row.dataset.retail = retail;
        row.dataset.third = third;
        row.dataset.branch = branch;

        const desc = row.dataset.description || '';
        const cells = row.querySelectorAll('td');
        if (cells.length >= 11) {
            cells[1].textContent = slno || '-';
            cells[2].textContent = desc || '-';
            cells[3].textContent = barcode || '-';
            cells[4].textContent = uom || '-';
            cells[5].textContent = factor;
            cells[6].textContent = cost;
            cells[7].textContent = wholesale;
            cells[8].textContent = retail;
            cells[9].textContent = third;
            cells[10].textContent = branch;
        }
    };

    const appendVariantRow = () => {
        const tbody = getVariantTableBody();
        if (!tbody) return null;
        const emptyRow = document.getElementById('variantEmptyRow');
        if (emptyRow) {
            emptyRow.remove();
        }

        const slnoInput = (document.getElementById('alternate_slno')?.value || '').trim();
        const slno = slnoInput || getNextVariantSlno();
        const barcode = (document.getElementById('alternate_barcode')?.value || '').trim();
        const uom = (document.getElementById('alternate_uom_code')?.value || '').trim();
        const factor = formatNum(document.getElementById('alternate_conversion_factor')?.value || 0, 3);
        const cost = formatNum(document.getElementById('alternate_cost_price')?.value || 0, 3);
        const wholesale = formatNum(document.getElementById('alternate_wholesale_price')?.value || 0, 2);
        const retail = formatNum(document.getElementById('alternate_retail_price')?.value || 0, 2);
        const third = formatNum(document.getElementById('alternate_third_price')?.value || 0, 2);
        const branch = formatNum(document.getElementById('alternate_branch_price')?.value || 0, 2);

        const tr = document.createElement('tr');
        tr.className = 'alt-variant-row';
        const desc = (document.getElementById('alternate_description')?.value || '').trim();
        tr.dataset.slno = slno;
        tr.dataset.description = desc;
        tr.dataset.barcode = barcode;
        tr.dataset.uom = uom;
        tr.dataset.factor = factor;
        tr.dataset.cost = cost;
        tr.dataset.wholesale = wholesale;
        tr.dataset.retail = retail;
        tr.dataset.third = third;
        tr.dataset.branch = branch;
        tr.innerHTML = `
            <td>-</td>
            <td>${slno || '-'}</td>
            <td>${escapeHtml(desc || '-')}</td>
            <td>${escapeHtml(barcode || '-')}</td>
            <td>${escapeHtml(uom || '-')}</td>
            <td>${factor}</td>
            <td>${cost}</td>
            <td>${wholesale}</td>
            <td>${retail}</td>
            <td>${third}</td>
            <td>${branch}</td>
            <td><button type="button" class="im-link alt-variant-edit">Edit</button></td>
        `;
        const editBtn = tr.querySelector('.alt-variant-edit');
        if (editBtn) editBtn.addEventListener('click', () => loadVariantRowToEditor(tr));

        tbody.appendChild(tr);
        return tr;
    };

    const saveVariantInline = (opts) => {
        if (selectedVariantRow && variantRowIsBase(selectedVariantRow)) {
            alert('The base variant cannot be edited here. Update Item Master fields (Base UOM, barcode, description, prices) instead.');
            return;
        }
        const options = opts && typeof opts === 'object' ? opts : {};
        const allowStagingWithoutItemCode = !!options.allowStagingWithoutItemCode;
        const itemCode = (itemCodeInput?.value || '').trim();
        const altUomCode = (document.getElementById('alternate_uom_code')?.value || '').trim();
        const altBarcode = (document.getElementById('alternate_barcode')?.value || '').trim();
        const currentSlno = (document.getElementById('alternate_slno')?.value || '').trim();
        const conversionFactor = (document.getElementById('alternate_conversion_factor')?.value || '').trim();
        const variantRequiredFieldIds = [
            'alternate_uom_display',
            'alternate_conversion_factor',
            'alternate_cost_price',
            'alternate_wholesale_price',
            'alternate_retail_price',
            'alternate_third_price',
            'alternate_branch_price',
        ];
        const clearVariantFieldError = (id) => {
            const el = document.getElementById(id);
            if (el) el.style.borderBottomColor = '';
        };
        const markVariantFieldError = (id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.borderBottomColor = '#dc3545';
        };
        const getVariantFieldValue = (id) => {
            if (id === 'alternate_uom_display') {
                return String(document.getElementById('alternate_uom_code')?.value || '').trim();
            }
            return String(document.getElementById(id)?.value || '').trim();
        };
        const findFirstMissingRequiredVariantField = () => {
            for (const id of variantRequiredFieldIds) {
                const v = getVariantFieldValue(id);
                if (!v) return id;
            }
            return '';
        };
        const focusVariantField = (id) => {
            const el = document.getElementById(id);
            if (!el) return;
            setActiveTabByName('variant');
            setTimeout(() => {
                el.focus();
                el.select?.();
            }, 0);
        };
        if (!allowStagingWithoutItemCode && !itemCode) {
            alert('Item code is not ready yet (still loading). Wait a moment, then use + or Save again—or refresh the page.');
            return;
        }
        if (altBarcode) {
            const missingId = findFirstMissingRequiredVariantField();
            variantRequiredFieldIds.forEach(clearVariantFieldError);
            if (missingId) {
                markVariantFieldError(missingId);
                focusVariantField(missingId);
                return;
            }
        }
        if (!altUomCode || !conversionFactor) {
            return;
        }

        // Client-side duplicate guard (backend also validates).
        const normalizedUom = altUomCode.toUpperCase();
        const normalizedBarcode = altBarcode.toUpperCase();
        const mainBarcode = ((manufacturerIdInput && manufacturerIdInput.value) ? manufacturerIdInput.value : '').trim().toUpperCase();
        const rows = Array.from(document.querySelectorAll('.alt-variant-row'));
        const dupUom = rows.some((r) => {
            const rowSl = String(r.dataset.slno || '').trim();
            if (currentSlno && rowSl === currentSlno) return false;
            return String(r.dataset.uom || '').trim().toUpperCase() === normalizedUom;
        });
        if (dupUom) {
            alert('Alternate UOM already exists for this item. Please use another UOM.');
            return;
        }
        if (normalizedBarcode) {
            const mirrorEdit = selectedVariantRow && selectedVariantRow.dataset.mirrorBase === '1';
            const mirrorPayload = normalizedUom === (document.getElementById('base_uom_hidden')?.value || '').trim().toUpperCase()
                && String(conversionFactor).trim() === '1'
                && mainBarcode
                && normalizedBarcode === mainBarcode;
            if (mainBarcode && normalizedBarcode === mainBarcode && !mirrorEdit && !mirrorPayload) {
                alert('Barcode already exists in Itemmaster. Please use another barcode.');
                return;
            }
            const dupBarcode = rows.some((r) => {
                const rowSl = String(r.dataset.slno || '').trim();
                if (currentSlno && rowSl === currentSlno) return false;
                return String(r.dataset.barcode || '').trim().toUpperCase() === normalizedBarcode;
            });
            if (dupBarcode) {
                alert('Alternate barcode already exists for this item. Please use another barcode.');
                return;
            }
        }
        const row = selectedVariantRow || findCurrentVariantRow();
        if (row) {
            applyVariantRowValues(row);
            selectedVariantRow = row;
        } else {
            const newRow = appendVariantRow();
            if (newRow) {
                selectedVariantRow = newRow;
            }
        }
        // Clear variant entry fields after local list insert/update.
        const clearIds = [
            'alternate_slno',
            'alternate_barcode',
            'alternate_uom_display',
            'alternate_uom_code',
            'alternate_conversion_factor',
            'alternate_cost_price',
            'alternate_wholesale_price',
            'alternate_retail_price',
            'alternate_third_price',
            'alternate_branch_price',
        ];
        clearIds.forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const altUomClear = document.getElementById('alternateUomClear');
        if (altUomClear) altUomClear.style.display = 'none';
        selectedVariantRow = null;
    };

    // Form submission
    if (form) {
        // Always use custom validation messages (avoid silent native blocking).
        form.setAttribute('novalidate', 'novalidate');

        const focusOrderIds = [
            // General
            'manufacturer_id', 'item_name', 'item_name_ara', 'description',
            'main_category', 'department_code', 'category_code', 'brand_code',
            'sup_code', 'base_uom',
            // Pricing
            'cost_price', 'retail_price', 'wholesale_price', 'third_price', 'branch_price',
            // Variant
            'alternate_barcode', 'alternate_uom_display', 'alternate_conversion_factor', 'alternate_cost_price',
            'alternate_wholesale_price', 'alternate_retail_price', 'alternate_third_price', 'alternate_branch_price', 'variantAddBtn',
            // Inventory (default warehouse first on this tab when stepping with Enter)
            'default_warehouse_display', 'maximum_level', 'reorder_level', 'quantity_limit',
            // Additional
            'property', 'origin', 'packing',
            // Accounts
            'sales_account_display', 'purchase_account_display', 'inventory_account_display', 'cogs_account_display', 'vat_percent',
        ];

        const focusNextField = (currentEl) => {
            if (!currentEl || !currentEl.id) return false;
            const idx = focusOrderIds.indexOf(currentEl.id);
            if (idx < 0) return false;
            for (let i = idx + 1; i < focusOrderIds.length; i += 1) {
                const next = document.getElementById(focusOrderIds[i]);
                if (!next || next.disabled) continue;
                const tabContent = next.closest('.tab-content');
                let switchedSection = false;
                if (tabContent && tabContent.id && tabContent.id.startsWith('tab-')) {
                    const tabName = tabContent.id.slice(4);
                    if (tabName !== itemmasterActiveSection) {
                        switchedSection = true;
                        setActiveTabByName(tabName);
                    }
                }
                next.focus({ preventScroll: !switchedSection });
                next.select?.();
                return true;
            }
            return false;
        };
        const computeNextAlternateBarcode = () => {
            const itemCode = String(itemCodeInput?.value || '').trim();
            if (!itemCode) return '';
            const prefixUpper = `${itemCode}L`.toUpperCase();
            let maxSeq = 0;
            document.querySelectorAll('.alt-variant-row').forEach((row) => {
                const barcode = String(row.dataset.barcode || '').trim().toUpperCase();
                if (!barcode.startsWith(prefixUpper)) return;
                const tail = barcode.slice(prefixUpper.length);
                const n = parseInt(tail, 10);
                if (!Number.isNaN(n) && n > maxSeq) {
                    maxSeq = n;
                }
            });
            return `${itemCode}L${maxSeq + 1}`;
        };
        const focusPreviousField = (currentEl) => {
            if (!currentEl || !currentEl.id) return false;
            const idx = focusOrderIds.indexOf(currentEl.id);
            if (idx < 0) return false;
            for (let i = idx - 1; i >= 0; i -= 1) {
                const prev = document.getElementById(focusOrderIds[i]);
                if (!prev || prev.disabled) continue;
                const tabContent = prev.closest('.tab-content');
                let switchedSection = false;
                if (tabContent && tabContent.id && tabContent.id.startsWith('tab-')) {
                    const tabName = tabContent.id.slice(4);
                    if (tabName !== itemmasterActiveSection) {
                        switchedSection = true;
                        setActiveTabByName(tabName);
                    }
                }
                prev.focus({ preventScroll: !switchedSection });
                prev.select?.();
                return true;
            }
            const first = document.getElementById(focusOrderIds[0]);
            if (first && !first.disabled) {
                const tabContent = first.closest('.tab-content');
                let switchedSection = false;
                if (tabContent && tabContent.id && tabContent.id.startsWith('tab-')) {
                    const tabName = tabContent.id.slice(4);
                    if (tabName !== itemmasterActiveSection) {
                        switchedSection = true;
                        setActiveTabByName(tabName);
                    }
                }
                first.focus({ preventScroll: !switchedSection });
                first.select?.();
                return true;
            }
            return false;
        };
        const variantRequiredFieldIds = [
            'alternate_uom_display',
            'alternate_conversion_factor',
            'alternate_cost_price',
            'alternate_wholesale_price',
            'alternate_retail_price',
            'alternate_third_price',
            'alternate_branch_price',
        ];
        const clearVariantFieldError = (id) => {
            const el = document.getElementById(id);
            if (el) el.style.borderBottomColor = '';
        };
        const markVariantFieldError = (id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.borderBottomColor = '#dc3545';
        };
        const getVariantFieldValue = (id) => {
            if (id === 'alternate_uom_display') {
                return String(document.getElementById('alternate_uom_code')?.value || '').trim();
            }
            return String(document.getElementById(id)?.value || '').trim();
        };
        const enforceVariantRequiredForEnter = (targetId) => {
            const altBarcodeVal = String(document.getElementById('alternate_barcode')?.value || '').trim();
            if (!altBarcodeVal) {
                variantRequiredFieldIds.forEach(clearVariantFieldError);
                return true;
            }
            if (!variantRequiredFieldIds.includes(targetId)) {
                return true;
            }
            const currentVal = getVariantFieldValue(targetId);
            if (currentVal) {
                clearVariantFieldError(targetId);
                return true;
            }
            markVariantFieldError(targetId);
            const el = document.getElementById(targetId);
            if (el) {
                setActiveTabByName('variant');
                setTimeout(() => {
                    el.focus();
                    el.select?.();
                }, 0);
            }
            return false;
        };
        variantRequiredFieldIds.forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            const clearIfFilled = () => {
                if (getVariantFieldValue(id)) clearVariantFieldError(id);
            };
            el.addEventListener('input', clearIfFilled);
            el.addEventListener('change', clearIfFilled);
            el.addEventListener('focus', clearIfFilled);
        });

        // Prevent implicit submit on Enter; save only through Save button click.
        form.addEventListener('keydown', async function(e) {
            const key = e.key || '';
            if (key !== 'Enter') return;
            const target = e.target;
            if (!target) return;
            if ((target.id || '') === 'variantAddBtn') {
                e.preventDefault();
                saveVariantInline({ allowStagingWithoutItemCode: true });
                const altBarcode = document.getElementById('alternate_barcode');
                if (altBarcode) {
                    altBarcode.focus();
                    altBarcode.select?.();
                }
                return;
            }
            const tag = String(target.tagName || '').toUpperCase();
            if (tag === 'TEXTAREA') return;
            e.preventDefault();
            // Blank barcode + Enter: suggest 13-digit (12 prefix + item code).
            if (!isItemRequestMode && (target.id || '') === 'manufacturer_id') {
                if (manufacturerIdInput && itemCodeInput) {
                    const barcode = String(manufacturerIdInput.value || '').trim();
                    const itemCode = String(itemCodeInput.value || '').trim();
                    if (!barcode && itemCode) {
                        await generateTenDigitBarcode({ silent: false });
                    }
                }
                const aiOnBarcode = !!(aiModeToggle && aiModeToggle.checked);
                const barcodeForWeb = String(manufacturerIdInput?.value || '').trim();
                if (aiOnBarcode && barcodeForWeb) {
                    await fillFromWebBarcode();
                    return;
                }
            }
            // On Enter from Item Name, mirror value into Description.
            if ((target.id || '') === 'item_name' && itemNameInput && descriptionInput) {
                descriptionInput.value = String(itemNameInput.value || '').trim();
                const aiOn = !!(aiModeToggle && aiModeToggle.checked);
                if (aiOn) {
                    await fillGeneralFromAiTemplate();
                    return;
                }
            }
            if ((target.id || '') === 'alternate_barcode') {
                const altBarcodeInput = document.getElementById('alternate_barcode');
                const altBarcodeVal = String(altBarcodeInput?.value || '').trim();
                if (!altBarcodeVal && altBarcodeInput) {
                    const autoBarcode = computeNextAlternateBarcode();
                    if (autoBarcode) {
                        altBarcodeInput.value = autoBarcode;
                    }
                }
            }
            if (!enforceVariantRequiredForEnter(target.id || '')) {
                return;
            }
            if (focusNextField(target)) return;
        });

        if (variantAddBtn) {
            variantAddBtn.addEventListener('click', function() {
                saveVariantInline({ allowStagingWithoutItemCode: true });
                const altBarcode = document.getElementById('alternate_barcode');
                if (altBarcode) {
                    altBarcode.focus();
                    altBarcode.select?.();
                }
            });
        }

        // ESC key: move focus back through Item Master fields.
        document.addEventListener('keydown', function(e) {
            if ((e.key || '') !== 'Escape') return;
            if (e.defaultPrevented) return;
            // If a popup/modal is open, let popup handlers process ESC first.
            if (document.querySelector('.modal:not(.hidden)')) return;
            const active = document.activeElement;
            if (!active || !form.contains(active)) return;
            if (focusPreviousField(active)) {
                e.preventDefault();
            }
        });

        const showSaveError = (msg) => {
            const errMsg = String(msg || 'An error occurred while saving the item');
            alert('Error: ' + errMsg);
            if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                window.reEnableFormSubmit(form);
            }
            if (btnSave) {
                btnSave.disabled = false;
                updateSaveButtonLabel();
            }
        };
        const getFieldLabel = (fieldEl) => {
            if (!fieldEl) return 'This field';
            const id = fieldEl.id;
            if (id) {
                const label = document.querySelector(`label[for="${id}"]`);
                const txt = String(label?.textContent || '').replace('*', '').trim();
                if (txt) return txt;
            }
            return fieldEl.name || fieldEl.id || 'This field';
        };

        // Catch any native invalid event and show a clear alert.
        form.addEventListener('invalid', function(e) {
            e.preventDefault();
            const target = e.target;
            const label = getFieldLabel(target);
            alert(`${label} is required.`);
            if (target && typeof target.focus === 'function') {
                target.focus();
                target.select?.();
            }
        }, true);
        const setSavingUi = (isSaving) => {
            if (!btnSave) return;
            btnSave.disabled = !!isSaving;
            const verb = getSaveVerb();
            const busy = verb === 'Update' ? 'Updating…' : 'Saving…';
            btnSave.innerHTML = isSaving ? `<span aria-hidden="true">⏳</span> ${busy}` : verb;
        };
        const requiredSelections = [
            { label: 'Item Name', codeId: 'item_name', fieldId: 'item_name', isText: true },
            { label: 'Main Category', codeId: 'main_category_code', fieldId: 'main_category' },
            { label: 'Category', codeId: 'department_code_hidden', fieldId: 'department_code' },
            { label: 'Micro Category', codeId: 'category_code_hidden', fieldId: 'category_code' },
            { label: 'Brand', codeId: 'brand_code_hidden', fieldId: 'brand_code' },
            { label: 'Supplier', codeId: 'sup_code_hidden', fieldId: 'sup_code' },
            { label: 'Base Uom', codeId: 'base_uom_hidden', fieldId: 'base_uom' },
        ];
        if (!isItemRequestMode) {
            // Default warehouse is on Inventory tab; validate after General required popups.
            requiredSelections.push({ label: 'Default warehouse', codeId: 'default_warehouse_id', fieldId: 'default_warehouse_display' });
        }
        const isMissingSelection = (v) => {
            const txt = String(v == null ? '' : v).trim();
            return !txt || txt === '0';
        };
        // Guard: only one mandatory field may hold focus at a time (prevents focus-fighting)
        let _imActiveMandatory = null;

        const markMandatoryError = (req) => {
            requiredSelections.forEach((x) => {
                const other = document.getElementById(x.fieldId);
                if (!other) return;
                other.style.borderBottomColor = '';
                const otherWrap = other.closest && other.closest('.search-field');
                if (otherWrap) {
                    otherWrap.style.borderBottomColor = '';
                }
            });
            const field = document.getElementById(req.fieldId);
            if (!field) return;
            field.style.borderBottomColor = '#dc3545';
            const wrapper = field.closest && field.closest('.search-field');
            if (wrapper) {
                wrapper.style.borderBottomColor = '#dc3545';
            }
        };
        const clearMandatoryError = (req) => {
            const field = document.getElementById(req.fieldId);
            if (!field) return;
            field.style.borderBottomColor = '';
            const wrapper = field.closest && field.closest('.search-field');
            if (wrapper) {
                wrapper.style.borderBottomColor = '';
            }
        };
        const validateRequiredSelection = (req) => {
            const fieldEl = document.getElementById(req.codeId);
            const codeVal = fieldEl?.value;
            const missing = req.isText
                ? !String(codeVal == null ? '' : codeVal).trim()
                : isMissingSelection(codeVal);
            if (!missing) {
                clearMandatoryError(req);
                if (_imActiveMandatory === req) _imActiveMandatory = null;
                return true;
            }
            // Another field is already holding focus — don't fight it
            if (_imActiveMandatory && _imActiveMandatory !== req) return false;
            markMandatoryError(req);
            _imActiveMandatory = req;
            const field = document.getElementById(req.fieldId);
            if (field) {
                setTimeout(() => {
                    if (_imActiveMandatory === req) {
                        field.focus();
                        field.select?.();
                    }
                }, 0);
            }
            return false;
        };

        // Ensure Save click always submits through same handler.
        if (btnSave) {
            btnSave.addEventListener('click', function(e) {
                if (!form) {
                    e.preventDefault();
                    showSaveError('Form not found.');
                    return;
                }
                if (typeof form.requestSubmit === 'function') {
                    e.preventDefault();
                    form.requestSubmit();
                }
            });
        }
        if (btnRemap) {
            btnRemap.addEventListener('click', async function() {
                if (!remapUrl) {
                    alert('Remap URL is not configured.');
                    return;
                }
                const itemCode = String(itemCodeInput?.value || '').trim();
                if (!itemCode) {
                    alert('Open an existing item before remap.');
                    return;
                }
                const checkedTargets = hoTargetTenantChecks()
                    .filter((el) => !!el.checked)
                    .map((el) => (el.value || '').trim())
                    .filter((x) => !!x);
                const remapTargets = checkedTargets.filter((tid) => !existingTargets.has(tid));
                if (!remapTargets.length) {
                    alert('Select new target DB(s) to remap.');
                    return;
                }
                const oldText = btnRemap.innerHTML;
                btnRemap.disabled = true;
                btnRemap.innerHTML = '<span>⏳</span> Remapping...';
                try {
                    const sourceLoc = String(hoSourceLocation || document.querySelector('input[name="location_code"]')?.value || '').trim();
                    const response = await fetch(remapUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body: JSON.stringify({
                            source_tenant_id: 'HO',
                            source_location_code: sourceLoc,
                            item_codes: [itemCode],
                            target_tenant_ids: remapTargets,
                        }),
                    });
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok || !data.success) {
                        throw new Error((data && (data.error || data.message)) || `Remap failed (HTTP ${response.status})`);
                    }
                    alert(data.message || 'Remap completed.');
                    window.location.href = `${viewUrl}?item_code=${encodeURIComponent(itemCode)}`;
                } catch (err) {
                    alert(`Error: ${(err && err.message) ? err.message : err}`);
                } finally {
                    btnRemap.disabled = false;
                    btnRemap.innerHTML = oldText;
                }
            });
        }
        if (btnDeleteItem) {
            btnDeleteItem.addEventListener('click', async function() {
                if (!deleteItemUrl) {
                    alert('Delete URL is not configured.');
                    return;
                }
                const itemCode = String(itemCodeInput?.value || '').trim();
                if (!itemCode) {
                    alert('Open an item before delete.');
                    return;
                }
                const pwd = prompt('Enter delete password');
                if (pwd === null) return;
                if (String(pwd).trim() !== '123') {
                    alert('Invalid password');
                    return;
                }
                if (!confirm(`Delete item ${itemCode}?`)) return;
                const oldText = btnDeleteItem.innerHTML;
                btnDeleteItem.disabled = true;
                btnDeleteItem.innerHTML = '<span>⏳</span> Deleting...';
                try {
                    const response = await fetch(deleteItemUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        body: JSON.stringify({
                            item_code: itemCode,
                            password: String(pwd).trim(),
                        }),
                    });
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok || !data.success) {
                        throw new Error((data && (data.error || data.message)) || `Delete failed (HTTP ${response.status})`);
                    }
                    alert(data.message || 'Item deleted.');
                    window.location.href = viewUrl;
                } catch (err) {
                    const msg = (err && err.message) ? err.message : String(err || 'Delete failed');
                    if (String(msg).toLowerCase().includes('failed to fetch')) {
                        const goList = confirm(
                            'Network/timeout while waiting for delete response.\n\n' +
                            'Delete may still have been processed in server.\n' +
                            'Click OK to open list and verify item status.'
                        );
                        if (goList) {
                            window.location.href = listUrl || viewUrl;
                            return;
                        }
                    }
                    alert(`Error: ${msg}`);
                } finally {
                    btnDeleteItem.disabled = false;
                    btnDeleteItem.innerHTML = oldText;
                }
            });
        }
        // Validate mandatory fields immediately when user leaves a field.
        requiredSelections.forEach((req) => {
            const field = document.getElementById(req.fieldId);
            if (!field) return;
            const clearIfValid = () => { validateRequiredSelection(req); };
            field.addEventListener('input', clearIfValid);
            field.addEventListener('change', clearIfValid);
            field.addEventListener('focus', clearIfValid);
            field.addEventListener('focusout', function(e) {
                const next = e.relatedTarget;
                if (!next) return;
                const sameSearchField = next
                    && field.closest
                    && next.closest
                    && field.closest('.search-field')
                    && field.closest('.search-field') === next.closest('.search-field');
                if (sameSearchField) return;
                if (document.querySelector('.modal:not(.hidden)')) return;
                // Don't fight: if another field is already trapped, skip
                if (_imActiveMandatory && _imActiveMandatory !== req) return;
                validateRequiredSelection(req);
            });
        });

        form.addEventListener('submit', function(e) {
            e.preventDefault();
            // prevent-double-submit.js marks form as submitting before this handler.
            // Re-enable here so validation-return paths don't leave Save disabled.
            if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                window.reEnableFormSubmit(form);
            }
            const runItemmasterSave = () => {
            try {
                // If user typed variant editor fields but did not press +,
                // auto-stage that row so Save always includes it.
                const pendingVariant = {
                    slno: String(document.getElementById('alternate_slno')?.value || '').trim(),
                    description: String(document.getElementById('alternate_description')?.value || '').trim(),
                    barcode: String(document.getElementById('alternate_barcode')?.value || '').trim(),
                    uom: String(document.getElementById('alternate_uom_code')?.value || '').trim(),
                    factor: String(document.getElementById('alternate_conversion_factor')?.value || '').trim(),
                    wholesale: String(document.getElementById('alternate_wholesale_price')?.value || '').trim(),
                    retail: String(document.getElementById('alternate_retail_price')?.value || '').trim(),
                    third: String(document.getElementById('alternate_third_price')?.value || '').trim(),
                    branch: String(document.getElementById('alternate_branch_price')?.value || '').trim(),
                };
                const hasPendingVariantInput = Object.values(pendingVariant).some((v) => String(v || '').trim() !== '');
                if (hasPendingVariantInput) {
                    const altBarcodeVal = String(document.getElementById('alternate_barcode')?.value || '').trim();
                    if (altBarcodeVal) {
                        let missingId = '';
                        for (const id of variantRequiredFieldIds) {
                            if (!getVariantFieldValue(id)) {
                                missingId = id;
                                break;
                            }
                        }
                        variantRequiredFieldIds.forEach(clearVariantFieldError);
                        if (missingId) {
                            markVariantFieldError(missingId);
                            const el = document.getElementById(missingId);
                            if (el) {
                                setActiveTabByName('variant');
                                el.focus();
                                el.select?.();
                            }
                            if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                                window.reEnableFormSubmit(form);
                            }
                            return;
                        }
                    }
                    const uomNeed = String(document.getElementById('alternate_uom_code')?.value || '').trim();
                    const facNeed = String(document.getElementById('alternate_conversion_factor')?.value || '').trim();
                    if (!uomNeed || !facNeed) {
                        setActiveTabByName('variant');
                        alert('Enter Alternate UOM and Conversion Factor for the variant row before saving.');
                        if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                            window.reEnableFormSubmit(form);
                        }
                        return;
                    }
                    saveVariantInline({ allowStagingWithoutItemCode: true });
                }

                const formData = new FormData(form);
                // Remove literal none-like text before submit.
                Array.from(formData.entries()).forEach(([k, v]) => {
                    if (typeof v !== 'string') return;
                    const cleaned = normalizeNoneLike(v);
                    if (cleaned !== v) {
                        formData.set(k, cleaned);
                    }
                });
                const variantRowsPayload = Array.from(document.querySelectorAll('.alt-variant-row')).map((r) => {
                    const row = {
                        slno: String(r.dataset.slno || '').trim(),
                        description: String(r.dataset.description || '').trim(),
                        manufacturer_id: String(r.dataset.barcode || '').trim(),
                        alternate_uom_code: String(r.dataset.uom || '').trim(),
                        conversion_factor: String(r.dataset.factor || '').trim(),
                        cost_price: String(r.dataset.cost || '').trim(),
                        wholesale_price: String(r.dataset.wholesale || '').trim(),
                        retail_price: String(r.dataset.retail || '').trim(),
                        third_price: String(r.dataset.third || '').trim(),
                        branch_price: String(r.dataset.branch || '').trim(),
                    };
                    if (r.dataset.mirrorBase === '1' || r.dataset.isBase === '1') {
                        row.mirror_itemmaster = true;
                        row.is_base = true;
                    }
                    return row;
                });
                formData.set('alternate_uoms_json', JSON.stringify(variantRowsPayload));
            if (requireTargetDb) {
                const targets = hoTargetTenantChecks()
                    .filter((el) => !!el.checked)
                    .map((el) => (el.value || '').trim())
                    .filter((x) => !!x);
                const isUpdateMode = !getIsNewMode();
                if (isUpdateMode) {
                    const newSelectedTargets = targets.filter((t) => !existingTargets.has(t));
                    if (newSelectedTargets.length) {
                        alert('Use Remap button for new selected DBs. Update can sync only fetched DBs.');
                        if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                            window.reEnableFormSubmit(form);
                        }
                        return;
                    }
                } else if (!targets.length) {
                    alert('Please select at least one target DB');
                    if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                        window.reEnableFormSubmit(form);
                    }
                    return;
                }
                formData.delete('target_tenant_ids');
                targets.forEach((t) => formData.append('target_tenant_ids', t));
            }
            formData.set('save_mode', getIsNewMode() ? 'save' : 'update');
            
            // Validate required fields
            const itemName = formData.get('item_name');
            const categoryCode = formData.get('category_code') || document.getElementById('category_code_hidden')?.value;
            const baseUom = formData.get('base_uom') || document.getElementById('base_uom_hidden')?.value;
            const alternateUom = formData.get('alternate_uom_code') || document.getElementById('alternate_uom_code')?.value;
            const salesAccount = (document.getElementById('sales_account')?.value || '').trim();
            const purchaseAccount = (document.getElementById('purchase_account')?.value || '').trim();
            const inventoryAccount = (document.getElementById('inventory_account')?.value || '').trim();
            const cogsAccount = (document.getElementById('cogs_account')?.value || '').trim();

            for (const req of requiredSelections) {
                if (!validateRequiredSelection(req)) {
                    if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                        window.reEnableFormSubmit(form);
                    }
                    return;
                }
            }
            
            if (!itemName || !categoryCode || categoryCode === '0' || !baseUom) {
                alert('Please fill in all required fields: Item Name, Category, and Base UOM');
                if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                    window.reEnableFormSubmit(form);
                }
                return;
            }
            if (!salesAccount || !purchaseAccount || !inventoryAccount || !cogsAccount) {
                alert('Please fill in all required account fields: Sales, Purchase, Inventory, and COGS.');
                if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                    window.reEnableFormSubmit(form);
                }
                return;
            }
            const mirrorRowsOnSave = Array.from(document.querySelectorAll('.alt-variant-row[data-mirror-base="1"]'));
            const editorMirror = alternateUom && baseUom && alternateUom === baseUom
                && String(formData.get('alternate_conversion_factor') || document.getElementById('alternate_conversion_factor')?.value || '').trim() === '1';
            if (alternateUom && baseUom && alternateUom === baseUom && !editorMirror && !mirrorRowsOnSave.length) {
                alert('Alternate UOM cannot match Base UOM. Please use another UOM.');
                if (window && typeof window.reEnableFormSubmit === 'function' && form) {
                    window.reEnableFormSubmit(form);
                }
                return;
            }

            // Show loading
            setSavingUi(true);

            fetch(form.action, {
                method: 'POST',
                body: formData
            })
            .then(async (response) => {
                const contentType = String(response.headers.get('content-type') || '').toLowerCase();
                let data = null;
                let rawText = '';
                try {
                    if (contentType.includes('application/json')) {
                        data = await response.json();
                    } else {
                        rawText = await response.text();
                    }
                } catch (e) {
                    rawText = rawText || '';
                }
                if (!response.ok) {
                    const msg = (data && (data.error || data.message))
                        || (rawText && rawText.trim())
                        || `Save failed (HTTP ${response.status})`;
                    throw new Error(msg);
                }
                if (!data) {
                    const msg = (rawText && rawText.trim()) || 'Unexpected save response.';
                    throw new Error(msg);
                }
                return data;
            })
            .then((data) => {
                if (data.success) {
                    alert(data.message || 'Item saved successfully!');
                    // Backend-driven redirect takes priority (used by central save flow).
                    if (data.redirect_url) {
                        window.location.href = data.redirect_url;
                        return;
                    }
                    // In item request mode redirect to the request list
                    if (isItemRequestMode && listUrl) {
                        window.location.href = listUrl;
                        return;
                    }
                    // Default save flow: go to itemmaster list.
                    window.location.href = listUrl || '/productlist';
                } else {
                    showSaveError(data.error || 'Failed to save item');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                const errMsg = (error && error.message) ? error.message : 'An error occurred while saving the item';
                showSaveError(errMsg);
            });
            } catch (error) {
                console.error('[itemmaster submit error]', error);
                showSaveError((error && error.message) ? error.message : 'Unexpected save error');
            }
            };
            if (!getIsNewMode()) {
                ensureVariantsLoaded().finally(runItemmasterSave);
            } else {
                runItemmasterSave();
            }
        });
    }

    // Auto-generate manufacturer ID if empty
    if (!isItemRequestMode && manufacturerIdInput && itemCodeInput) {
        itemCodeInput.addEventListener('blur', function() {
            if (!manufacturerIdInput.value && itemCodeInput.value) {
                manufacturerIdInput.value = itemCodeInput.value;
            }
        });
    }

    // Item Name should be uppercase while typing/pasting.
    if (itemNameInput) {
        const toUpperItemName = () => {
            const v = String(itemNameInput.value || '');
            itemNameInput.value = v.toUpperCase();
        };
        itemNameInput.addEventListener('input', toUpperItemName);
        itemNameInput.addEventListener('change', toUpperItemName);
        toUpperItemName();
    }

    // Set branch price = cost price when cost price changes
    const costPriceInput = document.getElementById('cost_price');
    const branchPriceInput = document.getElementById('branch_price');
    const wholesalePriceInput = document.getElementById('wholesale_price');
    const retailPriceInput = document.getElementById('retail_price');
    const thirdPriceInput = document.getElementById('third_price');
    const alternateConversionInput = document.getElementById('alternate_conversion_factor');
    const alternateCostPriceInput = document.getElementById('alternate_cost_price');
    const alternateWholesalePriceInput = document.getElementById('alternate_wholesale_price');
    const alternateRetailPriceInput = document.getElementById('alternate_retail_price');
    const alternateThirdPriceInput = document.getElementById('alternate_third_price');
    const alternateBranchPriceInput = document.getElementById('alternate_branch_price');
    if (costPriceInput && branchPriceInput) {
        costPriceInput.addEventListener('change', function() {
            if (!branchPriceInput.value || branchPriceInput.value === '0') {
                branchPriceInput.value = costPriceInput.value;
            }
        });
    }
    if (retailPriceInput && wholesalePriceInput && thirdPriceInput) {
        retailPriceInput.addEventListener('input', function() {
            const v = retailPriceInput.value;
            wholesalePriceInput.value = v;
            thirdPriceInput.value = v;
        });
    }
    if (alternateConversionInput) {
        const updateAlternatePrices = () => {
            const factor = parseFloat(alternateConversionInput.value);
            if (Number.isNaN(factor)) {
                if (alternateCostPriceInput) alternateCostPriceInput.value = '';
                if (alternateWholesalePriceInput) alternateWholesalePriceInput.value = '';
                if (alternateRetailPriceInput) alternateRetailPriceInput.value = '';
                if (alternateThirdPriceInput) alternateThirdPriceInput.value = '';
                if (alternateBranchPriceInput) alternateBranchPriceInput.value = '';
                return;
            }

            const calc = (value, decimals) => {
                const num = parseFloat(value);
                if (Number.isNaN(num)) return '';
                return (factor * num).toFixed(decimals);
            };

            if (alternateCostPriceInput && costPriceInput) {
                alternateCostPriceInput.value = calc(costPriceInput.value, 3);
            }
            if (alternateWholesalePriceInput && wholesalePriceInput) {
                alternateWholesalePriceInput.value = calc(wholesalePriceInput.value, 2);
            }
            if (alternateRetailPriceInput && retailPriceInput) {
                alternateRetailPriceInput.value = calc(retailPriceInput.value, 2);
            }
            if (alternateThirdPriceInput && thirdPriceInput) {
                alternateThirdPriceInput.value = calc(thirdPriceInput.value, 2);
            }
            if (alternateBranchPriceInput && branchPriceInput) {
                alternateBranchPriceInput.value = calc(branchPriceInput.value, 2);
            }
        };

        alternateConversionInput.addEventListener('input', updateAlternatePrices);
        if (costPriceInput) costPriceInput.addEventListener('input', updateAlternatePrices);
        if (wholesalePriceInput) wholesalePriceInput.addEventListener('input', updateAlternatePrices);
        if (retailPriceInput) retailPriceInput.addEventListener('input', updateAlternatePrices);
        if (thirdPriceInput) thirdPriceInput.addEventListener('input', updateAlternatePrices);
        if (branchPriceInput) branchPriceInput.addEventListener('input', updateAlternatePrices);
    }

    if (costPriceInput) {
        ['focus', 'click', 'change', 'blur'].forEach((ev) => {
            costPriceInput.addEventListener(ev, () => applyCategoryPriceMarkupFromCost());
        });
    }

    // Initialize all popup modals
    const popupConfigs = [
        { type: 'mainCategory', modalId: 'mainCategoryModal', inputId: 'main_category', codeId: 'main_category_code', clearId: 'mainCategoryClear', pickerId: 'mainCategoryPicker' },
        { type: 'department', modalId: 'departmentModal', inputId: 'department_code', codeId: 'department_code_hidden', clearId: 'departmentClear', pickerId: 'departmentPicker' },
        { type: 'category', modalId: 'categoryModal', inputId: 'category_code', codeId: 'category_code_hidden', clearId: 'categoryClear', pickerId: 'categoryPicker' },
        { type: 'brand', modalId: 'brandModal', inputId: 'brand_code', codeId: 'brand_code_hidden', clearId: 'brandClear', pickerId: 'brandPicker' },
        { type: 'property', modalId: 'propertyModal', inputId: 'property', codeId: 'property_code', clearId: 'propertyClear', pickerId: 'propertyPicker' },
        { type: 'origin', modalId: 'originModal', inputId: 'origin', codeId: 'origin_code', clearId: 'originClear', pickerId: 'originPicker' },
        { type: 'baseUom', modalId: 'baseUomModal', inputId: 'base_uom', codeId: 'base_uom_hidden', clearId: 'baseUomClear', pickerId: 'baseUomPicker' },
        { type: 'alternateUom', modalId: 'alternateUomModal', inputId: 'alternate_uom_display', codeId: 'alternate_uom_code', clearId: 'alternateUomClear', pickerId: 'alternateUomPicker' },
        { type: 'supplier', modalId: 'supplierModal', inputId: 'sup_code', codeId: 'sup_code_hidden', clearId: 'supplierClear', pickerId: 'supplierPicker' },
        ...(isItemRequestMode
            ? [{ type: 'requestLocation', modalId: 'storeModal', inputId: 'dbocode_display', codeId: 'dbocode_hidden', clearId: 'dbocodeClear', pickerId: 'dbocodePicker' }]
            : [{ type: 'warehouse', modalId: 'storeModal', inputId: 'default_warehouse_display', codeId: 'default_warehouse_id', clearId: 'defaultWarehouseClear', pickerId: 'defaultWarehousePicker' }])
    ];
    if (document.getElementById('defaultBinModal')) {
        popupConfigs.push(
            { type: 'defaultBin', modalId: 'defaultBinModal', inputId: 'default_bin_display', codeId: 'default_bin_storage_id', clearId: 'defaultBinClear', pickerId: 'defaultBinPicker' }
        );
    }

    const bootstrapLookupTableByType = {
        mainCategory: 'mainCategoryModalTable',
        brand: 'brandModalTable',
        baseUom: 'baseUomModalTable',
        alternateUom: 'alternateUomModalTable',
        supplier: 'supplierModalTable',
        property: 'propertyModalTable',
        origin: 'originModalTable',
        warehouse: 'storeModalTable',
        store: 'storeModalTable',
        requestLocation: 'storeModalTable',
    };
    const bootstrapLookupPromises = {};
    const resolveBootstrapApiUrl = () =>
        (typeof window !== 'undefined' && window.IM_BOOTSTRAP_API) ||
        (form && form.dataset && form.dataset.bootstrapApi) ||
        '';
    const modalTableHasRows = (tableId) => {
        const table = document.getElementById(tableId);
        return !!(table && table.querySelector('tbody tr[data-code]'));
    };
    const bootstrapLookupLoadedTypes = new Set(
        Object.keys(bootstrapLookupTableByType).filter((type) => modalTableHasRows(bootstrapLookupTableByType[type]))
    );
    const ensureBootstrapLookupsLoaded = (type) => {
        const url = resolveBootstrapApiUrl();
        if (!url) return Promise.resolve();
        const lookupType = String(type || '').trim();
        if (!lookupType) return Promise.resolve();
        const tableId = bootstrapLookupTableByType[lookupType];
        if (!tableId) return Promise.resolve();
        if (modalTableHasRows(tableId) || bootstrapLookupLoadedTypes.has(lookupType)) return Promise.resolve();
        if (bootstrapLookupPromises[lookupType]) return bootstrapLookupPromises[lookupType];
        const sep = url.indexOf('?') >= 0 ? '&' : '?';
        bootstrapLookupPromises[lookupType] = fetch(`${url}${sep}kinds=${encodeURIComponent(lookupType)}`, { credentials: 'same-origin' })
            .then((r) => {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then((data) => {
                if (!data || !data.success || !data.lookups) return;
                const rows = data.lookups[lookupType] || [];
                populateModalTable(tableId, rows);
                bootstrapLookupLoadedTypes.add(lookupType);
                delete bootstrapLookupPromises[lookupType];
            })
            .catch((err) => {
                delete bootstrapLookupPromises[lookupType];
                console.warn('Item Master bootstrap lookup failed:', err);
            });
        return bootstrapLookupPromises[lookupType];
    };

    popupConfigs.forEach(config => {
        initializePopup(config);
    });

    // Item account popup bindings (Sales/Purchase/Inventory/COGS)
    const itemAccountModal = document.getElementById('itemAccountModal');
    const itemAccountModalSearch = document.getElementById('itemAccountModalSearch');
    const itemAccountModalClear = document.getElementById('itemAccountModalClear');
    const itemAccountModalTable = document.getElementById('itemAccountModalTable');
    const accountFieldConfigs = [
        { displayId: 'sales_account_display', valueId: 'sales_account', pickerId: 'salesAccountPicker' },
        { displayId: 'purchase_account_display', valueId: 'purchase_account', pickerId: 'purchaseAccountPicker' },
        { displayId: 'inventory_account_display', valueId: 'inventory_account', pickerId: 'inventoryAccountPicker' },
        { displayId: 'cogs_account_display', valueId: 'cogs_account', pickerId: 'cogsAccountPicker' },
    ];
    const accountPickerByDisplayId = {};
    let activeAccountFieldConfig = null;
    let activeAccountTriggerEl = null;
    let itemAccountsFetchPromise = null;

    const resolveItemAccountsApiUrl = () =>
        (typeof window !== 'undefined' && window.IM_ITEM_ACCOUNTS_API) ||
        (form && form.dataset && form.dataset.itemAccountsApi) ||
        '';

    const fillItemAccountRowsFromApi = (accounts) => {
        if (!itemAccountModalTable) return;
        const tb = itemAccountModalTable.querySelector('tbody');
        if (!tb) return;
        tb.innerHTML = '';
        (accounts || []).forEach((acc) => {
            const code = String(acc && acc.code != null ? acc.code : '');
            const name = String(acc && acc.name != null ? acc.name : '');
            const typ = String(acc && acc.type != null ? acc.type : '');
            const tr = document.createElement('tr');
            tr.dataset.code = code;
            tr.dataset.name = name;
            tr.dataset.text = `${code} ${name} ${typ}`.toLowerCase();
            const td1 = document.createElement('td');
            td1.textContent = code;
            const td2 = document.createElement('td');
            td2.textContent = name;
            const td3 = document.createElement('td');
            td3.textContent = typ;
            tr.appendChild(td1);
            tr.appendChild(td2);
            tr.appendChild(td3);
            tb.appendChild(tr);
        });
        refreshRowTabIndex(itemAccountModalTable);
    };

    const ensureItemAccountsLoaded = () => {
        const url = resolveItemAccountsApiUrl();
        if (!url || !itemAccountModalTable) {
            return Promise.resolve();
        }
        if (itemAccountsFetchPromise) {
            return itemAccountsFetchPromise;
        }
        itemAccountsFetchPromise = fetch(url, { credentials: 'same-origin' })
            .then((r) => {
                if (!r.ok) {
                    itemAccountsFetchPromise = null;
                    return Promise.reject(new Error('HTTP ' + r.status));
                }
                return r.json();
            })
            .then((d) => {
                if (!d || !d.success || !Array.isArray(d.accounts)) {
                    itemAccountsFetchPromise = null;
                    return;
                }
                if (d.accounts.length > 0) {
                    fillItemAccountRowsFromApi(d.accounts);
                }
                // success with empty list: keep resolved promise (avoid refetch loop); server-rendered rows stay
            })
            .catch(() => {
                itemAccountsFetchPromise = null;
            });
        return itemAccountsFetchPromise;
    };

    const getVisibleModalRows = (table) => {
        if (!table) return [];
        return Array.from(table.querySelectorAll('tbody tr')).filter((row) => row.style.display !== 'none');
    };
    const refreshRowTabIndex = (table) => {
        const visibleRows = getVisibleModalRows(table);
        visibleRows.forEach((row) => row.setAttribute('tabindex', '0'));
    };
    const focusModalRowAt = (table, idx) => {
        const visibleRows = getVisibleModalRows(table);
        if (!visibleRows.length) return false;
        const safeIdx = Math.max(0, Math.min(idx, visibleRows.length - 1));
        visibleRows[safeIdx].focus();
        return true;
    };
    const focusNextVisibleRow = (table, currentRow, dir, fallbackEl) => {
        const visibleRows = getVisibleModalRows(table);
        if (!visibleRows.length) return false;
        const idx = visibleRows.indexOf(currentRow);
        if (idx < 0) return false;
        const nextIdx = idx + dir;
        if (nextIdx < 0) {
            if (fallbackEl) fallbackEl.focus();
            return true;
        }
        if (nextIdx >= visibleRows.length) return true;
        visibleRows[nextIdx].focus();
        return true;
    };

    const filterAccountModalRows = (searchTerm) => {
        if (!itemAccountModalTable) return;
        const rows = itemAccountModalTable.querySelectorAll('tbody tr');
        const term = (searchTerm || '').toLowerCase();
        rows.forEach((row) => {
            const text = (row.dataset.text || '').toLowerCase();
            row.style.display = !term || text.includes(term) ? '' : 'none';
        });
        refreshRowTabIndex(itemAccountModalTable);
    };

    const closeItemAccountModal = () => {
        if (!itemAccountModal) return;
        itemAccountModal.classList.add('hidden');
        if (activeAccountTriggerEl) {
            setTimeout(() => {
                activeAccountTriggerEl.focus();
                activeAccountTriggerEl.select?.();
            }, 0);
        }
    };

    const selectItemAccountRow = (row) => {
        if (viewOnly) return;
        if (!row || !row.dataset.code || !activeAccountFieldConfig) return;
        const code = row.dataset.code || '';
        const name = row.dataset.name || '';
        const displayInput = document.getElementById(activeAccountFieldConfig.displayId);
        const valueInput = document.getElementById(activeAccountFieldConfig.valueId);
        if (displayInput) displayInput.value = code ? `${code} - ${name}` : '';
        if (valueInput) valueInput.value = code;
        // After selection, keep focus on the same account text field.
        if (displayInput) activeAccountTriggerEl = displayInput;
        closeItemAccountModal();
    };

    const openItemAccountModal = (cfg, sourceEl = null) => {
        if (viewOnly) return;
        if (!itemAccountModal) return;
        activeAccountFieldConfig = cfg;
        activeAccountTriggerEl = sourceEl || document.getElementById(cfg.displayId) || null;
        const finishOpen = () => {
            itemAccountModal.classList.remove('hidden');
            if (itemAccountModalSearch) {
                itemAccountModalSearch.value = '';
                filterAccountModalRows('');
                itemAccountModalSearch.focus();
            }
        };
        if (resolveItemAccountsApiUrl()) {
            ensureItemAccountsLoaded().then(finishOpen).catch(finishOpen);
        } else {
            finishOpen();
        }
    };

    accountFieldConfigs.forEach((cfg) => {
        if (viewOnly || isItemRequestMode || accountsLocked) {
            const displayInput = document.getElementById(cfg.displayId);
            const pickerBtn = document.getElementById(cfg.pickerId);
            if (displayInput) displayInput.readOnly = true;
            if (pickerBtn) {
                pickerBtn.disabled = true;
                pickerBtn.setAttribute('aria-disabled', 'true');
            }
            return;
        }
        const displayInput = document.getElementById(cfg.displayId);
        const pickerBtn = document.getElementById(cfg.pickerId);
        if (!displayInput || !pickerBtn) return;
        accountPickerByDisplayId[cfg.displayId] = cfg.pickerId;
        pickerBtn.addEventListener('click', () => openItemAccountModal(cfg, pickerBtn));
        displayInput.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                openItemAccountModal(cfg, displayInput);
            }
        });
    });

    if (itemAccountModal) {
        itemAccountModal.addEventListener('click', (e) => {
            if (e.target.dataset.close === 'itemAccountModal' || e.target.classList.contains('modal__close')) {
                closeItemAccountModal();
            }
        });
        itemAccountModal.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                closeItemAccountModal();
            }
        });
    }
    if (itemAccountModalSearch) {
        itemAccountModalSearch.addEventListener('input', (e) => filterAccountModalRows(e.target.value));
        itemAccountModalSearch.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                closeItemAccountModal();
                return;
            }
            if (e.key === 'Enter' || e.key === 'ArrowDown') {
                e.preventDefault();
                if (!focusModalRowAt(itemAccountModalTable, 0)) {
                    alert('No selection found.');
                }
            }
        });
    }
    if (itemAccountModalClear) {
        itemAccountModalClear.addEventListener('click', () => {
            if (!itemAccountModalSearch) return;
            itemAccountModalSearch.value = '';
            filterAccountModalRows('');
            itemAccountModalSearch.focus();
        });
    }
    if (itemAccountModalTable) {
        itemAccountModalTable.addEventListener('click', (e) => {
            const row = e.target.closest('tr');
            selectItemAccountRow(row);
        });
        itemAccountModalTable.addEventListener('keydown', (e) => {
            const row = e.target.closest('tr');
            if (!row) return;
            if (e.key === 'Enter') {
                e.preventDefault();
                selectItemAccountRow(row);
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                focusNextVisibleRow(itemAccountModalTable, row, 1, itemAccountModalSearch);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                focusNextVisibleRow(itemAccountModalTable, row, -1, itemAccountModalSearch);
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                closeItemAccountModal();
            }
        });
    }

    // Reliable keyboard trigger for popup fields (F1 on focused text field).
    const popupPickerByInputId = {};
    popupConfigs.forEach((cfg) => {
        popupPickerByInputId[cfg.inputId] = cfg.pickerId;
    });
    const handlePopupF1 = (e) => {
        if (e.key !== 'F1') return;
        const active = document.activeElement;
        if (!active || !active.id) return;
        const pickerId = popupPickerByInputId[active.id] || accountPickerByDisplayId[active.id];
        if (!pickerId) return;
        const picker = document.getElementById(pickerId);
        if (!picker) return;
        e.preventDefault();
        e.stopPropagation();
        picker.click();
    };
    document.addEventListener('keydown', handlePopupF1, true);
    window.addEventListener('keydown', handlePopupF1, true);

    const resolveDefaultBinsApiUrl = () =>
        (typeof window !== 'undefined' && window.IM_DEFAULT_BINS_API) || '';
    const currentDefaultWarehouseId = () => {
        const hidden = document.getElementById('default_warehouse_id');
        return String((hidden && hidden.value) || '').trim();
    };
    const populateDefaultBinTable = (bins) => {
        const table = document.getElementById('defaultBinModalTable');
        const tbody = table ? table.querySelector('tbody') : null;
        if (!tbody) return;
        tbody.innerHTML = '';
        const noneRow = document.createElement('tr');
        noneRow.tabIndex = 0;
        noneRow.dataset.binNone = '1';
        noneRow.dataset.text = 'none no bin clear empty';
        const noneCell = document.createElement('td');
        noneCell.colSpan = 2;
        noneCell.textContent = '\u2014 No bin \u2014';
        noneRow.appendChild(noneCell);
        tbody.appendChild(noneRow);
        (bins || []).forEach((bin) => {
            const sid = String(bin && bin.storage_id != null ? bin.storage_id : '');
            const code = String(bin && bin.code != null ? bin.code : '').trim();
            if (!sid || !code) return;
            const name = String(bin && bin.name != null ? bin.name : '').trim();
            const row = document.createElement('tr');
            row.tabIndex = 0;
            row.dataset.code = sid;
            row.dataset.binCode = code;
            row.dataset.name = name;
            row.dataset.locKey = String(bin && bin.loc_key != null ? bin.loc_key : '');
            row.dataset.text = `${code} ${name}`.toLowerCase();
            const codeCell = document.createElement('td');
            codeCell.textContent = code;
            const nameCell = document.createElement('td');
            nameCell.textContent = name || '\u2014';
            row.appendChild(codeCell);
            row.appendChild(nameCell);
            tbody.appendChild(row);
        });
        refreshRowTabIndex(table);
    };
    let defaultBinsLoadedWh = null;
    let defaultBinsFetchPromise = null;
    const ensureDefaultBinsForCurrentWarehouse = () => {
        const url = resolveDefaultBinsApiUrl();
        const whId = currentDefaultWarehouseId();
        if (!url) return Promise.resolve();
        if (!whId) {
            defaultBinsLoadedWh = '';
            populateDefaultBinTable([]);
            return Promise.resolve();
        }
        if (defaultBinsLoadedWh === whId) return Promise.resolve();
        if (defaultBinsFetchPromise) return defaultBinsFetchPromise;
        const sep = url.indexOf('?') >= 0 ? '&' : '?';
        defaultBinsFetchPromise = fetch(`${url}${sep}wh=${encodeURIComponent(whId)}`, { credentials: 'same-origin' })
            .then((r) => {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then((data) => {
                defaultBinsFetchPromise = null;
                if (!data || !data.success) throw new Error((data && data.error) || 'Failed to load bins');
                populateDefaultBinTable(data.bins || []);
                defaultBinsLoadedWh = whId;
            })
            .catch((err) => {
                defaultBinsFetchPromise = null;
                console.warn('Item Master default bins failed:', err);
                populateDefaultBinTable([]);
            });
        return defaultBinsFetchPromise;
    };
    if (document.getElementById('defaultBinModal') && !viewOnly) {
        const whOnLoad = currentDefaultWarehouseId();
        if (whOnLoad) {
            ensureDefaultBinsForCurrentWarehouse().catch(() => {});
        }
    }
    const clearDefaultBinSelection = () => {
        const display = document.getElementById('default_bin_display');
        const hidden = document.getElementById('default_bin_storage_id');
        const clearBtn = document.getElementById('defaultBinClear');
        if (display) display.value = '';
        if (hidden) hidden.value = '';
        if (clearBtn) clearBtn.style.display = 'none';
    };

    function initializePopup(config) {
        const input = document.getElementById(config.inputId);
        const picker = document.getElementById(config.pickerId);
        const clear = document.getElementById(config.clearId);
        const modal = document.getElementById(config.modalId);
        const modalSearch = document.getElementById(config.modalId + 'Search');
        const modalClear = document.getElementById(config.modalId + 'Clear');
        const modalTable = document.getElementById(config.modalId + 'Table');
        const codeInput = document.getElementById(config.codeId);

        if (!input || !picker || !modal || !modalTable) return;
        if (viewOnly) {
            input.readOnly = true;
            picker.disabled = true;
            picker.setAttribute('aria-disabled', 'true');
            if (clear) {
                clear.disabled = true;
                clear.setAttribute('aria-disabled', 'true');
            }
            return;
        }
        // Treat popup fields like normal text fields.
        input.readOnly = false;
        if (config.type === 'defaultBin' || config.type === 'stagingBin') {
            input.readOnly = true;
        }

        const applyAlternateUomBlock = () => {
            if (config.type !== 'alternateUom') return;
            const used = new Set();
            const baseUom = (document.getElementById('base_uom_hidden')?.value || '').trim().toUpperCase();
            if (baseUom) used.add(baseUom);
            document.querySelectorAll('.alt-variant-row').forEach((r) => {
                const u = (r.dataset.uom || '').trim().toUpperCase();
                if (u) used.add(u);
            });

            // While editing an existing alternate row, allow its current UOM to remain selectable.
            const currentSlno = (document.getElementById('alternate_slno')?.value || '').trim();
            const currentEditUom = currentSlno
                ? (document.getElementById('alternate_uom_code')?.value || '').trim().toUpperCase()
                : '';
            if (currentEditUom) used.delete(currentEditUom);

            modalTable.querySelectorAll('tbody tr').forEach((row) => {
                const code = (row.dataset.code || '').trim().toUpperCase();
                row.dataset.altBlocked = (code && used.has(code)) ? '1' : '0';
            });
        };

        let popupTriggerEl = input;
        const closePopup = () => {
            modal.classList.add('hidden');
            if (popupTriggerEl) {
                setTimeout(() => {
                    popupTriggerEl.focus();
                    popupTriggerEl.select?.();
                }, 0);
            }
        };

        const applySelection = (row) => {
            if (viewOnly) return;
            if (!row) return;

            if (config.type === 'defaultBin' || config.type === 'stagingBin') {
                if (row.dataset.binNone === '1') {
                    input.value = '';
                    if (codeInput) codeInput.value = '';
                    if (clear) clear.style.display = 'none';
                    popupTriggerEl = input;
                    closePopup();
                    return;
                }
                const sid = row.dataset.code;
                if (sid === undefined || sid === null || String(sid).trim() === '') return;
                const binCode = row.dataset.binCode || '';
                const name = row.dataset.name || '';
                input.value = name ? `${binCode} — ${name}` : binCode;
                if (codeInput) codeInput.value = String(sid);
                if (clear) clear.style.display = 'block';
                popupTriggerEl = input;
                closePopup();
                return;
            }

            if (!row.dataset.code) return;

            const code = row.dataset.code;
            const name = row.dataset.name;

            // Handle special cases for "Select" options
            if (code === '0' || code === '') {
                input.value = '';
                if (codeInput) {
                    codeInput.value = code === '0' ? '0' : '';
                }
                if (clear) {
                    clear.style.display = 'none';
                }

                // Cascade clearing
                if (config.type === 'mainCategory') {
                    clearDependentFields('department', 'category');
                } else if (config.type === 'department') {
                    clearDependentFields('category');
                }
            } else {
                if (config.type === 'warehouse') {
                    const whCode = String(row.dataset.whCode || '').trim();
                    input.value = (whCode && name) ? `${whCode} — ${name}` : (whCode || name || `${code}`);
                } else {
                    input.value = name ? `${code} - ${name}` : `${code}`;
                }
                if (codeInput) {
                    codeInput.value = code;
                }
                if (config.type === 'requestLocation') {
                    input.value = `${code}`;
                    if (codeInput) codeInput.value = code;
                    const branchCode = String(row.dataset.dbkey || '').trim();
                    const branchDisplay = document.getElementById('branch_display');
                    const branchHidden = document.getElementById('branch_hidden');
                    if (branchDisplay) branchDisplay.value = branchCode;
                    if (branchHidden) branchHidden.value = branchCode;
                }
                if (clear) {
                    clear.style.display = 'block';
                }

                // Cascade updates
                if (config.type === 'mainCategory') {
                    updateDepartments(code);
                } else if (config.type === 'department') {
                    updateCategories(code);
                }
                if (config.type === 'category') {
                    setTimeout(applyCategoryPriceMarkupFromCost, 0);
                }
                if (config.type === 'baseUom') {
                    setTimeout(() => {
                        seedDefaultMirrorVariantRow();
                    }, 0);
                }
                if (config.type === 'warehouse') {
                    defaultBinsLoadedWh = null;
                    clearDefaultBinSelection();
                    ensureDefaultBinsForCurrentWarehouse().catch(() => {});
                }
            }

            // After selection, keep focus on the popup source text field.
            popupTriggerEl = input;
            closePopup();
        };

        const openPopup = async (sourceEl = null) => {
            if (viewOnly) return;
            popupTriggerEl = sourceEl || input;
            const bootstrapTableId = bootstrapLookupTableByType[config.type];
            if (bootstrapTableId && !modalTableHasRows(bootstrapTableId)) {
                await ensureBootstrapLookupsLoaded(config.type);
            }
            if (config.type === 'defaultBin') {
                const whId = currentDefaultWarehouseId();
                if (!whId) {
                    alert('Select a default warehouse before choosing a default bin.');
                    return;
                }
                await ensureDefaultBinsForCurrentWarehouse();
            }
            // For department, check if maincategory is selected first
            if (config.type === 'department') {
                const mainCategoryCode = document.getElementById('main_category_code')?.value;
                if (!mainCategoryCode || mainCategoryCode === '0') {
                    alert('Please select Main Category first');
                    return;
                }
                // Reload departments filtered by maincategory - wait for it to complete
                await updateDepartments(mainCategoryCode, true);
            }

            modal.classList.remove('hidden');
            applyAlternateUomBlock();
            if (modalSearch) {
                modalSearch.value = '';
                filterModalRows(modalTable, '');
                modalSearch.focus();
            } else {
                filterModalRows(modalTable, '');
                focusModalRowAt(modalTable, 0);
            }
        };

        picker.addEventListener('click', () => openPopup(picker));
        input.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                openPopup(input);
            }
        });

        // Close modal
        modal.addEventListener('click', (e) => {
            if (e.target.dataset.close === config.modalId || e.target.classList.contains('modal__close')) {
                closePopup();
            }
        });
        modal.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                closePopup();
            }
        });

        // Search in modal
        if (modalSearch) {
            modalSearch.addEventListener('input', (e) => {
                applyAlternateUomBlock();
                filterModalRows(modalTable, e.target.value.toLowerCase());
            });
            modalSearch.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    closePopup();
                    return;
                }
                if (e.key === 'Enter' || e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (!focusModalRowAt(modalTable, 0)) {
                        alert('No selection found.');
                    }
                }
            });
        }

        // Clear search
        if (modalClear) {
            modalClear.addEventListener('click', () => {
                if (modalSearch) {
                    modalSearch.value = '';
                    filterModalRows(modalTable, '');
                    modalSearch.focus();
                }
            });
        }

        // Select from table
        modalTable.addEventListener('click', (e) => {
            const row = e.target.closest('tr');
            applySelection(row);
        });
        modalTable.addEventListener('keydown', (e) => {
            const row = e.target.closest('tr');
            if (!row) return;
            if (e.key === 'Enter') {
                e.preventDefault();
                applySelection(row);
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                focusNextVisibleRow(modalTable, row, 1, modalSearch);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                focusNextVisibleRow(modalTable, row, -1, modalSearch);
                return;
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                closePopup();
            }
        });

        // Clear selection
        if (clear) {
            clear.addEventListener('click', () => {
                if (viewOnly) return;
                input.value = '';
            if (codeInput) {
                    codeInput.value = config.type === 'mainCategory' || config.type === 'category' || config.type === 'brand' || config.type === 'property' || config.type === 'origin' || config.type === 'color' || config.type === 'supplier' ? '0' : '';
                }
                if (config.type === 'requestLocation') {
                    const branchDisplay = document.getElementById('branch_display');
                    const branchHidden = document.getElementById('branch_hidden');
                    if (branchDisplay) branchDisplay.value = '';
                    if (branchHidden) branchHidden.value = '';
                }
                clear.style.display = 'none';
                
                // Cascade clearing
                if (config.type === 'mainCategory') {
                    clearDependentFields('department', 'category');
                } else if (config.type === 'department') {
                    clearDependentFields('category');
                }
                if (config.type === 'warehouse') {
                    defaultBinsLoadedWh = null;
                    clearDefaultBinSelection();
                    ensureDefaultBinsForCurrentWarehouse().catch(() => {});
                }
            });
        }
    }

    function filterModalRows(table, searchTerm) {
        if (!table) return;
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(row => {
            if (row.dataset.altBlocked === '1') {
                row.style.display = 'none';
                return;
            }
            const text = (row.dataset.text || '').toLowerCase();
            if (!searchTerm || text.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
        refreshRowTabIndex(table);
    }

    // Cascade functions
    function clearDependentFields(...types) {
        types.forEach(type => {
            const inputId = type === 'department' ? 'department_code' : 'category_code';
            const codeId = type === 'department' ? 'department_code_hidden' : 'category_code_hidden';
            const clearId = type === 'department' ? 'departmentClear' : 'categoryClear';
            
            const input = document.getElementById(inputId);
            const codeInput = document.getElementById(codeId);
            const clearBtn = document.getElementById(clearId);
            
            if (input) input.value = '';
            if (codeInput) codeInput.value = type === 'category' ? '0' : '';
            if (clearBtn) clearBtn.style.display = 'none';
        });
    }

    function updateDepartments(mainCategoryCode, preserveSelection = false) {
        // mainCategoryCode is the Main Category's CODE
        // Filter: Department.ID = Main Category.CODE
        if (!mainCategoryCode || mainCategoryCode === '0') {
            if (!preserveSelection) {
                clearDependentFields('department', 'category');
            }
            return Promise.resolve();
        }
        
        console.log(`[DEBUG] Filtering departments by Main Category CODE: ${mainCategoryCode}`);
        return fetch(`/api/filters/departments?maincategorycode=${mainCategoryCode}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.data) {
                    console.log(`[DEBUG] Found ${data.data.length} departments for Main Category CODE ${mainCategoryCode}`);
                    console.log(`[DEBUG] Department data:`, data.data);
                    populateModalTable('departmentModalTable', data.data);
                    // Only clear selections if not preserving (i.e., user changed main category)
                    if (!preserveSelection) {
                        clearDependentFields('department', 'category');
                    }
                } else {
                    console.warn(`[DEBUG] No departments found or API error:`, data);
                    populateModalTable('departmentModalTable', []);
                }
            })
            .catch(error => {
                console.error('Error loading departments:', error);
                populateModalTable('departmentModalTable', []);
            });
    }

    function updateCategories(departmentCode, preserveSelection = false) {
        // departmentCode is the Department's CODE
        // Filter: Category.DEPARTMENTCODE = Department.CODE
        const dept = normalizeLookupCode(departmentCode);
        if (!dept) {
            if (!preserveSelection) {
                clearDependentFields('category');
            }
            return Promise.resolve();
        }

        console.log(`[DEBUG] Filtering categories by Department CODE: ${dept}`);
        return fetch(`/api/filters/categories-filtered?departmentcode=${dept}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.data) {
                    console.log(`[DEBUG] Found ${data.data.length} categories for Department CODE ${dept}`);
                    populateModalTable('categoryModalTable', data.data);
                    if (!preserveSelection) {
                        clearDependentFields('category');
                    }
                } else {
                    populateModalTable('categoryModalTable', []);
                }
            })
            .catch(error => {
                console.error('Error loading categories:', error);
                populateModalTable('categoryModalTable', []);
            });
    }

    function populateModalTable(tableId, data) {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const tbody = table.querySelector('tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        const isWarehousePicker = tableId === 'storeModalTable' && !isItemRequestMode;
        
        data.forEach(item => {
            const row = document.createElement('tr');
            row.dataset.code = normalizeLookupCode(item.code);
            row.dataset.name = item.name;
            row.dataset.id = item.id || item.code;
            if (isWarehousePicker) {
                const whCode = String(item.warehouse_code || '').trim();
                row.dataset.whCode = whCode;
                row.dataset.text = `${item.code} ${whCode} ${item.name}`.toLowerCase();
                row.innerHTML = `
                    <td>${item.code}</td>
                    <td>${whCode || '—'}</td>
                    <td>${item.name || ''}</td>
                `;
            } else {
                row.dataset.text = `${item.code} ${item.name}`.toLowerCase();
                row.innerHTML = `
                    <td>${item.code}</td>
                    <td>${item.name}</td>
                `;
            }
            tbody.appendChild(row);
        });
    }

    (function initItemLedgerModal() {
        const ledgerBtn = document.getElementById('btnItemLedger');
        const modal = document.getElementById('itemLedgerModal');
        const tbodyLedger = document.getElementById('itemLedgerBody');
        const statusEl = document.getElementById('itemLedgerStatus');
        const tabBtns = document.querySelectorAll('[data-ledger-tab]');
        const barcodeInput = document.getElementById('itemLedgerBarcode');
        const itemCodeInput = document.getElementById('itemLedgerItemCode');
        const itemNameInput = document.getElementById('itemLedgerItemName');
        const loadBtn = document.getElementById('itemLedgerLoadBtn');
        if (!form || !modal || !tbodyLedger || !ledgerBtn) return;

        const cache = {};
        let cacheItemCode = '';
        let activeLedgerTab = 'purchase';

        function closeLedgerModal() {
            modal.classList.add('hidden');
        }

        function openLedgerModal() {
            modal.classList.remove('hidden');
        }

        function ledgerBaseUrl() {
            return (form.getAttribute('data-item-ledger-url') || '').trim();
        }

        function formItemCode() {
            const el = document.getElementById('item_code');
            return el ? String(el.value || '').trim() : '';
        }

        function formBarcode() {
            const el = document.getElementById('manufacturer_id');
            return el ? String(el.value || '').trim() : '';
        }

        function formItemName() {
            const el = document.getElementById('item_name');
            return el ? String(el.value || '').trim() : '';
        }

        function syncLedgerSearchFromForm() {
            if (itemCodeInput) itemCodeInput.value = formItemCode();
            if (barcodeInput && !String(barcodeInput.value || '').trim()) {
                barcodeInput.value = formBarcode();
            }
            if (itemNameInput) itemNameInput.value = formItemName();
        }

        function currentLedgerItemCode() {
            if (itemCodeInput) {
                const v = String(itemCodeInput.value || '').trim();
                if (v) return v;
            }
            return formItemCode();
        }

        function currentLedgerBarcode() {
            return barcodeInput ? String(barcodeInput.value || '').trim() : '';
        }

        function clearLedgerCache() {
            Object.keys(cache).forEach((k) => delete cache[k]);
            cacheItemCode = '';
        }

        function escCell(v) {
            if (v === null || v === undefined) return '';
            const td = document.createElement('td');
            td.textContent = String(v);
            return td.textContent;
        }

        function fmtNum(v, decimals) {
            const n = Number.parseFloat(v);
            if (Number.isFinite(n)) return n.toFixed(decimals);
            return '';
        }

        /** Ledger optional numeric: null/undefined/non-numeric → em dash */
        function fmtLedgerDash(v, decimals) {
            if (v === null || v === undefined || v === '') return '\u2014';
            const n = Number.parseFloat(v);
            if (!Number.isFinite(n)) return '\u2014';
            return n.toFixed(decimals);
        }

        function setLedgerTableHeader(tabName) {
            const partyTh = document.querySelector('#itemLedgerTable th.im-ledger-party');
            if (!partyTh) return;
            partyTh.textContent = tabName === 'stock_adjustment'
                ? 'Warehouse'
                : 'Supplier / customer';
        }

        function renderLedgerRows(rows) {
            tbodyLedger.innerHTML = '';
            if (!rows || rows.length === 0) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 10;
                td.style.color = '#6c757d';
                td.style.fontStyle = 'italic';
                td.textContent = 'No rows for this tab.';
                tr.appendChild(td);
                tbodyLedger.appendChild(tr);
                return;
            }
            rows.forEach((r) => {
                const tr = document.createElement('tr');
                const party =
                    (r.party_name && String(r.party_name).trim()) ||
                    (r.party_code !== undefined && r.party_code !== null && String(r.party_code).trim() !== ''
                        ? String(r.party_code)
                        : '');
                const texts = [
                    escCell(r.doc_no),
                    escCell(r.doc_date),
                    party,
                    fmtNum(r.qty, 3),
                    escCell(r.uom),
                    fmtNum(r.rate, 3),
                    fmtLedgerDash(r.bonus, 3),
                    fmtLedgerDash(r.foc, 3),
                    fmtLedgerDash(r.discount, 3),
                    fmtNum(r.amount, 3),
                ];
                texts.forEach((text, idx) => {
                    const td = document.createElement('td');
                    td.textContent = text;
                    if (idx === 2) td.classList.add('im-ledger-party');
                    if (idx === 3 || idx === 5 || idx === 6 || idx === 7 || idx === 8 || idx === 9)
                        td.classList.add('im-ledger-metric');
                    tr.appendChild(td);
                });
                tbodyLedger.appendChild(tr);
            });
        }

        async function loadLedgerTab(tabName, opts) {
            opts = opts || {};
            activeLedgerTab = tabName || 'purchase';
            setLedgerTableHeader(activeLedgerTab);
            const base = ledgerBaseUrl();
            const ic = currentLedgerItemCode();
            const bc = currentLedgerBarcode();
            if (!base) {
                statusEl.textContent = 'Missing ledger URL.';
                renderLedgerRows([]);
                return;
            }
            if (!ic && !bc) {
                statusEl.textContent = 'Enter item code or scan a barcode.';
                renderLedgerRows([]);
                return;
            }
            const ck = (ic || bc) + '|' + activeLedgerTab;
            if (!opts.forceReload && cacheItemCode === (ic || bc) && cache[ck]) {
                statusEl.textContent = cache[ck].statusText || '';
                if (itemCodeInput && cache[ck].itemCode) itemCodeInput.value = String(cache[ck].itemCode);
                if (itemNameInput && cache[ck].itemName) itemNameInput.value = String(cache[ck].itemName);
                renderLedgerRows(cache[ck].rows);
                return;
            }
            if (cacheItemCode !== (ic || bc)) {
                clearLedgerCache();
                cacheItemCode = ic || bc;
            }
            statusEl.textContent = 'Loading…';
            tbodyLedger.innerHTML = '';
            const params = new URLSearchParams();
            params.set('tab', activeLedgerTab);
            if (ic) params.set('item_code', ic);
            else if (bc) params.set('barcode', bc);
            const url = `${base}?${params.toString()}`;
            try {
                const res = await fetch(url, { credentials: 'same-origin' });
                const data = await res.json();
                if (!data.success) {
                    statusEl.textContent = data.error || 'Could not load ledger.';
                    renderLedgerRows([]);
                    return;
                }
                const rows = Array.isArray(data.rows) ? data.rows : [];
                if (data.item_code != null && itemCodeInput) {
                    itemCodeInput.value = String(data.item_code);
                    cacheItemCode = String(data.item_code);
                }
                if (data.item_name != null && itemNameInput) {
                    itemNameInput.value = String(data.item_name);
                }
                const statusText = rows.length
                    ? `${rows.length} row(s)${data.item_name ? ' — ' + data.item_name : ''}`
                    : (data.item_name ? String(data.item_name) : '');
                cache[ck] = { rows: rows, statusText: statusText, itemCode: data.item_code, itemName: data.item_name };
                statusEl.textContent = statusText;
                renderLedgerRows(rows);
            } catch (e) {
                console.error('item ledger', e);
                statusEl.textContent = 'Failed to load.';
                renderLedgerRows([]);
            }
        }

        function loadLedgerFromSearch() {
            clearLedgerCache();
            const ic = currentLedgerItemCode();
            const bc = currentLedgerBarcode();
            if (!ic && !bc) {
                statusEl.textContent = 'Enter item code or scan a barcode.';
                if (barcodeInput) barcodeInput.focus();
                return;
            }
            cacheItemCode = ic || bc;
            loadLedgerTab(activeLedgerTab, { forceReload: true });
        }

        ledgerBtn.addEventListener('click', () => {
            clearLedgerCache();
            syncLedgerSearchFromForm();
            activeLedgerTab = 'purchase';
            tabBtns.forEach((t) => {
                const active = t.getAttribute('data-ledger-tab') === 'purchase';
                t.classList.toggle('im-ledger-tab--active', active);
            });
            openLedgerModal();
            if (barcodeInput && !currentLedgerItemCode() && !currentLedgerBarcode()) {
                barcodeInput.focus();
                statusEl.textContent = 'Scan or enter barcode, or type item code.';
                renderLedgerRows([]);
                return;
            }
            loadLedgerTab('purchase', { forceReload: true });
            if (barcodeInput) barcodeInput.focus();
        });

        if (loadBtn) loadBtn.addEventListener('click', loadLedgerFromSearch);
        if (barcodeInput) {
            barcodeInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    loadLedgerFromSearch();
                }
            });
        }
        if (itemCodeInput) {
            itemCodeInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    loadLedgerFromSearch();
                }
            });
        }

        tabBtns.forEach((btn) => {
            btn.addEventListener('click', () => {
                const name = btn.getAttribute('data-ledger-tab');
                tabBtns.forEach((t) =>
                    t.classList.toggle('im-ledger-tab--active', t.getAttribute('data-ledger-tab') === name),
                );
                loadLedgerTab(name || 'purchase');
            });
        });

        modal.addEventListener('click', (e) => {
            const t = e.target;
            if (!t || typeof t.closest !== 'function') return;
            if (t.closest('[data-close="itemLedgerModal"]')) closeLedgerModal();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (!modal.classList.contains('hidden')) closeLedgerModal();
        });
    })();

    (function initItemCostingSection() {
        const section = document.getElementById('imCostingSection');
        const modal = document.getElementById('itemCostingModal');
        const triggers = section.querySelectorAll('.im-costing-trigger[data-costing-card]');
        if (!form || !section || !modal || !triggers.length) return;

        const methodTitle = document.getElementById('imCostingMethodTitle');
        const valLast = document.getElementById('imCostValLastPurchase');
        const valAvg = document.getElementById('imCostValAverage');
        const valLand = document.getElementById('imCostValLanding');
        const valCost = document.getElementById('imCostValCostPrice');
        const titleEl = document.getElementById('itemCostingModalTitle');
        const metaEl = document.getElementById('itemCostingModalMeta');
        const formulaEl = document.getElementById('itemCostingModalFormula');
        const stepsEl = document.getElementById('itemCostingModalSteps');
        const extraEl = document.getElementById('itemCostingModalExtra');
        const receiptsWrap = document.getElementById('itemCostingReceiptsWrap');
        const receiptsBody = document.getElementById('itemCostingReceiptsBody');
        const receiptsFoot = document.getElementById('itemCostingReceiptsFoot');
        const receiptsCol = document.getElementById('itemCostingReceiptsCol');
        const receiptsEmpty = document.getElementById('itemCostingReceiptsEmpty');
        const kvBody = document.getElementById('itemCostingModalKvBody');

        let cachePayload = null;
        let cacheItemCode = '';

        function costingUrl() {
            return (form.getAttribute('data-item-costing-url') || '').trim();
        }

        function currentItemCode() {
            const el = document.getElementById('item_code');
            return el ? String(el.value || '').trim() : '';
        }

        function fmt3(v) {
            const n = Number.parseFloat(v);
            return Number.isFinite(n) ? n.toFixed(3) : '\u2014';
        }

        function toggleSectionVisible() {
            const ic = currentItemCode();
            const isNew = !!(isNewInput && isNewInput.value === 'true');
            section.style.display = ic && !isNew ? '' : 'none';
        }

        function applySummary(payload) {
            if (!payload || !payload.ok) return;
            if (methodTitle && payload.costing_method) {
                methodTitle.value = String(payload.costing_method);
            }
            if (valLast) valLast.value = fmt3(payload.last_purchase_cost);
            if (valAvg) valAvg.value = fmt3(payload.average_cost);
            if (valLand) valLand.value = fmt3(payload.landing_cost);
            if (valCost) valCost.value = fmt3(payload.cost_price);
            const costInput = document.getElementById('cost_price');
            if (costInput && payload.cost_price != null) {
                const n = Number.parseFloat(payload.cost_price);
                if (Number.isFinite(n)) costInput.value = String(n);
            }
        }

        async function loadCostingSummary(force) {
            const ic = currentItemCode();
            const base = costingUrl();
            toggleSectionVisible();
            if (!ic || !base) return;
            if (!force && cacheItemCode === ic && cachePayload) {
                applySummary(cachePayload);
                return;
            }
            try {
                const res = await fetch(`${base}?item_code=${encodeURIComponent(ic)}`, { credentials: 'same-origin' });
                const data = await res.json();
                if (!data || !data.ok) return;
                cacheItemCode = ic;
                cachePayload = data;
                applySummary(data);
            } catch (e) {
                /* ignore */
            }
        }

        function closeModal() {
            modal.classList.add('hidden');
        }

        function openModal() {
            modal.classList.remove('hidden');
        }

        function renderKvTable(card, payload) {
            if (!kvBody) return;
            kvBody.innerHTML = '';
            const pairs = [
                ['Cost type', card.title || ''],
                ['Current value', card.value_label != null ? String(card.value_label) : fmt3(card.value)],
                ['Stock on hand', payload.current_stock != null ? fmt3(payload.current_stock) : '\u2014'],
                ['Costing method', payload.costing_method || '\u2014'],
                ['Data source', card.source || '\u2014'],
            ];
            pairs.forEach(([label, val]) => {
                const tr = document.createElement('tr');
                const th = document.createElement('th');
                const td = document.createElement('td');
                th.textContent = label;
                td.textContent = val;
                tr.appendChild(th);
                tr.appendChild(td);
                kvBody.appendChild(tr);
            });
        }

        function renderReceiptsTable(rows) {
            if (!receiptsBody) return;
            receiptsBody.innerHTML = '';
            const hasRows = !!(rows && rows.length);
            if (receiptsWrap) receiptsWrap.style.display = hasRows ? '' : 'none';
            if (receiptsEmpty) receiptsEmpty.style.display = hasRows ? 'none' : '';
            if (receiptsFoot) receiptsFoot.style.display = hasRows ? '' : 'none';
            if (!hasRows) return;

            let sumBaseQty = 0;
            let sumAmount = 0;
            let sumOtherCharge = 0;
            let sumLandingValue = 0;

            rows.forEach((r) => {
                const bq = Number.parseFloat(r.base_qty);
                const amt = Number.parseFloat(r.amount);
                const och = Number.parseFloat(r.other_charge);
                const lu = Number.parseFloat(r.landing_unit);
                const baseQty = Number.isFinite(bq) ? bq : 0;
                const amount = Number.isFinite(amt) ? amt : 0;
                const otherCharge = Number.isFinite(och) ? och : 0;
                const landingUnit = Number.isFinite(lu) ? lu : 0;
                sumBaseQty += baseQty;
                sumAmount += amount;
                sumOtherCharge += otherCharge;
                sumLandingValue += baseQty * landingUnit;

                const tr = document.createElement('tr');
                const cells = [
                    r.receipt_no,
                    r.receipt_date,
                    fmt3(baseQty),
                    fmt3(r.rate),
                    fmt3(amount),
                    fmt3(otherCharge),
                    fmt3(landingUnit),
                ];
                cells.forEach((text) => {
                    const td = document.createElement('td');
                    td.textContent = text === null || text === undefined ? '' : String(text);
                    tr.appendChild(td);
                });
                receiptsBody.appendChild(tr);
            });

            const weightedLanding = sumBaseQty > 1e-12 ? sumLandingValue / sumBaseQty : 0;
            const elBq = document.getElementById('itemCostingTotalBaseQty');
            const elAmt = document.getElementById('itemCostingTotalAmount');
            const elOch = document.getElementById('itemCostingTotalOtherCharge');
            const elLand = document.getElementById('itemCostingTotalLanding');
            if (elBq) elBq.textContent = fmt3(sumBaseQty);
            if (elAmt) elAmt.textContent = fmt3(sumAmount);
            if (elOch) elOch.textContent = fmt3(sumOtherCharge);
            if (elLand) elLand.textContent = fmt3(weightedLanding);
        }

        function showCardDetail(cardId) {
            const payload = cachePayload;
            if (!payload || !payload.ok) return;
            const card = (payload.cards || []).find((c) => c.id === cardId);
            if (!card) return;
            if (titleEl) titleEl.textContent = card.title || 'Costing detail';
            renderKvTable(card, payload);
            const showReceiptsCol =
                cardId === 'last_purchase' || cardId === 'landing_cost' || cardId === 'average_cost';
            modal.classList.toggle('im-costing-modal--single', !showReceiptsCol);
            if (receiptsCol) receiptsCol.style.display = showReceiptsCol ? '' : 'none';
            if (metaEl) metaEl.textContent = card.summary || '';
            if (formulaEl) formulaEl.textContent = card.formula ? 'Formula: ' + card.formula : '';
            if (stepsEl) {
                stepsEl.innerHTML = '';
                (card.steps || []).forEach((step) => {
                    const li = document.createElement('li');
                    li.textContent = String(step);
                    stepsEl.appendChild(li);
                });
            }
            if (extraEl) {
                extraEl.innerHTML = '';
                if (card.last_receipt && card.last_receipt.receipt_no) {
                    const lr = card.last_receipt;
                    const p = document.createElement('p');
                    p.style.fontSize = '12px';
                    p.style.color = '#475569';
                    p.textContent =
                        'Last receipt #' + lr.receipt_no +
                        (lr.receipt_date ? ' · ' + lr.receipt_date : '') +
                        (lr.uom ? ' · UOM ' + lr.uom : '') +
                        ' · Rate ' + fmt3(lr.rate) +
                        ' · Base qty ' + fmt3(lr.base_qty);
                    extraEl.appendChild(p);
                }
            }
            if (showReceiptsCol) {
                renderReceiptsTable(payload.recent_receipts || []);
            } else if (receiptsEmpty) {
                receiptsEmpty.style.display = 'none';
            }
            openModal();
        }

        function activateCostingRow(row) {
            const cardId = row.getAttribute('data-costing-card') || '';
            if (!cardId) return;
            loadCostingSummary(false).then(() => showCardDetail(cardId));
        }

        section.querySelectorAll('.im-costing-detail-btn').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const ic = currentItemCode();
                if (!ic) {
                    alert('Open an item with an item code first.');
                    return;
                }
                const row = btn.closest('[data-costing-card]');
                if (row) activateCostingRow(row);
            });
        });

        triggers.forEach((row) => {
            const input = row.querySelector('input.input-readonly');
            const open = () => {
                const ic = currentItemCode();
                if (!ic) {
                    alert('Open an item with an item code first.');
                    return;
                }
                activateCostingRow(row);
            };
            row.addEventListener('click', (e) => {
                if (e.target.closest('.im-costing-detail-btn')) return;
                open();
            });
            if (input) {
                input.addEventListener('click', (e) => {
                    e.stopPropagation();
                    open();
                });
            }
        });

        modal.addEventListener('click', (e) => {
            const t = e.target;
            if (!t || typeof t.closest !== 'function') return;
            if (t.closest('[data-close="itemCostingModal"]')) closeModal();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (!modal.classList.contains('hidden')) closeModal();
        });

        if (isNewInput) {
            isNewInput.addEventListener('change', toggleSectionVisible);
        }
        if (itemCodeInput) {
            itemCodeInput.addEventListener('change', () => {
                cacheItemCode = '';
                cachePayload = null;
                loadCostingSummary(true);
            });
        }

        toggleSectionVisible();
        // Do not block first paint — load costing when Pricing / costing section is near view.
        const costingSection = document.getElementById('imCostingSection') || document.getElementById('tab-pricing');
        if (costingSection && 'IntersectionObserver' in window) {
            const costingObserver = new IntersectionObserver((entries) => {
                if (!entries.some((entry) => entry.isIntersecting)) return;
                costingObserver.disconnect();
                loadCostingSummary(false);
            }, { rootMargin: '80px 0px' });
            costingObserver.observe(costingSection);
            costingSection.addEventListener('focusin', () => loadCostingSummary(false), { once: true });
            costingSection.addEventListener('pointerenter', () => loadCostingSummary(false), { once: true });
        } else {
            loadCostingSummary(false);
        }
    })();

    ['manufacturer_id', 'cost_price', 'wholesale_price', 'retail_price', 'third_price', 'branch_price', 'base_uom', 'base_uom_hidden', 'description', 'item_name'].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        const onMirrorSync = () => {
            syncMirrorVariantRowFromItemmaster();
            if (id === 'base_uom' || id === 'base_uom_hidden') seedDefaultMirrorVariantRow();
        };
        el.addEventListener('input', onMirrorSync);
        el.addEventListener('change', onMirrorSync);
    });
    setTimeout(() => {
        seedDefaultMirrorVariantRow();
        syncMirrorVariantRowFromItemmaster();
    }, 400);
});
