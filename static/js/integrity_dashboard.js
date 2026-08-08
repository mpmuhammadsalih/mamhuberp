(function () {
  const app = document.getElementById("integrityDashboardApp");
  if (!app) return;

  const apiUrl = app.dataset.api || "";
  const journalUrl = app.dataset.journal || "";
  const movementUrl = app.dataset.movement || "";
  const exportExcel = app.dataset.exportExcel || "";
  const exportPdf = app.dataset.exportPdf || "";
  const stockGlDrillUrl = app.dataset.stockGlDrill || "";

  const form = document.getElementById("aidFilterForm");
  const kpiGrid = document.getElementById("aidKpiGrid");
  const sectionsHost = document.getElementById("aidSectionsHost");
  const sectionTabs = document.getElementById("aidSectionTabs");
  const insightsEl = document.getElementById("aidInsights");
  const detailPanel = document.getElementById("aidDetailPanel");
  const errEl = document.getElementById("aidError");
  const statusEl = document.getElementById("aidStatus");
  const drillModal = document.getElementById("aidDrillModal");
  const drillBody = document.getElementById("aidDrillBody");
  const drillTitle = document.getElementById("aidDrillTitle");

  if (drillModal && drillModal.parentElement !== document.body) {
    document.body.appendChild(drillModal);
  }

  let lastPayload = null;
  let activeSection = "posting";

  const SECTIONS = [
    { id: "posting", label: "Posting Verification", key: "posting_verification" },
    { id: "stock_gl", label: "Stock vs GL", key: "stock_gl_reconciliation" },
    { id: "customer", label: "Customer Recon", key: "customer_reconciliation" },
    { id: "supplier", label: "Supplier Recon", key: "supplier_reconciliation" },
    { id: "unbalanced", label: "Unbalanced Journals", key: "unbalanced_journals" },
    { id: "negative", label: "Negative Stock", key: "negative_stock" },
    { id: "cost", label: "Cost Verification", key: "cost_verification" },
    { id: "mapping", label: "Account Mapping", key: "account_mappings" },
    { id: "tax", label: "Tax Validation", key: "tax_validation" },
    { id: "cash", label: "Cash & Bank", key: "cash_bank" },
    { id: "pl", label: "P&L Validation", key: "profit_loss" },
    { id: "movement", label: "Inventory Movement", key: "inventory_movement" },
  ];

  const fmt = (n, d) => {
    if (n == null || n === "") return "—";
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString(undefined, { maximumFractionDigits: d != null ? d : 2 });
  };

  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };

  const badge = (st) => {
    const s = String(st || "ok").toLowerCase();
    const cls = s === "err" || s === "error" ? "aid-badge--err" : s === "warn" || s === "warning" ? "aid-badge--warn" : "aid-badge--ok";
    return `<span class="aid-badge ${cls}">${esc(s)}</span>`;
  };

  function queryParams() {
    const p = new URLSearchParams(new FormData(form));
    return p;
  }

  function syncExportLinks() {
    const q = queryParams().toString();
    const ex = document.getElementById("aidBtnExcel");
    const pdf = document.getElementById("aidBtnPdf");
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

  function openModal(title, html) {
    if (!drillModal) return;
    drillTitle.textContent = title;
    drillBody.innerHTML = html;
    drillModal.classList.remove("hidden");
    document.body.classList.add("aid-modal-open");
    document.body.appendChild(drillModal);
  }

  function closeModal() {
    if (!drillModal) return;
    drillModal.classList.add("hidden");
    document.body.classList.remove("aid-modal-open");
  }

  drillModal?.addEventListener("click", (e) => {
    if (e.target.classList.contains("aid-modal__backdrop") || e.target.closest("[data-close='aidDrillModal']")) {
      closeModal();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drillModal && !drillModal.classList.contains("hidden")) closeModal();
  });

  function renderKpis(summary) {
    if (!kpiGrid || !summary) return;
    kpiGrid.querySelectorAll("[data-kpi]").forEach((el) => {
      const key = el.dataset.kpi;
      const val = summary[key];
      const vEl = el.querySelector(".aid-kpi__val");
      if (!vEl) return;
      if (key.includes("variance") && key !== "inventory_variance") {
        vEl.textContent = fmt(val, 2);
      } else if (key === "inventory_variance") {
        vEl.textContent = fmt(val, 2);
      } else {
        vEl.textContent = fmt(val, 0);
      }
      el.classList.remove("aid-kpi--ok", "aid-kpi--warn", "aid-kpi--err");
      const n = Number(val);
      if (key === "successful_postings" && n > 0) el.classList.add("aid-kpi--ok");
      else if (key === "critical_errors" || key === "failed_postings" || key === "unbalanced_journals") {
        if (n > 0) el.classList.add("aid-kpi--err");
      } else if (key.includes("variance") || key === "missing_account_mappings" || key === "negative_stock_count") {
        if (Math.abs(n) > 0) el.classList.add("aid-kpi--warn");
      }
    });
  }

  function customerReconSummaryHtml(sum) {
    if (!sum || sum.customer_ledger_total == null) return "";
    const acct = sum.ar_control_account || "1200";
    const diff = Number(sum.control_difference) || 0;
    return `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Customer ledger total</span><strong>${fmt(sum.customer_ledger_total, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>AR control (${esc(acct)})</span><strong>${fmt(sum.ar_control_balance, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Control difference</span><strong>${fmt(diff, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Customers checked</span><strong>${fmt(sum.customer_count, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">AR variance is the absolute control difference: customer outstanding total vs GL AR control account for the selected date range.</p>`;
  }

  function stockGlSummaryHtml(sum) {
    if (!sum || sum.total_stock_value == null) return "";
    const acct = sum.inventory_account || "1300";
    const diff = Number(sum.difference) || 0;
    return `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Branch stock total</span><strong>${fmt(sum.total_stock_value, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Inventory control (${esc(acct)})</span><strong>${fmt(sum.gl_inventory_balance, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Control difference</span><strong>${fmt(diff, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Warehouses</span><strong>${fmt(sum.warehouse_count, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">Inventory variance compares branch stock valuation to the GL inventory control account. Warehouse rows show proportional GL allocation for breakdown only — the <strong>Branch total</strong> row is the real reconciliation.</p>`;
  }

  function requirePayload(title) {
    if (!lastPayload) {
      openModal(title, "<p>Run full audit first.</p>");
      return false;
    }
    return true;
  }

  function goToSection(sectionId) {
    closeModal();
    activeSection = sectionId;
    renderSections(lastPayload);
    document.getElementById("aidSec_" + sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function bindDrillGo(btnId, sectionId) {
    document.getElementById(btnId)?.addEventListener("click", () => goToSection(sectionId));
  }

  function drillActionsHtml(btnId, label) {
    return `<div class="aid-drill-actions"><button type="button" class="aid-btn aid-btn--primary" id="${btnId}">${esc(label)}</button></div>`;
  }

  const POSTING_COLS = [
    { key: "document_no", label: "Document No" },
    { key: "document_date", label: "Date" },
    { key: "module", label: "Module" },
    { key: "voucher_no", label: "Voucher" },
    { key: "expected_entries", label: "Expected", num: 0 },
    { key: "actual_entries", label: "Actual", num: 0 },
    { key: "status", label: "Status", badge: true },
    { key: "status_note", label: "Note" },
  ];

  function postingSummaryHtml(sum) {
    if (!sum || sum.total == null) return "";
    return `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Total checked</span><strong>${fmt(sum.total, 0)}</strong></div>
        <div class="aid-recon-summary__item"><span>Successful</span><strong>${fmt(sum.ok, 0)}</strong></div>
        <div class="aid-recon-summary__item"><span>Failed</span><strong>${fmt(sum.failed, 0)}</strong></div>
        <div class="aid-recon-summary__item"><span>Warnings</span><strong>${fmt(sum.warn, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">Posting verification checks sales, purchase, receipt, and payment documents for expected GL voucher lines in the selected period.</p>`;
  }

  function postingRows(filterFn, limit) {
    const rows = (lastPayload.posting_verification?.rows || []).filter(filterFn);
    return rows.slice(0, limit || 150);
  }

  function drillTransactionsChecked() {
    if (!requirePayload("Transactions Checked")) return;
    const block = lastPayload.posting_verification || {};
    const sum = block.summary || {};
    const rows = postingRows(() => true, 150);
    let html = postingSummaryHtml(sum);
    html += `<p><strong>KPI:</strong> ${fmt(lastPayload.summary?.total_transactions_checked, 0)} documents checked in the selected period.</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Documents checked</h4>";
    html += tableHtml(POSTING_COLS, rows);
    html += drillActionsHtml("aidDrillGoPosting", "Open Posting Verification tab");
    openModal("Transactions Checked — Details", html);
    bindDrillGo("aidDrillGoPosting", "posting");
  }

  function drillSuccessfulPostings() {
    if (!requirePayload("Successful Postings")) return;
    const block = lastPayload.posting_verification || {};
    const sum = block.summary || {};
    const rows = postingRows((r) => r.status === "ok", 150);
    let html = postingSummaryHtml(sum);
    html += `<p><strong>KPI:</strong> ${fmt(lastPayload.summary?.successful_postings, 0)} documents with balanced GL postings.</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Successful postings</h4>";
    html += tableHtml(POSTING_COLS, rows);
    html += drillActionsHtml("aidDrillGoPostingOk", "Open Posting Verification tab");
    openModal("Successful Postings — Details", html);
    bindDrillGo("aidDrillGoPostingOk", "posting");
  }

  function drillFailedPostings() {
    if (!requirePayload("Failed Postings")) return;
    const block = lastPayload.posting_verification || {};
    const sum = block.summary || {};
    const rows = postingRows((r) => r.status !== "ok", 150);
    let html = postingSummaryHtml(sum);
    html += `<p><strong>KPI:</strong> ${fmt(lastPayload.summary?.failed_postings, 0)} documents with missing or incomplete GL postings.</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Failed / incomplete postings</h4>";
    html += tableHtml(POSTING_COLS, rows);
    html += drillActionsHtml("aidDrillGoPostingFail", "Open Posting Verification tab");
    openModal("Failed Postings — Details", html);
    bindDrillGo("aidDrillGoPostingFail", "posting");
  }

  function drillInventoryVariance() {
    if (!requirePayload("Inventory Variance")) return;
    const block = lastPayload.stock_gl_reconciliation || {};
    const sum = block.summary || {};
    const rows = block.rows || [];
    const variance = Number(lastPayload.summary?.inventory_variance) || 0;
    const stock = Number(sum.total_stock_value) || 0;
    const control = Number(sum.gl_inventory_balance) || 0;
    const diff = Number(sum.difference) || 0;
    const acct = sum.inventory_account || "1300";
    const absVar = Math.abs(variance);
    const statusText = absVar <= 0.01
      ? "Balanced — branch stock valuation matches inventory control."
      : absVar <= 500
        ? "Minor variance — review stock valuation vs GL inventory account."
        : "Significant variance — investigate inventory postings, cost updates, and stock adjustments.";

    let html = stockGlSummaryHtml(sum);
    html += `<p><strong>Inventory variance (KPI):</strong> ${fmt(variance, 2)} &nbsp;|&nbsp; <strong>Status:</strong> ${esc(statusText)}</p>`;
    html += `<p class="aid-recon-note"><strong>Formula:</strong> Branch stock total (${fmt(stock, 2)}) − Inventory control ${esc(acct)} (${fmt(control, 2)}) = ${fmt(diff, 2)}</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Stock vs GL by warehouse <span class='aid-muted' style='font-weight:400'>(click a row for item breakdown)</span></h4>";
    html += stockGlTableHtml(
      [
        { key: "warehouse", label: "Warehouse" },
        { key: "stock_value", label: "Stock Value", num: 2 },
        { key: "gl_balance", label: "GL Balance", num: 2 },
        { key: "difference", label: "Difference", num: 2 },
        { key: "balance_source", label: "Source" },
        { key: "status", label: "Status", badge: true },
      ],
      rows.slice(0, 100)
    );
    html += drillActionsHtml("aidDrillGoStockGl", "Open Stock vs GL tab");
    openModal("Inventory Variance — Details", html);
    bindDrillGo("aidDrillGoStockGl", "stock_gl");
    bindStockGlDrillRows();
  }

  function stockGlTableHtml(cols, rows) {
    if (!rows.length) return "<p style='font-size:0.75rem;color:#6c757d'>No rows.</p>";
    const head = cols.map((c) => `<th>${esc(c.label)}</th>`).join("");
    const body = rows
      .map((row) => {
        const attrs = ` class="aid-stock-gl-row aid-row-click" data-warehouse-id="${esc(row.warehouse_id ?? "")}" data-row-type="${esc(row.row_type || "total")}" data-warehouse="${esc(row.warehouse || "")}"`;
        const cells = cols
          .map((c) => {
            let v = row[c.key];
            if (c.badge) return `<td>${badge(v)}</td>`;
            if (c.num) return `<td class="num">${fmt(v, c.num)}</td>`;
            return `<td>${esc(v ?? "")}</td>`;
          })
          .join("");
        return `<tr${attrs}>${cells}</tr>`;
      })
      .join("");
    return `<div class="aid-table-scroll"><table class="aid-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function stockGlDrillSummaryHtml(sum) {
    if (!sum || sum.stock_value == null) return "";
    const acct = sum.inventory_account || "1300";
    const diff = Number(sum.difference) || 0;
    const isWarehouse = sum.row_type === "warehouse";
    const stockLabel = isWarehouse ? "Warehouse stock value" : "Branch stock total";
    const glLabel = isWarehouse ? `GL allocated — est. share of ${esc(acct)}` : `Inventory control (${esc(acct)})`;
    const countLabel = isWarehouse ? "Items in warehouse" : "Items checked";
    const countVal = sum.item_count;
    const note = isWarehouse
      ? "Physical stock in this warehouse vs its estimated share of the branch GL inventory account."
      : "Branch stock valuation vs the full GL inventory control account — this is the real inventory variance check.";
    return `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>${stockLabel}</span><strong>${fmt(sum.stock_value, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>${glLabel}</span><strong>${fmt(sum.gl_balance, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>${isWarehouse ? "Estimated difference" : "Control difference"}</span><strong>${fmt(diff, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>${countLabel}</span><strong>${fmt(countVal, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">${note}</p>`;
  }

  function renderStockGlDrillPayload(data) {
    const sum = data.summary || {};
    const notes = (data.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
    let html = stockGlDrillSummaryHtml(sum);
    if (notes) html += `<ul class="aid-drill-notes">${notes}</ul>`;
    html += `<p class="aid-recon-note"><strong>${esc(sum.warehouse || "Scope")}</strong> — ${fmt(sum.item_count, 0)} item(s)`;
    if (sum.issue_count) html += `, <strong>${fmt(sum.issue_count, 0)}</strong> with mapping issues`;
    html += ".</p>";
    const isWarehouse = sum.row_type === "warehouse";
    const itemCols = isWarehouse
      ? [
          { key: "item_code", label: "Item" },
          { key: "item_name", label: "Name" },
          { key: "warehouse_qty", label: "WH Qty (here)", num: 3 },
          { key: "branch_warehouse_qty", label: "Branch WH Qty", num: 3 },
          { key: "itemmaster_qty", label: "IM Qty", num: 3 },
          { key: "qty_difference", label: "Qty Diff", num: 3 },
          { key: "stock_value", label: "WH Val", num: 2 },
          { key: "value_difference", label: "Val Diff", num: 2 },
          { key: "inventory_account", label: "Inv. Acct" },
          { key: "issue", label: "Issue" },
          { key: "status", label: "Status", badge: true },
        ]
      : [
          { key: "item_code", label: "Item" },
          { key: "item_name", label: "Name" },
          { key: "branch_warehouse_qty", label: "Branch WH Qty", num: 3 },
          { key: "itemmaster_qty", label: "IM Qty", num: 3 },
          { key: "qty_difference", label: "Qty Diff", num: 3 },
          { key: "branch_stock_value", label: "Stock Val", num: 2 },
          { key: "value_difference", label: "Val Diff", num: 2 },
          { key: "inventory_account", label: "Inv. Acct" },
          { key: "issue", label: "Issue" },
          { key: "status", label: "Status", badge: true },
        ];
    html += `<h4 style='margin:14px 0 8px;font-size:0.85rem;'>${isWarehouse ? "Items in this warehouse" : "Items driving variance"}</h4>`;
    html += `<p class="aid-recon-note" style="margin-bottom:8px;"><strong>Qty Diff</strong> = Branch warehouse qty − Item Master qty. <strong>Val Diff</strong> = value impact of that qty gap. Status <strong>WARN</strong> when they do not match.</p>`;
    html += tableHtml(itemCols, (data.items || []).slice(0, 150));
    const glRows = data.gl_movements || [];
    if (glRows.length) {
      html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>GL movements on inventory control</h4>";
      html += tableHtml(
        [
          { key: "voucher_no", label: "Voucher" },
          { key: "date", label: "Date" },
          { key: "debit", label: "Debit", num: 2 },
          { key: "credit", label: "Credit", num: 2 },
          { key: "net", label: "Net", num: 2 },
          { key: "narration", label: "Narration" },
        ],
        glRows.slice(0, 40),
        "voucher_no"
      );
    }
    html += `<div class="aid-drill-actions"><button type="button" class="aid-btn" id="aidDrillStockGlBack">← Back to warehouses</button></div>`;
    return html;
  }

  async function drillStockGlVarianceRow(warehouseId, rowType, warehouseLabel) {
    if (!stockGlDrillUrl) {
      openModal("Variance detail", "<p>Drill API not configured.</p>");
      return;
    }
    const p = queryParams();
    p.set("warehouse_id", warehouseId || "");
    p.set("row_type", rowType || "total");
    if (warehouseLabel) p.set("warehouse_label", warehouseLabel);
    const title = "Variance detail — " + (warehouseLabel || "Branch total");
    openModal(title, "<p class='aid-loading'>Loading item breakdown…</p>");
    try {
      const res = await fetch(stockGlDrillUrl + "?" + p.toString());
      const data = await res.json();
      if (!data.success) {
        drillBody.innerHTML = "<p>" + esc(data.error || "Failed to load breakdown.") + "</p>";
        return;
      }
      drillBody.innerHTML = renderStockGlDrillPayload(data);
      document.getElementById("aidDrillStockGlBack")?.addEventListener("click", drillInventoryVariance);
      bindRowClicksIn(drillBody);
    } catch (e) {
      drillBody.innerHTML = "<p>Failed to load variance breakdown.</p>";
    }
  }

  function bindStockGlDrillRows(root) {
    const host = root || drillBody;
    host?.querySelectorAll("tr.aid-stock-gl-row").forEach((tr) => {
      tr.style.cursor = "pointer";
      tr.title = "Click to see item-level variance breakdown";
      tr.addEventListener("click", () => {
        drillStockGlVarianceRow(
          tr.dataset.warehouseId || "",
          tr.dataset.rowType || "total",
          tr.dataset.warehouse || ""
        );
      });
    });
  }

  function drillUnbalancedJournals() {
    if (!requirePayload("Unbalanced Journals")) return;
    const block = lastPayload.unbalanced_journals || {};
    const rows = block.rows || [];
    const count = Number(lastPayload.summary?.unbalanced_journals) || rows.length;
    let html = `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Unbalanced journals</span><strong>${fmt(count, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">Journals where total debits do not equal total credits within tolerance.</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Unbalanced journal vouchers</h4>";
    html += tableHtml(
      [
        { key: "journal_no", label: "Journal No" },
        { key: "date", label: "Date" },
        { key: "debit", label: "Debit", num: 2 },
        { key: "credit", label: "Credit", num: 2 },
        { key: "difference", label: "Difference", num: 2 },
        { key: "source", label: "Source" },
        { key: "status", label: "Status", badge: true },
      ],
      rows.slice(0, 100)
    );
    html += drillActionsHtml("aidDrillGoUnbalanced", "Open Unbalanced Journals tab");
    openModal("Unbalanced Journals — Details", html);
    bindDrillGo("aidDrillGoUnbalanced", "unbalanced");
  }

  function drillMissingMappings() {
    if (!requirePayload("Missing Mappings")) return;
    const block = lastPayload.account_mappings || {};
    const rows = block.rows || [];
    const count = Number(lastPayload.summary?.missing_account_mappings) || rows.length;
    let html = `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Missing mappings</span><strong>${fmt(count, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">Master records (items, customers, suppliers) missing required GL account fields.</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Records with missing account mappings</h4>";
    html += tableHtml(
      [
        { key: "entity", label: "Entity" },
        { key: "code", label: "Code" },
        { key: "name", label: "Name" },
        { key: "missing_field", label: "Missing Field" },
        { key: "status", label: "Status", badge: true },
      ],
      rows.slice(0, 100)
    );
    html += drillActionsHtml("aidDrillGoMapping", "Open Account Mapping tab");
    openModal("Missing Mappings — Details", html);
    bindDrillGo("aidDrillGoMapping", "mapping");
  }

  function drillNegativeStock() {
    if (!requirePayload("Negative Stock")) return;
    const block = lastPayload.negative_stock || {};
    const rows = block.rows || [];
    const count = Number(lastPayload.summary?.negative_stock_count) || rows.length;
    let html = `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Negative stock items</span><strong>${fmt(count, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">Items with on-hand quantity below zero — may indicate posting or count errors.</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Items with negative stock</h4>";
    html += tableHtml(
      [
        { key: "item_code", label: "Item" },
        { key: "item_name", label: "Name" },
        { key: "warehouse", label: "Warehouse" },
        { key: "current_stock", label: "Stock", num: 3 },
        { key: "average_cost", label: "Avg Cost", num: 4 },
        { key: "stock_value", label: "Value", num: 2 },
        { key: "status", label: "Status", badge: true },
      ],
      rows.slice(0, 100)
    );
    html += drillActionsHtml("aidDrillGoNegative", "Open Negative Stock tab");
    openModal("Negative Stock — Details", html);
    bindDrillGo("aidDrillGoNegative", "negative");
  }

  function drillCriticalErrors() {
    if (!requirePayload("Critical Errors")) return;
    const s = lastPayload.summary || {};
    const failed = Number(s.failed_postings) || 0;
    const unbalanced = Number(s.unbalanced_journals) || 0;
    const negative = Number(s.negative_stock_count) || 0;
    const total = Number(s.critical_errors) || failed + unbalanced + negative;
    let html = `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Critical errors (total)</span><strong>${fmt(total, 0)}</strong></div>
        <div class="aid-recon-summary__item"><span>Failed postings</span><strong>${fmt(failed, 0)}</strong></div>
        <div class="aid-recon-summary__item"><span>Unbalanced journals</span><strong>${fmt(unbalanced, 0)}</strong></div>
        <div class="aid-recon-summary__item"><span>Negative stock</span><strong>${fmt(negative, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">Critical errors = failed postings + unbalanced journals + negative stock items.</p>`;

    if (failed > 0) {
      html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Failed postings</h4>";
      html += tableHtml(POSTING_COLS, postingRows((r) => r.status !== "ok", 50));
    }
    if (unbalanced > 0) {
      html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Unbalanced journals</h4>";
      html += tableHtml(
        [
          { key: "journal_no", label: "Journal No" },
          { key: "date", label: "Date" },
          { key: "debit", label: "Debit", num: 2 },
          { key: "credit", label: "Credit", num: 2 },
          { key: "difference", label: "Difference", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        (lastPayload.unbalanced_journals?.rows || []).slice(0, 50)
      );
    }
    if (negative > 0) {
      html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Negative stock</h4>";
      html += tableHtml(
        [
          { key: "item_code", label: "Item" },
          { key: "item_name", label: "Name" },
          { key: "current_stock", label: "Stock", num: 3 },
          { key: "stock_value", label: "Value", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        (lastPayload.negative_stock?.rows || []).slice(0, 50)
      );
    }
    if (total === 0) {
      html += "<p>No critical errors in this audit run.</p>";
    }
    openModal("Critical Errors — Breakdown", html);
  }

  const KPI_DRILL_HANDLERS = {
    transactions: drillTransactionsChecked,
    successful: drillSuccessfulPostings,
    failed: drillFailedPostings,
    inventory: drillInventoryVariance,
    ar: drillArVariance,
    ap: drillApVariance,
    unbalanced: drillUnbalancedJournals,
    mappings: drillMissingMappings,
    negative: drillNegativeStock,
    critical: drillCriticalErrors,
  };

  function drillArVariance() {
    if (!lastPayload) {
      openModal("AR Variance", "<p>Run full audit first.</p>");
      return;
    }
    const block = lastPayload.customer_reconciliation || {};
    const sum = block.summary || {};
    const rows = (block.rows || []).slice().sort((a, b) => Math.abs(Number(b.ledger_balance) || 0) - Math.abs(Number(a.ledger_balance) || 0));
    const variance = Math.abs(Number(lastPayload.summary?.ar_variance) || 0);
    const acct = sum.ar_control_account || "1200";
    const ledger = Number(sum.customer_ledger_total) || 0;
    const control = Number(sum.ar_control_balance) || 0;
    const diff = Number(sum.control_difference) || 0;
    const statusText = variance <= 0.01
      ? "Balanced — customer sub-ledger matches AR control."
      : variance <= 100
        ? "Minor variance — review customer receivable mappings and unallocated receipts."
        : "Significant variance — investigate GL journals on AR control vs customer postings.";

    let html = customerReconSummaryHtml(sum);
    html += `<p><strong>AR variance (KPI):</strong> ${fmt(variance, 2)} &nbsp;|&nbsp; <strong>Status:</strong> ${esc(statusText)}</p>`;
    html += `<p class="aid-recon-note"><strong>Formula:</strong> Customer ledger total (${fmt(ledger, 2)}) − AR control ${esc(acct)} (${fmt(control, 2)}) = ${fmt(diff, 2)}</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Customers by receivable balance</h4>";
    html += tableHtml(
      [
        { key: "customer_code", label: "Code" },
        { key: "customer_name", label: "Customer" },
        { key: "ledger_balance", label: "Receivable", num: 2 },
        { key: "receivable_account", label: "Recv. Account" },
        { key: "balance_source", label: "Source" },
      ],
      rows.slice(0, 100).map((r) => ({
        customer_code: r.customer_code,
        customer_name: r.customer_name,
        ledger_balance: r.ledger_balance,
        receivable_account: r.receivable_account,
        balance_source: r.balance_source || "",
      }))
    );
    html += drillActionsHtml("aidDrillGoCustomer", "Open Customer Recon tab");
    openModal("AR Variance — Details", html);
    bindDrillGo("aidDrillGoCustomer", "customer");
  }

  function supplierReconSummaryHtml(sum) {
    if (!sum || sum.supplier_ledger_total == null) return "";
    const acct = sum.ap_control_account || "2110";
    const diff = Number(sum.control_difference) || 0;
    return `
      <div class="aid-recon-summary">
        <div class="aid-recon-summary__item"><span>Supplier ledger total</span><strong>${fmt(sum.supplier_ledger_total, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>AP control (${esc(acct)})</span><strong>${fmt(sum.ap_control_balance, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Control difference</span><strong>${fmt(diff, 2)}</strong></div>
        <div class="aid-recon-summary__item"><span>Suppliers checked</span><strong>${fmt(sum.supplier_count, 0)}</strong></div>
      </div>
      <p class="aid-recon-note">AP variance is the absolute control difference: supplier outstanding total vs GL AP control account for the selected date range.</p>`;
  }

  function drillApVariance() {
    if (!lastPayload) {
      openModal("AP Variance", "<p>Run full audit first.</p>");
      return;
    }
    const block = lastPayload.supplier_reconciliation || {};
    const sum = block.summary || {};
    const rows = (block.rows || []).slice().sort((a, b) => Math.abs(Number(b.ledger_balance) || 0) - Math.abs(Number(a.ledger_balance) || 0));
    const variance = Math.abs(Number(lastPayload.summary?.ap_variance) || 0);
    const acct = sum.ap_control_account || "2110";
    const ledger = Number(sum.supplier_ledger_total) || 0;
    const control = Number(sum.ap_control_balance) || 0;
    const diff = Number(sum.control_difference) || 0;
    const statusText = variance <= 0.01
      ? "Balanced — supplier sub-ledger matches AP control."
      : variance <= 100
        ? "Minor variance — review supplier payable mappings and unallocated payments."
        : "Significant variance — investigate GL journals on AP control vs supplier postings.";

    let html = supplierReconSummaryHtml(sum);
    html += `<p><strong>AP variance (KPI):</strong> ${fmt(variance, 2)} &nbsp;|&nbsp; <strong>Status:</strong> ${esc(statusText)}</p>`;
    html += `<p class="aid-recon-note"><strong>Formula:</strong> Supplier ledger total (${fmt(ledger, 2)}) − AP control ${esc(acct)} (${fmt(control, 2)}) = ${fmt(diff, 2)}</p>`;
    html += "<h4 style='margin:14px 0 8px;font-size:0.85rem;'>Suppliers by payable balance</h4>";
    html += tableHtml(
      [
        { key: "supplier_code", label: "Code" },
        { key: "supplier_name", label: "Supplier" },
        { key: "ledger_balance", label: "Payable", num: 2 },
        { key: "payable_account", label: "Pay. Account" },
        { key: "balance_source", label: "Source" },
      ],
      rows.slice(0, 100).map((r) => ({
        supplier_code: r.supplier_code,
        supplier_name: r.supplier_name,
        ledger_balance: r.ledger_balance,
        payable_account: r.payable_account,
        balance_source: r.balance_source || "",
      }))
    );
    html += drillActionsHtml("aidDrillGoSupplier", "Open Supplier Recon tab");
    openModal("AP Variance — Details", html);
    bindDrillGo("aidDrillGoSupplier", "supplier");
  }

  function renderInsights(list) {
    if (!insightsEl) return;
    if (!list || !list.length) {
      insightsEl.innerHTML = "<p class='aid-loading'>No insights.</p>";
      return;
    }
    insightsEl.innerHTML = list
      .map((i) => {
        const sev = (i.severity || "info").toLowerCase();
        const cls = sev === "high" ? "aid-insight--high" : sev === "medium" ? "aid-insight--medium" : "aid-insight--info";
        return `<div class="aid-insight ${cls}"><strong>${esc(i.title)}</strong>${esc(i.message)}</div>`;
      })
      .join("");
  }

  function tableHtml(cols, rows, rowClickAttr) {
    if (!rows.length) return "<p style='font-size:0.75rem;color:#6c757d'>No rows.</p>";
    const head = cols.map((c) => `<th>${esc(c.label)}</th>`).join("");
    const body = rows
      .map((row, idx) => {
        const attrs = rowClickAttr ? ` class="aid-row-click" data-${rowClickAttr}="${esc(row[rowClickAttr] || "")}"` : "";
        const cells = cols
          .map((c) => {
            let v = row[c.key];
            if (c.badge) return `<td>${badge(v)}</td>`;
            if (c.num) return `<td class="num">${fmt(v, c.num)}</td>`;
            return `<td>${esc(v ?? "")}</td>`;
          })
          .join("");
        return `<tr${attrs}>${cells}</tr>`;
      })
      .join("");
    return `<div class="aid-table-scroll"><table class="aid-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function buildSectionContent(id, payload) {
    const sec = SECTIONS.find((s) => s.id === id);
    if (!sec) return "";
    const block = payload[sec.key] || {};
    const rows = block.rows || [];

    if (id === "posting") {
      return tableHtml(
        [
          { key: "document_no", label: "Document No" },
          { key: "document_date", label: "Date" },
          { key: "module", label: "Module" },
          { key: "expected_entries", label: "Expected", num: 0 },
          { key: "actual_entries", label: "Actual", num: 0 },
          { key: "status", label: "Status", badge: true },
          { key: "status_note", label: "Note" },
        ],
        rows.filter((r) => r.status !== "ok").slice(0, 200).concat(rows.filter((r) => r.status === "ok").slice(0, 50))
      );
    }
    if (id === "stock_gl") {
      const sum = block.summary || {};
      return (
        stockGlSummaryHtml(sum) +
        `<p class="aid-recon-note">Click a warehouse row to see item-level variance breakdown.</p>` +
        stockGlTableHtml(
          [
            { key: "warehouse", label: "Warehouse" },
            { key: "stock_value", label: "Stock Value", num: 2 },
            { key: "gl_balance", label: "GL Balance", num: 2 },
            { key: "difference", label: "Difference", num: 2 },
            { key: "balance_source", label: "Source" },
            { key: "status", label: "Status", badge: true },
          ],
          rows
        )
      );
    }
    if (id === "customer") {
      const sum = block.summary || {};
      return (
        customerReconSummaryHtml(sum) +
        tableHtml(
          [
            { key: "customer_code", label: "Code" },
            { key: "customer_name", label: "Customer" },
            { key: "ledger_balance", label: "Ledger Bal", num: 2 },
            { key: "ar_balance", label: "AR Bal", num: 2 },
            { key: "difference", label: "Diff", num: 2 },
            { key: "status", label: "Status", badge: true },
          ],
          rows.slice(0, 200)
        )
      );
    }
    if (id === "supplier") {
      const sum = block.summary || {};
      return (
        supplierReconSummaryHtml(sum) +
        tableHtml(
          [
            { key: "supplier_code", label: "Code" },
            { key: "supplier_name", label: "Supplier" },
            { key: "ledger_balance", label: "Ledger Bal", num: 2 },
            { key: "ap_balance", label: "AP Bal", num: 2 },
            { key: "difference", label: "Diff", num: 2 },
            { key: "balance_source", label: "Source" },
            { key: "status", label: "Status", badge: true },
          ],
          rows.slice(0, 200)
        )
      );
    }
    if (id === "unbalanced") {
      return tableHtml(
        [
          { key: "journal_no", label: "Journal No" },
          { key: "date", label: "Date" },
          { key: "debit", label: "Debit", num: 2 },
          { key: "credit", label: "Credit", num: 2 },
          { key: "difference", label: "Difference", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        rows,
        "journal_no"
      );
    }
    if (id === "negative") {
      return tableHtml(
        [
          { key: "item_code", label: "Item" },
          { key: "item_name", label: "Name" },
          { key: "warehouse", label: "Warehouse" },
          { key: "current_stock", label: "Stock", num: 3 },
          { key: "average_cost", label: "Avg Cost", num: 4 },
          { key: "stock_value", label: "Value", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        rows,
        "item_code"
      );
    }
    if (id === "cost") {
      return tableHtml(
        [
          { key: "item_code", label: "Item" },
          { key: "item_name", label: "Name" },
          { key: "average_cost", label: "Avg Cost", num: 4 },
          { key: "last_purchase_cost", label: "Last Cost", num: 4 },
          { key: "current_stock", label: "Stock", num: 3 },
          { key: "inventory_value", label: "Inv Value", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        rows.filter((r) => r.status !== "ok").slice(0, 150)
      );
    }
    if (id === "mapping") {
      return tableHtml(
        [
          { key: "entity", label: "Entity" },
          { key: "code", label: "Code" },
          { key: "name", label: "Name" },
          { key: "missing_field", label: "Missing Field" },
          { key: "status", label: "Status", badge: true },
        ],
        rows
      );
    }
    if (id === "tax") {
      return tableHtml(
        [
          { key: "tax_type", label: "Tax Type" },
          { key: "account", label: "Account" },
          { key: "gl_balance", label: "GL Balance", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        rows
      );
    }
    if (id === "cash") {
      return tableHtml(
        [
          { key: "account_name", label: "Account" },
          { key: "account_code", label: "Code" },
          { key: "book_balance", label: "Book", num: 2 },
          { key: "gl_balance", label: "GL", num: 2 },
          { key: "difference", label: "Diff", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        rows
      );
    }
    if (id === "pl") {
      return tableHtml(
        [
          { key: "line", label: "Line" },
          { key: "amount", label: "Amount", num: 2 },
          { key: "status", label: "Status", badge: true },
        ],
        rows
      );
    }
    if (id === "movement") {
      return tableHtml(
        [
          { key: "item_code", label: "Item" },
          { key: "item_name", label: "Name" },
          { key: "purchases", label: "Purchases", num: 3 },
          { key: "sales", label: "Sales", num: 3 },
          { key: "returns", label: "Returns", num: 3 },
          { key: "adjustments", label: "Adjust", num: 3 },
          { key: "closing_stock", label: "Net Mov", num: 3 },
        ],
        rows,
        "item_code"
      );
    }
    return "";
  }

  function renderSections(payload) {
    if (!sectionTabs || !sectionsHost) return;
    sectionTabs.innerHTML = SECTIONS.map(
      (s) =>
        `<button type="button" class="aid-section-tab${s.id === activeSection ? " is-active" : ""}" data-section="${s.id}">${s.label}</button>`
    ).join("");

    let html = "";
    SECTIONS.forEach((s) => {
      html += `<div class="aid-section${s.id === activeSection ? " is-active" : ""}" id="aidSec_${s.id}" data-section="${s.id}">${buildSectionContent(s.id, payload)}</div>`;
    });
    sectionsHost.innerHTML = html;

    sectionTabs.querySelectorAll(".aid-section-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeSection = btn.dataset.section;
        renderSections(payload);
      });
    });

    bindRowClicks();
  }

  async function drillJournal(vno) {
    const p = queryParams();
    p.set("voucher_no", vno);
    openModal("Journal " + vno, "<p class='aid-loading'>Loading…</p>");
    try {
      const res = await fetch(journalUrl + "?" + p.toString());
      const data = await res.json();
      if (!data.success && data.error) {
        drillBody.innerHTML = "<p>" + esc(data.error) + "</p>";
        return;
      }
      const lines = (data.gl && data.gl.lines) || data.lines || [];
      let html = tableHtml(
        [
          { key: "line_no", label: "Line", num: 0 },
          { key: "account_code", label: "Account" },
          { key: "debit", label: "Debit", num: 2 },
          { key: "credit", label: "Credit", num: 2 },
          { key: "remarks", label: "Remarks" },
        ],
        lines.map((l) => ({
          line_no: l.line_no || l.LINE_NO,
          account_code: l.account_code || l.ACCOUNT_CODE,
          debit: l.debit || l.DEBIT,
          credit: l.credit || l.CREDIT,
          remarks: l.remarks || l.REMARKS,
        }))
      );
      if (data.issues && data.issues.length) {
        html += "<h4 style='margin-top:12px'>Issues</h4><ul>" + data.issues.map((i) => `<li>${esc(i.message)}</li>`).join("") + "</ul>";
      }
      drillBody.innerHTML = html;
    } catch (e) {
      drillBody.innerHTML = "<p>Failed to load journal.</p>";
    }
  }

  async function drillMovement(itemCode) {
    const p = queryParams();
    p.set("item_code", itemCode);
    openModal("Movement — Item " + itemCode, "<p class='aid-loading'>Loading…</p>");
    try {
      const res = await fetch(movementUrl + "?" + p.toString());
      const data = await res.json();
      drillBody.innerHTML = tableHtml(
        [
          { key: "dt", label: "Date" },
          { key: "trans_type", label: "Type" },
          { key: "reference_no", label: "Reference" },
          { key: "qty", label: "Qty", num: 3 },
        ],
        data.rows || []
      );
    } catch (e) {
      drillBody.innerHTML = "<p>Failed to load movement.</p>";
    }
  }

  function bindRowClicksIn(root) {
    const host = root || sectionsHost;
    host?.querySelectorAll("tr.aid-row-click").forEach((tr) => {
      if (tr.classList.contains("aid-stock-gl-row")) return;
      tr.style.cursor = "pointer";
      tr.addEventListener("click", () => {
        const j = tr.dataset.journal_no;
        const ic = tr.dataset.item_code;
        if (j) {
          drillJournal(j);
          if (detailPanel) detailPanel.innerHTML = "<p>Journal <strong>" + esc(j) + "</strong> — see modal for lines.</p>";
        } else if (ic) {
          drillMovement(ic);
          if (detailPanel) detailPanel.innerHTML = "<p>Item <strong>" + esc(ic) + "</strong> movement history.</p>";
        }
      });
    });
    bindStockGlDrillRows(host);
  }

  function bindRowClicks() {
    bindRowClicksIn(sectionsHost);
  }

  async function runAudit() {
    showError("");
    if (statusEl) statusEl.textContent = "Running audit…";
    sectionsHost.innerHTML = "<div class='aid-loading'>Running full integrity audit…</div>";
    if (typeof window.showLoadingOverlay === "function") {
      window.showLoadingOverlay("Running full integrity audit…");
    }
    const runBtn = document.getElementById("aidBtnRun");
    const refreshBtn = document.getElementById("aidBtnRefresh");
    if (runBtn) runBtn.disabled = true;
    if (refreshBtn) refreshBtn.disabled = true;
    syncExportLinks();
    const q = queryParams().toString();
    try {
      const res = await fetch(apiUrl + (q ? "?" + q : ""));
      const data = await res.json();
      if (!data.success) {
        showError(data.error || "Audit failed.");
        if (statusEl) statusEl.textContent = "Failed";
        return;
      }
      lastPayload = data;
      renderKpis(data.summary || {});
      renderInsights(data.insights || []);
      renderSections(data);
      if (statusEl) statusEl.textContent = "Updated " + new Date().toLocaleTimeString();
      if (detailPanel) {
        const s = data.summary || {};
        detailPanel.innerHTML =
          "<p>Audit completed at <strong>" +
          esc(data.generated_at || "") +
          "</strong>. " +
          fmt(s.critical_errors, 0) +
          " critical issue(s). Use section tabs for reconciliation tables; click rows for drill-down.</p>";
      }
    } catch (e) {
      showError("Network error running audit.");
      if (statusEl) statusEl.textContent = "Error";
    } finally {
      if (typeof window.hideLoadingOverlay === "function") {
        window.hideLoadingOverlay();
      }
      if (runBtn) runBtn.disabled = false;
      if (refreshBtn) refreshBtn.disabled = false;
    }
  }

  document.getElementById("aidBtnRun")?.addEventListener("click", runAudit);
  document.getElementById("aidBtnRefresh")?.addEventListener("click", runAudit);
  document.getElementById("aidBtnPrint")?.addEventListener("click", () => window.print());
  document.getElementById("aidBtnEmail")?.addEventListener("click", () => {
    const sub = encodeURIComponent("Integrity Audit Report");
    const body = encodeURIComponent("Please find the integrity audit export attached or run from ERP.");
    window.location.href = "mailto:?subject=" + sub + "&body=" + body;
  });
  document.getElementById("aidBtnAi")?.addEventListener("click", () => {
    if (!lastPayload) runAudit();
    else {
      renderInsights(lastPayload.insights || []);
      insightsEl?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
  form?.addEventListener("change", syncExportLinks);

  kpiGrid?.addEventListener("click", (e) => {
    const card = e.target.closest("[data-kpi-drill]");
    if (!card) return;
    const drill = card.dataset.kpiDrill;
    const handler = KPI_DRILL_HANDLERS[drill];
    if (handler) handler();
  });

  syncExportLinks();
  runAudit();
})();
