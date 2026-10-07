(function () {
    const cfg = window.__AI_FORECAST_REPORTS__ || {};
    const fmt = (n, d) => {
        const x = Number(n);
        if (!Number.isFinite(x)) return '—';
        return x.toLocaleString(undefined, { maximumFractionDigits: d != null ? d : 2 });
    };
    const esc = (s) => {
        const d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    };
    const tagClass = (v) => {
        const s = String(v || '').toLowerCase();
        if (s.includes('fast')) return 'ai-fc-tag--fast';
        if (s.includes('dead')) return 'ai-fc-tag--dead';
        if (s.includes('under') || s.includes('warn')) return 'ai-fc-tag--slow';
        return 'ai-fc-tag--slow';
    };
    const segClass = (v) => {
        const s = String(v || '').toLowerCase();
        if (s.includes('high')) return 'ai-fc-seg--high';
        if (s.includes('walk')) return 'ai-fc-seg--walk';
        return 'ai-fc-seg--regular';
    };

    let chartInst = null;
    const tableRegistry = new Map();

    const TABLE_CONFIGS = {
        reorder: {
            columns: [
                { key: 'itemcode', label: 'Item', sort: 'num' },
                { key: 'itemname', label: 'Name' },
                { key: 'current_stock', label: 'Stock', num: 3, sort: 'num' },
                { key: 'pending_lpo_qty', label: 'Pending PO', num: 3, sort: 'num' },
                { key: 'avg_daily_sales', label: 'Avg daily', num: 4, sort: 'num' },
                { key: 'lead_days', label: 'Lead days', num: 1, sort: 'num' },
                { key: 'reorder_point', label: 'Reorder pt', num: 2, sort: 'num' },
                { key: 'recommended_qty', label: 'Suggest qty', num: 2, sort: 'num' },
                { key: 'days_of_cover', label: 'Days cover', num: 1, sort: 'num' },
                { key: 'risk', label: 'Risk' },
                { key: 'velocity_class', label: 'Class', tag: true },
            ],
            rows: (d) => d.rows || [],
        },
        dead_stock: {
            columns: [
                { key: 'itemcode', label: 'Item', sort: 'num' },
                { key: 'itemname', label: 'Name' },
                { key: 'current_stock', label: 'Stock', num: 3, sort: 'num' },
                { key: 'avg_daily_sales', label: 'Avg daily', num: 4, sort: 'num' },
                { key: 'revenue', label: 'Revenue', num: 2, sort: 'num' },
                { key: 'velocity_class', label: 'Class', tag: true },
            ],
            rows: (d) => d.rows || [],
        },
        fast_moving: {
            columns: [
                { key: 'itemcode', label: 'Item', sort: 'num' },
                { key: 'itemname', label: 'Name' },
                { key: 'sold_qty', label: 'Sold qty', num: 3, sort: 'num' },
                { key: 'avg_daily_sales', label: 'Avg daily', num: 4, sort: 'num' },
                { key: 'revenue', label: 'Revenue', num: 2, sort: 'num' },
                { key: 'return_ratio', label: 'Return %', pct: true, sort: 'num' },
                { key: 'velocity_class', label: 'Class', tag: true },
            ],
            rows: (d) => d.rows || [],
        },
        supplier_analysis: {
            columns: [
                { key: 'supplier_code', label: 'Code', sort: 'num' },
                { key: 'supplier_name', label: 'Supplier' },
                { key: 'receipt_count', label: 'Receipts', num: 0, sort: 'num' },
                { key: 'avg_purchase_cost', label: 'Avg cost', num: 4, sort: 'num' },
                { key: 'avg_lead_days', label: 'Lead days', num: 1, sort: 'num' },
                { key: 'price_fluctuation_pct', label: 'Price fluct %', num: 1, sort: 'num' },
                { key: 'item_variety', label: 'SKU variety', num: 0, sort: 'num' },
                { key: 'rating', label: 'Score', num: 1, sort: 'num' },
                { key: 'preferred', label: 'Preferred', bool: true },
            ],
            rows: (d) => d.rows || [],
        },
    };

    function destroyChart() {
        if (chartInst) {
            try { chartInst.destroy(); } catch (e) { /* ignore */ }
            chartInst = null;
        }
    }

    function cellValue(row, c) {
        let v = row[c.key];
        if (c.key === 'segment') {
            const lbl = String(v || 'regular').replace(/_/g, ' ');
            return `<td><span class="ai-fc-seg ${segClass(v)}">${esc(lbl)}</span></td>`;
        }
        if (c.bool) return `<td>${v ? 'Yes' : 'No'}</td>`;
        if (c.pct) {
            const n = Number(v) * 100;
            return `<td class="num">${Number.isFinite(n) ? fmt(n, 1) + '%' : '—'}</td>`;
        }
        if (c.num != null) return `<td class="num">${fmt(v, c.num)}</td>`;
        if (c.tag) {
            return `<td><span class="ai-fc-tag ${tagClass(v)}">${esc(v)}</span></td>`;
        }
        return `<td>${esc(v ?? '')}</td>`;
    }

    function renderTable(columns, rows, tableId) {
        if (!rows.length) {
            return '<p class="ai-fc-muted">No rows for this report.</p>';
        }
        const tid = tableId || ('aiFcTbl' + Math.random().toString(36).slice(2, 8));
        tableRegistry.set(tid, { rows: rows.slice(), columns });
        const head = columns.map((c) => {
            const sortAttr = c.sort ? ` class="sortable" data-key="${esc(c.key)}"` : '';
            return `<th${sortAttr}>${esc(c.label)}</th>`;
        }).join('');
        const body = rows.map((row) => `<tr>${columns.map((c) => cellValue(row, c)).join('')}</tr>`).join('');
        return `<div class="ai-fc-table-scroll ai-fc-table-scroll--report"><table class="ai-fc-table ai-fc-table--sortable" id="${tid}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    }

    function bindSortableTables(root) {
        (root || document).querySelectorAll('.ai-fc-table--sortable').forEach((table) => {
            if (table.dataset.sortBound) return;
            const reg = tableRegistry.get(table.id);
            if (!reg) return;
            table.dataset.sortBound = '1';
            const rows = reg.rows;
            const columns = reg.columns;
            const state = { key: null, dir: 'desc' };
            table.querySelectorAll('th.sortable').forEach((th) => {
                th.addEventListener('click', () => {
                    const key = th.dataset.key;
                    const col = columns.find((c) => c.key === key);
                    if (!col) return;
                    if (state.key === key) state.dir = state.dir === 'asc' ? 'desc' : 'asc';
                    else { state.key = key; state.dir = 'desc'; }
                    table.querySelectorAll('th.sortable').forEach((h) => {
                        h.classList.remove('sort-asc', 'sort-desc');
                    });
                    th.classList.add(state.dir === 'asc' ? 'sort-asc' : 'sort-desc');
                    const sorted = rows.slice().sort((a, b) => {
                        let va = a[key];
                        let vb = b[key];
                        if (col.pct) { va = Number(va) * 100; vb = Number(vb) * 100; }
                        if (col.sort === 'num' || col.num != null) {
                            va = Number(va);
                            vb = Number(vb);
                            if (!Number.isFinite(va)) va = -Infinity;
                            if (!Number.isFinite(vb)) vb = -Infinity;
                        } else {
                            va = String(va ?? '').toLowerCase();
                            vb = String(vb ?? '').toLowerCase();
                        }
                        if (va < vb) return state.dir === 'asc' ? -1 : 1;
                        if (va > vb) return state.dir === 'asc' ? 1 : -1;
                        return 0;
                    });
                    const tbody = table.querySelector('tbody');
                    tbody.innerHTML = sorted.map((row) =>
                        `<tr>${columns.map((c) => cellValue(row, c)).join('')}</tr>`
                    ).join('');
                });
            });
        });
    }

    function renderKpis(items) {
        const el = document.getElementById('aiFcReportKpis');
        if (!el) return;
        if (!items || !items.length) {
            el.classList.add('hidden');
            el.innerHTML = '';
            return;
        }
        el.classList.remove('hidden');
        el.innerHTML = items.map((k) =>
            `<div class="ai-fc-kpi"><div class="ai-fc-kpi-label">${esc(k.label)}</div><div class="ai-fc-kpi-val${k.cls ? ' ' + k.cls : ''}">${esc(k.value)}</div></div>`
        ).join('');
    }

    function renderInsights(bullets) {
        const el = document.getElementById('aiFcReportInsights');
        if (!el) return;
        if (!bullets || !bullets.length) {
            el.classList.add('hidden');
            el.innerHTML = '';
            return;
        }
        el.classList.remove('hidden');
        el.innerHTML = '<strong>Key takeaways</strong><ul>' +
            bullets.map((b) => `<li>${esc(b)}</li>`).join('') + '</ul>';
    }

    function renderSalesForecast(d) {
        const data = d.data || {};
        const ma = data.moving_average || {};
        const items = data.item_demand_forecast || [];
        renderKpis([
            { label: 'Predicted qty (30d)', value: fmt(data.predicted_qty, 0) },
            { label: 'Predicted amount', value: fmt(data.predicted_amount, 2) },
            { label: 'Growth 30d', value: data.growth_pct_30d != null ? data.growth_pct_30d + '%' : '—', cls: Number(data.growth_pct_30d) > 0 ? 'ai-fc-kpi-val--ok' : '' },
            { label: 'MA 7 / 30 / 90', value: `${fmt(ma['7d'], 2)} / ${fmt(ma['30d'], 2)} / ${fmt(ma['90d'], 2)}` },
            { label: 'YoY same period', value: fmt(data.yoy_same_period_qty, 0) },
            { label: 'Top SKUs forecast', value: fmt(items.length, 0) },
        ]);
        renderInsights([
            `30-day quantity forecast: ${fmt(data.predicted_qty, 0)} units (${fmt(data.predicted_amount, 2)} value).`,
            data.growth_pct_30d != null ? `Sales trend vs prior 30 days: ${data.growth_pct_30d}%` : 'Compare last 30d qty to prior period for trend.',
            (data.fast_moving_items || []).length ? `${(data.fast_moving_items || []).length} fast movers drive short-term demand.` : null,
            (data.slow_moving_items || []).length ? `Review ${(data.slow_moving_items || []).length} slow/dead lines for clearance.` : null,
        ].filter(Boolean));
        const charts = document.getElementById('aiFcReportCharts');
        charts.classList.remove('hidden');
        charts.innerHTML = '<div class="ai-fc-grid-2"><div class="ai-fc-card"><div class="ai-fc-card__head">Daily sales (90d)</div><div class="ai-fc-card__body"><div class="ai-fc-chart-wrap"><canvas id="aiFcReportChart"></canvas></div></div></div></div>';
        const series = data.daily_series || [];
        if (typeof Chart !== 'undefined' && series.length) {
            destroyChart();
            chartInst = new Chart(document.getElementById('aiFcReportChart'), {
                type: 'line',
                data: {
                    labels: series.map((x) => x.date),
                    datasets: [{ label: 'Qty', data: series.map((x) => x.qty), borderColor: '#059669', backgroundColor: 'rgba(5,150,105,0.12)', tension: 0.25, fill: true }],
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { maxTicksLimit: 12 } } } },
            });
        }
        const cols = [
            { key: 'itemcode', label: 'Item', sort: 'num' },
            { key: 'itemname', label: 'Name' },
            { key: 'predicted_qty', label: 'Predicted qty', num: 2, sort: 'num' },
            { key: 'velocity_class', label: 'Class', tag: true },
        ];
        return '<h3 class="ai-fc-report-h3">Item demand forecast</h3>' + renderTable(cols, items, 'aiFcSalesItems');
    }

    function renderPurchaseForecast(d) {
        const data = d.data || {};
        const reorder = data.reorder_list || [];
        const understock = reorder.filter((r) => r.needs_reorder);
        renderKpis([
            { label: 'Understock lines', value: fmt(data.understock_count, 0), cls: 'ai-fc-kpi-val--warn' },
            { label: 'Suggested purchase qty', value: fmt(data.suggested_purchase_qty_total, 0) },
            { label: 'Overstock items', value: fmt((data.overstock_items || []).length, 0), cls: 'ai-fc-kpi-val--danger' },
            { label: 'Total reorder lines', value: fmt(reorder.length, 0) },
        ]);
        renderInsights([
            `${fmt(data.understock_count, 0)} SKUs below reorder point — total suggested order ${fmt(data.suggested_purchase_qty_total, 0)} units.`,
            (data.overstock_items || []).length ? `${(data.overstock_items || []).length} overstock risks; reduce inbound or run promotions.` : 'No major overstock flags in top list.',
            understock.length ? `Priority: top ${Math.min(5, understock.length)} lines by suggested qty in table below.` : 'Stock levels appear adequate for listed items.',
        ]);
        document.getElementById('aiFcReportCharts').classList.add('hidden');
        let html = '';
        html += '<h3 class="ai-fc-report-h3">Understock — suggested reorder</h3>';
        html += renderTable(TABLE_CONFIGS.reorder.columns, understock.slice(0, 200), 'aiFcPurchaseUnder');
        html += '<h3 class="ai-fc-report-h3">Overstock risk</h3>';
        html += renderTable([
            { key: 'itemcode', label: 'Item', sort: 'num' },
            { key: 'itemname', label: 'Name' },
            { key: 'current_stock', label: 'Stock', num: 3, sort: 'num' },
            { key: 'maximum_level', label: 'Max level', num: 3, sort: 'num' },
            { key: 'days_cover', label: 'Days cover', num: 0, sort: 'num' },
            { key: 'risk', label: 'Risk' },
        ], (data.overstock_items || []).slice(0, 100), 'aiFcPurchaseOver');
        return html;
    }

    function renderCustomerPattern(d) {
        const data = d.data || {};
        const customers = data.customers || [];
        renderKpis([
            { label: 'Customers', value: fmt(customers.length, 0) },
            { label: 'Cross-sell profiles', value: fmt((data.cross_sell || []).length, 0) },
            { label: 'High value', value: fmt(customers.filter((c) => c.segment === 'high_value').length, 0), cls: 'ai-fc-kpi-val--ok' },
            { label: 'Walk-in', value: fmt(customers.filter((c) => c.segment === 'walk_in').length, 0) },
        ]);
        const topAmt = customers[0];
        renderInsights([
            customers.length ? `Top customer: ${topAmt.customer_name || topAmt.customer_code} (${fmt(topAmt.total_amount, 2)}).` : 'No customer sales in the last 180 days.',
            customers.filter((c) => c.segment === 'high_value').length + ' high-value accounts — prioritize retention and upsell.',
            (data.cross_sell || []).length ? 'Cross-sell table shows top items per customer for basket expansion.' : null,
        ].filter(Boolean));
        document.getElementById('aiFcReportCharts').classList.add('hidden');
        let html = '<h3 class="ai-fc-report-h3">Top customers (180d)</h3>';
        html += renderTable([
            { key: 'customer_code', label: 'Code', sort: 'num' },
            { key: 'customer_name', label: 'Customer' },
            { key: 'total_amount', label: 'Amount', num: 2, sort: 'num' },
            { key: 'bill_count', label: 'Bills', num: 0, sort: 'num' },
            { key: 'purchase_frequency_days', label: 'Freq (days)', num: 1, sort: 'num' },
            { key: 'segment', label: 'Segment' },
        ], customers, 'aiFcCustTable');
        const cross = data.cross_sell || [];
        if (cross.length) {
            html += '<h3 class="ai-fc-report-h3">Cross-sell / top items by customer</h3>';
            html += '<div class="ai-fc-list">';
            cross.slice(0, 25).forEach((x) => {
                const items = (x.top_items || []).map((i) => `#${i.itemcode} (${fmt(i.qty, 2)})`).join(', ');
                html += `<div class="ai-fc-list-item"><strong>Customer ${esc(x.customer_code)}</strong> — ${esc(items || '—')}</div>`;
            });
            html += '</div>';
        }
        return html;
    }

    function tableReportKpis(rt, rows) {
        if (rt === 'reorder') {
            const need = rows.filter((r) => r.needs_reorder);
            return [
                { label: 'Lines', value: fmt(rows.length, 0) },
                { label: 'Need reorder', value: fmt(need.length, 0), cls: 'ai-fc-kpi-val--warn' },
                { label: 'Suggested qty', value: fmt(need.reduce((s, r) => s + (Number(r.recommended_qty) || 0), 0), 0) },
                { label: 'Understock risk', value: fmt(need.filter((r) => r.risk === 'understock').length, 0), cls: 'ai-fc-kpi-val--danger' },
            ];
        }
        if (rt === 'dead_stock') {
            const rev = rows.reduce((s, r) => s + (Number(r.revenue) || 0), 0);
            return [
                { label: 'Dead SKUs', value: fmt(rows.length, 0), cls: 'ai-fc-kpi-val--danger' },
                { label: 'Stock on hand', value: fmt(rows.reduce((s, r) => s + (Number(r.current_stock) || 0), 0), 0) },
                { label: 'Revenue (period)', value: fmt(rev, 2) },
            ];
        }
        if (rt === 'fast_moving') {
            return [
                { label: 'Fast movers', value: fmt(rows.length, 0), cls: 'ai-fc-kpi-val--ok' },
                { label: 'Sold qty', value: fmt(rows.reduce((s, r) => s + (Number(r.sold_qty) || 0), 0), 0) },
                { label: 'Revenue', value: fmt(rows.reduce((s, r) => s + (Number(r.revenue) || 0), 0), 2) },
            ];
        }
        if (rt === 'supplier_analysis') {
            return [
                { label: 'Suppliers', value: fmt(rows.length, 0) },
                { label: 'Preferred', value: fmt(rows.filter((r) => r.preferred).length, 0), cls: 'ai-fc-kpi-val--ok' },
                { label: 'Avg lead (top)', value: rows.length ? fmt(rows[0].avg_lead_days, 1) + ' d' : '—' },
            ];
        }
        return [{ label: 'Total rows', value: fmt(rows.length, 0) }];
    }

    function tableReportInsights(rt, rows) {
        if (rt === 'reorder') {
            const need = rows.filter((r) => r.needs_reorder);
            return [
                `${need.length} of ${rows.length} lines need replenishment.`,
                need.length ? `Largest suggested order: ${fmt(Math.max(...need.map((r) => Number(r.recommended_qty) || 0)), 0)} units on one SKU.` : 'All listed lines are above reorder point.',
            ];
        }
        if (rt === 'dead_stock') {
            return [`${rows.length} items with little or no movement — consider markdown or transfer.`, 'Focus on highest stock value dead lines first.'];
        }
        if (rt === 'fast_moving') {
            return [`${rows.length} high-velocity SKUs — ensure safety stock and supplier lead times.`, 'Monitor return % on fast lines for quality issues.'];
        }
        if (rt === 'supplier_analysis') {
            const pref = rows.filter((r) => r.preferred);
            return [
                `${pref.length} preferred suppliers for PO consolidation.`,
                rows.length ? `Top supplier by receipts: ${rows[0].supplier_name || rows[0].supplier_code}.` : 'No receipt history in the last year.',
            ];
        }
        return [];
    }

    function renderReport(payload) {
        const rt = payload.report || payload.report_type || cfg.reportType || 'reorder';
        const titleEl = document.getElementById('aiFcReportTitle');
        const metaEl = document.getElementById('aiFcReportMeta');
        const content = document.getElementById('aiFcReportContent');
        const charts = document.getElementById('aiFcReportCharts');
        const loading = document.getElementById('aiFcReportLoading');

        destroyChart();
        charts.classList.add('hidden');
        charts.innerHTML = '';

        const label = (cfg.reportLabels && cfg.reportLabels[rt]) || rt;
        if (titleEl) titleEl.textContent = label;
        const count = payload.row_count != null ? payload.row_count : (payload.rows || []).length;
        if (metaEl) metaEl.textContent = ` · ${count} rows · branch ${cfg.locationCode || ''}`;

        let html = '';
        if (rt === 'sales_forecast') html = renderSalesForecast(payload);
        else if (rt === 'purchase_forecast') html = renderPurchaseForecast(payload);
        else if (rt === 'customer_pattern') html = renderCustomerPattern(payload);
        else if (TABLE_CONFIGS[rt]) {
            const rows = TABLE_CONFIGS[rt].rows(payload) || [];
            renderKpis(tableReportKpis(rt, rows));
            renderInsights(tableReportInsights(rt, rows));
            html = renderTable(TABLE_CONFIGS[rt].columns, rows, 'aiFcTbl_' + rt);
        } else {
            renderKpis([]);
            renderInsights([]);
            html = `<pre class="ai-fc-json-fallback">${esc(JSON.stringify(payload, null, 2))}</pre>`;
        }

        if (loading) loading.classList.add('hidden');
        if (content) {
            content.classList.remove('hidden');
            content.innerHTML = html;
            bindSortableTables(content);
        }
    }

    function showError(msg) {
        const el = document.getElementById('aiFcReportError');
        if (!el) return;
        if (!msg) { el.classList.add('hidden'); el.textContent = ''; return; }
        el.textContent = msg;
        el.classList.remove('hidden');
    }

    function loadReport() {
        const status = document.getElementById('aiFcReportStatus');
        const loading = document.getElementById('aiFcReportLoading');
        const content = document.getElementById('aiFcReportContent');
        if (status) status.textContent = 'Loading…';
        showError('');
        renderInsights([]);
        if (loading) {
            loading.classList.remove('hidden');
            loading.textContent = 'Loading report…';
        }
        if (content) content.classList.add('hidden');
        document.getElementById('aiFcReportKpis')?.classList.add('hidden');

        fetch(cfg.apiReport)
            .then((r) => r.json())
            .then((d) => {
                if (!d.success) {
                    if (status) status.textContent = 'Failed';
                    showError(d.error || 'Could not load report.');
                    if (loading) {
                        loading.classList.remove('hidden');
                        loading.textContent = d.error || 'Load failed';
                    }
                    return;
                }
                renderReport(d);
                if (status) status.textContent = 'Updated ' + new Date().toLocaleTimeString();
            })
            .catch(() => {
                if (status) status.textContent = 'Request failed';
                showError('Network error loading report.');
            });
    }

    document.getElementById('aiFcReportRefresh')?.addEventListener('click', loadReport);
    document.getElementById('aiFcReportPrint')?.addEventListener('click', () => window.print());

    const exportBtn = document.getElementById('aiFcReportExport');
    if (exportBtn && cfg.exportUrl) {
        exportBtn.href = cfg.exportUrl;
    }

    if (document.getElementById('aiFcReportsPage')) {
        loadReport();
    }
})();
