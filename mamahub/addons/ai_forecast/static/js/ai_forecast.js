(function () {
    const cfg = window.__AI_FORECAST__ || {};

    const fmt = (n, d) => {
        const x = Number(n);
        if (!Number.isFinite(x)) return '—';
        return x.toLocaleString(undefined, {
            maximumFractionDigits: d != null ? d : 2,
            minimumFractionDigits: d === 0 ? 0 : undefined,
        });
    };

    const esc = (s) => {
        const d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    };

    function tagClass(v) {
        const s = String(v || '').toLowerCase();
        if (s.includes('fast')) return 'ai-fc-tag--fast';
        if (s.includes('dead')) return 'ai-fc-tag--dead';
        return 'ai-fc-tag--slow';
    }

    let chartStore = {};

    function destroyCharts() {
        Object.keys(chartStore).forEach((k) => {
            try {
                chartStore[k].destroy();
            } catch (e) {
                /* ignore */
            }
        });
        chartStore = {};
    }

    function makeChart(id, config) {
        if (typeof Chart === 'undefined') return;
        const el = document.getElementById(id);
        if (!el) return;
        if (chartStore[id]) {
            try {
                chartStore[id].destroy();
            } catch (e) {
                /* ignore */
            }
        }
        chartStore[id] = new Chart(el, {
            ...config,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                ...(config.options || {}),
            },
        });
    }

    function renderNarrativeMarkdown(text) {
        if (!text) return '';
        return esc(text)
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/^# (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>');
    }

    function setKpi(id, val, cls, footId, footText) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = val;
        el.className = 'ai-fc-kpi-val' + (cls ? ' ' + cls : '');
        if (footId && footText != null) {
            const f = document.getElementById(footId);
            if (f) f.textContent = footText;
        }
    }

    function renderKpis(s, horizon) {
        const h = horizon || 30;
        setKpi('aiFcKpiPredQty', fmt(s.predicted_sales_qty_30d, 0));
        const footQty = document.getElementById('aiFcKpiPredQtyFoot');
        if (footQty) footQty.textContent = h + '-day horizon (API uses 30d base)';
        setKpi('aiFcKpiPredAmt', fmt(s.predicted_sales_amount_30d, 2));
        const growth = s.sales_growth_pct;
        setKpi(
            'aiFcKpiGrowth',
            growth != null ? growth + '%' : '—',
            growth > 0 ? 'ai-fc-kpi-val--ok' : growth < 0 ? 'ai-fc-kpi-val--danger' : ''
        );
        setKpi('aiFcKpiLast30', fmt(s.last_30d_sales_qty, 0));
        const yoy = document.getElementById('aiFcKpiYoY');
        if (yoy) yoy.textContent = 'YoY same period: ' + fmt(s.yoy_same_period_qty, 0);
        setKpi('aiFcKpiUnder', fmt(s.understock_alerts, 0), 'ai-fc-kpi-val--warn');
        setKpi('aiFcKpiOver', fmt(s.overstock_alerts, 0), 'ai-fc-kpi-val--danger');
        setKpi('aiFcKpiPurchase', fmt(s.suggested_purchase_qty_total, 0));
        setKpi('aiFcKpiFast', fmt(s.fast_moving_count, 0), 'ai-fc-kpi-val--ok');
        const dead = document.getElementById('aiFcKpiDead');
        if (dead) dead.textContent = 'Slow/dead SKUs: ' + fmt(s.dead_slow_count, 0);
    }

    function renderTrendCharts(sales, purchase) {
        makeChart('aiFcSalesChart', {
            type: 'line',
            data: {
                labels: (sales || []).map((x) => x.date),
                datasets: [
                    {
                        label: 'Sales qty',
                        data: (sales || []).map((x) => x.qty),
                        borderColor: '#059669',
                        backgroundColor: 'rgba(5,150,105,0.12)',
                        tension: 0.25,
                        fill: true,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Sales amount',
                        data: (sales || []).map((x) => x.amount),
                        borderColor: '#2563eb',
                        backgroundColor: 'transparent',
                        tension: 0.25,
                        borderDash: [4, 4],
                        yAxisID: 'y1',
                    },
                ],
            },
            options: {
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
                scales: {
                    y: { beginAtZero: true, position: 'left', title: { display: true, text: 'Qty' } },
                    y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Amount' } },
                },
            },
        });

        makeChart('aiFcPurchaseChart', {
            type: 'bar',
            data: {
                labels: (purchase || []).map((x) => x.date),
                datasets: [
                    {
                        label: 'GRN qty',
                        data: (purchase || []).map((x) => x.qty),
                        backgroundColor: 'rgba(37,99,235,0.75)',
                    },
                ],
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    function renderOutlookChart(summary) {
        const s = summary || {};
        makeChart('aiFcOutlookChart', {
            type: 'bar',
            data: {
                labels: ['Last 7 days', 'Last 30 days', 'Predicted (30d)', 'YoY period'],
                datasets: [
                    {
                        label: 'Quantity',
                        data: [
                            Number(s.last_7d_sales_qty) || 0,
                            Number(s.last_30d_sales_qty) || 0,
                            Number(s.predicted_sales_qty_30d) || 0,
                            Number(s.yoy_same_period_qty) || 0,
                        ],
                        backgroundColor: ['#94a3b8', '#64748b', '#059669', '#f59e0b'],
                    },
                ],
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    function fillTable(sel, rowsHtml, emptyColspan, emptyMsg) {
        const tb = document.querySelector(sel + ' tbody');
        if (!tb) return;
        tb.innerHTML = rowsHtml || `<tr><td colspan="${emptyColspan}">${emptyMsg}</td></tr>`;
    }

    function renderTables(d) {
        const reorder = (d.suggested_reorder || d.low_stock_alerts || []).slice(0, 15);
        fillTable(
            '#aiFcReorderTable',
            reorder
                .map(
                    (r) =>
                        `<tr><td>${esc(r.itemcode)}</td><td>${esc(r.itemname)}</td><td class="num">${fmt(r.current_stock, 2)}</td>` +
                        `<td class="num"><strong>${fmt(r.recommended_qty, 2)}</strong></td><td class="num">${r.days_of_cover != null ? fmt(r.days_of_cover, 1) : '—'}</td>` +
                        `<td><span class="ai-fc-tag ${tagClass(r.velocity_class)}">${esc(r.velocity_class)}</span></td></tr>`
                )
                .join(''),
            6,
            'No reorder suggestions'
        );

        const top = (d.top_selling_items || []).slice(0, 12);
        fillTable(
            '#aiFcTopItemsTable',
            top
                .map(
                    (r) =>
                        `<tr><td>${esc(r.itemcode)}</td><td>${esc(r.itemname)}</td><td class="num">${fmt(r.avg_daily_sales, 3)}</td>` +
                        `<td class="num">${fmt(r.revenue, 2)}</td><td><span class="ai-fc-tag ${tagClass(r.velocity_class)}">${esc(r.velocity_class)}</span></td></tr>`
                )
                .join(''),
            5,
            'No sales velocity data'
        );

        const products = (d.product_leaders || []).slice(0, 10);
        fillTable(
            '#aiFcProductTable',
            products
                .map(
                    (r) =>
                        `<tr><td class="num"><strong>${esc(r.performance_score)}</strong></td><td>${esc(r.itemcode)}</td><td>${esc(r.itemname)}</td>` +
                        `<td>${esc(r.classification || r.velocity_class)}</td><td class="num">${fmt(r.revenue, 2)}</td></tr>`
                )
                .join(''),
            5,
            'No product scores'
        );

        const cust = (d.top_customers || []).slice(0, 10);
        fillTable(
            '#aiFcCustomerTable',
            cust
                .map(
                    (c) =>
                        `<tr><td>${esc(c.customer_name)} <span class="ai-fc-muted">#${esc(c.customer_code)}</span></td>` +
                        `<td class="num">${fmt(c.total_amount, 2)}</td><td class="num">${fmt(c.bill_count, 0)}</td><td>${esc(c.segment)}</td></tr>`
                )
                .join(''),
            4,
            'No customer data'
        );

        renderList(
            'aiFcLowStock',
            (d.low_stock_alerts || []).slice(0, 8),
            (r) =>
                `<div class="ai-fc-list-item ai-fc-list-item--warn"><strong>#${esc(r.itemcode)}</strong> ${esc(r.itemname)} — stock ${fmt(r.current_stock, 2)}, suggest ${fmt(r.recommended_qty, 2)}</div>`,
            'No low-stock lines'
        );

        renderList(
            'aiFcOverstock',
            (d.overstock_warnings || []).slice(0, 8),
            (r) =>
                `<div class="ai-fc-list-item ai-fc-list-item--danger"><strong>#${esc(r.itemcode)}</strong> ${esc(r.itemname)} — stock ${fmt(r.current_stock, 2)}${r.days_cover != null ? ' (' + fmt(r.days_cover, 0) + 'd cover)' : ''}</div>`,
            'No overstock warnings'
        );

        renderList(
            'aiFcSupplierRisk',
            (d.supplier_risk || []).slice(0, 6),
            (s) =>
                `<div class="ai-fc-list-item"><strong>${esc(s.supplier_name || s.supplier_code)}</strong> — score ${fmt(s.rating, 1)}, lead ${fmt(s.avg_lead_days, 1)}d, price fluct ${fmt(s.price_fluctuation_pct, 0)}%</div>`,
            'No supplier risk flags'
        );
    }

    function renderList(id, items, fn, empty) {
        const el = document.getElementById(id);
        if (!el) return;
        if (!items.length) {
            el.innerHTML = `<p class="ai-fc-muted">${empty}</p>`;
            return;
        }
        el.innerHTML = items.map(fn).join('');
    }

    function showError(msg) {
        const el = document.getElementById('aiFcError');
        if (!el) return;
        if (!msg) {
            el.classList.add('hidden');
            el.textContent = '';
            return;
        }
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    function loadDashboard() {
        if (!cfg.apiDashboard) return;
        const status = document.getElementById('aiFcStatus');
        const horizon = parseInt(document.getElementById('aiFcHorizon')?.value || '30', 10) || 30;
        if (status) status.textContent = 'Loading forecast data…';
        showError('');
        destroyCharts();

        const dashUrl = cfg.apiDashboard;
        const salesUrl = cfg.apiSalesForecast ? cfg.apiSalesForecast + '?horizon=' + horizon : null;

        Promise.all([
            fetch(dashUrl).then((r) => r.json()),
            salesUrl ? fetch(salesUrl).then((r) => r.json()).catch(() => null) : Promise.resolve(null),
        ])
            .then(([d, salesExtra]) => {
                if (!d.success) {
                    if (status) status.textContent = 'Load failed';
                    showError(d.error || 'Could not load dashboard.');
                    return;
                }
                let summary = d.summary || {};
                if (salesExtra && salesExtra.success && salesExtra.data) {
                    const sd = salesExtra.data;
                    summary = {
                        ...summary,
                        predicted_sales_qty_30d: sd.predicted_qty,
                        predicted_sales_amount_30d: sd.predicted_amount,
                        sales_growth_pct: sd.growth_pct_30d,
                        last_7d_sales_qty: sd.last_7d_qty,
                        last_30d_sales_qty: sd.last_30d_qty,
                        yoy_same_period_qty: sd.yoy_same_period_qty,
                    };
                    if (sd.daily_series && sd.daily_series.length) {
                        d.sales_trend = sd.daily_series;
                    }
                }
                renderKpis(summary, horizon);
                renderTrendCharts(d.sales_trend || [], d.purchase_trend || []);
                renderOutlookChart(summary);
                renderTables(d);
                if (status) status.textContent = 'Updated ' + new Date().toLocaleTimeString();
            })
            .catch((err) => {
                if (status) status.textContent = 'Could not load dashboard.';
                showError('Network error loading forecast data.');
            });
    }

    function loadNarrative() {
        const box = document.getElementById('aiFcNarrative');
        const btn = document.getElementById('aiFcNarrativeBtn');
        if (!cfg.apiNarrative || !box) return;
        btn.disabled = true;
        box.innerHTML = '<p class="ai-fc-muted">Generating AI summary…</p>';
        fetch(cfg.apiNarrative, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
        })
            .then((r) => r.json())
            .then((d) => {
                btn.disabled = false;
                if (!d.success) {
                    box.innerHTML = '<p class="ai-fc-alert ai-fc-alert--error">' + esc(d.error || 'Failed') + '</p>';
                    return;
                }
                box.innerHTML = '<p>' + renderNarrativeMarkdown(d.narrative || '') + '</p>';
            })
            .catch(() => {
                btn.disabled = false;
                box.textContent = 'Request failed.';
            });
    }

    function loadPageApi(url, renderFn) {
        const status = document.getElementById('aiFcPageStatus');
        if (status) status.textContent = 'Loading…';
        fetch(url)
            .then((r) => r.json())
            .then((d) => {
                if (!d.success) {
                    if (status) status.textContent = d.error || 'Failed';
                    return;
                }
                renderFn(d);
                if (status) status.textContent = '';
            })
            .catch(() => {
                if (status) status.textContent = 'Request failed';
            });
    }

    window.AiForecast = {
        loadDashboard,
        loadPageApi,
        loadNarrative,
        fmt,
        esc,
        tagClass,
        makeChart,
        destroyCharts,
    };

    document.getElementById('aiFcRefreshBtn')?.addEventListener('click', loadDashboard);
    document.getElementById('aiFcHorizon')?.addEventListener('change', loadDashboard);
    document.getElementById('aiFcNarrativeBtn')?.addEventListener('click', loadNarrative);

    if (document.getElementById('aiFcDashboard')) {
        const run = () => loadDashboard();
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
        else run();
    }
})();
