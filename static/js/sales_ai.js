(function () {
  'use strict';

  var app = document.getElementById('salesAiApp');
  if (!app) return;

  var apiUrl = app.getAttribute('data-api') || '';
  var narrativeUrl = app.getAttribute('data-narrative') || '';
  var charts = {};
  var payload = null;
  var productRows = [];

  function fmtCurrency(n) {
    var v = Number(n) || 0;
    try {
      return v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
    } catch (e) {
      return String(Math.round(v));
    }
  }

  function fmtVal(kpi) {
    var v = Number(kpi.value) || 0;
    if (kpi.format === 'percent') return v.toFixed(1) + (kpi.suffix || '%');
    if (kpi.format === 'number') return Math.round(v).toLocaleString();
    return fmtCurrency(v);
  }

  function trendIcon(t) {
    if (t === 'up') return '▲';
    if (t === 'down') return '▼';
    return '●';
  }

  function setStatus(msg) {
    var el = document.getElementById('saiStatus');
    if (el) el.textContent = msg || '';
  }

  function showError(msg) {
    var el = document.getElementById('saiError');
    if (!el) return;
    el.textContent = msg;
    el.classList.toggle('hidden', !msg);
  }

  function destroyChart(id) {
    if (charts[id]) {
      charts[id].destroy();
      delete charts[id];
    }
  }

  function chartColors() {
    var dark = app.classList.contains('sai-dark');
    return {
      text: dark ? '#c8c6c4' : '#605e5c',
      grid: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
      primary: '#0078d4',
      green: '#107c10',
      orange: '#ca5010',
    };
  }

  function queryParams() {
    var form = document.getElementById('saiFilterForm');
    if (!form) return '';
    var fd = new FormData(form);
    var p = new URLSearchParams();
    fd.forEach(function (v, k) {
      if (v) p.set(k, v);
    });
    return p.toString();
  }

  function loadData() {
    setStatus('Loading…');
    showError('');
    var url = apiUrl + (apiUrl.indexOf('?') >= 0 ? '&' : '?') + queryParams();
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.success && d.error) throw new Error(d.error);
        payload = d;
        renderAll(d);
        setStatus('Updated ' + (d.generated_at || ''));
      })
      .catch(function (e) {
        showError(e.message || 'Failed to load dashboard');
        setStatus('');
      });
  }

  function renderKpis(kpis) {
    var grid = document.getElementById('saiKpiGrid');
    if (!grid) return;
    grid.innerHTML = '';
    (kpis || []).forEach(function (k, i) {
      var card = document.createElement('div');
      card.className = 'sai-kpi glass';
      card.style.animationDelay = (i * 0.03) + 's';
      var targetPct = Math.min(100, Number(k.target_pct) || 0);
      var sparkId = 'spark_' + k.id;
      card.innerHTML =
        '<div class="sai-kpi__label">' + k.label + '</div>' +
        '<div class="sai-kpi__value">' + fmtVal(k) + '</div>' +
        '<div class="sai-kpi__meta">' +
          '<span class="sai-kpi__trend sai-kpi__trend--' + (k.trend || 'flat') + '">' +
            trendIcon(k.trend) + ' ' + (k.change_pct || 0) + '%</span>' +
          '<span>Target ' + targetPct + '%</span></div>' +
        '<div class="sai-kpi__target"><div class="sai-kpi__target-fill" style="width:' + targetPct + '%"></div></div>' +
        '<canvas class="sai-kpi__spark" id="' + sparkId + '" height="28"></canvas>';
      grid.appendChild(card);
      var ctx = document.getElementById(sparkId);
      if (ctx && k.sparkline && k.sparkline.length) {
        destroyChart(sparkId);
        var c = chartColors();
        charts[sparkId] = new Chart(ctx, {
          type: 'line',
          data: {
            labels: k.sparkline.map(function (_, idx) { return idx; }),
            datasets: [{ data: k.sparkline, borderColor: c.primary, borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0.35 }],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { display: false }, y: { display: false } },
          },
        });
            }
        });
    }

  function renderGamify(g) {
    if (!g) return;
    var bar = document.getElementById('saiDailyBar');
    if (bar) bar.style.width = Math.min(100, g.daily_progress_pct || 0) + '%';
    var msg = document.getElementById('saiGapMsg');
    if (msg) msg.textContent = g.gap_message || '';
    var streak = document.getElementById('saiStreak');
    if (streak) streak.textContent = '🔥 Streak: ' + (g.streak_days || 0) + ' days';
    var rank = document.getElementById('saiRank');
    if (rank) rank.textContent = 'Rank #' + (g.personal_rank || '—');
    var rewards = document.getElementById('saiRewards');
    if (rewards) rewards.textContent = 'Rewards ' + (g.monthly_rewards_progress || 0) + '%';
    var cel = document.getElementById('saiCelebrate');
    if (cel && g.celebrate) {
      cel.classList.remove('hidden');
      setTimeout(function () { cel.classList.add('hidden'); }, 3000);
    }
  }

  function renderComparison(key) {
    if (!payload || !payload.comparisons) return;
    var comp = payload.comparisons[key];
    if (!comp) return;
    var ctx = document.getElementById('saiCompChart');
    if (!ctx) return;
    destroyChart('saiCompChart');
    var c = chartColors();
    var cur = comp.current_series || [];
    var prev = comp.previous_series || [];
    charts.saiCompChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: cur.map(function (x) { return (x.date || '').slice(5); }),
        datasets: [
          { label: 'Current', data: cur.map(function (x) { return x.amount; }), borderColor: c.primary, backgroundColor: 'rgba(0,120,212,0.15)', fill: true, tension: 0.35 },
          { label: 'Previous', data: prev.map(function (x) { return x.amount; }), borderColor: c.orange, borderDash: [4, 4], tension: 0.35 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: c.text } } },
        scales: {
          x: { ticks: { color: c.text }, grid: { color: c.grid } },
          y: { ticks: { color: c.text }, grid: { color: c.grid } },
        },
      },
    });
  }

  function renderHeatmap() {
    if (!payload || !payload.kpis) return;
    var ctx = document.getElementById('saiHeatChart');
    if (!ctx) return;
    destroyChart('saiHeatChart');
    var c = chartColors();
    var labels = payload.kpis.slice(0, 8).map(function (k) { return k.label.split(' ')[0]; });
    var vals = payload.kpis.slice(0, 8).map(function (k) { return Math.abs(k.change_pct || 0); });
    charts.saiHeatChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ label: 'Change %', data: vals, backgroundColor: vals.map(function (v) {
          return v >= 15 ? c.green : v >= 5 ? c.primary : c.orange;
        }) }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: c.text }, grid: { color: c.grid } }, y: { ticks: { color: c.text }, grid: { display: false } } },
      },
    });
  }

  function renderForecast(fc) {
    if (!fc) return;
    var box = document.getElementById('saiForecastKpis');
    if (box) {
      box.innerHTML = [
        ['Tomorrow', fc.tomorrow],
        ['Next Week', fc.next_week],
        ['Next Month', fc.next_month],
        ['Revenue', fc.expected_revenue],
        ['Profit', fc.expected_profit],
        ['Confidence', (fc.confidence_pct || 0) + '%'],
      ].map(function (x) {
        return '<div class="sai-forecast-kpi"><strong>' + fmtCurrency(x[1]) + '</strong><span>' + x[0] + '</span></div>';
      }).join('');
    }
    var ctx = document.getElementById('saiForecastChart');
    if (!ctx) return;
    destroyChart('saiForecastChart');
    var c = chartColors();
    var series = fc.trend_series || [];
    charts.saiForecastChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: series.map(function (x) { return 'D' + x.day; }),
        datasets: [
          { label: 'Forecast', data: series.map(function (x) { return x.forecast; }), borderColor: c.primary, tension: 0.35 },
          { label: 'Upper', data: series.map(function (x) { return x.high; }), borderColor: 'rgba(16,124,16,0.5)', borderDash: [2, 2], fill: false },
          { label: 'Lower', data: series.map(function (x) { return x.low; }), borderColor: 'rgba(209,52,56,0.4)', borderDash: [2, 2], fill: '-1' },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: c.text } } },
        scales: { x: { ticks: { color: c.text }, grid: { color: c.grid } }, y: { ticks: { color: c.text }, grid: { color: c.grid } } },
      },
    });
  }

  function renderAlerts(alerts) {
    var ul = document.getElementById('saiAlerts');
    if (!ul) return;
    ul.innerHTML = (alerts || []).map(function (a) {
      return '<li class="' + (a.level || '') + '">' + (a.icon || '') + ' ' + a.text + '</li>';
    }).join('') || '<li>No alerts — all clear.</li>';
  }

  function barChart(id, labels, data, label) {
    var ctx = document.getElementById(id);
    if (!ctx) return;
    destroyChart(id);
    var c = chartColors();
    charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ label: label || 'Amount', data: data, backgroundColor: c.primary }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: c.text, maxRotation: 45 }, grid: { display: false } }, y: { ticks: { color: c.text }, grid: { color: c.grid } } },
      },
    });
  }

  function groupedBar(id, rows) {
    var ctx = document.getElementById(id);
    if (!ctx || !rows) return;
    destroyChart(id);
    var c = chartColors();
    charts[id] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: rows.map(function (r) { return (r.label || r.key || '').slice(0, 12); }),
        datasets: [
          { label: 'Current', data: rows.map(function (r) { return r.current; }), backgroundColor: c.primary },
          { label: 'Previous', data: rows.map(function (r) { return r.previous; }), backgroundColor: c.orange },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: c.text } } },
        scales: { x: { ticks: { color: c.text }, grid: { display: false } }, y: { ticks: { color: c.text }, grid: { color: c.grid } } },
      },
    });
  }

  function renderCategories(cats) {
    var grid = document.getElementById('saiCategoryGrid');
    if (!grid) return;
    grid.innerHTML = (cats || []).map(function (cat) {
      var pct = Math.min(100, cat.target_achievement || 0);
      return '<div class="sai-cat-card">' +
        '<strong>' + cat.name + '</strong>' +
        '<div class="sai-ring" style="--pct:' + pct + '%">' + pct + '%</div>' +
        '<div>Sales ' + fmtCurrency(cat.sales) + '</div>' +
        '<div>Profit ' + fmtCurrency(cat.profit) + ' · Growth ' + (cat.growth_pct || 0) + '%</div>' +
        '</div>';
    }).join('');
  }

  function renderBrands(brands) {
    if (!brands) return;
    var top = brands.top_10 || [];
    barChart('saiBrandBarChart', top.map(function (b) { return (b.name || '').slice(0, 10); }), top.map(function (b) { return b.sales; }), 'Sales');
    var ctx = document.getElementById('saiBrandDonutChart');
    if (ctx) {
      destroyChart('saiBrandDonutChart');
      var c = chartColors();
      charts.saiBrandDonutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: top.map(function (b) { return b.name; }),
          datasets: [{ data: top.map(function (b) { return b.sales; }), backgroundColor: ['#0078d4', '#107c10', '#ca5010', '#8764b8', '#ffb900', '#00b7c3', '#498205', '#d13438', '#a19f9d', '#005a9e'] }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: c.text, boxWidth: 10 } } } },
      });
    }
    var ins = document.getElementById('saiBrandInsights');
    if (ins) {
      var fg = brands.fastest_growing;
      var sm = brands.slow_moving;
      var hp = brands.highest_profit;
      ins.innerHTML =
        '<p><strong>Fastest growing:</strong> ' + (fg ? fg.name + ' (' + (fg.difference_percent || 0) + '%)' : '—') + '</p>' +
        '<p><strong>Slow moving:</strong> ' + (sm ? sm.name : '—') + '</p>' +
        '<p><strong>Top brand:</strong> ' + (hp ? hp.name : '—') + '</p>';
    }
  }

  function renderProducts(rows) {
    productRows = rows || [];
    filterProducts();
  }

  function filterProducts() {
    var q = (document.getElementById('saiProductSearch') || {}).value || '';
    q = q.toLowerCase();
    var tbody = document.querySelector('#saiProductTable tbody');
    if (!tbody) return;
    var filtered = productRows.filter(function (r) {
      if (!q) return true;
      return (r.name + r.category + r.brand + r.item_code).toLowerCase().indexOf(q) >= 0;
    });
    tbody.innerHTML = filtered.map(function (r) {
      var initials = (r.name || '?').slice(0, 2).toUpperCase();
      return '<tr>' +
        '<td>' + r.rank + '</td>' +
        '<td><div class="sai-product-img">' + initials + '</div></td>' +
        '<td>' + r.name + '</td>' +
        '<td>' + r.category + '</td>' +
        '<td>' + r.brand + '</td>' +
        '<td>' + r.qty + '</td>' +
        '<td>' + fmtCurrency(r.sales) + '</td>' +
        '<td>' + fmtCurrency(r.profit) + '</td>' +
        '<td>' + r.margin_pct + '%</td>' +
        '<td>' + r.growth_pct + '%</td></tr>';
    }).join('');
  }

  function renderLeaderboard(rows) {
    var box = document.getElementById('saiLeaderboard');
    if (!box) return;
    var medals = ['🥇', '🥈', '🥉'];
    box.innerHTML = (rows || []).map(function (r, i) {
      return '<div class="sai-leader-row ' + (r.medal || '') + '">' +
        '<div class="sai-leader-rank">' + (medals[i] || r.rank) + '</div>' +
        '<div><strong>' + r.name + '</strong><br><small>' + r.badge + '</small></div>' +
        '<div>Sales<br><strong>' + fmtCurrency(r.sales) + '</strong></div>' +
        '<div>Target<br><strong>' + r.target_achievement + '%</strong></div>' +
        '<div>Bonus<br><strong>' + r.bonus_progress + '%</strong></div>' +
        '<div>Win rate<br><strong>' + r.win_rate + '%</strong></div></div>';
    }).join('');
  }

  function renderCustomers(cust) {
    if (!cust) return;
    var list = document.getElementById('saiTopCustomers');
    if (list) {
      list.innerHTML = (cust.top_customers || []).map(function (c) {
        return '<li><span>' + (c.name || c.code) + '</span><span>' + fmtCurrency(c.sales) + '</span></li>';
      }).join('');
    }
    var kpis = document.getElementById('saiCustomerKpis');
    if (kpis) {
      kpis.innerHTML =
        '<div class="sai-mini-kpi"><span>New customers</span><strong>' + (cust.new_customers || 0) + '</strong></div>' +
        '<div class="sai-mini-kpi"><span>Repeat customers</span><strong>' + (cust.repeat_customers || 0) + '</strong></div>' +
        '<div class="sai-mini-kpi"><span>Avg purchase</span><strong>' + fmtCurrency(cust.avg_purchase) + '</strong></div>' +
        '<div class="sai-mini-kpi"><span>CLV (est.)</span><strong>' + fmtCurrency(cust.clv) + '</strong></div>';
    }
    var ctx = document.getElementById('saiSegmentChart');
    if (ctx) {
      destroyChart('saiSegmentChart');
      var c = chartColors();
      var segs = cust.segments || [];
      charts.saiSegmentChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: segs.map(function (s) { return s.label; }),
          datasets: [{ data: segs.map(function (s) { return s.value; }), backgroundColor: ['#0078d4', '#107c10', '#ffb900', '#d13438'] }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: c.text } } } },
      });
    }
  }

  function renderGeo(geo) {
    var map = document.getElementById('saiGeoMap');
    if (!map || !geo) return;
    var cities = geo.cities || [];
    var max = Math.max.apply(null, cities.map(function (x) { return x.sales || 0; }).concat([1]));
    map.innerHTML = cities.map(function (cell) {
      var intensity = Math.round((cell.sales / max) * 100);
      var hue = 210 - Math.round(intensity * 0.8);
      return '<div class="sai-geo-cell" style="background:hsl(' + hue + ',70%,' + (35 + intensity * 0.25) + '%)">' +
        '<div>' + (cell.city || '—') + '</div><strong>' + fmtCurrency(cell.sales) + '</strong></div>';
    }).join('') || '<p>No geographic data</p>';
  }

  function renderTrend(series) {
    var ctx = document.getElementById('saiTrendChart');
    if (!ctx) return;
    destroyChart('saiTrendChart');
    var c = chartColors();
    charts.saiTrendChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: (series || []).map(function (x) { return (x.date || '').slice(5); }),
        datasets: [{ label: 'Sales', data: (series || []).map(function (x) { return x.amount || x.qty; }), borderColor: c.green, backgroundColor: 'rgba(16,124,16,0.12)', fill: true, tension: 0.35 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: c.text }, grid: { color: c.grid } }, y: { ticks: { color: c.text }, grid: { color: c.grid } } },
      },
    });
  }

  function renderTimeAnalysis(ta, key) {
    key = key || 'hour';
    var ctx = document.getElementById('saiTimeChart');
    if (!ctx || !ta) return;
    destroyChart('saiTimeChart');
    var c = chartColors();
    var rows = ta[key] || [];
    charts.saiTimeChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: rows.map(function (x) { return x.label; }),
        datasets: [{ label: 'Sales', data: rows.map(function (x) { return x.amount; }), backgroundColor: c.primary }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: c.text }, grid: { display: false } }, y: { ticks: { color: c.text }, grid: { color: c.grid } } },
      },
    });
  }

  function renderMovement(pm) {
    var box = document.getElementById('saiMovement');
    if (!box || !pm) return;
    box.innerHTML =
      '<p><strong>Fast moving:</strong> ' + (pm.fast_moving || []).slice(0, 3).map(function (x) { return x.itemname; }).join(', ') + '</p>' +
      '<p><strong>Slow moving:</strong> ' + (pm.slow_moving || []).slice(0, 3).map(function (x) { return x.itemname; }).join(', ') + '</p>' +
      '<p><strong>Low stock alerts:</strong> ' + (pm.low_stock || []).length + '</p>' +
      '<p><strong>Stock turnover:</strong> ' + (pm.stock_turnover || 0) + '</p>';
  }

  function renderAiInsights(tips, widgets) {
    var ul = document.getElementById('saiAiInsights');
    if (ul) ul.innerHTML = (tips || []).map(function (t) { return '<li>' + t + '</li>'; }).join('');
    var w = document.getElementById('saiAiWidgets');
    if (w && widgets) {
      w.innerHTML =
        '<p><strong>Best time to sell:</strong> ' + widgets.best_time_to_sell + '</p>' +
        '<p><strong>Likely stockout:</strong> ' + (widgets.likely_stockout || []).join(', ') + '</p>' +
        '<p><strong>Reorder soon:</strong> ' + (widgets.likely_reorder_customers || []).join(', ') + '</p>' +
        '<p><strong>Upsell:</strong> ' + (widgets.upsell_products || []).join(', ') + '</p>' +
        '<p><strong>Forecast accuracy:</strong> ' + widgets.forecast_accuracy_score + '%</p>' +
        '<p><em>' + (widgets.daily_action_plan || '') + '</em></p>';
    }
  }

  function renderAll(d) {
    renderKpis(d.kpis);
    renderGamify(d.gamification);
    renderComparison('today_vs_yesterday');
    renderHeatmap();
    renderForecast(d.forecast);
    renderAlerts(d.alerts);
    barChart('saiBranchChart', (d.comparisons.branch || []).map(function (b) { return (b.label || '').slice(0, 8); }), (d.comparisons.branch || []).map(function (b) { return b.current; }), 'Branch');
    groupedBar('saiSalesmanChart', d.comparisons.salesperson || []);
    groupedBar('saiCatBrandChart', d.comparisons.category || []);
    renderCategories(d.categories);
    renderBrands(d.brands);
    renderProducts(d.top_products);
    renderLeaderboard(d.leaderboard);
    renderCustomers(d.customers);
    renderGeo(d.geo);
    renderTrend(d.sales_trend);
    renderTimeAnalysis(d.time_analysis, 'hour');
    renderMovement(d.product_movement);
    renderAiInsights(d.ai_insights, d.ai_widgets);
  }

  document.getElementById('saiCompTabs') && document.getElementById('saiCompTabs').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-comp]');
    if (!btn) return;
    document.querySelectorAll('#saiCompTabs button').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    renderComparison(btn.getAttribute('data-comp'));
  });

  document.getElementById('saiTimeTabs') && document.getElementById('saiTimeTabs').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-time]');
    if (!btn || !payload) return;
    document.querySelectorAll('#saiTimeTabs button').forEach(function (b) { b.classList.remove('active'); });
    btn.classList.add('active');
    renderTimeAnalysis(payload.time_analysis, btn.getAttribute('data-time'));
  });

  document.getElementById('saiFilterForm') && document.getElementById('saiFilterForm').addEventListener('submit', function (e) {
                e.preventDefault();
    loadData();
  });

  document.getElementById('saiRefresh') && document.getElementById('saiRefresh').addEventListener('click', loadData);

  document.getElementById('saiProductSearch') && document.getElementById('saiProductSearch').addEventListener('input', filterProducts);

  document.getElementById('saiThemeToggle') && document.getElementById('saiThemeToggle').addEventListener('click', function () {
    app.classList.toggle('sai-dark');
    if (payload) renderAll(payload);
  });

  document.getElementById('saiAiPlan') && document.getElementById('saiAiPlan').addEventListener('click', function () {
    if (!narrativeUrl) return;
    var box = document.getElementById('saiNarrative');
    if (box) box.textContent = 'Generating AI plan…';
    fetch(narrativeUrl + '?' + queryParams(), { method: 'POST', credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (box) box.textContent = d.narrative || d.error || 'No response';
      })
      .catch(function () {
        if (box) box.textContent = 'Failed to generate plan.';
      });
  });

  document.querySelectorAll('#saiProductTable th[data-sort]').forEach(function (th) {
    th.addEventListener('click', function () {
      var key = th.getAttribute('data-sort');
      productRows.sort(function (a, b) {
        return (Number(b[key]) || 0) - (Number(a[key]) || 0);
      });
      filterProducts();
    });
  });

  loadData();
})();
