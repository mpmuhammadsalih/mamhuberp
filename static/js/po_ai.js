/**
 * Purchase Order AI assistant — insights panel, validation, natural language PO creation.
 * Requires window.PurchaseOrderAi hooks from purchase_order_form.html.
 */
(function () {
    const STORAGE_KEY = 'nexa-po-ai-panel-open';
    let lastInsights = null;
    let nlPreview = null;
    let refreshTimer = null;

    function fmt(n, dec) {
        const x = Number(n);
        if (!Number.isFinite(x)) return '0.00';
        return x.toFixed(dec != null ? dec : 2);
    }

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function mdToHtml(text) {
        if (!text) return '';
        return esc(text)
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    function riskClass(level) {
        const l = String(level || '').toLowerCase();
        if (l === 'high') return 'po-ai-risk--high';
        if (l === 'warning') return 'po-ai-risk--warning';
        return 'po-ai-risk--safe';
    }

    function collectState() {
        const api = window.PurchaseOrderAi;
        if (api && typeof api.collectPoState === 'function') {
            return api.collectPoState();
        }
        return {};
    }

    function setStatus(msg, isErr) {
        const el = document.getElementById('poAiStatus');
        if (!el) return;
        el.textContent = msg || '';
        el.style.color = isErr ? '#b91c1c' : '#64748b';
    }

    function renderInsights(data) {
        lastInsights = data;
        const root = document.getElementById('poAiInsightsRoot');
        if (!root || !data || !data.success) return;

        const val = data.validation || {};
        const summary = data.summary || {};
        const riskLevel = summary.risk_level || val.risk_level || 'safe';
        const riskScore = summary.risk_score != null ? summary.risk_score : val.risk_score;

        let html = '';
        html += `<div class="po-ai-risk ${riskClass(riskLevel)}">
          <span class="po-ai-risk__score">${esc(riskScore != null ? riskScore : '—')}</span>
          <span>Risk: <strong>${esc(String(riskLevel).toUpperCase())}</strong> · ${esc(summary.line_count || 0)} line(s) · Total ${fmt(summary.total_amount || 0)}</span>
        </div>`;

        if (data.narrative) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">AI summary</div>
              <div class="po-ai-section__body po-ai-narrative">${mdToHtml(data.narrative)}</div></div>`;
        }

        const reorder = (data.reorder_suggestions || []).filter((r) => r.suggested_qty > 0);
        if (reorder.length) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">Reorder suggestions</div><div class="po-ai-section__body"><ul>`;
            reorder.slice(0, 12).forEach((r) => {
                html += `<li><strong>#${esc(r.itemcode)}</strong> ${esc(r.itemname || '')}: suggest <strong>${fmt(r.suggested_qty, 3)}</strong> (stock ${fmt(r.current_stock, 3)}, reorder ${fmt(r.reorder_level, 3)}${r.pending_po_qty ? `, pending PO ${fmt(r.pending_po_qty, 3)}` : ''})</li>`;
            });
            html += '</ul></div></div>';
        }

        const delivery = data.delivery_prediction || {};
        if (delivery.predicted_date || delivery.avg_lead_days) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">Delivery prediction</div><div class="po-ai-section__body">
              Avg lead: <strong>${delivery.avg_lead_days != null ? esc(delivery.avg_lead_days) + ' days' : '—'}</strong>
              ${delivery.predicted_date ? ` · Expected around <strong>${esc(delivery.predicted_date)}</strong>` : ''}
              ${delivery.sample_size ? ` (${esc(delivery.sample_size)} past deliveries)` : ''}
            </div></div>`;
        }

        const prices = data.price_comparisons || [];
        const priceWarn = prices.filter((p) => p.severity && p.severity !== 'ok');
        if (priceWarn.length) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">Price vs history</div><div class="po-ai-section__body">`;
            priceWarn.slice(0, 10).forEach((p) => {
                const tag = p.severity === 'high' ? 'po-ai-tag--high' : 'po-ai-tag--warn';
                html += `<div class="po-ai-line-card"><span class="po-ai-tag ${tag}">${esc(p.severity)}</span>
                  #${esc(p.itemcode)} rate ${fmt(p.current_rate)} vs ref ${p.reference_rate != null ? fmt(p.reference_rate) : '—'}
                  ${p.variance_pct != null ? ` (${p.variance_pct > 0 ? '+' : ''}${fmt(p.variance_pct, 1)}%)` : ''}</div>`;
            });
            html += '</div></div>';
        }

        const dupes = data.duplicate_pos || [];
        if (dupes.length) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">Duplicate / suspicious PO</div><div class="po-ai-section__body"><ul>`;
            dupes.forEach((d) => {
                html += `<li><span class="po-ai-tag po-ai-tag--warn">PO ${esc(d.lpono)}</span> ${esc(d.lpodate)} — ${esc(d.reason)}</li>`;
            });
            html += '</ul></div></div>';
        }

        const lineInsights = data.line_insights || [];
        const withSup = lineInsights.filter((l) => l.best_supplier);
        if (withSup.length) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">Supplier recommendations</div><div class="po-ai-section__body">`;
            withSup.slice(0, 8).forEach((l) => {
                const bs = l.best_supplier;
                html += `<div class="po-ai-line-card">#${esc(l.itemcode)}: <strong>${esc(bs.supplier_name)}</strong> (score ${fmt(bs.score, 1)}, avg rate ${fmt(bs.avg_rate)})</div>`;
            });
            html += '</div></div>';
        }

        const errs = val.errors || [];
        const warns = val.warnings || [];
        if (errs.length || warns.length) {
            html += `<div class="po-ai-section"><div class="po-ai-section__head">Validation</div><div class="po-ai-section__body">`;
            if (errs.length) {
                html += '<ul>';
                errs.forEach((e) => { html += `<li style="color:#b91c1c;">${esc(e)}</li>`; });
                html += '</ul>';
            }
            if (warns.length) {
                html += '<ul>';
                warns.slice(0, 8).forEach((w) => { html += `<li style="color:#b45309;">${esc(w)}</li>`; });
                html += '</ul>';
            }
            html += '</div></div>';
        }

        if (!html.replace(/\s/g, '')) {
            html = '<p class="po-ai-status">Add supplier and lines, then click Refresh insights.</p>';
        }
        root.innerHTML = html;
    }

    function refreshInsights(opts) {
        const urls = window.__PO_AI__ || {};
        if (!urls.insights) return Promise.resolve(null);
        setStatus('Analyzing…');
        const payload = collectState();
        payload.include_narrative = !!(opts && opts.narrative);
        return fetch(urls.insights, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then((r) => r.json())
            .then((d) => {
                if (!d.success) {
                    setStatus(d.error || 'Analysis failed.', true);
                    return null;
                }
                renderInsights(d);
                setStatus('Updated ' + new Date().toLocaleTimeString());
                return d;
            })
            .catch(() => {
                setStatus('Could not reach AI service.', true);
                return null;
            });
    }

    function scheduleRefresh() {
        if (refreshTimer) clearTimeout(refreshTimer);
        refreshTimer = setTimeout(function () {
            const panel = document.getElementById('poAiPanel');
            if (panel && panel.classList.contains('is-open')) {
                refreshInsights({ narrative: false });
            }
        }, 1200);
    }

    function openPanel() {
        const panel = document.getElementById('poAiPanel');
        const backdrop = document.getElementById('poAiBackdrop');
        if (!panel) return;
        panel.classList.add('is-open');
        if (backdrop) backdrop.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        try { localStorage.setItem(STORAGE_KEY, '1'); } catch (e) {}
        refreshInsights({ narrative: true });
    }

    function closePanel() {
        const panel = document.getElementById('poAiPanel');
        const backdrop = document.getElementById('poAiBackdrop');
        if (panel) panel.classList.remove('is-open');
        if (backdrop) backdrop.classList.add('hidden');
        document.body.style.overflow = '';
        const toggle = document.getElementById('poAiToggle');
        if (toggle) toggle.checked = false;
        try { localStorage.setItem(STORAGE_KEY, '0'); } catch (e) {}
    }

    function renderNlPreview(data) {
        const box = document.getElementById('poAiNlPreview');
        if (!box) return;
        nlPreview = data;
        if (!data || !data.success) {
            box.innerHTML = '';
            box.style.display = 'none';
            return;
        }
        const rows = (data.matched || []).concat(data.unmatched || []);
        if (!rows.length) {
            box.innerHTML = '<p>No lines extracted.</p>';
            box.style.display = 'block';
            return;
        }
        let html = '';
        if (data.supplier_hint) {
            html += `<p>Supplier hint: <strong>${esc(data.supplier_hint)}</strong></p>`;
        }
        rows.forEach((r, i) => {
            const matched = !!(r.matched && r.item);
            const it = r.item || {};
            const label = matched
                ? `#${it.itemcode} ${esc(it.itemname || '')}`
                : esc((r.ai && (r.ai.description || r.ai.barcode)) || 'Unmatched');
            html += `<label class="po-ai-nl-row">
              <input type="checkbox" class="po-ai-nl-pick" data-nl-idx="${i}" ${matched ? 'checked' : ''} ${matched ? '' : 'disabled'} />
              <span>${matched ? '' : '<span class="po-ai-tag po-ai-tag--high">?</span>'}${label} · qty ${fmt(r.qty, 2)} · ${fmt(r.rate)}</span>
            </label>`;
        });
        box.innerHTML = html;
        box.style.display = 'block';
    }

    function applyNlLines() {
        if (!nlPreview || !nlPreview.success) return;
        const api = window.PurchaseOrderAi;
        if (!api || typeof api.appendAiLines !== 'function') {
            alert('PO form hooks not ready.');
            return;
        }
        const picks = document.querySelectorAll('.po-ai-nl-pick:checked');
        const lines = [];
        picks.forEach((cb) => {
            const idx = parseInt(cb.dataset.nlIdx, 10);
            const all = (nlPreview.matched || []).concat(nlPreview.unmatched || []);
            const row = all[idx];
            if (!row || !row.matched || !row.item) return;
            lines.push({
                itemcode: row.item.itemcode,
                itemname: row.item.itemname || '',
                barcode: row.item.barcode || '',
                quantity: Number(row.qty) || 1,
                rate: Number(row.rate) || Number(row.item.costprice) || 0,
                uom: row.uom || row.item.baseuom || 'NOS',
            });
        });
        if (!lines.length) {
            alert('Select matched lines to add.');
            return;
        }
        const n = api.appendAiLines(lines);
        alert(n ? `Added ${n} line(s) from AI.` : 'No lines added.');
        document.getElementById('poAiNlPreview').style.display = 'none';
        nlPreview = null;
        scheduleRefresh();
    }

    function validateBeforeSave(payload) {
        const urls = window.__PO_AI__ || {};
        if (!urls.validate) return Promise.resolve({ can_proceed: true });
        return fetch(urls.validate, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then((r) => r.json())
            .then((d) => {
                if (!d.success) return { can_proceed: true };
                if (d.blocking) {
                    alert('PO validation failed:\n\n' + (d.errors || []).join('\n'));
                    return { can_proceed: false, result: d };
                }
                if ((d.warnings || []).length && payload.approval_save_as === 'approved') {
                    const msg = 'AI validation warnings before approval:\n\n' +
                        (d.warnings || []).slice(0, 8).join('\n') +
                        ((d.warnings || []).length > 8 ? '\n…' : '') +
                        '\n\nSave as Approved anyway?';
                    if (!window.confirm(msg)) {
                        return { can_proceed: false, result: d };
                    }
                }
                return { can_proceed: true, result: d };
            })
            .catch(() => ({ can_proceed: true }));
    }

    function bindOnce() {
        const toggle = document.getElementById('poAiToggle');
        if (!toggle || toggle.dataset.bound === '1') return;
        toggle.dataset.bound = '1';

        toggle.addEventListener('change', function () {
            if (toggle.checked) openPanel();
            else closePanel();
        });

        document.getElementById('poAiPanelClose')?.addEventListener('click', closePanel);
        document.getElementById('poAiBackdrop')?.addEventListener('click', closePanel);
        document.getElementById('poAiRefreshBtn')?.addEventListener('click', function () {
            refreshInsights({ narrative: true });
        });
        document.getElementById('poAiNlParseBtn')?.addEventListener('click', function () {
            const urls = window.__PO_AI__ || {};
            const ta = document.getElementById('poAiNlInput');
            const text = ta ? ta.value.trim() : '';
            if (!urls.nlCreate) {
                setStatus('Natural language requires OpenAI.', true);
                return;
            }
            if (text.length < 8) {
                setStatus('Enter a longer description.', true);
                return;
            }
            setStatus('Parsing…');
            const st = collectState();
            fetch(urls.nlCreate, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, suppliercode: st.suppliercode }),
            })
                .then((r) => r.json())
                .then((d) => {
                    if (!d.success) {
                        setStatus(d.error || 'Parse failed.', true);
                        renderNlPreview(null);
                        return;
                    }
                    renderNlPreview(d);
                    setStatus(`Extracted ${(d.matched || []).length} matched line(s).`);
                })
                .catch(() => setStatus('Parse request failed.', true));
        });
        document.getElementById('poAiNlApplyBtn')?.addEventListener('click', applyNlLines);

        try {
            if (localStorage.getItem(STORAGE_KEY) === '1') {
                toggle.checked = true;
                openPanel();
            }
        } catch (e) {}

        document.addEventListener('po-lines-changed', scheduleRefresh);
        document.addEventListener('po-header-changed', scheduleRefresh);
    }

    window.PoAiAssistant = {
        refreshInsights: refreshInsights,
        validateBeforeSave: validateBeforeSave,
        openPanel: openPanel,
        closePanel: closePanel,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindOnce);
    } else {
        bindOnce();
    }
})();
