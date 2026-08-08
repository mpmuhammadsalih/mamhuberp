document.addEventListener('DOMContentLoaded', async () => {
    const salesItemDisplayName = (item) => {
        if (!item) return '';
        const en = String(item.itemname || '').trim();
        if (en) return en;
        return String(item.display_item_name || '').trim();
    };

    const form = document.getElementById('salesForm');
    const nextBillBase = (form?.dataset.nextBillBase || '/sales').trim();
    const saveBase = (form?.dataset.saveBase || '/sales').trim();
    const printBase = (form?.dataset.printBase || '/sales').trim();
    const enablePrint = String(form?.dataset.enablePrint || '1').trim() !== '0';
    const isSalesReturn = String(form?.dataset.isSalesReturn || '0').trim() === '1';
    let orderNoMandatory = String(form?.dataset.orderNoMandatory || '1').trim() === '1';
    const syncOrderNoMandatoryUi = () => {
        if (orderNoEl) {
            if (orderNoMandatory) orderNoEl.setAttribute('required', 'required');
            else orderNoEl.removeAttribute('required');
        }
        const reqMark = document.getElementById('orderNoRequiredMark');
        if (reqMark) reqMark.style.display = orderNoMandatory ? '' : 'none';
    };
    const refreshOrderNoMandatorySetting = async () => {
        try {
            const res = await fetch('/sales/api/form-settings', { credentials: 'same-origin' });
            const data = await res.json();
            if (data && data.success) {
                orderNoMandatory = Boolean(data.order_no_mandatory_return);
                if (form) form.dataset.orderNoMandatory = orderNoMandatory ? '1' : '0';
                syncOrderNoMandatoryUi();
            }
        } catch (ignore) {}
    };
    const openBillDate = String(window.__SALES_OPEN_BILL_DATE__ || '').trim();
    const openBillDateFrom = String(window.__SALES_OPEN_BILL_DATE_FROM__ || openBillDate || '').trim();
    const openBillDateTo = String(window.__SALES_OPEN_BILL_DATE_TO__ || openBillDateFrom || openBillDate || '').trim();
    const txnDateBlocked = Boolean(window.__SALES_TXN_DATE_BLOCKED__);
    const txnDateError = String(window.__SALES_TXN_DATE_ERROR__ || '').trim();
    const apiBase = isSalesReturn ? '/sales-return' : '/sales';
    const billNo = document.getElementById('bill_no');
    const billDate = document.getElementById('bill_date');
    const billTime = document.getElementById('bill_time');
    const billType = document.getElementById('bill_type');
    const deliveryDate = document.getElementById('delivery_date');
    const salesWarehouseCfg = window.__SALES_WAREHOUSE__ || {};
    const warehouseEnabled = !!salesWarehouseCfg.enabled;
    const salesBinCfg = window.__SALES_BIN__ || {};
    const binEnabled = !!salesBinCfg.enabled;
    const salesBatchCfg = window.__SALES_BATCH__ || {};
    const batchEnabled = !!salesBatchCfg.enabled;
    const siTableColSpan = Number(window.__SALES_TABLE_COLSPAN__ || ((warehouseEnabled ? 10 : 11) + (warehouseEnabled ? 1 : 0) + (binEnabled ? 1 : 0) + (batchEnabled ? 1 : 0)));
    const warehouseDisplay = document.getElementById('warehouseDisplay');
    const warehouseIdEl = document.getElementById('warehouse_id');
    const warehouseCodeEl = document.getElementById('warehouse_code');
    const warehouseNameEl = document.getElementById('warehouse_name');
    const warehouseClear = document.getElementById('warehouseClear');
    const warehousePicker = document.getElementById('warehousePicker');
    const remarks = document.getElementById('remarks');
    const orderNoEl = document.getElementById('order_no');
    await refreshOrderNoMandatorySetting();
    const invoiceBillNoLoad = document.getElementById('invoice_bill_no_load');
    const btnLoadInvoice = document.getElementById('btnLoadInvoice');
    const loadInvoiceApiBase = String(window.__LOAD_INVOICE_API__ || (apiBase + '/load-from-invoice')).replace(/\/$/, '');
    const loyaltyCustomerDisplay = document.getElementById('loyalty_customer_display');

    const customerDisplay = document.getElementById('customer_display');
    const customerCode = document.getElementById('customer_code');
    const customerPhone = document.getElementById('customer_phone');
    const customerName = document.getElementById('customer_name');
    const customerCategory = document.getElementById('customer_category');
    const customerAddress = document.getElementById('customer_address');
    const creditLimit = document.getElementById('credit_limit');
    const outstandingAmount = document.getElementById('outstanding_amount');
    const totalPoints = document.getElementById('total_points');
    const customerClear = document.getElementById('customerClear');
    const customerPicker = document.getElementById('customerPicker');
    const focusCustomerField = () => {
        if (customerDisplay) {
            customerDisplay.focus();
        } else if (customerPicker) {
            customerPicker.focus();
        }
    };

    const barcodeInput = document.getElementById('barcode_input');
    const itemCodeDisplay = document.getElementById('item_code');
    const itemCodeHidden = document.getElementById('item_code_hidden');
    const itemName = document.getElementById('item_name');
    const itemClear = document.getElementById('itemClear');
    const itemPicker = document.getElementById('itemPicker');
    const itemModal = document.getElementById('itemModal');
    const itemSearch = document.getElementById('itemSearch');
    const itemBody = document.getElementById('itemBody');
    const itemModalFilters = document.getElementById('itemModalFilters');
    const priceMode = document.getElementById('price_mode');
    const priceModeDisplay = document.getElementById('price_mode_display');
    const priceModeClear = document.getElementById('priceModeClear');
    const priceModePicker = document.getElementById('priceModePicker');

    const uomDisplay = document.getElementById('uom_display');
    const uomCode = document.getElementById('uom_code');
    const uomClear = document.getElementById('uomClear');
    const uomPicker = document.getElementById('uomPicker');
    const uomModalBody = document.getElementById('uomModalBody');
    const inventoryLocation = document.getElementById('inventory_location');
    const inventoryClear = document.getElementById('inventoryClear');
    const inventoryPicker = document.getElementById('inventoryPicker');
    const lineWarehouseDisplay = document.getElementById('line_warehouse_display');
    const lineWarehouseId = document.getElementById('line_warehouse_id');
    const lineWarehouseCode = document.getElementById('line_warehouse_code');
    const lineWarehouseName = document.getElementById('line_warehouse_name');
    const lineWarehouseClear = document.getElementById('lineWarehouseClear');
    const lineWarehousePicker = document.getElementById('lineWarehousePicker');
    const lineBinDisplay = document.getElementById('line_bin_display');
    const lineBinId = document.getElementById('line_bin_id');
    const lineBinCode = document.getElementById('line_bin_code');
    const lineBinName = document.getElementById('line_bin_name');
    const lineBinClear = document.getElementById('lineBinClear');
    const lineBinPicker = document.getElementById('lineBinPicker');
    const binModalBody = document.getElementById('binModalBody');
    const inventoryModalBody = document.getElementById('inventoryModalBody');

    const quantity = document.getElementById('quantity');
    const rate = document.getElementById('rate');
    const discount = document.getElementById('discount');
    const lineAmount = document.getElementById('line_amount');

    const salesLotDisplay = document.getElementById('sales_lot_display');
    const salesLotId = document.getElementById('sales_lot_id');
    const btnPickLot = document.getElementById('btnPickLot');
    const btnClearLot = document.getElementById('btnClearLot');

    const btnAddLine = document.getElementById('btnAddLine');
    const btnClearLine = document.getElementById('btnClearLine');
    const btnSave = document.getElementById('btnSave');
    const btnNew = document.getElementById('btnNew');
    const btnDiscard = document.getElementById('btnDiscard');
    const btnHistory = document.getElementById('btnHistory');
    const btnCustomerDetails = document.getElementById('btnCustomerDetails');

    const customerDetailsModal = document.getElementById('customerDetailsModal');
    const customerDetailsPhone = document.getElementById('customerDetailsPhone');
    const customerDetailsBillType = document.getElementById('customerDetailsBillType');
    const customerDetailsCreditLimit = document.getElementById('customerDetailsCreditLimit');
    const customerDetailsCategory = document.getElementById('customerDetailsCategory');
    const customerDetailsOutstanding = document.getElementById('customerDetailsOutstanding');
    const customerDetailsTotalPoints = document.getElementById('customerDetailsTotalPoints');
    const customerDetailsAddress = document.getElementById('customerDetailsAddress');

    const tableBody = document.getElementById('salesTableBody');
    const getEntryRow = () => (tableBody ? tableBody.querySelector('tr.line-entry') : null);
    const pinEntryRowToBottom = () => {
        const entry = getEntryRow();
        if (!entry || !tableBody || entry.parentNode !== tableBody) return;
        if (tableBody.lastElementChild === entry) return;
        const active = document.activeElement;
        if (active && entry.contains(active)) return;
        tableBody.appendChild(entry);
    };
    const removeTableEmpty = () => {
        const empty = tableBody?.querySelector('tr.table-empty');
        if (empty) empty.remove();
    };
    const showTableEmpty = () => {
        if (!tableBody || tableBody.querySelector('tr.table-empty')) return;
        const entry = getEntryRow();
        const tr = document.createElement('tr');
        tr.className = 'table-empty';
        tr.innerHTML = `<td colspan="${siTableColSpan}" style="text-align:center; padding:20px; color:#6b7280; font-style:italic;">No items added.</td>`;
        if (entry) tableBody.insertBefore(tr, entry);
        else tableBody.appendChild(tr);
    };
    const totalItems = document.getElementById('total_items');
    const loyaltyPoints = document.getElementById('loyalty_points');
    const totalAmount = document.getElementById('total_amount');
    const additionalDiscount = document.getElementById('additional_discount');
    const totalItemsItems = document.getElementById('total_items_items');
    const loyaltyPointsItems = document.getElementById('loyalty_points_items');
    const totalAmountItems = document.getElementById('total_amount_items');
    const additionalDiscountItems = document.getElementById('additional_discount_items');
    const totalDiscountItems = document.getElementById('total_discount_items');
    const netTotalItems = document.getElementById('net_total_items');
    const totalDiscount = document.getElementById('total_discount');
    const netTotal = document.getElementById('net_total');
    const voucherCodeInput = document.getElementById('voucher_code');
    const btnApplyVoucher = document.getElementById('btnApplyVoucher');
    const promotionDiscountEl = document.getElementById('promotion_discount');
    const promotionDiscountItemsEl = document.getElementById('promotion_discount_items');
    const appliedPromotionsEl = document.getElementById('applied_promotions');
    const initialOrderPayload = window.__INITIAL_ORDER__ || null;

    function openSavedReturnPdf(billno, pdfUrlFromServer, preOpenedWin) {
        if (!enablePrint || billno == null) return;
        const printUrl = (
            pdfUrlFromServer ||
            `/reports/crystal-reports/open/salesreturn?billno=${encodeURIComponent(billno)}`
        ).trim();
        if (!printUrl) return;
        try {
            if (preOpenedWin && !preOpenedWin.closed) {
                preOpenedWin.location = printUrl;
                try { preOpenedWin.focus(); } catch (ignore) {}
                return;
            }
            const w = window.open(printUrl, '_blank');
            if (!w) {
                // Popup blocked after async save — navigate same tab as fallback.
                window.location.assign(printUrl);
            }
        } catch (e) {
            console.warn('[sales-return] PDF open failed:', e);
            try { window.location.assign(printUrl); } catch (ignore) {}
        }
    }

    let promotionDiscount = 0;
    let appliedVouchers = [];
    let saveInFlight = false;

    const historyModal = document.getElementById('historyModal');
    const historyModalBody = document.getElementById('historyModalBody');
    const historyModalHead = document.getElementById('historyModalHead');

    const currentItem = {
        itemCode: '',
        itemName: '',
        barcode: '',
        baseUom: '',
        retail: 0,
        wholesale: 0,
        third: 0,
        branch: 0,
        cost: 0,
        factor: 1,
    };

    let editingRow = null;
    let siItemPickerCtl = null;

    const tabs = document.querySelectorAll('.itemmaster-tabs .tab');
    const tabContents = document.querySelectorAll('.tab-content');
    const headerTab = document.getElementById('tab-header');
    const headerWarehouseStoreCode = () => (warehouseCodeEl?.value || '').trim();

    const applyLineWarehouseSelection = (id, code, name) => {
        if (!warehouseEnabled) return;
        const whId = parseInt(id, 10) || 0;
        const whCode = String(code || '').trim();
        const whName = String(name || '').trim();
        setValue(lineWarehouseDisplay, formatWarehouseDisplay(whCode, whName));
        setValue(lineWarehouseId, whId || String(id || '').trim());
        setValue(lineWarehouseCode, whCode);
        setValue(lineWarehouseName, whName);
        setValue(inventoryLocation, whCode);
        showClear(lineWarehouseClear, Boolean(whCode));
        if (binEnabled && itemCodeHidden?.value) {
            resolveLineBinForItem(itemCodeHidden.value, whId);
        } else {
            clearLineBin();
        }
    };

    const clearLineWarehouse = () => {
        if (!warehouseEnabled) return;
        setValue(lineWarehouseDisplay, '');
        setValue(lineWarehouseId, '');
        setValue(lineWarehouseCode, '');
        setValue(lineWarehouseName, '');
        setValue(inventoryLocation, '');
        showClear(lineWarehouseClear, false);
        clearLineBin();
    };

    const applyHeaderWarehouseToLineStore = () => {
        if (!warehouseEnabled) return;
        const hdrId = parseInt(warehouseIdEl?.value, 10) || 0;
        if (!hdrId) return;
        applyLineWarehouseSelection(hdrId, warehouseCodeEl?.value, warehouseNameEl?.value);
    };

    const resolveLineWarehouseForItem = async (itemCode) => {
        if (!warehouseEnabled || !itemCode) {
            clearLineWarehouse();
            return;
        }
        const hdrId = parseInt(warehouseIdEl?.value, 10) || 0;
        if (hdrId > 0) {
            applyHeaderWarehouseToLineStore();
            return;
        }
        clearLineWarehouse();
        try {
            const res = await fetch(`${apiBase}/item-inventory?item_code=${encodeURIComponent(itemCode)}`);
            const data = await res.json();
            if (!data.success) return;
            const best = pickBestStockRow(data.items || []);
            if (best) {
                applyLineWarehouseSelection(
                    best.warehouse_id || best.code,
                    best.store || best.warehouse_code,
                    best.description || best.name || '',
                );
            } else if (binEnabled && itemCode) {
                clearLineBin();
            }
        } catch (e) {
            console.error('Failed to fetch item warehouse stock', e);
        }
    };

    const siRequireHeaderWarehouse = () => {
        if (!warehouseEnabled) return true;
        if (parseInt(warehouseIdEl?.value, 10) || 0) return true;
        alert('Please select warehouse before adding a line.');
        if (warehouseDisplay) warehouseDisplay.focus();
        else if (warehousePicker) warehousePicker.click();
        else {
            const whModal = document.getElementById('warehouseModal');
            if (whModal && typeof whModal.openModal === 'function') whModal.openModal();
        }
        return false;
    };

    const ensureHeaderSelections = () => {
        if (!customerCode?.value) {
            alert('Select customer first.');
            focusCustomerField();
            return false;
        }
        if (!priceMode?.value) {
            alert('Select price mode.');
            if (priceModePicker) priceModePicker.click();
            return false;
        }
        if (!siRequireHeaderWarehouse()) return false;
        if (orderNoMandatory && !String(orderNoEl?.value || '').trim()) {
            alert('Enter Order No.');
            if (orderNoEl) {
                orderNoEl.focus();
                try { orderNoEl.select(); } catch (ignore) {}
            }
            return false;
        }
        return true;
    };
    const focusItemEntry = () => {
        if (barcodeInput) {
            barcodeInput.focus();
            try { barcodeInput.select(); } catch (ignore) {}
        } else if (itemCodeDisplay) {
            itemCodeDisplay.focus();
            try { itemCodeDisplay.select(); } catch (ignore) {}
        } else if (itemPicker) {
            const itemModal = document.getElementById('itemModal');
            if (itemModal && typeof itemModal.openModal === 'function') itemModal.openModal();
        }
    };

    const siHeaderNavFields = () => {
        const out = [
            deliveryDate,
            priceModeDisplay,
            remarks,
            customerDisplay,
            orderNoEl,
            loyaltyCustomerDisplay,
        ];
        if (warehouseEnabled && warehouseDisplay) out.push(warehouseDisplay);
        return out.filter(Boolean);
    };

    const siFocusHeaderField = (el) => {
        if (!el || typeof el.focus !== 'function') return;
        el.focus();
        try { el.select(); } catch (ignore) {}
    };

    const siMoveHeaderBack = (fromEl) => {
        const fields = siHeaderNavFields();
        const idx = fields.indexOf(fromEl);
        if (idx > 0) siFocusHeaderField(fields[idx - 1]);
    };

    const siEntryNavFields = () => {
        const out = [];
        if (barcodeInput) out.push(barcodeInput);
        if (itemCodeDisplay) out.push(itemCodeDisplay);
        if (uomDisplay) out.push(uomDisplay);
        if (rate) out.push(rate);
        if (quantity) out.push(quantity);
        if (warehouseEnabled && lineWarehouseDisplay) out.push(lineWarehouseDisplay);
        else if (inventoryLocation) out.push(inventoryLocation);
        if (binEnabled && lineBinDisplay) out.push(lineBinDisplay);
        if (batchEnabled && salesLotDisplay) out.push(salesLotDisplay);
        if (discount) out.push(discount);
        if (lineAmount) out.push(lineAmount);
        return out.filter(Boolean);
    };

    const siFocusEntryField = (el) => {
        if (!el || typeof el.focus !== 'function') return;
        el.focus();
        try { el.select(); } catch (ignore) {}
    };

    const siMoveEntryBack = (fromEl) => {
        const fields = siEntryNavFields();
        const idx = fields.indexOf(fromEl);
        if (idx > 0) {
            siFocusEntryField(fields[idx - 1]);
            return;
        }
        const headerFields = siHeaderNavFields();
        if (!headerFields.length) return;
        setActiveTab('header');
        siFocusHeaderField(headerFields[headerFields.length - 1]);
    };

    const siModalOpen = () => !!document.querySelector('.modal:not(.hidden)');

    const wireSiHeaderEscNavigation = () => {
        siHeaderNavFields().forEach((field) => {
            field.addEventListener('keydown', (e) => {
                if (e.key !== 'Escape') return;
                if (siModalOpen()) return;
                if (!headerTab || !headerTab.classList.contains('tab-content--active')) return;
                e.preventDefault();
                siMoveHeaderBack(field);
            });
        });
    };

    const wireSiEntryEscNavigation = () => {
        siEntryNavFields().forEach((field) => {
            field.addEventListener('keydown', (e) => {
                if (e.key !== 'Escape') return;
                if (siModalOpen()) return;
                if (editingRow) return;
                e.preventDefault();
                e.stopPropagation();
                siMoveEntryBack(field);
            });
        });
    };

    const focusEntryForNextLine = () => {
        scrollTableToBottom();
        const entry = getEntryRow();
        if (entry && btnAddLine && document.activeElement === btnAddLine) {
            btnAddLine.blur();
        }
        setTimeout(() => focusItemEntry(), 0);
    };

    const setActiveTab = (targetTab) => {
        if (!tabs.length) {
            return true;
        }
        if (targetTab === 'items' && !ensureHeaderSelections()) {
            return false;
        }
        tabs.forEach(t => t.classList.remove('tab--active'));
        tabContents.forEach(tc => tc.classList.remove('tab-content--active'));
        const targetButton = document.querySelector(`.itemmaster-tabs .tab[data-tab="${targetTab}"]`);
        const targetContent = document.getElementById(`tab-${targetTab}`);
        if (targetButton) {
            targetButton.classList.add('tab--active');
        }
        if (targetContent) {
            targetContent.classList.add('tab-content--active');
        }
        return true;
    };

    tabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            setActiveTab(tab.dataset.tab);
        });
    });

    if (headerTab) {
        headerTab.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            const target = e.target;
            if (!target || !(target instanceof HTMLElement)) return;
            const tag = target.tagName.toLowerCase();
            if (!['input', 'select'].includes(tag)) return;
            if (!headerTab.classList.contains('tab-content--active')) return;
            if (!customerCode.value || !priceMode.value || (warehouseEnabled && !(parseInt(warehouseIdEl?.value, 10) || 0))) {
                if (!customerCode.value) {
                    focusCustomerField();
                } else if (!priceMode.value && priceModePicker) {
                    priceModePicker.click();
                } else if (warehouseEnabled && warehouseDisplay) {
                    warehouseDisplay.focus();
                }
                return;
            }
            e.preventDefault();
            setActiveTab('items');
            focusItemEntry();
        });
    }

    const setValue = (el, value) => {
        if (!el) return;
        el.value = value == null ? '' : value;
        if (el === billNo) syncRefDisplay();
    };
    const syncRefDisplay = () => {
        const ref = (billNo && billNo.value) ? billNo.value : 'New';
        const titleRef = document.getElementById('siTitleRef');
        const refLarge = document.getElementById('siRefLarge');
        if (titleRef) titleRef.textContent = ref;
        if (refLarge) refLarge.textContent = ref;
    };

    const showClear = (btn, show) => {
        if (!btn) return;
        btn.style.display = show ? 'block' : 'none';
    };

    const SI_QTY_DECIMALS = 3;
    const SI_RATE_DECIMALS = 3;
    const SI_AMT_DECIMALS = 2;

    const formatNumber = (value, decimals = SI_AMT_DECIMALS) => {
        const num = Number(value);
        if (Number.isNaN(num)) return (0).toFixed(decimals);
        return num.toFixed(decimals);
    };

    const formatRate = (value) => formatNumber(value, SI_RATE_DECIMALS);

    const setDetailText = (el, value) => {
        if (!el) return;
        const text = String(value == null ? '' : value).trim();
        el.textContent = text || '-';
    };

    const syncCustomerDetailsModal = () => {
        setDetailText(customerDetailsPhone, customerPhone?.value);
        setDetailText(customerDetailsBillType, billType?.value);
        setDetailText(customerDetailsCreditLimit, creditLimit?.value);
        setDetailText(customerDetailsCategory, customerCategory?.value);
        setDetailText(customerDetailsOutstanding, outstandingAmount?.value);
        setDetailText(customerDetailsTotalPoints, totalPoints?.value);
        setDetailText(customerDetailsAddress, customerAddress?.value);
    };

    const localDateIso = () => {
        const now = new Date();
        return [
            now.getFullYear(),
            String(now.getMonth() + 1).padStart(2, '0'),
            String(now.getDate()).padStart(2, '0'),
        ].join('-');
    };

    const applyBillDateRangeBounds = () => {
        if (!billDate) return;
        if (openBillDateFrom) billDate.min = openBillDateFrom;
        else billDate.removeAttribute('min');
        if (openBillDateTo) billDate.max = openBillDateTo;
        else billDate.removeAttribute('max');
        const multiDay = openBillDateFrom && openBillDateTo && openBillDateFrom !== openBillDateTo;
        if (multiDay) billDate.removeAttribute('readonly');
        else if (openBillDateFrom) billDate.setAttribute('readonly', 'readonly');
    };

    const updateBillDefaults = () => {
        const now = new Date();
        const today = localDateIso();
        applyBillDateRangeBounds();
        if (billDate && openBillDate) {
            setValue(billDate, openBillDate);
        } else if (billDate && !txnDateBlocked) {
            setValue(billDate, today);
        }
        setValue(billTime, now.toTimeString().slice(0, 8));
        if (deliveryDate && !deliveryDate.value) {
            setValue(deliveryDate, billDate?.value || openBillDate || today);
        }
        if (deliveryDate && billDate?.value) {
            deliveryDate.min = billDate.value;
        }
    };

    const syncBillDateFromOpen = () => {
        if (!billDate || !openBillDate) return;
        applyBillDateRangeBounds();
        const cur = String(billDate.value || '').trim();
        if (!cur || (openBillDateFrom && cur < openBillDateFrom) || (openBillDateTo && cur > openBillDateTo)) {
            setValue(billDate, openBillDate);
        }
        if (deliveryDate) {
            const floor = billDate.value || openBillDateFrom || openBillDate;
            if (!deliveryDate.value || deliveryDate.value < floor) {
                setValue(deliveryDate, floor);
            }
            deliveryDate.min = floor;
        }
    };

    const applyTxnDateBlockedUi = () => {
        if (btnSave) {
            btnSave.disabled = txnDateBlocked;
            btnSave.title = txnDateBlocked ? txnDateError : '';
        }
    };

    const DRAFT_KEY = (form?.dataset.draftKey || 'sales_draft').trim() || 'sales_draft';

    const setDefaultPriceMode = (force = false) => {
        if (force || !priceMode?.value) {
            setValue(priceMode, 'retail');
            setValue(priceModeDisplay, 'Retail');
            showClear(priceModeClear, true);
        }
    };

    const fetchNextBillNo = async () => {
        try {
            const res = await fetch(`${nextBillBase}/next-billno`, { credentials: 'same-origin' });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.error || `Could not reserve bill number (${res.status}).`);
                return false;
            }
            if (data.success) {
                setValue(billNo, data.billno);
                return true;
            }
            alert(data.error || 'Could not reserve bill number.');
            return false;
        } catch (e) {
            console.error('Failed to fetch next bill number', e);
            alert('Could not reserve bill number.');
            return false;
        }
    };

    const resetCustomer = () => {
        setValue(customerDisplay, '');
        setValue(customerCode, '');
        setValue(customerName, '');
        setValue(customerPhone, '');
        setValue(customerCategory, '');
        setValue(customerAddress, '');
        setValue(creditLimit, '');
        setValue(outstandingAmount, '');
        setValue(totalPoints, '');
        if (outstandingAmount) {
            outstandingAmount.dataset.outstandingCash = '';
            outstandingAmount.dataset.currentCredit = '';
            outstandingAmount.dataset.customerBillingType = '';
        }
        showClear(customerClear, false);
        syncCustomerDetailsModal();
        saveDraft();
    };

    const formatCustomerDisplay = (code, name) => {
        const c = String(code || '').trim();
        const n = String(name || '').trim();
        if (c && n) return `${c} - ${n}`;
        return c || n || '';
    };

    const formatWarehouseDisplay = (code, name) => {
        const c = String(code || '').trim();
        const n = String(name || '').trim();
        if (c && n) return `${c} - ${n}`;
        return c || n || '';
    };

    const formatBinDisplay = (code, name) => {
        const c = String(code || '').trim();
        const n = String(name || '').trim();
        if (c && n) return `${c} - ${n}`;
        return c || n || '';
    };

    const clearLineBin = () => {
        if (!binEnabled) return;
        setValue(lineBinDisplay, '');
        setValue(lineBinId, '');
        setValue(lineBinCode, '');
        setValue(lineBinName, '');
        showClear(lineBinClear, false);
    };

    const applyLineBinSelection = (id, code, name) => {
        if (!binEnabled) return;
        const binId = parseInt(id, 10) || 0;
        const binCode = String(code || '').trim();
        const binName = String(name || '').trim();
        setValue(lineBinDisplay, formatBinDisplay(binCode, binName));
        setValue(lineBinId, binId || String(id || '').trim());
        setValue(lineBinCode, binCode);
        setValue(lineBinName, binName);
        showClear(lineBinClear, Boolean(binCode));
    };

    const pickBestStockRow = (rows) => {
        const list = Array.isArray(rows) ? rows : [];
        if (!list.length) return null;
        const positive = list.filter((row) => Number(row.stock || 0) > 0);
        const pool = positive.length ? positive : list;
        return pool.reduce((best, row) => (
            Number(row.stock || 0) > Number(best.stock || 0) ? row : best
        ), pool[0]);
    };

    const resolveLineBinForItem = async (itemCode, warehouseId) => {
        if (!binEnabled || !itemCode) {
            clearLineBin();
            return;
        }
        const whId = parseInt(warehouseId, 10) || parseInt(lineWarehouseId?.value, 10) || 0;
        if (!whId) {
            clearLineBin();
            return;
        }
        clearLineBin();
        const itemBinApi = (salesBinCfg.itemBinInventoryApi || `${apiBase}/item-bin-inventory`).trim();
        try {
            const res = await fetch(`${itemBinApi}?item_code=${encodeURIComponent(itemCode)}&warehouse_id=${encodeURIComponent(String(whId))}`);
            const data = await res.json();
            if (!data.success) return;
            const best = pickBestStockRow(data.bins || []);
            if (best) {
                applyLineBinSelection(best.storage_id, best.code, best.name);
                return;
            }
            const whApi = (salesBinCfg.warehouseBinsApi || `${apiBase}/api/warehouse-bins`).trim();
            const res2 = await fetch(`${whApi}?wh=${encodeURIComponent(String(whId))}`);
            const data2 = await res2.json();
            const first = (data2.bins || [])[0];
            if (first) {
                applyLineBinSelection(first.storage_id, first.code, first.name);
            }
        } catch (e) {
            console.error('Failed to fetch item bin stock', e);
        }
    };

    const resolveWarehouseFieldsForItem = async (itemCode) => {
        if (!itemCode) return {};
        if (!warehouseEnabled) {
            try {
                const res = await fetch(`${apiBase}/item-inventory?item_code=${encodeURIComponent(itemCode)}`);
                const data = await res.json();
                if (!data.success) return {};
                const best = data.best || pickBestStockRow(data.items || []);
                if (best && best.store) {
                    return { store: String(best.store) };
                }
            } catch (e) {
                console.error('Failed to resolve store for item', e);
            }
            return {};
        }
        const hdrId = parseInt(warehouseIdEl?.value, 10) || 0;
        if (hdrId > 0) {
            return {
                store: warehouseCodeEl?.value || '',
                warehouseId: String(hdrId),
                warehouseCode: warehouseCodeEl?.value || '',
                warehouseName: warehouseNameEl?.value || '',
            };
        }
        try {
            const res = await fetch(`${apiBase}/item-inventory?item_code=${encodeURIComponent(itemCode)}`);
            const data = await res.json();
            if (!data.success) return {};
            const best = pickBestStockRow(data.items || []);
            if (!best) return {};
            return {
                store: best.store || best.warehouse_code || '',
                warehouseId: String(best.warehouse_id || best.code || ''),
                warehouseCode: best.store || best.warehouse_code || '',
                warehouseName: best.description || best.name || '',
            };
        } catch (e) {
            console.error('Failed to resolve warehouse for item', e);
        }
        return {};
    };

    const resolveBinFieldsForItem = async (itemCode, warehouseId) => {
        if (!binEnabled || !itemCode) return {};
        const whId = parseInt(warehouseId, 10) || 0;
        if (!whId) return {};
        const itemBinApi = (salesBinCfg.itemBinInventoryApi || `${apiBase}/item-bin-inventory`).trim();
        const whApi = (salesBinCfg.warehouseBinsApi || `${apiBase}/api/warehouse-bins`).trim();
        try {
            const res = await fetch(`${itemBinApi}?item_code=${encodeURIComponent(itemCode)}&warehouse_id=${encodeURIComponent(String(whId))}`);
            const data = await res.json();
            if (data.success) {
                const best = pickBestStockRow(data.bins || []);
                if (best) {
                    return {
                        storageId: String(best.storage_id || ''),
                        binCode: best.code || '',
                        binName: best.name || '',
                    };
                }
            }
            const res2 = await fetch(`${whApi}?wh=${encodeURIComponent(String(whId))}`);
            const data2 = await res2.json();
            const first = (data2.bins || [])[0];
            if (first) {
                return {
                    storageId: String(first.storage_id || ''),
                    binCode: first.code || '',
                    binName: first.name || '',
                };
            }
        } catch (e) {
            console.error('Failed to resolve bin for item', e);
        }
        return {};
    };

    const getLineUomPricing = async (itemCode, uom) => {
        if (!itemCode || !uom || !priceMode?.value) return null;
        try {
            const res = await fetch(
                `${apiBase}/uom-info?item_code=${encodeURIComponent(itemCode)}&uom_code=${encodeURIComponent(uom)}&price_mode=${encodeURIComponent(priceMode.value)}`
            );
            const data = await res.json();
            if (!data.success) return null;
            return data.pricing || null;
        } catch (e) {
            console.error('Failed to fetch UOM pricing', e);
            return null;
        }
    };

    const resetWarehouse = () => {
        setValue(warehouseDisplay, '');
        setValue(warehouseIdEl, '');
        setValue(warehouseCodeEl, '');
        setValue(warehouseNameEl, '');
        showClear(warehouseClear, false);
        saveDraft();
    };

    const applyUserDefaultWarehouse = () => {
        if (!warehouseEnabled) return;
        const defId = parseInt(salesWarehouseCfg.defaultId, 10) || 0;
        if (!defId) return;
        const whCode = String(salesWarehouseCfg.defaultCode || '').trim();
        const whName = String(salesWarehouseCfg.defaultName || '').trim();
        const label = String(salesWarehouseCfg.defaultLabel || '').trim() || formatWarehouseDisplay(whCode, whName);
        setValue(warehouseIdEl, String(defId));
        setValue(warehouseCodeEl, whCode);
        setValue(warehouseNameEl, whName);
        setValue(warehouseDisplay, label);
        showClear(warehouseClear, true);
        applyHeaderWarehouseToLineStore();
        saveDraft();
    };

    const clearSalesLotPick = () => {
        if (salesLotId) salesLotId.value = '';
        if (salesLotDisplay) salesLotDisplay.value = '';
    };

    const clearDuplicateUomHighlights = () => {
        tableBody?.querySelectorAll('.uom-duplicate-highlight').forEach((cell) => {
            cell.classList.remove('uom-duplicate-highlight');
        });
    };

    let siAddLineValidatePending = false;

    const siClearEntryInvalids = () => {
        const entry = getEntryRow();
        if (!entry) return;
        entry.querySelectorAll('td.si-cell-invalid, td.si-cell-checking').forEach((td) => {
            td.classList.remove('si-cell-invalid', 'si-cell-checking');
            td.removeAttribute('title');
        });
    };

    const siClearAllLineHighlights = () => {
        clearDuplicateUomHighlights();
        siClearEntryInvalids();
        tableBody?.querySelectorAll('tr[data-line] td.si-cell-invalid, tr[data-line] td.si-cell-checking').forEach((td) => {
            td.classList.remove('si-cell-invalid', 'si-cell-checking');
            td.removeAttribute('title');
        });
    };

    const siMarkEntryInvalid = (colKey, bad, msg) => {
        const entry = getEntryRow();
        const td = entry?.querySelector('.' + colKey);
        if (!td) return;
        td.classList.remove('si-cell-checking');
        if (bad) {
            td.classList.add('si-cell-invalid');
            td.title = msg || 'Invalid';
        } else {
            td.classList.remove('si-cell-invalid');
            td.removeAttribute('title');
        }
    };

    const siNormUom = (v) => String(v || '').trim().toUpperCase();
    const siNormStore = (v) => String(v || '').trim().toUpperCase();

    const siLineDuplicateKeyFromParts = (parts) => [
        String(parts.itemCode || '').trim(),
        siNormUom(parts.uom),
        warehouseEnabled ? String(parts.warehouseId || '').trim() : siNormStore(parts.store),
        binEnabled ? String(parts.storageId || '').trim() : '',
        batchEnabled ? String(parts.lotId || '').trim() : '',
        String(parts.barcode || '').trim(),
    ].join('\x1e');

    const siEntryDuplicateKey = () => siLineDuplicateKeyFromParts({
        itemCode: itemCodeHidden?.value,
        uom: uomCode?.value,
        warehouseId: lineWarehouseId?.value,
        store: warehouseEnabled ? lineWarehouseCode?.value : inventoryLocation?.value,
        storageId: lineBinId?.value,
        lotId: salesLotId?.value,
        barcode: barcodeInput?.value || currentItem.barcode,
    });

    const siDataRowDuplicateKey = (row) => {
        if (!row?.dataset) return '';
        return siLineDuplicateKeyFromParts({
            itemCode: row.dataset.itemCode,
            uom: row.dataset.uom,
            warehouseId: row.dataset.warehouseId,
            store: row.dataset.store,
            storageId: row.dataset.storageId,
            lotId: row.dataset.lotId,
            barcode: row.dataset.barcode,
        });
    };

    const siFindDuplicateDataLine = (excludeRow) => {
        const want = siEntryDuplicateKey();
        return Array.from(tableBody.querySelectorAll('tr[data-line]'))
            .find((r) => r !== excludeRow && siDataRowDuplicateKey(r) === want) || null;
    };

    const siMarkDuplicateDataRow = (dupRow) => {
        if (!dupRow) return;
        const msg = 'Duplicate line — same item, UOM, store, barcode, and location keys.';
        ['si-col-itemcode', 'si-col-uom', 'si-col-barcode'].forEach((k) => siMarkCellInvalid(dupRow, k, true, msg));
        if (warehouseEnabled) siMarkCellInvalid(dupRow, 'si-col-warehouse', true, msg);
        else siMarkCellInvalid(dupRow, 'si-col-store', true, msg);
        if (binEnabled) siMarkCellInvalid(dupRow, 'si-col-bin', true, msg);
        if (batchEnabled) siMarkCellInvalid(dupRow, 'si-col-lot', true, msg);
    };

    const siValidateBarcodeForEntry = async (itemCode, barcode) => {
        const bc = String(barcode || '').trim();
        if (!bc) {
            siMarkEntryInvalid('si-col-barcode', false);
            return true;
        }
        const bcTd = getEntryRow()?.querySelector('.si-col-barcode');
        if (bcTd) bcTd.classList.add('si-cell-checking');
        try {
            const res = await fetch(`${apiBase}/item-info?query=${encodeURIComponent(bc)}`);
            const data = await res.json();
            if (!data.success || !data.item) {
                siMarkEntryInvalid('si-col-barcode', true, `Barcode "${bc}" not found.`);
                return false;
            }
            const itCode = String(data.item.itemcode || '').trim();
            if (itCode && String(itemCode).trim() !== itCode) {
                siMarkEntryInvalid('si-col-barcode', true, `Barcode belongs to item ${itCode}, not ${itemCode}.`);
                return false;
            }
            siMarkEntryInvalid('si-col-barcode', false);
            return true;
        } catch (e) {
            siMarkEntryInvalid('si-col-barcode', true, 'Could not validate barcode.');
            return false;
        } finally {
            if (bcTd) bcTd.classList.remove('si-cell-checking');
        }
    };

    const siValidateEntryBeforeAdd = async () => {
        siClearAllLineHighlights();
        let ok = true;
        const code = String(itemCodeHidden?.value || itemCodeDisplay?.value || '').trim();
        const uom = String(uomCode?.value || uomDisplay?.value || '').trim();
        const qty = Number(quantity?.value || 0);
        const barcode = String(barcodeInput?.value || currentItem.barcode || '').trim();

        if (!code) {
            siMarkEntryInvalid('si-col-itemcode', true, 'Enter or select an item first.');
            ok = false;
        } else siMarkEntryInvalid('si-col-itemcode', false);

        if (!uom) {
            siMarkEntryInvalid('si-col-uom', true, 'Enter unit (UOM). Press F1 on UOM to pick.');
            ok = false;
        } else siMarkEntryInvalid('si-col-uom', false);

        if (qty <= 0) {
            siMarkEntryInvalid('si-col-qty', true, 'Enter a valid quantity greater than zero.');
            ok = false;
        } else siMarkEntryInvalid('si-col-qty', false);

        if (warehouseEnabled) {
            const whId = parseInt(lineWarehouseId?.value, 10) || 0;
            if (!whId) {
                siMarkEntryInvalid('si-col-warehouse', true, 'Select warehouse for this line.');
                ok = false;
            } else siMarkEntryInvalid('si-col-warehouse', false);
        } else if (!String(inventoryLocation?.value || '').trim()) {
            siMarkEntryInvalid('si-col-store', true, 'Enter receive store for this line.');
            ok = false;
        } else siMarkEntryInvalid('si-col-store', false);

        if (binEnabled) {
            const binId = parseInt(lineBinId?.value, 10) || 0;
            if (!binId) {
                siMarkEntryInvalid('si-col-bin', true, 'Select bin for this line.');
                ok = false;
            } else siMarkEntryInvalid('si-col-bin', false);
        }

        if (!ok) return false;

        const icTd = getEntryRow()?.querySelector('.si-col-itemcode');
        if (icTd) icTd.classList.add('si-cell-checking');
        try {
            const res = await fetch(`${apiBase}/item-info?query=${encodeURIComponent(code)}`);
            const data = await res.json();
            if (!data.success || !data.item) {
                siMarkEntryInvalid('si-col-itemcode', true, `Item code "${code}" not found.`);
                return false;
            }
            if (!String(itemName?.value || '').trim()) {
                siMarkEntryInvalid('si-col-itemcode', true, 'Item name is empty — pick the item with F1 or scan barcode first.');
                return false;
            }
            siMarkEntryInvalid('si-col-itemcode', false);

            const uomTd = getEntryRow()?.querySelector('.si-col-uom');
            if (uomTd) uomTd.classList.add('si-cell-checking');
            const uomsRes = await fetch(`${apiBase}/item-uoms?item_code=${encodeURIComponent(code)}`);
            const uomsData = await uomsRes.json();
            if (uomTd) uomTd.classList.remove('si-cell-checking');
            const uoms = (uomsData.success && uomsData.uoms) ? uomsData.uoms : [];
            if (!uoms.length) {
                siMarkEntryInvalid('si-col-itemcode', true, `Item ${code} has no units configured in item master.`);
                return false;
            }
            const uomHit = uoms.some((u) => siNormUom(u.code) === siNormUom(uom));
            if (!uomHit) {
                const allowed = uoms.map((u) => u.code).filter(Boolean).join(', ');
                siMarkEntryInvalid('si-col-uom', true, `Unit "${uom}" does not exist for this item. Allowed: ${allowed}.`);
                return false;
            }
            siMarkEntryInvalid('si-col-uom', false);

            if (!(await siValidateBarcodeForEntry(code, barcode))) return false;

            const dup = siFindDuplicateDataLine(editingRow);
            if (dup && !editingRow) {
                siMarkDuplicateDataRow(dup);
                siMarkEntryInvalid('si-col-itemcode', true, 'This line is already added (same item, UOM, store, barcode, and location).');
                siMarkEntryInvalid('si-col-uom', true, 'Duplicate line — change item, UOM, store, or barcode.');
                alert('This line is already added (same item, UOM, store, barcode, and location). Change one of those fields or edit the existing line.');
                return false;
            }

            const gross = qty * Number(rate?.value || 0);
            const disc = Number(discount?.value || 0);
            if (disc > gross) {
                siMarkEntryInvalid('si-col-disc', true, 'Discount cannot be greater than line amount.');
                alert('Discount cannot be greater than amount.');
                return false;
            }
            siMarkEntryInvalid('si-col-disc', false);
            return true;
        } catch (e) {
            siMarkEntryInvalid('si-col-itemcode', true, 'Could not validate item/unit. Try again.');
            return false;
        } finally {
            if (icTd) icTd.classList.remove('si-cell-checking');
        }
    };

    const siFocusFirstEntryInvalid = () => {
        const entry = getEntryRow();
        const bad = entry?.querySelector('td.si-cell-invalid');
        if (!bad) return;
        const input = bad.querySelector('input, select, button');
        if (input && typeof input.focus === 'function') input.focus();
    };

    const setEditorMode = (isEditing) => {
        if (btnAddLine) {
            btnAddLine.textContent = isEditing ? '✓' : '+';
            btnAddLine.title = isEditing ? 'Update line' : 'Add a line';
            btnAddLine.setAttribute('aria-label', isEditing ? 'Update line' : 'Add a line');
        }
        if (btnClearLine) {
            btnClearLine.textContent = isEditing ? '↶' : '×';
            btnClearLine.title = isEditing ? 'Cancel edit' : 'Clear line';
            btnClearLine.setAttribute('aria-label', isEditing ? 'Cancel edit' : 'Clear line');
        }
    };

    const lineRowHtmlDataFromDataset = (row) => ({
        lotId: row.dataset.lotId,
        lotLabel: row.dataset.lotLabel,
        barcode: row.dataset.barcode || '',
        itemCode: row.dataset.itemCode,
        itemName: row.dataset.itemName,
        uom: row.dataset.uom,
        rate: Number(row.dataset.rate || 0),
        quantity: Number(row.dataset.quantity || 0),
        store: row.dataset.store,
        warehouseCode: row.dataset.warehouseCode,
        warehouseName: row.dataset.warehouseName,
        warehouseLabel: formatWarehouseDisplay(row.dataset.warehouseCode, row.dataset.warehouseName),
        binCode: row.dataset.binCode,
        binName: row.dataset.binName,
        binLabel: formatBinDisplay(row.dataset.binCode, row.dataset.binName),
        discount: Number(row.dataset.discount || 0),
        amount: Number(row.dataset.amount || 0),
    });

    const applyLineRowPricing = (row, pricing) => {
        if (!row || !pricing) return;
        const qtyMag = siQtyMagnitude(row.dataset.quantity);
        const qty = siSignedQty(qtyMag);
        let lineDiscount = Number(row.dataset.discount || 0);
        const lineRate = Number(pricing.rate || 0);
        const factor = Number(pricing.conversion_factor || 1) || 1;
        const gross = qtyMag * lineRate;
        if (lineDiscount > gross) lineDiscount = gross;
        const amountAbs = gross - lineDiscount;
        const amount = isSalesReturn ? -amountAbs : amountAbs;
        row.dataset.quantity = String(qty);
        row.dataset.rate = String(lineRate);
        row.dataset.discount = String(lineDiscount);
        row.dataset.amount = String(amount);
        row.dataset.baseQty = String(qty * factor);
        if (pricing.cost_price != null) {
            row.dataset.cost = String(Number(pricing.cost_price || 0));
        }
        const lineNo = Number(row.dataset.line || 0) || 1;
        row.innerHTML = buildLineRowHtml(lineNo, lineRowHtmlDataFromDataset(row));
    };

    const buildLineRowHtml = (lineNo, data) => {
        const lotText = data.lotId
            ? (data.lotLabel || `#${data.lotId}`)
            : 'Auto';
        const warehouseCell = warehouseEnabled
            ? `<td class="si-col-warehouse">${data.warehouseLabel || formatWarehouseDisplay(data.warehouseCode, data.warehouseName) || data.store || ''}</td>`
            : '';
        const binCell = binEnabled
            ? `<td class="si-col-bin">${data.binLabel || formatBinDisplay(data.binCode, data.binName) || ''}</td>`
            : '';
        const lotCell = batchEnabled
            ? `<td class="si-col-lot">${lotText}</td>`
            : '';
        const storeCell = warehouseEnabled
            ? ''
            : `<td class="si-col-store">${data.store || ''}</td>`;
        return `
                <td class="si-col-sl">${lineNo}</td>
                <td class="si-col-barcode">${data.barcode || ''}</td>
                <td class="si-col-itemcode">${data.itemCode || ''}</td>
                <td class="si-col-itemname">${data.itemName || ''}</td>
                <td class="si-col-uom">${data.uom || ''}</td>
                <td class="si-col-rate">${formatRate(data.rate || 0)}</td>
                <td class="si-col-qty">${formatNumber(data.quantity || 0, 3)}</td>
                ${storeCell}
                ${warehouseCell}
                ${binCell}
                ${lotCell}
                <td class="si-col-disc">${formatNumber(data.discount || 0)}</td>
                <td class="si-col-amount">${formatNumber(data.amount || 0)}</td>
                <td class="si-col-action">
                    <button type="button" class="button button--link btn-remove" aria-label="Remove item">×</button>
                </td>
            `;
    };

    let siInlineModalRow = null;
    let siInlineUomRow = null;
    const SI_INLINE_COLS = {
        'si-col-barcode': { ds: 'barcode', type: 'text' },
        'si-col-itemcode': { ds: 'itemCode', type: 'text' },
        'si-col-uom': { ds: 'uom', type: 'text' },
        'si-col-qty': { ds: 'quantity', type: 'number' },
        'si-col-rate': { ds: 'rate', type: 'number' },
        'si-col-disc': { ds: 'discount', type: 'number' },
        'si-col-amount': { ds: 'amount', type: 'number' },
    };
    const SI_INLINE_ORDER = ['si-col-barcode', 'si-col-itemcode', 'si-col-uom', 'si-col-qty', 'si-col-rate', 'si-col-disc', 'si-col-amount'];

    const siInlineColKey = (td) => {
        if (!td || !td.classList) return null;
        for (const k of Object.keys(SI_INLINE_COLS)) {
            if (td.classList.contains(k)) return k;
        }
        return null;
    };

    const siGetItemCodeFromRow = (tr) => {
        if (!tr) return '';
        const fromDs = String(tr.dataset.itemCode || tr.getAttribute('data-item-code') || '').trim();
        if (fromDs) return fromDs;
        const cell = tr.querySelector('.si-col-itemcode');
        const fromCell = cell ? String(cell.textContent || '').trim() : '';
        if (fromCell) {
            tr.dataset.itemCode = fromCell;
        }
        return fromCell;
    };

    const siLineFactor = (tr) => {
        const qty = Math.abs(Number(tr.dataset.quantity || 0));
        const baseQty = Math.abs(Number(tr.dataset.baseQty || 0));
        if (qty > 0 && baseQty > 0) return baseQty / qty;
        return 1;
    };

    const siSignedQty = (mag) => {
        const n = Math.abs(Number(mag || 0));
        if (n <= 0) return 0;
        return isSalesReturn ? -n : n;
    };

    const siQtyMagnitude = (qty) => Math.abs(Number(qty || 0));

    const siSetCellText = (tr, cls, text) => {
        const el = tr.querySelector('.' + cls);
        if (el && !el._editing) el.textContent = text;
    };

    const siRefreshDataRowCells = (tr) => {
        const d = lineRowHtmlDataFromDataset(tr);
        const lineNo = Number(tr.dataset.line || 0) || 1;
        siSetCellText(tr, 'si-col-sl', String(lineNo));
        siSetCellText(tr, 'si-col-barcode', d.barcode || '');
        siSetCellText(tr, 'si-col-itemcode', d.itemCode || '');
        siSetCellText(tr, 'si-col-itemname', d.itemName || '');
        siSetCellText(tr, 'si-col-uom', d.uom || '');
        siSetCellText(tr, 'si-col-rate', formatRate(d.rate || 0));
        siSetCellText(tr, 'si-col-qty', formatNumber(d.quantity || 0, 3));
        siSetCellText(tr, 'si-col-disc', formatNumber(d.discount || 0));
        siSetCellText(tr, 'si-col-amount', formatNumber(d.amount || 0));
        if (!warehouseEnabled) siSetCellText(tr, 'si-col-store', d.store || '');
        if (warehouseEnabled) siSetCellText(tr, 'si-col-warehouse', d.warehouseLabel || '');
        if (binEnabled) siSetCellText(tr, 'si-col-bin', d.binLabel || '');
        if (batchEnabled) {
            const lotText = d.lotId ? (d.lotLabel || `#${d.lotId}`) : 'Auto';
            siSetCellText(tr, 'si-col-lot', lotText);
        }
    };

    const siRecalcDataRow = (tr) => {
        const qtyMag = siQtyMagnitude(tr.dataset.quantity);
        const qty = siSignedQty(qtyMag);
        const rate = Number(tr.dataset.rate || 0);
        let disc = Number(tr.dataset.discount || 0);
        const gross = qtyMag * rate;
        if (disc > gross) {
            disc = gross;
            tr.dataset.discount = String(disc);
        }
        const amountAbs = gross - disc;
        tr.dataset.quantity = String(qty);
        tr.dataset.amount = String(isSalesReturn ? -amountAbs : amountAbs);
        tr.dataset.baseQty = String(qty * siLineFactor(tr));
        siRefreshDataRowCells(tr);
    };

    const siRecalcDataRowFromAmount = (tr) => {
        const qtyMag = siQtyMagnitude(tr.dataset.quantity);
        let disc = Number(tr.dataset.discount || 0);
        let netAmountAbs = Math.abs(Number(tr.dataset.amount || 0));
        if (qtyMag > 0) {
            const gross = netAmountAbs + disc;
            if (disc > gross) {
                disc = gross;
                tr.dataset.discount = String(disc);
                netAmountAbs = Math.max(0, gross - disc);
            }
            tr.dataset.rate = String(gross / qtyMag);
        }
        tr.dataset.amount = String(isSalesReturn ? -netAmountAbs : netAmountAbs);
        tr.dataset.baseQty = String(siSignedQty(qtyMag) * siLineFactor(tr));
        siRefreshDataRowCells(tr);
    };

    const siMarkCellInvalid = (tr, colKey, bad, msg) => {
        const td = tr?.querySelector('.' + colKey);
        if (!td) return;
        td.classList.remove('si-cell-checking');
        if (bad) {
            td.classList.add('si-cell-invalid');
            td.title = msg || 'Invalid';
        } else {
            td.classList.remove('si-cell-invalid');
            td.removeAttribute('title');
        }
    };

    const siLineDisplayNo = (tr, idx) => String(tr?.dataset?.line || '').trim() || String((idx || 0) + 1);

    const siGetLineValidationBlockMessage = () => {
        const issues = [];
        const entry = getEntryRow();
        if (entry) {
            entry.querySelectorAll('td.si-cell-invalid').forEach((td) => {
                const hint = (td.title || td.getAttribute('title') || 'invalid field').trim();
                issues.push(`Entry row: ${hint || 'fix highlighted cell'}.`);
            });
            if (entry.querySelector('td.si-cell-checking')) {
                issues.push('Entry row: validation still in progress — wait a moment and try again.');
            }
        }
        tableBody?.querySelectorAll('tr[data-line]').forEach((tr, idx) => {
            const lineNo = siLineDisplayNo(tr, idx);
            tr.querySelectorAll('td.si-cell-invalid').forEach((td) => {
                const hint = (td.title || td.getAttribute('title') || 'invalid field').trim();
                issues.push(`Line ${lineNo}: ${hint || 'fix highlighted cell'}.`);
            });
            if (tr.querySelector('td.si-cell-checking')) {
                issues.push(`Line ${lineNo}: validation still in progress — wait a moment and try again.`);
            }
        });
        if (!issues.length) return '';
        let body = issues.slice(0, 10).join('\n');
        if (issues.length > 10) body += `\n… and ${issues.length - 10} more issue(s).`;
        return `Fix highlighted (red) lines before saving.\n\n${body}`;
    };

    const siApplyUomToDataRow = async (tr, uomVal) => {
        const uom = String(uomVal || '').trim().toUpperCase();
        if (!uom) return;
        tr.dataset.uom = uom;
        const pricing = await getLineUomPricing(tr.dataset.itemCode, uom);
        if (pricing) {
            applyLineRowPricing(tr, pricing);
            tr.dataset.baseQty = String(Number(tr.dataset.quantity || 0) * (Number(pricing.conversion_factor || 1) || 1));
            if (pricing.cost_price != null) tr.dataset.cost = String(Number(pricing.cost_price || 0));
        } else {
            siRecalcDataRow(tr);
        }
        siMarkCellInvalid(tr, 'si-col-uom', false);
        updateTotals();
        saveDraft();
    };

    const siApplyItemPayloadToDataRow = async (tr, payload) => {
        tr.dataset.itemCode = payload.itemCode || '';
        tr.dataset.itemName = payload.itemName || '';
        tr.dataset.barcode = payload.barcode || '';
        if (payload.uom) tr.dataset.uom = payload.uom;
        siMarkCellInvalid(tr, 'si-col-itemcode', false);
        const pricing = await getLineUomPricing(tr.dataset.itemCode, tr.dataset.uom);
        if (pricing) {
            applyLineRowPricing(tr, pricing);
            tr.dataset.baseQty = String(Number(tr.dataset.quantity || 0) * (Number(pricing.conversion_factor || 1) || 1));
            if (pricing.cost_price != null) tr.dataset.cost = String(Number(pricing.cost_price || 0));
        } else {
            siRecalcDataRow(tr);
        }
        siRefreshDataRowCells(tr);
        updateTotals();
        saveDraft();
    };

    const siResolveItemCodeOnRow = async (tr) => {
        const code = String(tr.dataset.itemCode || '').trim();
        if (!code) {
            siMarkCellInvalid(tr, 'si-col-itemcode', false);
            return;
        }
        const icTd = tr.querySelector('.si-col-itemcode');
        if (icTd) icTd.classList.add('si-cell-checking');
        try {
            const res = await fetch(`${apiBase}/item-info?query=${encodeURIComponent(code)}`);
            const data = await res.json();
            if (!data.success || !data.item) {
                siMarkCellInvalid(tr, 'si-col-itemcode', true, `Item code "${code}" not found.`);
                siRefreshDataRowCells(tr);
                return;
            }
            const item = data.item;
            await siApplyItemPayloadToDataRow(tr, {
                itemCode: String(item.itemcode || '').trim(),
                itemName: salesItemDisplayName(item),
                barcode: String(item.manufacturerid || '').trim(),
                uom: String(item.baseuom || tr.dataset.uom || '').trim(),
            });
        } catch (e) {
            console.error(e);
        } finally {
            if (icTd) icTd.classList.remove('si-cell-checking');
        }
    };

    const siResolveBarcodeOnRow = async (tr) => {
        const bc = String(tr.dataset.barcode || '').trim();
        if (!bc) {
            siMarkCellInvalid(tr, 'si-col-barcode', false);
            return;
        }
        const bcTd = tr.querySelector('.si-col-barcode');
        if (bcTd) bcTd.classList.add('si-cell-checking');
        try {
            const res = await fetch(`${apiBase}/item-info?query=${encodeURIComponent(bc)}`);
            const data = await res.json();
            if (!data.success || !data.item) {
                siMarkCellInvalid(tr, 'si-col-barcode', true, `Barcode "${bc}" not found.`);
                siRefreshDataRowCells(tr);
                return;
            }
            const item = data.item;
            const itemCode = String(item.itemcode || '').trim();
            const existing = String(tr.dataset.itemCode || '').trim();
            if (existing && itemCode && existing !== itemCode) {
                siMarkCellInvalid(tr, 'si-col-barcode', true, `Barcode belongs to item ${itemCode}, not ${existing}.`);
                siRefreshDataRowCells(tr);
                return;
            }
            await siApplyItemPayloadToDataRow(tr, {
                itemCode,
                itemName: salesItemDisplayName(item),
                barcode: bc,
                uom: String(item.baseuom || tr.dataset.uom || '').trim(),
            });
            siMarkCellInvalid(tr, 'si-col-barcode', false);
        } catch (e) {
            console.error(e);
        } finally {
            if (bcTd) bcTd.classList.remove('si-cell-checking');
        }
    };

    const siValidateUomOnRow = async (tr) => {
        const code = String(tr.dataset.itemCode || '').trim();
        const uom = String(tr.dataset.uom || '').trim();
        if (!code || !uom) {
            siMarkCellInvalid(tr, 'si-col-uom', false);
            return;
        }
        const uTd = tr.querySelector('.si-col-uom');
        if (uTd) uTd.classList.add('si-cell-checking');
        try {
            const uoms = await fetchItemUoms(code);
            const ok = (uoms || []).some((u) => String(u.code || '').trim().toUpperCase() === uom.toUpperCase());
            if (!ok) {
                siMarkCellInvalid(tr, 'si-col-uom', true, `UOM "${uom}" is not defined for item ${code}.`);
                siRefreshDataRowCells(tr);
                return;
            }
            await siApplyUomToDataRow(tr, uom);
        } catch (e) {
            siMarkCellInvalid(tr, 'si-col-uom', true, 'Could not validate UOM.');
            siRefreshDataRowCells(tr);
        } finally {
            if (uTd) uTd.classList.remove('si-cell-checking');
        }
    };

    const siApplyPopupItemToDataRow = async (tr, popupRow) => {
        if (!tr || !popupRow) return;
        await siApplyItemPayloadToDataRow(tr, {
            itemCode: popupRow.dataset.code || '',
            itemName: popupRow.dataset.name || '',
            barcode: popupRow.dataset.barcode || '',
            uom: popupRow.dataset.uom || '',
        });
    };

    const siOpenItemModalForDataRow = (tr) => {
        if (!customerCode?.value) {
            alert('Add customer first.');
            focusCustomerField();
            return;
        }
        siInlineModalRow = tr;
        if (itemModal && typeof itemModal.openModal === 'function') itemModal.openModal();
    };

    const siOpenUomModalForDataRow = async (tr) => {
        const code = siGetItemCodeFromRow(tr);
        if (!code) {
            alert('Select an item first.');
            return;
        }
        siInlineUomRow = tr;
        await fetchItemUoms(code);
        const uomModal = document.getElementById('uomModal');
        if (uomModal && typeof uomModal.openModal === 'function') uomModal.openModal();
    };

    const siInlineMove = (td, tr, dir) => {
        if (dir === 'down' || dir === 'up') {
            const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
            const ri = rows.indexOf(tr);
            const target = rows[ri + (dir === 'down' ? 1 : -1)];
            if (!target) return;
            const key = siInlineColKey(td);
            const ntd = key ? target.querySelector('.' + key) : null;
            if (ntd) siBeginInlineEdit(ntd, target, key);
            return;
        }
        const curKey = siInlineColKey(td);
        const oi = SI_INLINE_ORDER.indexOf(curKey);
        if (oi === -1) return;
        const step = dir === 'right' ? 1 : -1;
        for (let i = oi + step; i >= 0 && i < SI_INLINE_ORDER.length; i += step) {
            const c = tr.querySelector('.' + SI_INLINE_ORDER[i]);
            if (c) { siBeginInlineEdit(c, tr, SI_INLINE_ORDER[i]); return; }
        }
    };

    const siBeginInlineEdit = (td, tr, key) => {
        if (!td || td._editing) return;
        if (key === 'si-col-uom') {
            siOpenUomModalForDataRow(tr);
            return;
        }
        const cfg = SI_INLINE_COLS[key];
        if (!cfg) return;
        let cur = cfg.type === 'number'
            ? String(Number(tr.dataset[cfg.ds] || 0))
            : String(tr.dataset[cfg.ds] || '');
        if (cfg.type === 'number' && key === 'si-col-qty' && isSalesReturn) {
            cur = String(siQtyMagnitude(tr.dataset[cfg.ds]));
        }
        if (key === 'si-col-amount') {
            cur = String(Math.abs(Number(tr.dataset.amount || 0)));
        }
        const input = document.createElement('input');
        input.className = 'si-inline-input';
        input.type = cfg.type === 'number' ? 'number' : 'text';
        if (cfg.type === 'number') {
            input.step = key === 'si-col-qty' || key === 'si-col-rate' ? '0.001' : '0.01';
            if (key !== 'si-col-amount') input.min = '0';
        }
        input.value = cur;
        td._editing = true;
        td.textContent = '';
        td.appendChild(input);
        input.focus();
        try { input.select(); } catch (ignore) {}
        let done = false;
        const finish = async (commit) => {
            if (done) return;
            done = true;
            td._editing = false;
            if (commit) {
                if (key === 'si-col-amount') {
                    const rawAmt = String(input.value ?? '').trim();
                    if (rawAmt === '' || rawAmt === '-' || rawAmt === '.' || rawAmt === '-.') {
                        siRecalcDataRow(tr);
                    } else {
                        let n = parseFloat(rawAmt);
                        if (isNaN(n) || n < 0) n = 0;
                        tr.dataset.amount = String(isSalesReturn ? -n : n);
                        siRecalcDataRowFromAmount(tr);
                    }
                } else if (cfg.type === 'number') {
                    let n = parseFloat(input.value);
                    if (isNaN(n) || n < 0) n = 0;
                    if (key === 'si-col-qty' && isSalesReturn) {
                        tr.dataset[cfg.ds] = String(siSignedQty(n));
                        tr.dataset.baseQty = String(siSignedQty(n) * siLineFactor(tr));
                    } else {
                        tr.dataset[cfg.ds] = String(n);
                        if (key === 'si-col-qty') {
                            tr.dataset.baseQty = String(n * siLineFactor(tr));
                        }
                    }
                    siRecalcDataRow(tr);
                } else {
                    let tv = String(input.value || '').trim();
                    if (key === 'si-col-uom') tv = tv.toUpperCase();
                    tr.dataset[cfg.ds] = tv;
                    siRecalcDataRow(tr);
                }
            } else {
                siRefreshDataRowCells(tr);
            }
            if (commit) {
                if (key === 'si-col-itemcode') await siResolveItemCodeOnRow(tr);
                else if (key === 'si-col-barcode') await siResolveBarcodeOnRow(tr);
                else if (key === 'si-col-uom') await siValidateUomOnRow(tr);
                else {
                    updateTotals();
                    saveDraft();
                }
            }
        };
        input.addEventListener('blur', () => { finish(true); });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'F1' || e.keyCode === 112) {
                if (key === 'si-col-barcode' || key === 'si-col-itemcode') {
                    e.preventDefault();
                    e.stopPropagation();
                    finish(false);
                    siOpenItemModalForDataRow(tr);
                } else if (key === 'si-col-uom') {
                    e.preventDefault();
                    e.stopPropagation();
                    finish(false);
                    siOpenUomModalForDataRow(tr);
                }
                return;
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                finish(true).then(() => siInlineMove(td, tr, 'down'));
            } else if (e.key === 'Tab') {
                e.preventDefault();
                finish(true).then(() => siInlineMove(td, tr, e.shiftKey ? 'left' : 'right'));
            } else if (e.key === 'Escape') {
                e.preventDefault();
                finish(false);
            }
        });
    };

    const resetItemLine = () => {
        siClearAllLineHighlights();
        if (barcodeInput) barcodeInput.value = '';
        setValue(itemCodeDisplay, '');
        setValue(itemCodeHidden, '');
        setValue(itemName, '');
        setValue(uomDisplay, '');
        setValue(uomCode, '');
        setValue(inventoryLocation, '');
        clearLineWarehouse();
        clearLineBin();
        setValue(quantity, '');
        setValue(rate, '');
        setValue(discount, '');
        setValue(lineAmount, '');
        showClear(itemClear, false);
        showClear(uomClear, false);
        showClear(inventoryClear, false);
        showClear(lineWarehouseClear, false);
        showClear(lineBinClear, false);
        editingRow = null;
        setEditorMode(false);
        Object.assign(currentItem, {
            itemCode: '',
            itemName: '',
            barcode: '',
            baseUom: '',
            retail: 0,
            wholesale: 0,
            third: 0,
            branch: 0,
            cost: 0,
            factor: 1,
        });
        clearSalesLotPick();
    };

    const clearTable = () => {
        tableBody.querySelectorAll('tr[data-line]').forEach((r) => r.remove());
        showTableEmpty();
        pinEntryRowToBottom();
        setValue(totalItems, '0');
        setValue(loyaltyPoints, '0');
        setValue(totalAmount, '0.00');
        setValue(additionalDiscount, '');
        setValue(totalDiscount, '0.00');
        setValue(netTotal, '0.00');
        setValue(totalItemsItems, '0');
        setValue(loyaltyPointsItems, '0');
        setValue(totalAmountItems, '0.00');
        setValue(additionalDiscountItems, '');
        setValue(totalDiscountItems, '0.00');
        setValue(netTotalItems, '0.00');
        promotionDiscount = 0;
        appliedVouchers = [];
        if (promotionDiscountEl) setValue(promotionDiscountEl, '0.00');
        if (promotionDiscountItemsEl) setValue(promotionDiscountItemsEl, '0.00');
        if (appliedPromotionsEl) appliedPromotionsEl.innerHTML = '';
    };

    const syncAdditionalDiscount = (value) => {
        const raw = value == null ? '' : value;
        if (additionalDiscount && additionalDiscount.value !== raw) {
            setValue(additionalDiscount, raw);
        }
        if (additionalDiscountItems && additionalDiscountItems.value !== raw) {
            setValue(additionalDiscountItems, raw);
        }
    };

    const updateTotals = () => {
        const extraDiscount = Math.abs(Number(additionalDiscount?.value || additionalDiscountItems?.value || 0));
        let discountSum = 0;
        let grossAbs = 0;
        let lineNetAbs = 0;
        const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
        rows.forEach((row) => {
            const rowDiscount = Math.abs(Number(row.dataset.discount || 0));
            const rowQty = Math.abs(Number(row.dataset.quantity || 0));
            const rowRate = Number(row.dataset.rate || 0);
            const rowAmt = Math.abs(Number(row.dataset.amount || 0));
            grossAbs += rowQty * rowRate;
            discountSum += rowDiscount;
            // Prefer stored line amount (invoice load) over recomputed qty×rate−disc.
            lineNetAbs += rowAmt > 0 || rowQty === 0
                ? rowAmt
                : Math.max(0, rowQty * rowRate - rowDiscount);
        });
        const totalDiscountValue = discountSum + extraDiscount;
        // Net from line amounts, then subtract header-only extras (addl / promo).
        const netAbs = Math.max(0, lineNetAbs - extraDiscount - Math.abs(promotionDiscount || 0));
        // Sales return: show signed (negative) totals; sales: non-negative.
        const sign = isSalesReturn ? -1 : 1;
        const grossSum = sign * grossAbs;
        const netTotalValue = sign * netAbs;
        setValue(totalItems, String(rows.length));
        setValue(loyaltyPoints, '0');
        setValue(totalAmount, formatNumber(grossSum));
        setValue(totalDiscount, formatNumber(totalDiscountValue));
        if (promotionDiscountEl) setValue(promotionDiscountEl, formatNumber(promotionDiscount));
        setValue(netTotal, formatNumber(netTotalValue));
        setValue(totalItemsItems, String(rows.length));
        setValue(loyaltyPointsItems, '0');
        setValue(totalAmountItems, formatNumber(grossSum));
        setValue(totalDiscountItems, formatNumber(totalDiscountValue));
        if (promotionDiscountItemsEl) setValue(promotionDiscountItemsEl, formatNumber(promotionDiscount));
        setValue(netTotalItems, formatNumber(netTotalValue));
        if (appliedPromotionsEl) {
            appliedPromotionsEl.innerHTML = appliedVouchers.length
                ? appliedVouchers.map(v => v.code + ': ' + v.message + ' (-' + formatNumber(v.discount_amount) + ')').join('<br/>')
                : '';
        }
    };

    const applyVoucher = async () => {
        const code = (voucherCodeInput?.value || '').trim();
        if (!code) {
            alert('Enter voucher code.');
            return;
        }
        let grossSum = 0;
        let discountSum = 0;
        const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
        rows.forEach((row) => {
            const rowDiscount = Number(row.dataset.discount || 0);
            const rowQty = Number(row.dataset.quantity || 0);
            const rowRate = Number(row.dataset.rate || 0);
            grossSum += rowQty * rowRate;
            discountSum += rowDiscount;
        });
        const extraDiscount = Number(additionalDiscount?.value || additionalDiscountItems?.value || 0);
        const subtotal = Math.max(0, grossSum - discountSum - extraDiscount);
        if (subtotal <= 0) {
            alert('Add items and ensure subtotal is positive.');
            return;
        }
        try {
            const res = await fetch('/promotions/api/apply-voucher', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code, subtotal }),
            });
            const data = await res.json();
            if (data.success && data.discount_amount != null) {
                promotionDiscount += Number(data.discount_amount) || 0;
                appliedVouchers.push({
                    code: data.code || code,
                    message: data.message || 'Applied',
                    discount_amount: data.discount_amount,
                });
                if (voucherCodeInput) voucherCodeInput.value = '';
                updateTotals();
                saveDraft();
            } else {
                alert(data.error || 'Voucher not valid.');
            }
        } catch (e) {
            alert('Request failed.');
        }
    };

    if (btnApplyVoucher) btnApplyVoucher.addEventListener('click', applyVoucher);
    if (voucherCodeInput) voucherCodeInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); applyVoucher(); } });

    const saveDraft = () => {
        if (!tableBody) return;
        const lines = Array.from(tableBody.querySelectorAll('tr[data-line]')).map((row, index) => ({
            line: index + 1,
            item_code: row.dataset.itemCode || '',
            barcode: row.dataset.barcode || '',
            item_name: row.dataset.itemName || '',
            uom: row.dataset.uom || '',
            store: row.dataset.store || '',
            warehouse_id: row.dataset.warehouseId || '',
            warehouse_code: row.dataset.warehouseCode || '',
            warehouse_name: row.dataset.warehouseName || '',
            storage_id: row.dataset.storageId || '',
            bin_code: row.dataset.binCode || '',
            bin_name: row.dataset.binName || '',
            quantity: Number(row.dataset.quantity || 0),
            rate: Number(row.dataset.rate || 0),
            discount: Number(row.dataset.discount || 0),
            amount: Number(row.dataset.amount || 0),
            base_qty: Number(row.dataset.baseQty || 0),
            cost: Number(row.dataset.cost || 0),
            lot_id: row.dataset.lotId || '',
            lot_label: row.dataset.lotLabel || '',
        }));

        const header = {
            bill_no: billNo?.value || '',
            bill_date: billDate?.value || '',
            bill_time: billTime?.value || '',
            bill_type: billType?.value || '',
            delivery_date: deliveryDate?.value || '',
            remarks: remarks?.value || '',
            order_no: orderNoEl?.value || '',
            customer_display: customerDisplay?.value || '',
            customer_code: customerCode?.value || '',
            customer_name: customerName?.value || '',
            customer_phone: customerPhone?.value || '',
            customer_category: customerCategory?.value || '',
            customer_address: customerAddress?.value || '',
            credit_limit: creditLimit?.value || '',
            outstanding_amount: outstandingAmount?.value || '',
            total_points: totalPoints?.value || '',
            outstanding_cash: outstandingAmount?.dataset.outstandingCash || '',
            current_credit: outstandingAmount?.dataset.currentCredit || '',
            customer_billing_type: outstandingAmount?.dataset.customerBillingType || '',
            price_mode: priceMode?.value || '',
            price_mode_display: priceModeDisplay?.value || '',
            additional_discount: additionalDiscount?.value || additionalDiscountItems?.value || '',
            promotion_discount: promotionDiscount,
            applied_vouchers: appliedVouchers,
            warehouse_id: warehouseIdEl?.value || '',
            warehouse_code: warehouseCodeEl?.value || '',
            warehouse_name: warehouseNameEl?.value || '',
            warehouse_display: warehouseDisplay?.value || '',
        };

        const payload = { header, lines };
        sessionStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
    };

    const clearDraft = () => {
        sessionStorage.removeItem(DRAFT_KEY);
    };

    const restoreLines = (lines) => {
        tableBody.querySelectorAll('tr[data-line]').forEach((r) => r.remove());
        if (!lines.length) {
            showTableEmpty();
            pinEntryRowToBottom();
            updateTotals();
            return;
        }
        removeTableEmpty();
        const entry = getEntryRow();
        lines.forEach((line, idx) => {
            const row = document.createElement('tr');
            row.dataset.line = String(idx + 1);
            row.dataset.itemCode = String(line.item_code || line.itemcode || line.itemCode || '').trim();
            row.dataset.barcode = line.barcode || '';
            row.dataset.itemName = line.item_name || '';
            row.dataset.uom = line.uom || '';
            row.dataset.store = line.store || '';
            row.dataset.warehouseId = line.warehouse_id != null ? String(line.warehouse_id) : '';
            row.dataset.warehouseCode = line.warehouse_code || line.store || '';
            row.dataset.warehouseName = line.warehouse_name || '';
            row.dataset.storageId = line.storage_id != null ? String(line.storage_id) : '';
            row.dataset.binCode = line.bin_code || '';
            row.dataset.binName = line.bin_name || '';
            let qty = Number(line.quantity || 0);
            let baseQty = Number(line.base_qty || 0);
            let amount = Number(line.amount || 0);
            // Sales Return lines are always negative qty/amount (match manual add).
            if (isSalesReturn) {
                const qtyMag = Math.abs(qty);
                qty = qtyMag ? -qtyMag : 0;
                const baseMag = Math.abs(baseQty || qtyMag);
                baseQty = baseMag ? -baseMag : 0;
                const amtMag = Math.abs(amount);
                amount = amtMag ? -amtMag : 0;
            }
            row.dataset.quantity = String(qty);
            row.dataset.rate = Number(line.rate || 0);
            row.dataset.discount = Number(line.discount || 0);
            row.dataset.amount = String(amount);
            row.dataset.baseQty = String(baseQty);
            row.dataset.cost = Number(line.cost || 0);
            row.dataset.lotId = line.lot_id != null && line.lot_id !== '' ? String(line.lot_id) : '';
            row.dataset.lotLabel = line.lot_label != null ? String(line.lot_label) : '';
            row.innerHTML = buildLineRowHtml(idx + 1, {
                lotId: row.dataset.lotId,
                lotLabel: row.dataset.lotLabel,
                barcode: row.dataset.barcode || '',
                itemCode: line.item_code || '',
                itemName: line.item_name || '',
                uom: line.uom || '',
                rate: Number(line.rate || 0),
                quantity: qty,
                store: line.store || '',
                warehouseCode: row.dataset.warehouseCode,
                warehouseName: row.dataset.warehouseName,
                warehouseLabel: formatWarehouseDisplay(row.dataset.warehouseCode, row.dataset.warehouseName),
                binCode: row.dataset.binCode,
                binName: row.dataset.binName,
                binLabel: formatBinDisplay(row.dataset.binCode, row.dataset.binName),
                discount: Number(line.discount || 0),
                amount: amount,
            });
            if (entry) tableBody.insertBefore(row, entry);
            else tableBody.appendChild(row);
        });
        pinEntryRowToBottom();
        updateTotals();
    };

    const loadDraft = () => {
        const raw = sessionStorage.getItem(DRAFT_KEY);
        if (!raw) return false;
        let draft = null;
        try {
            draft = JSON.parse(raw);
        } catch (e) {
            return false;
        }
        if (!draft || !draft.header) return false;
        const header = draft.header || {};
        const draftCustomerCode = header.customer_code || '';
        const draftCustomerName = header.customer_name || '';
        const draftCustomerDisplay = header.customer_display || '';
        setValue(billNo, header.bill_no || '');
        setValue(billDate, header.bill_date || '');
        syncBillDateFromOpen();
        setValue(billTime, header.bill_time || '');
        setValue(billType, header.bill_type || '');
        setValue(deliveryDate, header.delivery_date || '');
        setValue(remarks, header.remarks || '');
        setValue(orderNoEl, header.order_no || header.orderno || '');
        setValue(customerDisplay, draftCustomerDisplay || formatCustomerDisplay(draftCustomerCode, draftCustomerName));
        setValue(customerCode, draftCustomerCode);
        setValue(customerName, draftCustomerName);
        setValue(customerPhone, header.customer_phone || '');
        setValue(customerCategory, header.customer_category || '');
        setValue(customerAddress, header.customer_address || '');
        setValue(creditLimit, header.credit_limit || '');
        setValue(totalPoints, header.total_points || '');
        if (outstandingAmount) {
            outstandingAmount.dataset.outstandingCash = header.outstanding_cash || '';
            outstandingAmount.dataset.currentCredit = header.current_credit || '';
            outstandingAmount.dataset.customerBillingType = header.customer_billing_type || 'CASH';
        }
        updateOutstandingByBillType();
        setValue(priceMode, header.price_mode || '');
        setValue(priceModeDisplay, header.price_mode_display || '');
        syncAdditionalDiscount(header.additional_discount || '');
        promotionDiscount = Number(header.promotion_discount) || 0;
        appliedVouchers = Array.isArray(header.applied_vouchers) ? header.applied_vouchers : [];

        if (warehouseEnabled) {
            setValue(warehouseIdEl, header.warehouse_id || '');
            setValue(warehouseCodeEl, header.warehouse_code || '');
            setValue(warehouseNameEl, header.warehouse_name || '');
            setValue(warehouseDisplay, header.warehouse_display || formatWarehouseDisplay(header.warehouse_code, header.warehouse_name));
            showClear(warehouseClear, Boolean(header.warehouse_id || header.warehouse_code));
        }

        showClear(customerClear, !!customerCode?.value);
        showClear(priceModeClear, !!priceMode?.value);
        syncCustomerDetailsModal();

        restoreLines(Array.isArray(draft.lines) ? draft.lines : []);
        updateTotals();
        return true;
    };

    const applyInitialOrder = (payload, opts) => {
        if (!payload || !payload.header || !Array.isArray(payload.lines)) return false;
        const options = opts || {};
        const keepReturnBillNo = Boolean(options.keepReturnBillNo && isSalesReturn);
        const header = payload.header || {};
        const code = header.customercode || '';
        const name = header.customername || '';
        const preservedBillNo = keepReturnBillNo ? String(billNo?.value || '').trim() : '';
        if (!keepReturnBillNo) {
            setValue(billNo, header.billno || '');
        }
        if (header.billdate) setValue(billDate, header.billdate);
        if (header.billtime) setValue(billTime, header.billtime);
        if (header.billtype) setValue(billType, header.billtype);
        // Keep Cash/Credit hint in sync for save confirm (C=Cash, R=Credit)
        if (outstandingAmount) {
            let billingHint = String(header.customer_billing_type || '').trim().toUpperCase();
            if (!billingHint) {
                const bt = String(header.billtype || '').trim().toUpperCase();
                billingHint = (bt === 'R' || bt === 'CREDIT' || bt === 'CR') ? 'CREDIT' : 'CASH';
            }
            outstandingAmount.dataset.customerBillingType = billingHint === 'CREDIT' || billingHint === 'R' || billingHint === 'CR'
                ? 'CREDIT'
                : 'CASH';
        }
        setValue(customerDisplay, formatCustomerDisplay(code, name));
        setValue(customerCode, code);
        setValue(customerName, name);
        setValue(remarks, header.remarks || '');
        setValue(orderNoEl, header.orderno || header.order_no || '');
        if (invoiceBillNoLoad && header.source_invoice_billno) {
            setValue(invoiceBillNoLoad, header.source_invoice_billno);
        }
        // Invoice DISCOUNTAMOUNT is already in line discounts — never treat as addl disc.
        if (header.source_invoice_billno) {
            syncAdditionalDiscount('');
        } else if (header.additional_discount != null && header.additional_discount !== '') {
            syncAdditionalDiscount(header.additional_discount);
        } else if (header.discountamount != null && header.discountamount !== '') {
            syncAdditionalDiscount(header.discountamount);
        }
        showClear(customerClear, Boolean(header.customercode));
        if (warehouseEnabled && (header.warehouse_id || header.warehouse_code)) {
            setValue(warehouseIdEl, header.warehouse_id || '');
            setValue(warehouseCodeEl, header.warehouse_code || '');
            setValue(warehouseNameEl, header.warehouse_name || '');
            setValue(warehouseDisplay, formatWarehouseDisplay(header.warehouse_code, header.warehouse_name));
            showClear(warehouseClear, Boolean(header.warehouse_id || header.warehouse_code));
        }
        restoreLines(payload.lines || []);
        if (keepReturnBillNo && preservedBillNo) {
            setValue(billNo, preservedBillNo);
        }
        // Keep source invoice billno for save (orderno uniqueness / audit).
        if (header.source_invoice_billno != null && form) {
            form.dataset.sourceInvoiceBillno = String(header.source_invoice_billno);
        }
        syncBillDateFromOpen();
        updateTotals();
        syncRefDisplay();
        syncCustomerDetailsModal();
        return true;
    };

    const loadInvoiceForReturn = async () => {
        if (!isSalesReturn) return;
        const raw = String(invoiceBillNoLoad?.value || orderNoEl?.value || '').trim();
        if (!/^\d+$/.test(raw) || Number(raw) <= 0) {
            alert('Enter a sales invoice bill number to load.');
            invoiceBillNoLoad?.focus();
            return;
        }
        const prevLabel = btnLoadInvoice ? btnLoadInvoice.textContent : '';
        if (btnLoadInvoice) {
            btnLoadInvoice.disabled = true;
            btnLoadInvoice.textContent = '…';
        }
        try {
            const res = await fetch(loadInvoiceApiBase + '/' + encodeURIComponent(raw), {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                alert((data && data.error) || 'Could not load sales invoice ' + raw + '.');
                return;
            }
            const ok = applyInitialOrder(
                { header: data.header || {}, lines: data.lines || [] },
                { keepReturnBillNo: true },
            );
            if (!ok) {
                alert('Invoice loaded but could not apply details to the form.');
                return;
            }
            setValue(orderNoEl, String((data.header && data.header.orderno) || raw));
            if (invoiceBillNoLoad) setValue(invoiceBillNoLoad, raw);
        } catch (e) {
            alert('Network error loading sales invoice.');
        } finally {
            if (btnLoadInvoice) {
                btnLoadInvoice.disabled = false;
                btnLoadInvoice.textContent = prevLabel || 'Load';
            }
        }
    };

    const scrollTableToBottom = () => {
        const scrollEl = tableBody?.closest('.scroll-table');
        if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    };

    const setItemFromRow = (row) => {
        currentItem.itemCode = row.dataset.code || '';
        currentItem.itemName = row.dataset.name || '';
        currentItem.barcode = row.dataset.barcode || '';
        setValue(barcodeInput, currentItem.barcode || '');
        currentItem.baseUom = row.dataset.uom || '';
        currentItem.retail = Number(row.dataset.retail || 0);
        currentItem.wholesale = Number(row.dataset.wholesale || 0);
        currentItem.third = Number(row.dataset.third || 0);
        currentItem.branch = Number(row.dataset.branch || 0);
        currentItem.cost = Number(row.dataset.cost || 0);
        currentItem.factor = 1;

        setValue(itemCodeDisplay, currentItem.itemCode);
        setValue(itemCodeHidden, currentItem.itemCode);
        setValue(itemName, currentItem.itemName);
        setValue(uomDisplay, currentItem.baseUom);
        setValue(uomCode, currentItem.baseUom);
        showClear(itemClear, true);
        showClear(uomClear, true);
        updateRateFromMode();
        clearSalesLotPick();
        fetchItemUoms(currentItem.itemCode).then(() => {
            applyUomSelection(currentItem.baseUom);
        });
        fetchInventoryLocations(currentItem.itemCode);
    };

    const setItemFromGridRow = (row) => {
        if (!row || !row.dataset.itemCode) return;
        editingRow = row;
        setEditorMode(true);
        currentItem.itemCode = row.dataset.itemCode || '';
        currentItem.itemName = row.dataset.itemName || '';
        currentItem.baseUom = row.dataset.uom || '';
        currentItem.barcode = row.dataset.barcode || '';
        setValue(barcodeInput, currentItem.barcode);
        currentItem.cost = Number(row.dataset.cost || 0);
        currentItem.factor = Number(row.dataset.baseQty || 0) && Number(row.dataset.quantity || 0)
            ? Number(row.dataset.baseQty || 0) / Number(row.dataset.quantity || 0)
            : 1;

        setValue(itemCodeDisplay, currentItem.itemCode);
        setValue(itemCodeHidden, currentItem.itemCode);
        setValue(itemName, currentItem.itemName);
        setValue(uomDisplay, currentItem.baseUom);
        setValue(uomCode, currentItem.baseUom);
        setValue(inventoryLocation, row.dataset.store || '');
        if (warehouseEnabled) {
            applyLineWarehouseSelection(
                row.dataset.warehouseId || '',
                row.dataset.warehouseCode || row.dataset.store || '',
                row.dataset.warehouseName || '',
            );
        }
        if (binEnabled) {
            applyLineBinSelection(
                row.dataset.storageId || '',
                row.dataset.binCode || '',
                row.dataset.binName || '',
            );
        }
        setValue(quantity, row.dataset.quantity || '');
        setValue(rate, row.dataset.rate ? formatRate(row.dataset.rate) : '');
        setValue(discount, row.dataset.discount || '');
        updateLineAmount();
        showClear(itemClear, true);
        showClear(uomClear, true);
        if (warehouseEnabled) {
            showClear(lineWarehouseClear, Boolean(row.dataset.warehouseCode || row.dataset.store));
        } else {
            showClear(inventoryClear, Boolean(row.dataset.store));
        }
        if (binEnabled) {
            showClear(lineBinClear, Boolean(row.dataset.binCode || row.dataset.storageId));
        }
        const lidGrid = row.dataset.lotId || '';
        if (salesLotId) salesLotId.value = lidGrid;
        if (salesLotDisplay) salesLotDisplay.value = lidGrid ? (row.dataset.lotLabel || '') : '';
        fetchItemUoms(currentItem.itemCode).then(() => {
            applyUomSelection(row.dataset.uom || currentItem.baseUom);
        });
        fetchInventoryLocations(currentItem.itemCode);
        if (quantity) {
            quantity.focus();
        }
        scrollTableToBottom();
    };

    const updateRateFromMode = () => {
        const mode = (priceMode.value || 'retail').toLowerCase();
        let newRate = currentItem.retail;
        if (mode === 'wholesale') newRate = currentItem.wholesale;
        if (mode === 'third') newRate = currentItem.third;
        if (mode === 'branch') newRate = currentItem.branch;
        setValue(rate, formatRate(newRate));
        updateLineAmount();
    };

    let siEntryAmountEditing = false;

    const parseEntryAmount = (raw) => {
        const n = parseFloat(String(raw ?? '').trim());
        return Number.isFinite(n) ? n : 0;
    };

    const isEntryAmountBlank = (raw) => {
        const s = String(raw ?? '').trim();
        return s === '' || s === '-' || s === '.' || s === '-.';
    };

    const updateLineAmount = () => {
        if (siEntryAmountEditing) return;
        const enteredQty = Number(quantity?.value || 0);
        const qty = isSalesReturn ? -Math.abs(enteredQty) : enteredQty;
        const lineRate = Number(rate?.value || 0);
        let lineDiscount = Number(discount?.value || 0);
        const gross = Math.abs(qty) * lineRate;
        if (lineDiscount > gross) {
            lineDiscount = gross;
            setValue(discount, formatNumber(lineDiscount));
        }
        const amountAbs = gross - lineDiscount;
        const amount = isSalesReturn ? -amountAbs : amountAbs;
        setValue(lineAmount, formatNumber(amount));
    };

    const updateRateFromAmount = () => {
        const qtyAbs = Math.abs(Number(quantity?.value || 0));
        if (qtyAbs <= 0) return;
        if (isEntryAmountBlank(lineAmount?.value)) return;
        let lineDiscount = Number(discount?.value || 0);
        let netAmountAbs = Math.abs(parseEntryAmount(lineAmount?.value));
        const gross = netAmountAbs + lineDiscount;
        if (lineDiscount > gross) {
            lineDiscount = gross;
            setValue(discount, formatNumber(lineDiscount));
            netAmountAbs = Math.max(0, gross - lineDiscount);
        }
        const newRate = gross / qtyAbs;
        setValue(rate, formatRate(newRate));
        if (!siEntryAmountEditing) {
            const signedAmount = isSalesReturn ? -netAmountAbs : netAmountAbs;
            setValue(lineAmount, formatNumber(signedAmount));
        }
    };

    let currentItemFilter = 'all';
    const ITEM_POPUP_PREVIEW_LIMIT = 30;

    const resolveItemPopupWarehouseId = () => {
        if (!warehouseEnabled) return 0;
        let whId = parseInt(warehouseIdEl?.value, 10) || 0;
        if (whId <= 0) {
            whId = parseInt(salesWarehouseCfg.defaultId, 10) || 0;
        }
        return whId;
    };

    const itemPopupPriceForItem = (item) => {
        const mode = (priceMode?.value || 'retail').toLowerCase();
        const priceMap = {
            retail: item.retailprice,
            wholesale: item.wholesaleprice,
            third: item.thirdprice,
            branch: item.branchprice,
        };
        return priceMap[mode] ?? item.retailprice ?? 0;
    };

    const mapItemPopupToPickerRow = (item) => {
        const price = itemPopupPriceForItem(item);
        return {
            code: item.itemcode || '',
            name: salesItemDisplayName(item) || '',
            barcode: item.manufacturerid || '',
            uom: item.unit || item.baseuom || 'NOS',
            cost: Number(item.costprice || 0),
            retail: Number(price || item.retailprice || 0),
            wholesale: Number(item.wholesaleprice || 0),
            third: Number(item.thirdprice || 0),
            branch: Number(item.branchprice || 0),
            ownproduct: item.ownproduct || '',
            stock: Number(item.stock != null ? item.stock : 0),
        };
    };

    const fetchItemPopupPickerRows = async (filterKey, searchTerm, signal) => {
        const normalizedFilter = (filterKey || 'all').toLowerCase();
        if (normalizedFilter === 'customer_item') {
            if (!customerCode?.value) {
                alert('Select customer first.');
                focusCustomerField();
                return [];
            }
            if (!billNo?.value) {
                alert('Bill no not generated yet.');
                return [];
            }
        }
        const params = new URLSearchParams();
        params.set('filter', normalizedFilter || 'all');
        if (searchTerm) {
            params.set('search', searchTerm);
            params.set('limit', '100');
        } else {
            params.set('limit', String(ITEM_POPUP_PREVIEW_LIMIT));
        }
        if (priceMode?.value) params.set('price_mode', priceMode.value);
        if (warehouseEnabled) {
            const whId = resolveItemPopupWarehouseId();
            if (whId > 0) params.set('warehouse_id', String(whId));
        }
        if (customerCode?.value) params.set('customer_code', customerCode.value);
        if (billNo?.value) params.set('bill_no', billNo.value);
        if (itemCodeHidden?.value) params.set('seed_item_code', itemCodeHidden.value);
        if (isSalesReturn) params.set('is_sales_return', '1');
        const res = await fetch(`${apiBase}/item-popup-items?${params.toString()}`, { signal });
        const data = await res.json();
        if (!data.success) return [];
        return (data.items || []).map(mapItemPopupToPickerRow);
    };

    const renderUomOptions = (uoms) => {
        if (!uomModalBody) return;
        if (!uoms || !uoms.length) {
            uomModalBody.innerHTML = `
                <tr class="table-empty">
                    <td colspan="2">No UOMs available.</td>
                </tr>
            `;
            return;
        }
        uomModalBody.innerHTML = uoms.map(uom => `
            <tr data-code="${uom.code || ''}" data-name="${uom.name || uom.code || ''}">
                <td>${uom.code || '-'}</td>
                <td>${uom.name || uom.code || '-'}</td>
            </tr>
        `).join('');
    };

    const renderHistoryTable = (type, rows) => {
        if (!historyModalBody || !historyModalHead) return;
        const isCustomer = type === 'customer_item';
        if (isCustomer) {
            historyModalHead.innerHTML = `
                <tr>
                    <th>Sl.No</th>
                    <th>Bill No</th>
                    <th>Bill Date</th>
                    <th>Item Code</th>
                    <th>Quantity</th>
                    <th>Uom</th>
                    <th>Rate</th>
                    <th>Discount</th>
                    <th>Total</th>
                </tr>
            `;
        } else {
            historyModalHead.innerHTML = `
                <tr>
                    <th>Sl.No</th>
                    <th>Bill No</th>
                    <th>Bill Date</th>
                    <th>Code</th>
                    <th>Customer Name</th>
                    <th>Qty</th>
                    <th>Uom</th>
                    <th>Rate</th>
                    <th>Discount</th>
                    <th>Total</th>
                </tr>
            `;
        }

        if (!rows || !rows.length) {
            const colCount = isCustomer ? 9 : 10;
            historyModalBody.innerHTML = `
                <tr class="table-empty">
                    <td colspan="${colCount}">No history found.</td>
                </tr>
            `;
            return;
        }

        historyModalBody.innerHTML = rows.map((row, index) => {
            if (isCustomer) {
                return `
                    <tr>
                        <td>${index + 1}</td>
                        <td>${row.billno || '-'}</td>
                        <td>${row.billdate || '-'}</td>
                        <td>${row.itemcode || '-'}</td>
                        <td>${formatNumber(row.quantity || 0, 3)}</td>
                        <td>${row.uom || '-'}</td>
                        <td>${formatRate(row.rate || 0)}</td>
                        <td>${formatNumber(row.discount || 0)}</td>
                        <td>${formatNumber(row.total || 0)}</td>
                    </tr>
                `;
            }
            return `
                <tr>
                    <td>${index + 1}</td>
                    <td>${row.billno || '-'}</td>
                    <td>${row.billdate || '-'}</td>
                    <td>${row.itemcode || '-'}</td>
                    <td>${row.customername || '-'}</td>
                    <td>${formatNumber(row.quantity || 0, 3)}</td>
                    <td>${row.uom || '-'}</td>
                    <td>${formatRate(row.rate || 0)}</td>
                    <td>${formatNumber(row.discount || 0)}</td>
                    <td>${formatNumber(row.total || 0)}</td>
                </tr>
            `;
        }).join('');
    };

    const fetchHistoryRows = async (type) => {
        if (!itemCodeHidden?.value) {
            alert('Select an item first.');
            return;
        }
        if (type === 'customer_item' && !customerCode?.value) {
            alert('Select customer first.');
            focusCustomerField();
            return;
        }
        try {
            const params = new URLSearchParams();
            params.set('type', type);
            params.set('item_code', itemCodeHidden.value);
            if (customerCode?.value) params.set('customer_code', customerCode.value);
            const res = await fetch(`${apiBase}/item-history?${params.toString()}`);
            const data = await res.json();
            if (!data.success) {
                renderHistoryTable(type, []);
                return;
            }
            renderHistoryTable(type, data.items || []);
        } catch (e) {
            console.error('Failed to fetch item history', e);
            renderHistoryTable(type, []);
        }
    };

    const renderInventoryRows = (items) => {
        if (!inventoryModalBody) return;
        const colSpan = warehouseEnabled ? 3 : 2;
        const emptyLabel = warehouseEnabled ? 'No warehouses found.' : 'No stores found.';
        if (!items || !items.length) {
            inventoryModalBody.innerHTML = `
                <tr class="table-empty">
                    <td colspan="${colSpan}">${emptyLabel}</td>
                </tr>
            `;
            return;
        }
        const hasPositive = items.some(item => Number(item.stock || 0) > 0);
        const displayItems = hasPositive
            ? items.filter(item => Number(item.stock || 0) > 0)
            : items;
        if (!displayItems.length) {
            inventoryModalBody.innerHTML = `
                <tr class="table-empty">
                    <td colspan="${colSpan}">${emptyLabel}</td>
                </tr>
            `;
            return;
        }
        if (warehouseEnabled) {
            inventoryModalBody.innerHTML = displayItems.map((item) => {
                const whId = item.warehouse_id != null ? String(item.warehouse_id) : String(item.code || '');
                const whCode = String(item.store || item.warehouse_code || '').trim();
                const whName = String(item.description || item.name || '').trim();
                return `
            <tr data-id="${whId}" data-code="${whCode}" data-name="${whName}" data-store="${whCode}" data-stock="${item.stock || 0}">
                <td>${whCode || '-'}</td>
                <td>${whName || '-'}</td>
                <td>${formatNumber(item.stock || 0, 3)}</td>
            </tr>`;
            }).join('');
            return;
        }
        inventoryModalBody.innerHTML = displayItems.map(item => `
            <tr data-store="${item.store || ''}" data-stock="${item.stock || 0}">
                <td>${item.store || '-'}</td>
                <td>${formatNumber(item.stock || 0, 3)}</td>
            </tr>
        `).join('');
    };

    const applyInventorySelection = (store) => {
        if (!store) return;
        setValue(inventoryLocation, store);
        showClear(inventoryClear, true);
    };

    let _invLoadAbort = null;
    const loadInventoryModalRows = async (itemCode) => {
        if (!itemCode) {
            renderInventoryRows([]);
            return;
        }
        if (_invLoadAbort) _invLoadAbort.abort();
        _invLoadAbort = new AbortController();
        const signal = _invLoadAbort.signal;
        try {
            const res = await fetch(`${apiBase}/item-inventory?item_code=${encodeURIComponent(itemCode)}`, { signal });
            const data = await res.json();
            if (!data.success) {
                renderInventoryRows([]);
                return;
            }
            renderInventoryRows(data.items || []);
        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('Failed to fetch item inventory', e);
            renderInventoryRows([]);
        }
    };

    const renderBinRows = (bins) => {
        if (!binModalBody) return;
        if (!bins || !bins.length) {
            binModalBody.innerHTML = `
                <tr class="table-empty">
                    <td colspan="3">No bins found.</td>
                </tr>
            `;
            return;
        }
        const hasPositive = bins.some((row) => Number(row.stock || 0) > 0);
        const displayItems = hasPositive
            ? bins.filter((row) => Number(row.stock || 0) > 0)
            : bins;
        if (!displayItems.length) {
            binModalBody.innerHTML = `
                <tr class="table-empty">
                    <td colspan="3">No bins with stock.</td>
                </tr>
            `;
            return;
        }
        binModalBody.innerHTML = displayItems.map((row) => {
            const sid = row.storage_id != null ? String(row.storage_id) : '';
            const code = String(row.code || '').trim();
            const name = String(row.name || '').trim();
            return `
            <tr data-id="${sid}" data-code="${code}" data-name="${name}" data-stock="${row.stock || 0}">
                <td>${code || '-'}</td>
                <td>${name || '-'}</td>
                <td>${formatNumber(row.stock || 0, 3)}</td>
            </tr>`;
        }).join('');
    };

    const loadBinModalRows = async () => {
        if (!binEnabled || !binModalBody) {
            renderBinRows([]);
            return;
        }
        const whId = parseInt(lineWarehouseId?.value, 10) || 0;
        if (!whId) {
            renderBinRows([]);
            return;
        }
        const itemCode = (itemCodeHidden?.value || '').trim();
        const itemBinApi = (salesBinCfg.itemBinInventoryApi || `${apiBase}/item-bin-inventory`).trim();
        const whApi = (salesBinCfg.warehouseBinsApi || `${apiBase}/api/warehouse-bins`).trim();
        try {
            if (itemCode) {
                const res = await fetch(`${itemBinApi}?item_code=${encodeURIComponent(itemCode)}&warehouse_id=${encodeURIComponent(String(whId))}`);
                const data = await res.json();
                if (data.success) {
                    renderBinRows(data.bins || []);
                    return;
                }
            }
            const res = await fetch(`${whApi}?wh=${encodeURIComponent(String(whId))}`);
            const data = await res.json();
            if (!data.success) {
                renderBinRows([]);
                return;
            }
            const bins = (data.bins || []).map((b) => ({
                storage_id: b.storage_id,
                code: b.code,
                name: b.name,
                stock: 0,
            }));
            renderBinRows(bins);
        } catch (e) {
            console.error('Failed to fetch bins', e);
            renderBinRows([]);
        }
    };

    const fetchInventoryLocations = async (itemCode) => {
        if (warehouseEnabled) {
            await resolveLineWarehouseForItem(itemCode);
            return;
        }
        if (!itemCode) {
            renderInventoryRows([]);
            setValue(inventoryLocation, '');
            showClear(inventoryClear, false);
            return;
        }
        try {
            const res = await fetch(`${apiBase}/item-inventory?item_code=${encodeURIComponent(itemCode)}`);
            const data = await res.json();
            if (!data.success) {
                renderInventoryRows([]);
                return;
            }
            const items = data.items || [];
            renderInventoryRows(items);
            if (!inventoryLocation?.value) {
                const hasPositive = items.some(item => Number(item.stock || 0) > 0);
                const listForBest = hasPositive
                    ? items.filter(item => Number(item.stock || 0) > 0)
                    : items;
                if (listForBest.length) {
                    const bestRow = pickBestStockRow(listForBest);
                    if (bestRow && bestRow.store) {
                        applyInventorySelection(String(bestRow.store));
                    }
                }
            }
        } catch (e) {
            console.error('Failed to fetch item inventory', e);
            renderInventoryRows([]);
        }
    };

    const fetchItemUoms = async (itemCode) => {
        if (!itemCode) return [];
        try {
            const res = await fetch(`${apiBase}/item-uoms?item_code=${encodeURIComponent(itemCode)}`);
            const data = await res.json();
            if (!data.success) {
                renderUomOptions([]);
                return [];
            }
            const uoms = data.uoms || [];
            renderUomOptions(uoms);
            return uoms;
        } catch (e) {
            console.error('Failed to fetch item UOMs', e);
            renderUomOptions([]);
            return [];
        }
    };

    const applyUomSelection = (uomValue) => {
        if (!uomValue) return;
        setValue(uomDisplay, uomValue);
        setValue(uomCode, uomValue);
        showClear(uomClear, true);
        updatePricingByUom();
    };

    const updatePricingByUom = async () => {
        if (!currentItem.itemCode || !uomCode.value) return;
        try {
            const res = await fetch(`${apiBase}/uom-info?item_code=${encodeURIComponent(currentItem.itemCode)}&uom_code=${encodeURIComponent(uomCode.value)}&price_mode=${encodeURIComponent(priceMode.value)}`);
            const data = await res.json();
            if (!data.success) {
                alert(data.error || 'UOM not available');
                setValue(uomDisplay, currentItem.baseUom);
                setValue(uomCode, currentItem.baseUom);
                currentItem.factor = 1;
                updateRateFromMode();
                return;
            }
            const pricing = data.pricing;
            currentItem.factor = Number(pricing.conversion_factor || 1);
            currentItem.cost = Number(pricing.cost_price || currentItem.cost || 0);
            setValue(rate, formatRate(pricing.rate || 0));
        } catch (e) {
            console.error('Failed to fetch UOM pricing', e);
        }
    };

    const fetchItemByBarcode = async (barcode, options = {}) => {
        const showNotFoundAlert = options.showNotFoundAlert !== false;
        const notFoundMessage = options.notFoundMessage || 'Item not found';
        const focusOnSuccess = options.focusOnSuccess !== false;
        try {
            const res = await fetch(`${apiBase}/item-info?query=${encodeURIComponent(barcode)}`);
            const data = await res.json();
            if (!data.success) {
                if (showNotFoundAlert) {
                    alert(data.error || notFoundMessage);
                }
                return false;
            }
            const item = data.item || {};
            currentItem.itemCode = item.itemcode || '';
            currentItem.itemName = salesItemDisplayName(item);
            currentItem.barcode = item.manufacturerid || '';
            currentItem.baseUom = item.baseuom || '';
            currentItem.retail = Number(item.retailprice || 0);
            currentItem.wholesale = Number(item.wholesaleprice || 0);
            currentItem.third = Number(item.thirdprice || 0);
            currentItem.branch = Number(item.branchprice || 0);
            currentItem.cost = Number(item.costprice || 0);
            currentItem.factor = 1;

            setValue(barcodeInput, currentItem.barcode || barcode);
            setValue(itemCodeDisplay, currentItem.itemCode);
            setValue(itemCodeHidden, currentItem.itemCode);
            setValue(itemName, currentItem.itemName);
            setValue(uomDisplay, currentItem.baseUom);
            setValue(uomCode, currentItem.baseUom);
            showClear(itemClear, true);
            showClear(uomClear, true);
            updateRateFromMode();
            clearSalesLotPick();
            fetchItemUoms(currentItem.itemCode).then(() => {
                applyUomSelection(currentItem.baseUom);
            });
            fetchInventoryLocations(currentItem.itemCode);
            if (focusOnSuccess && quantity) {
                quantity.focus();
            }
            return true;
        } catch (e) {
            console.error('Barcode lookup failed', e);
            return false;
        }
    };

    const updateOutstandingByBillType = () => {
        if (!outstandingAmount) return;
        const cashOutstanding = Number(outstandingAmount.dataset.outstandingCash || 0);
        const currentCredit = Number(outstandingAmount.dataset.currentCredit || 0);
        const billingType = (outstandingAmount.dataset.customerBillingType || 'CASH').toUpperCase();
        const isCredit = billingType === 'CREDIT';
        const value = isCredit ? currentCredit : cashOutstanding;
        setValue(outstandingAmount, formatNumber(value));
        syncCustomerDetailsModal();
    };

    const applyCustomerBillingType = (billingType) => {
        const bt = billingType != null && String(billingType).trim() !== '' ? billingType : 'CASH';
        if (window.NexaCustomerBilling) {
            NexaCustomerBilling.applyBillTypeFromBillingType(billType, bt);
        } else {
            setValue(billType, String(bt).toUpperCase() === 'CREDIT' ? 'R' : 'C');
        }
        updateOutstandingByBillType();
    };

    const handleEnterMove = (event, nextFocus, action) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        if (typeof action === 'function') {
            action();
            return;
        }
        if (nextFocus && typeof nextFocus.focus === 'function') {
            nextFocus.focus();
        }
    };

    const appendOrMergeLine = (spec, options = {}) => {
        const mergeSilently = options.mergeSilently === true;
        const skipConfirmZeroNet = options.skipConfirmZeroNet === true;

        const itemCodeVal = String(spec.itemCode || '').trim();
        const itemNameVal = String(spec.itemName || '').trim();
        const uomVal = String(spec.uom || '').trim();
        const whIdVal = spec.warehouseId != null ? String(spec.warehouseId) : '';
        const storageIdVal = spec.storageId != null ? String(spec.storageId) : '';
        const storeVal = String(spec.store || '').trim();
        const lotIdVal = String(spec.lotId || '').trim();
        const lotLabelVal = String(spec.lotLabel || '').trim();
        const lineCost = Number(spec.cost || 0);
        const lineFactor = Number(spec.factor || 1) || 1;

        if (warehouseEnabled && !(parseInt(whIdVal, 10) > 0)) return false;
        if (binEnabled && !(parseInt(storageIdVal, 10) > 0)) return false;
        if (!itemCodeVal || !uomVal) return false;

        let qty = Number(spec.qty || 0);
        if (isSalesReturn) {
            qty = -Math.abs(qty);
            if (qty >= 0) return false;
        } else if (qty <= 0) {
            return false;
        }

        let lineRate = Number(spec.rate || 0);
        let lineDiscount = Number(spec.discount || 0);
        let targetRow = editingRow || null;

        if (!targetRow) {
            const existingRow = Array.from(tableBody.querySelectorAll('tr[data-line]'))
                .find((row) =>
                    row.dataset.itemCode === itemCodeVal &&
                    row.dataset.uom === uomVal &&
                    (warehouseEnabled
                        ? (row.dataset.warehouseId || '') === whIdVal
                        : (row.dataset.store || '') === storeVal) &&
                    (!binEnabled || (row.dataset.storageId || '') === storageIdVal) &&
                    (!batchEnabled || (row.dataset.lotId || '') === lotIdVal)
                );
            if (existingRow) {
                if (mergeSilently) {
                    qty += Number(existingRow.dataset.quantity || 0);
                    lineDiscount += Number(existingRow.dataset.discount || 0);
                    if (!lineRate) {
                        lineRate = Number(existingRow.dataset.rate || 0);
                    }
                    targetRow = existingRow;
                } else {
                    siMarkDuplicateDataRow(existingRow);
                    siMarkEntryInvalid('si-col-itemcode', true, 'This line is already added (same item, UOM, store, barcode, and location).');
                    siMarkEntryInvalid('si-col-uom', true, 'Duplicate line — change item, UOM, store, or barcode.');
                    alert('This line is already added (same item, UOM, store, barcode, and location). Change one of those fields or edit the existing line.');
                    return false;
                }
            }
        }

        const gross = Math.abs(qty) * lineRate;
        if (lineDiscount > gross) {
            if (!mergeSilently) {
                siMarkEntryInvalid('si-col-disc', true, 'Discount cannot be greater than line amount.');
                alert('Discount cannot be greater than amount.');
                if (discount) discount.focus();
            }
            return false;
        }
        if (!skipConfirmZeroNet && gross > 0 && lineDiscount === gross) {
            const ok = window.confirm('Discount equals amount. Net amount is 0. Continue?');
            if (!ok) {
                if (discount) discount.focus();
                return false;
            }
        }

        const amountAbs = gross - lineDiscount;
        const amount = isSalesReturn ? -amountAbs : amountAbs;
        const baseQty = qty * lineFactor;
        const row = targetRow || document.createElement('tr');
        const isNewRow = !targetRow;
        const whCodeVal = String(spec.warehouseCode || storeVal || '').trim();
        const whNameVal = String(spec.warehouseName || '').trim();
        const binCodeVal = String(spec.binCode || '').trim();
        const binNameVal = String(spec.binName || '').trim();

        row.dataset.itemCode = itemCodeVal;
        row.dataset.barcode = String(spec.barcode || '').trim();
        row.dataset.itemName = itemNameVal;
        row.dataset.uom = uomVal;
        row.dataset.store = warehouseEnabled ? whCodeVal : storeVal;
        if (warehouseEnabled) {
            row.dataset.warehouseId = whIdVal;
            row.dataset.warehouseCode = whCodeVal;
            row.dataset.warehouseName = whNameVal;
        }
        if (binEnabled) {
            row.dataset.storageId = storageIdVal;
            row.dataset.binCode = binCodeVal;
            row.dataset.binName = binNameVal;
        }
        row.dataset.quantity = qty;
        row.dataset.rate = lineRate;
        row.dataset.discount = lineDiscount;
        row.dataset.amount = amount;
        row.dataset.baseQty = baseQty;
        row.dataset.cost = lineCost;
        row.dataset.lotId = lotIdVal;
        row.dataset.lotLabel = lotIdVal ? lotLabelVal : '';

        const rowHtmlData = {
            lotId: row.dataset.lotId,
            lotLabel: row.dataset.lotLabel,
            barcode: row.dataset.barcode || '',
            itemCode: itemCodeVal,
            itemName: itemNameVal,
            uom: uomVal,
            rate: lineRate,
            quantity: qty,
            store: row.dataset.store,
            warehouseCode: row.dataset.warehouseCode,
            warehouseName: row.dataset.warehouseName,
            warehouseLabel: formatWarehouseDisplay(row.dataset.warehouseCode, row.dataset.warehouseName),
            binCode: row.dataset.binCode,
            binName: row.dataset.binName,
            binLabel: formatBinDisplay(row.dataset.binCode, row.dataset.binName),
            discount: lineDiscount,
            amount,
        };

        if (isNewRow) {
            removeTableEmpty();
            const rowCount = tableBody.querySelectorAll('tr[data-line]').length;
            row.dataset.line = String(rowCount + 1);
            row.innerHTML = buildLineRowHtml(rowCount + 1, rowHtmlData);
            const entry = getEntryRow();
            if (entry) tableBody.insertBefore(row, entry);
            else tableBody.appendChild(row);
            pinEntryRowToBottom();
            scrollTableToBottom();
        } else {
            row.innerHTML = buildLineRowHtml(Number(row.dataset.line || 0) || 1, rowHtmlData);
        }
        return true;
    };

    const addLine = async () => {
        if (!siRequireHeaderWarehouse()) return;
        if (siAddLineValidatePending) return;
        siAddLineValidatePending = true;
        const valid = await siValidateEntryBeforeAdd();
        siAddLineValidatePending = false;
        if (!valid) {
            siFocusFirstEntryInvalid();
            return;
        }
        const enteredQty = Number(quantity.value || 0);
        const ok = appendOrMergeLine({
            itemCode: itemCodeHidden.value,
            barcode: currentItem.barcode || (barcodeInput?.value || '').trim(),
            itemName: itemName.value,
            uom: uomCode.value,
            qty: enteredQty,
            rate: rate.value,
            discount: discount.value,
            cost: currentItem.cost || 0,
            factor: currentItem.factor || 1,
            store: warehouseEnabled ? (lineWarehouseCode?.value || '') : (inventoryLocation?.value || ''),
            warehouseId: lineWarehouseId?.value,
            warehouseCode: lineWarehouseCode?.value,
            warehouseName: lineWarehouseName?.value,
            storageId: lineBinId?.value,
            binCode: lineBinCode?.value,
            binName: lineBinName?.value,
            lotId: salesLotId?.value?.trim() || '',
            lotLabel: salesLotDisplay?.value?.trim() || '',
        });
        if (!ok) {
            siFocusFirstEntryInvalid();
            return;
        }
        siClearAllLineHighlights();
        updateTotals();
        saveDraft();
        resetItemLine();
        focusEntryForNextLine();
    };

    const gatherLines = () => {
        return Array.from(tableBody.querySelectorAll('tr[data-line]')).map((row, index) => {
            const line = {
                slno: index + 1,
                item_code: row.dataset.itemCode,
                item_name: row.dataset.itemName,
                uom: row.dataset.uom,
                store: row.dataset.store,
                quantity: Number(row.dataset.quantity || 0),
                rate: Number(row.dataset.rate || 0),
                discount: Number(row.dataset.discount || 0),
                amount: Number(row.dataset.amount || 0),
                base_qty: Number(row.dataset.baseQty || 0),
                cost: Number(row.dataset.cost || 0),
                lot_id: row.dataset.lotId || '',
            };
            const whId = parseInt(row.dataset.warehouseId, 10) || 0;
            if (whId > 0) line.warehouse_id = whId;
            const sid = parseInt(row.dataset.storageId, 10) || 0;
            if (sid > 0) {
                line.storage_id = sid;
                line.bin_storage_id = sid;
                if (whId > 0) line.bin_loc_key = String(whId);
            }
            return line;
        });
    };

    const saveInvoice = async () => {
        if (saveInFlight) return;
        if (txnDateBlocked) {
            alert(txnDateError || 'No open transaction date. Set it in Transaction Date Setup before posting.');
            return;
        }
        const lines = gatherLines();
        if (!lines.length) {
            alert('No items to save.');
            return;
        }
        const zeroQtyLine = lines.find((ln) => siQtyMagnitude(ln.quantity) <= 0);
        if (zeroQtyLine) {
            alert('One or more lines have zero quantity. Enter a quantity greater than zero before saving.');
            return;
        }
        if (!customerCode.value) {
            alert('Select a customer.');
            focusCustomerField();
            return;
        }
        const orderNoVal = String(orderNoEl?.value || '').trim();
        if (orderNoMandatory && !orderNoVal) {
            alert('Enter Order No.');
            if (orderNoEl) {
                orderNoEl.focus();
                try { orderNoEl.select(); } catch (ignore) {}
            }
            return;
        }
        const lineBlockMsg = siGetLineValidationBlockMessage();
        if (lineBlockMsg) {
            alert(lineBlockMsg);
            return;
        }

        // Sales return: BILLTYPE C = Cash, R = Credit (from customer / loaded invoice; no prompt)
        let returnBillType = String(billType?.value || '').trim().toUpperCase().slice(0, 1);
        let returnBillingType = String(outstandingAmount?.dataset.customerBillingType || '').trim().toUpperCase();
        if (isSalesReturn) {
            if (returnBillingType === 'CREDIT' || returnBillingType === 'R' || returnBillingType === 'CR') {
                returnBillType = 'R';
                returnBillingType = 'CREDIT';
            } else if (returnBillingType === 'CASH' || returnBillingType === 'C') {
                returnBillType = 'C';
                returnBillingType = 'CASH';
            } else if (returnBillType === 'R') {
                returnBillingType = 'CREDIT';
            } else if (returnBillType === 'C') {
                returnBillingType = 'CASH';
            } else {
                alert('Select a customer to determine bill type (Cash/Credit).');
                return;
            }
            if (billType) billType.value = returnBillType;
            if (outstandingAmount) outstandingAmount.dataset.customerBillingType = returnBillingType;
            if (typeof window.NexaCustomerBilling?.applyBillTypeFromBillingType === 'function') {
                window.NexaCustomerBilling.applyBillTypeFromBillingType(billType, returnBillingType);
            }
        }

        let remarksVal = remarks?.value || '';
        if (appliedVouchers.length) {
            const voucherText = appliedVouchers.map(v => v.code + '(' + v.message + ')').join(', ');
            remarksVal = (remarksVal ? remarksVal + '; ' : '') + 'Voucher: ' + voucherText + (promotionDiscount ? '; Promo disc: ' + promotionDiscount : '');
        }
        const header = {
            billno: billNo.value,
            use_existing_billno: true,
            billdate: billDate.value,
            billtime: billTime.value,
            billtype: isSalesReturn ? returnBillType : (billType?.value || '').trim(),
            customer_billing_type: isSalesReturn
                ? returnBillingType
                : (outstandingAmount?.dataset.customerBillingType || 'CASH').toUpperCase(),
            customercode: customerCode.value,
            customername: customerName.value,
            sessioncode: 0,
            deliverydate: deliveryDate ? deliveryDate.value : '',
            remarks: remarksVal,
            address: customerAddress.value,
            orderno: orderNoVal.slice(0, 80),
        };
        const srcInv = parseInt(form?.dataset.sourceInvoiceBillno || invoiceBillNoLoad?.value || '0', 10) || 0;
        if (srcInv > 0) header.source_invoice_billno = srcInv;
        const addlDisc = Number(additionalDiscount?.value || additionalDiscountItems?.value || 0);
        if (addlDisc) header.discountamount = Math.abs(addlDisc);
        if (warehouseEnabled) {
            const whId = parseInt(warehouseIdEl?.value, 10) || 0;
            if (whId > 0) header.warehouse_id = whId;
            const whCode = headerWarehouseStoreCode();
            if (whCode) header.warehouse_code = whCode;
        }

        if (!window.confirm('Do you want to save?')) return;

        const overlayMsg = isSalesReturn ? 'Saving sales return…' : 'Saving invoice…';
        const saveBtnLabel = btnSave ? btnSave.textContent : 'Save';
        // Open blank tab while still in the click gesture so popup blockers allow PDF.
        let pdfWin = null;
        if (enablePrint) {
            try {
                pdfWin = window.open('about:blank', '_blank');
                if (pdfWin) {
                    try {
                        pdfWin.document.write('<!doctype html><title>Preparing PDF…</title><body style="font:14px sans-serif;padding:24px;color:#334155">Preparing sales return PDF…</body>');
                        pdfWin.document.close();
                    } catch (ignore) {}
                }
            } catch (ignore) {
                pdfWin = null;
            }
        }
        saveInFlight = true;
        if (btnSave) {
            btnSave.disabled = true;
            btnSave.textContent = 'Saving…';
        }
        try {
            const res = await fetch(`${saveBase}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header, lines }),
                loadingMessage: overlayMsg,
            });
            const data = await res.json();
            if (!data.success) {
                if (pdfWin && !pdfWin.closed) {
                    try { pdfWin.close(); } catch (ignore) {}
                }
                if ((data.duplicate_billno || data.duplicate_doc_key) && data.suggested_billno != null) {
                    header.billno = String(data.suggested_billno);
                    setValue(billNo, data.suggested_billno);
                    let pdfWin2 = null;
                    if (enablePrint) {
                        try { pdfWin2 = window.open('about:blank', '_blank'); } catch (ignore) { pdfWin2 = null; }
                    }
                    const res2 = await fetch(`${saveBase}/save`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ header, lines }),
                        loadingMessage: overlayMsg,
                    });
                    const data2 = await res2.json();
                    if (data2.success) {
                        if (data2.billno != null) setValue(billNo, data2.billno);
                        window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data2 }));
                        openSavedReturnPdf(data2.billno, data2.pdf_url, pdfWin2);
                        clearDraft();
                        resetForm();
                        return;
                    }
                    if (pdfWin2 && !pdfWin2.closed) {
                        try { pdfWin2.close(); } catch (ignore) {}
                    }
                }
                let msg = data.error || 'Save failed.';
                if (data.replay_blocked) {
                    msg += ' The save token was refreshed; try Save again.';
                }
                alert(msg);
                window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: data }));
                return;
            }
            if (data.billno != null) setValue(billNo, data.billno);
            window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data }));
            openSavedReturnPdf(data.billno, data.pdf_url, pdfWin);
            clearDraft();
            resetForm();
        } catch (e) {
            if (pdfWin && !pdfWin.closed) {
                try { pdfWin.close(); } catch (ignore) {}
            }
            console.error('Save failed', e);
            alert('Save failed.');
            window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: { error: String(e) } }));
        } finally {
            saveInFlight = false;
            if (btnSave) {
                btnSave.disabled = false;
                btnSave.textContent = saveBtnLabel;
            }
        }
    };

    let resetFormInFlight = false;

    const resetForm = async (opts = {}) => {
        const reserveBillNo = opts.reserveBillNo !== false;
        if (resetFormInFlight) return;
        resetFormInFlight = true;
        try {
            clearDraft();
            if (form) form.reset();
            resetCustomer();
            if (warehouseEnabled) resetWarehouse();
            resetItemLine();
            clearTable();
            updateBillDefaults();
            setDefaultPriceMode(true);
            if (reserveBillNo || !String(billNo?.value || '').trim()) {
                await fetchNextBillNo();
            } else {
                syncRefDisplay();
            }
            applyUserDefaultWarehouse();
            if (customerDisplay) {
                customerDisplay.focus();
            }
        } finally {
            resetFormInFlight = false;
        }
    };

    const initialOrderLoaded = applyInitialOrder(initialOrderPayload, { keepReturnBillNo: true });
    applyTxnDateBlockedUi();
    if (!initialOrderLoaded) {
        // Run immediately so a later listener error cannot skip bill no setup.
        void resetForm({ reserveBillNo: false });
    }
    if (btnLoadInvoice) {
        btnLoadInvoice.addEventListener('click', () => { void loadInvoiceForReturn(); });
    }
    if (invoiceBillNoLoad) {
        invoiceBillNoLoad.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                void loadInvoiceForReturn();
            }
        });
    }

    window.addEventListener('pageshow', (ev) => {
        if (ev.persisted && !initialOrderLoaded) {
            void resetForm({ reserveBillNo: true });
        }
    });


    const setupModal = (config) => {
        const modal = document.getElementById(config.modalId);
        const input = document.getElementById(config.inputId);
        const picker = document.getElementById(config.pickerId);
        const clear = document.getElementById(config.clearId);
        const modalSearch = document.getElementById(config.modalId + 'Search');
        const modalClear = document.getElementById(config.modalId + 'Clear');
        const modalTable = document.getElementById(config.modalId + 'Table');

        if (!modal || !input || !picker || !modalTable) return;

        let activeRow = null;

        const getVisibleRows = () => Array.from(modalTable.querySelectorAll('tbody tr'))
            .filter(row => row.style.display !== 'none');

        const isPlaceholderModalRow = (row) => {
            if (!row || row.classList.contains('table-empty')) return true;
            const tds = row.querySelectorAll(':scope > td');
            if (tds.length !== 1) return false;
            return Number(tds[0].getAttribute('colspan') || 1) > 1;
        };

        const getNavigateRows = () => {
            const rows = getVisibleRows();
            if (!config.strictModalRowNav) {
                return rows;
            }
            return rows.filter((r) => !isPlaceholderModalRow(r));
        };

        const setActiveRow = (row) => {
            if (activeRow) {
                activeRow.classList.remove('modal-row--active');
            }
            activeRow = row;
            if (activeRow) {
                activeRow.classList.add('modal-row--active');
                activeRow.setAttribute('tabindex', '0');
                activeRow.focus({ preventScroll: true });
                activeRow.scrollIntoView({ block: 'nearest' });
            }
        };

        const moveActiveRow = (direction) => {
            const rows = getNavigateRows();
            if (!rows.length) return;
            const currentIndex = activeRow && rows.includes(activeRow) ? rows.indexOf(activeRow) : -1;
            let nextIndex = currentIndex + direction;
            if (currentIndex === -1) {
                nextIndex = direction > 0 ? 0 : rows.length - 1;
            }
            nextIndex = Math.max(0, Math.min(rows.length - 1, nextIndex));
            setActiveRow(rows[nextIndex]);
        };

        const selectActiveRow = () => {
            if (!activeRow) return;
            const rows = getNavigateRows();
            if (!rows.includes(activeRow)) return;
            if (config.onSelect) {
                config.onSelect(activeRow);
            }
            modal.classList.add('hidden');
        };

        let suppressModalSearchInput = false;

        const openModal = () => {
            const wasHidden = modal.classList.contains('hidden');
            if (wasHidden && typeof config.beforeOpen === 'function' && !config.beforeOpen()) {
                return;
            }
            if (!wasHidden) {
                if (modalSearch) modalSearch.focus();
                return;
            }
            modal.classList.remove('hidden');
            if (modalSearch) {
                suppressModalSearchInput = true;
                modalSearch.value = '';
                suppressModalSearchInput = false;
                if (typeof config.onSearch === 'function') {
                    config.onSearch('', { immediate: true });
                } else {
                    filterModalRows(modalTable, '');
                }
                activeRow = null;
                modalSearch.focus();
            }
        };
        modal.openModal = openModal;

        picker.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openModal();
        });
        if (!config.disableOpenOnClick) {
            input.addEventListener('click', openModal);
        }

        modal.addEventListener('click', (e) => {
            if (e.target.dataset.close === config.modalId || e.target.classList.contains('modal__close')) {
                modal.classList.add('hidden');
                if (config.focusOnClose) {
                    focusItemEntry();
                }
            }
        });

        if (modalSearch) {
            modalSearch.addEventListener('input', (e) => {
                if (suppressModalSearchInput) return;
                if (typeof config.onSearch === 'function') {
                    config.onSearch(e.target.value);
                    return;
                }
                filterModalRows(modalTable, e.target.value.toLowerCase());
                if (activeRow) {
                    activeRow.classList.remove('modal-row--active');
                    activeRow = null;
                }
            });
            modalSearch.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    moveActiveRow(1);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    moveActiveRow(-1);
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    moveActiveRow(1);
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    if (modalSearch.value && modalSearch.value.trim()) {
                        modalSearch.value = '';
                        if (typeof config.onSearch === 'function') {
                            config.onSearch('');
                        } else {
                            filterModalRows(modalTable, '');
                        }
                        if (activeRow) {
                            activeRow.classList.remove('modal-row--active');
                            activeRow = null;
                        }
                        modalSearch.focus();
                    } else {
                        modal.classList.add('hidden');
                        if (config.focusOnClose) {
                            focusItemEntry();
                        }
                    }
                }
            });
        }

        if (modalClear) {
            modalClear.addEventListener('click', () => {
                if (modalSearch) {
                    modalSearch.value = '';
                    if (typeof config.onSearch === 'function') {
                        config.onSearch('');
                    } else {
                        filterModalRows(modalTable, '');
                    }
                    modalSearch.focus();
                }
            });
        }

        modalTable.addEventListener('click', (e) => {
            const row = e.target.closest('tr');
            if (!row) return;
            if (!row.closest('tbody')) return;
            if (config.onSelect) {
                config.onSelect(row);
            }
            modal.classList.add('hidden');
            if (config.focusOnClose) {
                focusItemEntry();
            }
        });

        modalTable.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                moveActiveRow(1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                moveActiveRow(-1);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                selectActiveRow();
            }
        });

        if (clear) {
            clear.addEventListener('click', () => {
                config.onClear();
            });
        }
    };

    const filterModalRows = (table, searchTerm) => {
        const tokens = searchTerm
            .trim()
            .toLowerCase()
            .split(/\s+/)
            .filter(Boolean);
        const rows = Array.from(table.querySelectorAll('tbody tr'));
        rows.forEach((row) => {
            const rowText = row.textContent.toLowerCase();
            const matches = tokens.every(token => rowText.includes(token));
            row.style.display = matches ? '' : 'none';
        });
    };

    let _custPickTimer = null;
    let _custPickAbort = null;
    let _custPickerFullCache = [];
    let _custPickerEmptyCacheAt = 0;
    const CUST_PICKER_EMPTY_CACHE_MS = 120000;
    let _whPickTimer = null;
    let _whPickAbort = null;

    function _escapeHtmlAttrSr(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;');
    }

    function renderSalesCustomerPickerRowsSr(customers) {
        const tb = document.querySelector('#customerModalTable tbody');
        if (!tb) return;
        if (!customers || !customers.length) {
            tb.innerHTML = '<tr><td colspan="4">No customers found. Try another search.</td></tr>';
            return;
        }
        const html = customers.map((c) => {
            const code = c.code != null ? String(c.code) : '';
            const name = c.name != null ? String(c.name) : '';
            const phone = c.phone != null ? String(c.phone) : '';
            const addr = c.address != null ? String(c.address) : '';
            const catc = c.categorycode != null ? String(c.categorycode) : '';
            const catn = c.categoryname != null ? String(c.categoryname) : '';
            const bt = String(c.customer_billing_type || c.CUSTOMER_BILLING_TYPE || 'CASH').toUpperCase();
            const creditlimit = c.creditlimit != null ? String(c.creditlimit) : '0';
            const curcred = c.currentcredit != null ? String(c.currentcredit) : '0';
            const outcash = c.outstandingcash != null ? String(c.outstandingcash) : '0';
            const pts = c.totalpoints != null ? String(c.totalpoints) : '0';
            const billTd = bt === 'CREDIT' ? 'Credit' : 'Cash';
            return (
                `<tr data-code="${_escapeHtmlAttrSr(code)}" data-name="${_escapeHtmlAttrSr(name)}" data-phone="${_escapeHtmlAttrSr(phone)}"`
                + ` data-address="${_escapeHtmlAttrSr(addr)}" data-categorycode="${_escapeHtmlAttrSr(catc)}" data-categoryname="${_escapeHtmlAttrSr(catn)}"`
                + ` data-billing-type="${_escapeHtmlAttrSr(bt)}" data-creditlimit="${_escapeHtmlAttrSr(creditlimit)}"`
                + ` data-currentcredit="${_escapeHtmlAttrSr(curcred)}" data-outstandingcash="${_escapeHtmlAttrSr(outcash)}" data-totalpoints="${_escapeHtmlAttrSr(pts)}">`
                + `<td>${_escapeHtmlAttrSr(code)}</td><td>${_escapeHtmlAttrSr(name || '-')}</td><td>${_escapeHtmlAttrSr(phone || '-')}</td>`
                + `<td>${billTd}</td></tr>`
            );
        }).join('');
        tb.innerHTML = html;
    }

    function filterSalesCustomerPickerRowsSr(customers, term) {
        const q = String(term || '').trim().toLowerCase();
        if (!q) return customers || [];
        return (customers || []).filter((c) => {
            const code = String(c.code != null ? c.code : '').toLowerCase();
            const name = String(c.name != null ? c.name : '').toLowerCase();
            const phone = String(c.phone != null ? c.phone : '').toLowerCase();
            return code.indexOf(q) !== -1 || name.indexOf(q) !== -1 || phone.indexOf(q) !== -1;
        });
    }

    function scheduleSalesCustomerPickerSearchSr(term, opts) {
        clearTimeout(_custPickTimer);
        if (opts && opts.immediate) {
            loadSalesCustomerPickerSr(term, opts);
            return;
        }
        _custPickTimer = setTimeout(() => loadSalesCustomerPickerSr(term, opts), 280);
    }

    function loadSalesCustomerPickerSr(term, opts) {
        const tb = document.querySelector('#customerModalTable tbody');
        const urlBase = window.__SALES_CUSTOMERS_PICKER__;
        if (!tb || !urlBase) return;
        const q = String(term || '').trim();
        const emptyQ = !q;
        const limit = emptyQ ? 150 : 200;

        if (emptyQ && _custPickerFullCache.length && Date.now() - _custPickerEmptyCacheAt < CUST_PICKER_EMPTY_CACHE_MS) {
            renderSalesCustomerPickerRowsSr(_custPickerFullCache);
            return;
        }

        if (!emptyQ) {
            if (q.length < 2) {
                if (_custPickerFullCache.length) {
                    renderSalesCustomerPickerRowsSr(filterSalesCustomerPickerRowsSr(_custPickerFullCache, q));
                }
                return;
            }
            const localHits = filterSalesCustomerPickerRowsSr(_custPickerFullCache, q);
            if (localHits.length) {
                renderSalesCustomerPickerRowsSr(localHits);
                return;
            }
        }

        if (_custPickAbort) _custPickAbort.abort();
        _custPickAbort = new AbortController();
        const u = `${urlBase}?q=${encodeURIComponent(q)}&limit=${limit}`;
        if (!(opts && opts.silent)) {
            tb.innerHTML = '<tr><td colspan="4">Loading…</td></tr>';
        }
        fetch(u, { credentials: 'same-origin', signal: _custPickAbort.signal })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.success) throw new Error((data && data.error) || 'Load failed');
                const rows = data.customers || [];
                if (emptyQ) {
                    _custPickerFullCache = rows;
                    _custPickerEmptyCacheAt = Date.now();
                }
                renderSalesCustomerPickerRowsSr(rows);
            })
            .catch((err) => {
                if (err.name === 'AbortError') return;
                if (_custPickerFullCache.length) {
                    renderSalesCustomerPickerRowsSr(filterSalesCustomerPickerRowsSr(_custPickerFullCache, q));
                    return;
                }
                tb.innerHTML = `<tr><td colspan="4">${_escapeHtmlAttrSr(err.message || err)}</td></tr>`;
            });
    }

    setupModal({
        modalId: 'customerModal',
        inputId: 'customer_display',
        pickerId: 'customerPicker',
        clearId: 'customerClear',
        onSearch: (term, opts) => {
            scheduleSalesCustomerPickerSearchSr(term, opts);
        },
        onSelect: (row) => {
            const code = row.dataset.code || '';
            const name = row.dataset.name || '';
            setValue(customerDisplay, formatCustomerDisplay(code, name));
            setValue(customerCode, code);
            setValue(customerName, name);
            setValue(customerPhone, row.dataset.phone || '');
            setValue(customerAddress, row.dataset.address || '');
            const categoryLabel = row.dataset.categoryname || row.dataset.categorycode || '';
            setValue(customerCategory, categoryLabel);
            setValue(creditLimit, row.dataset.creditlimit || 0);
            setValue(totalPoints, row.dataset.totalpoints || 0);
            if (outstandingAmount) {
                outstandingAmount.dataset.outstandingCash = row.dataset.outstandingcash || 0;
                outstandingAmount.dataset.currentCredit = row.dataset.currentcredit || 0;
                outstandingAmount.dataset.customerBillingType = row.dataset.billingType || 'CASH';
            }
            updateOutstandingByBillType();
            showClear(customerClear, true);
            applyCustomerBillingType(row.dataset.billingType || 'CASH');
            saveDraft();
            if (priceModeDisplay) {
                priceModeDisplay.focus();
            } else {
                focusItemEntry();
            }
        },
        onClear: resetCustomer,
    });

    if (customerDisplay && customerPicker) {
        customerDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const customerModal = document.getElementById('customerModal');
                if (customerModal && typeof customerModal.openModal === 'function') {
                    customerModal.openModal();
                }
            }
        });
    }

    if (deliveryDate) {
        deliveryDate.addEventListener('keydown', (e) => {
            handleEnterMove(e, null, () => {
                setActiveTab('items');
                focusItemEntry();
            });
        });
        deliveryDate.addEventListener('change', saveDraft);
    }

    if (remarks) {
        remarks.addEventListener('input', saveDraft);
    }
    if (orderNoEl) {
        orderNoEl.addEventListener('input', saveDraft);
    }

    setupModal({
        modalId: 'priceModeModal',
        inputId: 'price_mode_display',
        pickerId: 'priceModePicker',
        clearId: 'priceModeClear',
        onSelect: (row) => {
            setValue(priceMode, row.dataset.code || '');
            setValue(priceModeDisplay, row.dataset.name || '');
            showClear(priceModeClear, true);
            updateRateFromMode();
            updatePricingByUom();
            saveDraft();
        },
        onClear: () => {
            setValue(priceMode, '');
            setValue(priceModeDisplay, '');
            showClear(priceModeClear, false);
            updateRateFromMode();
            saveDraft();
        },
    });

    function renderSalesWarehousePickerRows(warehouses) {
        const tb = document.querySelector('#warehouseModalTable tbody');
        if (!tb) return;
        if (!warehouses || !warehouses.length) {
            tb.innerHTML = '<tr><td colspan="2">No warehouses found. Try another search.</td></tr>';
            return;
        }
        const html = warehouses.map((w) => {
            const id = w.code != null ? String(w.code) : '';
            const whCode = w.warehouse_code != null ? String(w.warehouse_code) : id;
            const name = w.name != null ? String(w.name) : '';
            return (
                `<tr data-id="${_escapeHtmlAttrSr(id)}" data-code="${_escapeHtmlAttrSr(whCode)}" data-name="${_escapeHtmlAttrSr(name)}">`
                + `<td>${_escapeHtmlAttrSr(whCode)}</td><td>${_escapeHtmlAttrSr(name || '-')}</td></tr>`
            );
        }).join('');
        tb.innerHTML = html;
    }

    function scheduleSalesWarehousePickerSearch(term) {
        clearTimeout(_whPickTimer);
        _whPickTimer = setTimeout(() => loadSalesWarehousePicker(term), 280);
    }

    function loadSalesWarehousePicker(term) {
        const tb = document.querySelector('#warehouseModalTable tbody');
        const urlBase = (window.__SALES_WAREHOUSES_PICKER__ || salesWarehouseCfg.apiUrl || '/sales/warehouses-picker').trim();
        if (!tb || !urlBase || !warehouseEnabled) return;
        if (_whPickAbort) _whPickAbort.abort();
        _whPickAbort = new AbortController();
        const docKind = (salesWarehouseCfg.docKind || 'sales_return').trim();
        const u = `${urlBase}?q=${encodeURIComponent(term || '')}&limit=300&doc_kind=${encodeURIComponent(docKind)}`;
        tb.innerHTML = '<tr><td colspan="2">Loading…</td></tr>';
        fetch(u, { credentials: 'same-origin', signal: _whPickAbort.signal })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.success) throw new Error((data && data.error) || 'Load failed');
                renderSalesWarehousePickerRows(data.warehouses || []);
            })
            .catch((err) => {
                if (err.name === 'AbortError') return;
                tb.innerHTML = `<tr><td colspan="2">${_escapeHtmlAttrSr(err.message || err)}</td></tr>`;
            });
    }

    if (warehouseEnabled && warehouseDisplay && warehousePicker) {
        setupModal({
            modalId: 'warehouseModal',
            inputId: 'warehouseDisplay',
            pickerId: 'warehousePicker',
            clearId: 'warehouseClear',
            onSearch: (term, opts) => {
                if (opts && opts.immediate) {
                    clearTimeout(_whPickTimer);
                    loadSalesWarehousePicker(term);
                } else {
                    scheduleSalesWarehousePickerSearch(term);
                }
            },
            onSelect: (row) => {
                const id = row.dataset.id || '';
                const whCode = row.dataset.code || '';
                const whName = row.dataset.name || '';
                setValue(warehouseDisplay, formatWarehouseDisplay(whCode, whName));
                setValue(warehouseIdEl, id);
                setValue(warehouseCodeEl, whCode);
                setValue(warehouseNameEl, whName);
                showClear(warehouseClear, true);
                applyHeaderWarehouseToLineStore();
                saveDraft();
                setActiveTab('items');
                focusItemEntry();
            },
            onClear: resetWarehouse,
        });

        warehouseDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const whModal = document.getElementById('warehouseModal');
                if (whModal && typeof whModal.openModal === 'function') {
                    whModal.openModal();
                }
            } else if (e.key === 'Enter') {
                if (!(parseInt(warehouseIdEl?.value, 10) || 0)) {
                    e.preventDefault();
                    alert('Select warehouse.');
                    const whModal = document.getElementById('warehouseModal');
                    if (whModal && typeof whModal.openModal === 'function') whModal.openModal();
                    return;
                }
                handleEnterMove(e, null, () => {
                    setActiveTab('items');
                    focusItemEntry();
                });
            }
        });
    }

    if (typeof initSiItemPicker === 'function') {
        siItemPickerCtl = initSiItemPicker({
            modalEl: itemModal,
            searchEl: itemSearch,
            bodyEl: itemBody,
            getFilterKey: () => currentItemFilter,
            beforeOpen: () => {
                if (!customerCode?.value) {
                    alert('Add customer first.');
                    focusCustomerField();
                    return false;
                }
                if (!siRequireHeaderWarehouse()) return false;
                return true;
            },
            fetchItems: fetchItemPopupPickerRows,
            onSelect: (row) => {
                if (siInlineModalRow) {
                    siApplyPopupItemToDataRow(siInlineModalRow, row);
                    siInlineModalRow = null;
                    return;
                }
                setItemFromRow(row);
                if (uomDisplay) uomDisplay.focus();
            },
            onClose: () => {
                siInlineModalRow = null;
            },
        });
    }

    if (itemCodeDisplay && itemPicker) {
        itemCodeDisplay.addEventListener('keydown', async (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const itemModal = document.getElementById('itemModal');
                if (itemModal && typeof itemModal.openModal === 'function') itemModal.openModal();
                return;
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                if (!customerCode?.value) {
                    alert('Add customer.');
                    focusCustomerField();
                    return;
                }
                if (warehouseEnabled && !(parseInt(warehouseIdEl?.value, 10) || 0)) {
                    alert('Select warehouse.');
                    if (warehouseDisplay) warehouseDisplay.focus();
                    return;
                }
                const code = (itemCodeDisplay.value || '').trim();
                if (!code) {
                    alert('Add item.');
                    itemCodeDisplay.focus();
                    return;
                }
                const ok = await fetchItemByBarcode(code, {
                    showNotFoundAlert: false,
                    focusOnSuccess: false,
                });
                if (!ok) {
                    alert('Add item.');
                    itemCodeDisplay.focus();
                    return;
                }
                if (uomDisplay) {
                    uomDisplay.focus();
                } else if (quantity) {
                    quantity.focus();
                }
            }
        });
    }

    setupModal({
        modalId: 'uomModal',
        inputId: 'uom_display',
        pickerId: 'uomPicker',
        clearId: 'uomClear',
        disableOpenOnClick: false,
        beforeOpen: () => {
            if (siInlineUomRow) {
                const code = siGetItemCodeFromRow(siInlineUomRow);
                if (!code) {
                    alert('Select an item first.');
                    siInlineUomRow = null;
                    return false;
                }
                fetchItemUoms(code);
                return true;
            }
            if (!itemCodeHidden.value) {
                alert('Select an item first.');
                return false;
            }
            fetchItemUoms(itemCodeHidden.value);
            return true;
        },
        onSelect: (row) => {
            if (siInlineUomRow) {
                siApplyUomToDataRow(siInlineUomRow, row.dataset.code);
                siInlineUomRow = null;
                return;
            }
            applyUomSelection(row.dataset.code);
            if (uomDisplay) {
                setTimeout(() => {
                    uomDisplay.focus();
                    uomDisplay.select?.();
                }, 0);
            }
        },
        onClear: () => {
            setValue(uomDisplay, '');
            setValue(uomCode, '');
            showClear(uomClear, false);
            currentItem.factor = 1;
            updateRateFromMode();
        },
    });

    const uomModalEl = document.getElementById('uomModal');
    if (uomModalEl) {
        uomModalEl.addEventListener('click', (e) => {
            if (e.target.dataset.close === 'uomModal' || e.target.classList.contains('modal__close')) {
                siInlineUomRow = null;
            }
        });
    }

    setupModal({
        modalId: 'inventoryModal',
        inputId: warehouseEnabled ? 'line_warehouse_display' : 'inventory_location',
        pickerId: warehouseEnabled ? 'lineWarehousePicker' : 'inventoryPicker',
        clearId: warehouseEnabled ? 'lineWarehouseClear' : 'inventoryClear',
        disableOpenOnClick: !warehouseEnabled,
        beforeOpen: () => {
            if (!itemCodeHidden.value) {
                alert('Select an item first.');
                return false;
            }
            loadInventoryModalRows(itemCodeHidden.value);
            return true;
        },
        onSelect: (row) => {
            if (warehouseEnabled) {
                applyLineWarehouseSelection(row.dataset.id, row.dataset.code, row.dataset.name);
            } else {
                applyInventorySelection(row.dataset.store);
            }
            if (binEnabled && lineBinDisplay) {
                lineBinDisplay.focus();
            } else if (discount) {
                discount.focus();
            }
        },
        onClear: () => {
            if (warehouseEnabled) {
                clearLineWarehouse();
            } else {
                setValue(inventoryLocation, '');
                showClear(inventoryClear, false);
            }
        },
    });

    if (binEnabled && lineBinDisplay && lineBinPicker) {
        setupModal({
            modalId: 'binModal',
            inputId: 'line_bin_display',
            pickerId: 'lineBinPicker',
            clearId: 'lineBinClear',
            beforeOpen: () => {
                const whId = parseInt(lineWarehouseId?.value, 10) || 0;
                if (!whId) {
                    alert('Select warehouse first.');
                    if (lineWarehouseDisplay) lineWarehouseDisplay.focus();
                    return false;
                }
                loadBinModalRows();
                return true;
            },
            onSelect: (row) => {
                applyLineBinSelection(row.dataset.id, row.dataset.code, row.dataset.name);
                if (discount) discount.focus();
            },
            onClear: () => {
                clearLineBin();
            },
        });
    }

    if (uomDisplay && uomPicker) {
        uomDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const uomModal = document.getElementById('uomModal');
                if (uomModal && typeof uomModal.openModal === 'function') uomModal.openModal();
                return;
            }
            if (e.key === 'Enter' || e.key === 'Tab' || e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Home' || e.key === 'End') {
                if (e.key === 'Enter') handleEnterMove(e, rate);
                return;
            }
            if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
            }
        });
    }

    if (itemModalFilters) {
        itemModalFilters.addEventListener('change', (e) => {
            const target = e.target;
            if (!target || target.name !== 'item_filter') return;
            currentItemFilter = target.value || 'all';
            if (siItemPickerCtl && typeof siItemPickerCtl.refresh === 'function') {
                siItemPickerCtl.refresh(itemSearch ? itemSearch.value : '');
            }
            if (itemSearch) itemSearch.focus();
        });
    }

    if (barcodeInput) {
        barcodeInput.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const itemModal = document.getElementById('itemModal');
                if (itemModal && typeof itemModal.openModal === 'function') itemModal.openModal();
                return;
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                const hasItemCode = (itemCodeHidden?.value || itemCodeDisplay?.value || '').trim();
                if (hasItemCode) {
                    if (uomDisplay) {
                        uomDisplay.focus();
                    } else if (uomPicker) {
                        const uomModal = document.getElementById('uomModal');
                        if (uomModal && typeof uomModal.openModal === 'function') uomModal.openModal();
                    }
                    return;
                }
                const barcode = barcodeInput.value.trim();
                if (barcode) {
                    fetchItemByBarcode(barcode);
                }
            }
        });
    }

    if (quantity) {
        quantity.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                let qtyVal = Number(quantity?.value || 0);
                if (!qtyVal) {
                    quantity.value = '1';
                    if (typeof updateLineAmount === 'function') updateLineAmount();
                    qtyVal = 1;
                }
                const nextAfterQty = warehouseEnabled
                    ? lineWarehouseDisplay
                    : (inventoryLocation || discount);
                handleEnterMove(e, nextAfterQty);
            }
        });
        quantity.addEventListener('input', updateLineAmount);
    }
    if (lineWarehouseDisplay && warehouseEnabled) {
        lineWarehouseDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const inventoryModal = document.getElementById('inventoryModal');
                if (inventoryModal && typeof inventoryModal.openModal === 'function') inventoryModal.openModal();
                return;
            }
            if (e.key === 'Enter') {
                const nextAfterWh = binEnabled
                    ? lineBinDisplay
                    : (batchEnabled && salesLotDisplay ? salesLotDisplay : discount);
                handleEnterMove(e, nextAfterWh);
            }
        });
    }
    if (lineBinDisplay && binEnabled) {
        lineBinDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const binModal = document.getElementById('binModal');
                if (binModal && typeof binModal.openModal === 'function') binModal.openModal();
                return;
            }
            if (e.key === 'Enter') {
                const nextAfterBin = batchEnabled && salesLotDisplay ? salesLotDisplay : discount;
                handleEnterMove(e, nextAfterBin);
            }
        });
    }
    if (inventoryLocation && !warehouseEnabled) {
        inventoryLocation.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                const inventoryModal = document.getElementById('inventoryModal');
                if (inventoryModal && typeof inventoryModal.openModal === 'function') inventoryModal.openModal();
                return;
            }
            if (e.key === 'Enter') {
                const nextAfterStore = batchEnabled && salesLotDisplay ? salesLotDisplay : discount;
                handleEnterMove(e, nextAfterStore);
            }
        });
    }
    if (batchEnabled && salesLotDisplay) {
        salesLotDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                handleEnterMove(e, discount);
            }
        });
    }
    if (rate) {
        rate.addEventListener('keydown', (e) => handleEnterMove(e, quantity));
        rate.addEventListener('input', updateLineAmount);
        rate.addEventListener('blur', () => {
            const n = Number(rate.value || 0);
            if (n < 0) {
                setValue(rate, formatRate(0));
            } else {
                setValue(rate, formatRate(n));
            }
            updateLineAmount();
        });
    }
    if (discount) {
        discount.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const nextAfterDisc = lineAmount || btnAddLine;
                handleEnterMove(e, nextAfterDisc);
                return;
            }
        });
        discount.addEventListener('input', updateLineAmount);
    }
    if (lineAmount) {
        lineAmount.addEventListener('focus', () => { siEntryAmountEditing = true; });
        lineAmount.addEventListener('blur', () => {
            siEntryAmountEditing = false;
            if (isEntryAmountBlank(lineAmount.value)) {
                setValue(lineAmount, '');
                return;
            }
            const parsed = parseEntryAmount(lineAmount.value);
            const signed = isSalesReturn ? -Math.abs(parsed) : parsed;
            setValue(lineAmount, formatNumber(signed));
            updateRateFromAmount();
        });
        lineAmount.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                updateRateFromAmount();
                handleEnterMove(e, btnAddLine);
                return;
            }
        });
        lineAmount.addEventListener('input', updateRateFromAmount);
    }

    if (additionalDiscount) {
        additionalDiscount.addEventListener('input', () => {
            syncAdditionalDiscount(additionalDiscount.value);
            updateTotals();
            saveDraft();
        });
    }
    if (additionalDiscountItems) {
        additionalDiscountItems.addEventListener('input', () => {
            syncAdditionalDiscount(additionalDiscountItems.value);
            updateTotals();
            saveDraft();
        });
    }

    priceMode.addEventListener('change', () => {
        updatePricingByUom();
    });

    if (btnAddLine) {
        btnAddLine.addEventListener('click', addLine);
        btnAddLine.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addLine();
            }
        });
    }
    if (btnClearLine) {
        btnClearLine.addEventListener('click', () => {
            resetItemLine();
            setTimeout(() => focusItemEntry(), 0);
        });
    }
    btnSave.addEventListener('click', saveInvoice);
    btnNew.addEventListener('click', () => { void resetForm({ reserveBillNo: true }); });
    if (btnDiscard) btnDiscard.addEventListener('click', () => { void resetForm({ reserveBillNo: true }); });
    syncRefDisplay();
    syncCustomerDetailsModal();

    if (btnCustomerDetails && customerDetailsModal) {
        btnCustomerDetails.addEventListener('click', () => {
            syncCustomerDetailsModal();
            customerDetailsModal.classList.remove('hidden');
        });
        customerDetailsModal.addEventListener('click', (e) => {
            if (e.target.dataset.close === 'customerDetailsModal' || e.target.classList.contains('modal__close')) {
                customerDetailsModal.classList.add('hidden');
            }
        });
    }

    [itemCodeDisplay, itemName, uomDisplay, rate, quantity, inventoryLocation, discount]
        .filter(Boolean)
        .forEach((field) => {
            field.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && e.ctrlKey) {
                    e.preventDefault();
                    addLine();
                    return;
                }
                if (e.key === 'Escape' && editingRow) {
                    e.preventDefault();
                    resetItemLine();
                    focusItemEntry();
                }
            });
        });

    wireSiHeaderEscNavigation();
    wireSiEntryEscNavigation();

    if (btnHistory && historyModal) {
        btnHistory.addEventListener('click', () => {
            historyModal.classList.remove('hidden');
            const selected = historyModal.querySelector('input[name="history_filter"]:checked');
            const type = selected ? selected.value : 'customer_item';
            fetchHistoryRows(type);
        });
    }
    if (historyModal) {
        historyModal.addEventListener('click', (e) => {
            if (e.target.dataset.close === 'historyModal' || e.target.classList.contains('modal__close')) {
                historyModal.classList.add('hidden');
            }
        });
        const radios = historyModal.querySelectorAll('input[name="history_filter"]');
        radios.forEach((radio) => {
            radio.addEventListener('change', () => {
                fetchHistoryRows(radio.value);
            });
        });
    }

    const removeDataRow = (row) => {
        if (!row) return;
        const wasEditing = editingRow === row;
        // Remove the row first so a failure in later cleanup can never leave the line undeletable.
        row.remove();
        try {
            if (wasEditing) resetItemLine();
        } catch (err) {
            console.error('resetItemLine after remove failed', err);
            editingRow = null;
        }
        try {
            const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
            rows.forEach((r, idx) => {
                r.dataset.line = String(idx + 1);
                if (r.children[0]) r.children[0].textContent = String(idx + 1);
            });
            if (!rows.length) {
                clearTable();
            } else {
                updateTotals();
            }
            pinEntryRowToBottom();
            saveDraft();
        } catch (err) {
            console.error('post-remove refresh failed', err);
        }
    };

    tableBody.addEventListener('click', (e) => {
        // Handle the remove (×) button FIRST so nothing else in this listener can
        // intercept or short-circuit the click before the line gets deleted.
        const removeBtn = e.target.closest('.btn-remove');
        if (removeBtn) {
            e.preventDefault();
            const row = removeBtn.closest('tr[data-line]');
            if (row) removeDataRow(row);
            return;
        }
        const td = e.target.closest('td');
        if (td) {
            const entryTr = td.closest('tr.line-entry');
            if (entryTr && td.classList.contains('si-col-uom') && !e.target.closest('#uom_display')) {
                const uomModal = document.getElementById('uomModal');
                if (uomModal && typeof uomModal.openModal === 'function') uomModal.openModal();
                return;
            }
            if (entryTr && td.classList.contains('si-col-amount') && lineAmount && !e.target.closest('#btnAddLine')) {
                lineAmount.focus();
                try { lineAmount.select(); } catch (ignore) {}
                return;
            }
            const inlineTr = td.closest('tr[data-line]');
            if (inlineTr && !inlineTr.classList.contains('line-entry')
                && !td.querySelector('input, select, button')) {
                const key = siInlineColKey(td);
                if (key === 'si-col-uom') {
                    siOpenUomModalForDataRow(inlineTr);
                    return;
                }
                if (key) {
                    siBeginInlineEdit(td, inlineTr, key);
                    return;
                }
            }
        }
    });

    const lotPickModal = document.getElementById('lotPickModal');
    const lotPickModalBody = document.getElementById('lotPickModalBody');
    const lotPickHint = document.getElementById('lotPickHint');

    const openLotPicker = async () => {
        const ic = (itemCodeHidden && itemCodeHidden.value) ? String(itemCodeHidden.value).trim() : '';
        if (!ic) {
            alert('Select an item first.');
            return;
        }
        if (!lotPickModal || !lotPickModalBody) return;
        if (lotPickHint) lotPickHint.textContent = 'Loading lots…';
        lotPickModalBody.innerHTML = '<tr><td colspan="4" style="padding:12px;">Loading…</td></tr>';
        lotPickModal.classList.remove('hidden');
        try {
            const res = await fetch(`${saveBase}/api/batch-lots-for-line?item_code=${encodeURIComponent(ic)}`);
            const data = await res.json();
            const lots = data && data.success && Array.isArray(data.lots) ? data.lots : [];
            if (!lots.length) {
                lotPickModalBody.innerHTML = '<tr><td colspan="4" style="padding:12px;">No available lots with stock.</td></tr>';
                if (lotPickHint) {
                    lotPickHint.textContent = 'No pickable lots (QC-blocked excluded). Use Auto (FEFO) or receipt stock first.';
                }
                return;
            }
            if (lotPickHint) lotPickHint.textContent = 'QC-held lots are not listed. Clear lot for Auto (FEFO).';
            lotPickModalBody.innerHTML = lots.map((lot) => {
                const lid = lot.lot_id != null ? String(lot.lot_id) : '';
                const bn = lot.batch_no != null ? String(lot.batch_no) : '';
                const q = Number(lot.qty || 0);
                let exp = lot.expiry_date;
                exp = exp != null ? String(exp).slice(0, 10) : '—';
                const batchAttr = bn.replace(/\\/g, '').replace(/\"/g, '&quot;');
                return `<tr role="button" tabindex="0" class="lot-pick-row" data-lot-id="${lid}" data-batch="${batchAttr}" style="cursor:pointer;">
                  <td>${lid}</td>
                  <td>${bn || '—'}</td>
                  <td>${exp}</td>
                  <td style="text-align:right;">${q.toFixed(3)}</td>
                </tr>`;
            }).join('');
        } catch (err) {
            lotPickModalBody.innerHTML = '<tr><td colspan="4" style="padding:12px;">Could not load lots.</td></tr>';
            if (lotPickHint) lotPickHint.textContent = '';
        }
    };

    if (btnPickLot) {
        btnPickLot.addEventListener('click', () => { openLotPicker(); });
    }
    if (btnClearLot) {
        btnClearLot.addEventListener('click', () => { clearSalesLotPick(); });
    }
    if (lotPickModal) {
        lotPickModal.addEventListener('click', (e) => {
            if (e.target.dataset.close === 'lotPickModal' || e.target.classList.contains('modal__close')) {
                lotPickModal.classList.add('hidden');
            }
            const pr = e.target.closest('.lot-pick-row');
            if (pr && lotPickModalBody && lotPickModalBody.contains(pr)) {
                const lid = pr.dataset.lotId || '';
                const bn = pr.dataset.batch || '';
                if (salesLotId) salesLotId.value = lid;
                if (salesLotDisplay) {
                    salesLotDisplay.value = lid
                        ? (bn ? `${bn} (#${lid})` : `#${lid}`)
                        : '';
                }
                lotPickModal.classList.add('hidden');
            }
        });
    }

    window.SalesInvoiceAi = {
        formatNumber,
        async addLineFromItem(item, qtyRaw) {
            if (!item || item.itemcode == null) return false;
            if (!ensureHeaderSelections()) return false;

            const qty = Math.max(0.0001, Math.abs(Number(qtyRaw) || 1));
            const itemCode = String(item.itemcode).trim();
            const query = String(item.manufacturerid || item.manufacturer_id || itemCode).trim();
            if (!itemCode) return false;

            let itemName = String(item.itemname || '').trim();
            let baseUom = String(item.baseuom || '').trim();
            let cost = Number(item.costprice || 0);
            if (!itemName || !baseUom) {
                try {
                    const res = await fetch(`${apiBase}/item-info?query=${encodeURIComponent(query)}`);
                    const data = await res.json();
                    if (!data.success) return false;
                    const it = data.item || {};
                    itemName = itemName || salesItemDisplayName(it);
                    baseUom = baseUom || it.baseuom || 'PCS';
                    cost = cost || Number(it.costprice || 0);
                } catch (e) {
                    console.error('AI item lookup failed', e);
                    return false;
                }
            }

            let uom = String(item.barcode_uom || '').trim() || baseUom || 'PCS';
            let rate = 0;
            let factor = 1;
            if (item.barcode_uom != null && item.barcode_retail_price != null) {
                rate = Number(item.barcode_retail_price) || 0;
            } else {
                const pricing = await getLineUomPricing(itemCode, uom);
                if (pricing) {
                    rate = Number(pricing.rate || 0);
                    factor = Number(pricing.conversion_factor || 1) || 1;
                } else {
                    rate = Number(item.retailprice || 0);
                }
            }

            const whFields = await resolveWarehouseFieldsForItem(itemCode);
            if (warehouseEnabled && !(parseInt(whFields.warehouseId, 10) > 0)) {
                return false;
            }

            const binFields = await resolveBinFieldsForItem(itemCode, whFields.warehouseId);
            if (binEnabled && !(parseInt(binFields.storageId, 10) > 0)) {
                return false;
            }

            const store = warehouseEnabled
                ? (whFields.warehouseCode || whFields.store || '')
                : (whFields.store || '');

            const ok = appendOrMergeLine({
                itemCode,
                barcode: item.barcode || item.manufacturerid || '',
                itemName,
                uom,
                qty,
                rate,
                discount: 0,
                cost,
                factor,
                store,
                warehouseId: whFields.warehouseId,
                warehouseCode: whFields.warehouseCode,
                warehouseName: whFields.warehouseName,
                storageId: binFields.storageId,
                binCode: binFields.binCode,
                binName: binFields.binName,
                lotId: '',
                lotLabel: '',
            }, {
                mergeSilently: true,
                skipConfirmZeroNet: true,
            });

            if (ok) {
                updateTotals();
                saveDraft();
                scrollTableToBottom();
            }
            return ok;
        },
    };
});
