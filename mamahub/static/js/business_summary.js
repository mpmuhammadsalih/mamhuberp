(function () {
  'use strict';

  function boot() {
    var app = document.getElementById('dbsApp');
    if (!app) return;

    var apiUrl = app.getAttribute('data-api') || '';
    var charts = {};
    var lastPayload = null;
    var drillModal = document.getElementById('dbsDrillModal');
    var drillBody = document.getElementById('dbsDrillBody');
    var drillTitle = document.getElementById('dbsDrillTitle');
    if (drillModal && drillModal.parentElement !== document.body) {
      document.body.appendChild(drillModal);
    }

    function esc(s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function openDrillModal(title, html) {
      if (!drillModal) return;
      if (drillTitle) drillTitle.textContent = title;
      if (drillBody) drillBody.innerHTML = html;
      drillModal.classList.remove('hidden');
      document.body.appendChild(drillModal);
    }

    function closeDrillModal() {
      if (!drillModal) return;
      drillModal.classList.add('hidden');
    }

    if (drillModal) {
      drillModal.addEventListener('click', function (e) {
        if (e.target.classList.contains('dbs-modal__backdrop') || e.target.closest('[data-close="dbsDrillModal"]')) {
          closeDrillModal();
        }
      });
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drillModal && !drillModal.classList.contains('hidden')) closeDrillModal();
    });

    function periodNote() {
      if (!lastPayload || !lastPayload.filters) return '';
      var f = lastPayload.filters;
      return '<p class="dbs-drill-note"><strong>Period:</strong> ' + esc(f.date_from || '') + ' to ' + esc(f.date_to || '') + '</p>';
    }

    function summaryTiles(items) {
      return '<div class="dbs-drill-summary">' + items.map(function (t) {
        return '<div class="dbs-drill-summary__item"><span>' + esc(t[0]) + '</span><strong>' + esc(t[1]) + '</strong></div>';
      }).join('') + '</div>';
    }

    function tableHtml(title, cols, rows) {
      if (!rows || !rows.length) {
        return '<div class="dbs-drill-section"><h4>' + esc(title) + '</h4><p class="dbs-drill-note">No records for selected filters.</p></div>';
      }
      var head = cols.map(function (c) { return '<th class="' + (c.num ? 'num' : '') + '">' + esc(c.label) + '</th>'; }).join('');
      var body = rows.map(function (row) {
        return '<tr>' + cols.map(function (c) {
          var v = row[c.key];
          if (c.num) v = fmt(v, c.kind || 'currency');
          return '<td class="' + (c.num ? 'num' : '') + '">' + esc(v == null ? '' : v) + '</td>';
        }).join('') + '</tr>';
      }).join('');
      return '<div class="dbs-drill-section"><h4>' + esc(title) + '</h4><table class="dbs-drill-table"><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>';
    }

    function txRow(name) {
      var rows = (lastPayload && lastPayload.transaction_summary) || [];
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].transaction === name) return rows[i];
      }
      return null;
    }

    function entityRows(key, limit) {
      return ((lastPayload && lastPayload.charts && lastPayload.charts[key]) || []).slice(0, limit || 10);
    }

    function kpiValue(id) {
      var kpis = (lastPayload && lastPayload.kpis) || [];
      for (var i = 0; i < kpis.length; i++) {
        if (kpis[i].id === id) return kpis[i];
      }
      return null;
    }

    function entityTable(title, rows) {
      return tableHtml(title, [
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'amount', label: 'Amount', num: true },
      ], rows);
    }

    function dailyTrendTable(title, rows) {
      return tableHtml(title, [
        { key: 'date', label: 'Date' },
        { key: 'amount', label: 'Amount', num: true },
      ], rows);
    }

    function financialBreakdown() {
      var f = (lastPayload && lastPayload.financial) || {};
      return summaryTiles([
        ['Sales', fmt(f.sales)],
        ['Sales Return', fmt(f.sales_return)],
        ['Net Sales', fmt(f.net_sales)],
        ['Purchases', fmt(f.purchases)],
        ['Purchase Return', fmt(f.purchase_return)],
        ['Net Purchases', fmt(f.net_purchases)],
        ['COGS', fmt(f.cogs)],
        ['Gross Profit', fmt(f.gross_profit)],
        ['Gross Margin %', fmt(f.gross_profit_pct, 'percent')],
        ['Expenses', fmt(f.expense_total)],
        ['Net Profit', fmt(f.net_profit)],
      ]);
    }

    function inventoryTiles() {
      var inv = (lastPayload && lastPayload.inventory) || {};
      return summaryTiles([
        ['Total Items', fmt(inv.total_items, 'number')],
        ['Active Items', fmt(inv.active_items, 'number')],
        ['Out of Stock', fmt(inv.out_of_stock, 'number')],
        ['Low Stock', fmt(inv.low_stock, 'number')],
        ['Negative Stock', fmt(inv.negative_stock, 'number')],
        ['Dead Stock', fmt(inv.dead_stock, 'number')],
      ]);
    }

    function stockPositionTiles() {
      var sp = (lastPayload && lastPayload.kpi_drill && lastPayload.kpi_drill.stock_position) || {};
      return summaryTiles([
        ['Opening Value', fmt(sp.opening_stock)],
        ['Closing Value', fmt(sp.closing_stock)],
        ['Opening Qty', fmt(sp.opening_qty, 'number')],
        ['Closing Qty', fmt(sp.closing_qty, 'number')],
      ]);
    }

    function stockMovementTiles() {
      var sm = (lastPayload && lastPayload.kpi_drill && lastPayload.kpi_drill.stock_movement) || {};
      return summaryTiles([
        ['GRN Amount', fmt(sm.grn_amount)],
        ['GRN Count', fmt(sm.grn_count, 'number')],
        ['Issue Amount', fmt(sm.issue_amount)],
        ['Issue Count', fmt(sm.issue_count, 'number')],
        ['Adjustment Amount', fmt(sm.adjustment_amount)],
        ['Adjustment Count', fmt(sm.adjustment_count, 'number')],
      ]);
    }

    function salesDrillTiles() {
      var s = (lastPayload && lastPayload.kpi_drill && lastPayload.kpi_drill.sales) || {};
      return summaryTiles([
        ['Total Sales', fmt(s.total_sales)],
        ['Sales Bills', fmt(s.sales_count, 'number')],
        ['Sales Return', fmt(s.sales_return)],
        ['Return Bills', fmt(s.return_count, 'number')],
        ['Net Sales', fmt(s.net_sales)],
        ['Cash Sales', fmt(s.cash_sales)],
        ['Credit Sales', fmt(s.credit_sales)],
      ]);
    }

    function purchaseDrillTiles() {
      var p = (lastPayload && lastPayload.kpi_drill && lastPayload.kpi_drill.purchase) || {};
      return summaryTiles([
        ['Total Purchases', fmt(p.total_purchases)],
        ['Purchase Bills', fmt(p.purchase_count, 'number')],
        ['Purchase Return', fmt(p.purchase_return)],
        ['Return Bills', fmt(p.return_count, 'number')],
        ['Net Purchases', fmt(p.net_purchases)],
        ['Source', p.purchase_source || '—'],
      ]);
    }

    var KPI_DRILL = {
      total_sales: function () {
        var k = kpiValue('total_sales');
        var tx = txRow('Sales');
        return periodNote() + salesDrillTiles() +
          (tx ? '<p class="dbs-drill-note"><strong>Transaction summary:</strong> ' + fmt(tx.count, 'number') + ' bills · ' + fmt(tx.amount) + ' (' + tx.percentage + '%)</p>' : '') +
          dailyTrendTable('Daily sales', entityRows('daily_sales_trend', 31)) +
          entityTable('Top selling items', entityRows('top_items', 10));
      },
      sales_return: function () {
        var tx = txRow('Sales Return');
        return periodNote() + salesDrillTiles() +
          (tx ? summaryTiles([['Return Bills', fmt(tx.count, 'number')], ['Return Amount', fmt(tx.amount)], ['Share of Activity', tx.percentage + '%']]) : '') +
          entityTable('Top customers (sales period)', entityRows('top_customers', 10));
      },
      net_sales: function () {
        return periodNote() + financialBreakdown() +
          entityTable('Top customers', entityRows('top_customers', 10)) +
          entityTable('Category-wise sales', entityRows('category_sales', 8));
      },
      total_purchases: function () {
        var tx = txRow('Purchase');
        return periodNote() + purchaseDrillTiles() +
          (tx ? '<p class="dbs-drill-note"><strong>Transaction summary:</strong> ' + fmt(tx.count, 'number') + ' bills · ' + fmt(tx.amount) + '</p>' : '') +
          entityTable('Top suppliers', entityRows('top_suppliers', 10));
      },
      purchase_return: function () {
        var tx = txRow('Purchase Return');
        return periodNote() + purchaseDrillTiles() +
          (tx ? summaryTiles([['Return Bills', fmt(tx.count, 'number')], ['Return Amount', fmt(tx.amount)]]) : '');
      },
      net_purchases: function () {
        return periodNote() + financialBreakdown() + entityTable('Top suppliers', entityRows('top_suppliers', 10));
      },
      gross_profit: function () {
        var f = (lastPayload && lastPayload.financial) || {};
        return periodNote() + financialBreakdown() +
          '<p class="dbs-drill-note"><strong>Formula:</strong> Net Sales (' + fmt(f.net_sales) + ') − COGS (' + fmt(f.cogs) + ') = Gross Profit (' + fmt(f.gross_profit) + ')</p>' +
          entityTable('Top items by sales', entityRows('top_items', 10));
      },
      gross_margin_pct: function () {
        var f = (lastPayload && lastPayload.financial) || {};
        return periodNote() + summaryTiles([
          ['Net Sales', fmt(f.net_sales)],
          ['Gross Profit', fmt(f.gross_profit)],
          ['Gross Margin %', fmt(f.gross_profit_pct, 'percent')],
        ]) +
          '<p class="dbs-drill-note"><strong>Formula:</strong> Gross Profit ÷ Net Sales × 100 = ' + fmt(f.gross_profit_pct, 'percent') + '</p>' +
          entityTable('Category-wise sales', entityRows('category_sales', 8));
      },
      inventory_value: function () {
        var k = kpiValue('inventory_value');
        var inv = (lastPayload && lastPayload.inventory) || {};
        return periodNote() + summaryTiles([['Inventory Value (KPI)', fmt(k && k.value)]]) +
          inventoryTiles() +
          tableHtml('Highest value stock items', [
            { key: 'item_code', label: 'Item' },
            { key: 'item_name', label: 'Name' },
            { key: 'qty', label: 'Qty', num: true, kind: 'number' },
            { key: 'stock_value', label: 'Value', num: true },
          ], inv.highest_value_stock || []);
      },
      current_stock_qty: function () {
        var k = kpiValue('current_stock_qty');
        return periodNote() + summaryTiles([['Current Stock Qty (KPI)', fmt(k && k.value, 'number')]]) + inventoryTiles();
      },
      opening_stock: function () {
        return periodNote() + stockPositionTiles() +
          '<p class="dbs-drill-note">Opening stock value is cumulative inventory movement before the period start date (ITEMJOURNAL).</p>';
      },
      closing_stock: function () {
        return periodNote() + stockPositionTiles() +
          '<p class="dbs-drill-note">Closing stock value is cumulative inventory movement up to the period end date (ITEMJOURNAL).</p>';
      },
      stock_adjustment: function () {
        var tx = txRow('Stock Adjustment');
        return periodNote() + stockMovementTiles() +
          (tx ? summaryTiles([['Adjustment Bills', fmt(tx.count, 'number')], ['Adjustment Amount', fmt(tx.amount)]]) : '');
      },
      goods_received: function () {
        var tx = txRow('Goods Receipt');
        return periodNote() + stockMovementTiles() +
          (tx ? summaryTiles([['GRN Bills', fmt(tx.count, 'number')], ['GRN Amount', fmt(tx.amount)]]) : '') +
          entityTable('Top suppliers (GRN / purchase)', entityRows('top_suppliers', 10));
      },
      goods_issued: function () {
        var tx = txRow('Goods Issue');
        return periodNote() + stockMovementTiles() +
          (tx ? summaryTiles([['Issue Bills', fmt(tx.count, 'number')], ['Issue Amount', fmt(tx.amount)]]) : '');
      },
      customer_receipts: function () {
        var k = kpiValue('customer_receipts');
        var tx = txRow('Expenses');
        return periodNote() + summaryTiles([['Customer Receipts (KPI)', fmt(k && k.value)]]) +
          '<p class="dbs-drill-note">Collections from AR receipt vouchers / settlement tables for the selected period.</p>' +
          tableHtml('Payment method mix (sales)', [
            { key: 'label', label: 'Method' },
            { key: 'amount', label: 'Amount', num: true },
          ], (lastPayload && lastPayload.charts && lastPayload.charts.payment_methods) || []);
      },
      supplier_payments: function () {
        var k = kpiValue('supplier_payments');
        return periodNote() + summaryTiles([['Supplier Payments (KPI)', fmt(k && k.value)]]) +
          '<p class="dbs-drill-note">Payments from AP receipt vouchers / payment tables for the selected period.</p>' +
          entityTable('Top suppliers', entityRows('top_suppliers', 10));
      },
      expenses: function () {
        var k = kpiValue('expenses');
        var f = (lastPayload && lastPayload.financial) || {};
        return periodNote() + summaryTiles([
          ['Expenses (KPI)', fmt(k && k.value)],
          ['Expense Total (P&amp;L)', fmt(f.expense_total)],
          ['Net Profit', fmt(f.net_profit)],
        ]) + financialBreakdown();
      },
      cash_sales: function () {
        return periodNote() + salesDrillTiles() +
          tableHtml('Payment method distribution', [
            { key: 'label', label: 'Method' },
            { key: 'amount', label: 'Amount', num: true },
          ], (lastPayload && lastPayload.charts && lastPayload.charts.payment_methods) || []);
      },
      credit_sales: function () {
        return periodNote() + salesDrillTiles() +
          entityTable('Top credit customers', entityRows('top_customers', 10));
      },
      outstanding_receivables: function () {
        var k = kpiValue('outstanding_receivables');
        var rows = ((lastPayload && lastPayload.kpi_drill && lastPayload.kpi_drill.receivables) || []).slice(0, 100);
        return periodNote() + summaryTiles([
          ['Outstanding Receivables (KPI)', fmt(k && k.value)],
          ['Customers with balance', fmt(rows.length, 'number')],
        ]) +
          tableHtml('Customers by receivable balance', [
            { key: 'code', label: 'Code' },
            { key: 'name', label: 'Customer' },
            { key: 'balance', label: 'Balance', num: true },
            { key: 'account', label: 'Account' },
            { key: 'source', label: 'Source' },
          ], rows);
      },
      outstanding_payables: function () {
        var k = kpiValue('outstanding_payables');
        var rows = ((lastPayload && lastPayload.kpi_drill && lastPayload.kpi_drill.payables) || []).slice(0, 100);
        return periodNote() + summaryTiles([
          ['Outstanding Payables (KPI)', fmt(k && k.value)],
          ['Suppliers with balance', fmt(rows.length, 'number')],
        ]) +
          tableHtml('Suppliers by payable balance', [
            { key: 'code', label: 'Code' },
            { key: 'name', label: 'Supplier' },
            { key: 'balance', label: 'Balance', num: true },
            { key: 'account', label: 'Account' },
            { key: 'source', label: 'Source' },
          ], rows);
      },
    };

    function drillKpi(id) {
      if (!lastPayload) {
        openDrillModal('Details', '<p class="dbs-drill-note">Load dashboard data first.</p>');
        return;
      }
      var fn = KPI_DRILL[id];
      var k = kpiValue(id);
      var title = (k && k.label ? k.label : id) + ' — Details';
      if (!fn) {
        openDrillModal(title, periodNote() + '<p class="dbs-drill-note">No drill-down available for this KPI.</p>');
        return;
      }
      openDrillModal(title, fn());
    }

    function fmt(n, kind) {
      var v = Number(n) || 0;
      if (kind === 'percent') return v.toFixed(1) + '%';
      if (kind === 'number') return Math.round(v).toLocaleString();
      try { return v.toLocaleString('en-IN', { maximumFractionDigits: 0 }); } catch (e) { return String(Math.round(v)); }
    }

    function queryParams() {
      var form = document.getElementById('dbsFilterForm');
      var p = new URLSearchParams();
      if (form) {
        var fd = new FormData(form);
        fd.forEach(function (v, k) { if (v) p.set(k, v); });
      }
      var dbkey = new URLSearchParams(window.location.search).get('dbkey');
      var loc = new URLSearchParams(window.location.search).get('locationcode');
      if (dbkey && !p.has('dbkey')) p.set('dbkey', dbkey);
      if (loc && !p.has('locationcode')) p.set('locationcode', loc);
      return p.toString();
    }

    function setStatus(msg) {
      var el = document.getElementById('dbsStatus');
      if (el) el.textContent = msg || '';
    }

    function showError(msg, asWarning) {
      var el = document.getElementById('dbsError');
      if (!el) return;
      el.textContent = msg || '';
      el.classList.toggle('hidden', !msg);
      if (asWarning && msg) {
        el.style.background = '#fffbeb';
        el.style.borderColor = '#fde68a';
        el.style.color = '#92400e';
      } else if (msg) {
        el.style.background = '#fef2f2';
        el.style.borderColor = '#fecaca';
        el.style.color = '#991b1b';
      }
    }

    function chartReady() {
      return typeof window.Chart !== 'undefined';
    }

    function setChartEmpty(canvasId, empty) {
      var canvas = document.getElementById(canvasId);
      if (!canvas) return;
      var wrap = canvas.closest('.dbs-chart-wrap');
      if (!wrap) return;
      var msg = wrap.querySelector('.dbs-chart-empty');
      if (msg) msg.classList.toggle('hidden', !empty);
      canvas.style.display = empty ? 'none' : 'block';
    }

    function destroyChart(id) {
      if (charts[id]) { charts[id].destroy(); delete charts[id]; }
    }

    function colors() {
      return { blue: '#0078d4', green: '#107c10', teal: '#0ea5e9', orange: '#f59e0b', grid: 'rgba(0,0,0,0.06)', text: '#64748b' };
    }

    function hasSeriesData(arr) {
      if (!arr || !arr.length) return false;
      for (var i = 0; i < arr.length; i++) {
        if (Math.abs(Number(arr[i]) || 0) > 0.0005) return true;
      }
      return false;
    }

    function loadData() {
      if (!apiUrl) {
        showError('Dashboard API URL is missing.');
        return Promise.resolve();
      }
      setStatus('Loading…');
      showError('');
      var url = apiUrl + (apiUrl.indexOf('?') >= 0 ? '&' : '?') + queryParams();
      return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (r) {
          return r.text().then(function (text) {
            var d = null;
            try { d = text ? JSON.parse(text) : null; } catch (e) {
              throw new Error('Invalid JSON from server');
            }
            if (!r.ok) {
              throw new Error((d && d.error) || ('Request failed (' + r.status + ')'));
            }
            return d;
          });
        })
        .then(function (d) {
          if (!d || d.success === false) {
            throw new Error((d && d.error) || 'Dashboard API returned no data');
          }
          lastPayload = d;
          if (!chartReady()) {
            showError('Chart library failed to load. KPIs and tables will still update.', true);
          }
          renderAll(d);
          if (d.warnings && d.warnings.length) {
            showError(d.warnings.join(' '), true);
          }
          setStatus('Updated ' + (d.generated_at || ''));
        })
        .catch(function (e) {
          showError(e.message || 'Failed to load dashboard');
          setStatus('');
        });
    }

    function renderKpis(kpis) {
      var grid = document.getElementById('dbsKpiGrid');
      if (!grid) return;
      grid.innerHTML = '';
      if (!kpis || !kpis.length) {
        grid.innerHTML = '<div class="dbs-kpi glass"><div class="dbs-kpi__label">No KPI data</div><div class="dbs-kpi__value">0</div></div>';
        return;
      }
      kpis.forEach(function (k) {
        var card = document.createElement('div');
        card.className = 'dbs-kpi glass dbs-kpi--clickable';
        card.setAttribute('data-kpi-id', k.id || '');
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');
        card.setAttribute('title', 'Click for details');
        var iconCls = k.id && (k.id.indexOf('profit') >= 0 || k.id.indexOf('margin') >= 0 || k.id.indexOf('net') >= 0)
          ? 'dbs-kpi__icon dbs-kpi__icon--green' : 'dbs-kpi__icon';
        card.innerHTML =
          '<div class="' + iconCls + '"><i class="bi ' + (k.icon || 'bi-graph-up') + '"></i></div>' +
          '<div class="dbs-kpi__label">' + (k.label || '') + '</div>' +
          '<div class="dbs-kpi__value">' + fmt(k.value, k.format) + '</div>';
        grid.appendChild(card);
      });
    }

    function renderTxTable(rows) {
      var tb = document.querySelector('#dbsTxTable tbody');
      if (!tb) return;
      tb.innerHTML = '';
      (rows || []).forEach(function (r) {
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + r.transaction + '</td>' +
          '<td>' + (r.count || 0) + '</td>' +
          '<td>' + fmt(r.amount) + '</td>' +
          '<td>' + (r.percentage || 0) + '%</td>';
        tb.appendChild(tr);
      });
    }

    function renderFinancial(f) {
      var el = document.getElementById('dbsFinancial');
      if (!el || !f) return;
      el.innerHTML =
        '<div class="dbs-fin-row"><span>Sales</span><span>' + fmt(f.sales) + '</span></div>' +
        '<div class="dbs-fin-row"><span>Sales Return</span><span>- ' + fmt(f.sales_return) + '</span></div>' +
        '<div class="dbs-fin-row dbs-fin-row--total"><span>= Net Sales</span><span>' + fmt(f.net_sales) + '</span></div>' +
        '<div class="dbs-fin-row"><span>Purchases</span><span>' + fmt(f.purchases) + '</span></div>' +
        '<div class="dbs-fin-row"><span>Purchase Return</span><span>- ' + fmt(f.purchase_return) + '</span></div>' +
        '<div class="dbs-fin-row dbs-fin-row--total"><span>= Net Purchases</span><span>' + fmt(f.net_purchases) + '</span></div>' +
        '<div class="dbs-fin-row"><span>Cost of Goods Sold</span><span>- ' + fmt(f.cogs) + '</span></div>' +
        '<div class="dbs-fin-row dbs-fin-row--total"><span>= Gross Profit</span><span>' + fmt(f.gross_profit) + '</span></div>' +
        '<div class="dbs-fin-row"><span>Gross Profit %</span><span>' + fmt(f.gross_profit_pct, 'percent') + '</span></div>' +
        '<div class="dbs-fin-row"><span>Net Profit</span><span>' + fmt(f.net_profit) + '</span></div>' +
        '<div class="dbs-fin-row"><span>Expense Total</span><span>' + fmt(f.expense_total) + '</span></div>';
    }

    function renderInventory(inv) {
      var el = document.getElementById('dbsInventory');
      if (!el || !inv) return;
      var tiles = [
        ['Total Items', inv.total_items, 'number'],
        ['Active Items', inv.active_items, 'number'],
        ['Out of Stock', inv.out_of_stock, 'number'],
        ['Low Stock', inv.low_stock, 'number'],
        ['Negative Stock', inv.negative_stock, 'number'],
        ['Dead Stock', inv.dead_stock, 'number'],
      ];
      el.innerHTML = tiles.map(function (t) {
        return '<div class="dbs-inv-tile"><span>' + t[0] + '</span><strong>' + fmt(t[1], t[2]) + '</strong></div>';
      }).join('');
    }

    function barChart(id, labels, datasets, horizontal) {
      destroyChart(id);
      var c = document.getElementById(id);
      if (!c || !chartReady()) { setChartEmpty(id, true); return; }
      var values = (datasets[0] && datasets[0].data) || [];
      if (!hasSeriesData(values) && !(datasets[1] && hasSeriesData(datasets[1].data))) {
        setChartEmpty(id, true);
        return;
      }
      setChartEmpty(id, false);
      var pal = colors();
      charts[id] = new Chart(c, {
        type: 'bar',
        data: { labels: labels && labels.length ? labels : ['—'], datasets: datasets },
        options: {
          indexAxis: horizontal ? 'y' : 'x',
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: datasets.length > 1 } },
          scales: {
            x: { grid: { color: pal.grid }, ticks: { color: pal.text } },
            y: { grid: { color: pal.grid }, ticks: { color: pal.text } },
          },
        },
      });
    }

    function lineChart(id, labels, datasets) {
      destroyChart(id);
      var c = document.getElementById(id);
      if (!c || !chartReady()) { setChartEmpty(id, true); return; }
      var hasData = false;
      (datasets || []).forEach(function (ds) { if (hasSeriesData(ds.data)) hasData = true; });
      if (!hasData) { setChartEmpty(id, true); return; }
      setChartEmpty(id, false);
      var pal = colors();
      charts[id] = new Chart(c, {
        type: 'line',
        data: { labels: labels && labels.length ? labels : ['—'], datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: {
            x: { grid: { color: pal.grid }, ticks: { color: pal.text, maxRotation: 45 } },
            y: { grid: { color: pal.grid }, ticks: { color: pal.text }, beginAtZero: true },
          },
        },
      });
    }

    function doughnutChart(id, labels, values) {
      destroyChart(id);
      var c = document.getElementById(id);
      if (!c || !chartReady()) { setChartEmpty(id, true); return; }
      if (!hasSeriesData(values)) { setChartEmpty(id, true); return; }
      setChartEmpty(id, false);
      charts[id] = new Chart(c, {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{ data: values, backgroundColor: ['#0078d4', '#107c10', '#f59e0b', '#8b5cf6', '#64748b'] }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } },
      });
    }

    function entityLabel(r) {
      return String((r && (r.name || r.code)) || 'Unknown').slice(0, 24);
    }

    function entityChart(id, rows, horizontal) {
      rows = rows || [];
      barChart(id,
        rows.map(entityLabel),
        [{ label: 'Amount', data: rows.map(function (r) { return r.amount; }), backgroundColor: '#0078d4' }],
        horizontal !== false);
    }

    function renderCharts(ch) {
      if (!ch) return;
      var pal = colors();
      var svp = ch.sales_vs_purchase_trend || {};
      lineChart('dbsChartSalesPurchase', svp.labels || [], [
        { label: 'Sales', data: svp.sales || [], borderColor: pal.blue, backgroundColor: 'rgba(0,120,212,0.08)', tension: 0.3 },
        { label: 'Purchase', data: svp.purchase || [], borderColor: pal.green, backgroundColor: 'rgba(16,124,16,0.08)', tension: 0.3 },
      ]);
      var svgp = ch.sales_vs_gross_profit || {};
      barChart('dbsChartSalesProfit', svgp.labels || ['Net Sales', 'Gross Profit'], [
        { label: 'Amount', data: svgp.values || [0, 0], backgroundColor: [pal.blue, pal.green] },
      ], false);
      var daily = ch.daily_sales_trend || [];
      lineChart('dbsChartDailySales', daily.map(function (d) { return d.date; }), [
        { label: 'Sales', data: daily.map(function (d) { return d.amount; }), borderColor: pal.teal, fill: true, backgroundColor: 'rgba(14,165,233,0.12)', tension: 0.3 },
      ]);
      entityChart('dbsChartCategory', ch.category_sales, true);
      entityChart('dbsChartBrand', ch.brand_sales, true);
      entityChart('dbsChartTopItems', ch.top_items, true);
      entityChart('dbsChartTopCustomers', ch.top_customers, true);
      entityChart('dbsChartTopSuppliers', ch.top_suppliers, true);
      var pm = ch.payment_methods || [];
      doughnutChart('dbsChartPayment', pm.map(function (p) { return p.label; }), pm.map(function (p) { return p.amount; }));
      var sm = ch.stock_movement || {};
      barChart('dbsChartStock', sm.labels || ['GRN In', 'Goods Issue', 'Adjustment'], [
        { label: 'In', data: sm.in || [0, 0, 0], backgroundColor: pal.green },
        { label: 'Out', data: sm.out || [0, 0, 0], backgroundColor: pal.orange },
      ], false);
    }

    function renderAll(d) {
      renderKpis(d.kpis);
      renderCharts(d.charts);
      renderTxTable(d.transaction_summary);
      renderFinancial(d.financial);
      renderInventory(d.inventory);
    }

    var form = document.getElementById('dbsFilterForm');
    if (form) form.addEventListener('submit', function (e) { e.preventDefault(); loadData(); });
    var btn = document.getElementById('dbsRefresh');
    if (btn) btn.addEventListener('click', loadData);

    var kpiGrid = document.getElementById('dbsKpiGrid');
    if (kpiGrid) {
      kpiGrid.addEventListener('click', function (e) {
        var card = e.target.closest('[data-kpi-id]');
        if (!card) return;
        drillKpi(card.getAttribute('data-kpi-id'));
      });
      kpiGrid.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var card = e.target.closest('[data-kpi-id]');
        if (!card) return;
        e.preventDefault();
        drillKpi(card.getAttribute('data-kpi-id'));
      });
    }

    loadData();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
