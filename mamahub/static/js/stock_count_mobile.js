/**
 * Stock counting — mobile / PDT UI (Material-style).
 */
const ScmMobile = (function () {
    function toast(msg, type) {
        const el = document.getElementById('scmToast');
        if (!el) return;
        el.textContent = msg;
        el.className = 'scm-toast' + (type ? ` scm-toast--${type}` : '');
        el.hidden = false;
        clearTimeout(el._t);
        el._t = setTimeout(() => {
            el.hidden = true;
        }, 2800);
    }

    function vibrate(ms) {
        if (navigator.vibrate) navigator.vibrate(ms || 30);
    }

    async function postJson(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
            throw new Error(data.error || 'Request failed');
        }
        return data;
    }

    function openSheet(id) {
        const sheet = document.getElementById(id);
        const backdrop = document.getElementById('scmSheetBackdrop');
        if (!sheet) return;
        sheet.hidden = false;
        requestAnimationFrame(() => sheet.classList.add('is-open'));
        if (backdrop) backdrop.hidden = false;
    }

    function closeSheets() {
        document.querySelectorAll('.scm-sheet.is-open').forEach((s) => {
            s.classList.remove('is-open');
            setTimeout(() => {
                s.hidden = true;
            }, 280);
        });
        const backdrop = document.getElementById('scmSheetBackdrop');
        if (backdrop) backdrop.hidden = true;
    }

    function bindSheetBackdrop() {
        const backdrop = document.getElementById('scmSheetBackdrop');
        if (backdrop && !backdrop.dataset.bound) {
            backdrop.dataset.bound = '1';
            backdrop.addEventListener('click', closeSheets);
        }
    }

    function fmtQty(n) {
        const x = Number(n);
        if (!Number.isFinite(x)) return '0';
        return Math.abs(x - Math.round(x)) < 0.001 ? String(Math.round(x)) : x.toFixed(3);
    }

    function renderLinesHtml(lines) {
        if (!lines || !lines.length) {
            return `<div class="scm-empty"><i class="bi bi-inbox"></i><p>Scan a barcode to add the first line.</p></div>`;
        }
        return lines.map((ln) => {
            const v = Number(ln.variance_qty || 0);
            const varCls =
                v > 0.0005 ? ' scm-line-card__var--pos' : v < -0.0005 ? ' scm-line-card__var--neg' : '';
            const iconVar = Math.abs(v) > 0.0005 ? ' scm-line-card__icon--var' : '';
            const varTxt = Math.abs(v) > 0.0005 ? `${v >= 0 ? '+' : ''}${v.toFixed(3)}` : '—';
            const bc = ln.barcode ? ` · ${ln.barcode}` : '';
            const name = (ln.item_name || `Item ${ln.itemcode}`).replace(/</g, '&lt;');
            const wh =
                ln.warehouse_code ||
                ln.warehouse_name ||
                (ln.warehouse_id ? `WH ${ln.warehouse_id}` : '');
            const whHtml = wh
                ? `<p class="scm-line-card__meta" style="font-size:12px;margin:2px 0 0;opacity:.85;">${String(wh).replace(/</g, '&lt;')}</p>`
                : '';
            return `<div class="scm-line-card" data-line="${ln.line_no || ''}">
              <div class="scm-line-card__icon${iconVar}"><i class="bi bi-box-seam"></i></div>
              <div class="scm-line-card__main">
                <div class="scm-line-card__code">#${ln.itemcode || ''}${bc}</div>
                <p class="scm-line-card__name">${name}</p>
                ${whHtml}
                <div class="scm-line-card__nums">
                  <div><span>System</span><strong>${fmtQty(ln.system_qty)}</strong></div>
                  <div><span>Counted</span><strong>${fmtQty(ln.counted_qty)}</strong></div>
                </div>
              </div>
              <div class="scm-line-card__var${varCls}">${varTxt}</div>
            </div>`;
        }).join('');
    }

    function updateStats(lines) {
        const n = (lines || []).length;
        let varN = 0;
        let total = 0;
        (lines || []).forEach((ln) => {
            const v = Number(ln.variance_qty || 0);
            if (Math.abs(v) > 0.0005) varN += 1;
            total += Number(ln.counted_qty || 0);
        });
        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        set('scmStatLines', n);
        set('scmStatVar', varN);
        set('scmStatQty', fmtQty(total));
        set('scmBottomLines', `${n} items`);
    }

    function initHome() {
        bindSheetBackdrop();
        const fab = document.getElementById('scmFabNew');
        fab?.addEventListener('click', () => openSheet('scmNewSheet'));

        document.querySelectorAll('.scm-chip').forEach((chip) => {
            chip.addEventListener('click', () => {
                document.querySelectorAll('.scm-chip').forEach((c) => c.classList.remove('is-active'));
                chip.classList.add('is-active');
                const f = (chip.dataset.filter || '').toUpperCase();
                document.querySelectorAll('#scmCountList .scm-card').forEach((card) => {
                    const st = (card.dataset.status || '').toUpperCase();
                    card.style.display = !f || st === f ? '' : 'none';
                });
                const visible = document.querySelectorAll('#scmCountList .scm-card[style=""], #scmCountList .scm-card:not([style])');
                let any = false;
                document.querySelectorAll('#scmCountList .scm-card').forEach((c) => {
                    if (c.style.display !== 'none') any = true;
                });
                const empty = document.getElementById('scmEmptyDefault');
                if (empty) empty.style.display = any ? 'none' : '';
            });
        });
    }

    const HTML5_QR_CDN = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
    let html5QrInstance = null;
    let cameraBusy = false;
    let lastCameraScanAt = 0;

    function loadHtml5QrcodeLib() {
        return new Promise((resolve, reject) => {
            if (window.Html5Qrcode) {
                resolve();
                return;
            }
            const existing = document.querySelector('script[data-scm-html5-qrcode]');
            if (existing) {
                existing.addEventListener('load', () => resolve());
                existing.addEventListener('error', () => reject(new Error('Scanner library failed to load')));
                return;
            }
            const s = document.createElement('script');
            s.src = HTML5_QR_CDN;
            s.async = true;
            s.dataset.scmHtml5Qrcode = '1';
            s.onload = () => resolve();
            s.onerror = () => reject(new Error('Scanner library failed to load. Check internet connection.'));
            document.head.appendChild(s);
        });
    }

    async function stopCameraScanner() {
        const modal = document.getElementById('scmCameraModal');
        if (html5QrInstance) {
            try {
                const state = html5QrInstance.getState();
                if (state === 2 /* SCANNING */) {
                    await html5QrInstance.stop();
                }
            } catch (e) {
                /* ignore */
            }
            try {
                html5QrInstance.clear();
            } catch (e2) {
                /* ignore */
            }
            html5QrInstance = null;
        }
        if (modal) {
            modal.hidden = true;
            modal.setAttribute('aria-hidden', 'true');
        }
        cameraBusy = false;
    }

    function initCameraScanner(scanInput, onBarcode) {
        const openCamera = async () => {
            if (cameraBusy) return;
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                toast(
                    'Camera not available. Use HTTPS, or type the barcode manually.',
                    'error'
                );
                return;
            }
            cameraBusy = true;
            const modal = document.getElementById('scmCameraModal');
            const hint = document.getElementById('scmCameraHint');
            if (hint) hint.textContent = 'Allow camera access when prompted…';
            try {
                await loadHtml5QrcodeLib();
                if (modal) {
                    modal.hidden = false;
                    modal.setAttribute('aria-hidden', 'false');
                }
                const readerEl = document.getElementById('scmCameraReader');
                if (!readerEl) throw new Error('Scanner element missing');
                readerEl.innerHTML = '';
                html5QrInstance = new Html5Qrcode('scmCameraReader');
                const config = {
                    fps: 12,
                    qrbox: (vw, vh) => {
                        const w = Math.min(vw * 0.92, 320);
                        const h = Math.min(vh * 0.35, 140);
                        return { width: w, height: h };
                    },
                    aspectRatio: 1.777,
                };
                const onSuccess = (decodedText) => {
                    const code = String(decodedText || '').trim();
                    if (!code) return;
                    const now = Date.now();
                    if (now - lastCameraScanAt < 800) return;
                    lastCameraScanAt = now;
                    vibrate(50);
                    if (scanInput) scanInput.value = code;
                    if (hint) hint.textContent = `Scanned: ${code}`;
                    if (typeof onBarcode === 'function') onBarcode(code);
                    stopCameraScanner().then(() => {
                        if (scanInput) scanInput.focus();
                    });
                };
                try {
                    await html5QrInstance.start(
                        { facingMode: 'environment' },
                        config,
                        onSuccess,
                        () => {}
                    );
                } catch (envErr) {
                    await html5QrInstance.start(
                        { facingMode: 'user' },
                        config,
                        onSuccess,
                        () => {}
                    );
                }
                if (hint) hint.textContent = 'Align barcode inside the box';
            } catch (e) {
                await stopCameraScanner();
                const msg = (e && e.message) || String(e);
                if (/denied|permission|notallowed/i.test(msg)) {
                    toast('Camera permission denied. Enable camera for this site in browser settings.', 'error');
                } else if (/secure|https/i.test(msg)) {
                    toast('Camera requires HTTPS. Open the site with https://', 'error');
                } else {
                    toast(msg || 'Could not start camera', 'error');
                }
            } finally {
                cameraBusy = false;
            }
        };

        document.getElementById('scmBtnCamera')?.addEventListener('click', (e) => {
            e.preventDefault();
            openCamera();
        });
        document.getElementById('scmBtnCameraFull')?.addEventListener('click', (e) => {
            e.preventDefault();
            openCamera();
        });
        document.getElementById('scmCameraClose')?.addEventListener('click', (e) => {
            e.preventDefault();
            stopCameraScanner();
        });
    }

    function initScan() {
        bindSheetBackdrop();
        const page = document.getElementById('scmScanPage');
        if (!page) return;

        const countNo = parseInt(page.dataset.countNo, 10);
        const readonly = page.dataset.readonly === '1';
        const apiLine = page.dataset.apiLine;
        const apiPost = page.dataset.apiPost;
        const apiCancel = page.dataset.apiCancel;
        const apiDelete = page.dataset.apiDelete;
        const homeUrl = page.dataset.homeUrl || '/warehouse/stock-counting/mobile';
        const desktopUrl = `/warehouse/stock-counting/${countNo}`;

        const scanInput = document.getElementById('scmScanInput');
        const qtyInput = document.getElementById('scmQtyInput');
        const whInput = document.getElementById('scmWhInput');
        const binInput = document.getElementById('scmBinInput');
        const linesList = document.getElementById('scmLinesList');
        const lastScan = document.getElementById('scmLastScan');
        const lastScanText = document.getElementById('scmLastScanText');
        const statusLabel = document.getElementById('scmStatusLabel');

        if (!readonly) {
            document.getElementById('scmQtyMinus')?.addEventListener('click', () => {
                const v = Math.max(0, parseFloat(qtyInput?.value || '0') - 1);
                if (qtyInput) qtyInput.value = String(v);
            });
            document.getElementById('scmQtyPlus')?.addEventListener('click', () => {
                const v = parseFloat(qtyInput?.value || '0') + 1;
                if (qtyInput) qtyInput.value = String(v);
            });

            async function addLine() {
                const barcode = (scanInput?.value || '').trim();
                const qty = parseFloat(qtyInput?.value || '0');
                const storageId = (binInput?.value || page.dataset.defaultBin || '').trim();
                if (!barcode) {
                    toast('Scan or enter a barcode', 'error');
                    scanInput?.focus();
                    return;
                }
                const payload = { count_no: countNo, barcode, counted_qty: qty, qty };
                if (storageId) payload.storage_id = parseInt(storageId, 10);
                const whId = whInput?.value?.trim();
                if (whId) payload.warehouse_id = parseInt(whId, 10);
                const btn = document.getElementById('scmBtnAdd');
                if (btn) btn.disabled = true;
                try {
                    const data = await postJson(apiLine, payload);
                    if (linesList) linesList.innerHTML = renderLinesHtml(data.lines);
                    updateStats(data.lines);
                    if (statusLabel) statusLabel.textContent = 'PENDING';
                    if (lastScan && lastScanText) {
                        const last = (data.lines || [])[data.lines.length - 1];
                        if (last) {
                            lastScan.classList.add('is-visible');
                            lastScanText.textContent = `#${last.itemcode} · qty ${fmtQty(last.counted_qty)}`;
                        }
                    }
                    vibrate(40);
                    toast('Line saved', 'success');
                    if (scanInput) {
                        scanInput.value = '';
                        scanInput.focus();
                    }
                } catch (e) {
                    vibrate([50, 30, 50]);
                    toast(e.message || 'Save failed', 'error');
                } finally {
                    if (btn) btn.disabled = false;
                }
            }

            document.getElementById('scmBtnAdd')?.addEventListener('click', () => {
                addLine().catch(() => {});
            });
            scanInput?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addLine().catch(() => {});
                }
            });
            initCameraScanner(scanInput, (code) => {
                toast(`Barcode: ${code}`, 'success');
            });
            setTimeout(() => scanInput?.focus(), 300);
        }

        document.getElementById('scmBtnMenu')?.addEventListener('click', () => openSheet('scmMenuSheet'));

        async function doPost(onlyVariance) {
            const msg = onlyVariance
                ? 'Update stock only for lines with variance?'
                : 'Post counted quantities to stock?';
            if (!confirm(msg)) return;
            try {
                const data = await postJson(apiPost, {
                    count_no: countNo,
                    only_variance: !!onlyVariance,
                });
                toast(data.message || 'Posted', 'success');
                setTimeout(() => window.location.reload(), 600);
            } catch (e) {
                toast(e.message || 'Post failed', 'error');
            }
        }

        document.getElementById('scmBtnPost')?.addEventListener('click', () => doPost(false));
        document.getElementById('scmMenuPostVar')?.addEventListener('click', () => {
            closeSheets();
            doPost(true);
        });
        document.getElementById('scmMenuCancel')?.addEventListener('click', async () => {
            closeSheets();
            if (!confirm('Cancel this count?')) return;
            try {
                await postJson(apiCancel, { count_no: countNo });
                toast('Cancelled', 'success');
                setTimeout(() => { window.location.href = homeUrl; }, 500);
            } catch (e) {
                toast(e.message || 'Failed', 'error');
            }
        });
        document.getElementById('scmMenuDelete')?.addEventListener('click', async () => {
            closeSheets();
            if (!confirm('Delete this count?')) return;
            try {
                await postJson(apiDelete, { count_no: countNo });
                window.location.href = homeUrl;
            } catch (e) {
                toast(e.message || 'Failed', 'error');
            }
        });
        document.getElementById('scmMenuDesktop')?.addEventListener('click', () => {
            window.location.href = desktopUrl;
        });
    }

    return { initHome, initScan, toast };
})();
