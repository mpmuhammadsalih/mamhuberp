(function () {
  const app = document.getElementById("stockAgingApp");
  if (!app) return;

  const apiUrl = app.dataset.api || "";
  const drillUrl = app.dataset.drill || "";
  const exportExcelBase = app.dataset.exportExcel || "";
  const exportPdfBase = app.dataset.exportPdf || "";

  const form = document.getElementById("saFilterForm");
  const bucketsEditor = document.getElementById("saBucketsEditor");
  const bucketsJsonInput = document.getElementById("saBucketsJson");
  const gridBody = document.getElementById("saGridBody");
  const gridTable = document.getElementById("saGridTable");
  const gridLoading = document.getElementById("saGridLoading");
  const insightsEl = document.getElementById("saInsights");
  const errEl = document.getElementById("saError");
  const drillModal = document.getElementById("saDrillModal");
  const drillBody = document.getElementById("saDrillBody");
  const drillTitle = document.getElementById("saDrillTitle");
  const drillDialog = drillModal?.querySelector(".sa-modal__dialog");

  const pageRoot = document.getElementById("stockAgingApp");

  function ensureDrillModalPortaled() {
    if (!drillModal) return;
    document.body.appendChild(drillModal);
  }
  ensureDrillModalPortaled();

  let chartInstances = {};
  let lastPayload = null;
  let gridRows = [];
  let gridSortKey = "stockvalue";
  let gridSortDir = "desc";

  const GRID_COLUMNS = [
    { key: "itemcode", label: "Item Code", type: "text" },
    { key: "barcode", label: "Barcode", type: "text" },
    { key: "itemname", label: "Item Name", type: "text" },
    { key: "category", label: "Category", type: "text" },
    { key: "brand", label: "Brand", type: "text" },
    { key: "supplier", label: "Supplier", type: "text" },
    { key: "uom", label: "UOM", type: "text" },
    { key: "currentstock", label: "Current Stock", type: "number" },
    { key: "averagecost", label: "Avg Cost", type: "number" },
    { key: "stockvalue", label: "Stock Value", type: "number" },
    { key: "last_purchase_date", label: "Last Purchase", type: "date" },
    { key: "last_receipt_date", label: "Last Receipt", type: "date" },
    { key: "last_sales_date", label: "Last Sales", type: "date" },
    { key: "last_movement_date", label: "Last Movement", type: "date" },
    { key: "age_days", label: "Age Days", type: "number" },
    { key: "aging_bucket", label: "Aging Bucket", type: "text" },
    { key: "status", label: "Status", type: "text" },
    { key: null, label: "", sortable: false },
  ];

  const defaultBuckets = window.STOCK_AGING_DEFAULT_BUCKETS || [
    { id: "b1", label: "0-30 Days", min_days: 0, max_days: 30 },
    { id: "b2", label: "31-60 Days", min_days: 31, max_days: 60 },
    { id: "b3", label: "61-90 Days", min_days: 61, max_days: 90 },
    { id: "b4", label: "91-180 Days", min_days: 91, max_days: 180 },
    { id: "b5", label: "181-365 Days", min_days: 181, max_days: 365 },
    { id: "b6", label: "Above 365 Days", min_days: 366, max_days: null },
  ];

  let buckets = JSON.parse(JSON.stringify(defaultBuckets));

  function fmtNum(n, dec) {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }

  function fmtMoney(n) {
    return fmtNum(n, 2);
  }

  function statusClass(st) {
    const s = String(st || "").toLowerCase();
    if (s.includes("fast")) return "sa-status--fast";
    if (s.includes("slow")) return "sa-status--slow";
    if (s.includes("non")) return "sa-status--non";
    if (s.includes("dead")) return "sa-status--dead";
    return "sa-status--inactive";
  }

  function collectBucketsFromEditor() {
    const rows = bucketsEditor.querySelectorAll(".sa-bucket-row");
    const out = [];
    rows.forEach((row, i) => {
      const label = row.querySelector('[data-f="label"]')?.value?.trim() || `Bucket ${i + 1}`;
      const min = parseInt(row.querySelector('[data-f="min"]')?.value, 10);
      const maxRaw = row.querySelector('[data-f="max"]')?.value;
      const max = maxRaw === "" || maxRaw == null ? null : parseInt(maxRaw, 10);
      out.push({
        id: `b${i}`,
        label,
        min_days: Number.isFinite(min) ? min : 0,
        max_days: Number.isFinite(max) ? max : null,
      });
    });
    return out.length ? out : defaultBuckets;
  }

  function renderBucketsEditor() {
    bucketsEditor.innerHTML = "";
    buckets.forEach((b, i) => {
      const row = document.createElement("div");
      row.className = "sa-bucket-row";
      row.innerHTML = `
        <input data-f="label" type="text" value="${escapeAttr(b.label)}" title="Label" />
        <input data-f="min" type="number" min="0" value="${b.min_days ?? 0}" title="Min days" />
        <input data-f="max" type="number" min="0" value="${b.max_days == null ? "" : b.max_days}" placeholder="∞" title="Max days" />
        <button type="button" class="sa-btn" data-rm="${i}" title="Remove">×</button>
      `;
      bucketsEditor.appendChild(row);
    });
    bucketsEditor.querySelectorAll("[data-rm]").forEach((btn) => {
      btn.addEventListener("click", () => {
        buckets = collectBucketsFromEditor();
        buckets.splice(parseInt(btn.dataset.rm, 10), 1);
        renderBucketsEditor();
      });
    });
  }

  function escapeAttr(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function queryParams() {
    const fd = new FormData(form);
    buckets = collectBucketsFromEditor();
    bucketsJsonInput.value = JSON.stringify(buckets);
    const p = new URLSearchParams();
    fd.forEach((v, k) => {
      if (k === "include_zero") return;
      if (v != null && String(v).trim() !== "") p.set(k, v);
    });
    if (form.querySelector('[name="include_zero"]')?.checked) p.set("include_zero", "1");
    p.set("buckets_json", bucketsJsonInput.value);
    return p;
  }

  function syncExportLinks() {
    const q = queryParams().toString();
    document.getElementById("saBtnExcel").href = exportExcelBase + (q ? `?${q}` : "");
    document.getElementById("saBtnPdf").href = exportPdfBase + (q ? `?${q}` : "");
  }

  function showError(msg) {
    if (!msg) {
      errEl.classList.add("hidden");
      errEl.textContent = "";
      return;
    }
    errEl.textContent = msg;
    errEl.classList.remove("hidden");
  }

  function updateKpis(summary) {
    document.querySelectorAll("[data-kpi]").forEach((el) => {
      const key = el.dataset.kpi;
      const v = summary[key];
      if (key.includes("value")) el.textContent = fmtMoney(v);
      else if (key === "total_stock_quantity") el.textContent = fmtNum(v, 3);
      else el.textContent = v != null ? String(v) : "—";
    });
  }

  function destroyCharts() {
    Object.values(chartInstances).forEach((c) => c.destroy());
    chartInstances = {};
  }

  function makeChart(id, type, labels, values, opts) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    if (chartInstances[id]) chartInstances[id].destroy();
    const isSmall = window.matchMedia("(max-width: 768px)").matches;
    chartInstances[id] = new Chart(canvas, {
      type,
      data: {
        labels,
        datasets: [
          {
            label: opts?.label || "Value",
            data: values,
            backgroundColor: opts?.colors || [
              "#1e3a5f", "#0d6efd", "#20c997", "#fd7e14", "#dc3545", "#6f42c1",
            ],
            borderWidth: type === "line" ? 2 : 0,
            fill: type === "line",
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: type === "pie" || type === "doughnut",
            position: isSmall ? "bottom" : "top",
            labels: { boxWidth: 10, font: { size: isSmall ? 9 : 11 } },
          },
        },
        scales:
          type === "bar" || type === "line"
            ? {
                x: { ticks: { maxRotation: isSmall ? 45 : 0, autoSkip: true, maxTicksLimit: isSmall ? 6 : 12 } },
                y: { beginAtZero: true, ticks: { font: { size: isSmall ? 9 : 11 } } },
              }
            : {},
      },
    });
  }

  function resizeAllCharts() {
    Object.values(chartInstances).forEach((c) => {
      try {
        c.resize();
      } catch (e) {
        /* ignore */
      }
    });
  }

  function renderCharts(charts) {
    if (!charts) return;
    makeChart("chartBuckets", "bar", charts.bucket_chart?.labels || [], charts.bucket_chart?.values || [], { label: "Stock value" });
    makeChart("chartCategory", "doughnut", charts.by_category?.labels || [], charts.by_category?.values || []);
    makeChart("chartDead", "bar", charts.dead_stock_top20?.labels || [], charts.dead_stock_top20?.values || [], { label: "Dead stock value" });
    makeChart("chartSlow", "bar", charts.slow_moving_top20?.labels || [], charts.slow_moving_top20?.values || [], { label: "Slow moving value" });
    makeChart("chartSupplier", "bar", charts.by_supplier?.labels || [], charts.by_supplier?.values || [], { label: "By supplier" });
    makeChart("chartTrend", "line", charts.inventory_trend?.labels || [], charts.inventory_trend?.values || [], { label: "Activity" });
  }

  function renderInsights(insights) {
    if (!insights || !insights.length) {
      insightsEl.innerHTML = "<p class='sa-loading'>No insights for current filters.</p>";
      return;
    }
    insightsEl.innerHTML = insights
      .map(
        (i) => `
      <div class="sa-insight sa-insight--${i.severity || "info"}">
        <strong>${escapeHtml(i.title || "")}</strong>
        ${escapeHtml(i.message || "")}
      </div>`
      )
      .join("");
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function compareGridRows(a, b, col) {
    if (!col || !col.key) return 0;
    const key = col.key;
    const type = col.type || "text";
    let va = a[key];
    let vb = b[key];
    if (type === "number") {
      const na = Number(va);
      const nb = Number(vb);
      const aBad = !Number.isFinite(na);
      const bBad = !Number.isFinite(nb);
      if (aBad && bBad) return 0;
      if (aBad) return 1;
      if (bBad) return -1;
      return na - nb;
    }
    if (type === "date") {
      const da = Date.parse(String(va || "").slice(0, 10));
      const db = Date.parse(String(vb || "").slice(0, 10));
      const aBad = Number.isNaN(da);
      const bBad = Number.isNaN(db);
      if (aBad && bBad) return 0;
      if (aBad) return 1;
      if (bBad) return -1;
      return da - db;
    }
    return String(va ?? "")
      .toLowerCase()
      .localeCompare(String(vb ?? "").toLowerCase(), undefined, { numeric: true });
  }

  function sortGridRows(rows) {
    const col = GRID_COLUMNS.find((c) => c.key === gridSortKey);
    if (!col || col.sortable === false) return rows;
    const sorted = rows.slice();
    const dir = gridSortDir === "asc" ? 1 : -1;
    sorted.sort((a, b) => compareGridRows(a, b, col) * dir);
    return sorted;
  }

  function updateSortHeaderUi() {
    const headRow = document.getElementById("saGridHeadRow");
    if (!headRow) return;
    headRow.querySelectorAll("th[data-sort-key]").forEach((th) => {
      th.classList.remove("sa-sort-asc", "sa-sort-desc");
      if (th.dataset.sortKey === gridSortKey) {
        th.classList.add(gridSortDir === "asc" ? "sa-sort-asc" : "sa-sort-desc");
      }
    });
  }

  function renderGridHead() {
    const headRow = document.getElementById("saGridHeadRow");
    if (!headRow) return;
    headRow.innerHTML = "";
    GRID_COLUMNS.forEach((col) => {
      const th = document.createElement("th");
      if (col.key && col.sortable !== false) {
        th.className = "sa-sortable";
        th.dataset.sortKey = col.key;
        th.setAttribute("scope", "col");
        th.setAttribute("title", `Sort by ${col.label}`);
        th.textContent = col.label;
      } else {
        th.textContent = col.label || "";
      }
      headRow.appendChild(th);
    });
    updateSortHeaderUi();
  }

  function onGridHeaderClick(e) {
    const th = e.target.closest("th.sa-sortable[data-sort-key]");
    if (!th) return;
    e.preventDefault();
    e.stopPropagation();
    const key = th.dataset.sortKey;
    if (!key) return;
    if (gridSortKey === key) {
      gridSortDir = gridSortDir === "asc" ? "desc" : "asc";
    } else {
      gridSortKey = key;
      const col = GRID_COLUMNS.find((c) => c.key === key);
      gridSortDir = col && col.type === "text" ? "asc" : "desc";
    }
    updateSortHeaderUi();
    renderGridBody(sortGridRows(gridRows));
  }

  function renderGridBody(rows) {
    if (!gridBody) return;
    gridBody.innerHTML = "";
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      tr.dataset.itemcode = r.itemcode;
      tr.innerHTML = `
        <td>${escapeHtml(r.itemcode)}</td>
        <td>${escapeHtml(r.barcode)}</td>
        <td>${escapeHtml(r.itemname)}</td>
        <td>${escapeHtml(r.category)}</td>
        <td>${escapeHtml(r.brand)}</td>
        <td>${escapeHtml(r.supplier)}</td>
        <td>${escapeHtml(r.uom)}</td>
        <td class="num">${fmtNum(r.currentstock, 3)}</td>
        <td class="num">${fmtNum(r.averagecost, 4)}</td>
        <td class="num">${fmtMoney(r.stockvalue)}</td>
        <td>${escapeHtml(r.last_purchase_date)}</td>
        <td>${escapeHtml(r.last_receipt_date)}</td>
        <td>${escapeHtml(r.last_sales_date)}</td>
        <td>${escapeHtml(r.last_movement_date)}</td>
        <td>${escapeHtml(r.age_days)}</td>
        <td>${escapeHtml(r.aging_bucket)}</td>
        <td><span class="sa-status ${statusClass(r.status)}">${escapeHtml(r.status)}</span></td>
        <td><button type="button" class="sa-btn sa-view-btn">View</button></td>
      `;
      tr.addEventListener("click", (e) => {
        if (e.target.closest(".sa-view-btn")) {
          e.stopPropagation();
          openDrilldown(r.itemcode, r.itemname);
        } else {
          openDrilldown(r.itemcode, r.itemname);
        }
      });
      gridBody.appendChild(tr);
    });
  }

  function renderGrid(rows) {
    gridLoading.classList.add("hidden");
    gridTable.classList.remove("hidden");
    gridRows = Array.isArray(rows) ? rows.slice() : [];
    renderGridBody(sortGridRows(gridRows));
  }

  async function runAnalysis() {
    syncExportLinks();
    showError("");
    gridLoading.classList.remove("hidden");
    gridLoading.textContent = "Loading stock aging data…";
    gridTable.classList.add("hidden");
    destroyCharts();
    const q = queryParams().toString();
    try {
      const res = await fetch(`${apiUrl}?${q}`);
      const data = await res.json();
      if (!data.success && data.error) {
        showError(data.error);
        gridLoading.textContent = "No data.";
        return;
      }
      lastPayload = data;
      updateKpis(data.summary || {});
      renderCharts(data.charts);
      renderInsights(data.insights);
      renderGrid(data.rows || []);
      window.setTimeout(resizeAllCharts, 80);
      if (data.error) showError(data.error);
    } catch (err) {
      showError("Failed to load stock aging data.");
      gridLoading.textContent = "Error loading data.";
    }
  }

  function tableHtml(cols, rows) {
    if (!rows || !rows.length) return "<p class='muted'>No records.</p>";
    const heads = cols.map((c) => `<th>${escapeHtml(c.label)}</th>`).join("");
    const body = rows
      .map((r) => `<tr>${cols.map((c) => `<td>${escapeHtml(r[c.key] ?? "")}</td>`).join("")}</tr>`)
      .join("");
    return `<table class="sa-mini-table"><thead><tr>${heads}</tr></thead><tbody>${body}</tbody></table>`;
  }

  const tabSchemas = {
    receipts: [
      { key: "receipt_no", label: "Receipt No" },
      { key: "dt", label: "Date" },
      { key: "supplier", label: "Supplier" },
      { key: "qty", label: "Qty" },
      { key: "cost", label: "Cost" },
    ],
    purchases: [
      { key: "receipt_no", label: "Bill No" },
      { key: "dt", label: "Date" },
      { key: "qty", label: "Qty" },
      { key: "cost", label: "Cost" },
    ],
    sales: [
      { key: "invoice_no", label: "Invoice No" },
      { key: "dt", label: "Date" },
      { key: "qty", label: "Qty" },
      { key: "selling_price", label: "Selling Price" },
    ],
    movements: [
      { key: "dt", label: "Date" },
      { key: "transaction_type", label: "Type" },
      { key: "reference_no", label: "Reference" },
      { key: "qty_in", label: "Qty In" },
      { key: "qty_out", label: "Qty Out" },
      { key: "balance_qty", label: "Balance" },
    ],
    cost_history: [
      { key: "previous_cost", label: "Previous Cost" },
      { key: "new_cost", label: "New Cost" },
      { key: "change_date", label: "Change Date" },
      { key: "note", label: "Note" },
    ],
  };

  let drillCache = null;
  let activeTab = "receipts";

  function renderDrillTab(tab) {
    activeTab = tab;
    document.querySelectorAll("#saDrillTabs .sa-tab").forEach((t) => {
      t.classList.toggle("is-active", t.dataset.tab === tab);
    });
    if (!drillCache) {
      drillBody.innerHTML = "Loading…";
      return;
    }
    const rows = drillCache[tab] || drillCache.data?.[tab] || [];
    drillBody.innerHTML = tableHtml(tabSchemas[tab] || [], rows);
  }

  function openDrillModal() {
    if (!drillModal) return;
    ensureDrillModalPortaled();
    drillModal.classList.remove("hidden");
    document.body.classList.add("sa-drill-modal-open");
    pageRoot?.setAttribute("aria-hidden", "true");
    window.setTimeout(() => {
      drillModal.querySelector(".sa-tab.is-active")?.focus?.();
    }, 50);
  }

  function closeDrillModal() {
    if (!drillModal) return;
    drillModal.classList.add("hidden");
    document.body.classList.remove("sa-drill-modal-open");
    pageRoot?.removeAttribute("aria-hidden");
  }

  async function openDrilldown(itemcode, itemname) {
    if (!drillModal) return;
    openDrillModal();
    drillTitle.textContent = `${itemcode} — ${itemname || ""}`;
    drillCache = null;
    activeTab = "receipts";
    renderDrillTab("receipts");
    const p = queryParams();
    p.set("itemcode", String(itemcode ?? "").trim());
    try {
      const res = await fetch(`${drillUrl}?${p}`);
      const data = await res.json();
      drillCache = data.data || data;
      renderDrillTab(activeTab);
    } catch (e) {
      drillBody.innerHTML = "<p>Could not load drill-down data.</p>";
    }
  }

  document.getElementById("saDrillTabs")?.addEventListener("click", (e) => {
    const tab = e.target.closest(".sa-tab");
    if (!tab) return;
    renderDrillTab(tab.dataset.tab);
  });

  drillDialog?.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  drillModal?.addEventListener("click", (e) => {
    const isBackdrop = e.target.classList.contains("sa-modal__backdrop");
    const isCloseBtn = e.target.closest("[data-close='saDrillModal']");
    if (isBackdrop || isCloseBtn) {
      closeDrillModal();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drillModal && !drillModal.classList.contains("hidden")) {
      closeDrillModal();
    }
  });

  document.getElementById("saBtnRun")?.addEventListener("click", runAnalysis);
  document.getElementById("saBtnAi")?.addEventListener("click", () => {
    if (!lastPayload) runAnalysis();
    else renderInsights(lastPayload.insights);
    insightsEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  document.getElementById("saBtnPrint")?.addEventListener("click", () => window.print());
  document.getElementById("saBtnEmail")?.addEventListener("click", () => {
    const sub = encodeURIComponent("Stock Aging Report");
    const body = encodeURIComponent(
      `Stock Aging Analysis\nAs on: ${form.as_on_date?.value || ""}\nTotal value: ${document.querySelector('[data-kpi="total_inventory_value"]')?.textContent || ""}\n\nOpen report in ERP for full detail.`
    );
    window.location.href = `mailto:?subject=${sub}&body=${body}`;
  });

  document.getElementById("saAddBucket")?.addEventListener("click", () => {
    buckets = collectBucketsFromEditor();
    buckets.push({ id: `b${buckets.length}`, label: "New bucket", min_days: 0, max_days: 30 });
    renderBucketsEditor();
  });

  form?.addEventListener("change", syncExportLinks);

  const filtersPanel = document.getElementById("saFiltersPanel");
  const filtersToggle = document.getElementById("saFiltersToggle");
  const mobileMq = window.matchMedia("(max-width: 900px)");

  function syncFiltersPanelState() {
    if (!filtersPanel || !filtersToggle) return;
    const mobile = mobileMq.matches;
    if (!mobile) {
      filtersPanel.classList.add("is-open");
      filtersToggle.setAttribute("aria-expanded", "true");
      filtersToggle.textContent = "Filters";
      return;
    }
    const open = filtersPanel.classList.contains("is-open");
    filtersToggle.setAttribute("aria-expanded", open ? "true" : "false");
    filtersToggle.textContent = open ? "Hide filters ▴" : "Show filters ▾";
  }

  filtersToggle?.addEventListener("click", () => {
    filtersPanel?.classList.toggle("is-open");
    syncFiltersPanelState();
    window.setTimeout(resizeAllCharts, 120);
  });

  mobileMq.addEventListener("change", () => {
    if (!mobileMq.matches) {
      filtersPanel?.classList.add("is-open");
    } else {
      filtersPanel?.classList.remove("is-open");
    }
    syncFiltersPanelState();
    resizeAllCharts();
  });

  syncFiltersPanelState();

  let resizeTimer;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(resizeAllCharts, 150);
  });

  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => resizeAllCharts());
    document.getElementById("saCharts")?.querySelectorAll(".sa-chart-canvas-wrap").forEach((el) => ro.observe(el));
  }

  renderGridHead();
  document.getElementById("saGridHead")?.addEventListener("click", onGridHeaderClick);

  renderBucketsEditor();
  syncExportLinks();

  const init = window.STOCK_AGING_INITIAL_FILTERS;
  if (init?.as_on_date) {
    runAnalysis();
  }
})();
