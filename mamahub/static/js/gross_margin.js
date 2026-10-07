(function () {
  const app = document.getElementById("grossMarginApp");
  if (!app) return;

  const apiUrl = app.dataset.api || "";
  const drillUrl = app.dataset.drill || "";
  const exportExcel = app.dataset.exportExcel || "";
  const exportPdf = app.dataset.exportPdf || "";

  const form = document.getElementById("gmaFilterForm");
  const kpiGrid = document.getElementById("gmaKpiGrid");
  const gridBody = document.getElementById("gmaGridBody");
  const summaryTabs = document.getElementById("gmaSummaryTabs");
  const summaryBody = document.getElementById("gmaSummaryBody");
  const insightsEl = document.getElementById("gmaInsights");
  const errEl = document.getElementById("gmaError");
  const statusEl = document.getElementById("gmaStatus");
  const drillModal = document.getElementById("gmaDrillModal");
  const drillBody = document.getElementById("gmaDrillBody");
  const drillTitle = document.getElementById("gmaDrillTitle");
  const advancedHost = document.getElementById("gmaAdvancedHost");

  if (drillModal && drillModal.parentElement !== document.body) {
    document.body.appendChild(drillModal);
  }

  let lastPayload = null;
  let activeView = "grid";
  let activeSummary = "item";
  const chartInstances = {};

  const SUMMARY_KEYS = [
    { id: "item", label: "Item" },
    { id: "category", label: "Category" },
    { id: "brand", label: "Brand" },
    { id: "customer", label: "Customer" },
    { id: "salesman", label: "Salesman" },
    { id: "branch", label: "Branch" },
    { id: "invoice", label: "Invoice" },
  ];

  const fmt = (n, d) => {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString(undefined, { maximumFractionDigits: d != null ? d : 2 });
  };

  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };

  const badge = (cls, text) =>
    `<span class="gma-badge ${esc(cls || "")}">${esc(text || "")}</span>`;

  function queryParams() {
    return new URLSearchParams(new FormData(form));
  }

  function syncExportLinks() {
    const q = queryParams().toString();
    const ex = document.getElementById("gmaBtnExcel");
    const pdf = document.getElementById("gmaBtnPdf");
    if (ex && exportExcel) ex.href = exportExcel + (q ? "?" + q : "");
    if (pdf && exportPdf) pdf.href = exportPdf + (q ? "?" + q : "");
  }

  function showError(msg) {
    if (!errEl) return;
    if (!msg) {
      errEl.classList.add("hidden");
      errEl.textContent = "";
      return;
    }
    errEl.textContent = msg;
    errEl.classList.remove("hidden");
  }

  function setView(view) {
    activeView = view;
    document.querySelectorAll("#gmaViewTabs .gma-tab").forEach((t) => {
      t.classList.toggle("gma-tab--active", t.dataset.view === view);
    });
    ["grid", "summary", "charts", "advanced"].forEach((v) => {
      const el = document.getElementById("gmaView" + v.charAt(0).toUpperCase() + v.slice(1));
      if (!el) return;
      const on = v === view;
      el.classList.toggle("hidden", !on);
      el.classList.toggle("gma-view--active", on);
    });
    if (view === "charts") window.setTimeout(resizeCharts, 100);
  }

  document.getElementById("gmaViewTabs")?.addEventListener("click", (e) => {
    const tab = e.target.closest(".gma-tab");
    if (tab?.dataset.view) setView(tab.dataset.view);
  });

  function openModal(title, html) {
    if (!drillModal) return;
    drillTitle.textContent = title;
    drillBody.innerHTML = html;
    drillModal.classList.remove("hidden");
    document.body.classList.add("gma-modal-open");
    document.body.appendChild(drillModal);
  }

  function closeModal() {
    if (!drillModal) return;
    drillModal.classList.add("hidden");
    document.body.classList.remove("gma-modal-open");
  }

  drillModal?.addEventListener("click", (e) => {
    if (e.target.classList.contains("gma-modal__backdrop") || e.target.closest("[data-close='gmaDrillModal']")) {
      closeModal();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drillModal && !drillModal.classList.contains("hidden")) closeModal();
  });

  function renderKpis(kpis) {
    if (!kpiGrid || !kpis) return;
    kpiGrid.querySelectorAll("[data-kpi]").forEach((el) => {
      const key = el.dataset.kpi;
      const vEl = el.querySelector(".gma-kpi__val");
      if (!vEl) return;
      if (key === "highest_margin_item" || key === "lowest_margin_item") {
        const o = kpis[key];
        if (!o) vEl.textContent = "—";
        else vEl.textContent = `${o.item_code || ""} ${o.item_name || ""} (${o.margin_pct != null ? o.margin_pct + "%" : "—"})`;
      } else if (key === "top_customer_by_profit") {
        const o = kpis.top_customer_by_profit;
        if (!o) vEl.textContent = "—";
        else vEl.textContent = `${o.customer_name || o.customer_code || ""} — ${fmt(o.profit, 0)}`;
      } else if (key === "margin_pct") {
        vEl.textContent = kpis.margin_pct != null ? kpis.margin_pct + "%" : "—";
      } else {
        vEl.textContent = fmt(kpis[key], key.includes("items") ? 0 : 2);
      }
    });
  }

  function renderInsights(list) {
    if (!insightsEl) return;
    if (!list?.length) {
      insightsEl.innerHTML = "<p class='gma-loading'>No insights.</p>";
      return;
    }
    insightsEl.innerHTML = list
      .map((i) => {
        const sev = (i.severity || "info").toLowerCase();
        const cls = sev === "high" ? "gma-insight--high" : sev === "medium" ? "gma-insight--medium" : "gma-insight--info";
        return `<div class="gma-insight ${cls}"><strong>${esc(i.title)}</strong>${esc(i.message)}</div>`;
      })
      .join("");
  }

  function renderGrid(rows) {
    if (!gridBody) return;
    if (!rows?.length) {
      gridBody.innerHTML = '<tr><td colspan="14" class="gma-loading">No rows for selected filters.</td></tr>';
      return;
    }
    const max = 2500;
    const slice = rows.slice(0, max);
    gridBody.innerHTML = slice
      .map((r) => {
        const ic = r.item_code || "";
        return `<tr class="gma-row-click" data-item-raw="${encodeURIComponent(ic)}">
          <td>${esc(r.invoice_no)}</td>
          <td>${esc(r.invoice_date)}</td>
          <td>${esc(r.customer)}</td>
          <td>${esc(r.salesman)}</td>
          <td>${esc(ic)}</td>
          <td>${esc(r.item_name)}</td>
          <td class="num">${fmt(r.qty, 3)}</td>
          <td class="num">${fmt(r.sales_rate, 4)}</td>
          <td class="num">${fmt(r.cost_rate, 4)}</td>
          <td class="num">${fmt(r.sales_amount)}</td>
          <td class="num">${fmt(r.cost_amount)}</td>
          <td class="num">${fmt(r.profit_amount)}</td>
          <td class="num">${r.margin_pct != null ? r.margin_pct + "%" : "—"}</td>
          <td>${badge(r.margin_class, r.status)}</td>
        </tr>`;
      })
      .join("");
    if (rows.length > max) {
      gridBody.innerHTML += `<tr><td colspan="14" class="gma-loading">Showing first ${max} of ${rows.length} lines. Export for full data.</td></tr>`;
    }
  }

  gridBody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-item-raw]");
    if (!tr) return;
    const ic = decodeURIComponent(tr.getAttribute("data-item-raw") || "");
    if (ic) loadDrilldown(ic);
  });

  function renderSummaryTabs() {
    if (!summaryTabs) return;
    summaryTabs.innerHTML = SUMMARY_KEYS.map(
      (s) =>
        `<button type="button" class="gma-tab ${s.id === activeSummary ? "gma-tab--active" : ""}" data-summary="${s.id}">${esc(s.label)}</button>`
    ).join("");
  }

  summaryTabs?.addEventListener("click", (e) => {
    const tab = e.target.closest("[data-summary]");
    if (!tab) return;
    activeSummary = tab.dataset.summary;
    renderSummaryTabs();
    renderSummaryTable();
  });

  function renderSummaryTable() {
    if (!summaryBody || !lastPayload) return;
    const rows = (lastPayload.summaries || {})[activeSummary] || [];
    if (!rows.length) {
      summaryBody.innerHTML = '<tr><td colspan="6" class="gma-loading">No data</td></tr>';
      return;
    }
    summaryBody.innerHTML = rows
      .slice(0, 500)
      .map(
        (r) => `<tr>
          <td>${esc(r.label || r.key)}</td>
          <td class="num">${fmt(r.sales_amount)}</td>
          <td class="num">${fmt(r.cost_amount)}</td>
          <td class="num">${fmt(r.profit_amount)}</td>
          <td class="num">${r.margin_pct != null ? r.margin_pct + "%" : "—"}</td>
          <td>${badge(r.margin_class, r.status)}</td>
        </tr>`
      )
      .join("");
  }

  function destroyCharts() {
    Object.keys(chartInstances).forEach((k) => {
      try {
        chartInstances[k].destroy();
      } catch (_) {}
      delete chartInstances[k];
    });
  }

  function makeChart(id, type, labels, datasets, opts) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    if (chartInstances[id]) {
      chartInstances[id].destroy();
      delete chartInstances[id];
    }
    chartInstances[id] = new Chart(canvas, {
      type: type,
      data: { labels, datasets },
      options: Object.assign(
        {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: type === "doughnut" } },
        },
        opts || {}
      ),
    });
  }

  function resizeCharts() {
    Object.values(chartInstances).forEach((c) => c.resize());
  }

  function renderCharts(charts) {
    if (!charts) return;
    destroyCharts();
    const tp = charts.top_profitable_items || {};
    makeChart(
      "gmaChartTopProfit",
      "bar",
      tp.labels || [],
      [{ label: "Profit", data: tp.profit || [], backgroundColor: "#198754" }],
      { indexAxis: "y" }
    );
    const tl = charts.top_loss_items || {};
    makeChart(
      "gmaChartTopLoss",
      "bar",
      tl.labels || [],
      [{ label: "Loss", data: tl.profit || [], backgroundColor: "#dc3545" }],
      { indexAxis: "y" }
    );
    const cat = charts.margin_by_category || {};
    makeChart("gmaChartCategory", "bar", cat.labels || [], [
      { label: "Margin %", data: cat.margin_pct || [], backgroundColor: "#0d6efd" },
    ]);
    const sm = charts.margin_by_salesman || {};
    makeChart("gmaChartSalesman", "bar", sm.labels || [], [
      { label: "Margin %", data: sm.margin_pct || [], backgroundColor: "#6f42c1" },
    ]);
    const tr = charts.margin_trend_month || {};
    makeChart("gmaChartTrend", "line", tr.labels || [], [
      { label: "Margin %", data: tr.margin_pct || [], borderColor: "#0d6efd", yAxisID: "y" },
      { label: "Profit", data: tr.profit || [], borderColor: "#198754", yAxisID: "y1" },
    ], {
      scales: {
        y: { position: "left", title: { display: true, text: "Margin %" } },
        y1: { position: "right", grid: { drawOnChartArea: false } },
      },
    });
    const cu = charts.margin_by_customer || {};
    makeChart("gmaChartCustomer", "bar", cu.labels || [], [
      { label: "Profit", data: cu.profit || [], backgroundColor: "#20c997" },
    ]);
  }

  function renderAdvanced(adv) {
    if (!advancedHost || !adv) return;
    const dims = [
      ["Customer", adv.by_customer],
      ["Item", adv.by_item],
      ["Category", adv.by_category],
      ["Brand", adv.by_brand],
      ["Branch", adv.by_branch],
      ["Salesman", adv.by_salesman],
      ["Invoice", adv.by_invoice],
    ];
    advancedHost.innerHTML = dims
      .map(([title, rows]) => {
        const top = (rows || []).slice(0, 5);
        const lines = top
          .map((r) => `<li>${esc(r.label || r.key)}: ${fmt(r.profit_amount)} (${r.margin_pct != null ? r.margin_pct + "%" : "—"})</li>`)
          .join("");
        return `<div class="gma-adv-card"><h4>${esc(title)}</h4><ul>${lines || "<li>—</li>"}</ul></div>`;
      })
      .join("");
  }

  function tableHtml(title, rows, cols) {
    if (!rows?.length) return `<div class="gma-drill-section"><h3>${esc(title)}</h3><p>No records.</p></div>`;
    const head = cols.map((c) => `<th>${esc(c.label)}</th>`).join("");
    const body = rows
      .map((r) => `<tr>${cols.map((c) => `<td>${esc(r[c.key])}</td>`).join("")}</tr>`)
      .join("");
    return `<div class="gma-drill-section"><h3>${esc(title)}</h3><table class="gma-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  async function loadDrilldown(itemCode) {
    openModal("Loading…", "<p class='gma-loading'>Loading drill-down…</p>");
    const q = queryParams();
    q.set("item_code", itemCode);
    try {
      const res = await fetch(drillUrl + "?" + q.toString());
      const json = await res.json();
      if (!json.success) throw new Error(json.error || "Drill-down failed");
      const d = json.data || {};
      let html = tableHtml("Purchase / Receipt History", d.receipts || d.purchases, [
        { key: "receipt_no", label: "Receipt" },
        { key: "dt", label: "Date" },
        { key: "qty", label: "Qty" },
        { key: "cost", label: "Cost" },
      ]);
      html += tableHtml("Sales History", d.sales, [
        { key: "invoice_no", label: "Invoice" },
        { key: "dt", label: "Date" },
        { key: "qty", label: "Qty" },
        { key: "selling_price", label: "Rate" },
      ]);
      html += tableHtml("Inventory Movement", d.movements, [
        { key: "dt", label: "Date" },
        { key: "transaction_type", label: "Type" },
        { key: "reference_no", label: "Ref" },
        { key: "qty_in", label: "In" },
        { key: "qty_out", label: "Out" },
        { key: "balance", label: "Balance" },
      ]);
      html += tableHtml("Cost History", d.cost_history, [
        { key: "dt", label: "Date" },
        { key: "cost", label: "Cost" },
      ]);
      html += tableHtml("Margin Trend", d.margin_trend, [
        { key: "label", label: "Period" },
        { key: "sales_amount", label: "Sales" },
        { key: "profit_amount", label: "Profit" },
        { key: "margin_pct", label: "Margin %" },
      ]);
      openModal(`Item ${itemCode} — Drill-down`, html);
    } catch (e) {
      openModal("Drill-down", `<p class="gma-error">${esc(e.message)}</p>`);
    }
  }

  async function runAnalysis() {
    showError("");
    if (statusEl) statusEl.textContent = "Loading…";
    syncExportLinks();
    destroyCharts();
    try {
      const res = await fetch(apiUrl + "?" + queryParams().toString());
      const data = await res.json();
      if (!data.success) throw new Error(data.error || "Analysis failed");
      lastPayload = data;
      renderKpis(data.kpis);
      renderGrid(data.grid);
      renderSummaryTabs();
      renderSummaryTable();
      renderCharts(data.charts);
      renderInsights(data.insights);
      renderAdvanced(data.advanced);
      if (statusEl) statusEl.textContent = `Updated ${data.generated_at || ""} · ${(data.grid || []).length} lines`;
    } catch (e) {
      showError(e.message);
      if (statusEl) statusEl.textContent = "";
    }
  }

  document.getElementById("gmaBtnRun")?.addEventListener("click", runAnalysis);
  form?.addEventListener("change", syncExportLinks);
  document.getElementById("gmaBtnPrint")?.addEventListener("click", () => window.print());
  document.getElementById("gmaBtnEmail")?.addEventListener("click", () => {
    const sub = encodeURIComponent("Gross Margin Analysis Report");
    const body = encodeURIComponent("Please find the gross margin analysis report attached or review in the ERP.\n\n" + window.location.href);
    window.location.href = `mailto:?subject=${sub}&body=${body}`;
  });

  syncExportLinks();
  renderSummaryTabs();
  runAnalysis();
})();
