/**
 * Sales Invoice / Sales Return — AI line capture (toggle, paste, image, drawer).
 * Requires window.SalesInvoiceAi from sales.js / sales_return.js.
 */
(function () {
    'use strict';

    var pendingAiScreenshotResults = null;
    var siAiScreenshotDrawerOpen = null;
    var reopenSiAiScreenshotPreviewFn = null;

    function formatNum(n, decimals) {
        var dec = decimals == null ? 2 : decimals;
        var num = Number(n);
        if (!Number.isFinite(num)) return '0.00';
        return num.toFixed(dec);
    }

    function showSiAiMessage(title, msg) {
        var text = String(msg || '').trim();
        if (title && text) alert(String(title) + ': ' + text);
        else if (text) alert(text);
    }

    function getSalesAiApi() {
        return window.SalesInvoiceAi || null;
    }

    function bindSiAiScreenshotDrawerUiOnce() {
        var root = document.getElementById('siAiScreenshotDrawer');
        if (!root || root.dataset.bound === '1') return;
        root.dataset.bound = '1';

        var backdrop = document.getElementById('siAiDrawerBackdrop');
        var btnClose = document.getElementById('siAiDrawerClose');
        var btnCancel = document.getElementById('siAiDrawerCancel');
        var btnConfirm = document.getElementById('siAiDrawerConfirm');
        var selAll = document.getElementById('siAiDrawerSelectAll');
        var tbody = document.getElementById('siAiDrawerBody');
        var grandTotalEl = document.getElementById('siAiDrawerGrandTotal');

        function aiDrawerEffectiveUnitPrice(it) {
            if (!it) return 0;
            if (it.barcode_uom != null && it.barcode_retail_price != null) {
                return Number(it.barcode_retail_price) || 0;
            }
            return Number(it.retailprice) || 0;
        }

        function formatAiDrawerStock(v) {
            var n = Number(v);
            if (!Number.isFinite(n)) return '—';
            if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
            return formatNum(n, 3);
        }

        function updateAiDrawerTotals() {
            if (!tbody || !grandTotalEl) return;
            var sum = 0;
            tbody.querySelectorAll('.si-ai-cart-card[data-matched="1"]').forEach(function (card) {
                var cb = card.querySelector('.si-ai-drawer-inc');
                if (!cb || !cb.checked) return;
                var unit = Number(card.dataset.unitPrice || 0);
                var qInp = card.querySelector('.si-ai-drawer-qty');
                var q = Math.abs(Number(qInp && qInp.value !== '' ? qInp.value : 1) || 0);
                sum += q * unit;
            });
            grandTotalEl.innerHTML = '<span class="si-ai-drawer__grand-label">Subtotal</span><span class="si-ai-drawer__grand-value">' + formatNum(sum) + '</span>';
        }

        function refreshAiDrawerRowAmount(card) {
            if (!card || card.dataset.matched !== '1') return;
            var unit = Number(card.dataset.unitPrice || 0);
            var qInp = card.querySelector('.si-ai-drawer-qty');
            var sp = card.querySelector('.si-ai-drawer-line-amt');
            if (!sp) return;
            var q = Math.abs(Number(qInp && qInp.value !== '' ? qInp.value : 1) || 0);
            sp.textContent = formatNum(q * unit);
        }

        function wireAiDrawerQtyStepper(card) {
            var inp = card.querySelector('.si-ai-drawer-qty');
            var minus = card.querySelector('[data-ai-qty-minus]');
            var plus = card.querySelector('[data-ai-qty-plus]');
            function bump(delta) {
                var v = Math.abs(Number(inp && inp.value !== '' ? inp.value : 1) || 1);
                if (delta < 0) v = Math.max(0.0001, v + delta);
                else v = v + delta;
                if (inp) inp.value = String(v);
                refreshAiDrawerRowAmount(card);
                updateAiDrawerTotals();
            }
            if (minus) minus.addEventListener('click', function () { bump(-1); });
            if (plus) plus.addEventListener('click', function () { bump(1); });
        }

        function closeSiAiScreenshotDrawer(opts) {
            var keepPreview = !!(opts && opts.keepPreview);
            root.classList.add('hidden');
            root.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
            if (!keepPreview) {
                pendingAiScreenshotResults = null;
                if (tbody) tbody.innerHTML = '';
                if (grandTotalEl) grandTotalEl.innerHTML = '';
            }
            updateAiReviewButtonVisibility();
        }

        function updateAiReviewButtonVisibility() {
            var btn = document.getElementById('siAiReviewCartBtn');
            if (!btn || !root) return;
            var show = !!(pendingAiScreenshotResults && pendingAiScreenshotResults.length && root.classList.contains('hidden'));
            btn.classList.toggle('hidden', !show);
            btn.setAttribute('aria-hidden', show ? 'false' : 'true');
        }

        function reopenSiAiScreenshotDrawer() {
            if (!pendingAiScreenshotResults || !pendingAiScreenshotResults.length) return false;
            if (!root.classList.contains('hidden')) return true;
            root.classList.remove('hidden');
            root.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
            updateAiReviewButtonVisibility();
            return true;
        }

        function renderSiAiScreenshotDrawer(results) {
            var summaryEl = document.getElementById('siAiDrawerSummary');
            if (!tbody || !summaryEl) return;
            pendingAiScreenshotResults = results;
            tbody.innerHTML = '';
            var nMatch = 0;
            var nMiss = 0;
            (results || []).forEach(function (raw, i) {
                var r = raw && typeof raw === 'object' ? raw : {};
                var matched = !!(r.matched && r.item);
                if (matched) nMatch += 1;
                else nMiss += 1;
                var ai = r.ai && typeof r.ai === 'object' ? r.ai : {};
                var nameHint = String(ai.item_name || ai.itemname || ai.name || ai.product_name || ai.description || ai.product || '').trim();
                var bc = String(ai.barcode || ai.manufacturerid || ai.manufacturer_id || ai.ean || ai.upc || '').trim() || '—';
                var aiExtractLabel = nameHint && nameHint !== bc ? bc + ' · ' + nameHint : bc;

                var card = document.createElement('article');
                card.className = 'si-ai-cart-card' + (matched ? '' : ' si-ai-cart-card--miss');
                card.dataset.aiIndex = String(i);
                card.dataset.matched = matched ? '1' : '0';

                var pick = document.createElement('div');
                pick.className = 'si-ai-cart-card__pick';
                var thumb = document.createElement('div');
                thumb.className = 'si-ai-cart-card__thumb';
                var body = document.createElement('div');
                body.className = 'si-ai-cart-card__body';
                var titleRow = document.createElement('div');
                var badge = document.createElement('span');
                badge.className = 'si-ai-cart-card__badge';
                var titleEl = document.createElement('p');
                titleEl.className = 'si-ai-cart-card__title';
                var metaEl = document.createElement('div');
                metaEl.className = 'si-ai-cart-card__meta';
                var aiEl = document.createElement('div');
                aiEl.className = 'si-ai-cart-card__ai';
                aiEl.textContent = 'Extracted · ' + aiExtractLabel;
                var side = document.createElement('div');
                side.className = 'si-ai-cart-card__side';

                if (matched && r.item) {
                    var it = r.item;
                    var unitPrice = aiDrawerEffectiveUnitPrice(it);
                    card.dataset.unitPrice = String(unitPrice);
                    var stockRaw = it.currentstock != null ? it.currentstock : (it.current_stock != null ? it.current_stock : it.CURRENTSTOCK);
                    var sysRetail = it.system_retail_price != null ? it.system_retail_price : (it.systemRetailPrice != null ? it.systemRetailPrice : it.retailprice);
                    var nm = String(it.itemname || '').trim();
                    var ic = it.itemcode != null ? String(it.itemcode) : '';
                    var qu = String(r.query_used || '').trim();
                    var titleText = nm || (ic ? 'Item ' + ic : 'Item');
                    thumb.textContent = (titleText || '?').trim().charAt(0).toUpperCase() || '?';

                    var cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.className = 'si-ai-drawer-inc';
                    cb.checked = true;
                    cb.addEventListener('change', syncSelectAllFromRows);
                    pick.appendChild(cb);

                    badge.textContent = 'Matched';
                    titleEl.textContent = titleText;
                    var metaBits = [];
                    if (ic) metaBits.push('#' + ic);
                    metaBits.push('Stock ' + formatAiDrawerStock(stockRaw));
                    metaBits.push('List ' + formatNum(Number(sysRetail) || 0));
                    if (qu && qu !== bc) metaBits.push('Found via ' + qu);
                    metaEl.textContent = metaBits.join(' · ');

                    var unitWrap = document.createElement('div');
                    unitWrap.className = 'si-ai-cart-card__unit-price';
                    unitWrap.innerHTML = 'Price ea.<strong>' + formatNum(unitPrice) + '</strong>';

                    var qtyRow = document.createElement('div');
                    qtyRow.className = 'si-ai-cart-qty';
                    var btnMinus = document.createElement('button');
                    btnMinus.type = 'button';
                    btnMinus.className = 'si-ai-cart-qty__btn';
                    btnMinus.setAttribute('data-ai-qty-minus', '');
                    btnMinus.textContent = '−';
                    var inp = document.createElement('input');
                    inp.type = 'number';
                    inp.className = 'si-ai-drawer-qty';
                    inp.step = 'any';
                    inp.min = '0.0001';
                    inp.value = String(Number(r.qty) > 0 ? Number(r.qty) : 1);
                    var btnPlus = document.createElement('button');
                    btnPlus.type = 'button';
                    btnPlus.className = 'si-ai-cart-qty__btn';
                    btnPlus.setAttribute('data-ai-qty-plus', '');
                    btnPlus.textContent = '+';
                    qtyRow.append(btnMinus, inp, btnPlus);

                    var lineTot = document.createElement('div');
                    lineTot.className = 'si-ai-cart-card__line-total';
                    var spanAmt = document.createElement('span');
                    spanAmt.className = 'si-ai-drawer-line-amt';
                    var q0 = Math.abs(Number(r.qty) > 0 ? Number(r.qty) : 1);
                    spanAmt.textContent = formatNum(q0 * unitPrice);
                    lineTot.appendChild(spanAmt);

                    side.append(unitWrap, qtyRow, lineTot);
                    titleRow.append(badge, titleEl);
                    body.append(titleRow, metaEl, aiEl);
                    card.append(pick, thumb, body, side);
                    tbody.appendChild(card);
                    wireAiDrawerQtyStepper(card);
                    inp.addEventListener('input', function () {
                        refreshAiDrawerRowAmount(card);
                        updateAiDrawerTotals();
                    });
                } else {
                    thumb.textContent = '?';
                    pick.innerHTML = '<span style="display:inline-block;width:18px;height:18px;"></span>';
                    badge.textContent = 'Unavailable';
                    titleEl.textContent = 'Not in catalog';
                    var tried = Array.isArray(r.queries_tried) ? r.queries_tried.filter(Boolean).join(', ') : '';
                    metaEl.textContent = tried ? 'No ITEMMASTER match for: ' + tried : 'Could not resolve this line against your catalog.';
                    titleRow.append(badge, titleEl);
                    body.append(titleRow, metaEl, aiEl);
                    var missQty = document.createElement('div');
                    missQty.className = 'si-ai-cart-card__unit-price';
                    missQty.innerHTML = '<strong>Qty ' + String(Number(r.qty) > 0 ? Number(r.qty) : 1) + '</strong>';
                    side.appendChild(missQty);
                    card.append(pick, thumb, body, side);
                    tbody.appendChild(card);
                }
            });

            summaryEl.textContent = !(results || []).length
                ? 'No lines extracted.'
                : nMatch + ' item' + (nMatch === 1 ? '' : 's') + ' ready · ' + nMiss + ' need attention — adjust quantities, then add to invoice.';
            syncSelectAllFromRows();
            if (btnConfirm) {
                btnConfirm.disabled = nMatch === 0;
                btnConfirm.textContent = nMatch ? 'Add to invoice (' + nMatch + ')' : 'Add to invoice';
            }
        }

        function syncSelectAllFromRows() {
            if (!selAll || !tbody) return;
            var boxes = tbody.querySelectorAll('.si-ai-cart-card[data-matched="1"] .si-ai-drawer-inc');
            var list = Array.from(boxes);
            if (!list.length) {
                selAll.checked = false;
                selAll.disabled = true;
                updateAiDrawerTotals();
                return;
            }
            selAll.disabled = false;
            selAll.checked = list.every(function (c) { return c.checked; });
            updateAiDrawerTotals();
        }

        function openSiAiScreenshotDrawer(results) {
            renderSiAiScreenshotDrawer(results);
            root.classList.remove('hidden');
            root.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
            updateAiReviewButtonVisibility();
        }

        siAiScreenshotDrawerOpen = openSiAiScreenshotDrawer;
        reopenSiAiScreenshotPreviewFn = reopenSiAiScreenshotDrawer;

        var btnReviewCart = document.getElementById('siAiReviewCartBtn');
        if (btnReviewCart) btnReviewCart.addEventListener('click', function () { reopenSiAiScreenshotDrawer(); });
        if (backdrop) backdrop.addEventListener('click', function () { closeSiAiScreenshotDrawer({ keepPreview: true }); });
        if (btnClose) btnClose.addEventListener('click', function () { closeSiAiScreenshotDrawer({ keepPreview: true }); });
        if (btnCancel) btnCancel.addEventListener('click', function () { closeSiAiScreenshotDrawer({ keepPreview: true }); });

        if (selAll) {
            selAll.addEventListener('change', function () {
                if (!tbody || !selAll) return;
                var on = selAll.checked;
                tbody.querySelectorAll('.si-ai-cart-card[data-matched="1"] .si-ai-drawer-inc').forEach(function (cb) {
                    cb.checked = on;
                });
                updateAiDrawerTotals();
            });
        }

        if (btnConfirm) {
            btnConfirm.addEventListener('click', async function () {
                if (!tbody || !pendingAiScreenshotResults) return;
                var api = getSalesAiApi();
                if (!api || typeof api.addLineFromItem !== 'function') {
                    showSiAiMessage('AI lines', 'Sales form is not ready. Refresh the page.');
                    return;
                }
                var rows = Array.from(tbody.querySelectorAll('.si-ai-cart-card[data-ai-index]'));
                btnConfirm.disabled = true;
                var added = 0;
                try {
                    for (var j = 0; j < rows.length; j++) {
                        var card = rows[j];
                        var cb = card.querySelector('.si-ai-drawer-inc');
                        if (!cb || !cb.checked) continue;
                        var idx = parseInt(card.dataset.aiIndex || '-1', 10);
                        if (idx < 0 || idx >= pendingAiScreenshotResults.length) continue;
                        var r = pendingAiScreenshotResults[idx];
                        if (!r || !r.matched || !r.item) continue;
                        var qInp = card.querySelector('.si-ai-drawer-qty');
                        var qtyVal = qInp && qInp.value !== '' ? qInp.value : r.qty;
                        var ok = await api.addLineFromItem(r.item, qtyVal);
                        if (ok) added += 1;
                    }
                    closeSiAiScreenshotDrawer();
                    if (added > 0) {
                        var ta = document.getElementById('siAiCapturePaste');
                        if (ta) ta.value = '';
                        var stEl = document.getElementById('siAiCaptureStatus');
                        if (stEl) stEl.textContent = '';
                    }
                    if (added === 0 && rows.some(function (card) { return card.dataset.matched === '1'; })) {
                        showSiAiMessage('AI lines', 'No lines were selected or add failed. Check customer, warehouse, and line fields.');
                    }
                } finally {
                    btnConfirm.disabled = false;
                }
            });
        }

        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            if (!root || root.classList.contains('hidden')) return;
            closeSiAiScreenshotDrawer({ keepPreview: true });
        });
    }

    function bindSiAiScreenshotCapture() {
        var url = typeof window.__SALES_AI_SCREENSHOT_URL__ === 'string' ? window.__SALES_AI_SCREENSHOT_URL__.trim() : '';
        var toggle = document.getElementById('siAiCaptureToggle');
        var panel = document.getElementById('siAiCapturePanel');
        var fileEl = document.getElementById('siAiCaptureFile');
        var pick = document.getElementById('siAiCapturePick');
        var statusEl = document.getElementById('siAiCaptureStatus');
        if (!url || !toggle || !panel || !fileEl || !pick) return;

        bindSiAiScreenshotDrawerUiOnce();

        var STORAGE = 'nexa-si-ai-capture-on';

        function setStatus(t) {
            if (statusEl) statusEl.textContent = t || '';
        }

        function syncPanel() {
            var on = toggle.checked;
            panel.classList.toggle('hidden', !on);
            toggle.setAttribute('aria-checked', on ? 'true' : 'false');
            try { localStorage.setItem(STORAGE, on ? '1' : '0'); } catch (e) { /* ignore */ }
            if (!on) setStatus('');
        }

        try { toggle.checked = localStorage.getItem(STORAGE) === '1'; } catch (e) { toggle.checked = false; }
        syncPanel();
        toggle.addEventListener('change', syncPanel);
        pick.addEventListener('click', function () { fileEl.click(); });

        var pasteTa = document.getElementById('siAiCapturePaste');
        var analyzeBtn = document.getElementById('siAiAnalyzeTextBtn');
        var barcodeInput = document.getElementById('barcode_input');
        var AI_CLIPBOARD_TEXT_CAP = 32000;

        function appendPasteBoxSnippet(snippet) {
            if (!pasteTa || snippet === '') return;
            var cur = pasteTa.value.replace(/\s+$/, '');
            var next = cur ? cur + '\n' + snippet : snippet;
            if (next.length > AI_CLIPBOARD_TEXT_CAP) next = next.slice(-AI_CLIPBOARD_TEXT_CAP);
            pasteTa.value = next;
            pasteTa.focus();
        }

        async function handleAiLinesResponse(data) {
            if (!data.success) {
                showSiAiMessage('AI lines', data.error ? String(data.error) : 'Request failed' + (data.detail ? ': ' + String(data.detail) : ''));
                setStatus('');
                return;
            }
            var results = data.results || [];
            if (!results.length) {
                showSiAiMessage('AI lines', 'No lines extracted.');
                setStatus('');
                return;
            }
            if (typeof siAiScreenshotDrawerOpen === 'function') {
                siAiScreenshotDrawerOpen(results);
                var matchedN = results.filter(function (row) { return row && row.matched && row.item; }).length;
                var unmatchedN = results.length - matchedN;
                setStatus('Preview: ' + matchedN + ' matched' + (unmatchedN ? ' · ' + unmatchedN + ' unavailable' : '') + '. Review in drawer.');
            } else {
                var api = getSalesAiApi();
                if (!api || typeof api.addLineFromItem !== 'function') {
                    showSiAiMessage('AI lines', 'Sales form is not ready.');
                    setStatus('');
                    return;
                }
                var added = 0;
                var skipped = 0;
                for (var i = 0; i < results.length; i++) {
                    var r = results[i];
                    if (!r.matched || !r.item) { skipped++; continue; }
                    var ok = await api.addLineFromItem(r.item, r.qty);
                    if (ok) added += 1;
                    else skipped += 1;
                }
                setStatus('Added ' + added + ' line(s).' + (skipped ? ' ' + skipped + ' skipped.' : ''));
                if (added > 0 && pasteTa) pasteTa.value = '';
                if (added === 0 && results.length > 0) {
                    showSiAiMessage('AI lines', 'No lines matched your item master. Try clearer text or barcodes.');
                }
            }
        }

        async function fetchAiLines(reqInit) {
            var res = await fetch(url, Object.assign({ credentials: 'same-origin' }, reqInit));
            var ctHdr = (res.headers.get('content-type') || '').toLowerCase();
            var data = {};
            if (ctHdr.indexOf('application/json') >= 0) {
                try { data = await res.json(); } catch (e) {
                    data = { success: false, error: 'Invalid JSON from server (HTTP ' + res.status + ').' };
                }
            } else {
                var txt = await res.text().catch(function () { return ''; });
                showSiAiMessage('AI lines', 'HTTP ' + res.status + ': ' + (txt ? String(txt).replace(/\s+/g, ' ').trim().slice(0, 280) : '(empty body)'));
                setStatus('');
                return;
            }
            await handleAiLinesResponse(data);
        }

        async function runAiPayload(spec) {
            var blob = spec && spec.blob && spec.blob.size ? spec.blob : null;
            var textOnly = spec && spec.textOnly ? String(spec.textOnly).trim() : '';
            if (!blob && !textOnly) return;
            pick.disabled = true;
            if (analyzeBtn) analyzeBtn.disabled = true;
            setStatus(blob ? 'Reading image…' : 'Analyzing text…');
            try {
                if (blob) {
                    var fd = new FormData();
                    fd.append('image', blob, blob instanceof File && blob.name ? blob.name : 'capture.png');
                    var hint = (pasteTa && pasteTa.value.trim()) || '';
                    if (hint) fd.append('text', hint.slice(0, AI_CLIPBOARD_TEXT_CAP));
                    await fetchAiLines({ method: 'POST', body: fd });
                } else {
                    await fetchAiLines({
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: textOnly.slice(0, AI_CLIPBOARD_TEXT_CAP) }),
                    });
                }
            } catch (err) {
                showSiAiMessage('AI lines', err && err.message ? String(err.message) : 'Request failed.');
                setStatus('');
            } finally {
                pick.disabled = false;
                if (analyzeBtn) analyzeBtn.disabled = false;
            }
        }

        if (analyzeBtn) {
            analyzeBtn.addEventListener('click', async function () {
                var t = (pasteTa && pasteTa.value.trim()) || '';
                var drawerEl = document.getElementById('siAiScreenshotDrawer');
                var drawerHidden = drawerEl && drawerEl.classList.contains('hidden');
                if (!t) {
                    if (drawerHidden && typeof reopenSiAiScreenshotPreviewFn === 'function' && reopenSiAiScreenshotPreviewFn()) return;
                    showSiAiMessage('AI lines', 'Paste or type text in the AI field first.');
                    return;
                }
                if (drawerHidden && typeof reopenSiAiScreenshotPreviewFn === 'function') reopenSiAiScreenshotPreviewFn();
                await runAiPayload({ textOnly: t });
            });
        }

        if (statusEl) {
            statusEl.classList.add('si-ai-capture-status--clickable');
            statusEl.title = 'Click to reopen AI preview';
            statusEl.addEventListener('click', function () {
                if (typeof reopenSiAiScreenshotPreviewFn === 'function') reopenSiAiScreenshotPreviewFn();
            });
        }

        fileEl.addEventListener('change', async function () {
            var f = fileEl.files && fileEl.files[0];
            fileEl.value = '';
            if (!f) return;
            await runAiPayload({ blob: f });
        });

        function clipboardFirstImageFile(cd) {
            if (!cd || !cd.items) return null;
            var items = Array.from(cd.items);
            for (var i = 0; i < items.length; i++) {
                var it = items[i];
                if (it.kind === 'file') {
                    var f = it.getAsFile();
                    if (f && f.type && f.type.indexOf('image') === 0 && f.size > 0) return f;
                } else if (it.type && it.type.indexOf('image/') === 0) {
                    var f2 = it.getAsFile();
                    if (f2 && f2.size > 0) return f2;
                }
            }
            return null;
        }

        document.addEventListener('paste', async function (e) {
            if (!toggle.checked) return;
            var cd = e.clipboardData;
            if (!cd) return;
            var ae = document.activeElement;
            var isPasteBox = ae && ae.id === 'siAiCapturePaste';
            var isBarcodeFocus = ae && (ae === barcodeInput || ae.id === 'barcode_input');
            var imageFile = clipboardFirstImageFile(cd);
            if (imageFile) {
                var inOtherEditable = ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT') && !isBarcodeFocus && !isPasteBox;
                if (inOtherEditable) return;
                e.preventDefault();
                await runAiPayload({ blob: imageFile });
                return;
            }
            if (isPasteBox) return;
            if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT') && !isBarcodeFocus) return;
            var pastedText = '';
            try { pastedText = String(cd.getData('text/plain') || '').replace(/\r\n/g, '\n'); } catch (err) { pastedText = ''; }
            var trimmed = pastedText.trim();
            if (!trimmed || isBarcodeFocus || !pasteTa) return;
            e.preventDefault();
            appendPasteBoxSnippet(trimmed);
            setStatus('Text added — tap Analyze when ready.');
        }, true);
    }

    function boot() {
        if (!document.getElementById('siAiCaptureToggle')) return;
        if (!getSalesAiApi() || typeof getSalesAiApi().addLineFromItem !== 'function') {
            setTimeout(boot, 50);
            return;
        }
        bindSiAiScreenshotCapture();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
