(function () {
    window.posHoldBtnLabel = function (hasActiveLines) {
        if (hasActiveLines) return 'Hold';
        return 'Hold Retrive';
    };

    window.posSalesReturnBtnLabel = function (mode) {
        if (mode === 'sales') return 'Sales';
        return 'Sales Return';
    };

    if (document.body.classList.contains('pos-page')) {
        document.body.classList.add('pos-page-loading');
        document.addEventListener(
            'contextmenu',
            function (e) {
                e.preventDefault();
            },
            true
        );
    }

    (function posBillingAutoFullscreen() {
        const STORAGE_DISMISS = 'nexa-pos-fs-gate-dismissed';
        const STORAGE_AUTO_FS = 'nexa-pos-auto-fullscreen';

        function isFullscreen() {
            return !!(
                document.fullscreenElement
                || document.webkitFullscreenElement
                || document.msFullscreenElement
                || document.mozFullScreenElement
            );
        }

        async function enterPageFullscreen() {
            if (!document.body.classList.contains('pos-page')) return false;
            if (isFullscreen()) return true;
            const root = document.documentElement;
            const fn =
                root.requestFullscreen
                || root.webkitRequestFullscreen
                || root.msRequestFullscreen
                || root.mozRequestFullScreen;
            if (!fn) return false;
            try {
                await fn.call(root);
                return true;
            } catch (_e) {
                return false;
            }
        }

        async function exitPageFullscreen() {
            if (!isFullscreen()) return true;
            const fn =
                document.exitFullscreen
                || document.webkitExitFullscreen
                || document.msExitFullscreen
                || document.mozCancelFullScreen;
            if (!fn) return false;
            try {
                await fn.call(document);
                return true;
            } catch (_e) {
                return false;
            }
        }

        async function togglePageFullscreen() {
            if (isFullscreen()) return exitPageFullscreen();
            return enterPageFullscreen();
        }

        window.__posBillingFullscreen = {
            isFullscreen,
            enter: enterPageFullscreen,
            exit: exitPageFullscreen,
            toggle: togglePageFullscreen,
            isAutoEnabled: isAutoFullscreenEnabled,
            setAutoEnabled: setAutoFullscreenEnabled,
            bindAutoOnGesture: bindAutoFullscreenOnGesture,
        };

        function isAutoFullscreenEnabled() {
            try {
                const v = localStorage.getItem(STORAGE_AUTO_FS);
                if (v === null) return true;
                return v === '1';
            } catch (_e) {
                return false;
            }
        }

        function setAutoFullscreenEnabled(on) {
            try {
                localStorage.setItem(STORAGE_AUTO_FS, on ? '1' : '0');
            } catch (_e) {
                /* ignore */
            }
        }

        function bindAutoFullscreenOnGesture() {
            if (!document.body.classList.contains('pos-page')) return;
            if (!isAutoFullscreenEnabled() || isFullscreen()) return;
            const tryEnter = () => {
                enterPageFullscreen();
            };
            document.addEventListener('pointerdown', tryEnter, { capture: true, passive: true, once: true });
            document.addEventListener('keydown', tryEnter, { capture: true, once: true });
        }

        function fullscreenGateDismissed() {
            try {
                return sessionStorage.getItem(STORAGE_DISMISS) === '1';
            } catch (_e) {
                return false;
            }
        }

        function hideFullscreenGate() {
            const gate = document.getElementById('posFullscreenGate');
            if (!gate) return;
            gate.classList.add('hidden');
            gate.setAttribute('aria-hidden', 'true');
            window.dispatchEvent(new CustomEvent('posBarcodeFocusRequest'));
        }

        function showFullscreenGateIfNeeded() {
            if (isAutoFullscreenEnabled()) return;
            if (!document.body.classList.contains('pos-page')) return;
            const gate = document.getElementById('posFullscreenGate');
            if (!gate || fullscreenGateDismissed()) return;
            if (isFullscreen()) {
                hideFullscreenGate();
                return;
            }
            gate.classList.remove('hidden');
            gate.setAttribute('aria-hidden', 'false');
        }

        function onFullscreenViewportChange() {
            if (isFullscreen()) hideFullscreenGate();
            else showFullscreenGateIfNeeded();
        }

        function bindFullscreenGate() {
            const gate = document.getElementById('posFullscreenGate');
            const btn = document.getElementById('posFullscreenGateBtn');
            const dismiss = document.getElementById('posFullscreenGateDismiss');
            if (!gate || !btn) return;

            async function activate(ev) {
                if (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                }
                await enterPageFullscreen();
                if (isFullscreen()) hideFullscreenGate();
            }

            btn.addEventListener('click', activate);

            gate.addEventListener(
                'click',
                (e) => {
                    if (e.target === gate) activate(e);
                },
                false
            );

            if (dismiss) {
                dismiss.addEventListener('click', (e) => {
                    if (e) e.preventDefault();
                    try {
                        sessionStorage.setItem(STORAGE_DISMISS, '1');
                    } catch (_e) {
                        /* ignore */
                    }
                    hideFullscreenGate();
                });
            }
        }

        if (!document.body.classList.contains('pos-page')) return;

        [
            'fullscreenchange',
            'webkitfullscreenchange',
            'mozfullscreenchange',
            'MSFullscreenChange',
        ].forEach((evt) => document.addEventListener(evt, onFullscreenViewportChange, false));

        bindFullscreenGate();
        hideFullscreenGate();

        if (isAutoFullscreenEnabled()) {
            bindAutoFullscreenOnGesture();
            enterPageFullscreen();
        }
    })();

    (function posBillingSetupModal() {
        if (!document.body.classList.contains('pos-page')) return;
        const modal = document.getElementById('posHandednessModal');
        const btnLeft = document.getElementById('posHandednessLeft');
        const btnRight = document.getElementById('posHandednessRight');
        const btnContinue = document.getElementById('posSetupContinue');
        const btnSetupFullscreen = document.getElementById('posSetupFullscreen');
        const chkAutoFs = document.getElementById('posSetupAutoFullscreen');
        const chkShowCost = document.getElementById('posSetupShowCost');
        const btnOpenSetup = document.getElementById('btnPosSetup');
        const STORAGE_THEME = 'nexa-pos-theme';
        const STORAGE_LAYOUT = 'nexa-pos-layout';
        const STORAGE_DONE = 'nexa-pos-setup-done';
        const STORAGE_SHOW_COST = 'nexa-pos-show-cost';
        const THEME_SIDES = /** @type {const} */ (['white', 'black', 'lite', 'ocean', 'warmgrey']);

        if (!modal || !btnLeft || !btnRight) return;

        function currentThemeId() {
            for (let i = 0; i < THEME_SIDES.length; i++) {
                const id = THEME_SIDES[i];
                if (document.body.classList.contains(`pos-theme-${id}`)) return id;
            }
            return 'default';
        }

        /** @param {string} theme */
        function applyPosTheme(theme) {
            THEME_SIDES.forEach((id) => {
                document.body.classList.remove(`pos-theme-${id}`);
            });
            if (theme && theme !== 'default' && THEME_SIDES.includes(theme)) {
                document.body.classList.add(`pos-theme-${theme}`);
            }
            try {
                localStorage.setItem(STORAGE_THEME, theme === 'default' || !theme ? 'default' : theme);
            } catch (_e) {
                /* ignore */
            }
            syncThemePills();
        }

        function syncThemePills() {
            const cur = currentThemeId();
            document.querySelectorAll('.pos-setup-theme-btn[data-pos-theme]').forEach((el) => {
                const btn = el;
                const v = btn.getAttribute('data-pos-theme') || 'default';
                btn.classList.toggle('is-active', v === cur);
            });
        }

        document.querySelectorAll('.pos-setup-theme-btn[data-pos-theme]').forEach((el) => {
            el.addEventListener('click', () => {
                const theme = el.getAttribute('data-pos-theme') || 'default';
                applyPosTheme(theme);
            });
        });

        syncThemePills();

        function closeModal() {
            modal.classList.add('hidden');
            modal.setAttribute('aria-hidden', 'true');
            try {
                localStorage.setItem(STORAGE_DONE, '1');
            } catch (_e) {
                /* ignore */
            }
        }

        function openSetupModal() {
            modal.classList.remove('hidden');
            modal.setAttribute('aria-hidden', 'false');
            syncThemePills();
            syncSetupFullscreenBtn();
            syncAutoFsCheckbox();
            syncShowCostCheckbox();
        }

        function readShowCostPref() {
            try {
                return localStorage.getItem(STORAGE_SHOW_COST) === '1';
            } catch (_e) {
                return false;
            }
        }

        function applyShowCostPref(enabled, opts) {
            const on = !!enabled;
            try {
                localStorage.setItem(STORAGE_SHOW_COST, on ? '1' : '0');
            } catch (_e) {
                /* ignore */
            }
            document.body.classList.toggle('pos-show-cost', on);
            if (!opts || !opts.silent) {
                window.dispatchEvent(new CustomEvent('posShowCostPrefChanged', { detail: { enabled: on } }));
            }
        }

        function syncShowCostCheckbox() {
            if (chkShowCost) chkShowCost.checked = readShowCostPref();
        }

        window.__posBillingShowCost = {
            isEnabled: readShowCostPref,
            setEnabled: (enabled) => applyShowCostPref(enabled),
        };

        if (chkShowCost) {
            chkShowCost.addEventListener('change', () => {
                applyShowCostPref(chkShowCost.checked);
            });
        }
        applyShowCostPref(readShowCostPref(), { silent: true });

        function applyLayout(layout) {
            if (layout === 'left') {
                document.body.classList.add('pos-handedness-left');
            } else {
                document.body.classList.remove('pos-handedness-left');
                layout = 'right';
            }
            try {
                localStorage.setItem(STORAGE_LAYOUT, layout);
            } catch (_e) {
                /* ignore */
            }
        }

        try {
            const savedLayout = localStorage.getItem(STORAGE_LAYOUT);
            if (savedLayout === 'left' || savedLayout === 'right') {
                applyLayout(savedLayout);
            }
        } catch (_e) {
            /* ignore */
        }

        async function finishSetup(layout) {
            if (layout) applyLayout(layout);
            const api = window.__posBillingFullscreen;
            if (api && typeof api.isAutoEnabled === 'function' && api.isAutoEnabled()) {
                await api.enter();
            }
            closeModal();
            window.dispatchEvent(new CustomEvent('posBarcodeFocusRequest'));
        }

        btnLeft.addEventListener('click', () => {
            document.body.classList.add('pos-handedness-left');
            finishSetup('left');
        });
        btnRight.addEventListener('click', () => {
            document.body.classList.remove('pos-handedness-left');
            finishSetup('right');
        });
        if (btnContinue) {
            btnContinue.addEventListener('click', () => finishSetup(null));
        }
        if (btnOpenSetup) {
            btnOpenSetup.addEventListener('click', openSetupModal);
        }

        function syncAutoFsCheckbox() {
            if (!chkAutoFs) return;
            const api = window.__posBillingFullscreen;
            chkAutoFs.checked = !!(api && typeof api.isAutoEnabled === 'function' && api.isAutoEnabled());
        }

        if (chkAutoFs) {
            chkAutoFs.addEventListener('change', () => {
                const api = window.__posBillingFullscreen;
                if (api && typeof api.setAutoEnabled === 'function') {
                    api.setAutoEnabled(chkAutoFs.checked);
                }
                if (chkAutoFs.checked && api && typeof api.bindAutoOnGesture === 'function') {
                    api.bindAutoOnGesture();
                }
            });
            syncAutoFsCheckbox();
        }

        function syncSetupFullscreenBtn() {
            if (!btnSetupFullscreen) return;
            const api = window.__posBillingFullscreen;
            const on = api && typeof api.isFullscreen === 'function' && api.isFullscreen();
            btnSetupFullscreen.textContent = on ? 'Exit full screen' : 'Full screen';
            btnSetupFullscreen.setAttribute('aria-pressed', on ? 'true' : 'false');
        }

        if (btnSetupFullscreen) {
            btnSetupFullscreen.addEventListener('click', async () => {
                const api = window.__posBillingFullscreen;
                if (!api || typeof api.toggle !== 'function') return;
                await api.toggle();
                syncSetupFullscreenBtn();
            });
            [
                'fullscreenchange',
                'webkitfullscreenchange',
                'mozfullscreenchange',
                'MSFullscreenChange',
            ].forEach((evt) => document.addEventListener(evt, syncSetupFullscreenBtn, false));
            syncSetupFullscreenBtn();
        }

        closeModal();
        if (window.__posBillingFullscreen && typeof window.__posBillingFullscreen.bindAutoOnGesture === 'function') {
            window.__posBillingFullscreen.bindAutoOnGesture();
        }
        window.dispatchEvent(new CustomEvent('posBarcodeFocusRequest'));
    })();
    const billNo = document.getElementById('bill_no');
    function posBillnoFromInput(raw) {
        return String(raw == null ? '' : raw).trim();
    }
    function posBillnoIsValid(raw) {
        const s = posBillnoFromInput(raw);
        if (!s) return false;
        if (/^\d+$/.test(s)) {
            const n = parseInt(s, 10);
            return Number.isFinite(n) && n > 0;
        }
        return true;
    }
    function posBillnoForApi(raw) {
        const s = posBillnoFromInput(raw);
        return s || null;
    }
    const billDate = document.getElementById('bill_date');
    const customerDisplay = document.getElementById('customer_display');
    const customerCode = document.getElementById('customer_code');
    const loyaltyCustomerDisplay = document.getElementById('loyalty_customer_display');
    const loyaltyCustomerCode = document.getElementById('loyalty_customer_code');
    const customerCreditLimitDisplay = document.getElementById('customer_credit_limit_display');
    const customerOutstandingDisplay = document.getElementById('customer_outstanding_display');
    const customerCreditLimitWarn = document.getElementById('customer_credit_limit_warn');
    /** @type {number | null} */
    let billingCustomerCreditLimit = null;
    /** @type {number | null} */
    let billingCustomerOutstanding = null;
    const loyaltyPointsDisplay = document.getElementById('loyalty_points_display');
    const loyaltyCardnoDisplay = document.getElementById('loyalty_cardno_display');
    const posOrderNoEl = document.getElementById('pos_orderno');
    const btnClearCustomer = document.getElementById('btnClearCustomer');
    const btnClearLoyaltyCustomer = document.getElementById('btnClearLoyaltyCustomer');
    const customerModal = document.getElementById('customerModal');
    const customerModalTitle = document.getElementById('customerModalTitle');
    const customerModalSearch = document.getElementById('customerModalSearch');
    const customerModalBody = document.getElementById('customerModalBody');
    const barcodeInput = document.getElementById('barcode_input');
    const barcodeLookupModal = document.getElementById('barcodeLookupModal');
    const barcodeLookupSearch = document.getElementById('barcodeLookupSearch');
    const barcodeLookupBody = document.getElementById('barcodeLookupBody');
    const barcodeQtyModal = document.getElementById('barcodeQtyModal');
    const barcodeQtyInput = document.getElementById('barcodeQtyInput');
    const barcodeQtyItemName = document.getElementById('barcodeQtyItemName');
    const btnBarcodeQtyApply = document.getElementById('btnBarcodeQtyApply');
    const posOrderEmpty = document.getElementById('posOrderEmpty');
    const posOrderList = document.getElementById('posOrderList');
    const posOrderLines = document.getElementById('posOrderLines');
    const posGrandTotalEl = document.getElementById('posGrandTotal');
    const posTotalDiscountEl = document.getElementById('posTotalDiscount');
    const posDdTotalPointsEl = document.getElementById('posDdTotalPoints');
    const posNetTotalEl = document.getElementById('posNetTotal');
    const checkoutNetTotalEl = document.getElementById('checkout_net_total');
    const btnNew = document.getElementById('btnNew');
    const btnVoid = document.getElementById('btnVoid');
    const btnCheckout = document.getElementById('btnCheckout');
    const btnPosBarcodeEnter = document.getElementById('btnPosBarcodeEnter');
    const btnPosBarcodeBackspace = document.getElementById('btnPosBarcodeBackspace');
    const btnPosBarcodeClear = document.getElementById('btnPosBarcodeClear');
    const posLastBillSummary = document.getElementById('posLastBillSummary');
    const posLastBillNet = document.getElementById('posLastBillNet');
    const posLastBillPaid = document.getElementById('posLastBillPaid');
    const posLastBillChange = document.getElementById('posLastBillChange');
    const posLastBillNo = document.getElementById('posLastBillNo');
    const checkoutModal = document.getElementById('checkoutModal');
    const posValidateOverlay = document.getElementById('posValidateOverlay');
    const posValidateOverlayLabel = document.getElementById('posValidateOverlayLabel');
    const checkoutTotalPaidEl = document.getElementById('checkout_total_paid');
    const checkoutValidationMsg = document.getElementById('checkout_validation_msg');
    const btnCheckoutConfirm = document.getElementById('btnCheckoutConfirm');
    let posCheckoutSubmitInFlight = false;

    function setPosCheckoutActionsDisabled(disabled) {
        if (btnCheckout) btnCheckout.disabled = disabled;
        if (btnCheckoutConfirm) btnCheckoutConfirm.disabled = disabled;
    }
    const receiptPreviewModal = document.getElementById('receiptPreviewModal');
    const receiptPreviewText = document.getElementById('receiptPreviewText');
    const receiptPreviewStatus = document.getElementById('receiptPreviewStatus');
    const btnPrintReceiptPreview = document.getElementById('btnPrintReceiptPreview');
    const voidModal = document.getElementById('voidModal');
    const voidBillNo = document.getElementById('voidBillNo');
    const btnVoidConfirm = document.getElementById('btnVoidConfirm');
    const btnRetrieveHold = document.getElementById('btnRetrieveHold');
    const btnHold = document.getElementById('btnHold');
    const btnSalesReturn = document.getElementById('btnSalesReturn');
    const btnPosCustomer = document.getElementById('btnPosCustomer');
    const btnPosLoyaltyCustomer = document.getElementById('btnPosLoyaltyCustomer');
    const btnPosCreateLoyalty = document.getElementById('btnPosCreateLoyalty');
    const btnItemVoid = document.getElementById('btnItemVoid');
    const btnChangeQty = document.getElementById('btnChangeQty');
    const changeQtyModal = document.getElementById('changeQtyModal');
    const changeQtyInput = document.getElementById('changeQtyInput');
    const changeQtyHint = document.getElementById('changeQtyHint');
    const btnChangeQtyApply = document.getElementById('btnChangeQtyApply');
    const btnChangePrice = document.getElementById('btnChangePrice');
    const changePriceModal = document.getElementById('changePriceModal');
    const changePriceInput = document.getElementById('changePriceInput');
    const changePriceHint = document.getElementById('changePriceHint');
    const btnChangePriceApply = document.getElementById('btnChangePriceApply');
    const btnChangeAmount = document.getElementById('btnChangeAmount');
    const changeAmountModal = document.getElementById('changeAmountModal');
    const changeAmountInput = document.getElementById('changeAmountInput');
    const changeAmountHint = document.getElementById('changeAmountHint');
    const btnChangeAmountApply = document.getElementById('btnChangeAmountApply');
    const btnLineDiscount = document.getElementById('btnLineDiscount');
    const lineDiscountInput = document.getElementById('lineDiscountInput');
    const btnLineDiscountApply = document.getElementById('btnLineDiscountApply');
    const counterCodeEl = document.getElementById('counter_code');
    const counterDisplayEl = document.getElementById('counter_display');

    function formatPosCounterDisplay(code, name) {
        const c = String(code == null ? '' : code).trim();
        const n = String(name == null ? '' : name).trim();
        if (c && n && c !== '—' && n !== '—') return `${c} — ${n}`;
        if (c && c !== '—') return c;
        if (n && n !== '—') return n;
        return '—';
    }

    function getPosCounterNameFromDisplay() {
        if (counterDisplayEl && counterDisplayEl.dataset) {
            const n = String(counterDisplayEl.dataset.name || '').trim();
            if (n) return n;
        }
        return '';
    }

    function applyPosCounterDisplay(code, name) {
        const c = String(code == null ? '' : code).trim();
        const n = String(name == null ? '' : name).trim();
        const text = formatPosCounterDisplay(c || '—', n || '—');
        if (!counterDisplayEl) return;
        counterDisplayEl.textContent = text;
        counterDisplayEl.dataset.code = c;
        counterDisplayEl.dataset.name = n;
        counterDisplayEl.title = c && n ? `${c} — ${n}` : text;
    }
    const btnItemDetails = document.getElementById('btnItemDetails');
    const itemDetailsBarcodeInput = document.getElementById('itemDetailsBarcode');
    const btnItemDetailsCheck = document.getElementById('btnItemDetailsCheck');
    const itemDetailsResult = document.getElementById('itemDetailsResult');
    const itemDetailsError = document.getElementById('itemDetailsError');

    function syncPosSaveNonceFromResponse(data) {
        if (data && typeof data.save_nonce === 'string' && data.save_nonce) {
            window.__POS_SAVE_NONCE = data.save_nonce;
        }
    }

    async function posPostJson(url, body, options = {}) {
        const maxAttempts = Math.max(1, options.maxAttempts || 2);
        let lastRes = null;
        let lastData = {};
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            lastRes = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
                body: JSON.stringify(body),
                credentials: options.credentials || 'same-origin',
            });
            lastData = await lastRes.json().catch(() => ({}));
            syncPosSaveNonceFromResponse(lastData);
            const replay = !!(lastData.replay_blocked || lastRes.status === 409);
            if (!replay || attempt >= maxAttempts - 1) {
                break;
            }
        }
        return { res: lastRes, data: lastData };
    }

    async function refreshPosSaveNonce() {
        try {
            const res = await fetch('/pos-billing/refresh-save-nonce', { credentials: 'same-origin' });
            const data = await res.json().catch(() => ({}));
            syncPosSaveNonceFromResponse(data);
            return !!(data && data.success);
        } catch (_e) {
            return false;
        }
    }

    function syncPosDdTotalPointsBar() {
        if (!posDdTotalPointsEl) return;
        const lcBar = loyaltyCustomerCode?.value?.trim() ?? '';
        if (!lcBar || lcBar === '0') {
            posDdTotalPointsEl.textContent = '—';
            return;
        }
        const pt = loyaltyPointsDisplay ? String(loyaltyPointsDisplay.textContent || '').trim() : '';
        posDdTotalPointsEl.textContent = pt || '—';
    }

    let cart = [];
    const belowCostAlerted = new Set();
    let selectedLineIndex = null;
    let promotionDiscount = 0;
    let appliedVouchers = [];
    let salesReturnEnabled = false;
    let salesReturnOneShot = false;
    let _salesReturnTapTimer = null;

    window.__syncPosDynamicCompactLabels = function () {
        const activeCount = (cart || []).filter((ln) => !ln.voided).length;
        if (btnHold) {
            btnHold.textContent = window.posHoldBtnLabel(activeCount > 0);
        }
        if (btnSalesReturn) {
            const mode = salesReturnEnabled ? 'sales' : 'return';
            btnSalesReturn.textContent = window.posSalesReturnBtnLabel(mode);
        }
    };

    function syncPosSalesReturnBanner() {
        const el = document.getElementById('pos_sales_return_banner');
        if (!el) return;
        if (salesReturnEnabled) {
            el.classList.add('pos-sales-return-banner--visible');
            el.setAttribute('aria-hidden', 'false');
        } else {
            el.classList.remove('pos-sales-return-banner--visible');
            el.setAttribute('aria-hidden', 'true');
        }
    }

    function focusPosBarcodeScan() {
        const el = barcodeInput || document.getElementById('barcode_input');
        if (!el) return;
        const apply = () => {
            const ae = document.activeElement;
            if (btnSalesReturn && ae === btnSalesReturn) {
                btnSalesReturn.blur();
            }
            try {
                el.focus({ preventScroll: true });
            } catch (e) {
                try {
                    el.focus();
                } catch (e2) {
                    /* ignore */
                }
            }
        };
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                apply();
                if (document.activeElement !== el) {
                    window.setTimeout(apply, 60);
                }
                if (document.activeElement !== el) {
                    window.setTimeout(apply, 150);
                }
            });
        });
    }

    function shouldDeferBarcodeFocusForBlockingGates() {
        const handedness = document.getElementById('posHandednessModal');
        if (handedness && !handedness.classList.contains('hidden')) return true;
        const fsGate = document.getElementById('posFullscreenGate');
        if (fsGate && !fsGate.classList.contains('hidden')) return true;
        return false;
    }

    function focusPosBarcodeScanIfNoBlockingGate() {
        if (shouldDeferBarcodeFocusForBlockingGates()) return;
        focusPosBarcodeScan();
    }

    /** POS setup / fullscreen gates dismiss before barcode exists — listener registered early */
    window.addEventListener('posBarcodeFocusRequest', () => focusPosBarcodeScanIfNoBlockingGate());

    function exitSalesReturnMode() {
        if (_salesReturnTapTimer) {
            clearTimeout(_salesReturnTapTimer);
            _salesReturnTapTimer = null;
        }
        salesReturnEnabled = false;
        salesReturnOneShot = false;
        if (btnSalesReturn) {
            btnSalesReturn.classList.remove('pos-action-btn--active');
            btnSalesReturn.textContent = window.posSalesReturnBtnLabel('return');
        }
        syncPosSalesReturnBanner();
        focusPosBarcodeScan();
    }

    function armSalesReturnSticky() {
        if (_salesReturnTapTimer) {
            clearTimeout(_salesReturnTapTimer);
            _salesReturnTapTimer = null;
        }
        salesReturnEnabled = true;
        salesReturnOneShot = false;
        if (btnSalesReturn) {
            btnSalesReturn.classList.add('pos-action-btn--active');
            btnSalesReturn.textContent = window.posSalesReturnBtnLabel('sales');
        }
        syncPosSalesReturnBanner();
        focusPosBarcodeScan();
    }

    function armSalesReturnOneShot() {
        if (_salesReturnTapTimer) {
            clearTimeout(_salesReturnTapTimer);
            _salesReturnTapTimer = null;
        }
        salesReturnEnabled = true;
        salesReturnOneShot = true;
        if (btnSalesReturn) {
            btnSalesReturn.classList.add('pos-action-btn--active');
            btnSalesReturn.textContent = window.posSalesReturnBtnLabel('sales');
        }
        syncPosSalesReturnBanner();
        focusPosBarcodeScan();
    }

    function finishOneShotSalesReturnAfterScan() {
        if (salesReturnEnabled && salesReturnOneShot) {
            exitSalesReturnMode();
        }
    }

    let _posCustTimer = null;
    let _posCustAbort = null;
    let _custPickerEmptyCacheAt = 0;
    let _custPickerEmptyCacheKey = '';
    let _custPickerEmptyCacheRows = /** @type {unknown[] | null} */ (null);
    const CUST_PICKER_EMPTY_CACHE_MS = 45 * 1000;

    /** @param {HTMLElement | null} tb */
    function renderPosCustomerPickerRows(tb, rows) {
        if (!tb) return;
        if (!rows.length) {
            tb.innerHTML = '<tr><td colspan="3">No customers found.</td></tr>';
            return;
        }
        tb.innerHTML = rows
            .map((raw) => {
                const c = normalizePickerCustomer(raw);
                const code = c.code;
                const name = c.name;
                const phone = c.phone;
                const cl = c.creditLimit;
                const os = c.outstandingCash;
                const pts = c.totalPoints;
                const cno = c.cardNo;
                return (
                    `<tr class="customer-row" data-code="${escapeHtmlPos(code)}" data-name="${escapeHtmlPos(name)}" data-phone="${escapeHtmlPos(phone)}" data-credit-limit="${escapeHtmlPos(String(cl))}" data-outstanding-cash="${escapeHtmlPos(String(os))}" data-total-points="${escapeHtmlPos(String(pts))}" data-card-no="${escapeHtmlPos(String(cno))}">`
                    + `<td style="padding:8px;">${escapeHtmlPos(code)}</td>`
                    + `<td style="padding:8px;">${escapeHtmlPos(name || '-')}</td>`
                    + `<td style="padding:8px;">${escapeHtmlPos(phone || '-')}</td></tr>`
                );
            })
            .join('');
    }
    /** @type {'billing'|'loyalty'} */
    let posCustomerPickTarget = 'billing';
    let _posBarcodeTimer = null;
    let _posBarcodeAbort = null;
    const _posItemLookupCache = new Map();
    let pendingBarcodeLookupLine = null;
    let pendingBarcodeQtyPosting = false;
    /** @type {unknown[] | null} Holds latest AI screenshot API ``results`` until user confirms drawer. */
    let pendingAiScreenshotResults = null;
    /** @type {null | ((rows: unknown[]) => void)} Set when AI drawer markup is bound. */
    let posAiScreenshotDrawerOpen = null;
    /** @type {null | (() => boolean)} Reopen closed AI preview drawer without re-fetching. */
    let reopenPosAiScreenshotPreviewFn = null;
    let lastReceiptPreviewData = null;
    let lastReceiptPreviewText = '';

    function escapeHtmlPos(s) {
        return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }

    const DEFAULT_CHECKOUT_TENDERS = [
        { tender_code: 'CASH', tender_name: 'Cash', category: 'Cash', sort_order: 10, icon_key: 'cash' },
        { tender_code: 'CARD', tender_name: 'Card', category: 'Card', sort_order: 20, icon_key: 'card' },
        { tender_code: 'LOYALTY', tender_name: 'Loyalty points', category: 'Wallet', sort_order: 60, icon_key: 'loyalty' },
        { tender_code: 'POINTS', tender_name: 'Points amount', category: 'Wallet', sort_order: 61, icon_key: 'points' },
    ];

    const TENDER_ICON_BI = {
        cash: 'bi-cash-coin',
        card: 'bi-credit-card',
        visa: 'bi-credit-card-2-front',
        mc: 'bi-credit-card-2-front',
        voucher: 'bi-ticket-perforated',
        wallet: 'bi-wallet2',
        credit: 'bi-journal-text',
        loyalty: 'bi-star-fill',
        points: 'bi-asterisk',
        generic: 'bi-wallet2',
    };

    function resolveTenderIconKey(t) {
        const ik = String(t?.icon_key || '').trim().toLowerCase();
        if (ik && TENDER_ICON_BI[ik]) return ik;
        const cat = String(t?.category || '').trim().toLowerCase();
        if (cat === 'cash') return 'cash';
        if (cat === 'card') return 'card';
        if (cat === 'wallet') return 'wallet';
        if (cat === 'voucher') return 'voucher';
        if (cat === 'credit') return 'credit';
        const code = String(t?.tender_code || '').trim().toLowerCase();
        if (code === 'cash') return 'cash';
        if (code === 'card' || code === 'visa' || code === 'mc') return code === 'visa' || code === 'mc' ? code : 'card';
        if (code === 'loyalty') return 'loyalty';
        if (code === 'points') return 'points';
        if (code === 'wallet') return 'wallet';
        if (code === 'voucher') return 'voucher';
        return 'generic';
    }

    function tenderIconHtml(t) {
        const ik = resolveTenderIconKey(t);
        const bi = TENDER_ICON_BI[ik] || TENDER_ICON_BI.generic;
        return (
            '<span class="method-icon method-icon--' +
            escapeHtmlPos(ik) +
            '" aria-hidden="true"><i class="bi ' +
            bi +
            '"></i></span>'
        );
    }

    function getPaymentMethodListRoot() {
        return document.getElementById('paymentMethodList');
    }

    /** Accept tender rows from JSON with lowercase or uppercase keys (Oracle-style). */
    function normalizeCheckoutTendersFromApi(rawList) {
        const out = [];
        for (const raw of rawList || []) {
            if (!raw || typeof raw !== 'object') continue;
            const o = /** @type {Record<string, unknown>} */ (raw);
            const code = String(o.tender_code ?? o.TENDER_CODE ?? '').trim().toUpperCase();
            if (!code) continue;
            const name = String(o.tender_name ?? o.TENDER_NAME ?? code).trim();
            const category = String(o.category ?? o.CATEGORY ?? '').trim();
            const icon_key = String(o.icon_key ?? o.ICON_KEY ?? '').trim().toLowerCase();
            let sort_order = 0;
            try {
                sort_order = Number(o.sort_order ?? o.SORT_ORDER ?? 0);
            } catch (_e) {
                sort_order = 0;
            }
            out.push({
                tender_code: code,
                tender_name: name || code,
                category,
                icon_key,
                sort_order: Number.isFinite(sort_order) ? sort_order : 0,
            });
        }
        out.sort(
            (a, b) =>
                (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0) ||
                String(a.tender_code || '').localeCompare(String(b.tender_code || '')),
        );
        return out;
    }
    /** @type {{ tender_code?: string, tender_name?: string, category?: string, sort_order?: number }[]} */
    let checkoutTenders = [];
    /** @type {Promise<void> | null} */
    let checkoutTendersLoadPromise = null;
    let primaryRemainderCode = 'CARD';
    let zeroOnSelectCashCode = 'CASH';
    /** @type {HTMLInputElement | null} */
    let selectedPaymentInput = null;

    function posPayInputId(code) {
        return 'pay_t_' + String(code || '').toUpperCase();
    }

    function assignPrimaryRemainderAndCashDefaults() {
        const cards = checkoutTenders
            .filter(t => String(t.category || '').toUpperCase() === 'CARD')
            .sort((a, b) => (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0));
        const cardExact = cards.find(t => String(t.tender_code || '').toUpperCase() === 'CARD');
        primaryRemainderCode = String((cardExact || cards[0])?.tender_code || 'CARD').toUpperCase();
        const cashRows = checkoutTenders
            .filter(t => {
                const c = String(t.category || '').toUpperCase();
                const cd = String(t.tender_code || '').toUpperCase();
                return c === 'CASH' || cd === 'CASH';
            })
            .sort((a, b) => (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0));
        const cashExact = cashRows.find(t => String(t.tender_code || '').toUpperCase() === 'CASH');
        zeroOnSelectCashCode = String((cashExact || cashRows[0])?.tender_code || 'CASH').toUpperCase();
    }

    function renderCheckoutPaymentRows() {
        const paymentMethodListEl = getPaymentMethodListRoot();
        if (!paymentMethodListEl) return;
        if (!checkoutTenders.length) {
            checkoutTenders = DEFAULT_CHECKOUT_TENDERS.slice();
            assignPrimaryRemainderAndCashDefaults();
        }
        paymentMethodListEl.innerHTML = checkoutTenders
            .map(t => {
                const code = String(t.tender_code || '').trim().toUpperCase();
                const name = escapeHtmlPos(String(t.tender_name || code));
                const method = code.toLowerCase();
                const cat = String(t.category || '').trim().toLowerCase();
                const tid = posPayInputId(code);
                return (
                    '<div class="payment-method-row" data-tender-code="' +
                    escapeHtmlPos(code) +
                    '" data-method="' +
                    escapeHtmlPos(method) +
                    '" data-category="' +
                    escapeHtmlPos(cat) +
                    '"><span class="method-label">' +
                    tenderIconHtml(t) +
                    '<span class="method-name">' +
                    name +
                    '</span></span><input type="text" id="' +
                    tid +
                    '" class="amount-input" readonly inputmode="none" autocomplete="off" value="0" placeholder="0.00" /></div>'
                );
            })
            .join('');
        bindCheckoutPaymentRowsAndInputs();
    }

    function bindCheckoutPaymentRowsAndInputs() {
        const paymentMethodListEl = getPaymentMethodListRoot();
        if (!paymentMethodListEl) return;
        paymentMethodListEl.querySelectorAll('.payment-method-row').forEach(row => {
            row.addEventListener('click', () => {
                paymentMethodListEl.querySelectorAll('.payment-method-row').forEach(r => r.classList.remove('selected'));
                row.classList.add('selected');
                const code = String(row.getAttribute('data-tender-code') || '').toUpperCase();
                const input =
                    row.querySelector('.amount-input') || document.getElementById(posPayInputId(code));
                if (code === zeroOnSelectCashCode && input) {
                    input.value = '0';
                } else if (code === primaryRemainderCode && input) {
                    const netTotal = parseFloat(checkoutNetTotalEl?.value || '0') || 0;
                    let sumOthers = 0;
                    for (const t of checkoutTenders) {
                        const tc = String(t.tender_code || '').toUpperCase();
                        if (tc === code) continue;
                        const el = document.getElementById(posPayInputId(tc));
                        sumOthers += parseFloat(el?.value || '0') || 0;
                    }
                    input.value = formatNum(Math.max(0, netTotal - sumOthers));
                }
                selectedPaymentInput = input;
                updateCheckoutTotals();
            });
        });
        paymentMethodListEl.querySelectorAll('.amount-input').forEach(el => {
            el.addEventListener('paste', e => e.preventDefault());
            el.addEventListener('drop', e => e.preventDefault());
            el.addEventListener('input', updateCheckoutTotals);
        });
    }

    function resetAllCheckoutPaymentInputs() {
        for (const t of checkoutTenders) {
            const el = document.getElementById(posPayInputId(t.tender_code));
            if (el) setValue(el, '0');
        }
    }

    function selectDefaultCheckoutPaymentRow() {
        const paymentMethodListEl = getPaymentMethodListRoot();
        if (!paymentMethodListEl) return;
        const rows = paymentMethodListEl.querySelectorAll('.payment-method-row');
        if (!rows.length) return;
        rows.forEach(r => r.classList.remove('selected'));
        const pref = paymentMethodListEl.querySelector(
            '.payment-method-row[data-tender-code="' + zeroOnSelectCashCode + '"]',
        );
        const row = pref || rows[0];
        row.classList.add('selected');
        selectedPaymentInput = row.querySelector('.amount-input');
    }

    function getPaymentAmountsFromDom() {
        /** @type {Record<string, number>} */
        const m = {};
        for (const t of checkoutTenders) {
            const code = String(t.tender_code || '').toUpperCase();
            const el = document.getElementById(posPayInputId(code));
            m[code] = parseFloat(el?.value || '0') || 0;
        }
        return m;
    }

    function totalPaidFromAmountMap(m) {
        let s = 0;
        for (const v of Object.values(m)) s += v;
        return s;
    }

    /**
     * @param {Record<string, number> | { cash?: number, card?: number, loyalty?: number, points?: number } | null} paymentOverride
     * @returns {Record<string, number>}
     */
    function resolvePaymentAmountMap(paymentOverride) {
        if (paymentOverride != null && typeof paymentOverride === 'object') {
            const po = /** @type {Record<string, unknown>} */ (paymentOverride);
            if (
                'cash' in po ||
                'card' in po ||
                'loyalty' in po ||
                'points' in po
            ) {
                return {
                    CASH: Number(po.cash) || 0,
                    CARD: Number(po.card) || 0,
                    LOYALTY: Number(po.loyalty) || 0,
                    POINTS: Number(po.points) || 0,
                };
            }
            /** @type {Record<string, number>} */
            const out = {};
            for (const [k, v] of Object.entries(po)) {
                out[String(k).toUpperCase()] = Number(v) || 0;
            }
            return out;
        }
        return getPaymentAmountsFromDom();
    }

    function tenderDisplayName(code) {
        const u = String(code || '').toUpperCase();
        const t = checkoutTenders.find(x => String(x.tender_code || '').toUpperCase() === u);
        return t && t.tender_name ? String(t.tender_name) : u;
    }

    /** @param {Record<string, number>} amountsMap */
    function aggregateLegacyBuckets(amountsMap) {
        const metaByCode = Object.fromEntries(
            checkoutTenders.map(t => [String(t.tender_code || '').toUpperCase(), t]),
        );
        let cash = 0;
        let card = 0;
        let wallet = 0;
        let loyalty = 0;
        let points = 0;
        for (const [code, amt] of Object.entries(amountsMap)) {
            if (amt < 0.01) continue;
            const cd = code.toUpperCase();
            const t = metaByCode[cd];
            const cat = String(t?.category || '').toUpperCase();
            if (cd === 'LOYALTY') loyalty += amt;
            else if (cd === 'POINTS') points += amt;
            else if (cat === 'CASH' || cd === 'CASH') cash += amt;
            else if (cat === 'CARD') card += amt;
            else if (cat === 'WALLET') wallet += amt;
            else if (cat === 'VOUCHER') wallet += amt;
            else wallet += amt;
        }
        return { cash, card, wallet, loyalty, points };
    }

    function isCashCategoryTenderCode(code) {
        const cd = String(code || '').toUpperCase();
        if (cd === 'CASH') return true;
        const t = checkoutTenders.find(x => String(x.tender_code || '').toUpperCase() === cd);
        return String(t?.category || '').toUpperCase() === 'CASH';
    }

    /** Deduct change from cash tenders only — net cash kept in drawer is what gets saved. */
    function netAmountsMapAfterChange(amountsMap, changeDue) {
        const out = {};
        for (const [code, amt] of Object.entries(amountsMap || {})) {
            const v = Number(amt) || 0;
            if (v >= 0.01) out[String(code).toUpperCase()] = v;
        }
        let remaining = Math.max(0, Number(changeDue) || 0);
        if (remaining < 0.005) return out;

        const cashCodes = Object.keys(out)
            .filter(isCashCategoryTenderCode)
            .sort((a, b) => (a === 'CASH' ? -1 : b === 'CASH' ? 1 : a.localeCompare(b)));
        for (const code of cashCodes) {
            if (remaining < 0.005) break;
            const amt = out[code] || 0;
            if (amt < 0.01) continue;
            const deduct = Math.min(amt, remaining);
            const net = Math.round((amt - deduct) * 100) / 100;
            if (net >= 0.01) out[code] = net;
            else delete out[code];
            remaining = Math.round((remaining - deduct) * 100) / 100;
        }
        return out;
    }

    checkoutTenders = DEFAULT_CHECKOUT_TENDERS.slice();
    assignPrimaryRemainderAndCashDefaults();
    renderCheckoutPaymentRows();

    checkoutTendersLoadPromise = (async () => {
        try {
            const root = getPaymentMethodListRoot();
            const url = (root?.dataset?.checkoutTendersUrl || '').trim();
            let rows = DEFAULT_CHECKOUT_TENDERS.slice();
            if (url) {
                const res = await fetch(url, { credentials: 'same-origin' });
                const data = await res.json().catch(() => ({}));
                if (data.success && Array.isArray(data.tenders)) {
                    const normalized = normalizeCheckoutTendersFromApi(data.tenders);
                    if (normalized.length) {
                        rows = normalized;
                    }
                }
            }
            checkoutTenders = rows;
            assignPrimaryRemainderAndCashDefaults();
            renderCheckoutPaymentRows();
        } catch (_e) {
            checkoutTenders = DEFAULT_CHECKOUT_TENDERS.slice();
            assignPrimaryRemainderAndCashDefaults();
            renderCheckoutPaymentRows();
        }
    })();

    function normalizePickerCustomer(c) {
        const code = String(c.code ?? c.CODE ?? '').trim();
        const name = String(c.name ?? c.NAME ?? '').trim();
        const phone = String(c.phone ?? c.PHONE ?? '').trim();
        const creditLimit = Number(c.creditlimit ?? c.CREDITLIMIT ?? 0);
        const outstandingCash = Number(c.outstandingcash ?? c.OUTSTANDINGCASH ?? 0);
        const totalPoints = Number(c.totalpoints ?? c.TOTALPOINTS ?? 0);
        const cardNo = Number(c.cardno ?? c.CARDNO ?? 0);
        return {
            code,
            name,
            phone,
            creditLimit: Number.isFinite(creditLimit) ? creditLimit : 0,
            outstandingCash: Number.isFinite(outstandingCash) ? outstandingCash : 0,
            totalPoints: Number.isFinite(totalPoints) ? totalPoints : 0,
            cardNo: Number.isFinite(cardNo) ? cardNo : 0,
        };
    }

    function clearBillingCustomerMetrics() {
        billingCustomerCreditLimit = null;
        billingCustomerOutstanding = null;
        if (customerCreditLimitDisplay) {
            customerCreditLimitDisplay.textContent = '—';
            customerCreditLimitDisplay.classList.remove('pos-customer-metric__value--over-limit');
        }
        if (customerOutstandingDisplay) {
            customerOutstandingDisplay.textContent = '—';
            customerOutstandingDisplay.classList.remove('pos-customer-metric__value--warn');
            customerOutstandingDisplay.classList.remove('pos-customer-metric__value--over-limit');
        }
        syncBillingCustomerCreditWarn(0);
    }

    function setBillingCustomerMetrics(creditLimit, outstandingCash) {
        const cl = Number(creditLimit);
        const os = Number(outstandingCash);
        billingCustomerCreditLimit = Number.isFinite(cl) ? cl : null;
        billingCustomerOutstanding = Number.isFinite(os) ? os : null;
        if (customerCreditLimitDisplay) {
            customerCreditLimitDisplay.textContent = Number.isFinite(cl) ? formatNum(cl, 2) : '—';
        }
        if (customerOutstandingDisplay) {
            const okOs = Number.isFinite(os);
            customerOutstandingDisplay.textContent = okOs ? formatNum(os, 2) : '—';
            customerOutstandingDisplay.classList.toggle('pos-customer-metric__value--warn', okOs && Math.abs(os) > 1e-6);
        }
        syncBillingCustomerCreditWarn(getNetTotal());
    }

    function billingCustomerCreditLimitCheck(netTotal) {
        if (!billingCustomerSelected()) {
            return { exceeded: false, message: '' };
        }
        const limit = billingCustomerCreditLimit;
        const outstanding = Number.isFinite(billingCustomerOutstanding) ? billingCustomerOutstanding : 0;
        const net = Number(netTotal);
        const billDelta = Number.isFinite(net) ? net : 0;
        if (!Number.isFinite(limit) || limit <= 0) {
            return { exceeded: false, message: '' };
        }
        const newCredit = outstanding + billDelta;
        if (newCredit > limit + 0.009) {
            const msg =
                'Credit limit exceeded. Limit ' +
                formatNum(limit, 2) +
                ', outstanding ' +
                formatNum(outstanding, 2) +
                ', this bill ' +
                (billDelta >= 0 ? '+' : '') +
                formatNum(billDelta, 2) +
                '.';
            return { exceeded: true, message: msg };
        }
        return { exceeded: false, message: '' };
    }

    function syncBillingCustomerCreditWarn(netTotal) {
        const net = Number.isFinite(Number(netTotal)) ? Number(netTotal) : getNetTotal();
        const chk = billingCustomerCreditLimitCheck(net);
        if (customerCreditLimitDisplay) {
            customerCreditLimitDisplay.classList.toggle('pos-customer-metric__value--over-limit', chk.exceeded);
        }
        if (customerOutstandingDisplay) {
            customerOutstandingDisplay.classList.toggle('pos-customer-metric__value--over-limit', chk.exceeded);
        }
        if (customerCreditLimitWarn) {
            if (!billingCustomerSelected()) {
                customerCreditLimitWarn.hidden = true;
                customerCreditLimitWarn.textContent = '';
                return;
            }
            if (chk.exceeded) {
                customerCreditLimitWarn.hidden = false;
                customerCreditLimitWarn.textContent = chk.message + ' Validate is blocked until within limit.';
                customerCreditLimitWarn.classList.add('pos-customer-credit-warn--blocked');
                return;
            }
            const limit = billingCustomerCreditLimit;
            const outstanding = Number.isFinite(billingCustomerOutstanding) ? billingCustomerOutstanding : 0;
            if (Number.isFinite(limit) && limit > 0) {
                const remaining = limit - outstanding - net;
                customerCreditLimitWarn.hidden = false;
                customerCreditLimitWarn.textContent =
                    'Available credit after this bill: ' + formatNum(Math.max(0, remaining), 2) + '.';
                customerCreditLimitWarn.classList.remove('pos-customer-credit-warn--blocked');
            } else {
                customerCreditLimitWarn.hidden = true;
                customerCreditLimitWarn.textContent = '';
            }
        }
    }

    async function verifyCreditSaleAllowed(netTotal) {
        if (!billingCustomerSelected()) {
            return { ok: true };
        }
        const local = billingCustomerCreditLimitCheck(netTotal);
        if (local.exceeded) {
            return { ok: false, message: local.message };
        }
        let cc = 0;
        try {
            cc = parseInt(String(customerCode?.value || '').trim(), 10);
        } catch (_e) {
            cc = 0;
        }
        if (!Number.isFinite(cc) || cc <= 0) {
            return { ok: true };
        }
        try {
            const res = await fetch('/pos-billing/credit-sale-precheck', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    customercode: cc,
                    net_total: netTotal,
                    proposed_credit_delta: netTotal,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!data.success) {
                return { ok: false, message: data.error || 'Credit check failed.' };
            }
            if (data.accounts_ok === false) {
                return { ok: false, message: data.detail || 'Credit sale cannot post to accounts.' };
            }
            return { ok: true };
        } catch (_e) {
            return { ok: false, message: 'Could not verify credit limit. Try again.' };
        }
    }

    function clearLoyaltyPointsMetric() {
        if (loyaltyPointsDisplay) loyaltyPointsDisplay.textContent = '—';
        syncPosDdTotalPointsBar();
    }

    function clearLoyaltyCardNoMetric() {
        if (loyaltyCardnoDisplay) loyaltyCardnoDisplay.textContent = '—';
    }

    function setLoyaltyPointsMetric(totalPoints) {
        if (!loyaltyPointsDisplay) return;
        const n = Number(totalPoints);
        if (!Number.isFinite(n)) {
            loyaltyPointsDisplay.textContent = '—';
            syncPosDdTotalPointsBar();
            return;
        }
        loyaltyPointsDisplay.textContent = Math.abs(n - Math.round(n)) < 1e-9 ? String(Math.round(n)) : formatNum(n, 2);
        syncPosDdTotalPointsBar();
    }

    function setLoyaltyCardNoMetric(cardNo) {
        if (!loyaltyCardnoDisplay) return;
        if (cardNo === null || cardNo === undefined || cardNo === '') {
            loyaltyCardnoDisplay.textContent = '—';
            return;
        }
        const n = Number(cardNo);
        loyaltyCardnoDisplay.textContent = Number.isFinite(n) ? String(Math.round(n)) : '—';
    }

    async function refreshCustomerMetricsFromApi(customerCodeStr, mode) {
        const raw = (customerCodeStr || '').trim();
        const regularUrl = window.__POS_CUSTOMERS_PICKER__;
        const loyaltyUrl = window.__POS_LOYALTY_CUSTOMERS_PICKER__;
        const urlBase =
            mode === 'loyalty' && loyaltyUrl ? loyaltyUrl : regularUrl;
        if (!raw || !urlBase) return;
        try {
            const u = `${urlBase}?q=${encodeURIComponent(raw)}&limit=80`;
            const res = await fetch(u, { credentials: 'same-origin' });
            const data = await res.json();
            if (!data.success) return;
            const rows = (data.customers || []).map(normalizePickerCustomer);
            const hit = rows.find((r) => r.code === raw) || rows.find((r) => r.code === String(Number(raw)));
            if (!hit) return;
            if (mode === 'loyalty') {
                setLoyaltyPointsMetric(hit.totalPoints);
                setLoyaltyCardNoMetric(hit.cardNo);
            } else {
                setBillingCustomerMetrics(hit.creditLimit, hit.outstandingCash);
            }
            renderCart();
        } catch (e) {
            /* ignore */
        }
    }

    function clearLoyaltyCustomerUi() {
        if (loyaltyCustomerDisplay) loyaltyCustomerDisplay.textContent = '';
        setValue(loyaltyCustomerCode, '');
        clearLoyaltyPointsMetric();
        clearLoyaltyCardNoMetric();
        renderCart();
    }

    function loadPosCustomerPicker(term) {
        const tb = customerModalBody;
        const regularUrl = window.__POS_CUSTOMERS_PICKER__;
        const loyaltyUrl = window.__POS_LOYALTY_CUSTOMERS_PICKER__;
        const urlBase =
            posCustomerPickTarget === 'loyalty' && loyaltyUrl ? loyaltyUrl : regularUrl;
        if (!tb || !urlBase) return;
        const q = String(term || '').trim();
        const emptyQ = q === '';
        const limit = emptyQ ? 120 : 300;

        if (
            emptyQ &&
            _custPickerEmptyCacheRows != null &&
            _custPickerEmptyCacheKey === urlBase &&
            Date.now() - _custPickerEmptyCacheAt < CUST_PICKER_EMPTY_CACHE_MS
        ) {
            renderPosCustomerPickerRows(tb, _custPickerEmptyCacheRows);
            return;
        }

        if (_posCustAbort) _posCustAbort.abort();
        _posCustAbort = new AbortController();
        const u = `${urlBase}?q=${encodeURIComponent(q)}&limit=${limit}`;
        tb.innerHTML = '<tr><td colspan="3">Loading…</td></tr>';
        fetch(u, { credentials: 'same-origin', signal: _posCustAbort.signal })
            .then((r) => r.json())
            .then((data) => {
                if (!data.success) throw new Error(data.error || 'Failed');
                const rows = data.customers || [];
                if (emptyQ) {
                    _custPickerEmptyCacheKey = urlBase;
                    _custPickerEmptyCacheAt = Date.now();
                    _custPickerEmptyCacheRows = rows;
                }
                renderPosCustomerPickerRows(tb, rows);
            })
            .catch((err) => {
                if (err.name === 'AbortError') return;
                tb.innerHTML = `<tr><td colspan="3">${escapeHtmlPos(err.message)}</td></tr>`;
            });
    }

    function schedulePosCustomerPicker(term) {
        clearTimeout(_posCustTimer);
        _posCustTimer = setTimeout(() => loadPosCustomerPicker(term), 280);
    }

    function loadBarcodeLookup(term) {
        const tb = barcodeLookupBody;
        const urlBase = window.__POS_BARCODE_ITEMS__;
        if (!tb || !urlBase) return;
        if (_posBarcodeAbort) _posBarcodeAbort.abort();
        _posBarcodeAbort = new AbortController();
        const u = `${urlBase}?search=${encodeURIComponent(term || '')}`;
        const colSpan = barcodeLookupColSpan();
        tb.innerHTML = `<tr><td colspan="${colSpan}">Loading…</td></tr>`;
        fetch(u, { credentials: 'same-origin', signal: _posBarcodeAbort.signal })
            .then((r) => r.json())
            .then((data) => {
                if (!data.success) throw new Error(data.error || 'Failed');
                const rows = data.items || [];
                if (!rows.length) {
                    tb.innerHTML = `<tr><td colspan="${colSpan}">No items found.</td></tr>`;
                    return;
                }
                tb.innerHTML = rows.map((it) => {
                    const query = String(it.query ?? it.barcode ?? it.itemcode ?? '');
                    const barcode = String(it.barcode ?? '');
                    const itemCode = String(it.itemcode ?? '');
                    const itemName = String(it.itemname ?? '');
                    const uom = String(it.uom ?? 'PCS');
                    const price = Number(it.price || 0);
                    const cost = Number(it.cost || 0);
                    const costprice = Number((it.costprice ?? it.cost) || 0);
                    const averagecost = Number(it.averagecost ?? it.average_cost ?? 0);
                    const itemFactor = Number((it.item_factor ?? it.conversion_factor) ?? 1) || 1;
                    const unitCost = costprice > 0 ? costprice : (cost > 0 ? cost : averagecost);
                    return (
                        `<tr class="barcode-item-row" tabindex="0" data-query="${escapeHtmlPos(query)}" data-barcode="${escapeHtmlPos(barcode)}" data-item-code="${escapeHtmlPos(itemCode)}" data-item-name="${escapeHtmlPos(itemName)}" data-uom="${escapeHtmlPos(uom)}" data-price="${escapeHtmlPos(price)}" data-cost="${escapeHtmlPos(cost)}" data-costprice="${escapeHtmlPos(costprice)}" data-averagecost="${escapeHtmlPos(averagecost)}" data-item-factor="${escapeHtmlPos(itemFactor)}">`
                        + `<td>${escapeHtmlPos(barcode || itemCode)}</td>`
                        + `<td>${escapeHtmlPos(itemName || '-')}</td>`
                        + `<td>${escapeHtmlPos(uom || '-')}</td>`
                        + `<td class="num pos-cost-col">${formatNum(unitCost)}</td>`
                        + `<td class="num">${formatNum(price)}</td></tr>`
                    );
                }).join('');
            })
            .catch((err) => {
                if (err.name === 'AbortError') return;
                tb.innerHTML = `<tr><td colspan="${barcodeLookupColSpan()}">${escapeHtmlPos(err.message)}</td></tr>`;
            });
    }

    function scheduleBarcodeLookup(term) {
        clearTimeout(_posBarcodeTimer);
        _posBarcodeTimer = setTimeout(() => loadBarcodeLookup(term), 220);
    }

    function openBarcodeLookupFromScan() {
        if (!barcodeLookupModal) {
            showPosMessagePopup('Barcode lookup', 'Barcode lookup popup is not available on this page.');
            return;
        }
        openModal('barcodeLookupModal');
    }
    window.openPosBarcodeLookup = openBarcodeLookupFromScan;

    function setValue(el, value) {
        if (!el) return;
        el.value = value == null ? '' : value;
    }

    function formatNum(v, d = 2) {
        const n = Number(v);
        return (Number.isNaN(n) ? 0 : n).toFixed(d);
    }

    function isPosShowCostEnabled() {
        const api = window.__posBillingShowCost;
        if (api && typeof api.isEnabled === 'function') return api.isEnabled();
        try {
            return localStorage.getItem('nexa-pos-show-cost') === '1';
        } catch (_e) {
            return false;
        }
    }

    function barcodeLookupColSpan() {
        return isPosShowCostEnabled() ? 5 : 4;
    }

    function scrollCartToLatestLine() {
        if (!posOrderList) return;
        requestAnimationFrame(() => {
            posOrderList.scrollTop = posOrderList.scrollHeight;
            const rows = posOrderList.querySelectorAll('.pos-order-line');
            const last = rows.length ? rows[rows.length - 1] : null;
            if (last) last.scrollIntoView({ block: 'end', inline: 'nearest' });
        });
    }

    function showValidateOverlay(message) {
        if (posValidateOverlayLabel) posValidateOverlayLabel.textContent = message || 'Validating bill...';
        if (!posValidateOverlay) return;
        posValidateOverlay.classList.remove('hidden');
        posValidateOverlay.setAttribute('aria-hidden', 'false');
    }

    function hideValidateOverlay() {
        if (!posValidateOverlay) return;
        posValidateOverlay.classList.add('hidden');
        posValidateOverlay.setAttribute('aria-hidden', 'true');
    }

    /** Enable checkout phase timings: `?posCheckoutTiming=1`, `localStorage.pos_checkout_timing = '1'`, or `window.__POS_CHECKOUT_TIMING__ = true`. */
    function posCheckoutTimingEnabled() {
        try {
            if (window.__POS_CHECKOUT_TIMING__ === true) return true;
            if (typeof localStorage !== 'undefined' && localStorage.getItem('pos_checkout_timing') === '1') return true;
            const sp = typeof URLSearchParams !== 'undefined' ? new URLSearchParams(window.location.search || '') : null;
            if (sp && sp.get('posCheckoutTiming') === '1') return true;
        } catch (err) {
            /* ignore */
        }
        return false;
    }

    function onReceiptSaved(data) {
        if (!data || !data.receipt) return;
        if (data.receipt_printed) {
            return;
        }
        if (data.receipt_print_error) {
            console.warn('Receipt print failed:', data.receipt_print_error);
        }
    }

    function receiptPreviewLine(left, right, width = 42) {
        const l = String(left ?? '');
        const r = String(right ?? '');
        const gap = Math.max(1, width - l.length - r.length);
        return l + ' '.repeat(gap) + r;
    }

    function receiptPreviewCenter(text, width = 42) {
        const s = String(text ?? '').slice(0, width);
        const pad = Math.max(0, width - s.length);
        return ' '.repeat(Math.floor(pad / 2)) + s + ' '.repeat(Math.ceil(pad / 2));
    }

    function receiptBranchLogoUrl(receipt) {
        if (!receipt) return '';
        const loc = receipt.location_details || {};
        let rel = String(loc.logo_url || loc.logo_path || '').trim();
        if (!rel) return '';
        if (/^https?:\/\//i.test(rel)) return rel;
        const path = rel.startsWith('/') ? rel : '/static/' + rel.replace(/^\/+/, '');
        return window.location.origin + path;
    }

    function buildReceiptPreviewText(receipt) {
        if (!receipt) return 'No receipt preview.';
        const loc = receipt.location_details || {};
        const lines = receipt.lines || [];
        const footer = receipt.footer || {};
        const out = [];
        if (loc.locationname) out.push(receiptPreviewCenter(loc.locationname));
        const tel = String(loc.telephone || loc.phone || loc.tel || '').trim();
        if (tel) out.push(receiptPreviewCenter('Telephone : ' + tel));
        out.push(receiptPreviewLine('BILL # ' + (receipt.receiptno || ''), receipt.billdate || ''));
        if (receipt.billtime) out.push(receipt.billtime);
        if (receipt.countername || receipt.countercode) out.push('Counter: ' + (receipt.countername || receipt.countercode || ''));
        if (receipt.customername) out.push('Customer: ' + receipt.customername);
        out.push('-'.repeat(42));
        lines.forEach((line) => {
            const name = String(line.item || line.item_name || line.itemcode || '').trim();
            const bc = String(line.barcode || line.manufacturerid || '').trim();
            const qty = Number(line.qty || line.quantity || 0);
            const rate = Number(line.rate || 0);
            let disc = Number(
                line.disc != null ? line.disc : line.discount != null ? line.discount : line.itdisc != null ? line.itdisc : 0
            );
            if (!Number.isFinite(disc)) disc = 0;
            const amount = Number(line.amount != null ? line.amount : Math.max(0, qty * rate - disc));
            const sl = String(line.slno != null ? line.slno : '');
            const rowMain = receiptPreviewLine(
                `${sl}.`.slice(0, 6) + formatNum(qty, 3) + ' x ' + formatNum(rate),
                formatNum(amount)
            );
            out.push(rowMain.slice(0, 42));
            if (bc) {
                const wrapW = 42;
                let rest = bc;
                while (rest.length > 0) {
                    const chunk = rest.slice(0, wrapW);
                    rest = rest.slice(wrapW);
                    out.push(chunk);
                }
            }
            if (name) {
                let restName = name;
                while (restName.length > 0) {
                    out.push(('    ' + restName.slice(0, 38)).slice(0, 42));
                    restName = restName.slice(38);
                }
            }
            if (disc > 0.0005) {
                const gross = Math.abs(Number(qty) * Number(rate)) || Math.abs(Number(amount)) + Math.abs(Number(disc));
                const pctTxt =
                    gross > 1e-6 ? `${(Math.round((10000 * Math.abs(disc)) / gross) / 100).toFixed(1)}%` : '0.0%';
                out.push(`    Discount: ${formatNum(disc, 2)} (${pctTxt})`.slice(0, 42));
            }
        });
        out.push('-'.repeat(42));
        if (Number(footer.discount_total || 0)) out.push(receiptPreviewLine('Discount', formatNum(footer.discount_total)));
        out.push(receiptPreviewLine('NET TOTAL', formatNum(footer.net_total || 0)));
        if (footer.message) out.push(String(footer.message));
        return out.join('\n');
    }

    function isPosQzReceiptPreviewEnabled() {
        try {
            if (window.QzPrinterPrefs && typeof window.QzPrinterPrefs.getPosReceiptPreviewEnabled === 'function') {
                return window.QzPrinterPrefs.getPosReceiptPreviewEnabled();
            }
        } catch (e) {
            /* ignore */
        }
        return false;
    }

    function prepareReceiptPreviewState(receipt, receiptText) {
        lastReceiptPreviewData = receipt || null;
        lastReceiptPreviewText = receiptText || buildReceiptPreviewText(receipt);
    }

    /**
     * @returns {Promise<{ mode: string, qz_print_ms: number | null }>}
     */
    async function presentPosReceiptAfterSale(receipt, receiptText, queuedStatusText) {
        /* `.pos-validate-overlay` is z-index 10200; receipt modal must sit above or be hidden behind it. */
        hideValidateOverlay();
        if (isPosQzReceiptPreviewEnabled()) {
            showReceiptPreview(receipt, receiptText, queuedStatusText || '');
            return { mode: 'preview', qz_print_ms: null };
        }
        prepareReceiptPreviewState(receipt, receiptText);
        try {
            const qz0 = performance.now();
            await printReceiptPreviewViaQz();
            return { mode: 'qz_print', qz_print_ms: performance.now() - qz0 };
        } catch (e) {
            showPosMessagePopup('Print receipt', e.message || 'Print failed.');
            showReceiptPreview(receipt, receiptText, (queuedStatusText ? `${queuedStatusText} ` : '') + 'Tap Print to retry.');
            return { mode: 'qz_print_failed', qz_print_ms: null };
        }
    }

    function showReceiptPreview(receipt, receiptText, statusFooter = '') {
        prepareReceiptPreviewState(receipt, receiptText);
        const logoEl = document.getElementById('receiptPreviewLogo');
        const logoUrl = receiptBranchLogoUrl(receipt);
        if (logoEl) {
            if (logoUrl) {
                logoEl.src = logoUrl;
                logoEl.hidden = false;
            } else {
                logoEl.removeAttribute('src');
                logoEl.hidden = true;
            }
        }
        if (receiptPreviewText) receiptPreviewText.textContent = lastReceiptPreviewText;
        if (receiptPreviewStatus) receiptPreviewStatus.textContent = statusFooter != null ? String(statusFooter) : '';
        openModal('receiptPreviewModal');
        if (receiptPreviewModal) receiptPreviewModal.style.zIndex = '10004';
    }

    async function presentPosHoldCancelSlip(slipText, statusFooter = '') {
        const slip = String(slipText || '').trimEnd();
        if (!slip) return;
        prepareReceiptPreviewState(null, slip);
        if (isPosQzReceiptPreviewEnabled()) {
            showReceiptPreview(null, slip, statusFooter);
            return;
        }
        try {
            await printPosSlipText(slip);
        } catch (_e) {
            showReceiptPreview(null, slip, (statusFooter ? `${statusFooter} ` : '') + 'Tap Print to retry.');
        }
    }

    function escapeReceiptHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function escapeReceiptHtmlWithArabicFont(text) {
        let out = '';
        let inArabic = false;
        String(text || '').split('').forEach((ch) => {
            const isArabic = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/.test(ch);
            if (isArabic && !inArabic) {
                out += '<span class="ar">';
                inArabic = true;
            } else if (!isArabic && inArabic) {
                out += '</span>';
                inArabic = false;
            }
            out += escapeReceiptHtml(ch);
        });
        if (inArabic) out += '</span>';
        return out;
    }

    function buildReceiptHtml(text, logoUrl) {
        const logoBlock = logoUrl
            ? '<div class="logo-wrap"><img class="logo" src="' + escapeReceiptHtml(logoUrl) + '" alt=""></div>'
            : '';
        return '<!doctype html><html><head><meta charset="utf-8">'
            + '<style>@page{margin:0;}body{margin:0;padding:0;background:#fff;color:#000;display:flex;justify-content:center;}'
            + '.wrap{box-sizing:border-box;width:72mm;margin:0 auto;padding:2mm;}'
            + '.logo-wrap{text-align:center;margin:0 auto 2mm;}'
            + '.logo{max-width:60mm;max-height:20mm;height:auto;display:block;margin:0 auto;}'
            + 'pre{margin:0;font:11px Consolas,"Courier New",monospace;white-space:pre;unicode-bidi:plaintext;}'
            + '.ar{font-family:Tahoma,Arial,sans-serif;}</style>'
            + '</head><body><div class="wrap">' + logoBlock
            + '<pre>' + escapeReceiptHtmlWithArabicFont(text) + '</pre></div></body></html>';
    }

    function hasArabicText(text) {
        return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/.test(String(text || ''));
    }

    function indentRawReceipt(text) {
        const pad = '';
        return String(text || '')
            .split('\n')
            .map((line) => (line ? pad + line : ''))
            .join('\n');
    }

    async function printReceiptPreviewViaQz() {
        const text = String(lastReceiptPreviewText || '').trimEnd();
        if (!text) throw new Error('No receipt preview to print.');
        if (!window.SalesQzPrint || !window.SalesQzPrint.ensureQzSecurity) {
            throw new Error('QZ helper script not loaded.');
        }
        await window.SalesQzPrint.ensureQzSecurity(window.__POS_QZ_URLS__ || {});

        let printerName = '';
        try {
            if (window.QzPrinterPrefs && typeof window.QzPrinterPrefs.get === 'function') {
                printerName = String(window.QzPrinterPrefs.get('pos_receipt') || '').trim();
            }
        } catch (e) {
            printerName = '';
        }
        if (!printerName) {
            throw new Error('No POS receipt printer selected. Open Sales > Printer Setup, choose POS receipt printer, and Save.');
        }
        const config = qz.configs.create(printerName);
        const escInit = '\x1B@';
        const smallFont = '\x1BM\x01\x1B!\x01';
        const leftMargin = '\x1DL\x30\x00';
        const cut = '\x1DV\x01';
        const logoUrl = receiptBranchLogoUrl(lastReceiptPreviewData);
        const netForCopy = Number(lastReceiptPreviewData?.footer?.net_total);
        const copies = Number.isFinite(netForCopy) && netForCopy <= 0 ? 2 : 1;
        const printHtmlBatch = async (html) => {
            for (let c = 0; c < copies; c++) {
                await qz.print(config, [{ type: 'pixel', format: 'html', flavor: 'plain', data: html }]);
            }
        };
        const printRawBatch = async (rawData) => {
            for (let c = 0; c < copies; c++) {
                await qz.print(config, [{ type: 'raw', format: 'plain', data: rawData }]);
            }
        };
        if (logoUrl || hasArabicText(text)) {
            const html = buildReceiptHtml(text, logoUrl);
            await printHtmlBatch(html);
            return copies;
        }
        const raw = escInit + leftMargin + smallFont + indentRawReceipt(text) + '\n\n\n' + cut;
        try {
            await printRawBatch(raw);
        } catch (rawErr) {
            const html = buildReceiptHtml(text, logoUrl);
            await printHtmlBatch(html);
        }
        return copies;
    }

    async function printPosSlipText(text) {
        const slip = String(text || '').trimEnd();
        if (!slip) return;
        if (!window.SalesQzPrint || !window.SalesQzPrint.ensureQzSecurity) {
            return;
        }
        await window.SalesQzPrint.ensureQzSecurity(window.__POS_QZ_URLS__ || {});
        let printerName = '';
        try {
            if (window.QzPrinterPrefs && typeof window.QzPrinterPrefs.get === 'function') {
                printerName = String(window.QzPrinterPrefs.get('pos_receipt') || '').trim();
            }
        } catch (e) {
            printerName = '';
        }
        if (!printerName || !window.qz) return;
        const config = qz.configs.create(printerName);
        const escInit = '\x1B@';
        const smallFont = '\x1BM\x01\x1B!\x01';
        const leftMargin = '\x1DL\x30\x00';
        const cut = '\x1DV\x01';
        if (hasArabicText(slip)) {
            await qz.print(config, [{ type: 'pixel', format: 'html', flavor: 'plain', data: buildReceiptHtml(slip) }]);
            return;
        }
        const raw = escInit + leftMargin + smallFont + indentRawReceipt(slip) + '\n\n\n' + cut;
        try {
            await qz.print(config, [{ type: 'raw', format: 'plain', data: raw }]);
        } catch (rawErr) {
            await qz.print(config, [{ type: 'pixel', format: 'html', flavor: 'plain', data: buildReceiptHtml(slip) }]);
        }
    }

    function posCounterQuerySuffix() {
        const raw = (counterCodeEl?.value || '').trim();
        if (!raw) return '';
        const n = parseInt(raw, 10);
        if (!Number.isFinite(n)) return '';
        return `?countercode=${encodeURIComponent(String(n))}`;
    }

    function hidePosSetCounterModal() {
        const m = document.getElementById('posSetCounterModal');
        if (m) m.classList.add('hidden');
    }

    function applyPosWarehouseDisplay(code, name) {
        const el = document.getElementById('pos_warehouse_display');
        if (!el) return;
        const codeStr = String(code || '').trim();
        const nameStr = String(name || '').trim();
        const full = nameStr ? `${codeStr} — ${nameStr}` : (codeStr || '—');
        el.title = full;
        const fullSpan = el.querySelector('.pos-wh-full');
        const compactSpan = el.querySelector('.pos-wh-compact');
        if (fullSpan) fullSpan.textContent = full;
        if (compactSpan) compactSpan.textContent = codeStr || '—';
    }

    function posCounterWarehouseReadyFromPage() {
        const whCompact = document.querySelector('#pos_warehouse_display .pos-wh-compact');
        const whCode = whCompact ? String(whCompact.textContent || '').trim() : '';
        return Boolean(whCode && whCode !== '—');
    }

    async function bindPosCounterToSession(countercode, countername) {
        const bindUrl = typeof window.__POS_BIND_SESSION_COUNTER_URL__ === 'string' ? window.__POS_BIND_SESSION_COUNTER_URL__.trim() : '';
        if (!bindUrl || countercode == null || countercode === '') {
            return false;
        }
        try {
            const res = await fetch(bindUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ countercode, countername: countername || '' }),
            });
            const data = await res.json().catch(() => ({}));
            syncPosSaveNonceFromResponse(data);
            if (data && data.success === true) {
                applyPosWarehouseDisplay(data.warehouse_code, data.warehouse_name);
                return true;
            }
            return false;
        } catch (_e) {
            return false;
        }
    }

    let _posQzHostnamePromise = null;

    /** Connect to QZ once per page load (terminal lock + counter resolve both need PC name). */
    async function posQzHostnameOnce() {
        if (_posQzHostnamePromise) return _posQzHostnamePromise;
        _posQzHostnamePromise = (async () => {
            try {
                if (window.SalesQzPrint && window.SalesQzPrint.ensureQzSecurity && window.__POS_QZ_URLS__) {
                    await window.SalesQzPrint.ensureQzSecurity(window.__POS_QZ_URLS__);
                    if (window.qz && window.qz.networking && typeof window.qz.networking.hostname === 'function') {
                        return String((await window.qz.networking.hostname()) || '').trim();
                    }
                }
            } catch (_e) {
                /* QZ optional */
            }
            return '';
        })();
        return _posQzHostnamePromise;
    }

    async function collectPosTerminalHostnames() {
        const hostnames = [];
        const qzHn = await posQzHostnameOnce();
        if (qzHn) hostnames.push(qzHn);
        try {
            const lh = String(window.location.hostname || '').trim();
            if (
                lh &&
                lh !== 'localhost' &&
                lh !== '127.0.0.1' &&
                lh !== '[::1]' &&
                lh !== '::1'
            ) {
                hostnames.push(lh);
            }
        } catch (_e2) {
            /* ignore */
        }
        return dedupePosTerminalHostnames(hostnames);
    }

    function dedupePosTerminalHostnames(hostnames) {
        const seen = new Set();
        const uniq = [];
        for (let i = 0; i < hostnames.length; i += 1) {
            const h = String(hostnames[i] || '').trim();
            if (!h) continue;
            const k = h.replace(/\s+/g, '').toUpperCase();
            if (seen.has(k)) continue;
            seen.add(k);
            uniq.push(h);
        }
        return uniq;
    }

    function isPosTerminalIpv4Host(name) {
        return /^(?:\d{1,3}\.){3}\d{1,3}$/.test(String(name || '').trim());
    }

    /** Server lock uses PC name (QZ) only — not the app server IP in the browser URL. */
    async function collectPosTerminalLockHostnames() {
        const qzHn = await posQzHostnameOnce();
        if (!qzHn || isPosTerminalIpv4Host(qzHn)) {
            return [];
        }
        return dedupePosTerminalHostnames([qzHn]);
    }

    const POS_TERMINAL_TAB_ID_KEY = 'nexa-pos-billing-tab-id-v1';
    const POS_TERMINAL_LOCAL_LOCK_KEY = 'nexa-pos-billing-single-tab-v1';
    const POS_TERMINAL_LOCAL_STALE_MS = 90000;
    const POS_TERMINAL_HEARTBEAT_MS = 10000;
    const POS_TERMINAL_BC_NAME = 'nexa-pos-billing-leader-v1';
    const POS_TERMINAL_TAB_ID = (function posTerminalTabId() {
        try {
            let id = sessionStorage.getItem(POS_TERMINAL_TAB_ID_KEY);
            if (!id) {
                id =
                    typeof crypto !== 'undefined' && crypto.randomUUID
                        ? crypto.randomUUID()
                        : 'tab-' + String(Date.now()) + '-' + String(Math.random()).slice(2);
                sessionStorage.setItem(POS_TERMINAL_TAB_ID_KEY, id);
            }
            return id;
        } catch (_e) {
            return typeof crypto !== 'undefined' && crypto.randomUUID
                ? crypto.randomUUID()
                : 'tab-' + String(Date.now()) + '-' + String(Math.random()).slice(2);
        }
    })();
    let _posTerminalServerLockKey = '';
    let _posTerminalLockBlocked = false;
    let _posTerminalHeartbeatTimer = null;
    let _posTerminalAnnounceTimer = null;
    let _posTerminalAnnounceBc = null;
    let _posTerminalLockHooksBound = false;

    function posTerminalLeaderElection(tabId) {
        return new Promise((resolve) => {
            let peers = new Set();
            let bc = null;
            try {
                bc = new BroadcastChannel(POS_TERMINAL_BC_NAME);
            } catch (_e) {
                resolve(true);
                return;
            }
            const onMsg = (ev) => {
                const d = ev && ev.data;
                if (!d || d.type !== 'leader-claim' || !d.tabId) return;
                if (d.tabId !== tabId) peers.add(String(d.tabId));
            };
            bc.onmessage = onMsg;
            bc.postMessage({ type: 'leader-claim', tabId });
            setTimeout(() => {
                try {
                    bc.onmessage = null;
                    bc.close();
                } catch (_e2) {
                    /* ignore */
                }
                const ids = [tabId, ...Array.from(peers)].sort();
                resolve(ids.length > 0 && ids[0] === tabId);
            }, 320);
        });
    }

    function posTerminalLeaderAnnounceLoop(tabId) {
        if (_posTerminalAnnounceTimer) {
            clearInterval(_posTerminalAnnounceTimer);
            _posTerminalAnnounceTimer = null;
        }
        if (_posTerminalAnnounceBc) {
            try {
                _posTerminalAnnounceBc.close();
            } catch (_e0) {
                /* ignore */
            }
            _posTerminalAnnounceBc = null;
        }
        try {
            const bc = new BroadcastChannel(POS_TERMINAL_BC_NAME);
            _posTerminalAnnounceBc = bc;
            bc.onmessage = (ev) => {
                const d = ev && ev.data;
                if (!d || d.type !== 'leader-claim' || !d.tabId || d.tabId === tabId) return;
                // Do not block an already-running POS tab (e.g. left open for hours) when another
                // window opens — server + localStorage locks handle true duplicates.
                if (_posTerminalServerLockKey) return;
                const ids = [tabId, String(d.tabId)].sort();
                if (ids[0] !== tabId) showPosTerminalLockOverlay();
            };
            _posTerminalAnnounceTimer = setInterval(() => {
                try {
                    bc.postMessage({ type: 'leader-claim', tabId });
                } catch (_e) {
                    /* ignore */
                }
            }, 8000);
        } catch (_e) {
            /* ignore */
        }
    }

    function stopPosTerminalLeaderAnnounceLoop() {
        if (_posTerminalAnnounceTimer) {
            clearInterval(_posTerminalAnnounceTimer);
            _posTerminalAnnounceTimer = null;
        }
        if (_posTerminalAnnounceBc) {
            try {
                _posTerminalAnnounceBc.close();
            } catch (_e) {
                /* ignore */
            }
            _posTerminalAnnounceBc = null;
        }
    }

    function showPosTerminalLockOverlay() {
        _posTerminalLockBlocked = true;
        hidePosLoadOverlay();
        const ov = document.getElementById('posTerminalLockOverlay');
        if (ov) {
            ov.classList.remove('hidden');
            ov.setAttribute('aria-hidden', 'false');
        }
        document.body.classList.add('pos-terminal-locked');
    }

    function hidePosTerminalLockOverlay() {
        _posTerminalLockBlocked = false;
        const ov = document.getElementById('posTerminalLockOverlay');
        if (ov) {
            ov.classList.add('hidden');
            ov.setAttribute('aria-hidden', 'true');
        }
        document.body.classList.remove('pos-terminal-locked');
    }

    function readPosTerminalLocalLock() {
        try {
            const raw = localStorage.getItem(POS_TERMINAL_LOCAL_LOCK_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object') return null;
            return parsed;
        } catch (_e) {
            return null;
        }
    }

    function clearStalePosTerminalLocalLock() {
        const lock = readPosTerminalLocalLock();
        if (!lock || !lock.tabId) return;
        if (lock.tabId === POS_TERMINAL_TAB_ID) return;
        const at = Number(lock.at) || 0;
        if (Date.now() - at >= POS_TERMINAL_LOCAL_STALE_MS) {
            try {
                localStorage.removeItem(POS_TERMINAL_LOCAL_LOCK_KEY);
            } catch (_e) {
                /* ignore */
            }
        }
    }

    function writePosTerminalLocalLock() {
        try {
            localStorage.setItem(
                POS_TERMINAL_LOCAL_LOCK_KEY,
                JSON.stringify({ tabId: POS_TERMINAL_TAB_ID, at: Date.now() })
            );
        } catch (_e) {
            /* ignore */
        }
    }

    function forceClearPosTerminalLocalLock() {
        try {
            localStorage.removeItem(POS_TERMINAL_LOCAL_LOCK_KEY);
        } catch (_e) {
            /* ignore */
        }
    }

    function isPosTerminalLocalLockBlocked() {
        const lock = readPosTerminalLocalLock();
        if (!lock || !lock.tabId || lock.tabId === POS_TERMINAL_TAB_ID) return false;
        const at = Number(lock.at) || 0;
        return Date.now() - at < POS_TERMINAL_LOCAL_STALE_MS;
    }

    async function posTerminalLockReleaseServer() {
        if (!_posTerminalServerLockKey) return;
        try {
            await fetch('/pos-billing/terminal-lock/release', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                keepalive: true,
                body: JSON.stringify({ lock_key: _posTerminalServerLockKey, tab_id: POS_TERMINAL_TAB_ID }),
            });
        } catch (_e) {
            /* ignore */
        }
        _posTerminalServerLockKey = '';
    }

    async function posTerminalLockReacquireServer() {
        const hostnames = await collectPosTerminalLockHostnames();
        if (!hostnames.length) return true;
        try {
            const res = await fetch('/pos-billing/terminal-lock/acquire', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tab_id: POS_TERMINAL_TAB_ID,
                    hostnames,
                    force: true,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (data.success && data.granted !== false) {
                if (data.lock_key) _posTerminalServerLockKey = String(data.lock_key);
                writePosTerminalLocalLock();
                hidePosTerminalLockOverlay();
                return true;
            }
            return false;
        } catch (_e) {
            return false;
        }
    }

    async function posTerminalLockHeartbeatServer() {
        if (!_posTerminalServerLockKey) return true;
        try {
            const res = await fetch('/pos-billing/terminal-lock/heartbeat', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lock_key: _posTerminalServerLockKey, tab_id: POS_TERMINAL_TAB_ID }),
            });
            const data = await res.json().catch(() => ({}));
            if (data.success && data.granted === false) {
                const reclaimed = await posTerminalLockReacquireServer();
                if (!reclaimed) showPosTerminalLockOverlay();
                return reclaimed;
            }
            return !!(data.success && data.granted !== false);
        } catch (_e) {
            return true;
        }
    }

    async function tryAcquirePosTerminalLock(options) {
        const force = !!(options && options.force);
        clearStalePosTerminalLocalLock();
        if (force) {
            forceClearPosTerminalLocalLock();
            await posTerminalLockReleaseServer();
        }
        const leaderOk = await posTerminalLeaderElection(POS_TERMINAL_TAB_ID);
        if (!leaderOk) {
            showPosTerminalLockOverlay();
            return false;
        }
        posTerminalLeaderAnnounceLoop(POS_TERMINAL_TAB_ID);
        if (isPosTerminalLocalLockBlocked()) {
            showPosTerminalLockOverlay();
            return false;
        }
        writePosTerminalLocalLock();
        if (!_posTerminalLockHooksBound) {
            _posTerminalLockHooksBound = true;
            window.addEventListener('storage', (e) => {
                if (e.key !== POS_TERMINAL_LOCAL_LOCK_KEY) return;
                if (isPosTerminalLocalLockBlocked()) showPosTerminalLockOverlay();
            });
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState !== 'visible' || _posTerminalLockBlocked) return;
                clearStalePosTerminalLocalLock();
                writePosTerminalLocalLock();
                if (_posTerminalServerLockKey) {
                    posTerminalLockHeartbeatServer();
                }
            });
            window.addEventListener('pagehide', () => {
                stopPosTerminalLeaderAnnounceLoop();
                try {
                    const lock = readPosTerminalLocalLock();
                    if (lock && lock.tabId === POS_TERMINAL_TAB_ID) {
                        localStorage.removeItem(POS_TERMINAL_LOCAL_LOCK_KEY);
                    }
                } catch (_e) {
                    /* ignore */
                }
                posTerminalLockReleaseServer();
            });
        }
        if (_posTerminalHeartbeatTimer) clearInterval(_posTerminalHeartbeatTimer);
        _posTerminalHeartbeatTimer = setInterval(async () => {
            if (_posTerminalLockBlocked) return;
            writePosTerminalLocalLock();
            await posTerminalLockHeartbeatServer();
        }, POS_TERMINAL_HEARTBEAT_MS);
        const hostnames = await collectPosTerminalLockHostnames();
        if (!hostnames.length) {
            return true;
        }
        try {
            const res = await fetch('/pos-billing/terminal-lock/acquire', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tab_id: POS_TERMINAL_TAB_ID, hostnames, force: force }),
            });
            const data = await res.json().catch(() => ({}));
            if (!data.success) {
                showPosTerminalLockOverlay();
                return false;
            }
            if (data.granted === false) {
                showPosTerminalLockOverlay();
                return false;
            }
            if (data.lock_key) _posTerminalServerLockKey = String(data.lock_key);
            return true;
        } catch (_e) {
            return true;
        }
    }

    async function resolvePosCounterFromHostname() {
        const pre = (counterCodeEl?.value || '').trim();
        if (pre) {
            const n = parseInt(pre, 10);
            if (Number.isFinite(n) && n > 0) {
                const cn = getPosCounterNameFromDisplay();
                if (posCounterWarehouseReadyFromPage()) {
                    hidePosSetCounterModal();
                    return true;
                }
                const bound = await bindPosCounterToSession(n, cn === '—' ? '' : cn);
                if (!bound) {
                    console.warn('bind-session-counter failed; warehouse may be stale until refresh');
                }
                hidePosSetCounterModal();
                return true;
            }
        }
        const resolveUrl = typeof window.__POS_RESOLVE_COUNTER_URL__ === 'string' ? window.__POS_RESOLVE_COUNTER_URL__.trim() : '';
        const uniq = await collectPosTerminalHostnames();
        if (!uniq.length) {
            applyPosCounterDisplay('', 'Could not detect PC name (open POS via computer name in URL, or start QZ Tray, or use Counter Setup)');
            if (counterCodeEl) counterCodeEl.value = '';
            return false;
        }
        if (!resolveUrl) {
            applyPosCounterDisplay('', 'Counter resolve URL missing');
            return false;
        }
        try {
            const res = await fetch(resolveUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hostnames: uniq }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success || !data.matched) {
                applyPosCounterDisplay('', data.error || 'No COUNTER row for this PC');
                if (counterCodeEl) counterCodeEl.value = '';
                return false;
            }
            const cc = data.countercode != null ? String(data.countercode) : '';
            const cn = (data.countername || '').trim();
            if (counterCodeEl) counterCodeEl.value = cc;
            applyPosCounterDisplay(cc, cn);
            if (data.warehouse_code) {
                applyPosWarehouseDisplay(data.warehouse_code, data.warehouse_name);
            }
            const bound = await bindPosCounterToSession(data.countercode, cn);
            if (!bound) {
                console.warn('bind-session-counter failed; counter works this page only until refresh');
            }
            hidePosSetCounterModal();
            return true;
        } catch (e) {
            console.warn('resolve-counter-by-hostname failed', e);
            applyPosCounterDisplay('', 'Could not resolve counter');
            return false;
        }
    }

    const posOpenShiftRequiredModal = document.getElementById('posOpenShiftRequiredModal');

    function showOpenShiftRequiredModal() {
        if (!posOpenShiftRequiredModal) return;
        posOpenShiftRequiredModal.classList.remove('hidden');
        const lk = document.getElementById('posOpenShiftOpsLink');
        if (lk) {
            try {
                lk.focus();
            } catch (_f) {
                /* ignore */
            }
        }
    }

    function hideOpenShiftRequiredModal() {
        if (!posOpenShiftRequiredModal) return;
        posOpenShiftRequiredModal.classList.add('hidden');
    }

    function getCounterCodeIntForShiftCheck() {
        const raw = (counterCodeEl?.value || '').trim();
        if (!raw) return null;
        const n = parseInt(raw, 10);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    function applyPosDateToBillFields(isoDate) {
        if (!isoDate || typeof isoDate !== 'string') return;
        const ymd = isoDate.trim().slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return;
        const hiddenBd = document.getElementById('bill_date');
        if (hiddenBd) hiddenBd.value = ymd;
        const dispBd = document.getElementById('bill_date_display');
        if (dispBd) dispBd.textContent = ymd;
    }

    function applyShiftCodeFromOperations(shiftcode) {
        const hiddenSc = document.getElementById('shift_code');
        const dispSc = document.getElementById('shift_code_display');
        if (shiftcode == null || shiftcode === '') {
            if (hiddenSc) hiddenSc.value = '';
            if (dispSc) dispSc.textContent = '—';
            return;
        }
        const n = Number(shiftcode);
        const s = Number.isFinite(n) ? String(n) : String(shiftcode).trim();
        if (hiddenSc) hiddenSc.value = s;
        if (dispSc) dispSc.textContent = s || '—';
    }

    /** Align hidden + session header with COUNTER master (and echo countercode from server). */
    function applyCounterDisplayFromOpenShiftStatus(data) {
        if (!data || typeof data !== 'object') return;
        let code = counterDisplayEl ? String(counterDisplayEl.dataset.code || '').trim() : '';
        let name = counterDisplayEl ? String(counterDisplayEl.dataset.name || '').trim() : '';
        if (data.countercode != null && data.countercode !== '') {
            const s = String(data.countercode).trim();
            if (s) {
                if (counterCodeEl) counterCodeEl.value = s;
                code = s;
            }
        }
        if (Object.prototype.hasOwnProperty.call(data, 'countername')) {
            name = data.countername == null ? '' : String(data.countername).trim();
        }
        applyPosCounterDisplay(code, name);
    }

    function applyOpenShiftStatusPayload(data) {
        if (!data || data.success !== true) {
            hideOpenShiftRequiredModal();
            applyShiftCodeFromOperations(null);
            return;
        }
        applyCounterDisplayFromOpenShiftStatus(data);
        if (!data.open) {
            showOpenShiftRequiredModal();
            applyShiftCodeFromOperations(null);
            return;
        }
        hideOpenShiftRequiredModal();
        if (data.pos_date) applyPosDateToBillFields(data.pos_date);
        applyShiftCodeFromOperations(data.shiftcode != null ? data.shiftcode : null);
    }

    /** Sync OPENFLAG open row + POS date into bill date; block POS when shift closed for this counter. */
    async function syncOpenShiftGateAndBillDate(cachedPayload) {
        if (cachedPayload && typeof cachedPayload === 'object') {
            applyOpenShiftStatusPayload(cachedPayload);
            return;
        }
        const cc = getCounterCodeIntForShiftCheck();
        if (cc == null) {
            hideOpenShiftRequiredModal();
            applyShiftCodeFromOperations(null);
            return;
        }
        try {
            const res = await fetch(`/pos-billing/open-shift-status?countercode=${encodeURIComponent(String(cc))}`, {
                credentials: 'same-origin',
            });
            const data = await res.json().catch(() => ({}));
            applyOpenShiftStatusPayload(data);
        } catch (_e) {
            hideOpenShiftRequiredModal();
            applyShiftCodeFromOperations(null);
        }
    }

    async function fetchNextBillNo() {
        try {
            const res = await fetch('/pos-billing/next-billno' + posCounterQuerySuffix());
            const data = await res.json();
            if (data.success) setValue(billNo, data.billno);
        } catch (e) {
            console.error('Next bill no failed', e);
        }
    }

    /** Reserve bill + TEMPBILLHDR via server (peek-only next-billno does not create temp header). */
    async function syncBillNoFromActiveTempBill() {
        try {
            const res = await fetch('/pos-billing/last-in-progress-bill' + posCounterQuerySuffix());
            const data = await res.json();
            if (data.success && data.header != null && data.header.billno != null) {
                setValue(billNo, String(data.header.billno));
                return;
            }
        } catch (e) {
            console.warn('last-in-progress-bill failed', e);
        }
        await fetchNextBillNo();
    }

    /** After hold/save/void-all: set sales mode, get next bill via last-in-progress-bill (creates TEMPBILLHDR), set billno and cart. */
    async function loadNextBill() {
        exitSalesReturnMode();
        cart = [];
        clearBelowCostAlerts();
        promotionDiscount = 0;
        appliedVouchers = [];
        clearPosOrderNoField();
        let shiftPayload = null;
        try {
            const res = await fetch('/pos-billing/last-in-progress-bill' + posCounterQuerySuffix());
            const data = await res.json();
            shiftPayload = data.shift || null;
            if (data.success && data.header) {
                const h = data.header;
                const newBillno = h.billno != null ? String(h.billno) : '';
                if (newBillno) setValue(billNo, newBillno);
                cart = (data.lines || [])
                    .filter(l => (Number(l.quantity) || 0) !== 0)
                    .map(l => ({
                        slno: l.slno,
                        item_code: l.item_code,
                        barcode: l.manufacturerid || l.manufacturer_id || l.barcode || '',
                        manufacturerid: l.manufacturerid || l.manufacturer_id || l.barcode || '',
                        item_name: (l.item_name != null && l.item_name !== '') ? String(l.item_name) : String(l.item_code != null ? l.item_code : ''),
                        uom: (l.uom != null && l.uom !== '') ? String(l.uom) : 'PCS',
                        quantity: Number(l.quantity) || 0,
                        rate: Number(l.rate) || 0,
                        old_price: Number(l.old_price) > 0 ? Number(l.old_price) : Number(l.rate) || 0,
                        discount: Number(l.discount) || 0,
                        amount: l.amount != null ? Number(l.amount) : 0,
                        base_qty: l.base_qty != null ? Number(l.base_qty) : Number(l.quantity) || 0,
                        cost: Number(l.cost) || 0,
                        costprice: Number(l.costprice || l.cost) || 0,
                        averagecost: Number(l.averagecost || l.average_cost) || 0,
                        item_factor: Number(l.item_factor || l.conversion_factor || 1) || 1,
                        store: l.store || '',
                        default_bin_storage_id: l.default_bin_storage_id || l.bin_storage_id || null,
                        bin_storage_id: l.bin_storage_id || l.default_bin_storage_id || null,
                        voided: (l.item_flag != null ? Number(l.item_flag) : 1) === 0,
                    }));
                applyOrderNoFromLoadedHeader(h);
            } else {
                await syncBillNoFromActiveTempBill();
            }
        } catch (e) {
            await syncBillNoFromActiveTempBill();
        }
        await syncOpenShiftGateAndBillDate(shiftPayload);
    }

    async function moveToNextBillAfterQueue() {
        exitSalesReturnMode();
        cart = [];
        clearBelowCostAlerts();
        promotionDiscount = 0;
        appliedVouchers = [];
        clearPosOrderNoField();
        renderCart();
        if (customerDisplay) customerDisplay.textContent = '';
        setValue(customerCode, '');
        clearBillingCustomerMetrics();
        clearLoyaltyCustomerUi();
        syncCheckoutButtonLabel();
        await loadNextBill();
        renderCart();
        if (barcodeInput) focusPosBarcodeScanIfNoBlockingGate();
    }

    async function lookupItem(query) {
        const cacheKey = String(query || '').trim().toUpperCase();
        lookupItem.lastError = null;
        if (cacheKey && _posItemLookupCache.has(cacheKey)) {
            return _posItemLookupCache.get(cacheKey);
        }
        const res = await fetch(`/pos-billing/item-info?query=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (!data.success) {
            lookupItem.lastError = data.error || 'Item not found';
            return null;
        }
        if (cacheKey) _posItemLookupCache.set(cacheKey, data.item);
        return data.item;
    }
    lookupItem.lastError = null;

    function isPosWeightScanItem(item) {
        if (!item) return false;
        const flagged = item.is_weight_item === true
            || String(item.is_weight_item || '').toUpperCase() === 'Y';
        return flagged && Number(item.weight_kg) > 0;
    }

    async function addWeightLineFromScan(item, scannedBarcode) {
        const weightKg = Number(item.weight_kg) || 0;
        let ratePerKg = Number(item.rate_per_kg ?? item.barcode_retail_price ?? item.retailprice) || 0;
        if (ratePerKg <= 0) {
            const pricing = await getUomPricing(item.itemcode, 'KG');
            if (pricing) ratePerKg = Number(pricing.rate) || ratePerKg;
        }
        if (weightKg <= 0 || ratePerKg <= 0) {
            showPosMessagePopup('Weight item', 'Could not resolve weight or price per KG for this scan.');
            return false;
        }
        const scanQty = salesReturnEnabled ? -weightKg : weightKg;
        const itemCode = item.itemcode;
        const itemName = (item.itemname || '').trim() || String(itemCode);
        const store = (item.store || item.default_store || '').toString().trim() || 'STORE1';
        const defaultBinStorageId = item.default_bin_storage_id || item.defaultBinStorageId || null;
        const itemFactor = Number((item.item_factor ?? item.conversion_factor) ?? 1) || 1;
        const costprice = Number(item.costprice) || 0;
        const averagecost = Number((item.averagecost ?? item.average_cost) ?? 0) || 0;
        const cost = costprice;
        const discount = 0;
        const amount = scanQty * ratePerKg - discount;
        const scanCode = (scannedBarcode || item.scanned_barcode || item.barcode || '').toString().trim();
        const newLine = {
            item_code: itemCode,
            barcode: scanCode,
            manufacturerid: scanCode,
            scanned_barcode: scanCode,
            item_name: itemName,
            uom: 'KG',
            quantity: scanQty,
            rate: ratePerKg,
            old_price: ratePerKg,
            discount,
            amount,
            base_qty: scanQty * itemFactor,
            cost,
            costprice,
            averagecost,
            item_factor: itemFactor,
            store,
            default_bin_storage_id: defaultBinStorageId,
            bin_storage_id: defaultBinStorageId,
            is_weight_item: true,
            weight_kg: weightKg,
            voided: false,
        };
        cart.push(newLine);
        renderCart();
        const slno = await apiCartLineAdd(newLine);
        if (slno != null) {
            newLine.slno = slno;
            finishOneShotSalesReturnAfterScan();
            renderCart();
            scrollCartToLatestLine();
            if (barcodeInput) barcodeInput.focus();
            return true;
        }
        const idx = cart.indexOf(newLine);
        if (idx >= 0) cart.splice(idx, 1);
        renderCart();
        return false;
    }

    async function getUomPricing(itemCode, uomCode) {
        const res = await fetch(
            `/pos-billing/uom-info?item_code=${encodeURIComponent(itemCode)}&uom_code=${encodeURIComponent(uomCode)}&price_mode=retail`
        );
        const data = await res.json();
        if (!data.success) return null;
        return data.pricing;
    }

    async function addLineFromBarcode(barcode) {
        const query = (barcode || '').toString().trim();
        if (!query) return;
        setValue(barcodeInput, '');
        if (barcodeInput) barcodeInput.focus();
        if (!(billNo && billNo.value && String(billNo.value).trim())) {
            await syncBillNoFromActiveTempBill();
        }
        const item = await lookupItem(query);
        if (!item) {
            const errMsg = lookupItem.lastError || 'No matching item for this barcode or code.';
            const errTitle = errMsg.toLowerCase().includes('variable-weight') || errMsg.toLowerCase().includes('weight barcode')
                ? 'Invalid weight barcode'
                : 'Item not found';
            showPosMessagePopup(errTitle, errMsg);
            return;
        }
        if (isPosWeightScanItem(item)) {
            await addWeightLineFromScan(item, query);
            return;
        }
        const itemCode = item.itemcode;
        const manufacturerId = (item.manufacturerid || item.manufacturer_id || item.barcode || query || '').toString().trim();
        const itemName = (item.itemname || '').trim() || String(itemCode);
        const baseUom = (item.baseuom || '').trim() || 'PCS';
        const store = (item.store || item.default_store || '').toString().trim() || 'STORE1';
        const defaultBinStorageId = item.default_bin_storage_id || item.defaultBinStorageId || null;
        let uom = baseUom;
        let rate = 0;
        if (item.barcode_uom != null && item.barcode_retail_price != null) {
            uom = (item.barcode_uom || '').toString().trim() || baseUom;
            rate = Number(item.barcode_retail_price) || 0;
        }
        if (rate === 0) {
            rate = Number(item.retailprice) || 0;
            const pricing = await getUomPricing(itemCode, uom);
            if (pricing) rate = Number(pricing.rate) || rate;
        }
        const discount = 0;
        const itemFactor = Number((item.item_factor ?? item.conversion_factor) ?? 1) || 1;
        const costprice = Number(item.costprice) || 0;
        const averagecost = Number((item.averagecost ?? item.average_cost) ?? 0) || 0;
        const cost = costprice;

        const scanQty = salesReturnEnabled ? -1 : 1;
        const sameLineIndex = cart.findIndex(
            (line) =>
                !line.voided &&
                String(line.item_code) === String(itemCode) &&
                String(line.uom) === String(uom) &&
                Math.abs(Number(line.rate) - Number(rate)) < 1e-6
        );
        const sameLine = sameLineIndex >= 0 ? cart[sameLineIndex] : null;
        if (sameLine && sameLine.slno != null) {
            const newQty = sameLine.quantity + scanQty;
            if (newQty === 0) {
                const ok = await apiCartLineRemove(sameLine.slno);
                if (ok) {
                    cart.splice(sameLineIndex, 1);
                    if (selectedLineIndex !== null) {
                        if (selectedLineIndex === sameLineIndex) selectedLineIndex = null;
                        else if (selectedLineIndex > sameLineIndex) selectedLineIndex--;
                    }
                    finishOneShotSalesReturnAfterScan();
                }
            } else {
                const oldQty = sameLine.quantity;
                const oldBaseQty = sameLine.base_qty;
                const oldAmount = sameLine.amount;
                sameLine.quantity = newQty;
                sameLine.base_qty = newQty * (Number(sameLine.item_factor) || 1);
                sameLine.amount = newQty * sameLine.rate - (Number(sameLine.discount) || 0);
                renderCart();
                const ok = await apiCartLineUpdate(sameLine.slno, newQty);
                if (!ok) {
                    sameLine.quantity = oldQty;
                    sameLine.base_qty = oldBaseQty;
                    sameLine.amount = oldAmount;
                    renderCart();
                } else {
                    finishOneShotSalesReturnAfterScan();
                }
            }
        } else {
            const amount = scanQty * rate - discount;
            const newLine = {
                item_code: itemCode,
                barcode: manufacturerId,
                manufacturerid: manufacturerId,
                item_name: itemName,
                uom: uom,
                quantity: scanQty,
                rate,
                old_price: rate,
                discount,
                amount,
                base_qty: scanQty * itemFactor,
                cost,
                costprice,
                averagecost,
                item_factor: itemFactor,
                store,
                default_bin_storage_id: defaultBinStorageId,
                bin_storage_id: defaultBinStorageId,
                voided: false,
            };
            cart.push(newLine);
            renderCart();
            const slno = await apiCartLineAdd(newLine);
            if (slno != null) {
                newLine.slno = slno;
                finishOneShotSalesReturnAfterScan();
            } else {
                const idx = cart.indexOf(newLine);
                if (idx >= 0) cart.splice(idx, 1);
                renderCart();
            }
        }
        renderCart();
        scrollCartToLatestLine();
        if (barcodeInput) barcodeInput.focus();
    }

    /** Add line(s) from resolved ``item-info`` payload with explicit quantity (AI screenshot, etc.). */
    async function addLineFromItemWithQty(item, qtyRaw) {
        if (!item || item.itemcode == null) return false;
        if (isPosWeightScanItem(item)) {
            const scanCode = (item.scanned_barcode || item.barcode || item.manufacturerid || '').toString().trim();
            return addWeightLineFromScan(item, scanCode);
        }
        const qtyAbs = Math.max(0.0001, Math.abs(Number(qtyRaw) || 1));
        const scanQty = salesReturnEnabled ? -qtyAbs : qtyAbs;
        if (!(billNo && billNo.value && String(billNo.value).trim())) {
            await syncBillNoFromActiveTempBill();
        }
        const itemCode = item.itemcode;
        const manufacturerId = (item.manufacturerid || item.manufacturer_id || '').toString().trim();
        const itemName = (item.itemname || '').trim() || String(itemCode);
        const baseUom = (item.baseuom || '').trim() || 'PCS';
        const store = (item.store || item.default_store || '').toString().trim() || 'STORE1';
        const defaultBinStorageId = item.default_bin_storage_id || item.defaultBinStorageId || null;
        let uom = baseUom;
        let rate = 0;
        if (item.barcode_uom != null && item.barcode_retail_price != null) {
            uom = (item.barcode_uom || '').toString().trim() || baseUom;
            rate = Number(item.barcode_retail_price) || 0;
        }
        if (rate === 0) {
            rate = Number(item.retailprice) || 0;
            const pricing = await getUomPricing(itemCode, uom);
            if (pricing) rate = Number(pricing.rate) || rate;
        }
        const discount = 0;
        const itemFactor = Number((item.item_factor ?? item.conversion_factor) ?? 1) || 1;
        const costprice = Number(item.costprice) || 0;
        const averagecost = Number((item.averagecost ?? item.average_cost) ?? 0) || 0;
        const cost = costprice;

        const sameLineIndex = cart.findIndex(
            (line) =>
                !line.voided &&
                String(line.item_code) === String(itemCode) &&
                String(line.uom) === String(uom) &&
                Math.abs(Number(line.rate) - Number(rate)) < 1e-6
        );
        const sameLine = sameLineIndex >= 0 ? cart[sameLineIndex] : null;
        if (sameLine && sameLine.slno != null) {
            const newQty = sameLine.quantity + scanQty;
            if (newQty === 0) {
                const ok = await apiCartLineRemove(sameLine.slno);
                if (ok) {
                    cart.splice(sameLineIndex, 1);
                    if (selectedLineIndex !== null) {
                        if (selectedLineIndex === sameLineIndex) selectedLineIndex = null;
                        else if (selectedLineIndex > sameLineIndex) selectedLineIndex--;
                    }
                    finishOneShotSalesReturnAfterScan();
                }
                renderCart();
                return ok;
            }
            const oldQty = sameLine.quantity;
            const oldBaseQty = sameLine.base_qty;
            const oldAmount = sameLine.amount;
            sameLine.quantity = newQty;
            sameLine.base_qty = newQty * (Number(sameLine.item_factor) || 1);
            sameLine.amount = newQty * sameLine.rate - (Number(sameLine.discount) || 0);
            renderCart();
            const ok = await apiCartLineUpdate(sameLine.slno, newQty);
            if (!ok) {
                sameLine.quantity = oldQty;
                sameLine.base_qty = oldBaseQty;
                sameLine.amount = oldAmount;
                renderCart();
                return false;
            }
            finishOneShotSalesReturnAfterScan();
            renderCart();
            return true;
        }
        const amount = scanQty * rate - discount;
        const newLine = {
            item_code: itemCode,
            barcode: manufacturerId,
            manufacturerid: manufacturerId,
            item_name: itemName,
            uom: uom,
            quantity: scanQty,
            rate,
            old_price: rate,
            discount,
            amount,
            base_qty: scanQty * itemFactor,
            cost,
            costprice,
            averagecost,
            item_factor: itemFactor,
            store,
            default_bin_storage_id: defaultBinStorageId,
            bin_storage_id: defaultBinStorageId,
            voided: false,
        };
        cart.push(newLine);
        renderCart();
        const slno = await apiCartLineAdd(newLine);
        if (slno != null) {
            newLine.slno = slno;
            finishOneShotSalesReturnAfterScan();
            renderCart();
            return true;
        }
        const idx = cart.indexOf(newLine);
        if (idx >= 0) cart.splice(idx, 1);
        renderCart();
        return false;
    }

    function getLookupLineData(row) {
        if (!row) return null;
        return {
            itemCode: row.dataset.itemCode || '',
            barcode: (row.dataset.barcode || '').trim(),
            itemName: (row.dataset.itemName || '').trim(),
            uom: (row.dataset.uom || '').trim() || 'PCS',
            rate: Number(row.dataset.price || 0) || 0,
            cost: Number(row.dataset.cost || 0) || 0,
            costprice: Number(row.dataset.costprice || row.dataset.cost || 0) || 0,
            averagecost: Number(row.dataset.averagecost || 0) || 0,
            itemFactor: Number(row.dataset.itemFactor || row.dataset.item_factor || row.dataset.conversionFactor || 1) || 1,
        };
    }

    function openBarcodeQtyPopup(row) {
        const data = getLookupLineData(row);
        if (!data || !data.itemCode) return;
        pendingBarcodeLookupLine = data;
        pendingBarcodeQtyPosting = false;
        if (btnBarcodeQtyApply) btnBarcodeQtyApply.disabled = false;
        if (barcodeQtyInput) barcodeQtyInput.disabled = false;
        if (barcodeQtyItemName) {
            let label = data.itemName || String(data.itemCode);
            if (isPosShowCostEnabled()) {
                const unitCost = data.costprice || data.cost || data.averagecost || 0;
                if (unitCost > 0) label += ` · Cost ${formatNum(unitCost)}`;
            }
            barcodeQtyItemName.textContent = label;
        }
        if (barcodeQtyInput) barcodeQtyInput.value = '1';
        openModal('barcodeQtyModal');
        if (barcodeQtyModal) barcodeQtyModal.style.zIndex = '10003';
        setTimeout(() => {
            if (barcodeQtyInput) {
                barcodeQtyInput.focus();
                barcodeQtyInput.select();
            }
        }, 50);
    }

    async function addPendingLookupLineWithQty() {
        if (pendingBarcodeQtyPosting) return;
        const data = pendingBarcodeLookupLine;
        if (!data || !data.itemCode) return;
        const qtyRaw = Number(barcodeQtyInput?.value || 0);
        if (!(qtyRaw > 0)) {
            showPosMessagePopup('Quantity', 'Enter a quantity greater than zero.');
            if (barcodeQtyInput) barcodeQtyInput.focus();
            return;
        }
        pendingBarcodeQtyPosting = true;
        if (btnBarcodeQtyApply) btnBarcodeQtyApply.disabled = true;
        if (barcodeQtyInput) barcodeQtyInput.disabled = true;
        pendingBarcodeLookupLine = null;
        try {
            if (!(billNo && billNo.value && String(billNo.value).trim())) {
                await syncBillNoFromActiveTempBill();
            }
            const itemCode = data.itemCode;
            if (!itemCode) return;
            let manufacturerId = (data.barcode || '').trim();
            const itemName = data.itemName || String(itemCode);
            const uom = data.uom || 'PCS';
            let store = data.store || 'STORE1';
            let defaultBinStorageId = data.defaultBinStorageId || null;
            let rate = Number(data.rate) || 0;
            let cost = Number(data.cost) || 0;
            let costprice = Number(data.costprice || data.cost || 0) || 0;
            let averagecost = Number(data.averagecost || 0) || 0;
            let itemFactor = Number(data.itemFactor || 1) || 1;
            if (rate <= 0) {
                const pricing = await getUomPricing(itemCode, uom);
                if (pricing) {
                    const mid = pricing.manufacturer_id ?? pricing.manufacturerid;
                    if (mid != null && String(mid).trim() !== '') {
                        manufacturerId = String(mid).trim();
                    }
                    const pr = Number(pricing.rate);
                    if (!Number.isNaN(pr)) {
                        rate = pr;
                    }
                    const cp = Number(pricing.cost_price ?? pricing.costprice);
                    if (!Number.isNaN(cp)) {
                        cost = cp;
                    }
                    const itemCp = Number(pricing.costprice ?? costprice);
                    if (!Number.isNaN(itemCp)) {
                        costprice = itemCp;
                    }
                    const avgCp = Number(pricing.averagecost ?? pricing.average_cost);
                    if (!Number.isNaN(avgCp)) {
                        averagecost = avgCp;
                    }
                    const factor = Number(pricing.item_factor ?? pricing.conversion_factor);
                    if (!Number.isNaN(factor) && factor > 0) {
                        itemFactor = factor;
                    }
                    if (pricing.store || pricing.default_store) {
                        store = pricing.store || pricing.default_store || store;
                    }
                    if (pricing.default_bin_storage_id || pricing.defaultBinStorageId) {
                        defaultBinStorageId = pricing.default_bin_storage_id || pricing.defaultBinStorageId;
                    }
                }
            }

            function closeQtyLookupPopupsAndFocusScan() {
                closeModal('barcodeQtyModal');
                closeModal('barcodeLookupModal');
                scrollCartToLatestLine();
                setValue(barcodeInput, '');
                if (barcodeInput) barcodeInput.focus();
            }

            const scanQty = salesReturnEnabled ? -Math.abs(qtyRaw) : Math.abs(qtyRaw);
            const sameLineIndex = cart.findIndex(
                (line) =>
                    !line.voided &&
                    String(line.item_code) === String(itemCode) &&
                    String(line.uom) === String(uom) &&
                    Math.abs(Number(line.rate) - Number(rate)) < 1e-6
            );
            const sameLine = sameLineIndex >= 0 ? cart[sameLineIndex] : null;
            if (sameLine && sameLine.slno != null) {
                const newQty = sameLine.quantity + scanQty;
                if (newQty === 0) {
                    const ok = await apiCartLineRemove(sameLine.slno);
                    if (ok) {
                        cart.splice(sameLineIndex, 1);
                        if (selectedLineIndex !== null) {
                            if (selectedLineIndex === sameLineIndex) selectedLineIndex = null;
                            else if (selectedLineIndex > sameLineIndex) selectedLineIndex--;
                        }
                        finishOneShotSalesReturnAfterScan();
                    }
                    renderCart();
                    closeQtyLookupPopupsAndFocusScan();
                } else {
                    const oldQty = sameLine.quantity;
                    const oldBase = sameLine.base_qty;
                    const oldAmt = sameLine.amount;
                    sameLine.quantity = newQty;
                    sameLine.base_qty = newQty * (Number(sameLine.item_factor) || 1);
                    sameLine.amount = newQty * sameLine.rate - (Number(sameLine.discount) || 0);
                    renderCart();
                    closeQtyLookupPopupsAndFocusScan();
                    const ok = await apiCartLineUpdate(sameLine.slno, newQty);
                    if (!ok) {
                        sameLine.quantity = oldQty;
                        sameLine.base_qty = oldBase;
                        sameLine.amount = oldAmt;
                        renderCart();
                    } else {
                        finishOneShotSalesReturnAfterScan();
                    }
                }
            } else {
                const newLine = {
                    item_code: itemCode,
                    barcode: manufacturerId,
                    manufacturerid: manufacturerId,
                    item_name: itemName,
                    uom,
                    quantity: scanQty,
                    rate,
                    old_price: rate,
                    discount: 0,
                    amount: scanQty * rate,
                    base_qty: scanQty * itemFactor,
                    cost,
                    costprice,
                    averagecost,
                    item_factor: itemFactor,
                    store,
                    default_bin_storage_id: defaultBinStorageId,
                    bin_storage_id: defaultBinStorageId,
                    voided: false,
                };
                cart.push(newLine);
                renderCart();
                closeQtyLookupPopupsAndFocusScan();
                const slno = await apiCartLineAdd(newLine);
                if (slno != null) {
                    newLine.slno = slno;
                    finishOneShotSalesReturnAfterScan();
                } else {
                    const idx = cart.indexOf(newLine);
                    if (idx >= 0) cart.splice(idx, 1);
                    renderCart();
                }
            }
        } finally {
            pendingBarcodeQtyPosting = false;
            if (btnBarcodeQtyApply) btnBarcodeQtyApply.disabled = false;
            if (barcodeQtyInput) barcodeQtyInput.disabled = false;
        }
    }

    function addLineFromLookupRow(row) {
        openBarcodeQtyPopup(row);
    }

    async function removeLine(index) {
        const line = cart[index];
        if (!line) return;
        if (line.slno != null) {
            const ok = await apiCartLineRemove(line.slno);
            if (!ok) return;
        }
        cart.splice(index, 1);
        if (selectedLineIndex !== null) {
            if (selectedLineIndex === index) selectedLineIndex = null;
            else if (selectedLineIndex > index) selectedLineIndex--;
        }
        renderCart();
        finishOneShotSalesReturnAfterScan();
    }

    async function increaseQty(index) {
        if (index < 0 || index >= cart.length) return;
        const line = cart[index];
        if (line.voided) return;
        const newQty = line.quantity + 1;
        if (line.slno != null) {
            const ok = await apiCartLineUpdate(line.slno, newQty);
            if (!ok) return;
        }
        line.quantity = newQty;
        line.base_qty = newQty * (Number(line.item_factor) || 1);
        line.amount = Math.max(0, newQty * line.rate - (Number(line.discount) || 0));
        renderCart();
        finishOneShotSalesReturnAfterScan();
    }

    async function decreaseQty(index) {
        if (index < 0 || index >= cart.length) return;
        const line = cart[index];
        if (line.voided) return;
        const newQty = line.quantity - 1;
        if (newQty <= 0) {
            if (line.slno != null) {
                const ok = await apiCartLineRemove(line.slno);
                if (!ok) return;
            }
            cart.splice(index, 1);
            if (selectedLineIndex !== null) {
                if (selectedLineIndex === index) selectedLineIndex = null;
                else if (selectedLineIndex > index) selectedLineIndex--;
            }
        } else {
            if (line.slno != null) {
                const ok = await apiCartLineUpdate(line.slno, newQty);
                if (!ok) return;
            }
            line.quantity = newQty;
            line.base_qty = newQty * (Number(line.item_factor) || 1);
            line.amount = Math.max(0, newQty * line.rate - (Number(line.discount) || 0));
        }
        renderCart();
        finishOneShotSalesReturnAfterScan();
    }

    function buildSyncHeader() {
        const billno = (billNo?.value || '').trim();
        const countercode = (counterCodeEl?.value || '').trim();
        let loyaltycustomercode = 0;
        const lraw = loyaltyCustomerCode?.value?.trim();
        if (lraw) {
            try {
                loyaltycustomercode = parseInt(lraw, 10);
                if (Number.isNaN(loyaltycustomercode)) loyaltycustomercode = 0;
            } catch (e) {
                loyaltycustomercode = 0;
            }
        }
        let customercode = 0;
        const craw = customerCode?.value?.trim();
        if (craw) {
            try {
                customercode = parseInt(craw, 10);
                if (Number.isNaN(customercode)) customercode = 0;
            } catch (e2) {
                customercode = 0;
            }
        }
        let shiftcode = 0;
        const scRaw = (document.getElementById('shift_code')?.value || '').trim();
        if (scRaw) {
            try {
                shiftcode = parseInt(scRaw, 10);
                if (Number.isNaN(shiftcode)) shiftcode = 0;
            } catch (eSc) {
                shiftcode = 0;
            }
        }
        const out = {
            billno: posBillnoForApi(billno),
            billdate: (document.getElementById('bill_date')?.value || '').trim() || new Date().toISOString().slice(0, 10),
            billtime: new Date().toTimeString().slice(0, 8),
            createdby: '',
            countercode: countercode ? parseInt(countercode, 10) : 0,
            shiftcode,
            customercode,
            loyaltycustomercode,
        };
        const onRaw = (posOrderNoEl?.value || '').trim();
        if (onRaw) out.orderno = onRaw.slice(0, 80);
        return out;
    }

    let _posHeaderSnapTimer = null;
    function lineCatalogPrice(line, rate) {
        const op = Number(line && line.old_price);
        if (op > 0) return op;
        return Number(rate) || 0;
    }

    function isLinePriceEdited(line) {
        const rate = Number(line && line.rate) || 0;
        const catalog = lineCatalogPrice(line, rate);
        return Math.abs(rate - catalog) > 0.009;
    }

    function lineUnitCost(line) {
        if (!line) return 0;
        const cp = Number(line.costprice);
        const c = Number(line.cost);
        const ac = Number(line.averagecost);
        if (Number.isFinite(cp) && cp > 0) return cp;
        if (Number.isFinite(c) && c > 0) return c;
        if (Number.isFinite(ac) && ac > 0) return ac;
        const fallback = Math.max(
            Number.isFinite(cp) ? cp : 0,
            Number.isFinite(c) ? c : 0,
            Number.isFinite(ac) ? ac : 0
        );
        return fallback;
    }

    function isLineBelowCost(line, rateOverride) {
        if (!line || line.voided) return false;
        const rate = rateOverride != null ? Number(rateOverride) : Number(line.rate) || 0;
        if (rate <= 0) return true;
        const cost = lineUnitCost(line);
        if (cost > 0 && rate < cost - 1e-6) return true;
        return false;
    }

    function belowCostLineKey(line, index) {
        if (line && line.slno != null) return `s:${line.slno}`;
        return `i:${index}:${line && line.item_code}:${line && line.uom}`;
    }

    function syncBelowCostAlert(line, index) {
        if (!line || line.voided) return;
        const key = belowCostLineKey(line, index);
        if (isLineBelowCost(line)) {
            if (!belowCostAlerted.has(key)) {
                belowCostAlerted.add(key);
                showPosMessagePopup('Below Cost', 'Selling price is zero or below item cost.');
            }
        } else {
            belowCostAlerted.delete(key);
        }
    }

    function clearBelowCostAlerts() {
        belowCostAlerted.clear();
    }

    function cartLinesForTempSync() {
        return cart.map(line => ({
            item_code: line.item_code,
            uom: line.uom,
            quantity: line.quantity,
            rate: line.rate,
            old_price: lineCatalogPrice(line, line.rate),
            discount: line.discount || 0,
            base_qty: line.base_qty != null ? line.base_qty : line.quantity,
            costprice: line.costprice || line.cost || 0,
            cost: line.cost || 0,
            averagecost: line.averagecost || 0,
            item_factor: line.item_factor || 1,
            manufacturerid: line.manufacturerid || line.barcode || '',
            item_flag: line.voided ? 0 : 1,
        }));
    }
    async function pushPosHeaderSnapshotToTemp() {
        const billnoRaw = (billNo?.value || '').trim();
        if (!billnoRaw) return;
        const hdr = buildSyncHeader();
        hdr.billno = posBillnoForApi(billnoRaw);
        try {
            await fetch('/pos-billing/cart-sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header: hdr, lines: cartLinesForTempSync() }),
            });
        } catch (e) {
            console.warn('cart-sync header snapshot failed', e);
        }
    }
    function schedulePushPosHeaderSnapshotToTemp() {
        if (_posHeaderSnapTimer) clearTimeout(_posHeaderSnapTimer);
        _posHeaderSnapTimer = setTimeout(() => {
            _posHeaderSnapTimer = null;
            pushPosHeaderSnapshotToTemp();
        }, 450);
    }

    if (posOrderNoEl) {
        posOrderNoEl.addEventListener('input', schedulePushPosHeaderSnapshotToTemp);
        posOrderNoEl.addEventListener('blur', () => {
            if (_posHeaderSnapTimer) clearTimeout(_posHeaderSnapTimer);
            _posHeaderSnapTimer = null;
            pushPosHeaderSnapshotToTemp();
        });
    }

    function applyOrderNoFromLoadedHeader(h) {
        if (!posOrderNoEl || !h) return;
        const v = h.orderno != null && h.orderno !== '' ? String(h.orderno).trim() : '';
        posOrderNoEl.value = v || '';
    }

    function clearPosOrderNoField() {
        if (posOrderNoEl) posOrderNoEl.value = '';
    }

    async function apiCartLineAdd(line) {
        const header = buildSyncHeader();
        const billno = (billNo?.value || '').trim();
        if (!billno) {
            console.warn('Cart line add: no bill no');
            return null;
        }
        header.billno = posBillnoForApi(billno);
        try {
            const res = await fetch('/pos-billing/cart-line-add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    header,
                    line: {
                        item_code: line.item_code,
                        manufacturerid: line.manufacturerid || line.barcode || '',
                        uom: line.uom,
                        quantity: line.quantity,
                        rate: line.rate,
                        discount: line.discount || 0,
                        cost: line.cost || 0,
                        costprice: line.costprice || line.cost || 0,
                        averagecost: line.averagecost || 0,
                        item_factor: line.item_factor || 1,
                        base_qty: line.base_qty != null ? line.base_qty : line.quantity,
                        store: line.store || '',
                        default_bin_storage_id: line.default_bin_storage_id || line.bin_storage_id || null,
                        bin_storage_id: line.bin_storage_id || line.default_bin_storage_id || null,
                    },
                }),
            });
            const data = await res.json();
            if (!data.success) {
                console.warn('Cart line add failed:', data.error);
                showPosMessagePopup('Save line', 'Could not save to bill: ' + (data.error || 'Unknown error'));
                return null;
            }
            return data.slno;
        } catch (e) {
            console.warn('Cart line add failed', e);
            showPosMessagePopup('Save line', 'Could not save to bill: ' + (e.message || 'Network error'));
            return null;
        }
    }

    async function apiCartLineVoid(slno) {
        const header = buildSyncHeader();
        const billno = (billNo?.value || '').trim();
        if (!billno || slno == null) return false;
        header.billno = posBillnoForApi(billno);
        try {
            const res = await fetch('/pos-billing/cart-line-void', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header, slno }),
            });
            const data = await res.json();
            return !!data.success;
        } catch (e) {
            console.warn('Cart line void failed', e);
            return false;
        }
    }

    async function apiCartLineUpdate(slno, quantity) {
        const header = buildSyncHeader();
        const billno = (billNo?.value || '').trim();
        if (!billno || slno == null) return false;
        header.billno = posBillnoForApi(billno);
        try {
            const res = await fetch('/pos-billing/cart-line-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header, slno, quantity }),
            });
            const data = await res.json();
            if (!data.success) {
                console.warn('Cart line update failed:', data.error);
                showPosMessagePopup('Update quantity', 'Could not update quantity: ' + (data.error || 'Unknown error'));
                return false;
            }
            return true;
        } catch (e) {
            console.warn('Cart line update failed', e);
            showPosMessagePopup('Update quantity', 'Could not update quantity: ' + (e.message || 'Network error'));
            return false;
        }
    }

    async function apiCartLineSetRate(slno, rate) {
        const header = buildSyncHeader();
        const billno = (billNo?.value || '').trim();
        if (!billno || slno == null) return false;
        header.billno = posBillnoForApi(billno);
        try {
            const res = await fetch('/pos-billing/cart-line-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header, slno, rate }),
            });
            const data = await res.json();
            if (!data.success) {
                console.warn('Cart line price failed:', data.error);
                showPosMessagePopup('Change price', 'Could not update price: ' + (data.error || 'Unknown error'));
                return false;
            }
            return true;
        } catch (e) {
            console.warn('Cart line price failed', e);
            showPosMessagePopup('Change price', 'Could not update price: ' + (e.message || 'Network error'));
            return false;
        }
    }

    async function apiCartLineSetDiscount(slno, discount) {
        const header = buildSyncHeader();
        const billno = (billNo?.value || '').trim();
        if (!billno || slno == null) return false;
        header.billno = posBillnoForApi(billno);
        try {
            const res = await fetch('/pos-billing/cart-line-update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header, slno, discount }),
            });
            const data = await res.json();
            if (!data.success) {
                console.warn('Cart line discount failed:', data.error);
                showPosMessagePopup('Line discount', 'Could not update discount: ' + (data.error || 'Unknown error'));
                return false;
            }
            return true;
        } catch (e) {
            console.warn('Cart line discount failed', e);
            showPosMessagePopup('Line discount', 'Could not update discount: ' + (e.message || 'Network error'));
            return false;
        }
    }

    async function apiCartLineRemove(slno) {
        const header = buildSyncHeader();
        const billno = (billNo?.value || '').trim();
        if (!billno || slno == null) return false;
        header.billno = posBillnoForApi(billno);
        try {
            const res = await fetch('/pos-billing/cart-line-remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ header, slno }),
            });
            const data = await res.json();
            if (!data.success) {
                console.warn('Cart line remove failed:', data.error);
                showPosMessagePopup('Delete line', 'Could not delete line: ' + (data.error || 'Unknown error'));
                return false;
            }
            return true;
        } catch (e) {
            console.warn('Cart line remove failed', e);
            showPosMessagePopup('Delete line', 'Could not delete line: ' + (e.message || 'Network error'));
            return false;
        }
    }

    function renderCart() {
        for (let i = cart.length - 1; i >= 0; i--) {
            if (Number(cart[i].quantity) === 0) {
                cart.splice(i, 1);
                if (selectedLineIndex !== null) {
                    if (selectedLineIndex === i) selectedLineIndex = null;
                    else if (selectedLineIndex > i) selectedLineIndex--;
                }
            }
        }
        const activeLines = cart.filter(line => !line.voided);
        let totalAmt = 0;
        let totalDisc = 0;
        activeLines.forEach(line => {
            totalAmt += line.quantity * line.rate;
            totalDisc += Number(line.discount) || 0;
        });
        const net = totalAmt - totalDisc - promotionDiscount;
        const discTotal = totalDisc + promotionDiscount;
        if (posGrandTotalEl) posGrandTotalEl.textContent = formatNum(totalAmt);
        if (posTotalDiscountEl) posTotalDiscountEl.textContent = formatNum(discTotal);
        if (posNetTotalEl) posNetTotalEl.textContent = formatNum(net);
        syncPosDdTotalPointsBar();
        if (btnHold) btnHold.textContent = window.posHoldBtnLabel(activeLines.length > 0);
        syncBillingCustomerCreditWarn(net);
        if (cart.length === 0) {
            if (posOrderEmpty) posOrderEmpty.style.display = 'block';
            if (posOrderLines) { posOrderLines.style.display = 'none'; posOrderLines.innerHTML = ''; }
            return;
        }
        if (posOrderEmpty) posOrderEmpty.style.display = 'none';
        if (posOrderLines) {
            posOrderLines.style.display = 'block';
            let rowsHtml = '';
            cart.forEach((line, i) => {
                const amt = (line.quantity * line.rate) - (Number(line.discount) || 0);
                const name = (line.item_name || '').trim() || String(line.item_code);
                const barcode = (line.manufacturerid || line.barcode || '').toString();
                const qty = Number(line.quantity) || 0;
                const rate = Number(line.rate) || 0;
                const isWeightLine = line.is_weight_item === true
                    || String(line.is_weight_item || '').toUpperCase() === 'Y';
                const catalog = lineCatalogPrice(line, rate);
                const priceEdited = isLinePriceEdited(line);
                const discAmt = Number(line.discount) || 0;
                const lineTotal = qty * rate;
                const discPct = lineTotal > 0 ? ((discAmt / lineTotal) * 100).toFixed(1) : '0';
                const selectedClass = selectedLineIndex === i ? ' selected' : '';
                const voidedClass = line.voided ? ' item-voided' : '';
                const belowCost = !line.voided && isLineBelowCost(line);
                if (belowCost) syncBelowCostAlert(line, i);
                const belowCostClass = belowCost ? ' below-cost' : '';
                const priceCellClass = priceEdited
                    ? ' col-price pos-price-edited-cell pos-price-clickable'
                    : ' col-price pos-price-clickable';
                const qtyCellClass = line.voided
                    ? ' col-qty'
                    : (isWeightLine ? ' col-qty' : ' col-qty pos-qty-clickable');
                const qtyTitle = line.voided
                    ? ' title="Voided line"'
                    : (isWeightLine ? ' title="Weight (KG)"' : ' title="Click to change quantity"');
                const priceTitle = line.voided
                    ? ' title="Voided line"'
                    : (isWeightLine
                        ? (priceEdited ? ` title="Price/KG (catalog ${formatNum(catalog)}) — click to change"` : ' title="Price per KG — click to change"')
                        : (priceEdited ? ` title="Catalog ${formatNum(catalog)} — click to change price"` : ' title="Click to change price"'));
                const amountTitle = line.voided
                    ? ' title="Voided line"'
                    : ' title="Click to change amount (adjusts price)"';
                const amountCellClass = line.voided
                    ? ' col-amount'
                    : ' col-amount pos-amount-clickable';
                const priceDisplay = priceEdited
                    ? `${formatNum(rate)} <span class="pos-price-edited-mark" aria-hidden="true">*</span>`
                    : formatNum(rate);
                const barcodeSub = isWeightLine
                    ? `KG · ${(line.scanned_barcode || line.manufacturerid || line.barcode || String(line.item_code || '')).trim()}`
                    : (barcode || String(line.item_code || '')).trim();
                const qtyDisplay = isWeightLine ? formatNum(Math.abs(qty), 3) : formatNum(qty);
                const showCost = isPosShowCostEnabled();
                const unitCost = lineUnitCost(line);
                const costCell = showCost
                    ? `<td class="col-cost" title="Item cost">${formatNum(unitCost)}</td>`
                    : '';
                rowsHtml += `<tr class="pos-order-line${selectedClass}${voidedClass}${belowCostClass}" data-line="${i}" data-item-code="${line.item_code}" data-uom="${line.uom}" data-quantity="${line.quantity}" data-rate="${line.rate}" data-discount="${line.discount}" data-amount="${amt}">
                    <td class="col-slno">${i + 1}</td>
                    <td class="col-name"><div class="col-name-text">${name}</div><div class="col-name-barcode">${barcodeSub}</div></td>
                    <td class="${qtyCellClass}" data-line-qty="${i}"${qtyTitle}>${qtyDisplay}</td>
                    ${costCell}
                    <td class="${priceCellClass}" data-line-price="${i}"${priceTitle}>${priceDisplay}</td>
                    <td class="col-disc">${discPct}%</td>
                    <td class="${amountCellClass}" data-line-amount="${i}"${amountTitle}>${formatNum(amt)}</td>
                </tr>`;
            });
            const costHeader = isPosShowCostEnabled() ? '<th>Cost</th>' : '';
            posOrderLines.innerHTML = `<table class="pos-cart-table">
                <thead><tr>
                    <th>Sl No</th><th>Item name</th><th>Qty</th>${costHeader}<th>Price</th><th>Disc%</th><th>Amount</th>
                </tr></thead>
                <tbody>${rowsHtml}</tbody>
            </table>`;
            posOrderLines.querySelectorAll('.pos-order-line').forEach((rowEl, i) => {
                rowEl.addEventListener('click', (e) => {
                    if (e.target.closest('.pos-order-line__actions')) return;
                    if (e.target.closest('.pos-price-clickable')) return;
                    if (e.target.closest('.pos-qty-clickable')) return;
                    if (e.target.closest('.pos-amount-clickable')) return;
                    selectedLineIndex = i;
                    posOrderLines.querySelectorAll('.pos-order-line').forEach(el => el.classList.remove('selected'));
                    rowEl.classList.add('selected');
                });
            });
            posOrderLines.querySelectorAll('.pos-price-clickable').forEach((cellEl) => {
                cellEl.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const idx = parseInt(cellEl.getAttribute('data-line-price'), 10);
                    if (Number.isNaN(idx)) return;
                    openChangePriceModalForLine(idx);
                });
            });
            posOrderLines.querySelectorAll('.pos-qty-clickable').forEach((cellEl) => {
                cellEl.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const idx = parseInt(cellEl.getAttribute('data-line-qty'), 10);
                    if (Number.isNaN(idx)) return;
                    openChangeQtyModalForLine(idx);
                });
            });
            posOrderLines.querySelectorAll('.pos-amount-clickable').forEach((cellEl) => {
                cellEl.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const idx = parseInt(cellEl.getAttribute('data-line-amount'), 10);
                    if (Number.isNaN(idx)) return;
                    openChangeAmountModalForLine(idx);
                });
            });
        }
    }

    function openChangeQtyModalForLine(lineIndex) {
        if (lineIndex == null || lineIndex < 0 || lineIndex >= cart.length) {
            showPosMessagePopup('Select a line', 'Select an item from the cart first (click on a line).');
            return;
        }
        const line = cart[lineIndex];
        if (line.voided) {
            showPosMessagePopup('Change quantity', 'Cannot change qty for a voided item.');
            return;
        }
        selectedLineIndex = lineIndex;
        if (posOrderLines) {
            posOrderLines.querySelectorAll('.pos-order-line').forEach((el, i) => {
                el.classList.toggle('selected', i === lineIndex);
            });
        }
        const inputVal = salesReturnEnabled ? Math.abs(line.quantity) : line.quantity;
        if (changeQtyHint) {
            changeQtyHint.textContent = salesReturnEnabled
                ? 'Return quantity (positive number):'
                : 'New quantity for selected item:';
        }
        setValue(changeQtyInput, inputVal);
        openModal('changeQtyModal');
        setTimeout(() => changeQtyInput && changeQtyInput.focus(), 100);
    }

    function openChangePriceModalForLine(lineIndex) {
        if (lineIndex == null || lineIndex < 0 || lineIndex >= cart.length) {
            showPosMessagePopup('Select a line', 'Select an item from the cart first (click on a line).');
            return;
        }
        const line = cart[lineIndex];
        if (line.voided) {
            showPosMessagePopup('Change price', 'Cannot change price for a voided item.');
            return;
        }
        selectedLineIndex = lineIndex;
        if (posOrderLines) {
            posOrderLines.querySelectorAll('.pos-order-line').forEach((el, i) => {
                el.classList.toggle('selected', i === lineIndex);
            });
        }
        const catalog = lineCatalogPrice(line, line.rate);
        if (changePriceHint) {
            changePriceHint.textContent = catalog > 0 && Math.abs(Number(line.rate) - catalog) > 0.009
                ? `Catalog price ${formatNum(catalog)}. Enter new unit price:`
                : 'New unit price for selected item:';
        }
        setValue(changePriceInput, Number(line.rate) || 0);
        openModal('changePriceModal');
        setTimeout(() => changePriceInput && changePriceInput.focus(), 100);
    }

    function openChangeAmountModalForLine(lineIndex) {
        if (lineIndex == null || lineIndex < 0 || lineIndex >= cart.length) {
            showPosMessagePopup('Select a line', 'Select an item from the cart first (click on a line).');
            return;
        }
        const line = cart[lineIndex];
        if (line.voided) {
            showPosMessagePopup('Change amount', 'Cannot change amount for a voided item.');
            return;
        }
        const qty = Number(line.quantity) || 0;
        if (Math.abs(qty) < 1e-9) {
            showPosMessagePopup('Change amount', 'Quantity must not be zero.');
            return;
        }
        selectedLineIndex = lineIndex;
        if (posOrderLines) {
            posOrderLines.querySelectorAll('.pos-order-line').forEach((el, i) => {
                el.classList.toggle('selected', i === lineIndex);
            });
        }
        const disc = Number(line.discount) || 0;
        const currentAmt = Number(line.amount != null ? line.amount : (qty * Number(line.rate) - disc));
        const rate = Number(line.rate) || 0;
        if (changeAmountHint) {
            changeAmountHint.textContent =
                `Qty ${formatNum(Math.abs(qty))} × price ${formatNum(rate)}`
                + (disc ? ` − disc ${formatNum(disc)}` : '')
                + `. Enter new line amount (price will be adjusted):`;
        }
        // Keypad uses absolute value; sign follows qty (sales vs return).
        setValue(changeAmountInput, Math.abs(currentAmt) || 0);
        openModal('changeAmountModal');
        setTimeout(() => changeAmountInput && changeAmountInput.focus(), 100);
    }

    function localDateInputString(d) {
        const dt = d instanceof Date ? d : new Date();
        const y = dt.getFullYear();
        const m = String(dt.getMonth() + 1).padStart(2, '0');
        const day = String(dt.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }

    function datePlusOneYear(d) {
        const dt = d instanceof Date ? new Date(d.getTime()) : new Date();
        dt.setFullYear(dt.getFullYear() + 1);
        return dt;
    }

    function prepCreateLoyaltyForm() {
        const st = document.getElementById('create_loyalty_status');
        if (st) {
            st.textContent = '';
            st.style.color = '';
        }
        setValue(document.getElementById('create_loyalty_name'), '');
        setValue(document.getElementById('create_loyalty_qidno'), '');
        setValue(document.getElementById('create_loyalty_mob'), '');
        setValue(document.getElementById('create_loyalty_email'), '');
        const cardEl = document.getElementById('create_loyalty_cardno');
        if (cardEl) cardEl.value = '';
        setValue(document.getElementById('create_loyalty_points'), '0');
        const today = new Date();
        const idEl = document.getElementById('create_loyalty_issuedate');
        const exEl = document.getElementById('create_loyalty_expirydate');
        if (idEl) idEl.value = localDateInputString(today);
        if (exEl) exEl.value = localDateInputString(datePlusOneYear(today));
        const ccEl = document.getElementById('create_loyalty_customercode');
        setValue(ccEl, '');
        const nextUrl = window.__POS_LOYALTY_NEXT_CODE__;
        if (!nextUrl || !ccEl) return;
        fetch(nextUrl, { credentials: 'same-origin' })
            .then((r) => r.json())
            .then((data) => {
                if (data.success && data.next_code != null) {
                    setValue(ccEl, String(data.next_code));
                }
            })
            .catch(() => {});
    }

    function openModal(id) {
        const m = document.getElementById(id);
        if (m) {
            m.classList.remove('hidden');
            m.style.display = 'flex';
            if (id === 'customerModal') {
                if (customerModalSearch) customerModalSearch.value = '';
                const regularUrl = window.__POS_CUSTOMERS_PICKER__;
                const loyaltyUrl = window.__POS_LOYALTY_CUSTOMERS_PICKER__;
                const canLoadPickers =
                    posCustomerPickTarget === 'loyalty'
                        ? Boolean(loyaltyUrl || regularUrl)
                        : Boolean(regularUrl);
                requestAnimationFrame(() => {
                    const el = customerModalSearch;
                    if (!el) return;
                    try {
                        el.focus({ preventScroll: true });
                    } catch (_) {
                        el.focus();
                    }
                });
                if (canLoadPickers) {
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => loadPosCustomerPicker(''));
                    });
                }
            }
            if (id === 'barcodeLookupModal' && window.__POS_BARCODE_ITEMS__) {
                if (barcodeLookupSearch) {
                    barcodeLookupSearch.value = barcodeInput ? (barcodeInput.value || '') : '';
                    setTimeout(() => barcodeLookupSearch.focus(), 80);
                }
                loadBarcodeLookup(barcodeLookupSearch ? barcodeLookupSearch.value.trim() : '');
            }
            if (id === 'createLoyaltyModal') {
                prepCreateLoyaltyForm();
            }
        }
    }

    function closeModal(id) {
        const m = document.getElementById(id);
        if (m) {
            m.classList.add('hidden');
            m.style.display = '';
        }
        if (id === 'posMessageModal') {
            requestAnimationFrame(() =>
                requestAnimationFrame(() => focusPosBarcodeScanIfNoBlockingGate()),
            );
        }
    }

    function openCustomerPicker(target) {
        posCustomerPickTarget = target === 'loyalty' ? 'loyalty' : 'billing';
        if (customerModalTitle) {
            customerModalTitle.textContent = posCustomerPickTarget === 'loyalty' ? 'Loyalty' : 'Customer';
        }
        openModal('customerModal');
    }

    document.querySelectorAll('[data-close]').forEach(el => {
        el.addEventListener('click', () => closeModal(el.getAttribute('data-close')));
    });

    function showPosMessagePopup(title, message) {
        const tEl = document.getElementById('posMessageModalTitle');
        const pEl = document.getElementById('posMessageModalText');
        if (tEl) tEl.textContent = title != null && title !== '' ? title : 'Notice';
        if (pEl) pEl.textContent = message != null ? String(message) : '';
        openModal('posMessageModal');
    }

    window.showPosMessagePopup = showPosMessagePopup;

    let posConfirmResolver = null;

    function closePosConfirmModal(result) {
        const r = posConfirmResolver;
        posConfirmResolver = null;
        closeModal('posConfirmModal');
        if (r) r(!!result);
        requestAnimationFrame(() => requestAnimationFrame(() => focusPosBarcodeScanIfNoBlockingGate()));
    }

    /** @returns {Promise<boolean>} true = OK, false = cancel/close */
    function showPosConfirmPopup(title, message) {
        return new Promise((resolve) => {
            if (posConfirmResolver) posConfirmResolver(false);
            posConfirmResolver = resolve;
            const tEl = document.getElementById('posConfirmModalTitle');
            const pEl = document.getElementById('posConfirmModalText');
            if (tEl) tEl.textContent = title != null && title !== '' ? title : 'Confirm';
            if (pEl) pEl.textContent = message != null ? String(message) : '';
            openModal('posConfirmModal');
        });
    }

    document.getElementById('btnPosConfirmOk')?.addEventListener('click', () => closePosConfirmModal(true));
    document.getElementById('btnPosConfirmCancel')?.addEventListener('click', () => closePosConfirmModal(false));
    document.getElementById('posConfirmModalOverlay')?.addEventListener('click', () => closePosConfirmModal(false));
    document.getElementById('posConfirmModalClose')?.addEventListener('click', () => closePosConfirmModal(false));

    const btnPosMessageModalOk = document.getElementById('btnPosMessageModalOk');
    if (btnPosMessageModalOk) {
        btnPosMessageModalOk.addEventListener('click', () => closeModal('posMessageModal'));
    }

    if (customerDisplay) {
        customerDisplay.addEventListener('click', () => openCustomerPicker('billing'));
    }
    if (loyaltyCustomerDisplay) {
        loyaltyCustomerDisplay.addEventListener('click', () => openCustomerPicker('loyalty'));
    }
    if (btnPosCustomer) {
        btnPosCustomer.addEventListener('click', () => openCustomerPicker('billing'));
    }
    if (btnPosLoyaltyCustomer) {
        btnPosLoyaltyCustomer.addEventListener('click', () => openCustomerPicker('loyalty'));
    }
    if (btnPosCreateLoyalty) {
        btnPosCreateLoyalty.addEventListener('click', () => {
            openModal('createLoyaltyModal');
            setTimeout(() => document.getElementById('create_loyalty_name')?.focus(), 120);
        });
    }
    const btnCreateLoyaltySubmit = document.getElementById('btnCreateLoyaltySubmit');
    if (btnCreateLoyaltySubmit && window.__POS_LOYALTY_CREATE__) {
        btnCreateLoyaltySubmit.addEventListener('click', async () => {
            const st = document.getElementById('create_loyalty_status');
            const url = window.__POS_LOYALTY_CREATE__;
            const ccRaw = document.getElementById('create_loyalty_customercode')?.value?.trim() ?? '';
            const nm = document.getElementById('create_loyalty_name')?.value?.trim() ?? '';
            if (!nm) {
                if (st) {
                    st.style.color = '#fca5a5';
                    st.textContent = 'Customer name is required.';
                }
                return;
            }
            let customercode = 0;
            if (ccRaw) {
                const pcc = parseInt(ccRaw, 10);
                if (Number.isFinite(pcc) && pcc > 0) customercode = pcc;
            }
            const payload = {
                customercode,
                customername: nm,
                mob: document.getElementById('create_loyalty_mob')?.value?.trim() || '',
                email: document.getElementById('create_loyalty_email')?.value?.trim() || '',
                totalpoints: 0,
            };
            const cardRaw = document.getElementById('create_loyalty_cardno')?.value?.trim();
            if (cardRaw) {
                const cn = parseInt(cardRaw, 10);
                if (Number.isFinite(cn) && cn >= 0) payload.cardno = cn;
            }
            const qidRaw = document.getElementById('create_loyalty_qidno')?.value?.trim();
            if (qidRaw) {
                const qn = parseInt(qidRaw, 10);
                if (Number.isFinite(qn) && qn >= 0) payload.qidno = qn;
            }
            const isd = document.getElementById('create_loyalty_issuedate')?.value?.trim();
            const exd = document.getElementById('create_loyalty_expirydate')?.value?.trim();
            if (isd) payload.issuedate = isd;
            if (exd) payload.expirydate = exd;
            if (st) {
                st.style.color = '#94a3b8';
                st.textContent = 'Saving…';
            }
            btnCreateLoyaltySubmit.disabled = true;
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (data.success) {
                    const disName = (data.customername || nm).trim().toUpperCase();
                    const codeStr = data.customercode != null ? String(data.customercode) : String(customercode);
                    if (loyaltyCustomerDisplay) {
                        loyaltyCustomerDisplay.textContent = disName || codeStr || '';
                    }
                    setValue(loyaltyCustomerCode, codeStr);
                    const ptsDone = data.totalpoints != null ? data.totalpoints : payload.totalpoints;
                    setLoyaltyPointsMetric(ptsDone);
                    const cardDone =
                        data.cardno != null && data.cardno !== undefined
                            ? data.cardno
                            : payload.cardno !== undefined
                              ? payload.cardno
                              : null;
                    setLoyaltyCardNoMetric(cardDone);
                    renderCart();
                    closeModal('createLoyaltyModal');
                    if (st) st.textContent = '';
                    focusPosBarcodeScan();
                } else if (st) {
                    st.style.color = '#fca5a5';
                    st.textContent = data.error || 'Save failed.';
                }
            } catch (e) {
                if (st) {
                    st.style.color = '#fca5a5';
                    st.textContent = e.message || 'Request failed.';
                }
            } finally {
                btnCreateLoyaltySubmit.disabled = false;
            }
        });
    }
    if (btnClearCustomer) {
        btnClearCustomer.addEventListener('click', () => {
            if (customerDisplay) customerDisplay.textContent = '';
            setValue(customerCode, '');
            clearBillingCustomerMetrics();
            syncCheckoutButtonLabel();
            if (barcodeInput) barcodeInput.focus();
        });
    }
    if (btnClearLoyaltyCustomer) {
        btnClearLoyaltyCustomer.addEventListener('click', () => {
            clearLoyaltyCustomerUi();
            if (barcodeInput) barcodeInput.focus();
        });
    }
    if (customerModalBody) {
        customerModalBody.addEventListener('click', (e) => {
            const row = e.target.closest('.customer-row');
            if (!row) return;
            const name = (row.dataset.name || row.dataset.code || '').trim() || row.dataset.code;
            const cl = parseFloat(row.dataset.creditLimit || '0');
            const os = parseFloat(row.dataset.outstandingCash || '0');
            const pts = parseFloat(row.dataset.totalPoints || '0');
            const cnoRaw = row.dataset.cardNo;
            const cno = cnoRaw !== undefined && cnoRaw !== '' ? parseFloat(cnoRaw) : NaN;
            if (posCustomerPickTarget === 'loyalty') {
                if (loyaltyCustomerDisplay) loyaltyCustomerDisplay.textContent = name || '';
                setValue(loyaltyCustomerCode, row.dataset.code);
                setLoyaltyPointsMetric(pts);
                setLoyaltyCardNoMetric(Number.isFinite(cno) ? cno : null);
                renderCart();
            } else {
                if (customerDisplay) customerDisplay.textContent = name || '';
                setValue(customerCode, row.dataset.code);
                setBillingCustomerMetrics(cl, os);
                syncCheckoutButtonLabel();
            }
            closeModal('customerModal');
        });
    }
    if (customerModalSearch) {
        customerModalSearch.addEventListener('input', () => {
            schedulePosCustomerPicker(customerModalSearch.value.trim());
        });
    }

    function handleBarcodeInputKeydown(e) {
        if (e.key === 'F1' || e.keyCode === 112) {
            e.preventDefault();
            openBarcodeLookupFromScan();
            return;
        }
        if (e.key !== 'Enter') return;
        e.preventDefault();
        addLineFromBarcode(barcodeInput ? barcodeInput.value : '');
    }

    if (barcodeInput) {
        barcodeInput.addEventListener('keydown', handleBarcodeInputKeydown);
    }
    if (btnPosBarcodeEnter) {
        btnPosBarcodeEnter.addEventListener('click', (e) => {
            e.preventDefault();
            if (!barcodeInput) return;
            barcodeInput.focus();
            handleBarcodeInputKeydown(
                new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })
            );
        });
    }
    function showLastBillSummary(summary) {
        if (!posLastBillSummary) return;
        const s = summary || {};
        const net = Number(s.net);
        const paid = Number(s.paid);
        const change = Number(s.change);
        if (posLastBillNet) posLastBillNet.textContent = formatNum(Number.isFinite(net) ? net : 0);
        if (posLastBillPaid) posLastBillPaid.textContent = formatNum(Number.isFinite(paid) ? paid : 0);
        if (posLastBillChange) posLastBillChange.textContent = formatNum(Number.isFinite(change) ? change : 0);
        if (posLastBillNo) {
            const bn = s.billno != null && String(s.billno).trim() !== '' ? String(s.billno).trim() : '';
            posLastBillNo.textContent = bn ? 'Bill #' + bn : '';
        }
        posLastBillSummary.classList.remove('hidden');
    }

    if (btnPosBarcodeClear) {
        btnPosBarcodeClear.addEventListener('click', (e) => {
            e.preventDefault();
            setValue(barcodeInput, '');
            if (barcodeInput) barcodeInput.focus();
        });
    }
    if (btnPosBarcodeBackspace) {
        btnPosBarcodeBackspace.addEventListener('click', (e) => {
            e.preventDefault();
            if (!barcodeInput) return;
            const val = String(barcodeInput.value || '');
            if (val.length) barcodeInput.value = val.slice(0, -1);
            barcodeInput.focus();
        });
    }

    function bindPosAiScreenshotDrawerUiOnce() {
        const root = document.getElementById('posAiScreenshotDrawer');
        if (!root || root.dataset.bound === '1') return;
        root.dataset.bound = '1';
        const backdrop = document.getElementById('posAiDrawerBackdrop');
        const btnClose = document.getElementById('posAiDrawerClose');
        const btnCancel = document.getElementById('posAiDrawerCancel');
        const btnConfirm = document.getElementById('posAiDrawerConfirm');
        const selAll = document.getElementById('posAiDrawerSelectAll');
        const tbody = document.getElementById('posAiDrawerBody');
        const grandTotalEl = document.getElementById('posAiDrawerGrandTotal');

        function aiDrawerEffectiveUnitPrice(it) {
            if (!it) return 0;
            if (it.barcode_uom != null && it.barcode_retail_price != null) {
                return Number(it.barcode_retail_price) || 0;
            }
            return Number(it.retailprice) || 0;
        }

        function formatAiDrawerStock(v) {
            const n = Number(v);
            if (!Number.isFinite(n)) return '—';
            if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
            return formatNum(n, 3);
        }

        function updateAiDrawerTotals() {
            if (!tbody || !grandTotalEl) return;
            let sum = 0;
            tbody.querySelectorAll('.pos-ai-cart-card[data-matched="1"]').forEach((card) => {
                const cb = card.querySelector('.pos-ai-drawer-inc');
                if (!cb || !cb.checked) return;
                const unit = Number(card.dataset.unitPrice || 0);
                const qInp = card.querySelector('.pos-ai-drawer-qty');
                const q = Math.abs(Number(qInp && qInp.value !== '' ? qInp.value : 1) || 0);
                sum += q * unit;
            });
            grandTotalEl.innerHTML = `<span class="pos-ai-drawer__grand-label">Subtotal</span><span class="pos-ai-drawer__grand-value">${formatNum(sum)}</span>`;
        }

        function refreshAiDrawerRowAmount(card) {
            if (!card || card.dataset.matched !== '1') return;
            const unit = Number(card.dataset.unitPrice || 0);
            const qInp = card.querySelector('.pos-ai-drawer-qty');
            const sp = card.querySelector('.pos-ai-drawer-line-amt');
            if (!sp) return;
            const q = Math.abs(Number(qInp && qInp.value !== '' ? qInp.value : 1) || 0);
            sp.textContent = formatNum(q * unit);
        }

        function wireAiDrawerQtyStepper(card) {
            const inp = card.querySelector('.pos-ai-drawer-qty');
            const minus = card.querySelector('[data-ai-qty-minus]');
            const plus = card.querySelector('[data-ai-qty-plus]');
            const bump = (delta) => {
                let v = Math.abs(Number(inp && inp.value !== '' ? inp.value : 1) || 1);
                if (delta < 0) {
                    v = Math.max(0.0001, v + delta);
                } else {
                    v = v + delta;
                }
                if (inp) inp.value = String(v);
                refreshAiDrawerRowAmount(card);
                updateAiDrawerTotals();
            };
            minus?.addEventListener('click', () => bump(-1));
            plus?.addEventListener('click', () => bump(1));
        }

        function closePosAiScreenshotDrawer(opts) {
            const keepPreview = !!(opts && opts.keepPreview);
            root.classList.add('hidden');
            root.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
            if (!keepPreview) {
                pendingAiScreenshotResults = null;
                if (tbody) tbody.innerHTML = '';
                if (grandTotalEl) grandTotalEl.innerHTML = '';
            }
            updateAiReviewCartButtonVisibility();
        }

        function updateAiReviewCartButtonVisibility() {
            const btn = document.getElementById('posAiReviewCartBtn');
            if (!btn || !root) return;
            const show = !!(
                pendingAiScreenshotResults &&
                pendingAiScreenshotResults.length &&
                root.classList.contains('hidden')
            );
            btn.classList.toggle('hidden', !show);
            btn.setAttribute('aria-hidden', show ? 'false' : 'true');
        }

        function reopenPosAiScreenshotDrawer() {
            if (!pendingAiScreenshotResults || !pendingAiScreenshotResults.length) return false;
            if (!root.classList.contains('hidden')) return true;
            root.classList.remove('hidden');
            root.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
            updateAiReviewCartButtonVisibility();
            return true;
        }

        function syncSelectAllFromRows() {
            if (!selAll || !tbody) return;
            const boxes = tbody.querySelectorAll('.pos-ai-cart-card[data-matched="1"] .pos-ai-drawer-inc');
            const list = Array.from(boxes);
            if (!list.length) {
                selAll.checked = false;
                selAll.disabled = true;
                updateAiDrawerTotals();
                return;
            }
            selAll.disabled = false;
            const on = list.every((c) => c.checked);
            selAll.checked = on;
            updateAiDrawerTotals();
        }

        function renderPosAiScreenshotDrawer(results) {
            const summaryEl = document.getElementById('posAiDrawerSummary');
            if (!tbody || !summaryEl) return;
            pendingAiScreenshotResults = results;
            tbody.innerHTML = '';
            let nMatch = 0;
            let nMiss = 0;
            (results || []).forEach((raw, i) => {
                const r = raw && typeof raw === 'object' ? raw : {};
                const matched = !!(r.matched && r.item);
                if (matched) nMatch += 1;
                else nMiss += 1;
                const ai = r.ai && typeof r.ai === 'object' ? r.ai : {};
                const nameHint = String(
                    ai.item_name || ai.itemname || ai.name || ai.product_name || ai.description || ai.product || ''
                ).trim();
                const bc =
                    String(ai.barcode || ai.manufacturerid || ai.manufacturer_id || ai.ean || ai.upc || '').trim() || '—';
                const aiExtractLabel =
                    nameHint && nameHint !== bc ? `${bc} · ${nameHint}` : bc;

                const card = document.createElement('article');
                card.className = 'pos-ai-cart-card' + (matched ? '' : ' pos-ai-cart-card--miss');
                card.dataset.aiIndex = String(i);
                card.dataset.matched = matched ? '1' : '0';

                const pick = document.createElement('div');
                pick.className = 'pos-ai-cart-card__pick';

                const thumb = document.createElement('div');
                thumb.className = 'pos-ai-cart-card__thumb';

                const body = document.createElement('div');
                body.className = 'pos-ai-cart-card__body';

                const titleRow = document.createElement('div');
                titleRow.style.display = 'flex';
                titleRow.style.flexWrap = 'wrap';
                titleRow.style.alignItems = 'center';
                titleRow.style.gap = '8px';

                const badge = document.createElement('span');
                badge.className = 'pos-ai-cart-card__badge';

                const titleEl = document.createElement('p');
                titleEl.className = 'pos-ai-cart-card__title';

                const metaEl = document.createElement('div');
                metaEl.className = 'pos-ai-cart-card__meta';

                const aiEl = document.createElement('div');
                aiEl.className = 'pos-ai-cart-card__ai';
                aiEl.textContent = `Extracted · ${aiExtractLabel}`;

                const side = document.createElement('div');
                side.className = 'pos-ai-cart-card__side';

                if (matched && r.item) {
                    const it = r.item;
                    const unitPrice = aiDrawerEffectiveUnitPrice(it);
                    card.dataset.unitPrice = String(unitPrice);
                    const stockRaw = it.currentstock ?? it.current_stock ?? it.CURRENTSTOCK;
                    const sysRetail = it.system_retail_price ?? it.systemRetailPrice ?? it.retailprice;
                    const nm = String(it.itemname || '').trim();
                    const ic = it.itemcode != null ? String(it.itemcode) : '';
                    const qu = String(r.query_used || '').trim();
                    const titleText = nm || (ic ? `Item ${ic}` : 'Item');
                    const initial = (titleText || '?').trim().charAt(0).toUpperCase() || '?';
                    thumb.textContent = initial;

                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.className = 'pos-ai-drawer-inc';
                    cb.checked = true;
                    cb.addEventListener('change', syncSelectAllFromRows);
                    pick.appendChild(cb);

                    badge.textContent = 'Matched';
                    titleEl.textContent = titleText;

                    const metaBits = [];
                    if (ic) metaBits.push(`#${ic}`);
                    metaBits.push(`Stock ${formatAiDrawerStock(stockRaw)}`);
                    metaBits.push(`List ${formatNum(Number(sysRetail) || 0)}`);
                    if (qu && qu !== bc) metaBits.push(`Found via ${qu}`);
                    metaEl.textContent = metaBits.join(' · ');

                    const unitWrap = document.createElement('div');
                    unitWrap.className = 'pos-ai-cart-card__unit-price';
                    unitWrap.innerHTML = `Price ea.<strong>${formatNum(unitPrice)}</strong>`;

                    const qtyRow = document.createElement('div');
                    qtyRow.className = 'pos-ai-cart-qty';
                    const btnMinus = document.createElement('button');
                    btnMinus.type = 'button';
                    btnMinus.className = 'pos-ai-cart-qty__btn';
                    btnMinus.setAttribute('data-ai-qty-minus', '');
                    btnMinus.setAttribute('aria-label', 'Decrease quantity');
                    btnMinus.textContent = '−';
                    const inp = document.createElement('input');
                    inp.type = 'number';
                    inp.className = 'pos-ai-drawer-qty';
                    inp.step = 'any';
                    inp.min = '0.0001';
                    inp.value = String(Number(r.qty) > 0 ? Number(r.qty) : 1);
                    inp.setAttribute('aria-label', 'Quantity');
                    const btnPlus = document.createElement('button');
                    btnPlus.type = 'button';
                    btnPlus.className = 'pos-ai-cart-qty__btn';
                    btnPlus.setAttribute('data-ai-qty-plus', '');
                    btnPlus.setAttribute('aria-label', 'Increase quantity');
                    btnPlus.textContent = '+';
                    qtyRow.append(btnMinus, inp, btnPlus);

                    const lineTot = document.createElement('div');
                    lineTot.className = 'pos-ai-cart-card__line-total';
                    const spanAmt = document.createElement('span');
                    spanAmt.className = 'pos-ai-drawer-line-amt';
                    const q0 = Math.abs(Number(r.qty) > 0 ? Number(r.qty) : 1);
                    spanAmt.textContent = formatNum(q0 * unitPrice);
                    lineTot.appendChild(spanAmt);

                    side.append(unitWrap, qtyRow, lineTot);

                    titleRow.append(badge, titleEl);
                    body.append(titleRow, metaEl, aiEl);
                    card.append(pick, thumb, body, side);
                    tbody.appendChild(card);

                    wireAiDrawerQtyStepper(card);
                    inp.addEventListener('input', () => {
                        refreshAiDrawerRowAmount(card);
                        updateAiDrawerTotals();
                    });
                } else {
                    thumb.textContent = '?';
                    pick.innerHTML = '<span style="display:inline-block;width:18px;height:18px;"></span>';

                    badge.textContent = 'Unavailable';
                    titleEl.textContent = 'Not in catalog';
                    const tried = Array.isArray(r.queries_tried) ? r.queries_tried.filter(Boolean).join(', ') : '';
                    metaEl.textContent = tried
                        ? `No ITEMMASTER match for: ${tried}`
                        : 'Could not resolve this line against your catalog.';
                    titleRow.append(badge, titleEl);
                    body.append(titleRow, metaEl, aiEl);

                    const missQty = document.createElement('div');
                    missQty.className = 'pos-ai-cart-card__unit-price';
                    missQty.innerHTML = `<strong>Qty ${String(Number(r.qty) > 0 ? Number(r.qty) : 1)}</strong>`;
                    side.appendChild(missQty);

                    card.append(pick, thumb, body, side);
                    tbody.appendChild(card);
                }
            });

            summaryEl.textContent =
                (results || []).length === 0
                    ? 'No lines extracted from image.'
                    : `${nMatch} item${nMatch === 1 ? '' : 's'} ready · ${nMiss} need attention — adjust quantities, then add to your POS cart.`;
            syncSelectAllFromRows();
            if (btnConfirm) {
                btnConfirm.disabled = nMatch === 0;
                btnConfirm.textContent = nMatch ? `Add to cart (${nMatch})` : 'Add to cart';
            }
        }

        function openPosAiScreenshotDrawer(results) {
            renderPosAiScreenshotDrawer(results);
            root.classList.remove('hidden');
            root.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
            updateAiReviewCartButtonVisibility();
        }

        posAiScreenshotDrawerOpen = openPosAiScreenshotDrawer;
        reopenPosAiScreenshotPreviewFn = reopenPosAiScreenshotDrawer;

        const btnReviewCart = document.getElementById('posAiReviewCartBtn');
        btnReviewCart?.addEventListener('click', () => reopenPosAiScreenshotDrawer());

        backdrop?.addEventListener('click', () => closePosAiScreenshotDrawer({ keepPreview: true }));
        btnClose?.addEventListener('click', () => closePosAiScreenshotDrawer({ keepPreview: true }));
        btnCancel?.addEventListener('click', () => closePosAiScreenshotDrawer({ keepPreview: true }));

        selAll?.addEventListener('change', () => {
            if (!tbody || !selAll) return;
            const on = selAll.checked;
            tbody.querySelectorAll('.pos-ai-cart-card[data-matched="1"] .pos-ai-drawer-inc').forEach((cb) => {
                cb.checked = on;
            });
            updateAiDrawerTotals();
        });

        btnConfirm?.addEventListener('click', async () => {
            if (!tbody || !pendingAiScreenshotResults) return;
            const rows = Array.from(tbody.querySelectorAll('.pos-ai-cart-card[data-ai-index]'));
            btnConfirm.disabled = true;
            let added = 0;
            try {
                for (let j = 0; j < rows.length; j++) {
                    const card = rows[j];
                    const cb = card.querySelector('.pos-ai-drawer-inc');
                    if (!cb || !cb.checked) continue;
                    const idx = parseInt(card.dataset.aiIndex || '-1', 10);
                    if (idx < 0 || idx >= pendingAiScreenshotResults.length) continue;
                    const r = pendingAiScreenshotResults[idx];
                    if (!r || !r.matched || !r.item) continue;
                    const qInp = card.querySelector('.pos-ai-drawer-qty');
                    const qtyVal = qInp && qInp.value !== '' ? qInp.value : r.qty;
                    const ok = await addLineFromItemWithQty(r.item, qtyVal);
                    if (ok) added += 1;
                }
                closePosAiScreenshotDrawer();
                if (added > 0) {
                    const ta = document.getElementById('posAiCapturePaste');
                    if (ta) ta.value = '';
                    const stEl = document.getElementById('posAiCaptureStatus');
                    if (stEl) stEl.textContent = '';
                }
                if (added === 0 && rows.some((card) => card.dataset.matched === '1')) {
                    showPosMessagePopup('AI screenshot', 'No lines were selected or add failed.');
                } else {
                    scrollCartToLatestLine();
                    if (barcodeInput) barcodeInput.focus();
                }
            } finally {
                btnConfirm.disabled = false;
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            if (!root || root.classList.contains('hidden')) return;
            closePosAiScreenshotDrawer({ keepPreview: true });
        });
    }

    function bindPosAiScreenshotCapture() {
        const url = typeof window.__POS_AI_SCREENSHOT_URL__ === 'string' ? window.__POS_AI_SCREENSHOT_URL__.trim() : '';
        const toggle = document.getElementById('posAiCaptureToggle');
        const panel = document.getElementById('posAiCapturePanel');
        const fileEl = document.getElementById('posAiCaptureFile');
        const pick = document.getElementById('posAiCapturePick');
        const statusEl = document.getElementById('posAiCaptureStatus');
        if (!url || !toggle || !panel || !fileEl || !pick) return;

        bindPosAiScreenshotDrawerUiOnce();

        const STORAGE = 'nexa-pos-ai-capture-on';

        function setStatus(t) {
            if (statusEl) statusEl.textContent = t || '';
        }

        function syncPanel() {
            const on = toggle.checked;
            panel.classList.toggle('hidden', !on);
            toggle.setAttribute('aria-checked', on ? 'true' : 'false');
            try {
                localStorage.setItem(STORAGE, on ? '1' : '0');
            } catch (e) {
                /* ignore */
            }
            if (!on) setStatus('');
        }

        try {
            toggle.checked = localStorage.getItem(STORAGE) === '1';
        } catch (e) {
            toggle.checked = false;
        }
        syncPanel();
        toggle.addEventListener('change', syncPanel);
        pick.addEventListener('click', () => fileEl.click());

        const pasteTa = document.getElementById('posAiCapturePaste');
        const analyzeBtn = document.getElementById('posAiAnalyzeTextBtn');

        const AI_CLIPBOARD_TEXT_CAP = 32000;

        function appendPasteBoxSnippet(snippet) {
            if (!pasteTa || snippet === '') return;
            let cur = pasteTa.value.replace(/\s+$/, '');
            let next = cur ? `${cur}\n${snippet}` : snippet;
            if (next.length > AI_CLIPBOARD_TEXT_CAP) {
                next = next.slice(-AI_CLIPBOARD_TEXT_CAP);
            }
            pasteTa.value = next;
            pasteTa.focus();
        }

        async function handleAiLinesResponse(data) {
            if (!data.success) {
                showPosMessagePopup(
                    'AI screenshot',
                    data.error ? String(data.error) : 'HTTP error' + (data.detail ? ': ' + String(data.detail) : '')
                );
                setStatus('');
                return;
            }
            const results = data.results || [];
            if (!results.length) {
                showPosMessagePopup('AI screenshot', 'No lines extracted.');
                setStatus('');
                return;
            }
            if (typeof posAiScreenshotDrawerOpen === 'function') {
                posAiScreenshotDrawerOpen(results);
                const matchedN = results.filter((row) => row && row.matched && row.item).length;
                const unmatchedN = results.length - matchedN;
                setStatus(
                    `Cart preview: ${matchedN} product${matchedN === 1 ? '' : 's'} matched${unmatchedN ? ` · ${unmatchedN} unavailable` : ''}. Open drawer to review.`
                );
            } else {
                let added = 0;
                let skipped = 0;
                for (let i = 0; i < results.length; i++) {
                    const r = results[i];
                    if (!r.matched || !r.item) {
                        skipped++;
                        continue;
                    }
                    const ok = await addLineFromItemWithQty(r.item, r.qty);
                    if (ok) added += 1;
                    else skipped += 1;
                }
                setStatus(`Added ${added} line(s).${skipped ? ` ${skipped} unmatched.` : ''}`.trim());
                if (added > 0 && pasteTa) {
                    pasteTa.value = '';
                }
                if (added === 0 && results.length > 0) {
                    showPosMessagePopup(
                        'AI screenshot',
                        'No lines matched ITEMMASTER or ITEMALTERNATEUOMMAP. Try clearer content or barcodes.'
                    );
                }
                scrollCartToLatestLine();
                if (barcodeInput) barcodeInput.focus();
            }
        }

        async function fetchAiLines(reqInit) {
            const res = await fetch(url, { credentials: 'same-origin', ...reqInit });
            const ctHdr = (res.headers.get('content-type') || '').toLowerCase();
            let data = {};
            if (ctHdr.includes('application/json')) {
                try {
                    data = await res.json();
                } catch (e) {
                    data = { success: false, error: 'Invalid JSON from server (HTTP ' + res.status + ').' };
                }
            } else {
                const txt = await res.text().catch(() => '');
                showPosMessagePopup(
                    'AI screenshot',
                    'HTTP ' +
                        res.status +
                        ': ' +
                        (txt ? String(txt).replace(/\s+/g, ' ').trim().slice(0, 280) : '(empty body)')
                );
                setStatus('');
                return;
            }
            await handleAiLinesResponse(data);
        }

        /** @param {{ blob?: Blob, textOnly?: string }} spec */
        async function runAiPayload(spec) {
            const blob = spec && spec.blob && spec.blob.size ? spec.blob : null;
            const textOnly = spec && spec.textOnly ? String(spec.textOnly).trim() : '';
            if (!blob && !textOnly) return;

            pick.disabled = true;
            if (analyzeBtn) analyzeBtn.disabled = true;
            setStatus(blob ? 'Reading image…' : 'Analyzing pasted text…');
            try {
                if (blob) {
                    const fd = new FormData();
                    fd.append('image', blob, blob instanceof File && blob.name ? blob.name : 'capture.png');
                    const hint = (pasteTa && pasteTa.value.trim()) || '';
                    if (hint) {
                        fd.append('text', hint.slice(0, AI_CLIPBOARD_TEXT_CAP));
                    }
                    await fetchAiLines({ method: 'POST', body: fd });
                } else {
                    await fetchAiLines({
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: textOnly.slice(0, AI_CLIPBOARD_TEXT_CAP) }),
                    });
                }
            } catch (err) {
                showPosMessagePopup('AI screenshot', err && err.message ? String(err.message) : 'Request failed.');
                setStatus('');
            } finally {
                pick.disabled = false;
                if (analyzeBtn) analyzeBtn.disabled = false;
            }
        }

        async function runBlob(blob) {
            if (!blob || !blob.size) return;
            await runAiPayload({ blob });
        }

        analyzeBtn?.addEventListener('click', async () => {
            const t = (pasteTa && pasteTa.value.trim()) || '';
            const drawerEl = document.getElementById('posAiScreenshotDrawer');
            const drawerHidden = drawerEl && drawerEl.classList.contains('hidden');

            if (!t) {
                if (drawerHidden && typeof reopenPosAiScreenshotPreviewFn === 'function' && reopenPosAiScreenshotPreviewFn()) {
                    return;
                }
                showPosMessagePopup('AI screenshot', 'Paste or type text in the AI field first.');
                return;
            }

            if (drawerHidden && typeof reopenPosAiScreenshotPreviewFn === 'function') {
                reopenPosAiScreenshotPreviewFn();
            }
            await runAiPayload({ textOnly: t });
        });

        if (statusEl) {
            statusEl.classList.add('pos-ai-capture-status--clickable');
            statusEl.title = 'Click to reopen AI preview';
            statusEl.addEventListener('click', () => {
                if (typeof reopenPosAiScreenshotPreviewFn === 'function') reopenPosAiScreenshotPreviewFn();
            });
        }

        fileEl.addEventListener('change', async () => {
            const f = fileEl.files && fileEl.files[0];
            fileEl.value = '';
            if (!f) return;
            await runBlob(f);
        });

        /** @param {DataTransfer | null} cd */
        function clipboardFirstImageFile(cd) {
            if (!cd || !cd.items) return null;
            const items = Array.from(cd.items);
            for (let i = 0; i < items.length; i++) {
                const it = items[i];
                if (it.kind === 'file') {
                    const f = it.getAsFile();
                    if (f && f.type && f.type.indexOf('image') === 0 && f.size > 0) return f;
                } else if (it.type && it.type.indexOf('image/') === 0) {
                    const f = it.getAsFile();
                    if (f && f.size > 0) return f;
                }
            }
            return null;
        }

        document.addEventListener(
            'paste',
            async (e) => {
                if (!toggle.checked) return;
                const cd = e.clipboardData;
                if (!cd) return;

                const ae = /** @type {HTMLElement | null} */ (document.activeElement);
                const isPasteBox = ae && ae.id === 'posAiCapturePaste';
                const isBarcodeFocus =
                    ae && (ae === barcodeInput || ae.id === 'barcode_input');

                const imageFile = clipboardFirstImageFile(cd);
                if (imageFile) {
                    const inOtherEditable =
                        ae &&
                        (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT') &&
                        !isBarcodeFocus &&
                        !isPasteBox;
                    if (inOtherEditable) return;

                    e.preventDefault();
                    await runBlob(imageFile);
                    return;
                }

                if (isPasteBox) return;

                if (
                    ae &&
                    (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT')
                ) {
                    if (!isBarcodeFocus) {
                        return;
                    }
                }

                let pastedText = '';
                try {
                    pastedText = String(cd.getData('text/plain') || '').replace(/\r\n/g, '\n');
                } catch (err) {
                    pastedText = '';
                }
                const trimmed = pastedText.trim();
                if (!trimmed) return;

                if (isBarcodeFocus) {
                    return;
                }

                if (!pasteTa) return;
                e.preventDefault();
                appendPasteBoxSnippet(trimmed);
                setStatus('Text added — tap Analyze when ready.');
            },
            true
        );
    }

    bindPosAiScreenshotCapture();

    document.addEventListener('keydown', (e) => {
        if (!(e.key === 'F1' || e.keyCode === 112)) return;
        const active = document.activeElement;
        if (active === barcodeInput || active?.id === 'barcode_input') {
            e.preventDefault();
            e.stopPropagation();
            openBarcodeLookupFromScan();
        }
    }, true);

    window.addEventListener('posShowCostPrefChanged', () => {
        renderCart();
        if (barcodeLookupModal && !barcodeLookupModal.classList.contains('hidden')) {
            loadBarcodeLookup(barcodeLookupSearch ? barcodeLookupSearch.value.trim() : '');
        }
    });

    if (barcodeLookupSearch) {
        barcodeLookupSearch.addEventListener('input', () => {
            scheduleBarcodeLookup(barcodeLookupSearch.value.trim());
        });
        barcodeLookupSearch.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            const first = barcodeLookupBody?.querySelector('.barcode-item-row');
            if (first) {
                e.preventDefault();
                first.focus();
            }
        });
    }
    if (barcodeLookupBody) {
        barcodeLookupBody.addEventListener('click', (e) => {
            const row = e.target.closest('.barcode-item-row');
            if (!row) return;
            addLineFromLookupRow(row);
        });
        barcodeLookupBody.addEventListener('keydown', (e) => {
            const row = e.target.closest('.barcode-item-row');
            if (!row) return;
            if (e.key === 'Enter') {
                e.preventDefault();
                addLineFromLookupRow(row);
                return;
            }
            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
            e.preventDefault();
            const rows = Array.from(barcodeLookupBody.querySelectorAll('.barcode-item-row'));
            const idx = rows.indexOf(row);
            const next = e.key === 'ArrowDown' ? rows[idx + 1] : rows[idx - 1];
            if (next) next.focus();
            else if (e.key === 'ArrowUp' && barcodeLookupSearch) barcodeLookupSearch.focus();
        });
    }
    if (btnBarcodeQtyApply) {
        btnBarcodeQtyApply.addEventListener('click', () => {
            addPendingLookupLineWithQty();
        });
    }
    if (barcodeQtyInput) {
        barcodeQtyInput.addEventListener('keydown', (e) => {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            addPendingLookupLineWithQty();
        });
    }

    if (btnNew) {
        btnNew.addEventListener('click', async () => {
            cart = [];
            clearBelowCostAlerts();
            promotionDiscount = 0;
            appliedVouchers = [];
            exitSalesReturnMode();
            renderCart();
            clearPosOrderNoField();
            await syncBillNoFromActiveTempBill();
            const hdrNew = buildSyncHeader();
            if (hdrNew.billno) {
                try {
                    await fetch('/pos-billing/cart-sync', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ header: hdrNew, lines: [] }),
                    });
                } catch (e) {
                    console.warn('cart-sync clear on New failed', e);
                }
            }
            if (customerDisplay) customerDisplay.textContent = '';
            setValue(customerCode, '');
            clearBillingCustomerMetrics();
            clearLoyaltyCustomerUi();
            syncCheckoutButtonLabel();
        });
    }

    if (btnSalesReturn) {
        btnSalesReturn.addEventListener('mousedown', (e) => {
            e.preventDefault();
        });
        btnSalesReturn.addEventListener('click', () => {
            if (salesReturnEnabled) {
                exitSalesReturnMode();
                return;
            }
            if (_salesReturnTapTimer) {
                clearTimeout(_salesReturnTapTimer);
                _salesReturnTapTimer = null;
                armSalesReturnSticky();
                return;
            }
            _salesReturnTapTimer = setTimeout(() => {
                _salesReturnTapTimer = null;
                armSalesReturnOneShot();
            }, 320);
        });
    }

    function posCartHasActiveLines() {
        return cart.some(
            (line) => !line.voided && Math.abs(Number(line.quantity) || 0) > 1e-9,
        );
    }

    /** @param {{ silent?: boolean, syncCart?: boolean }} [options] */
    async function holdCurrentBill(options) {
        const opts = options || {};
        if (!posCartHasActiveLines()) {
            return { ok: true, skipped: true };
        }
        const billnoRaw = (billNo?.value || '').trim();
        if (!billnoRaw) {
            return { ok: false, error: 'No bill number. Start a new bill first.' };
        }
        if (!posBillnoIsValid(billnoRaw)) {
            return { ok: false, error: 'Invalid bill number.' };
        }
        if (opts.syncCart !== false) {
            await pushPosHeaderSnapshotToTemp();
        }
        try {
            const res = await fetch('/pos-billing/hold', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ billno: billnoRaw }),
            });
            const data = await res.json();
            if (!data.success) {
                return { ok: false, error: data.error || 'Hold failed.' };
            }
            if (data.slip_text && !opts.silent) {
                presentPosHoldCancelSlip(data.slip_text, 'Held bill slip').catch(() => {});
            }
            return { ok: true, billno: billnoRaw, data };
        } catch (_e) {
            return { ok: false, error: 'Request failed.' };
        }
    }

    function normalizePathname(path) {
        const p = String(path || '/').replace(/\/+$/, '');
        return p || '/';
    }

    function hrefLeavesPosPage(href) {
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return false;
        try {
            const target = new URL(href, window.location.href);
            if (target.origin !== window.location.origin) return true;
            return normalizePathname(target.pathname) !== normalizePathname(window.location.pathname);
        } catch (_e) {
            return false;
        }
    }

    function hrefIsLogout(href) {
        if (!href) return false;
        const exitUrl = typeof window.__POS_LOGOUT_URL__ === 'string' ? window.__POS_LOGOUT_URL__.trim() : '';
        try {
            const target = new URL(href, window.location.href);
            const p = normalizePathname(target.pathname).toLowerCase();
            if (p === '/auth/logout' || p.endsWith('/logout')) return true;
            if (exitUrl) {
                const exit = new URL(exitUrl, window.location.href);
                if (normalizePathname(target.pathname) === normalizePathname(exit.pathname)) return true;
            }
            return false;
        } catch (_e) {
            return /logout/i.test(String(href));
        }
    }

    let _posNavHoldInFlight = false;

    function showPosNavHoldOverlay() {
        const ov = document.getElementById('posValidateOverlay');
        const lbl = document.getElementById('posValidateOverlayLabel');
        if (lbl) lbl.textContent = 'Saving hold before leaving…';
        if (ov) {
            ov.classList.remove('hidden');
            ov.setAttribute('aria-hidden', 'false');
        }
    }

    function hidePosNavHoldOverlay() {
        const ov = document.getElementById('posValidateOverlay');
        const lbl = document.getElementById('posValidateOverlayLabel');
        if (lbl) lbl.textContent = 'Validating bill…';
        if (ov) {
            ov.classList.add('hidden');
            ov.setAttribute('aria-hidden', 'true');
        }
    }

    function installPosNavigationAutoHold() {
        if (!document.body.classList.contains('pos-page')) return;

        document.addEventListener(
            'click',
            async (e) => {
                if (_posNavHoldInFlight) {
                    e.preventDefault();
                    e.stopPropagation();
                    return;
                }
                const anchor = e.target && e.target.closest ? e.target.closest('a[href]') : null;
                if (!anchor || anchor.hasAttribute('data-no-pos-hold-nav')) return;
                if (anchor.target === '_blank' || anchor.hasAttribute('download')) return;
                const href = anchor.getAttribute('href') || '';
                if (hrefIsLogout(href)) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (posCartHasActiveLines()) {
                        openPosLogoutCartWarnPopup();
                    } else {
                        window.location.href = anchor.href;
                    }
                    return;
                }
                if (!posCartHasActiveLines() || !hrefLeavesPosPage(href)) return;
                e.preventDefault();
                e.stopPropagation();
                _posNavHoldInFlight = true;
                showPosNavHoldOverlay();
                const result = await holdCurrentBill({ silent: true });
                hidePosNavHoldOverlay();
                if (!result.ok && !result.skipped) {
                    _posNavHoldInFlight = false;
                    showPosMessagePopup('Hold bill', result.error || 'Could not hold before leaving POS.');
                    return;
                }
                window.location.href = anchor.href;
            },
            true,
        );

        window.addEventListener('pagehide', () => {
            if (!posCartHasActiveLines()) return;
            const billnoRaw = (billNo?.value || '').trim();
            if (!posBillnoIsValid(billnoRaw)) return;
            try {
                fetch('/pos-billing/hold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ billno: billnoRaw }),
                    keepalive: true,
                });
            } catch (_e) {
                /* ignore */
            }
        });
    }

    if (btnHold) {
        btnHold.addEventListener('click', async () => {
            if (cart.length === 0) {
                setValue(voidBillNo, '');
                openModal('voidModal');
                setTimeout(() => voidBillNo.focus(), 100);
                return;
            }
            const result = await holdCurrentBill({ silent: false });
            if (result.skipped) return;
            if (!result.ok) {
                showPosMessagePopup('Hold bill', result.error || 'Hold failed.');
                return;
            }
            showPosMessagePopup('Bill held', 'Bill No ' + result.billno + ' hold saved.');
            await loadNextBill();
            renderCart();
            if (customerDisplay) customerDisplay.textContent = '';
            setValue(customerCode, '');
            clearBillingCustomerMetrics();
            clearLoyaltyCustomerUi();
            syncCheckoutButtonLabel();
        });
    }

    if (btnItemVoid) {
        btnItemVoid.addEventListener('click', async () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                showPosMessagePopup(
                    'Select a line',
                    'Select an item from the cart first (click on a line).'
                );
                return;
            }
            const line = cart[selectedLineIndex];
            if (line.voided) return;
            if (line.slno == null) return;
            line.voided = true;
            await apiCartLineVoid(line.slno);
            renderCart();
        });
    }

    if (btnChangeQty) {
        btnChangeQty.addEventListener('click', () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                showPosMessagePopup(
                    'Select a line',
                    'Select an item from the cart first (click on a line).'
                );
                return;
            }
            openChangeQtyModalForLine(selectedLineIndex);
        });
    }

    if (btnChangeQtyApply) {
        btnChangeQtyApply.addEventListener('click', async () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                closeModal('changeQtyModal');
                return;
            }
            const val = (changeQtyInput && changeQtyInput.value) ? parseFloat(changeQtyInput.value) : NaN;
            if (Number.isNaN(val) || val < 0) {
                showPosMessagePopup('Change quantity', 'Enter a valid quantity (0 or greater).');
                return;
            }
            const line = cart[selectedLineIndex];
            if (line.voided) {
                showPosMessagePopup('Change quantity', 'Cannot change qty for a voided item.');
                closeModal('changeQtyModal');
                return;
            }
            const multiplier = salesReturnEnabled ? -1 : 1;
            const qty = val * multiplier;
            if (qty === 0) {
                if (line.slno != null) {
                    const ok = await apiCartLineRemove(line.slno);
                    if (!ok) { closeModal('changeQtyModal'); return; }
                }
                cart.splice(selectedLineIndex, 1);
                if (selectedLineIndex !== null) {
                    if (selectedLineIndex >= cart.length) selectedLineIndex = cart.length - 1;
                    if (selectedLineIndex < 0) selectedLineIndex = null;
                }
                closeModal('changeQtyModal');
                renderCart();
                finishOneShotSalesReturnAfterScan();
                return;
            }
            const oldQty = Number(line.quantity);
            const oldBaseQty = Number(line.base_qty);
            const oldAmount = Number(line.amount);
            line.quantity = qty;
            line.base_qty = qty;
            line.amount = qty * line.rate - (Number(line.discount) || 0);
            if (line.slno != null) {
                const okUp = await apiCartLineUpdate(line.slno, qty);
                if (!okUp) {
                    line.quantity = oldQty;
                    line.base_qty = oldBaseQty;
                    line.amount = oldAmount;
                    closeModal('changeQtyModal');
                    renderCart();
                    return;
                }
            }
            closeModal('changeQtyModal');
            renderCart();
            finishOneShotSalesReturnAfterScan();
        });
    }

    if (changeQtyInput) {
        changeQtyInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (btnChangeQtyApply) btnChangeQtyApply.click();
            }
        });
    }

    if (btnChangePrice) {
        btnChangePrice.addEventListener('click', () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                showPosMessagePopup('Select a line', 'Select an item from the cart first (click on a line).');
                return;
            }
            openChangePriceModalForLine(selectedLineIndex);
        });
    }

    if (btnChangePriceApply) {
        btnChangePriceApply.addEventListener('click', async () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                closeModal('changePriceModal');
                return;
            }
            const raw = (changePriceInput && changePriceInput.value) ? String(changePriceInput.value).trim().replace(/,/g, '') : '';
            const val = raw === '' ? NaN : parseFloat(raw);
            if (Number.isNaN(val) || val < 0) {
                showPosMessagePopup('Change price', 'Enter a valid price (0 or greater).');
                return;
            }
            const line = cart[selectedLineIndex];
            if (line.voided) {
                showPosMessagePopup('Change price', 'Cannot change price for a voided item.');
                closeModal('changePriceModal');
                return;
            }
            const newRate = Math.round(val * 100) / 100;
            const catalog = lineCatalogPrice(line, line.rate);
            if (line.old_price == null || Number(line.old_price) <= 0) {
                line.old_price = catalog;
            }
            const oldRate = Number(line.rate);
            const oldAmount = Number(line.amount);
            line.rate = newRate;
            line.amount = Number(line.quantity) * newRate - (Number(line.discount) || 0);
            if (line.slno != null) {
                const okUp = await apiCartLineSetRate(line.slno, newRate);
                if (!okUp) {
                    line.rate = oldRate;
                    line.amount = oldAmount;
                    closeModal('changePriceModal');
                    renderCart();
                    return;
                }
            }
            closeModal('changePriceModal');
            renderCart();
        });
    }

    if (changePriceInput) {
        changePriceInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (btnChangePriceApply) btnChangePriceApply.click();
            }
        });
    }

    document.getElementById('changePriceKeypad')?.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-num]');
        if (!btn || !changePriceInput) return;
        const key = btn.getAttribute('data-num');
        let val = (changePriceInput.value || '0').toString().replace(/^0+(\d)|^0$/, '$1') || '0';
        if (key === 'back') {
            val = val.slice(0, -1) || '0';
        } else if (key === 'clear') {
            val = '0';
        } else {
            if (key === '.' && val.includes('.')) return;
            if (key !== '.' && val === '0' && key !== '.') val = '';
            val += key;
        }
        changePriceInput.value = val === '' ? '0' : val;
    });

    if (btnChangeAmount) {
        btnChangeAmount.addEventListener('click', () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                showPosMessagePopup('Select a line', 'Select an item from the cart first (click on a line).');
                return;
            }
            openChangeAmountModalForLine(selectedLineIndex);
        });
    }

    if (btnChangeAmountApply) {
        btnChangeAmountApply.addEventListener('click', async () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                closeModal('changeAmountModal');
                return;
            }
            const raw = (changeAmountInput && changeAmountInput.value) ? String(changeAmountInput.value).trim().replace(/,/g, '') : '';
            const val = raw === '' ? NaN : parseFloat(raw);
            if (Number.isNaN(val) || val < 0) {
                showPosMessagePopup('Change amount', 'Enter a valid amount (0 or greater).');
                return;
            }
            const line = cart[selectedLineIndex];
            if (line.voided) {
                showPosMessagePopup('Change amount', 'Cannot change amount for a voided item.');
                closeModal('changeAmountModal');
                return;
            }
            const qty = Number(line.quantity) || 0;
            if (Math.abs(qty) < 1e-9) {
                showPosMessagePopup('Change amount', 'Quantity must not be zero.');
                return;
            }
            const disc = Number(line.discount) || 0;
            // amount = qty * rate − discount  →  rate = (amount + discount) / qty
            const signedAmount = (qty < 0 ? -1 : 1) * Math.abs(val);
            const newRate = Math.round(((signedAmount + disc) / qty) * 100) / 100;
            if (!Number.isFinite(newRate) || newRate < 0) {
                showPosMessagePopup('Change amount', 'Could not derive a valid unit price from that amount.');
                return;
            }
            const catalog = lineCatalogPrice(line, line.rate);
            if (line.old_price == null || Number(line.old_price) <= 0) {
                line.old_price = catalog;
            }
            const oldRate = Number(line.rate);
            const oldAmount = Number(line.amount);
            const newAmount = Math.round((qty * newRate - disc) * 100) / 100;
            line.rate = newRate;
            line.amount = newAmount;
            if (line.slno != null) {
                const okUp = await apiCartLineSetRate(line.slno, newRate);
                if (!okUp) {
                    line.rate = oldRate;
                    line.amount = oldAmount;
                    closeModal('changeAmountModal');
                    renderCart();
                    return;
                }
            }
            closeModal('changeAmountModal');
            renderCart();
        });
    }

    if (changeAmountInput) {
        changeAmountInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (btnChangeAmountApply) btnChangeAmountApply.click();
            }
        });
    }

    document.getElementById('changeAmountKeypad')?.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-num]');
        if (!btn || !changeAmountInput) return;
        const key = btn.getAttribute('data-num');
        let val = (changeAmountInput.value || '0').toString().replace(/^0+(\d)|^0$/, '$1') || '0';
        if (key === 'back') {
            val = val.slice(0, -1) || '0';
        } else if (key === 'clear') {
            val = '0';
        } else {
            if (key === '.' && val.includes('.')) return;
            if (key !== '.' && val === '0' && key !== '.') val = '';
            val += key;
        }
        changeAmountInput.value = val === '' ? '0' : val;
    });

    if (btnLineDiscount) {
        btnLineDiscount.addEventListener('click', () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                showPosMessagePopup(
                    'Line discount',
                    'Select an item from the cart first (click on a line).'
                );
                return;
            }
            const line = cart[selectedLineIndex];
            if (line.voided) {
                showPosMessagePopup(
                    'Line discount',
                    'Cannot set discount for a voided item.'
                );
                return;
            }
            setValue(lineDiscountInput, Number(line.discount) || 0);
            openModal('lineDiscountModal');
            setTimeout(() => lineDiscountInput && lineDiscountInput.focus(), 100);
        });
    }

    if (btnLineDiscountApply) {
        btnLineDiscountApply.addEventListener('click', async () => {
            if (selectedLineIndex == null || selectedLineIndex < 0 || selectedLineIndex >= cart.length) {
                closeModal('lineDiscountModal');
                return;
            }
            const raw = (lineDiscountInput && lineDiscountInput.value) ? String(lineDiscountInput.value).trim() : '';
            const discParsed = raw === '' ? 0 : parseFloat(raw.replace(/,/g, ''));
            if (Number.isNaN(discParsed) || discParsed < 0) {
                showPosMessagePopup('Line discount', 'Enter a valid discount (0 or greater).');
                return;
            }
            const line = cart[selectedLineIndex];
            if (line.voided) {
                showPosMessagePopup('Line discount', 'Cannot set discount for a voided item.');
                closeModal('lineDiscountModal');
                return;
            }
            const lineGross = Math.abs(Number(line.quantity) * Number(line.rate));
            const discRounded = Math.round(discParsed * 100) / 100;
            if (discRounded > lineGross + 1e-6) {
                showPosMessagePopup('Line discount', 'Discount cannot exceed the line total (' + formatNum(lineGross) + ').');
                return;
            }
            if (line.slno != null) {
                const okUp = await apiCartLineSetDiscount(line.slno, discRounded);
                if (!okUp) return;
            }
            line.discount = discRounded;
            line.amount = Number(line.quantity) * Number(line.rate) - discRounded;
            closeModal('lineDiscountModal');
            renderCart();
        });
    }

    if (lineDiscountInput) {
        lineDiscountInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (btnLineDiscountApply) btnLineDiscountApply.click();
            }
        });
    }

    document.getElementById('lineDiscountKeypad')?.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-num]');
        if (!btn || !lineDiscountInput) return;
        const key = btn.getAttribute('data-num');
        let val = (lineDiscountInput.value || '0').toString().replace(/^0+(\d)|^0$/, '$1') || '0';
        if (key === 'back') {
            val = val.slice(0, -1) || '0';
        } else if (key === 'clear') {
            val = '0';
        } else if (key === '+10' || key === '+20' || key === '+50') {
            const add = parseInt(key.slice(1), 10);
            val = String((parseFloat(val) || 0) + add);
        } else {
            if (key === '.' && val.includes('.')) return;
            if (key !== '.' && val === '0' && key !== '.') val = '';
            val += key;
        }
        lineDiscountInput.value = val === '' ? '0' : val;
    });

    document.getElementById('changeQtyKeypad')?.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-num]');
        if (!btn || !changeQtyInput) return;
        const key = btn.getAttribute('data-num');
        let val = (changeQtyInput.value || '0').toString().replace(/^0+(\d)|^0$/, '$1') || '0';
        if (key === 'back') {
            val = val.slice(0, -1) || '0';
        } else if (key === 'clear') {
            val = '0';
        } else if (key === '+10' || key === '+20' || key === '+50') {
            const add = parseInt(key.slice(1), 10);
            val = String((parseFloat(val) || 0) + add);
        } else {
            if (key === '.' && val.includes('.')) return;
            if (key !== '.' && val === '0' && key !== '.') val = '';
            val += key;
        }
        changeQtyInput.value = val === '' ? '0' : val;
    });

    document.body.addEventListener('click', (e) => {
        const btn = e.target && e.target.id === 'btnItemDetails' ? e.target : e.target.closest && e.target.closest('#btnItemDetails');
        if (!btn) return;
        const barcodeInp = document.getElementById('itemDetailsBarcode');
        const resultDiv = document.getElementById('itemDetailsResult');
        const placeholderDiv = document.getElementById('itemDetailsPlaceholder');
        const errorDiv = document.getElementById('itemDetailsError');
        if (barcodeInp) barcodeInp.value = '';
        if (placeholderDiv) placeholderDiv.style.display = 'block';
        if (resultDiv) resultDiv.style.display = 'none';
        if (errorDiv) { errorDiv.style.display = 'none'; errorDiv.textContent = ''; }
        openModal('itemDetailsModal');
        setTimeout(() => barcodeInp && barcodeInp.focus(), 100);
    });

    async function doItemDetailsCheck() {
        const barcode = (itemDetailsBarcodeInput && itemDetailsBarcodeInput.value || '').toString().trim();
        const placeholderDiv = document.getElementById('itemDetailsPlaceholder');
        if (!barcode) {
            if (itemDetailsError) {
                itemDetailsError.textContent = 'Enter barcode or item code.';
                itemDetailsError.style.display = 'block';
            }
            if (placeholderDiv) placeholderDiv.style.display = 'block';
            if (itemDetailsResult) itemDetailsResult.style.display = 'none';
            return;
        }
        const item = await lookupItem(barcode);
        const codeEl = document.getElementById('itemDetailsItemCode');
        const barcodeEl = document.getElementById('itemDetailsBarcodeVal');
        const nameEl = document.getElementById('itemDetailsItemName');
        const uomEl = document.getElementById('itemDetailsUom');
        const priceEl = document.getElementById('itemDetailsRetailPrice');
        if (!item) {
            if (itemDetailsError) {
                itemDetailsError.textContent = lookupItem.lastError || 'Item not found.';
                itemDetailsError.style.display = 'block';
            }
            if (placeholderDiv) placeholderDiv.style.display = 'block';
            if (itemDetailsResult) itemDetailsResult.style.display = 'none';
            return;
        }
        if (itemDetailsError) itemDetailsError.style.display = 'none';
        if (placeholderDiv) placeholderDiv.style.display = 'none';
        if (codeEl) codeEl.textContent = item.itemcode != null ? String(item.itemcode) : '-';
        if (barcodeEl) barcodeEl.textContent = barcode;
        if (nameEl) nameEl.textContent = (item.itemname || '').trim() || '-';
        const uom = isPosWeightScanItem(item)
            ? 'KG'
            : ((item.barcode_uom != null && item.barcode_uom !== '') ? item.barcode_uom : (item.baseuom || 'PCS'));
        if (uomEl) uomEl.textContent = uom;
        let price = item.barcode_retail_price != null ? Number(item.barcode_retail_price) : (item.retailprice != null ? Number(item.retailprice) : 0);
        if (isPosWeightScanItem(item)) {
            price = Number(item.rate_per_kg ?? item.barcode_retail_price ?? item.retailprice) || 0;
        }
        if (priceEl) priceEl.textContent = formatNum(price);
        if (itemDetailsResult) itemDetailsResult.style.display = 'block';
    }

    if (btnItemDetailsCheck) btnItemDetailsCheck.addEventListener('click', doItemDetailsCheck);
    if (itemDetailsBarcodeInput) {
        itemDetailsBarcodeInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); doItemDetailsCheck(); }
        });
    }

    document.getElementById('itemDetailsKeypad')?.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-num]');
        if (!btn || !itemDetailsBarcodeInput) return;
        const key = btn.getAttribute('data-num');
        let val = (itemDetailsBarcodeInput.value || '').toString();
        if (key === 'back') {
            val = val.slice(0, -1);
        } else if (key === 'clear') {
            val = '';
        } else {
            if (key === '.' && val.includes('.')) return;
            val += key;
        }
        itemDetailsBarcodeInput.value = val;
    });

    document.body.addEventListener('click', async (e) => {
        const btn = e.target && e.target.id === 'btnVoidAll' ? e.target : e.target.closest && e.target.closest('#btnVoidAll');
        if (!btn) return;
        const billno = (billNo && billNo.value || '').trim();
        if (!billno) {
            showPosMessagePopup('Bill number', 'No bill number.');
            return;
        }
        const hasActiveLine = cart.some(
            (line) => !line.voided && Math.abs(Number(line.quantity) || 0) > 1e-9
        );
        if (!hasActiveLine) {
            showPosMessagePopup(
                'Void all',
                'At least one item is needed in the list.'
            );
            return;
        }
        const okVoidAll = await showPosConfirmPopup(
            'Void entire bill?',
            'Current bill will be moved to canceled and cart will be cleared.'
        );
        if (!okVoidAll) return;
        try {
            const res = await fetch('/pos-billing/void-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ billno: posBillnoForApi(billno) }),
            });
            const data = await res.json();
            if (data.success) {
                if (data.slip_text) {
                    presentPosHoldCancelSlip(data.slip_text, 'Canceled bill slip').catch(() => {});
                }
                selectedLineIndex = null;
                await loadNextBill();
                renderCart();
            } else {
                showPosMessagePopup('Void bill', data.error || 'Void All failed.');
            }
        } catch (err) {
            showPosMessagePopup('Void bill', 'Request failed.');
        }
    });

    if (btnVoid) {
        btnVoid.addEventListener('click', () => {
            setValue(voidBillNo, '');
            openModal('voidModal');
            setTimeout(() => voidBillNo.focus(), 100);
        });
    }

    if (btnVoidConfirm) {
        btnVoidConfirm.addEventListener('click', async () => {
            const billno = voidBillNo.value.trim();
            if (!billno) {
                showPosMessagePopup('Void bill', 'Enter bill number to void.');
                return;
            }
            try {
                const res = await fetch('/pos-billing/void', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ billno: posBillnoForApi(billno) }),
                });
                const data = await res.json();
                if (data.success) {
                    showPosMessagePopup('Void bill', 'Bill voided.');
                    closeModal('voidModal');
                } else {
                    showPosMessagePopup('Void bill', data.error || 'Void failed.');
                }
            } catch (e) {
                showPosMessagePopup('Void bill', 'Request failed.');
            }
        });
    }

    function mapHeldLinesToCart(lines) {
        return (lines || []).map((l) => {
            const qty = Number(l.quantity) || 0;
            const rate = Number(l.rate) || 0;
            const disc = Number(l.discount) || 0;
            const amt = l.amount != null ? Number(l.amount) : Math.max(0, qty * rate - disc);
            const itemFlag = l.item_flag != null ? Number(l.item_flag) : 1;
            return {
                slno: l.slno != null ? Number(l.slno) : undefined,
                item_code: l.item_code,
                barcode: l.manufacturerid || l.manufacturer_id || l.barcode || '',
                manufacturerid: l.manufacturerid || l.manufacturer_id || l.barcode || '',
                item_name:
                    l.item_name != null && l.item_name !== ''
                        ? String(l.item_name)
                        : String(l.item_code != null ? l.item_code : ''),
                uom: l.uom != null && l.uom !== '' ? String(l.uom) : 'PCS',
                quantity: qty,
                rate: rate,
                discount: disc,
                amount: amt,
                base_qty: l.base_qty != null ? Number(l.base_qty) : qty,
                cost: Number(l.cost) || 0,
                costprice: Number(l.costprice || l.cost) || 0,
                averagecost: Number(l.averagecost || l.average_cost) || 0,
                item_factor: Number(l.item_factor || l.conversion_factor || 1) || 1,
                store: l.store || '',
                default_bin_storage_id: l.default_bin_storage_id || l.bin_storage_id || null,
                bin_storage_id: l.bin_storage_id || l.default_bin_storage_id || null,
                voided: itemFlag === 0,
            };
        });
    }

    function applyHeldBillHeaderToUi(header) {
        const h = header || {};
        if (h.customercode && customerDisplay) customerDisplay.textContent = String(h.customercode);
        if (h.customercode != null && customerCode) setValue(customerCode, h.customercode);
        const lccRaw = h.loyaltycustomercode;
        const lccNum = lccRaw != null ? Number(lccRaw) : 0;
        if (lccNum) {
            if (loyaltyCustomerDisplay) loyaltyCustomerDisplay.textContent = String(lccRaw);
            if (loyaltyCustomerCode) setValue(loyaltyCustomerCode, String(lccRaw));
        } else {
            clearLoyaltyCustomerUi();
        }
        applyOrderNoFromLoadedHeader(h);
        const ccApiRh = (customerCode?.value || '').trim();
        if (ccApiRh && ccApiRh !== '0') {
            refreshCustomerMetricsFromApi(ccApiRh, 'billing');
        } else {
            clearBillingCustomerMetrics();
        }
        const lcApiRh = (loyaltyCustomerCode?.value || '').trim();
        if (lcApiRh && lcApiRh !== '0') {
            refreshCustomerMetricsFromApi(lcApiRh, 'loyalty');
        }
    }

    /** Load held bill (H→P) into cart; used by void modal retrieve and ?billno= deep link. */
    async function loadHeldBillByBillno(billnoRaw, options) {
        const opts = options || {};
        const billnoStr = String(billnoRaw == null ? '' : billnoRaw).trim();
        if (!billnoStr) {
            return { ok: false, error: 'Enter bill number to retrieve.' };
        }
        if (!posBillnoIsValid(billnoStr)) {
            return { ok: false, error: 'Invalid bill number.' };
        }
        try {
            const res = await fetch('/pos-billing/held-bill?billno=' + encodeURIComponent(billnoStr));
            const data = await res.json();
            if (data.success) {
                cart = mapHeldLinesToCart(data.lines || []);
                setValue(billNo, billnoStr);
                const retrieveRes = await fetch('/pos-billing/retrieve-hold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ billno: billnoStr }),
                });
                const retrieveData = await retrieveRes.json();
                if (!retrieveData.success) {
                    return { ok: false, error: retrieveData.error || 'Retrieve failed.' };
                }
                promotionDiscount = 0;
                appliedVouchers = [];
                exitSalesReturnMode();
                if (opts.closeVoidModal) closeModal('voidModal');
                renderCart();
                applyHeldBillHeaderToUi(data.header || {});
                syncCheckoutButtonLabel();
                return { ok: true };
            }
            const tempRes = await fetch('/pos-billing/verify/temp-bill?billno=' + encodeURIComponent(billnoStr));
            const tempData = await tempRes.json();
            if (!tempData.success) {
                return { ok: false, error: data.error || tempData.error || 'Held bill not found.' };
            }
            cart = mapHeldLinesToCart(tempData.lines || []);
            setValue(billNo, billnoStr);
            promotionDiscount = 0;
            appliedVouchers = [];
            exitSalesReturnMode();
            if (opts.closeVoidModal) closeModal('voidModal');
            renderCart();
            applyHeldBillHeaderToUi(tempData.header || {});
            syncCheckoutButtonLabel();
            return { ok: true };
        } catch (_e) {
            return { ok: false, error: 'Request failed.' };
        }
    }

    function stripPosBillnoFromUrl() {
        try {
            const sp = new URLSearchParams(window.location.search || '');
            if (!sp.has('billno')) return;
            sp.delete('billno');
            const qs = sp.toString();
            const next = window.location.pathname + (qs ? '?' + qs : '') + (window.location.hash || '');
            history.replaceState({}, '', next);
        } catch (_e) {
            /* ignore */
        }
    }

    /** Block browser Back from leaving POS (e.g. after Counter Operations redirect). */
    function installPosBackNavigationGuard() {
        if (!document.body.classList.contains('pos-page')) return;
        try {
            const anchor = window.location.pathname + window.location.search + (window.location.hash || '');
            history.replaceState({ posPage: 1 }, '', anchor);
            history.pushState({ posPage: 1 }, '', anchor);
            window.addEventListener('popstate', () => {
                history.pushState(
                    { posPage: 1 },
                    '',
                    window.location.pathname + window.location.search + (window.location.hash || '')
                );
            });
        } catch (_e) {
            /* ignore */
        }
    }

    async function loadHeldBillFromQueryParam() {
        let raw = '';
        try {
            const sp = new URLSearchParams(window.location.search || '');
            raw = (sp.get('billno') || '').trim();
        } catch (_e) {
            return false;
        }
        if (!raw || !/^\d+$/.test(raw)) return false;
        const result = await loadHeldBillByBillno(raw);
        if (!result.ok) {
            showPosMessagePopup('Retrieve hold', result.error || 'Could not open held bill.');
            stripPosBillnoFromUrl();
            return false;
        }
        stripPosBillnoFromUrl();
        await syncOpenShiftGateAndBillDate();
        if (barcodeInput) focusPosBarcodeScanIfNoBlockingGate();
        return true;
    }

    if (btnRetrieveHold) {
        btnRetrieveHold.addEventListener('click', async () => {
            const billno = voidBillNo.value.trim();
            if (!billno) {
                showPosMessagePopup('Retrieve hold', 'Enter bill number to retrieve.');
                return;
            }
            const result = await loadHeldBillByBillno(billno, { closeVoidModal: true });
            if (!result.ok) {
                showPosMessagePopup('Retrieve hold', result.error || 'Retrieve failed.');
            }
        });
    }

    function getNetTotal() {
        const activeLines = cart.filter(line => !line.voided);
        let totalAmt = 0;
        let totalDisc = 0;
        activeLines.forEach(line => {
            totalAmt += line.quantity * line.rate;
            totalDisc += Number(line.discount) || 0;
        });
        return totalAmt - totalDisc - promotionDiscount;
    }

    const checkoutBtnPaymentHtml = '<span class="arrow">→</span> Payment';
    const checkoutBtnValidateHtml = '<span class="arrow">→</span> Validate';

    function billingCustomerSelected() {
        const code = (customerCode?.value || '').trim();
        return !!code && code !== '0';
    }

    function syncCheckoutButtonLabel() {
        if (!btnCheckout) return;
        const selected = billingCustomerSelected();
        btnCheckout.innerHTML = selected ? checkoutBtnValidateHtml : checkoutBtnPaymentHtml;
        btnCheckout.setAttribute('aria-label', selected ? 'Validate and post sale' : 'Payment');
    }

    const checkoutRemainingEl = document.getElementById('checkout_remaining');
    const checkoutRemainingLabelEl = document.getElementById('checkout_remaining_label');
    const checkoutChangeEl = document.getElementById('checkout_change');
    const checkoutChangeLabelEl = document.getElementById('checkout_change_label');
    const checkoutTotalDueEl = document.getElementById('checkout_total_due');
    const checkoutSummaryLinesEl = document.getElementById('checkoutSummaryLines');

    function updateCheckoutTotals() {
        const netTotal = parseFloat(checkoutNetTotalEl?.value || '0') || 0;
        const amountsMap = getPaymentAmountsFromDom();
        const totalPaid = totalPaidFromAmountMap(amountsMap);
        const isRefundBill = netTotal < -0.005;
        const netNearZero = Math.abs(netTotal) < 0.005;
        const remaining = Math.max(0, netTotal - totalPaid);
        const payCustomerOrChange = Math.max(0, totalPaid - netTotal);
        if (checkoutTotalPaidEl) checkoutTotalPaidEl.value = formatNum(totalPaid);
        if (checkoutRemainingEl) checkoutRemainingEl.textContent = isRefundBill ? '—' : formatNum(remaining);
        if (checkoutRemainingLabelEl)
            checkoutRemainingLabelEl.textContent = isRefundBill ? '—' : 'Remaining';
        if (checkoutChangeEl) checkoutChangeEl.textContent = formatNum(payCustomerOrChange);
        if (checkoutChangeLabelEl)
            checkoutChangeLabelEl.textContent = isRefundBill ? 'Pay customer' : 'Change';
        if (checkoutTotalDueEl) checkoutTotalDueEl.textContent = formatNum(netTotal);
        if (checkoutSummaryLinesEl) {
            const lines = [];
            for (const t of checkoutTenders) {
                const code = String(t.tender_code || '').toUpperCase();
                const amt = amountsMap[code] || 0;
                if (amt > 0) lines.push({ name: tenderDisplayName(code), amt });
            }
            for (const [code, amt] of Object.entries(amountsMap)) {
                if (amt <= 0 || checkoutTenders.some(x => String(x.tender_code || '').toUpperCase() === code)) continue;
                lines.push({ name: tenderDisplayName(code), amt });
            }
            checkoutSummaryLinesEl.innerHTML = lines.length
                ? lines.map(l => `<div class="payment-summary-line"><span class="method">${escapeHtmlPos(l.name)}</span><span class="amt">${formatNum(l.amt)}</span></div>`).join('')
                : '<div class="payment-summary-line payment-summary-line--empty">No payments yet</div>';
        }
        if (checkoutValidationMsg) {
            const diff = Math.abs(totalPaid - netTotal);
            if (isRefundBill) {
                checkoutValidationMsg.textContent =
                    'Refund: pay customer ' + formatNum(payCustomerOrChange) + '. Validate to print.';
                checkoutValidationMsg.style.color = '#0f766e';
            } else if (netNearZero) {
                if (diff < 0.01) {
                    checkoutValidationMsg.textContent = 'No amount due. Validate to print.';
                    checkoutValidationMsg.style.color = '#0f766e';
                } else if (totalPaid > netTotal + 0.005) {
                    checkoutValidationMsg.innerHTML =
                        'Change: <span class="payment-validation-msg__change-amt">' +
                        escapeHtmlPos(formatNum(payCustomerOrChange)) +
                        '</span>';
                    checkoutValidationMsg.style.color = '';
                } else {
                    checkoutValidationMsg.textContent = '';
                    checkoutValidationMsg.style.color = '';
                }
            } else if (diff < 0.01) {
                checkoutValidationMsg.textContent = 'Amount matches.';
                checkoutValidationMsg.style.color = '#0f766e';
            } else if (totalPaid < netTotal) {
                checkoutValidationMsg.textContent = 'Total payment must equal amount to pay. (Paid is less than amount due.)';
                checkoutValidationMsg.style.color = '#dc2626';
            } else {
                checkoutValidationMsg.innerHTML =
                    'Change: <span class="payment-validation-msg__change-amt">' +
                    escapeHtmlPos(formatNum(payCustomerOrChange)) +
                    '</span>';
                checkoutValidationMsg.style.color = '';
            }
        }
    }

    document.getElementById('paymentKeypad')?.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-num]');
        if (!btn || !selectedPaymentInput) return;
        const key = btn.getAttribute('data-num');
        let val = (selectedPaymentInput.value || '0').toString().replace(/^0+(\d)|^0$/, '$1') || '0';
        if (key === 'back') {
            val = val.slice(0, -1) || '0';
        } else if (key === 'clear') {
            val = '0';
        } else if (key === '+10' || key === '+20' || key === '+50') {
            const add = parseInt(key.slice(1), 10);
            val = formatNum((parseFloat(val) || 0) + add);
        } else {
            if (key === '.' && val.includes('.')) return;
            if (key !== '.' && val === '0' && key !== '.') val = '';
            val += key;
        }
        selectedPaymentInput.value = val === '' ? '0' : val;
        updateCheckoutTotals();
    });

    /**
     * @param {Record<string, number> | { cash?: number, card?: number, loyalty?: number, points?: number } | null} paymentOverride - optional tender amounts (legacy keys or tender codes)
     */
    async function executePosSaleSubmission(paymentOverride) {
        if (posCheckoutSubmitInFlight) {
            return;
        }
        posCheckoutSubmitInFlight = true;
        setPosCheckoutActionsDisabled(true);
        try {
        const netTotal = parseFloat(checkoutNetTotalEl?.value || '0') || 0;
        const amountsMap = resolvePaymentAmountMap(paymentOverride);
        const customercode = customerCode?.value?.trim() || '0';
        const customercodeNum = parseInt(customercode, 10);
        const isCreditSale = Number.isFinite(customercodeNum) && customercodeNum > 0;
        if (isCreditSale) {
            const creditCheck = await verifyCreditSaleAllowed(netTotal);
            if (!creditCheck.ok) {
                showPosMessagePopup('Credit limit', creditCheck.message || 'Credit sale not allowed.');
                syncBillingCustomerCreditWarn(netTotal);
                return;
            }
        }
        const totalPaid = totalPaidFromAmountMap(amountsMap);
        const diff = Math.abs(totalPaid - netTotal);
        if (!isCreditSale && netTotal > 0.005 && totalPaid < netTotal && diff >= 0.01) {
            showPosMessagePopup('Payment', 'Total payment must equal amount to pay. You have paid less than the amount due.');
            return;
        }
        const changeDue = isCreditSale ? 0 : Math.max(0, totalPaid - netTotal);
        const payParts = [];
        if (isCreditSale) {
            payParts.push('Credit / receivable');
        } else {
            const seen = new Set();
            for (const t of checkoutTenders) {
                const code = String(t.tender_code || '').toUpperCase();
                const amt = amountsMap[code] || 0;
                if (amt >= 0.01) {
                    payParts.push(tenderDisplayName(code));
                    seen.add(code);
                }
            }
            for (const [code, amt] of Object.entries(amountsMap)) {
                if (amt < 0.01 || seen.has(code.toUpperCase())) continue;
                payParts.push(tenderDisplayName(code));
            }
        }
        const paymentTypeLabel = payParts.length ? payParts.join(' + ') : isCreditSale ? 'Credit / receivable' : 'Cash';
        const customername = (customerDisplay?.textContent || '').trim();
        const loyaltycustomercode = loyaltyCustomerCode?.value?.trim() || '0';
        const loyaltycustomername = (loyaltyCustomerDisplay?.textContent || '').trim();
        let remarks = '';
        if (!isCreditSale) {
            const seenRm = new Set();
            for (const t of checkoutTenders) {
                const code = String(t.tender_code || '').toUpperCase();
                const amt = amountsMap[code] || 0;
                if (amt < 0.01) continue;
                remarks +=
                    (remarks ? '; ' : '') + tenderDisplayName(code) + ': ' + formatNum(amt);
                seenRm.add(code);
            }
            for (const [code, amt] of Object.entries(amountsMap)) {
                if (amt < 0.01 || seenRm.has(code.toUpperCase())) continue;
                remarks +=
                    (remarks ? '; ' : '') + tenderDisplayName(code) + ': ' + formatNum(amt);
            }
        } else {
            remarks = 'On-account sale (receivable)';
        }
        let loyaltyReceiptLine = '';
        if (
            loyaltycustomercode
            && loyaltycustomercode !== '0'
            && loyaltycustomername
        ) {
            remarks += (remarks ? '; ' : '') + 'Loyalty: ' + loyaltycustomername + ' (' + loyaltycustomercode + ')';
            const cardDispRaw = loyaltyCardnoDisplay ? String(loyaltyCardnoDisplay.textContent || '').trim() : '';
            const cardDisp = cardDispRaw && cardDispRaw !== '—' ? cardDispRaw : '';
            loyaltyReceiptLine = loyaltycustomername + (cardDisp ? ' ' + cardDisp : '');
        }
        let totalPointsReceipt = 0;
        const ptsDisp = loyaltyPointsDisplay ? String(loyaltyPointsDisplay.textContent || '').trim() : '';
        if (ptsDisp && ptsDisp !== '—') {
            const pn = parseFloat(ptsDisp.replace(/,/g, ''));
            if (Number.isFinite(pn)) totalPointsReceipt = pn;
        }

        let grossPreDisc = 0;
        cart
            .filter(line => !line.voided && (Number(line.quantity) || 0) !== 0)
            .forEach(line => {
                grossPreDisc += Number(line.quantity) * Number(line.rate);
            });
        const bill_discount_total = Math.max(0, grossPreDisc - netTotal);

        const receipt_extras = {
            credit_sale: isCreditSale,
            tender_total: isCreditSale ? netTotal : totalPaid,
            change: changeDue,
            payment_type_label: paymentTypeLabel,
            loyalty_customer_line: loyaltyReceiptLine,
            total_points: totalPointsReceipt,
            net_bill_total: netTotal,
            bill_discount_total,
        };
        if (appliedVouchers.length) {
            const voucherText = appliedVouchers.map(v => v.code + '(' + v.message + ')').join(', ');
            remarks = (remarks ? remarks + '; ' : '') + 'Voucher: ' + voucherText + (promotionDiscount ? '; Promo disc: ' + promotionDiscount : '');
        }
        if (!isCreditSale && changeDue >= 0.01) {
            remarks = (remarks ? remarks + '; ' : '') + 'Change: ' + formatNum(changeDue);
        }
        const saveAmountsMap = isCreditSale ? amountsMap : netAmountsMapAfterChange(amountsMap, changeDue);
        /** @type {{ code: string, amount: number, reference?: string }[]} */
        const payment_modes = [];
        if (isCreditSale) {
            payment_modes.push({ code: 'CREDIT', amount: netTotal, reference: '' });
        } else {
            const seenPm = new Set();
            for (const t of checkoutTenders) {
                const code = String(t.tender_code || '').toUpperCase();
                const amt = saveAmountsMap[code] || 0;
                if (amt >= 0.01) {
                    payment_modes.push({ code: code.slice(0, 30), amount: amt, reference: '' });
                    seenPm.add(code);
                }
            }
            for (const [code, amt] of Object.entries(saveAmountsMap)) {
                if (amt < 0.01 || seenPm.has(code.toUpperCase())) continue;
                payment_modes.push({
                    code: code.toUpperCase().slice(0, 30),
                    amount: amt,
                    reference: '',
                });
            }
        }
        const leg = aggregateLegacyBuckets(saveAmountsMap);
        let countercode = 0;
        const ctrSaveRaw = (counterCodeEl?.value || '').trim();
        if (ctrSaveRaw) {
            const ctp = parseInt(ctrSaveRaw, 10);
            if (Number.isFinite(ctp)) countercode = ctp;
        }
        const header = {
            billno: posBillnoForApi(billNo?.value),
            countercode,
            customercode: customercode === '' ? 0 : customercode,
            customername: customername || '',
            loyaltycustomercode: loyaltycustomercode === '' || loyaltycustomercode === '0' ? 0 : loyaltycustomercode,
            cashamount: isCreditSale ? 0 : leg.cash,
            cardamount: isCreditSale ? 0 : leg.card,
            walletamount: isCreditSale ? 0 : leg.wallet,
            loyaltyamount: isCreditSale ? 0 : leg.loyalty,
            pointsamount: isCreditSale ? 0 : leg.points,
            payment_modes,
            remarks: remarks,
        };
        const lastBillSummarySnapshot = {
            net: netTotal,
            paid: isCreditSale ? netTotal : totalPaid,
            change: changeDue,
            billno: header.billno,
        };
        const onRawCh = (posOrderNoEl?.value || '').trim();
        if (onRawCh) header.orderno = onRawCh.slice(0, 80);
        const lines = cart
            .filter(line => !line.voided && (Number(line.quantity) || 0) !== 0)
            .map(line => ({
                item_code: line.item_code,
                item_name: line.item_name || '',
                manufacturerid: line.manufacturerid || line.barcode || '',
                uom: line.uom,
                quantity: line.quantity,
                rate: line.rate,
                old_price: lineCatalogPrice(line, line.rate),
                discount: line.discount || 0,
                base_qty: line.base_qty ?? line.quantity,
                cost: line.cost || 0,
                costprice: line.costprice || line.cost || 0,
                averagecost: line.averagecost || 0,
                item_factor: line.item_factor || 1,
                store: line.store || '',
                default_bin_storage_id: line.default_bin_storage_id || line.bin_storage_id || null,
                bin_storage_id: line.bin_storage_id || line.default_bin_storage_id || null,
            }));
        const checkoutT0 = performance.now();
        let saveMs = 0;
        let receiptMs = 0;
        let receiptMeta = { mode: 'none', qz_print_ms: null };
        let nextBillMs = 0;
        let saveQueued = false;
        let saveSucceeded = false;

        showValidateOverlay('Completing sale…');
        try {
            const tSave0 = performance.now();
            const { res, data } = await posPostJson('/pos-billing/save', { header, lines, receipt_extras });
            saveMs = performance.now() - tSave0;
            if (data.success) {
                saveSucceeded = true;
                saveQueued = !!data.queued;
                lastBillSummarySnapshot.billno =
                    data.billno != null ? data.billno : data.posted_billno != null ? data.posted_billno : lastBillSummarySnapshot.billno;
                showLastBillSummary(lastBillSummarySnapshot);
                closeModal('checkoutModal');
                const queuedMsg = data.queued ? `Queued for background posting. Job #${data.queue_job_id || ''}` : '';
                const tReceipt0 = performance.now();
                const nextBillPromise = data.queued
                    ? moveToNextBillAfterQueue()
                    : (async () => {
                          await loadNextBill();
                          renderCart();
                          if (customerDisplay) customerDisplay.textContent = '';
                          setValue(customerCode, '');
                          clearBillingCustomerMetrics();
                          clearLoyaltyCustomerUi();
                          syncCheckoutButtonLabel();
                      })();
                const rtCheckout = typeof data.receipt_text === 'string' ? data.receipt_text.trimEnd() : '';
                const hasRcptObj = data.receipt && typeof data.receipt === 'object';
                if (hasRcptObj || rtCheckout) {
                    receiptMeta = await presentPosReceiptAfterSale(
                        hasRcptObj ? data.receipt : null,
                        rtCheckout || '',
                        queuedMsg,
                    );
                } else {
                    onReceiptSaved(data);
                }
                receiptMs = performance.now() - tReceipt0;
                const tNext0 = performance.now();
                await nextBillPromise;
                nextBillMs = performance.now() - tNext0;
            } else {
                const title = data.pos_credit_accounts_error ? 'Credit limit / accounts' : 'Save sale';
                if (data.save_session_locked || res.status === 423) {
                    syncPosSaveNonceFromResponse(data);
                    showPosMessagePopup(
                        title,
                        data.error || 'A save is already in progress. Please wait for it to finish.'
                    );
                } else if (data.replay_blocked || res.status === 409) {
                    syncPosSaveNonceFromResponse(data);
                    showPosMessagePopup(
                        title,
                        data.error ||
                            'Duplicate save request after retry. Wait a moment, then validate / checkout again.'
                    );
                } else {
                    syncPosSaveNonceFromResponse(data);
                    showPosMessagePopup(title, data.error || 'Save failed.');
                }
            }
        } catch (e) {
            showPosMessagePopup('Save sale', 'Save request failed.');
        } finally {
            const totalMs = performance.now() - checkoutT0;
            hideValidateOverlay();
            if (posCheckoutTimingEnabled()) {
                const timingPayload = {
                    save_ms: Math.round(saveMs * 1000) / 1000,
                    receipt_ms: Math.round(receiptMs * 1000) / 1000,
                    receipt_mode: receiptMeta.mode,
                    qz_print_ms:
                        receiptMeta.qz_print_ms != null
                            ? Math.round(receiptMeta.qz_print_ms * 1000) / 1000
                            : null,
                    next_bill_ms: Math.round(nextBillMs * 1000) / 1000,
                    overlay_total_ms: Math.round(totalMs * 1000) / 1000,
                    queued: saveQueued,
                    success: saveSucceeded,
                };
                console.info('[POS_CHECKOUT_TIMING]', timingPayload);
                fetch('/pos-billing/client-checkout-timing', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(timingPayload),
                }).catch(() => {});
            }
        }
        } finally {
            posCheckoutSubmitInFlight = false;
            setPosCheckoutActionsDisabled(false);
        }
    }

    if (btnCheckout) {
        btnCheckout.addEventListener('click', async () => {
            if (cart.filter(l => !l.voided).length === 0) {
                showPosMessagePopup('Checkout', 'Add at least one item.');
                return;
            }
            if (billingCustomerSelected()) {
                const netTotal = getNetTotal();
                if (checkoutNetTotalEl) checkoutNetTotalEl.value = formatNum(netTotal);
                const tender =
                    netTotal > 0.005
                        ? { cash: netTotal, card: 0, loyalty: 0, points: 0 }
                        : { cash: 0, card: 0, loyalty: 0, points: 0 };
                await executePosSaleSubmission(tender);
                return;
            }
            const netTotal = getNetTotal();
            if (checkoutNetTotalEl) checkoutNetTotalEl.value = formatNum(netTotal);
            try {
                await checkoutTendersLoadPromise;
            } catch (_e) {
                /* renderCheckoutPaymentRows runs in finally-like paths */
            }
            resetAllCheckoutPaymentInputs();
            if (checkoutTotalPaidEl) setValue(checkoutTotalPaidEl, '0.00');
            if (checkoutValidationMsg) checkoutValidationMsg.textContent = '';
            const custNameEl = document.getElementById('checkout_customer_name');
            const checkoutLoyaltyEl = document.getElementById('checkout_loyalty_customer');
            const billNoEl = document.getElementById('checkout_bill_no');
            if (custNameEl) custNameEl.textContent = (customerDisplay?.textContent || '').trim() || '—';
            if (checkoutLoyaltyEl) {
                const lt = (loyaltyCustomerDisplay?.textContent || '').trim();
                const lc = (loyaltyCustomerCode?.value || '').trim();
                if (lc && lc !== '0' && lt) {
                    checkoutLoyaltyEl.textContent = 'Loyalty: ' + lt + (lc ? ' (' + lc + ')' : '');
                } else {
                    checkoutLoyaltyEl.textContent = '';
                }
            }
            if (billNoEl) billNoEl.textContent = (billNo?.value || '').trim() || '—';
            selectDefaultCheckoutPaymentRow();
            openModal('checkoutModal');
            updateCheckoutTotals();
        });
    }

    if (btnCheckoutConfirm) {
        btnCheckoutConfirm.addEventListener('click', async () => {
            await executePosSaleSubmission(null);
        });
    }

    if (btnPrintReceiptPreview) {
        btnPrintReceiptPreview.addEventListener('click', async () => {
            if (!String(lastReceiptPreviewText || '').trim()) {
                showPosMessagePopup('Receipt', 'No receipt to print.');
                return;
            }
            const oldText = btnPrintReceiptPreview.textContent;
            btnPrintReceiptPreview.disabled = true;
            btnPrintReceiptPreview.textContent = 'Printing...';
            if (receiptPreviewStatus) receiptPreviewStatus.textContent = '';
            try {
                const copiesPrinted = await printReceiptPreviewViaQz();
                if (receiptPreviewStatus) {
                    receiptPreviewStatus.textContent =
                        copiesPrinted > 1
                            ? 'Print sent to QZ Tray (' + copiesPrinted + ' copies — zero/refund bill).'
                            : 'Print sent to QZ Tray.';
                    receiptPreviewStatus.style.color = '#0f766e';
                }
                closeModal('receiptPreviewModal');
            } catch (e) {
                if (receiptPreviewStatus) {
                    receiptPreviewStatus.textContent = e.message || 'Print failed.';
                    receiptPreviewStatus.style.color = '#dc2626';
                } else {
                    showPosMessagePopup('Print', e.message || 'Print failed.');
                }
            } finally {
                btnPrintReceiptPreview.disabled = false;
                btnPrintReceiptPreview.textContent = oldText;
            }
        });
    }

    document.querySelectorAll('.pos-keypad [data-key]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const key = btn.getAttribute('data-key');
            if (key === 'payment') {
                if (btnCheckout) btnCheckout.click();
            } else {
                if (barcodeInput) {
                    barcodeInput.value += key;
                    barcodeInput.focus();
                }
            }
        });
    });

    const posLogoutModalTitleEl = document.getElementById('posLogoutModalTitle');
    const posLogoutModalTextEl = document.getElementById('posLogoutModalText');
    const posLogoutModalActionsWarn = document.getElementById('posLogoutModalActionsWarn');
    const posLogoutModalActionsConfirm = document.getElementById('posLogoutModalActionsConfirm');
    const btnPosLogoutModalOk = document.getElementById('btnPosLogoutModalOk');
    const btnPosLogoutModalConfirm = document.getElementById('btnPosLogoutModalConfirm');

    function openPosLogoutCartWarnPopup() {
        if (!posLogoutModalTextEl) return;
        if (posLogoutModalTitleEl) posLogoutModalTitleEl.textContent = 'Cannot log out';
        posLogoutModalTextEl.textContent =
            'You have items in the cart. Hold or void all lines before logging out.';
        if (posLogoutModalActionsWarn) posLogoutModalActionsWarn.style.display = 'flex';
        if (posLogoutModalActionsConfirm) posLogoutModalActionsConfirm.style.display = 'none';
        openModal('posLogoutModal');
    }

    function openPosLogoutConfirmPopup() {
        if (!posLogoutModalTextEl) return;
        if (posLogoutModalTitleEl) posLogoutModalTitleEl.textContent = 'Log out';
        posLogoutModalTextEl.textContent = 'Leave POS billing and return to the dashboard?';
        if (posLogoutModalActionsWarn) posLogoutModalActionsWarn.style.display = 'none';
        if (posLogoutModalActionsConfirm) posLogoutModalActionsConfirm.style.display = 'flex';
        openModal('posLogoutModal');
    }

    function showPosLogoutNavigatingOverlay() {
        const ov = document.getElementById('posLogoutOverlay');
        if (!ov) return;
        ov.classList.remove('hidden');
        ov.setAttribute('aria-hidden', 'false');
    }

    if (btnPosLogoutModalOk) {
        btnPosLogoutModalOk.addEventListener('click', () => closeModal('posLogoutModal'));
    }
    if (btnPosLogoutModalConfirm) {
        btnPosLogoutModalConfirm.addEventListener('click', () => {
            btnPosLogoutModalConfirm.disabled = true;
            showPosLogoutNavigatingOverlay();
            requestAnimationFrame(() => {
                window.setTimeout(() => {
                    const u = typeof window.__POS_LOGOUT_URL__ === 'string' ? window.__POS_LOGOUT_URL__.trim() : '';
                    window.location.href = u || '/dashboard';
                }, 100);
            });
        });
    }

    const btnExit = document.getElementById('btnExit');
    if (btnExit) {
        btnExit.addEventListener('click', () => {
            if (posCartHasActiveLines()) {
                openPosLogoutCartWarnPopup();
                return;
            }
            openPosLogoutConfirmPopup();
        });
    }

    installPosNavigationAutoHold();

    async function loadInitialState() {
        exitSalesReturnMode();
        clearPosOrderNoField();
        let billPayload = null;
        try {
            const res = await fetch('/pos-billing/last-in-progress-bill' + posCounterQuerySuffix());
            billPayload = await res.json();
            if (billPayload.success && billPayload.header) {
                const header = billPayload.header;
                const lines = (billPayload.lines || []).filter(l => (Number(l.quantity) || 0) !== 0);
                const billno = header.billno != null ? String(header.billno) : '';
                cart = lines.map(l => {
                    const qty = Number(l.quantity) || 0;
                    const rate = Number(l.rate) || 0;
                    const disc = Number(l.discount) || 0;
                    const amt = l.amount != null ? Number(l.amount) : Math.max(0, qty * rate - disc);
                    const itemFlag = l.item_flag != null ? Number(l.item_flag) : 1;
                    return {
                        slno: l.slno != null ? Number(l.slno) : undefined,
                        item_code: l.item_code,
                        barcode: l.manufacturerid || l.manufacturer_id || l.barcode || '',
                        manufacturerid: l.manufacturerid || l.manufacturer_id || l.barcode || '',
                        item_name: (l.item_name != null && l.item_name !== '') ? String(l.item_name) : String(l.item_code != null ? l.item_code : ''),
                        uom: (l.uom != null && l.uom !== '') ? String(l.uom) : 'PCS',
                        quantity: qty,
                        rate: rate,
                        discount: disc,
                        amount: amt,
                        base_qty: l.base_qty != null ? Number(l.base_qty) : qty,
                        cost: Number(l.cost) || 0,
                        costprice: Number(l.costprice || l.cost) || 0,
                        averagecost: Number(l.averagecost || l.average_cost) || 0,
                        item_factor: Number(l.item_factor || l.conversion_factor || 1) || 1,
                        store: l.store || '',
                        default_bin_storage_id: l.default_bin_storage_id || l.bin_storage_id || null,
                        bin_storage_id: l.bin_storage_id || l.default_bin_storage_id || null,
                        voided: itemFlag === 0,
                    };
                });
                promotionDiscount = 0;
                appliedVouchers = [];
                if (billno) setValue(billNo, billno);
                if (header.customercode != null && customerDisplay) customerDisplay.textContent = String(header.customercode);
                if (header.customercode != null && customerCode) setValue(customerCode, header.customercode);
                const lccRaw = header.loyaltycustomercode;
                const lccNum = lccRaw != null ? Number(lccRaw) : 0;
                if (lccNum) {
                    if (loyaltyCustomerDisplay) loyaltyCustomerDisplay.textContent = String(lccRaw);
                    if (loyaltyCustomerCode) setValue(loyaltyCustomerCode, String(lccRaw));
                } else {
                    clearLoyaltyCustomerUi();
                }
                renderCart();
                const ccApi = (customerCode?.value || '').trim();
                const lcApi = (loyaltyCustomerCode?.value || '').trim();
                const metricJobs = [];
                if (ccApi && ccApi !== '0') {
                    metricJobs.push(refreshCustomerMetricsFromApi(ccApi, 'billing'));
                } else {
                    clearBillingCustomerMetrics();
                }
                if (lcApi && lcApi !== '0') {
                    metricJobs.push(refreshCustomerMetricsFromApi(lcApi, 'loyalty'));
                }
                if (metricJobs.length) await Promise.all(metricJobs);
                renderCart();
                if (barcodeInput) focusPosBarcodeScanIfNoBlockingGate();
                syncCheckoutButtonLabel();
                await syncOpenShiftGateAndBillDate(billPayload.shift);
                applyOrderNoFromLoadedHeader(header);
                return;
            }
        } catch (e) {
            console.warn('last-in-progress-bill failed', e);
        }
        if (billPayload && billPayload.success) {
            if (billPayload.header != null && billPayload.header.billno != null) {
                setValue(billNo, String(billPayload.header.billno));
            } else {
                await fetchNextBillNo();
            }
        } else {
            await syncBillNoFromActiveTempBill();
        }
        renderCart();
        if (barcodeInput) focusPosBarcodeScanIfNoBlockingGate();
        syncCheckoutButtonLabel();
        await syncOpenShiftGateAndBillDate(billPayload && billPayload.shift ? billPayload.shift : null);
    }

    const posFooterDatetime = document.getElementById('pos_footer_datetime');
    function updatePosFooterDatetime() {
        if (!posFooterDatetime) return;
        const d = new Date();
        posFooterDatetime.textContent = d.toLocaleString(undefined, {
            weekday: 'short',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
        try {
            posFooterDatetime.setAttribute('datetime', d.toISOString());
        } catch (_e) {
            /* ignore */
        }
    }
    if (posFooterDatetime) {
        updatePosFooterDatetime();
        setInterval(updatePosFooterDatetime, 1000);
    }

    function wfNetFromCheckoutLines(lines) {
        let t = 0;
        const arr = lines || [];
        for (let i = 0; i < arr.length; i++) {
            const ln = arr[i];
            t += (Number(ln.quantity) || 0) * (Number(ln.rate) || 0) - (Number(ln.discount) || 0);
        }
        return Math.round(t * 100) / 100;
    }

    function wfBuildHeaderForBill(bn) {
        const h = buildSyncHeader();
        h.billno = bn;
        return h;
    }

    async function wfPostJson(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}),
        });
        const data = await res.json().catch(() => ({}));
        return { res, data };
    }

    async function runPosWorkflowSuite(options) {
        const opts = options || {};
        const steps = [];
        const started = new Date().toISOString();
        let billno = null;
        let lastSim = null;

        function pushStep(name, passed, ms, detail) {
            steps.push({
                name,
                ok: !!passed,
                ms: Math.round(ms * 10) / 10,
                detail: detail === undefined || detail === null ? null : detail,
            });
        }

        async function runStep(name, fn, stepOpts) {
            const fatal = stepOpts && stepOpts.fatal;
            const t0 = performance.now();
            try {
                const detail = await fn();
                pushStep(name, true, performance.now() - t0, detail);
                return { ok: true, detail };
            } catch (e) {
                const msg = e && e.message ? e.message : String(e);
                pushStep(name, false, performance.now() - t0, msg);
                if (fatal) throw e;
                return { ok: false, error: msg };
            }
        }

        try {
            await runStep(
                'last-in-progress-bill',
                async () => {
                    const res = await fetch('/pos-billing/last-in-progress-bill' + posCounterQuerySuffix(), {
                        credentials: 'same-origin',
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!data.success || !data.header || data.header.billno == null) {
                        throw new Error(data.error || 'No temp bill — open shift / bind counter?');
                    }
                    billno = posBillnoFromInput(data.header.billno);
                    if (!posBillnoIsValid(billno)) throw new Error('Invalid billno');
                    return { billno };
                },
                { fatal: true },
            );
        } catch (_e) {
            return {
                started_at: started,
                finished_at: new Date().toISOString(),
                billno,
                steps,
                aborted: true,
                summary: { passed: false, failed: steps.filter(s => !s.ok).map(s => s.name) },
                last_simulation: lastSim,
            };
        }

        let sample = null;
        let uomCode = 'PCS';
        let rate = 0;
        let pricingInfo = null;

        await runStep('sample-test-barcode', async () => {
            const res = await fetch('/pos-billing/sample-test-barcode', { credentials: 'same-origin' });
            const data = await res.json().catch(() => ({}));
            if (!data.success) throw new Error(data.error || 'sample barcode failed');
            sample = data;
            return { itemcode: data.itemcode, barcode: data.barcode };
        });

        await runStep('item-uoms + uom-info', async () => {
            const r1 = await fetch(`/pos-billing/item-uoms?item_code=${encodeURIComponent(String(sample.itemcode))}`, {
                credentials: 'same-origin',
            });
            const d1 = await r1.json().catch(() => ({}));
            if (!d1.success || !d1.uoms || !d1.uoms.length) throw new Error(d1.error || 'No UOMs');
            uomCode = d1.uoms[0].code || 'PCS';
            const r2 = await fetch(
                `/pos-billing/uom-info?item_code=${encodeURIComponent(String(sample.itemcode))}&uom_code=${encodeURIComponent(uomCode)}&price_mode=retail`,
                { credentials: 'same-origin' },
            );
            const d2 = await r2.json().catch(() => ({}));
            if (!d2.success || !d2.pricing) throw new Error(d2.error || 'uom-info failed');
            pricingInfo = d2.pricing;
            rate = Number(pricingInfo.rate) || 0;
            return { uom: uomCode, rate };
        });

        async function wfAddLine(qty) {
            const factor = Number(pricingInfo.item_factor || pricingInfo.conversion_factor || 1) || 1;
            const header = wfBuildHeaderForBill(billno);
            const line = {
                item_code: sample.itemcode,
                manufacturerid: sample.barcode || '',
                uom: uomCode,
                quantity: qty,
                rate,
                discount: 0,
                cost: 0,
                costprice: 0,
                averagecost: 0,
                item_factor: factor,
                base_qty: qty * factor,
                store: '',
            };
            const { data } = await wfPostJson('/pos-billing/cart-line-add', { header, line });
            if (!data.success) throw new Error(data.error || 'cart-line-add failed');
            return data.slno;
        }

        let slA = null;
        await runStep('cart-line-add', async () => {
            slA = await wfAddLine(1);
            return { slno: slA };
        });

        await runStep('cart-line-update qty', async () => {
            const header = wfBuildHeaderForBill(billno);
            const { data } = await wfPostJson('/pos-billing/cart-line-update', { header, slno: slA, quantity: 2 });
            if (!data.success) throw new Error(data.error || 'qty update');
            return {};
        });

        await runStep('cart-line-update discount', async () => {
            const header = wfBuildHeaderForBill(billno);
            const { data } = await wfPostJson('/pos-billing/cart-line-update', { header, slno: slA, discount: 0.25 });
            if (!data.success) throw new Error(data.error || 'discount update');
            return {};
        });

        await runStep('hold bill', async () => {
            const { data } = await wfPostJson('/pos-billing/hold', { billno });
            if (!data.success) throw new Error(data.error || 'hold');
            return {};
        });

        await runStep('retrieve hold', async () => {
            const { data } = await wfPostJson('/pos-billing/retrieve-hold', { billno });
            if (!data.success) throw new Error(data.error || 'retrieve');
            return {};
        });

        await runStep('cart-line-void', async () => {
            const header = wfBuildHeaderForBill(billno);
            const { data } = await wfPostJson('/pos-billing/cart-line-void', { header, slno: slA });
            if (!data.success) throw new Error(data.error || 'line void');
            return {};
        });

        await runStep('cart-line-add (active line)', async () => {
            const sl = await wfAddLine(1);
            return { slno: sl };
        });

        await runStep('cart-line-remove', async () => {
            const slRm = await wfAddLine(1);
            const header = wfBuildHeaderForBill(billno);
            const { data } = await wfPostJson('/pos-billing/cart-line-remove', { header, slno: slRm });
            if (!data.success) throw new Error(data.error || 'remove line');
            return { removed_slno: slRm };
        });

        await runStep('verify/simulate (stock)', async () => {
            const res = await fetch(`/pos-billing/verify/temp-bill?billno=${encodeURIComponent(String(billno))}`, {
                credentials: 'same-origin',
            });
            const tb = await res.json().catch(() => ({}));
            if (!tb.success) throw new Error(tb.error || 'temp bill load');
            const { data } = await wfPostJson('/pos-billing/verify/simulate', {
                header: tb.header,
                lines: tb.lines,
                strict: false,
            });
            if (!data.success) throw new Error(data.error || 'simulate');
            lastSim = data;
            return {
                simulation_ok: !!data.simulation_ok,
                simulation_message: data.simulation_message || null,
            };
        });

        if (opts.creditPrecheck) {
            await runStep('credit-sale-precheck', async () => {
                const ccRaw = (customerCode?.value || '').trim();
                const cc = ccRaw ? parseInt(ccRaw, 10) : 0;
                if (!cc || Number.isNaN(cc)) {
                    return { skipped: true, reason: 'No billing customer code in POS fields' };
                }
                const res = await fetch(`/pos-billing/verify/temp-bill?billno=${encodeURIComponent(String(billno))}`, {
                    credentials: 'same-origin',
                });
                const tb = await res.json().catch(() => ({}));
                if (!tb.success) throw new Error(tb.error || 'temp bill load');
                const net = wfNetFromCheckoutLines(tb.lines);
                const { data } = await wfPostJson('/pos-billing/credit-sale-precheck', {
                    customercode: cc,
                    proposed_credit_delta: net,
                });
                if (!data.success) throw new Error(data.error || 'precheck HTTP');
                if (data.skipped) return { skipped: true, detail: data.detail };
                if (!data.accounts_ok) throw new Error(data.detail || 'Credit precheck failed');
                return { accounts_ok: true, detail: data.detail || null };
            });
        }

        if (opts.liveCashSave) {
            await runStep('save cash (queued)', async () => {
                const res = await fetch(`/pos-billing/verify/temp-bill?billno=${encodeURIComponent(String(billno))}`, {
                    credentials: 'same-origin',
                });
                const tb = await res.json().catch(() => ({}));
                if (!tb.success) throw new Error(tb.error || 'temp bill load');
                const net = wfNetFromCheckoutLines(tb.lines);
                if (!(net > 0)) throw new Error('Net total not positive; add stock/pricing or disable live save');
                const header = Object.assign({}, tb.header, {
                    customercode: 0,
                    cashamount: net,
                    cardamount: 0,
                    loyaltyamount: 0,
                    pointsamount: 0,
                    payment_modes: [{ code: 'CASH', amount: net, reference: '' }],
                });
                const { data } = await wfPostJson('/pos-billing/save', {
                    header,
                    lines: tb.lines,
                    receipt_extras: {},
                });
                if (!data.success) throw new Error(data.error || 'save failed');
                const detail = { queued: !!data.queued, queue_job_id: data.queue_job_id || null, billno: data.billno };
                const rt = typeof data.receipt_text === 'string' ? data.receipt_text.trimEnd() : '';
                const hasReceiptObj = data.receipt && typeof data.receipt === 'object';
                if (opts.printReceipt && (hasReceiptObj || rt)) {
                    try {
                        closeModal('posWorkflowTestModal');
                        const qMsg = data.queued ? `Queued for background posting. Job #${data.queue_job_id || ''}` : '';
                        await presentPosReceiptAfterSale(hasReceiptObj ? data.receipt : null, rt || '', qMsg);
                        detail.receipt_presented = true;
                    } catch (pe) {
                        detail.receipt_presented = false;
                        detail.receipt_error = pe && pe.message ? String(pe.message) : String(pe);
                    }
                }
                return detail;
            });
        } else {
            await runStep('void-all (cleanup)', async () => {
                const { data } = await wfPostJson('/pos-billing/void-all', { billno });
                if (!data.success) throw new Error(data.error || 'void-all');
                return {};
            });
        }

        const passed = steps.every(s => s.ok);
        const report = {
            started_at: started,
            finished_at: new Date().toISOString(),
            billno,
            steps,
            summary: { passed, failed: steps.filter(s => !s.ok).map(s => s.name) },
            last_simulation: lastSim
                ? {
                      simulation_ok: !!lastSim.simulation_ok,
                      simulation_message: lastSim.simulation_message || null,
                  }
                : null,
            notes: [
                'Payment keypad UI is not automated here; cash save uses the same /pos-billing/save API as Validate.',
                'With live save + print receipt: uses presentPosReceiptAfterSale (QZ auto-print or preview — same as checkout).',
                'For AI commentary on stock simulation use POS Verify → AI insights.',
            ],
        };
        return report;
    }

    (function wirePosWorkflowTestUi() {
        const modal = document.getElementById('posWorkflowTestModal');
        const btnOpen = document.getElementById('btnPosWorkflowOpen');
        const btnRun = document.getElementById('btnPosWorkflowRun');
        const btnDl = document.getElementById('btnPosWorkflowDownload');
        const pre = document.getElementById('posWorkflowReport');
        const wfCredit = document.getElementById('wfOptCreditPrecheck');
        const wfCash = document.getElementById('wfOptLiveCashSave');
        const wfPrint = document.getElementById('wfOptPrintReceipt');
        const wfReload = document.getElementById('wfOptReloadUi');
        let lastReport = null;

        function openModal() {
            if (!modal) return;
            modal.classList.remove('hidden');
        }

        if (btnOpen && modal) {
            btnOpen.addEventListener('click', () => openModal());
        }

        if (btnRun && pre) {
            btnRun.addEventListener('click', async () => {
                btnRun.disabled = true;
                if (btnDl) btnDl.disabled = true;
                pre.textContent = 'Running…';
                try {
                    const rep = await runPosWorkflowSuite({
                        creditPrecheck: !!(wfCredit && wfCredit.checked),
                        liveCashSave: !!(wfCash && wfCash.checked),
                        printReceipt: !!(wfCash && wfCash.checked && wfPrint && wfPrint.checked),
                    });
                    lastReport = rep;
                    window.__POS_WORKFLOW_LAST_REPORT__ = rep;
                    pre.textContent = JSON.stringify(rep, null, 2);
                    if (btnDl) btnDl.disabled = false;
                    if (wfReload && wfReload.checked) {
                        await loadNextBill();
                        renderCart();
                        syncCheckoutButtonLabel();
                    }
                } catch (e) {
                    pre.textContent = 'Fatal: ' + (e && e.message ? e.message : String(e));
                } finally {
                    btnRun.disabled = false;
                }
            });
        }

        if (btnDl) {
            btnDl.addEventListener('click', () => {
                if (!lastReport) return;
                const blob = new Blob([JSON.stringify(lastReport, null, 2)], { type: 'application/json' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `pos-workflow-report-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            });
        }

        window.runPosWorkflowSuite = runPosWorkflowSuite;
    })();

    const POS_LOAD_STEP_LABELS = {
        terminal_single_tab_lock: 'Checking this terminal…',
        resolve_counter_from_hostname: 'Resolving counter and warehouse…',
        load_held_bill_from_query: 'Opening held bill…',
        load_initial_state: 'Loading bill, shift, and cart…',
    };

    function setPosLoadOverlayStep(stepKey) {
        const hint = document.getElementById('posLoadOverlayHint');
        if (!hint) return;
        hint.textContent = POS_LOAD_STEP_LABELS[stepKey] || 'Please wait…';
    }

    function hidePosLoadOverlay() {
        document.body.classList.remove('pos-page-loading');
        const ov = document.getElementById('posLoadOverlay');
        if (!ov) return;
        ov.classList.add('hidden');
        ov.setAttribute('aria-hidden', 'true');
        ov.setAttribute('aria-busy', 'false');
    }

    async function posStartupStep(name, fn) {
        setPosLoadOverlayStep(name);
        const t0 = performance.now();
        try {
            return await fn();
        } finally {
            try {
                console.info('[TIMING pos_billing_ui]', name, Math.round((performance.now() - t0) * 10) / 10 + 'ms');
            } catch (_e) {
                /* ignore */
            }
        }
    }

    installPosBackNavigationGuard();

    let _posTabHiddenAt = 0;
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            _posTabHiddenAt = Date.now();
            return;
        }
        if (document.visibilityState !== 'visible') return;
        if (posCheckoutSubmitInFlight) return;
        if (Date.now() - _posTabHiddenAt < 800) return;
        refreshPosSaveNonce();
    });

    syncCheckoutButtonLabel();
    (async () => {
        const startupT0 = performance.now();
        try {
            const lockOk = await posStartupStep('terminal_single_tab_lock', tryAcquirePosTerminalLock);
            if (!lockOk || _posTerminalLockBlocked) {
                const retryBtn = document.getElementById('btnPosTerminalLockRetry');
                if (retryBtn && !retryBtn.dataset.bound) {
                    retryBtn.dataset.bound = '1';
                    retryBtn.addEventListener('click', async () => {
                        retryBtn.disabled = true;
                        hidePosTerminalLockOverlay();
                        document.body.classList.add('pos-page-loading');
                        const loadOv = document.getElementById('posLoadOverlay');
                        if (loadOv) {
                            loadOv.classList.remove('hidden');
                            loadOv.setAttribute('aria-hidden', 'false');
                            loadOv.setAttribute('aria-busy', 'true');
                        }
                        setPosLoadOverlayStep('terminal_single_tab_lock');
                        const ok = await tryAcquirePosTerminalLock({ force: true });
                        retryBtn.disabled = false;
                        hidePosLoadOverlay();
                        if (ok && !_posTerminalLockBlocked) {
                            window.location.reload();
                        }
                    });
                }
                return;
            }
            await posStartupStep('resolve_counter_from_hostname', resolvePosCounterFromHostname);
            const heldFromUrl = await posStartupStep('load_held_bill_from_query', loadHeldBillFromQueryParam);
            if (!heldFromUrl) {
                await posStartupStep('load_initial_state', loadInitialState);
            }
        } finally {
            hidePosLoadOverlay();
            try {
                console.info(
                    '[TIMING pos_billing_ui]',
                    'startup_total',
                    Math.round((performance.now() - startupT0) * 10) / 10 + 'ms',
                );
            } catch (_e) {
                /* ignore */
            }
        }
    })();
})();
