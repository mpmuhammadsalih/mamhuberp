document.addEventListener('DOMContentLoaded', async () => {
    /** Sales screens show ITEMNAME (English); display_item_name prefers Arabic for POS/popups. */
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
    // Minus billing (LOCATIONMASTER.MINUSBILLING) — when on, allow committing lines
    // even if the store lacks enough stock (on-hand may go negative).
    const minusBillingEnabled = String(form?.dataset.minusBilling || '0').trim() === '1';
    const openBillDate = String(window.__SALES_OPEN_BILL_DATE__ || '').trim();
    const openBillDateFrom = String(window.__SALES_OPEN_BILL_DATE_FROM__ || openBillDate || '').trim();
    const openBillDateTo = String(window.__SALES_OPEN_BILL_DATE_TO__ || openBillDateFrom || openBillDate || '').trim();
    const txnDateBlocked = Boolean(window.__SALES_TXN_DATE_BLOCKED__);
    const txnDateError = String(window.__SALES_TXN_DATE_ERROR__ || '').trim();
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
    const orderNoEl = document.getElementById('order_no');
    const focusOrderNoField = () => {
        if (orderNoEl) {
            orderNoEl.focus();
            try { orderNoEl.select(); } catch (ignore) {}
        }
    };
    const focusWarehouseField = () => {
        if (warehouseEnabled && warehouseDisplay) {
            siFocusHeaderField(warehouseDisplay);
        }
    };
    const focusBarcodeEntry = () => {
        setActiveTab('items');
        focusItemEntry();
    };
    const loyaltyCustomerDisplay = document.getElementById('loyalty_customer_display');
    const loyaltyCustomerCode = document.getElementById('loyalty_customer_code');
    const loyaltyCustomerClear = document.getElementById('loyaltyCustomerClear');
    const loyaltyCustomerPicker = document.getElementById('loyaltyCustomerPicker');

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
    const btnPrintOrderPdf = document.getElementById('btnPrintOrderPdf');
    const btnCancelOrder = document.getElementById('btnCancelOrder');
    const btnConvertToInvoice = document.getElementById('btnConvertToInvoice');
    const sourceOrderBillnoEl = document.getElementById('source_order_billno');
    const sourceOrderBillnosEl = document.getElementById('source_order_billnos');
    const soCancelledBanner = document.getElementById('soCancelledBanner');
    const isSalesOrderScreen = saveBase === '/sales-order';
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
                if (isSalesOrderScreen) {
                    orderNoMandatory = Boolean(data.order_no_mandatory_order);
                } else {
                    orderNoMandatory = Boolean(data.order_no_mandatory_invoice);
                }
                if (form) form.dataset.orderNoMandatory = orderNoMandatory ? '1' : '0';
                syncOrderNoMandatoryUi();
            }
        } catch (ignore) {}
    };
    await refreshOrderNoMandatorySetting();
    const convertFromOrders = Array.isArray(window.__CONVERT_FROM_ORDERS__) ? window.__CONVERT_FROM_ORDERS__ : [];
    let orderBillStatus = '';
    let salesOrderEditMode = false;

    const parseSourceOrderBillnos = (header) => {
        const fromHeader = header && Array.isArray(header.source_order_billnos)
            ? header.source_order_billnos
            : null;
        const rawList = fromHeader
            || (header && header.source_order_billnos != null && header.source_order_billnos !== ''
                ? String(header.source_order_billnos).split(',')
                : null)
            || (header && header.source_order_billno != null && header.source_order_billno !== ''
                ? [header.source_order_billno]
                : null)
            || convertFromOrders
            || [];
        return rawList
            .map((v) => String(v || '').trim())
            .filter((v) => v.length > 0);
    };

    const customerDetailsModal = document.getElementById('customerDetailsModal');
    const customerDetailsPhone = document.getElementById('customerDetailsPhone');
    const customerDetailsBillType = document.getElementById('customerDetailsBillType');
    const customerDetailsCreditLimit = document.getElementById('customerDetailsCreditLimit');
    const customerDetailsCategory = document.getElementById('customerDetailsCategory');
    const customerDetailsOutstanding = document.getElementById('customerDetailsOutstanding');
    const customerDetailsTotalPoints = document.getElementById('customerDetailsTotalPoints');
    const customerDetailsAddress = document.getElementById('customerDetailsAddress');

    const tableBody = document.getElementById('salesTableBody');
    const siLineStatus = document.getElementById('siLineStatus');
    const getEntryRow = () => (tableBody ? tableBody.querySelector('tr.line-entry') : null);
    const SI_NO_STOCK_ALERT = 'No stock';

    // "No stock" is a soft warning: it must not block selecting/adding an item.
    // Only genuine validation errors (missing warehouse, item not found, load failure) block.
    const siStockCheckBlocks = (stockCheck) => {
        if (stockCheck?.ok) return false;
        return String(stockCheck?.message || SI_NO_STOCK_ALERT) !== SI_NO_STOCK_ALERT;
    };

    const siShowLineStatus = (msg, isError = false) => {
        const text = String(msg || '').trim();
        if (siLineStatus) {
            siLineStatus.textContent = text;
            siLineStatus.classList.toggle('si-line-status--error', !!isError && !!text);
            siLineStatus.classList.toggle('si-line-status--hidden', !text);
        }
    };

    const siShowLineMessage = (msg, isError = false) => {
        const text = String(msg || '').trim();
        siShowLineStatus(text, isError);
        if (isError && text) {
            try { alert(text); } catch (ignore) {}
        }
    };

    const siFocusQuantityField = (row) => {
        const tr = row && row.matches?.('tr[data-line]') ? row : null;
        const inlineQty = tr?.querySelector('.si-col-qty input');
        if (inlineQty) {
            inlineQty.focus();
            try { inlineQty.select(); } catch (ignore) {}
            return;
        }
        if (tr) {
            const qtyTd = tr.querySelector('.si-col-qty');
            if (qtyTd && typeof siBeginInlineEdit === 'function') {
                siBeginInlineEdit(qtyTd, tr, 'si-col-qty');
                return;
            }
        }
        if (!quantity || typeof quantity.focus !== 'function') return;
        quantity.focus();
        try { quantity.select(); } catch (ignore) {}
    };

    if (form) {
        form.addEventListener('click', (e) => {
            if (!e.target.closest('#btnAddLine')) return;
            e.preventDefault();
            e.stopPropagation();
            const fn = window.__siTriggerAddLine;
            if (typeof fn === 'function') {
                fn();
            } else {
                siShowLineMessage('Sales form is still loading. Wait a moment and try again.', true);
            }
        }, true);
    }
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
    const initialOrderPayloadSeed = window.__INITIAL_ORDER__ || null;
    const loadFromOrderApiBase = String(window.__LOAD_FROM_ORDER_API__ || '/sales/load-from-order/').trim();

    const fetchOrderForInvoice = async (billnoRaw) => {
        const token = String(billnoRaw || '').trim();
        if (!token) return null;
        const url = `${loadFromOrderApiBase}${encodeURIComponent(token)}`;
        try {
            const res = await fetch(url, { credentials: 'same-origin' });
            const data = await res.json();
            if (data && data.success && data.order) return data.order;
        } catch (e) {
            console.error('fetchOrderForInvoice failed', e);
        }
        return null;
    };

    const fetchSalesOrderForEdit = async (billnoRaw) => {
        const token = String(billnoRaw || '').trim();
        if (!token) return null;
        try {
            const res = await fetch(`/sales-order/load/${encodeURIComponent(token)}`, { credentials: 'same-origin' });
            const data = await res.json();
            if (data && data.success && data.order) return data.order;
        } catch (e) {
            console.error('fetchSalesOrderForEdit failed', e);
        }
        return null;
    };

    const resolveInitialOrderPayload = async () => {
        let payload = initialOrderPayloadSeed;
        if (payload && payload.header && Array.isArray(payload.lines)) return payload;
        const params = new URLSearchParams(window.location.search);
        if (isSalesOrderScreen) {
            const editBillno = (params.get('billno') || '').trim();
            if (editBillno) {
                return (await fetchSalesOrderForEdit(editBillno)) || payload;
            }
            return payload;
        }
        const raw = (params.get('from_orders') || params.get('from_order') || '').trim();
        if (!raw) return payload;
        const tokens = raw.replace(/;/g, ',').split(',').map((s) => s.trim()).filter(Boolean);
        if (!tokens.length) return payload;
        if (tokens.length === 1) {
            return (await fetchOrderForInvoice(tokens[0])) || payload;
        }
        return payload;
    };
    const SALES_PRINT_PDF_LS_KEY = 'sales_print_pdf_on_save';
    const SALES_INVOICE_TEMPLATE_KEY = 'nexa_sales_invoice_template';
    const siPrintPdfOnSave = document.getElementById('siPrintPdfOnSave');
    const siInvoiceTemplate = document.getElementById('siInvoiceTemplate');
    const SALES_INVOICE_TEMPLATE_PREFER_URL = '/sales/invoice-templates/prefer';

    function readSalesInvoiceTemplate() {
        try {
            const v = (localStorage.getItem(SALES_INVOICE_TEMPLATE_KEY) || 'classic').trim().toLowerCase();
            if (['classic', 'modern', 'compact', 'slate', 'gulfnova'].includes(v)) return v;
        } catch (e) { /* ignore */ }
        return 'classic';
    }

    function writeSalesInvoiceTemplate(v) {
        try { localStorage.setItem(SALES_INVOICE_TEMPLATE_KEY, v); } catch (e) { /* ignore */ }
    }

    function persistSalesInvoiceTemplate(v) {
        const id = (v || 'classic').trim().toLowerCase();
        writeSalesInvoiceTemplate(id);
        try {
            fetch(SALES_INVOICE_TEMPLATE_PREFER_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ template: id }),
            }).then((r) => r.json()).then((res) => {
                if (res && res.template) writeSalesInvoiceTemplate(res.template);
            }).catch(() => { /* keep local */ });
        } catch (e) { /* ignore */ }
    }

    function syncSalesInvoiceTemplateFromServer() {
        try {
            fetch(SALES_INVOICE_TEMPLATE_PREFER_URL, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
            }).then((r) => r.json()).then((res) => {
                if (!res || !res.success) return;
                const local = readSalesInvoiceTemplate();
                // First-time migrate: browser had a choice but company setting not saved yet.
                if (!res.saved && local && local !== 'classic') {
                    persistSalesInvoiceTemplate(local);
                    return;
                }
                if (!res.template) return;
                writeSalesInvoiceTemplate(res.template);
                if (siInvoiceTemplate) siInvoiceTemplate.value = res.template;
            }).catch(() => { /* ignore */ });
        } catch (e) { /* ignore */ }
    }

    function appendInvoiceTemplateParam(url) {
        const tmpl = readSalesInvoiceTemplate();
        if (!url) return url;
        try {
            const u = new URL(url, window.location.origin);
            u.searchParams.set('template', tmpl);
            if (!/^https?:\/\//i.test(url)) {
                return u.pathname + u.search + u.hash;
            }
            return u.toString();
        } catch (e) {
            const sep = url.includes('?') ? '&' : '?';
            return `${url}${sep}template=${encodeURIComponent(tmpl)}`;
        }
    }

    if (siInvoiceTemplate) {
        siInvoiceTemplate.value = readSalesInvoiceTemplate();
        siInvoiceTemplate.addEventListener('change', () => {
            persistSalesInvoiceTemplate(siInvoiceTemplate.value || 'classic');
        });
        syncSalesInvoiceTemplateFromServer();
    }

    function readSalesPrintPdfPref() {
        try {
            const v = localStorage.getItem(SALES_PRINT_PDF_LS_KEY);
            if (v === '0') return false;
            if (v === '1') return true;
        } catch (e) {
            /* ignore */
        }
        return true;
    }

    function isSalesPrintPdfOnSaveEnabled() {
        if (!enablePrint) return false;
        if (!siPrintPdfOnSave) return readSalesPrintPdfPref();
        return siPrintPdfOnSave.checked;
    }

    if (siPrintPdfOnSave) {
        siPrintPdfOnSave.checked = readSalesPrintPdfPref();
        siPrintPdfOnSave.addEventListener('change', () => {
            try {
                localStorage.setItem(SALES_PRINT_PDF_LS_KEY, siPrintPdfOnSave.checked ? '1' : '0');
            } catch (e) {
                /* ignore */
            }
        });
    }

    function openSavedInvoicePdf(billno, pdfUrlFromServer) {
        if (!isSalesPrintPdfOnSaveEnabled() || billno == null) return;
        let printUrl = (
            pdfUrlFromServer ||
            (saveBase === '/sales-order'
                ? `/sales-order/pdf/${encodeURIComponent(billno)}`
                : `/reports/crystal-reports/open/cashbilldup?billno=${encodeURIComponent(billno)}`)
        ).trim();
        if (!printUrl) return;
        printUrl = appendInvoiceTemplateParam(printUrl);
        try {
            window.open(printUrl, '_blank');
        } catch (e) {
            console.warn('[sales] PDF open failed:', e);
        }
    }

    function openOrderPdf(billno) {
        const bno = String(billno != null ? billno : (billNo?.value || '')).trim();
        if (!bno) {
            alert('Save the order first to print PDF.');
            return;
        }
        let printUrl = `${printBase}/pdf/${encodeURIComponent(bno)}`;
        printUrl = appendInvoiceTemplateParam(printUrl);
        try {
            window.open(printUrl, '_blank');
        } catch (e) {
            console.warn('[sales] order PDF open failed:', e);
        }
    }

    let promotionDiscount = 0;
    let appliedVouchers = [];
    let saveInFlight = false;
    const SAVE_REQUEST_TIMEOUT_MS = 120000;

    async function fetchSaveJson(url, payload) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), SAVE_REQUEST_TIMEOUT_MS);
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
            let data = {};
            try {
                data = await res.json();
            } catch (parseErr) {
                throw new Error(res.ok ? 'Invalid server response.' : `Save failed (${res.status}).`);
            }
            return { res, data };
        } catch (err) {
            if (err && err.name === 'AbortError') {
                throw new Error('Save timed out. The database may be busy — wait a moment and try again.');
            }
            throw err;
        } finally {
            clearTimeout(timer);
        }
    }

    function applySalesOrderActionState() {
        const bno = String(billNo?.value || '').trim();
        let saveDisabled = txnDateBlocked;
        let saveTitle = txnDateBlocked ? txnDateError : '';

        if (isSalesOrderScreen) {
            const status = String(orderBillStatus || '').trim().toUpperCase();
            const cancelled = status === 'V';
            const invoiced = status === 'I';
            const locked = cancelled || invoiced;
            if (locked) {
                saveDisabled = true;
                saveTitle = cancelled
                    ? 'Cancelled orders cannot be saved.'
                    : 'Invoiced orders cannot be changed.';
            } else if (txnDateBlocked) {
                saveDisabled = true;
                saveTitle = txnDateError || 'Setup date is missing. Open a From–To date range in Transaction Date Setup before posting.';
            }
            if (soCancelledBanner) {
                soCancelledBanner.style.display = cancelled ? '' : 'none';
                if (cancelled) {
                    soCancelledBanner.textContent = 'This sales order is cancelled. You can view or print it, but changes are not allowed.';
                } else if (invoiced) {
                    soCancelledBanner.style.display = '';
                    soCancelledBanner.textContent = 'This sales order is invoiced. You can view or print it, but changes are not allowed.';
                }
            }
            if (btnPrintOrderPdf) {
                btnPrintOrderPdf.style.display = bno ? '' : 'none';
            }
            if (btnCancelOrder) {
                btnCancelOrder.style.display = (salesOrderEditMode && bno && !locked) ? '' : 'none';
            }
            if (btnConvertToInvoice) {
                const showConvert = Boolean(salesOrderEditMode && bno && !locked);
                btnConvertToInvoice.style.display = showConvert ? '' : 'none';
                if (showConvert) {
                    btnConvertToInvoice.href = `/sales?from_order=${encodeURIComponent(bno)}`;
                }
            }
        }

        if (btnSave) {
            btnSave.disabled = saveDisabled || saveInFlight;
            btnSave.title = saveTitle;
        }
    }

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

    const siGetHeaderWarehouseContext = () => {
        const idRaw = String(warehouseIdEl?.value || '').trim();
        const code = String(warehouseCodeEl?.value || '').trim();
        const name = String(warehouseNameEl?.value || '').trim();
        const idNum = parseInt(idRaw, 10) || 0;
        return {
            id: idNum || idRaw,
            code,
            name,
        };
    };

    const siHeaderWarehouseSelected = () => {
        const wh = siGetHeaderWarehouseContext();
        return Boolean(parseInt(wh.id, 10) || wh.code);
    };

    const siPickWarehouseOption = (optionValue, headerValue) => {
        const opt = String(optionValue ?? '').trim();
        if (opt) return opt;
        return String(headerValue ?? '').trim();
    };

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
        const wh = siGetHeaderWarehouseContext();
        if (!parseInt(wh.id, 10) && !wh.code) return;
        applyLineWarehouseSelection(wh.id || wh.code, wh.code, wh.name);
    };

    const resolveLineWarehouseForItem = async (itemCode) => {
        if (!warehouseEnabled || !itemCode) {
            clearLineWarehouse();
            return;
        }
        const hdrId = parseInt(warehouseIdEl?.value, 10) || 0;
        const hdrCode = String(warehouseCodeEl?.value || '').trim();
        if (hdrId > 0 || hdrCode) {
            applyHeaderWarehouseToLineStore();
            return;
        }
        clearLineWarehouse();
        try {
            const data = await siFetchItemInventory(itemCode);
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
        if (siHeaderWarehouseSelected()) return true;
        siShowLineMessage('Please select warehouse before adding a line.', true);
        if (warehouseDisplay) warehouseDisplay.focus();
        else if (warehousePicker) warehousePicker.click();
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
            if (!customerCode.value || !priceMode.value) {
                if (!customerCode.value) {
                    focusCustomerField();
                } else if (!priceMode.value && priceModePicker) {
                    priceModePicker.click();
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
        applySalesOrderActionState();
    };

    const showClear = (btn, show) => {
        if (!btn) return;
        btn.style.display = show ? 'block' : 'none';
    };

    const SI_QTY_DECIMALS = 3;
    const SI_RATE_DECIMALS = 3;
    const SI_AMT_DECIMALS = isSalesOrderScreen ? 3 : 2;

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
        const cur = String(billDate.value || '').trim();
        if (cur && openBillDateFrom && cur < openBillDateFrom) setValue(billDate, openBillDate || openBillDateFrom);
        else if (cur && openBillDateTo && cur > openBillDateTo) setValue(billDate, openBillDate || openBillDateTo);
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

    /** Bill date from TBLTRANSACTIONDATE range (Transaction Date Setup). */
    const syncBillDateFromOpen = (opts) => {
        const keepExisting = !!(opts && opts.keepExisting);
        if (!billDate) return;
        applyBillDateRangeBounds();
        if (openBillDate) {
            const cur = String(billDate.value || '').trim();
            // Keep existing only when it is inside the open Transaction Date Setup range.
            if (!keepExisting || !cur || (openBillDateFrom && cur < openBillDateFrom) || (openBillDateTo && cur > openBillDateTo)) {
                setValue(billDate, openBillDate);
            }
        }
        if (deliveryDate) {
            const floor = billDate.value || openBillDateFrom || openBillDate;
            if (floor && (!deliveryDate.value || deliveryDate.value < floor)) {
                setValue(deliveryDate, floor);
            }
            if (floor) deliveryDate.min = floor;
        }
    };

    const applyTxnDateBlockedUi = () => {
        applySalesOrderActionState();
    };

    const DRAFT_KEY = (form?.dataset.draftKey || 'sales_draft').trim() || 'sales_draft';

    const setDefaultPriceMode = (force = false) => {
        if (force || !priceMode?.value) {
            setValue(priceMode, 'retail');
            setValue(priceModeDisplay, 'Retail');
            showClear(priceModeClear, true);
        }
    };

    const fetchNextBillNo = async (retrying = false) => {
        // Peek on open (no BILLNOTABLE lock/insert). Save allocates/reserves the final number.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 45000);
        try {
            const sep = String(nextBillBase || '').includes('?') ? '&' : '?';
            const res = await fetch(`${nextBillBase}/next-billno${sep}peek=1`, { signal: controller.signal });
            const data = await res.json();
            if (data.success) {
                setValue(billNo, data.billno);
                return;
            }
            if (data.billno_busy && !retrying) {
                setTimeout(() => fetchNextBillNo(true), 1500);
                return;
            }
            alert(data.error || 'Could not load next bill number. Click New to try again.');
        } catch (e) {
            console.error('Failed to fetch next bill number', e);
            if (!retrying) {
                setTimeout(() => fetchNextBillNo(true), 1500);
                return;
            }
            alert('Could not load next bill number (database busy). Click New to try again.');
        } finally {
            clearTimeout(timer);
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

    const resetLoyaltyCustomer = () => {
        setValue(loyaltyCustomerDisplay, '');
        setValue(loyaltyCustomerCode, '');
        showClear(loyaltyCustomerClear, false);
        saveDraft();
    };

    const parseLoyaltyCustomerCode = () => {
        const raw = loyaltyCustomerCode?.value?.trim();
        if (!raw) return 0;
        const n = parseInt(raw, 10);
        return Number.isNaN(n) ? 0 : n;
    };

    async function refreshLoyaltyDisplayFromPicker(code) {
        const urlBase = window.__SALES_LOYALTY_CUSTOMERS_PICKER__;
        const raw = String(code || '').trim();
        if (!urlBase || !raw) return;
        try {
            const res = await fetch(`${urlBase}?q=${encodeURIComponent(raw)}&limit=40`, { credentials: 'same-origin' });
            const data = await res.json();
            if (!data || !data.success) return;
            const rows = data.customers || [];
            const hit = rows.find((c) => String(c.code) === raw) || rows.find((c) => String(c.code) === String(Number(raw)));
            if (!hit) return;
            setValue(loyaltyCustomerDisplay, formatCustomerDisplay(hit.code, hit.name));
            const pts = hit.totalpoints != null ? hit.totalpoints : hit.totalPoints;
            if (pts != null && loyaltyPoints) setValue(loyaltyPoints, pts);
        } catch (e) {
            /* ignore */
        }
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
        const apiBase = (salesBinCfg.itemBinInventoryApi || '/sales/item-bin-inventory').trim();
        try {
            const res = await fetch(`${apiBase}?item_code=${encodeURIComponent(itemCode)}&warehouse_id=${encodeURIComponent(String(whId))}`);
            const data = await res.json();
            if (!data.success) return;
            const best = pickBestStockRow(data.bins || []);
            if (best) {
                applyLineBinSelection(best.storage_id, best.code, best.name);
                return;
            }
            const whApi = (salesBinCfg.warehouseBinsApi || '/sales/api/warehouse-bins').trim();
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

    const resetWarehouse = (force = false) => {
        if (!force && siHasDocumentLines()) {
            alert(SI_WAREHOUSE_LOCKED_MSG);
            return;
        }
        setValue(warehouseDisplay, '');
        setValue(warehouseIdEl, '');
        setValue(warehouseCodeEl, '');
        setValue(warehouseNameEl, '');
        showClear(warehouseClear, false);
        saveDraft();
        siSyncHeaderWarehouseLock();
    };

    const SI_WAREHOUSE_LOCKED_MSG = 'Warehouse cannot be changed after lines are added. Remove all lines first.';

    const siHasDocumentLines = () => Boolean(tableBody?.querySelector('tr[data-line]'));

    const siGuardHeaderWarehouseChange = () => {
        if (!warehouseEnabled) return true;
        if (!siHasDocumentLines()) return true;
        alert(SI_WAREHOUSE_LOCKED_MSG);
        return false;
    };

    const siSyncHeaderWarehouseLock = () => {
        if (!warehouseEnabled) return;
        const locked = siHasDocumentLines();
        if (warehouseDisplay) {
            warehouseDisplay.title = locked ? SI_WAREHOUSE_LOCKED_MSG : '';
            warehouseDisplay.classList.toggle('si-warehouse-locked', locked);
        }
        if (warehousePicker) {
            warehousePicker.disabled = locked;
            warehousePicker.title = locked ? SI_WAREHOUSE_LOCKED_MSG : '';
        }
        if (warehouseClear) {
            warehouseClear.disabled = locked;
            if (locked) {
                warehouseClear.style.display = 'none';
            } else {
                showClear(warehouseClear, Boolean(warehouseIdEl?.value));
            }
        }
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

    const siApplyHeaderWarehouseFromOrder = (header, lines) => {
        if (!warehouseEnabled) return;
        const hdr = header || {};
        const lineList = Array.isArray(lines) ? lines : [];
        let whId = hdr.warehouse_id ?? hdr.warehouseId ?? '';
        let whCode = String(hdr.warehouse_code ?? hdr.warehouseCode ?? '').trim();
        let whName = String(hdr.warehouse_name ?? hdr.warehouseName ?? '').trim();
        if (!whId && !whCode) {
            for (const line of lineList) {
                const lid = line.warehouse_id ?? line.warehouseId;
                const lcode = String(line.warehouse_code ?? line.warehouseCode ?? line.store ?? '').trim();
                const lname = String(line.warehouse_name ?? line.warehouseName ?? '').trim();
                if (lid || lcode) {
                    whId = whId || lid || '';
                    whCode = whCode || lcode;
                    whName = whName || lname;
                    break;
                }
            }
        }
        if (whId || whCode) {
            setValue(warehouseIdEl, whId != null && whId !== '' ? String(whId) : '');
            setValue(warehouseCodeEl, whCode);
            setValue(warehouseNameEl, whName);
            setValue(
                warehouseDisplay,
                hdr.warehouse_display || formatWarehouseDisplay(whCode, whName),
            );
            showClear(warehouseClear, Boolean(whId || whCode));
            applyHeaderWarehouseToLineStore();
            return;
        }
        applyUserDefaultWarehouse();
    };

    const clearDuplicateUomHighlights = () => {
        tableBody?.querySelectorAll('.uom-duplicate-highlight').forEach((cell) => {
            cell.classList.remove('uom-duplicate-highlight');
        });
    };

    let siAddLineValidatePending = false;

    const SI_FETCH_CACHE_MS = 90000;
    const _siItemInfoCache = new Map();
    const _siItemUomsCache = new Map();
    const _siItemInventoryCache = new Map();

    const siCacheGet = (map, key) => {
        const hit = map.get(key);
        if (!hit) return null;
        if (Date.now() - hit.ts > SI_FETCH_CACHE_MS) {
            map.delete(key);
            return null;
        }
        return hit.data;
    };

    const siCacheSet = (map, key, data) => {
        map.set(key, { ts: Date.now(), data });
    };

    const siFetchItemInfo = async (query) => {
        const q = String(query || '').trim();
        if (!q) return { success: false };
        const cacheKey = q.toUpperCase();
        const cached = siCacheGet(_siItemInfoCache, cacheKey);
        if (cached) return cached;
        const res = await fetch(`/sales/item-info?query=${encodeURIComponent(q)}`);
        const data = await res.json();
        siCacheSet(_siItemInfoCache, cacheKey, data);
        if (data.success && data.item?.itemcode) {
            siCacheSet(_siItemInfoCache, String(data.item.itemcode).trim().toUpperCase(), data);
        }
        return data;
    };

    const siFetchItemUoms = async (itemCode) => {
        const code = String(itemCode || '').trim();
        if (!code) return { success: false, uoms: [] };
        const cached = siCacheGet(_siItemUomsCache, code);
        if (cached) return cached;
        const res = await fetch(`/sales/item-uoms?item_code=${encodeURIComponent(code)}`);
        const data = await res.json();
        siCacheSet(_siItemUomsCache, code, data);
        return data;
    };

    const siFetchItemInventory = async (itemCode) => {
        const code = String(itemCode || '').trim();
        if (!code) return { success: false, items: [] };
        const cached = siCacheGet(_siItemInventoryCache, code);
        if (cached) return cached;
        const res = await fetch(`/sales/item-inventory?item_code=${encodeURIComponent(code)}`);
        const data = await res.json();
        siCacheSet(_siItemInventoryCache, code, data);
        return data;
    };

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
        if (!tableBody) return null;
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
            const ic = String(itemCode || '').trim();
            if (
                ic
                && String(currentItem.barcode || '').trim() === bc
                && String(currentItem.itemCode || '').trim() === ic
            ) {
                siMarkEntryInvalid('si-col-barcode', false);
                return true;
            }
            const data = await siFetchItemInfo(bc);
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
        const uomTd = getEntryRow()?.querySelector('.si-col-uom');
        if (uomTd) uomTd.classList.add('si-cell-checking');
        try {
            const [data, uomsData] = await Promise.all([
                siFetchItemInfo(code),
                siFetchItemUoms(code),
            ]);
            if (uomTd) uomTd.classList.remove('si-cell-checking');
            if (!data.success || !data.item) {
                siMarkEntryInvalid('si-col-itemcode', true, `Item code "${code}" not found.`);
                return false;
            }
            if (!String(itemName?.value || '').trim()) {
                const name = salesItemDisplayName(data.item);
                if (name) {
                    setValue(itemName, name);
                    currentItem.itemName = name;
                }
            }
            if (!String(itemName?.value || '').trim()) {
                siMarkEntryInvalid('si-col-itemcode', true, 'Item name is empty — pick the item with F1 or scan barcode first.');
                return false;
            }
            siMarkEntryInvalid('si-col-itemcode', false);

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

            const stockCheck = await siValidateItemStockInHeaderWarehouse(code, siStockCheckOptionsForEntry());
            if (!stockCheck.ok) {
                // Selecting/editing an item is allowed with no stock, but committing the
                // line (+ / Add) is blocked when the store lacks enough stock.
                siAlertNoStockIfNeeded(stockCheck);
                return false;
            }

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
        const qtyBad = entry?.querySelector('td.si-col-qty.si-cell-invalid');
        if (qtyBad && String(qtyBad.getAttribute('title') || '').trim() === SI_NO_STOCK_ALERT) {
            siFocusQuantityField();
            return;
        }
        const bad = entry?.querySelector('td.si-cell-invalid');
        if (!bad) return;
        const input = bad.querySelector('input, select, button');
        if (input && typeof input.focus === 'function') input.focus();
    };

    const siAlertFirstEntryInvalid = () => {
        const bad = getEntryRow()?.querySelector('td.si-cell-invalid');
        const msg = String(bad?.getAttribute('title') || '').trim();
        if (msg === SI_NO_STOCK_ALERT) {
            siShowLineStatus(msg, true);
            siFocusQuantityField();
            return;
        }
        if (msg) {
            siShowLineMessage(msg, true);
            return;
        }
        siShowLineMessage('Could not add line. Check item, UOM, quantity, store/warehouse, and bin.', true);
    };

    const siRaceTimeout = (promise, ms) => Promise.race([
        promise,
        new Promise((resolve) => setTimeout(resolve, ms)),
    ]);

    const siSyncEntryItemCode = () => {
        const display = String(itemCodeDisplay?.value || '').trim();
        const hidden = String(itemCodeHidden?.value || '').trim();
        if (display && !hidden) {
            setValue(itemCodeHidden, display);
        } else if (hidden && !display) {
            setValue(itemCodeDisplay, hidden);
        }
    };

    const siEnsureEntryResolvedForAdd = async () => {
        siSyncEntryItemCode();
        const code = String(itemCodeHidden?.value || itemCodeDisplay?.value || '').trim();
        if (!code) return;

        const needItemLookup = !String(itemName?.value || '').trim()
            || !String(uomCode?.value || uomDisplay?.value || '').trim();
        if (needItemLookup) {
            try {
                const data = await siFetchItemInfo(code);
                if (data.success && data.item) {
                    const it = data.item;
                    const resolvedCode = String(it.itemcode || code).trim();
                    setValue(itemCodeHidden, resolvedCode);
                    setValue(itemCodeDisplay, resolvedCode);
                    currentItem.itemCode = resolvedCode;
                    if (!String(itemName?.value || '').trim()) {
                        const name = salesItemDisplayName(it);
                        setValue(itemName, name);
                        currentItem.itemName = name;
                    }
                    const uom = String(it.baseuom || '').trim();
                    if (uom && !String(uomCode?.value || '').trim()) {
                        setValue(uomCode, uom);
                        setValue(uomDisplay, uom);
                        currentItem.baseUom = uom;
                        showClear(uomClear, true);
                    }
                    if (!currentItem.retail) {
                        currentItem.retail = Number(it.retailprice || 0);
                    }
                    if (!currentItem.cost) {
                        currentItem.cost = Number(it.costprice || 0);
                    }
                    showClear(itemClear, true);
                    if (!String(rate?.value || '').trim()) {
                        updateRateFromMode();
                    }
                }
            } catch (e) {
                console.error('Failed to resolve entry item before add', e);
            }
        }

        if (warehouseEnabled) {
            applyHeaderWarehouseToLineStore();
        }
        const storeReady = warehouseEnabled
            ? (parseInt(lineWarehouseId?.value, 10) > 0 || String(lineWarehouseCode?.value || '').trim())
            : Boolean(String(inventoryLocation?.value || '').trim());
        const binReady = !binEnabled || (parseInt(lineBinId?.value, 10) > 0);
        if (!storeReady || !binReady) {
            await fetchInventoryLocations(code);
        }
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

    const clearSalesLotPick = () => {
        if (salesLotId) salesLotId.value = '';
        if (salesLotDisplay) salesLotDisplay.value = '';
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

    const siHeaderWarehouseLabel = () => {
        const hdrCode = String(warehouseCodeEl?.value || '').trim();
        const hdrName = String(warehouseNameEl?.value || '').trim();
        return formatWarehouseDisplay(hdrCode, hdrName) || hdrCode || 'selected warehouse';
    };

    const siMatchInventoryWarehouseRow = (rows, warehouseId, warehouseCode) => {
        const whId = parseInt(warehouseId, 10) || 0;
        const whCode = String(warehouseCode || '').trim().toUpperCase();
        for (const row of rows || []) {
            const rowWhId = parseInt(row.warehouse_id ?? row.code, 10) || 0;
            const rowStore = String(row.store || row.warehouse_code || '').trim().toUpperCase();
            if (whId > 0 && rowWhId === whId) return row;
            if (whCode && rowStore === whCode) return row;
        }
        return null;
    };


    const siLineQtyBase = (qty, factor, row) => {
        if (row) {
            const baseFromRow = Number(row.dataset.baseQty || 0);
            if (baseFromRow > 0) return baseFromRow;
        }
        const q = Number(qty || 0);
        const f = Number(factor || 1) || 1;
        return q * f;
    };

    const siLineFactorFromRow = (row) => {
        const qty = Number(row?.dataset?.quantity || 0);
        const baseQty = Number(row?.dataset?.baseQty || 0);
        if (qty > 0 && baseQty > 0) return baseQty / qty;
        return 1;
    };

    const siSumOtherLinesBaseQty = (itemCode, excludeRow) => {
        const code = String(itemCode || '').trim();
        if (!code || !tableBody) return 0;
        const hdrId = parseInt(warehouseIdEl?.value, 10) || 0;
        const hdrCode = String(warehouseCodeEl?.value || '').trim().toUpperCase();
        let sum = 0;
        tableBody.querySelectorAll('tr[data-line]').forEach((row) => {
            if (row === excludeRow) return;
            if (String(row.dataset.itemCode || '').trim() !== code) return;
            if (warehouseEnabled) {
                const rowWhId = parseInt(row.dataset.warehouseId, 10) || 0;
                const rowStore = String(row.dataset.warehouseCode || row.dataset.store || '').trim().toUpperCase();
                if (hdrId > 0 && rowWhId !== hdrId) return;
                if (!hdrId && hdrCode && rowStore && rowStore !== hdrCode) return;
            }
            sum += siLineQtyBase(row.dataset.quantity, null, row);
        });
        return sum;
    };

    const siValidateItemStockInHeaderWarehouse = async (itemCode, options = {}) => {
        const code = String(itemCode || '').trim();
        if (!code) {
            return { ok: false, message: 'Item code is required.' };
        }
        const excludeRow = options.excludeRow || null;
        const qty = Number(options.qty || 0);
        const factor = Number(options.factor || 1) || 1;
        const needBase = qty > 0 ? siLineQtyBase(qty, factor, null) : 0;
        const otherBase = siSumOtherLinesBaseQty(code, excludeRow);
        const totalNeed = otherBase + needBase;

        const hdrId = parseInt(siPickWarehouseOption(options.warehouseId, warehouseIdEl?.value), 10) || 0;
        const hdrCode = siPickWarehouseOption(options.warehouseCode, warehouseCodeEl?.value);
        const lineStore = String(
            siPickWarehouseOption(options.store, lineWarehouseCode?.value)
            || siPickWarehouseOption(options.store, warehouseCodeEl?.value)
            || inventoryLocation?.value
            || '',
        ).trim();

        if (warehouseEnabled && !hdrId && !hdrCode) {
            return { ok: false, message: 'Select warehouse before adding items.' };
        }
        if (!warehouseEnabled && qty > 0 && !lineStore) {
            return { ok: false, message: 'Enter receive store for this line.' };
        }

        try {
            const data = await siFetchItemInventory(code);
            if (!data.success) {
                return { ok: false, message: 'Could not load stock for this item.' };
            }
            const items = data.items || [];
            let row = null;
            if (warehouseEnabled) {
                row = siMatchInventoryWarehouseRow(items, hdrId, hdrCode);
            } else {
                const storeUpper = lineStore.toUpperCase();
                row = items.find((r) => String(r.store || '').trim().toUpperCase() === storeUpper) || null;
                if (!row) {
                    row = pickBestStockRow(items);
                }
            }
            const stock = Number(row?.stock ?? 0);
            const fail = !minusBillingEnabled
                && ((totalNeed > 0 && stock < totalNeed) || (totalNeed <= 0 && stock <= 0));
            if (fail) {
                let message = SI_NO_STOCK_ALERT;
                const whLabel = siHeaderWarehouseLabel()
                    || formatWarehouseDisplay(hdrCode, warehouseNameEl?.value)
                    || 'selected warehouse';
                if (warehouseEnabled) {
                    const best = pickBestStockRow(items);
                    const bestStock = Number(best?.stock ?? 0);
                    if (best && bestStock > 0) {
                        const bestLabel = formatWarehouseDisplay(
                            best.store || best.warehouse_code,
                            best.description || best.name,
                        ) || 'another warehouse';
                        if (stock <= 0) {
                            message = `No stock in ${whLabel}. Available ${bestStock} in ${bestLabel}.`;
                        } else {
                            message = `Only ${stock} in ${whLabel} (need ${totalNeed}). Available ${bestStock} in ${bestLabel}.`;
                        }
                    } else if (stock <= 0) {
                        message = `No stock in ${whLabel}.`;
                    } else {
                        message = `Only ${stock} in ${whLabel} (need ${totalNeed}).`;
                    }
                }
                return {
                    ok: false,
                    message,
                    stock,
                    available: stock,
                };
            }
            return { ok: true, stock, available: stock };
        } catch (e) {
            console.error('Failed to validate warehouse stock', e);
            return { ok: false, message: 'Could not validate warehouse stock.' };
        }
    };

    const siValidateDocumentLinesStock = async ({ onLoad = false } = {}) => {
        const rows = Array.from(tableBody?.querySelectorAll('tr[data-line]') || []);
        if (!rows.length) return true;
        let allOk = true;
        const badItems = [];
        for (const row of rows) {
            const itemCode = String(row.dataset.itemCode || '').trim();
            if (!itemCode) continue;
            const qty = Number(row.dataset.quantity || 0);
            const check = await siValidateItemStockInHeaderWarehouse(itemCode, {
                qty,
                factor: siLineFactorFromRow(row),
                excludeRow: row,
                store: row.dataset.store || row.dataset.warehouseCode || '',
                warehouseId: row.dataset.warehouseId || '',
                warehouseCode: row.dataset.warehouseCode || row.dataset.store || '',
            });
            if (!check.ok) {
                allOk = false;
                badItems.push(itemCode);
                siMarkCellInvalid(row, 'si-col-qty', true, check.message);
            }
        }
        if (onLoad && badItems.length) {
            siShowLineStatus(
                badItems.length === 1
                    ? `${badItems[0]}: ${SI_NO_STOCK_ALERT}`
                    : `${SI_NO_STOCK_ALERT} (${badItems.join(', ')})`,
                true,
            );
            const firstBad = rows.find((row) => {
                const td = row.querySelector('.si-col-qty.si-cell-invalid');
                return td && String(td.getAttribute('title') || '').trim() === SI_NO_STOCK_ALERT;
            });
            siFocusQuantityField(firstBad);
        }
        return allOk;
    };

    const siStockCheckOptionsForEntry = () => {
        const hdr = siGetHeaderWarehouseContext();
        return {
            qty: Number(quantity?.value || 0),
            factor: Number(currentItem.factor || 1) || 1,
            excludeRow: editingRow,
            store: warehouseEnabled
                ? (lineWarehouseCode?.value || hdr.code || '')
                : (inventoryLocation?.value || ''),
            warehouseId: lineWarehouseId?.value || hdr.id || '',
            warehouseCode: lineWarehouseCode?.value || hdr.code || '',
        };
    };

    // Re-check stock for a committed line after its quantity is edited. Non-blocking:
    // marks the qty cell and shows a status message when the store lacks enough stock.
    const siValidateSingleRowStock = async (tr) => {
        if (!tr || !tr.matches?.('tr[data-line]')) return true;
        const itemCode = String(tr.dataset.itemCode || '').trim();
        if (!itemCode) return true;
        const check = await siValidateItemStockInHeaderWarehouse(itemCode, {
            qty: Number(tr.dataset.quantity || 0),
            factor: siLineFactorFromRow(tr),
            excludeRow: tr,
            store: tr.dataset.store || tr.dataset.warehouseCode || '',
            warehouseId: tr.dataset.warehouseId || '',
            warehouseCode: tr.dataset.warehouseCode || tr.dataset.store || '',
        });
        if (!check.ok) {
            const msg = String(check.message || SI_NO_STOCK_ALERT);
            siMarkCellInvalid(tr, 'si-col-qty', true, msg);
            siShowLineStatus(`${itemCode}: ${msg}`, true);
            return false;
        }
        siMarkCellInvalid(tr, 'si-col-qty', false);
        return true;
    };

    // Re-check stock for the entry (new/edited) line when its quantity changes. Non-blocking.
    const siValidateEntryQtyStock = async () => {
        const code = String(itemCodeHidden?.value || itemCodeDisplay?.value || '').trim();
        if (!code) return true;
        const qty = Number(quantity?.value || 0);
        if (qty <= 0) {
            siMarkEntryInvalid('si-col-qty', false);
            return true;
        }
        const check = await siValidateItemStockInHeaderWarehouse(code, siStockCheckOptionsForEntry());
        if (!check.ok) {
            const msg = String(check.message || SI_NO_STOCK_ALERT);
            siMarkEntryInvalid('si-col-qty', true, msg);
            siShowLineStatus(msg, true);
            return false;
        }
        siMarkEntryInvalid('si-col-qty', false);
        return true;
    };

    const siAlertNoStockIfNeeded = (stockCheck, row) => {
        if (stockCheck?.ok) return false;
        const msg = String(stockCheck?.message || SI_NO_STOCK_ALERT);
        if (msg !== SI_NO_STOCK_ALERT) {
            alert(msg);
            return true;
        }
        siShowLineStatus(msg, true);
        const tr = row && row.matches?.('tr[data-line]') ? row : null;
        if (tr) {
            siMarkCellInvalid(tr, 'si-col-itemcode', false);
            siMarkCellInvalid(tr, 'si-col-barcode', false);
            siMarkCellInvalid(tr, 'si-col-qty', true, msg);
            siRefreshDataRowCells(tr);
            siFocusQuantityField(tr);
            return true;
        }
        siMarkEntryInvalid('si-col-itemcode', false);
        siMarkEntryInvalid('si-col-barcode', false);
        siMarkEntryInvalid('si-col-qty', true, msg);
        siFocusQuantityField();
        return true;
    };

    const resolveWarehouseFieldsForItem = async (itemCode) => {
        if (!itemCode) return {};
        if (!warehouseEnabled) {
            try {
                const data = await siFetchItemInventory(itemCode);
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
            const data = await siFetchItemInventory(itemCode);
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
        const itemApi = (salesBinCfg.itemBinInventoryApi || '/sales/item-bin-inventory').trim();
        const whApi = (salesBinCfg.warehouseBinsApi || '/sales/api/warehouse-bins').trim();
        try {
            const res = await fetch(`${itemApi}?item_code=${encodeURIComponent(itemCode)}&warehouse_id=${encodeURIComponent(String(whId))}`);
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
        if (!itemCode || !uom) return null;
        const mode = (priceMode?.value || 'retail').toLowerCase();
        try {
            const res = await fetch(
                `/sales/uom-info?item_code=${encodeURIComponent(itemCode)}&uom_code=${encodeURIComponent(uom)}&price_mode=${encodeURIComponent(mode)}`
            );
            const data = await res.json();
            if (!data.success) return null;
            return data.pricing || null;
        } catch (e) {
            console.error('Failed to fetch UOM pricing', e);
            return null;
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
        const qty = Number(row.dataset.quantity || 0);
        let lineDiscount = Number(row.dataset.discount || 0);
        const lineRate = Number(pricing.rate || 0);
        const factor = Number(pricing.conversion_factor || 1) || 1;
        const gross = qty * lineRate;
        if (lineDiscount > gross) lineDiscount = gross;
        const amount = gross - lineDiscount;
        row.dataset.rate = String(lineRate);
        row.dataset.discount = String(lineDiscount);
        row.dataset.amount = String(amount);
        row.dataset.baseQty = String(qty * factor);
        if (pricing.cost_price != null) {
            row.dataset.cost = String(Number(pricing.cost_price || 0));
        }
        if (pricing.average_cost != null || pricing.averagecost != null) {
            row.dataset.averageCost = String(Number(pricing.average_cost || pricing.averagecost || 0));
        } else if (factor > 1 && Number(row.dataset.cost || 0) > 0) {
            row.dataset.averageCost = String(Number(row.dataset.cost || 0) / factor);
        }
        const lineNo = Number(row.dataset.line || 0) || 1;
        row.innerHTML = buildLineRowHtml(lineNo, lineRowHtmlDataFromDataset(row));
    };

    const repriceAllInvoiceLines = async () => {
        if (!priceMode?.value) return;
        const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
        for (const row of rows) {
            const itemCode = row.dataset.itemCode;
            const uom = row.dataset.uom;
            if (!itemCode || !uom) continue;
            const pricing = await getLineUomPricing(itemCode, uom);
            if (pricing) applyLineRowPricing(row, pricing);
        }
    };

    const handlePriceModeChange = () => {
        updateRateFromMode();
        repriceAllInvoiceLines().then(() => {
            updateTotals();
            saveDraft();
        });
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
        const qty = Number(tr.dataset.quantity || 0);
        const baseQty = Number(tr.dataset.baseQty || 0);
        if (qty > 0 && baseQty > 0) return baseQty / qty;
        return 1;
    };

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
        const qty = Number(tr.dataset.quantity || 0);
        const rate = Number(tr.dataset.rate || 0);
        let disc = Number(tr.dataset.discount || 0);
        const gross = qty * rate;
        if (disc > gross) {
            disc = gross;
            tr.dataset.discount = String(disc);
        }
        tr.dataset.amount = String(Math.max(0, gross - disc));
        tr.dataset.baseQty = String(qty * siLineFactor(tr));
        siRefreshDataRowCells(tr);
    };

    const siRecalcDataRowFromAmount = (tr) => {
        const qty = Number(tr.dataset.quantity || 0);
        let disc = Number(tr.dataset.discount || 0);
        let netAmount = Number(tr.dataset.amount || 0);
        if (netAmount < 0) netAmount = 0;
        if (qty > 0) {
            const gross = netAmount + disc;
            if (disc > gross) {
                disc = gross;
                tr.dataset.discount = String(disc);
                netAmount = Math.max(0, gross - disc);
            }
            tr.dataset.rate = String(gross / qty);
        }
        tr.dataset.amount = String(netAmount);
        tr.dataset.baseQty = String(qty * siLineFactor(tr));
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
            const fac = Number(pricing.conversion_factor || 1) || 1;
            const avg = Number(pricing.average_cost || pricing.averagecost || 0);
            if (avg > 0) tr.dataset.averageCost = String(avg);
            else if (fac > 1 && Number(tr.dataset.cost || 0) > 0) {
                tr.dataset.averageCost = String(Number(tr.dataset.cost || 0) / fac);
            }
        } else {
            siRecalcDataRow(tr);
        }
        siMarkCellInvalid(tr, 'si-col-uom', false);
        updateTotals();
        saveDraft();
    };

    const siApplyItemPayloadToDataRow = async (tr, payload) => {
        const stockCheck = await siValidateItemStockInHeaderWarehouse(payload.itemCode || '', {
            qty: Number(tr.dataset.quantity || 0),
            factor: siLineFactorFromRow(tr),
            excludeRow: tr,
            store: tr.dataset.store || tr.dataset.warehouseCode || '',
            warehouseId: tr.dataset.warehouseId || '',
            warehouseCode: tr.dataset.warehouseCode || tr.dataset.store || '',
        });
        if (!stockCheck.ok) {
            if (payload.barcode) {
                siMarkCellInvalid(tr, 'si-col-barcode', false);
            }
            siAlertNoStockIfNeeded(stockCheck, tr);
            if (siStockCheckBlocks(stockCheck)) return false;
        }
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
            const fac = Number(pricing.conversion_factor || 1) || 1;
            const avg = Number(pricing.average_cost || pricing.averagecost || 0);
            if (avg > 0) tr.dataset.averageCost = String(avg);
            else if (fac > 1 && Number(tr.dataset.cost || 0) > 0) {
                tr.dataset.averageCost = String(Number(tr.dataset.cost || 0) / fac);
            }
        } else if (payload.fallbackRate != null && Number(payload.fallbackRate) >= 0) {
            tr.dataset.rate = String(Number(payload.fallbackRate || 0));
            siRecalcDataRow(tr);
        } else {
            siRecalcDataRow(tr);
        }
        siRefreshDataRowCells(tr);
        updateTotals();
        saveDraft();
        return true;
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
            const res = await fetch(`/sales/item-info?query=${encodeURIComponent(code)}`);
            const data = await res.json();
            if (!data.success || !data.item) {
                siMarkCellInvalid(tr, 'si-col-itemcode', true, `Item code "${code}" not found.`);
                siRefreshDataRowCells(tr);
                return;
            }
            const item = data.item;
            const itemCode = String(item.itemcode || '').trim();
            const stockCheck = await siValidateItemStockInHeaderWarehouse(itemCode, {
                qty: Number(tr.dataset.quantity || 0),
                factor: siLineFactorFromRow(tr),
                excludeRow: tr,
                store: tr.dataset.store || tr.dataset.warehouseCode || '',
                warehouseId: tr.dataset.warehouseId || '',
                warehouseCode: tr.dataset.warehouseCode || tr.dataset.store || '',
            });
            if (!stockCheck.ok) {
                siAlertNoStockIfNeeded(stockCheck, tr);
                if (siStockCheckBlocks(stockCheck)) return;
            }
            await siApplyItemPayloadToDataRow(tr, {
                itemCode,
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
            const res = await fetch(`/sales/item-info?query=${encodeURIComponent(bc)}`);
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
            const stockCheck = await siValidateItemStockInHeaderWarehouse(itemCode, {
                qty: Number(tr.dataset.quantity || 0),
                factor: siLineFactorFromRow(tr),
                excludeRow: tr,
                store: tr.dataset.store || tr.dataset.warehouseCode || '',
                warehouseId: tr.dataset.warehouseId || '',
                warehouseCode: tr.dataset.warehouseCode || tr.dataset.store || '',
            });
            if (!stockCheck.ok) {
                siMarkCellInvalid(tr, 'si-col-barcode', false);
                siAlertNoStockIfNeeded(stockCheck, tr);
                if (siStockCheckBlocks(stockCheck)) return;
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
        if (!tr || !popupRow) return false;
        const pickerPrices = pricesFromPickerRow(popupRow);
        return siApplyItemPayloadToDataRow(tr, {
            itemCode: popupRow.dataset.code || '',
            itemName: popupRow.dataset.name || '',
            barcode: popupRow.dataset.barcode || '',
            uom: popupRow.dataset.uom || '',
            fallbackRate: Number(popupRow.dataset.rate || 0) || rateFromPriceMode(pickerPrices),
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
        if (key === 'si-col-amount') {
            cur = String(Math.max(0, Number(tr.dataset.amount || 0)));
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
                    let n = parseFloat(input.value);
                    if (isNaN(n) || n < 0) n = 0;
                    tr.dataset.amount = String(n);
                    siRecalcDataRowFromAmount(tr);
                } else if (cfg.type === 'number') {
                    let n = parseFloat(input.value);
                    if (isNaN(n) || n < 0) n = 0;
                    tr.dataset[cfg.ds] = String(n);
                    if (key === 'si-col-qty') {
                        tr.dataset.baseQty = String(n * siLineFactor(tr));
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
                    if (key === 'si-col-qty') void siValidateSingleRowStock(tr);
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
        if (warehouseEnabled && siHeaderWarehouseSelected()) {
            applyHeaderWarehouseToLineStore();
        }
        setValue(quantity, '');
        setValue(rate, '');
        setValue(discount, '');
        setValue(lineAmount, '');
        showClear(itemClear, false);
        showClear(uomClear, false);
        showClear(inventoryClear, false);
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
        siSyncHeaderWarehouseLock();
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
        const extraDiscount = Number(additionalDiscount?.value || additionalDiscountItems?.value || 0);
        let discountSum = 0;
        let grossSum = 0;
        let netSum = 0;
        const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
        rows.forEach((row) => {
            const rowDiscount = Number(row.dataset.discount || 0);
            const rowAmount = Number(row.dataset.amount || 0);
            const rowQty = Number(row.dataset.quantity || 0);
            const rowRate = Number(row.dataset.rate || 0);
            grossSum += rowQty * rowRate;
            discountSum += rowDiscount;
            netSum += rowAmount;
        });
        const totalDiscountValue = discountSum + extraDiscount;
        const netTotalValue = Math.max(0, grossSum - totalDiscountValue - promotionDiscount);
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
        siSyncHeaderWarehouseLock();
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
            averagecost: Number(row.dataset.averageCost || 0),
            average_cost: Number(row.dataset.averageCost || 0),
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
            order_no: orderNoEl?.value || '',
            loyalty_customer_code: loyaltyCustomerCode?.value || '',
            loyalty_customer_display: loyaltyCustomerDisplay?.value || '',
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
            row.dataset.quantity = Number(line.quantity || 0);
            row.dataset.rate = Number(line.rate || 0);
            row.dataset.discount = Number(line.discount || 0);
            row.dataset.amount = Number(line.amount || 0);
            row.dataset.baseQty = Number(line.base_qty || 0);
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
                quantity: Number(line.quantity || 0),
                store: line.store || '',
                warehouseCode: row.dataset.warehouseCode,
                warehouseName: row.dataset.warehouseName,
                warehouseLabel: formatWarehouseDisplay(row.dataset.warehouseCode, row.dataset.warehouseName),
                binCode: row.dataset.binCode,
                binName: row.dataset.binName,
                binLabel: formatBinDisplay(row.dataset.binCode, row.dataset.binName),
                discount: Number(line.discount || 0),
                amount: Number(line.amount || 0),
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
        if (!isSalesOrderScreen || salesOrderEditMode) {
            setValue(billNo, header.bill_no || '');
        }
        setValue(billDate, header.bill_date || '');
        syncBillDateFromOpen();
        setValue(billTime, header.bill_time || '');
        setValue(billType, header.bill_type || '');
        setValue(deliveryDate, header.delivery_date || '');
        setValue(remarks, header.remarks || '');
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
        setValue(orderNoEl, header.order_no || '');
        const draftLoyCode = header.loyalty_customer_code || '';
        setValue(loyaltyCustomerCode, draftLoyCode);
        setValue(loyaltyCustomerDisplay, header.loyalty_customer_display || (draftLoyCode ? String(draftLoyCode) : ''));
        showClear(loyaltyCustomerClear, !!draftLoyCode);
        if (draftLoyCode) refreshLoyaltyDisplayFromPicker(draftLoyCode);

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

    const applyInitialOrder = (payload) => {
        if (!payload || !payload.header || !Array.isArray(payload.lines)) return false;
        const header = payload.header || {};
        const code = header.customercode || '';
        const name = header.customername || '';
        const sourceOrderBillnos = parseSourceOrderBillnos(header);
        const convertingToInvoice = !isSalesOrderScreen && (
            sourceOrderBillnos.length > 0 || convertFromOrders.length > 0
        );
        if (convertingToInvoice) {
            const linked = sourceOrderBillnos.length ? sourceOrderBillnos : convertFromOrders;
            setValue(sourceOrderBillnosEl, linked.join(','));
            setValue(sourceOrderBillnoEl, linked[0] || '');
        } else {
            setValue(sourceOrderBillnosEl, '');
            setValue(sourceOrderBillnoEl, '');
            setValue(billNo, header.billno || '');
        }
        setValue(billDate, header.billdate || '');
        // Keep loaded order/invoice date; Sales Order edit must not replace billdate with open day.
        syncBillDateFromOpen({ keepExisting: true });
        setValue(billTime, header.billtime || '');
        const loadedBt = String(header.billtype || '').trim().toUpperCase().slice(0, 1);
        if (loadedBt === 'C' || loadedBt === 'R') {
            setValue(billType, loadedBt);
            if (outstandingAmount) {
                outstandingAmount.dataset.customerBillingType = loadedBt === 'R' ? 'CREDIT' : 'CASH';
            }
        } else if (header.customer_billing_type) {
            applyCustomerBillingType(header.customer_billing_type);
        } else if (code) {
            setValue(billType, '');
        }
        setValue(deliveryDate, header.deliverydate || header.delivery_date || '');
        setValue(remarks, header.remarks || '');
        setValue(customerDisplay, formatCustomerDisplay(code, name));
        setValue(customerCode, code);
        setValue(customerName, name);
        setValue(customerAddress, header.address || '');
        setValue(orderNoEl, header.orderno || header.order_no || '');
        const loyCode = header.loyaltycustomercode != null ? String(header.loyaltycustomercode) : '';
        if (loyCode && loyCode !== '0') {
            setValue(loyaltyCustomerCode, loyCode);
            showClear(loyaltyCustomerClear, true);
            refreshLoyaltyDisplayFromPicker(loyCode);
        } else {
            resetLoyaltyCustomer();
        }
        showClear(customerClear, Boolean(header.customercode));
        syncCustomerDetailsModal();
        siApplyHeaderWarehouseFromOrder(header, payload.lines || []);
        restoreLines(payload.lines || []);
        updateTotals();
        siSyncHeaderWarehouseLock();
        orderBillStatus = header.billstatus || 'P';
        if (isSalesOrderScreen) {
            salesOrderEditMode = true;
            applyBillDateRangeBounds();
        }
        syncRefDisplay();
        applySalesOrderActionState();
        if (convertingToInvoice) {
            void fetchNextBillNo();
        }
        void siValidateDocumentLinesStock({ onLoad: true });
        return true;
    };

    const scrollTableToBottom = () => {
        const scrollEl = tableBody?.closest('.scroll-table');
        if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    };

    const setItemFromRow = async (row) => {
        const itemCode = row.dataset.code || '';
        const stockCheck = await siValidateItemStockInHeaderWarehouse(itemCode, siStockCheckOptionsForEntry());
        if (!stockCheck.ok) {
            siAlertNoStockIfNeeded(stockCheck);
            if (siStockCheckBlocks(stockCheck)) return false;
        }
        currentItem.itemCode = itemCode;
        currentItem.itemName = row.dataset.name || '';
        currentItem.barcode = row.dataset.barcode || '';
        setValue(barcodeInput, currentItem.barcode);
        currentItem.baseUom = row.dataset.uom || '';
        currentItem.retail = Number(row.dataset.retail || 0);
        currentItem.wholesale = Number(row.dataset.wholesale || 0);
        currentItem.third = Number(row.dataset.third || 0);
        currentItem.branch = Number(row.dataset.branch || 0);
        currentItem.cost = Number(row.dataset.cost || 0);
        currentItem.factor = 1;

        setValue(barcodeInput, currentItem.barcode || '');
        setValue(itemCodeDisplay, currentItem.itemCode);
        setValue(itemCodeHidden, currentItem.itemCode);
        setValue(itemName, currentItem.itemName);
        setValue(uomDisplay, currentItem.baseUom);
        setValue(uomCode, currentItem.baseUom);
        showClear(itemClear, true);
        showClear(uomClear, true);
        applyEntryRateFromPrices(
            {
                retail: currentItem.retail,
                wholesale: currentItem.wholesale,
                third: currentItem.third,
                branch: currentItem.branch,
            },
            row.dataset.rate,
        );
        fetchItemUoms(currentItem.itemCode).then(() => {
            applyUomSelection(currentItem.baseUom || uomCode?.value || '');
        });
        fetchInventoryLocations(currentItem.itemCode);
        clearSalesLotPick();
        return true;
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
            const res = await fetch(`/sales/item-inventory?item_code=${encodeURIComponent(itemCode)}`, { signal });
            const data = await res.json();
            if (!data.success) {
                renderInventoryRows([]);
                return;
            }
            siCacheSet(_siItemInventoryCache, String(itemCode).trim(), data);
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
        const itemApi = (salesBinCfg.itemBinInventoryApi || '/sales/item-bin-inventory').trim();
        const whApi = (salesBinCfg.warehouseBinsApi || '/sales/api/warehouse-bins').trim();
        try {
            if (itemCode) {
                const res = await fetch(`${itemApi}?item_code=${encodeURIComponent(itemCode)}&warehouse_id=${encodeURIComponent(String(whId))}`);
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
            if (binEnabled && itemCode) {
                const binReady = parseInt(lineBinId?.value, 10) > 0;
                if (!binReady) {
                    const whId = parseInt(lineWarehouseId?.value, 10)
                        || parseInt(warehouseIdEl?.value, 10)
                        || 0;
                    await resolveLineBinForItem(itemCode, whId);
                }
            }
            return;
        }
        if (!itemCode) {
            renderInventoryRows([]);
            setValue(inventoryLocation, '');
            showClear(inventoryClear, false);
            return;
        }
        try {
            const data = await siFetchItemInventory(itemCode);
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
                    const bestRow = listForBest.reduce((best, row) => (
                        Number(row.stock || 0) > Number(best.stock || 0) ? row : best
                    ), listForBest[0]);
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
        void (async () => {
            const check = await siValidateItemStockInHeaderWarehouse(currentItem.itemCode, {
                qty: Number(row.dataset.quantity || 0),
                factor: siLineFactorFromRow(row),
                excludeRow: row,
                store: row.dataset.store || row.dataset.warehouseCode || '',
                warehouseId: row.dataset.warehouseId || '',
                warehouseCode: row.dataset.warehouseCode || row.dataset.store || '',
            });
            if (!check.ok) {
                siAlertNoStockIfNeeded(check);
            }
        })();
        if (quantity) {
            quantity.focus();
        }
        scrollTableToBottom();
    };

    const updateRateFromMode = () => {
        if (currentItem.itemCode && uomCode?.value && priceMode?.value) {
            updatePricingByUom();
            return;
        }
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

    const updateLineAmount = () => {
        if (siEntryAmountEditing) return;
        const qty = Number(quantity?.value || 0);
        const lineRate = Number(rate?.value || 0);
        let lineDiscount = Number(discount?.value || 0);
        const gross = qty * lineRate;
        if (lineDiscount > gross) {
            lineDiscount = gross;
            setValue(discount, formatNumber(lineDiscount));
        }
        const amount = gross - lineDiscount;
        setValue(lineAmount, formatNumber(amount));
    };

    const updateRateFromAmount = () => {
        const qty = Number(quantity?.value || 0);
        if (qty <= 0) return;
        let lineDiscount = Number(discount?.value || 0);
        let netAmount = parseEntryAmount(lineAmount?.value);
        if (netAmount < 0) {
            netAmount = 0;
            setValue(lineAmount, formatNumber(0));
        }
        const gross = netAmount + lineDiscount;
        if (lineDiscount > gross) {
            lineDiscount = gross;
            setValue(discount, formatNumber(lineDiscount));
            netAmount = Math.max(0, gross - lineDiscount);
            setValue(lineAmount, formatNumber(netAmount));
        }
        const newRate = gross / qty;
        setValue(rate, formatRate(newRate));
    };

    const rateFromPriceMode = (prices) => {
        const mode = (priceMode?.value || 'retail').toLowerCase();
        if (mode === 'wholesale') return Number(prices.wholesale || 0);
        if (mode === 'third') return Number(prices.third || 0);
        if (mode === 'branch') return Number(prices.branch || 0);
        return Number(prices.retail || 0);
    };

    const pricesFromPickerRow = (row) => ({
        retail: Number(row?.dataset?.retail || 0),
        wholesale: Number(row?.dataset?.wholesale || 0),
        third: Number(row?.dataset?.third || 0),
        branch: Number(row?.dataset?.branch || 0),
    });

    const applyEntryRateFromPrices = (prices, pickerRate) => {
        const pickRate = Number(pickerRate || 0) || rateFromPriceMode(prices);
        setValue(rate, formatRate(pickRate));
        updateLineAmount();
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
        const modeRate = Number(itemPopupPriceForItem(item) || 0);
        return {
            code: item.itemcode || '',
            name: salesItemDisplayName(item) || '',
            barcode: item.manufacturerid || '',
            uom: String(item.unit || item.baseuom || '').trim(),
            cost: Number(item.costprice || 0),
            retail: Number(item.retailprice || 0),
            wholesale: Number(item.wholesaleprice || 0),
            third: Number(item.thirdprice || 0),
            branch: Number(item.branchprice || 0),
            rate: modeRate,
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
        params.set('minus_billing', minusBillingEnabled ? '1' : '0');
        const res = await fetch(`/sales/item-popup-items?${params.toString()}`, { signal, credentials: 'same-origin' });
        let data;
        try {
            data = await res.json();
        } catch (parseErr) {
            console.error('item popup invalid JSON', res.status);
            return [];
        }
        if (!res.ok || !data.success) {
            console.error('item popup failed', data && data.error ? data.error : res.status);
            return [];
        }
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
            const res = await fetch(`/sales/item-history?${params.toString()}`);
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

    const fetchItemUoms = async (itemCode) => {
        if (!itemCode) return [];
        try {
            const res = await fetch(`/sales/item-uoms?item_code=${encodeURIComponent(itemCode)}`);
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
        const fallbackPrices = {
            retail: currentItem.retail,
            wholesale: currentItem.wholesale,
            third: currentItem.third,
            branch: currentItem.branch,
        };
        try {
            const res = await fetch(`/sales/uom-info?item_code=${encodeURIComponent(currentItem.itemCode)}&uom_code=${encodeURIComponent(uomCode.value)}&price_mode=${encodeURIComponent(priceMode?.value || 'retail')}`);
            const data = await res.json();
            if (!data.success) {
                const fallback = rateFromPriceMode(fallbackPrices);
                if (fallback > 0) {
                    currentItem.factor = 1;
                    setValue(rate, formatRate(fallback));
                    updateLineAmount();
                    return;
                }
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
            currentItem.averageCost = Number(
                pricing.average_cost || pricing.averagecost || 0
            );
            if (!(currentItem.averageCost > 0) && currentItem.factor > 1 && currentItem.cost > 0) {
                currentItem.averageCost = currentItem.cost / currentItem.factor;
            }
            setValue(rate, formatRate(pricing.rate || 0));
            updateLineAmount();
        } catch (e) {
            console.error('Failed to fetch UOM pricing', e);
            const fallback = rateFromPriceMode(fallbackPrices);
            if (fallback > 0) {
                setValue(rate, formatRate(fallback));
                updateLineAmount();
            }
        }
    };

    const fetchItemByBarcode = async (barcode, options = {}) => {
        const showNotFoundAlert = options.showNotFoundAlert !== false;
        const notFoundMessage = options.notFoundMessage || 'Item not found';
        const focusOnSuccess = options.focusOnSuccess !== false;
        try {
            const res = await fetch(`/sales/item-info?query=${encodeURIComponent(barcode)}`);
            const data = await res.json();
            if (!data.success) {
                if (showNotFoundAlert) {
                    alert(data.error || notFoundMessage);
                }
                return false;
            }
            const item = data.item || {};
            const itemCode = String(item.itemcode || '').trim();
            if (warehouseEnabled && !siRequireHeaderWarehouse()) {
                return false;
            }
            const stockCheck = await siValidateItemStockInHeaderWarehouse(itemCode, siStockCheckOptionsForEntry());
            if (!stockCheck.ok) {
                siAlertNoStockIfNeeded(stockCheck);
                if (siStockCheckBlocks(stockCheck)) return false;
            }
            currentItem.itemCode = item.itemcode || '';
            currentItem.itemName = salesItemDisplayName(item);
            currentItem.barcode = item.manufacturerid || '';
            currentItem.baseUom = item.baseuom || '';
            currentItem.retail = Number(item.retailprice || 0);
            currentItem.wholesale = Number(item.wholesaleprice || 0);
            currentItem.third = Number(item.thirdprice || 0);
            currentItem.branch = Number(item.branchprice || 0);
            currentItem.cost = Number(item.costprice || 0);
            currentItem.averageCost = Number(item.averagecost || item.average_cost || item.costprice || 0);
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
            try {
                nextFocus.scrollIntoView({ block: 'nearest' });
            } catch (ignore) {}
        }
    };

    const appendOrMergeLine = (spec, options = {}) => {
        if (!tableBody || !getEntryRow()) return false;
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
        let lineAvgCost = Number(spec.averageCost || spec.average_cost || 0);
        if (!(lineAvgCost > 0) && lineFactor > 1 && lineCost > 0) {
            lineAvgCost = lineCost / lineFactor;
        }

        if (warehouseEnabled && !(parseInt(whIdVal, 10) > 0) && !String(spec.warehouseCode || '').trim()) return false;
        if (binEnabled && !(parseInt(storageIdVal, 10) > 0)) return false;
        if (!itemCodeVal || !uomVal) return false;

        let qty = Number(spec.qty || 0);
        if (qty <= 0) return false;

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

        const gross = qty * lineRate;
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

        const amount = gross - lineDiscount;
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
        row.dataset.averageCost = lineAvgCost;
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

    const buildEntryLineSpec = () => {
        siSyncEntryItemCode();
        if (warehouseEnabled) applyHeaderWarehouseToLineStore();
        if (!String(uomCode?.value || '').trim() && uomDisplay?.value) {
            setValue(uomCode, uomDisplay.value.trim());
        }
        if (!String(itemName?.value || '').trim() && currentItem.itemName) {
            setValue(itemName, currentItem.itemName);
        }
        const hdr = siGetHeaderWarehouseContext();
        return {
            itemCode: itemCodeHidden?.value || itemCodeDisplay?.value,
            barcode: currentItem.barcode || (barcodeInput?.value || '').trim(),
            itemName: itemName?.value || currentItem.itemName || '',
            uom: uomCode?.value || uomDisplay?.value || currentItem.baseUom || '',
            qty: Number(quantity?.value || 0),
            rate: rate?.value,
            discount: discount?.value,
            cost: currentItem.cost || 0,
            averageCost: currentItem.averageCost || 0,
            factor: currentItem.factor || 1,
            store: warehouseEnabled ? (lineWarehouseCode?.value || hdr.code || '') : (inventoryLocation?.value || ''),
            warehouseId: lineWarehouseId?.value || hdr.id || '',
            warehouseCode: lineWarehouseCode?.value || hdr.code || '',
            warehouseName: lineWarehouseName?.value || hdr.name || '',
            storageId: lineBinId?.value,
            binCode: lineBinCode?.value,
            binName: lineBinName?.value,
            lotId: salesLotId?.value?.trim() || '',
            lotLabel: salesLotDisplay?.value?.trim() || '',
        };
    };

    const appendEntryLineOrExplain = (spec) => {
        const ok = appendOrMergeLine(spec);
        if (ok) return true;
        let reason = 'Could not add this line.';
        if (!String(spec.itemCode || '').trim()) {
            reason = 'Enter or select an item first.';
            siMarkEntryInvalid('si-col-itemcode', true, reason);
        } else if (!String(spec.uom || '').trim()) {
            reason = 'Enter unit (UOM) for this line.';
            siMarkEntryInvalid('si-col-uom', true, reason);
        } else if (!(Number(spec.qty || 0) > 0)) {
            reason = 'Enter a valid quantity greater than zero.';
            siMarkEntryInvalid('si-col-qty', true, reason);
        } else if (warehouseEnabled && !siHeaderWarehouseSelected() && !(parseInt(spec.warehouseId, 10) > 0) && !String(spec.warehouseCode || '').trim()) {
            reason = 'Select warehouse for this line (pick header warehouse first).';
            siMarkEntryInvalid('si-col-warehouse', true, reason);
        } else if (binEnabled && !(parseInt(spec.storageId, 10) > 0)) {
            reason = 'Select bin for this line.';
            siMarkEntryInvalid('si-col-bin', true, reason);
        } else if (!warehouseEnabled && !String(spec.store || '').trim()) {
            reason = 'Enter receive store for this line.';
            siMarkEntryInvalid('si-col-store', true, reason);
        } else {
            reason = 'This line may already be in the list. Change item, UOM, store, or barcode.';
        }
        siShowLineMessage(reason, true);
        siFocusFirstEntryInvalid();
        return false;
    };

    const finishAddedLine = () => {
        siClearAllLineHighlights();
        siShowLineMessage('');
        updateTotals();
        saveDraft();
        resetItemLine();
        focusEntryForNextLine();
    };

    const addLine = async () => {
        if (!tableBody || !getEntryRow()) {
            siShowLineMessage('Line entry row is missing. Please refresh the page.', true);
            return;
        }
        if (!siRequireHeaderWarehouse()) return;
        if (siAddLineValidatePending) {
            siShowLineMessage('Adding line, please wait…', true);
            return;
        }

        siSyncEntryItemCode();
        const code = String(itemCodeHidden?.value || itemCodeDisplay?.value || '').trim();
        if (!code) {
            siShowLineMessage('Enter or select an item first.', true);
            focusItemEntry();
            return;
        }
        const qty = Number(quantity?.value || 0);
        if (qty <= 0) {
            siShowLineMessage('Enter a valid quantity greater than zero.', true);
            siMarkEntryInvalid('si-col-qty', true, 'Enter a valid quantity greater than zero.');
            quantity?.focus();
            return;
        }

        siAddLineValidatePending = true;
        try {
            await siRaceTimeout(siEnsureEntryResolvedForAdd(), 6000);
            const valid = await siRaceTimeout(siValidateEntryBeforeAdd(), 8000);
            if (valid === false) {
                siFocusFirstEntryInvalid();
                siAlertFirstEntryInvalid();
                return;
            }
            const spec = buildEntryLineSpec();
            if (!appendEntryLineOrExplain(spec)) {
                return;
            }
            finishAddedLine();
        } catch (err) {
            console.error('addLine failed', err);
            siShowLineMessage('Could not add line. Please check item details and try again.', true);
        } finally {
            siAddLineValidatePending = false;
        }
    };
    window.__siTriggerAddLine = addLine;

    const wireSiAddLineControls = () => {
        if (!btnAddLine || btnAddLine.dataset.siWired === '1') return;
        btnAddLine.dataset.siWired = '1';
        btnAddLine.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                addLine();
            }
        });
    };
    wireSiAddLineControls();

    if (lineAmount) {
        lineAmount.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                updateRateFromAmount();
                handleEnterMove(e, btnAddLine);
            }
        });
    }

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
                averagecost: Number(row.dataset.averageCost || 0),
                average_cost: Number(row.dataset.averageCost || 0),
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
        if (isSalesOrderScreen && String(orderBillStatus || '').trim().toUpperCase() === 'V') {
            alert('This sales order is cancelled and cannot be changed.');
            return;
        }
        if (isSalesOrderScreen && String(orderBillStatus || '').trim().toUpperCase() === 'I') {
            alert('This sales order is invoiced and cannot be changed.');
            return;
        }
        if (txnDateBlocked) {
            alert(txnDateError || 'Setup date is missing. No open From–To date range in Transaction Date Setup. Open a date range in General Setup → Transaction Date Setup before posting.');
            return;
        }
        const lines = gatherLines();
        if (!lines.length) {
            alert('No items to save.');
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
            billtype: (billType?.value || '').trim(),
            customer_billing_type: (outstandingAmount?.dataset.customerBillingType || 'CASH').toUpperCase(),
            customercode: customerCode.value,
            customername: customerName.value,
            sessioncode: 0,
            deliverydate: deliveryDate ? deliveryDate.value : '',
            remarks: remarksVal,
            address: customerAddress.value,
            orderno: orderNoVal.slice(0, 80),
            loyaltycustomercode: parseLoyaltyCustomerCode(),
        };
        const sourceOrdersRaw = String(sourceOrderBillnosEl?.value || sourceOrderBillnoEl?.value || '').trim();
        if (sourceOrdersRaw) {
            const sourceOrders = sourceOrdersRaw.split(',').map((v) => v.trim()).filter(Boolean);
            header.source_order_billnos = sourceOrders;
            header.source_order_billno = sourceOrders[0] || '';
        }
        if (warehouseEnabled) {
            const whId = parseInt(warehouseIdEl?.value, 10) || 0;
            if (whId > 0) header.warehouse_id = whId;
            const whCode = headerWarehouseStoreCode();
            if (whCode) header.warehouse_code = whCode;
        }

        if (!window.confirm('Do you want to save?')) return;

        const saveBtnLabel = btnSave ? btnSave.textContent : 'Save';
        saveInFlight = true;
        if (btnSave) {
            btnSave.disabled = true;
            btnSave.textContent = 'Saving...';
        }
        try {
            const { res, data } = await fetchSaveJson(`${saveBase}/save`, { header, lines });
            if (!data.success) {
                if ((data.duplicate_billno || data.duplicate_doc_key) && data.suggested_billno != null) {
                    header.billno = String(data.suggested_billno);
                    setValue(billNo, data.suggested_billno);
                    const retry = await fetchSaveJson(`${saveBase}/save`, { header, lines });
                    const data2 = retry.data;
                    if (data2.success) {
                        window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data2 }));
                        openSavedInvoicePdf(data2.billno, data2.pdf_url);
                        if (!data2.billno_reassigned && data2.message) alert(data2.message);
                        clearDraft();
                        await resetForm({ nextBillno: data2.next_billno });
                        return;
                    }
                }
                let msg = data.error || 'Save failed.';
                if (data.save_session_locked) {
                    msg = 'Another save is still running. Wait for it to finish, then try again.';
                }
                if (data.replay_blocked) {
                    msg += ' The save token was refreshed; try Save again.';
                }
                alert(msg);
                window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: data }));
                return;
            }
            window.dispatchEvent(new CustomEvent('nexa-transaction-save-success', { detail: data }));
            openSavedInvoicePdf(data.billno, data.pdf_url);
            let saveMsg = data.billno_reassigned ? '' : (data.message || '');
            if (data.order_mark_warning) {
                saveMsg = saveMsg ? `${saveMsg}\n\n${data.order_mark_warning}` : data.order_mark_warning;
            } else if (Array.isArray(data.source_order_billnos) && data.source_order_billnos.length) {
                const linked = data.source_order_billnos.length > 1
                    ? `Sales orders ${data.source_order_billnos.join(', ')} marked invoiced.`
                    : `Sales order ${data.source_order_billnos[0]} marked invoiced.`;
                saveMsg = saveMsg ? `${saveMsg}\n\n${linked}` : linked;
            } else if (data.source_order_billno) {
                const linked = `Sales order ${data.source_order_billno} marked invoiced.`;
                saveMsg = saveMsg ? `${saveMsg}\n\n${linked}` : linked;
            }
            if (saveMsg) alert(saveMsg);
            clearDraft();
            if (sourceOrdersRaw) {
                setValue(sourceOrderBillnosEl, '');
                setValue(sourceOrderBillnoEl, '');
            }
            await resetForm({ nextBillno: data.next_billno });
        } catch (e) {
            console.error('Save failed', e);
            alert(e?.message || 'Save failed.');
            window.dispatchEvent(new CustomEvent('nexa-transaction-save-failed', { detail: { error: String(e) } }));
        } finally {
            saveInFlight = false;
            if (btnSave) {
                btnSave.textContent = saveBtnLabel;
            }
            applySalesOrderActionState();
        }
    };

    const resetForm = async (opts = {}) => {
        clearDraft();
        form.reset();
        resetCustomer();
        resetLoyaltyCustomer();
        setValue(orderNoEl, '');
        orderBillStatus = '';
        salesOrderEditMode = false;
        setValue(sourceOrderBillnosEl, '');
        setValue(sourceOrderBillnoEl, '');
        resetItemLine();
        clearTable();
        if (warehouseEnabled) resetWarehouse(true);
        updateBillDefaults();
        setDefaultPriceMode(true);
        const nextFromServer = opts.nextBillno != null && String(opts.nextBillno).trim() !== ''
            ? String(opts.nextBillno).trim()
            : '';
        if (nextFromServer) {
            setValue(billNo, nextFromServer);
        } else {
            await fetchNextBillNo();
        }
        applyUserDefaultWarehouse();
        applySalesOrderActionState();
        if (customerDisplay) {
            customerDisplay.focus();
        }
    };


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

    function _escapeHtmlAttr(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;');
    }

    function renderSalesCustomerPickerRows(customers) {
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
                `<tr data-code="${_escapeHtmlAttr(code)}" data-name="${_escapeHtmlAttr(name)}" data-phone="${_escapeHtmlAttr(phone)}"`
                + ` data-address="${_escapeHtmlAttr(addr)}" data-categorycode="${_escapeHtmlAttr(catc)}" data-categoryname="${_escapeHtmlAttr(catn)}"`
                + ` data-billing-type="${_escapeHtmlAttr(bt)}" data-creditlimit="${_escapeHtmlAttr(creditlimit)}"`
                + ` data-currentcredit="${_escapeHtmlAttr(curcred)}" data-outstandingcash="${_escapeHtmlAttr(outcash)}" data-totalpoints="${_escapeHtmlAttr(pts)}">`
                + `<td>${_escapeHtmlAttr(code)}</td><td>${_escapeHtmlAttr(name || '-')}</td><td>${_escapeHtmlAttr(phone || '-')}</td>`
                + `<td>${billTd}</td></tr>`
            );
        }).join('');
        tb.innerHTML = html;
    }

    function filterSalesCustomerPickerRows(customers, term) {
        const q = String(term || '').trim().toLowerCase();
        if (!q) return customers || [];
        return (customers || []).filter((c) => {
            const code = String(c.code != null ? c.code : '').toLowerCase();
            const name = String(c.name != null ? c.name : '').toLowerCase();
            const phone = String(c.phone != null ? c.phone : '').toLowerCase();
            return code.indexOf(q) !== -1 || name.indexOf(q) !== -1 || phone.indexOf(q) !== -1;
        });
    }

    function scheduleSalesCustomerPickerSearch(term, opts) {
        clearTimeout(_custPickTimer);
        if (opts && opts.immediate) {
            loadSalesCustomerPicker(term, opts);
            return;
        }
        _custPickTimer = setTimeout(() => loadSalesCustomerPicker(term, opts), 280);
    }

    function loadSalesCustomerPicker(term, opts) {
        const tb = document.querySelector('#customerModalTable tbody');
        const urlBase = window.__SALES_CUSTOMERS_PICKER__;
        if (!tb || !urlBase) return;
        const q = String(term || '').trim();
        const emptyQ = !q;
        const limit = emptyQ ? 150 : 200;

        if (emptyQ && _custPickerFullCache.length && Date.now() - _custPickerEmptyCacheAt < CUST_PICKER_EMPTY_CACHE_MS) {
            renderSalesCustomerPickerRows(_custPickerFullCache);
            return;
        }

        if (!emptyQ) {
            if (q.length < 2) {
                if (_custPickerFullCache.length) {
                    renderSalesCustomerPickerRows(filterSalesCustomerPickerRows(_custPickerFullCache, q));
                }
                return;
            }
            const localHits = filterSalesCustomerPickerRows(_custPickerFullCache, q);
            if (localHits.length) {
                renderSalesCustomerPickerRows(localHits);
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
                renderSalesCustomerPickerRows(rows);
            })
            .catch((err) => {
                if (err.name === 'AbortError') return;
                if (_custPickerFullCache.length) {
                    renderSalesCustomerPickerRows(filterSalesCustomerPickerRows(_custPickerFullCache, q));
                    return;
                }
                tb.innerHTML = `<tr><td colspan="4">${_escapeHtmlAttr(err.message || err)}</td></tr>`;
            });
    }

    setupModal({
        modalId: 'customerModal',
        inputId: 'customer_display',
        pickerId: 'customerPicker',
        clearId: 'customerClear',
        onSearch: (term, opts) => {
            scheduleSalesCustomerPickerSearch(term, opts);
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
            focusOrderNoField();
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
                return;
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                focusOrderNoField();
            }
        });
    }

    let _loyPickTimer = null;
    let _loyPickAbort = null;

    function renderSalesLoyaltyPickerRows(customers) {
        const tb = document.querySelector('#loyaltyCustomerModalTable tbody');
        if (!tb) return;
        if (!customers || !customers.length) {
            tb.innerHTML = '<tr><td colspan="4">No loyalty customers found. Try another search.</td></tr>';
            return;
        }
        const html = customers.map((c) => {
            const code = c.code != null ? String(c.code) : '';
            const name = c.name != null ? String(c.name) : '';
            const phone = c.phone != null ? String(c.phone) : '';
            const pts = c.totalpoints != null ? String(c.totalpoints) : (c.totalPoints != null ? String(c.totalPoints) : '0');
            return (
                `<tr data-code="${_escapeHtmlAttr(code)}" data-name="${_escapeHtmlAttr(name)}" data-phone="${_escapeHtmlAttr(phone)}" data-totalpoints="${_escapeHtmlAttr(pts)}">`
                + `<td>${_escapeHtmlAttr(code)}</td><td>${_escapeHtmlAttr(name || '-')}</td><td>${_escapeHtmlAttr(phone || '-')}</td>`
                + `<td>${_escapeHtmlAttr(pts)}</td></tr>`
            );
        }).join('');
        tb.innerHTML = html;
    }

    function scheduleSalesLoyaltyPickerSearch(term) {
        clearTimeout(_loyPickTimer);
        _loyPickTimer = setTimeout(() => loadSalesLoyaltyPicker(term), 280);
    }

    function loadSalesLoyaltyPicker(term) {
        const tb = document.querySelector('#loyaltyCustomerModalTable tbody');
        const urlBase = window.__SALES_LOYALTY_CUSTOMERS_PICKER__;
        if (!tb || !urlBase) return;
        if (_loyPickAbort) _loyPickAbort.abort();
        _loyPickAbort = new AbortController();
        const u = `${urlBase}?q=${encodeURIComponent(term || '')}&limit=300`;
        tb.innerHTML = '<tr><td colspan="4">Loading…</td></tr>';
        fetch(u, { credentials: 'same-origin', signal: _loyPickAbort.signal })
            .then((r) => r.json())
            .then((data) => {
                if (!data || !data.success) throw new Error((data && data.error) || 'Load failed');
                renderSalesLoyaltyPickerRows(data.customers || []);
            })
            .catch((err) => {
                if (err.name === 'AbortError') return;
                tb.innerHTML = `<tr><td colspan="4">${_escapeHtmlAttr(err.message || err)}</td></tr>`;
            });
    }

    setupModal({
        modalId: 'loyaltyCustomerModal',
        inputId: 'loyalty_customer_display',
        pickerId: 'loyaltyCustomerPicker',
        clearId: 'loyaltyCustomerClear',
        onSearch: (term) => {
            scheduleSalesLoyaltyPickerSearch(term);
        },
        onSelect: (row) => {
            const code = row.dataset.code || '';
            const name = row.dataset.name || '';
            setValue(loyaltyCustomerDisplay, formatCustomerDisplay(code, name));
            setValue(loyaltyCustomerCode, code);
            const pts = row.dataset.totalpoints || '0';
            if (loyaltyPoints) setValue(loyaltyPoints, pts);
            showClear(loyaltyCustomerClear, true);
            saveDraft();
        },
        onClear: resetLoyaltyCustomer,
    });

    if (orderNoEl) {
        orderNoEl.addEventListener('input', saveDraft);
        orderNoEl.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            e.stopPropagation();
            if (warehouseEnabled && warehouseDisplay) {
                focusWarehouseField();
            } else {
                focusBarcodeEntry();
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

    setupModal({
        modalId: 'priceModeModal',
        inputId: 'price_mode_display',
        pickerId: 'priceModePicker',
        clearId: 'priceModeClear',
        onSelect: (row) => {
            setValue(priceMode, row.dataset.code || '');
            setValue(priceModeDisplay, row.dataset.name || '');
            showClear(priceModeClear, true);
            handlePriceModeChange();
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
                `<tr data-id="${_escapeHtmlAttr(id)}" data-code="${_escapeHtmlAttr(whCode)}" data-name="${_escapeHtmlAttr(name)}">`
                + `<td>${_escapeHtmlAttr(whCode)}</td><td>${_escapeHtmlAttr(name || '-')}</td></tr>`
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
        const docKind = (salesWarehouseCfg.docKind || 'sales').trim();
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
                tb.innerHTML = `<tr><td colspan="2">${_escapeHtmlAttr(err.message || err)}</td></tr>`;
            });
    }

    if (warehouseEnabled && warehouseDisplay && warehousePicker) {
        setupModal({
            modalId: 'warehouseModal',
            inputId: 'warehouseDisplay',
            pickerId: 'warehousePicker',
            clearId: 'warehouseClear',
            beforeOpen: () => siGuardHeaderWarehouseChange(),
            onSearch: (term, opts) => {
                if (opts && opts.immediate) {
                    clearTimeout(_whPickTimer);
                    loadSalesWarehousePicker(term);
                } else {
                    scheduleSalesWarehousePickerSearch(term);
                }
            },
                onSelect: (row) => {
                if (!siGuardHeaderWarehouseChange()) return;
                const id = row.dataset.id || '';
                const whCode = row.dataset.code || '';
                const whName = row.dataset.name || '';
                setValue(warehouseDisplay, formatWarehouseDisplay(whCode, whName));
                setValue(warehouseIdEl, id);
                setValue(warehouseCodeEl, whCode);
                setValue(warehouseNameEl, whName);
                showClear(warehouseClear, true);
                if (itemCodeHidden?.value) {
                    resolveLineWarehouseForItem(itemCodeHidden.value);
                } else {
                    applyHeaderWarehouseToLineStore();
                }
                saveDraft();
                focusBarcodeEntry();
            },
            onClear: resetWarehouse,
        });

        warehouseDisplay.addEventListener('keydown', (e) => {
            if (e.key === 'F1') {
                e.preventDefault();
                if (!siGuardHeaderWarehouseChange()) return;
                const whModal = document.getElementById('warehouseModal');
                if (whModal && typeof whModal.openModal === 'function') {
                    whModal.openModal();
                }
            } else if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                focusBarcodeEntry();
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
            onSelect: async (row) => {
                if (siInlineModalRow) {
                    const ok = await siApplyPopupItemToDataRow(siInlineModalRow, row);
                    siInlineModalRow = null;
                    return ok !== false;
                }
                const ok = await setItemFromRow(row);
                if (!ok) return false;
                if (uomDisplay) uomDisplay.focus();
                return true;
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
                if (!siRequireHeaderWarehouse()) return;
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
                    alert('Item not found or not in stock in the selected warehouse.');
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
                    if (!siRequireHeaderWarehouse()) return;
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
                void siValidateEntryQtyStock();
                handleEnterMove(e, nextAfterQty);
            }
        });
        quantity.addEventListener('input', updateLineAmount);
        quantity.addEventListener('change', () => { void siValidateEntryQtyStock(); });
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
            const parsed = parseEntryAmount(lineAmount.value);
            setValue(lineAmount, formatNumber(parsed));
            updateRateFromAmount();
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

    if (priceMode) {
        priceMode.addEventListener('change', handlePriceModeChange);
    }

    if (btnAddLine && btnAddLine.dataset.siWired !== '1') {
        wireSiAddLineControls();
    }
    if (btnClearLine) {
        btnClearLine.addEventListener('click', () => {
            resetItemLine();
            setTimeout(() => focusItemEntry(), 0);
        });
    }
    if (btnSave) btnSave.addEventListener('click', saveInvoice);
    if (btnPrintOrderPdf) btnPrintOrderPdf.addEventListener('click', () => openOrderPdf());
    if (btnCancelOrder) {
        btnCancelOrder.addEventListener('click', async () => {
            const bno = String(billNo?.value || '').trim();
            if (!bno) return;
            if (!window.confirm(`Cancel sales order ${bno}? This cannot be undone.`)) return;
            try {
                const res = await fetch(`/sales-order/${encodeURIComponent(bno)}/cancel`, { method: 'POST' });
                const data = await res.json();
                if (!data.success) {
                    alert(data.error || 'Cancel failed.');
                    return;
                }
                orderBillStatus = 'V';
                applySalesOrderActionState();
                alert('Sales order cancelled.');
            } catch (e) {
                alert('Cancel failed.');
            }
        });
    }
    if (btnNew) btnNew.addEventListener('click', resetForm);
    if (btnDiscard) btnDiscard.addEventListener('click', resetForm);
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

    if (tableBody) tableBody.addEventListener('click', (e) => {
        if (e.target.closest('#btnAddLine')) {
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
                && !e.target.closest('.btn-remove')
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
        const btn = e.target.closest('.btn-remove');
        if (!btn) return;
        const row = btn.closest('tr');
        if (row && row.dataset.line) {
            if (editingRow === row) {
                resetItemLine();
            }
            row.remove();
            const rows = Array.from(tableBody.querySelectorAll('tr[data-line]'));
            rows.forEach((r, idx) => {
                r.dataset.line = String(idx + 1);
                r.children[0].textContent = String(idx + 1);
            });
            if (!rows.length) {
                clearTable();
            } else {
                updateTotals();
            }
            pinEntryRowToBottom();
            saveDraft();
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

    if (form) {
        form.addEventListener('submit', (e) => e.preventDefault());
    }

    const isReloadNavigation = (() => {
        try {
            const nav = (performance && performance.getEntriesByType)
                ? performance.getEntriesByType('navigation')
                : [];
            if (nav && nav.length && nav[0] && nav[0].type) {
                return nav[0].type === 'reload';
            }
            // Legacy fallback.
            return !!(performance && performance.navigation && performance.navigation.type === 1);
        } catch (e) {
            return false;
        }
    })();

    const initialOrderPayload = await resolveInitialOrderPayload();
    const initialOrderLoaded = applyInitialOrder(initialOrderPayload);
    if (!initialOrderLoaded) {
        const convertParams = new URLSearchParams(window.location.search);
        const convertRaw = (convertParams.get('from_orders') || convertParams.get('from_order') || '').trim();
        if (convertRaw && !isSalesOrderScreen) {
            console.warn('Sales order convert failed for', convertRaw);
        }
    }
    if (!initialOrderLoaded && isReloadNavigation) {
        // Refresh should behave like New: discard in-session draft state.
        clearDraft();
    }
    const draftLoaded = (initialOrderLoaded || isReloadNavigation) ? false : loadDraft();

    applySalesOrderActionState();

    if (!initialOrderLoaded && !draftLoaded) {
        updateBillDefaults();
        setDefaultPriceMode();
        if (!String(billNo?.value || '').trim()) {
            fetchNextBillNo();
        } else {
            syncRefDisplay();
        }
        clearTable();
        applyUserDefaultWarehouse();
        if (customerDisplay) {
            customerDisplay.focus();
        }
    } else if (draftLoaded) {
        syncBillDateFromOpen();
        updateTotals();
        // Draft keeps the reserved bill no; only fetch if draft was saved before async reservation finished.
        if (!String(billNo?.value || '').trim() || (isSalesOrderScreen && !salesOrderEditMode)) {
            void fetchNextBillNo();
        } else {
            syncRefDisplay();
        }
    } else if (String(billNo?.value || '').trim()) {
        syncRefDisplay();
    }

    applyTxnDateBlockedUi();
    siSyncHeaderWarehouseLock();

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
                    const res = await fetch(`/sales/item-info?query=${encodeURIComponent(query)}`);
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
            let averageCost = 0;
            if (item.barcode_uom != null && item.barcode_retail_price != null) {
                rate = Number(item.barcode_retail_price) || 0;
            } else {
                const pricing = await getLineUomPricing(itemCode, uom);
                if (pricing) {
                    rate = Number(pricing.rate || 0);
                    factor = Number(pricing.conversion_factor || 1) || 1;
                    if (pricing.cost_price != null) cost = Number(pricing.cost_price || 0);
                    averageCost = Number(pricing.average_cost || pricing.averagecost || 0);
                } else {
                    rate = Number(item.retailprice || 0);
                }
            }
            if (!(averageCost > 0) && factor > 1 && cost > 0) averageCost = cost / factor;
            else if (!(averageCost > 0)) averageCost = cost;

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
                averageCost,
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
