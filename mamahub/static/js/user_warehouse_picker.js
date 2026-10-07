/**
 * Shared warehouse pickers on Users create / edit forms.
 * Expects window.USER_WAREHOUSES_API and optional tenant_id input (#tenant_id).
 */
(function () {
  const WH_FIELDS = [
    { kind: "sales", displayId: "defaultWhSalesDisplay", hiddenId: "default_wh_sales", clearId: "defaultWhSalesClear", pickerId: "defaultWhSalesPicker", label: "Sales" },
    { kind: "sales_return", displayId: "defaultWhSalesReturnDisplay", hiddenId: "default_wh_sales_return", clearId: "defaultWhSalesReturnClear", pickerId: "defaultWhSalesReturnPicker", label: "Sales return" },
    { kind: "purchase", displayId: "defaultWhPurchaseDisplay", hiddenId: "default_wh_purchase", clearId: "defaultWhPurchaseClear", pickerId: "defaultWhPurchasePicker", label: "Purchase / GRN" },
    { kind: "purchase_return", displayId: "defaultWhPurchaseReturnDisplay", hiddenId: "default_wh_purchase_return", clearId: "defaultWhPurchaseReturnClear", pickerId: "defaultWhPurchaseReturnPicker", label: "Purchase return" },
  ];

  function whApiBase() {
    return typeof window.USER_WAREHOUSES_API === "string" ? window.USER_WAREHOUSES_API.trim() : "";
  }

  function tenantIdValue() {
    const el = document.getElementById("tenant_id");
    return el ? String(el.value || "").trim() : "";
  }

  function formatWhDisplay(code, name) {
    const c = String(code || "").trim();
    const n = String(name || "").trim();
    if (c && n) return `${c} — ${n}`;
    return c || n || "";
  }

  function setWhField(field, id, code, name) {
    const display = document.getElementById(field.displayId);
    const hidden = document.getElementById(field.hiddenId);
    const clearBtn = document.getElementById(field.clearId);
    if (hidden) hidden.value = id ? String(id) : "";
    if (display) display.value = id ? formatWhDisplay(code, name) : "";
    if (clearBtn) clearBtn.style.display = id ? "block" : "none";
  }

  function clearWhField(field) {
    setWhField(field, "", "", "");
  }

  let activeField = null;
  let whCacheKey = "";
  let whRows = [];
  let whLoading = false;
  let whSearchTimer = null;
  let whFetchAbort = null;

  function renderWhModalRows(rows) {
    const tb = document.querySelector("#userWhModalTable tbody");
    if (!tb) return;
    if (!rows || !rows.length) {
      tb.innerHTML = '<tr><td colspan="2" class="muted" style="text-align:center;padding:12px;">No warehouses found. Select a tenant first, or try another search.</td></tr>';
      return;
    }
    tb.innerHTML = rows
      .map((w) => {
        const id = w.code != null ? String(w.code) : "";
        const code = w.warehouse_code != null ? String(w.warehouse_code) : id;
        const name = w.name != null ? String(w.name) : "";
        return `<tr data-id="${id.replace(/"/g, "&quot;")}" data-code="${code.replace(/"/g, "&quot;")}" data-name="${name.replace(/"/g, "&quot;")}"><td>${code || id}</td><td>${name || "—"}</td></tr>`;
      })
      .join("");
  }

  function loadWarehouses(search, force) {
    const api = whApiBase();
    const tb = document.querySelector("#userWhModalTable tbody");
    if (!api || !tb) return Promise.resolve();
    const tid = tenantIdValue();
    const key = `${tid}|${String(search || "").trim().toLowerCase()}`;
    if (!force && key === whCacheKey && whRows.length) {
      renderWhModalRows(whRows);
      return Promise.resolve();
    }
    if (whFetchAbort) whFetchAbort.abort();
    whFetchAbort = new AbortController();
    whLoading = true;
    tb.innerHTML = '<tr><td colspan="2" class="muted" style="text-align:center;padding:12px;">Loading…</td></tr>';
    const u = `${api}?tenant_id=${encodeURIComponent(tid)}&q=${encodeURIComponent(search || "")}&limit=500`;
    return fetch(u, { credentials: "same-origin", signal: whFetchAbort.signal })
      .then((r) => r.json())
      .then((data) => {
        whLoading = false;
        if (!data || !data.success) throw new Error((data && data.error) || "Load failed");
        whRows = Array.isArray(data.warehouses) ? data.warehouses : [];
        whCacheKey = key;
        renderWhModalRows(whRows);
      })
      .catch((err) => {
        whLoading = false;
        if (err && err.name === "AbortError") return;
        tb.innerHTML = `<tr><td colspan="2" class="muted" style="text-align:center;padding:12px;">${String(err.message || err)}</td></tr>`;
      });
  }

  function openWhModal(field) {
    activeField = field;
    const modal = document.getElementById("userWhModal");
    const search = document.getElementById("userWhModalSearch");
    if (search) search.value = "";
    if (modal) modal.classList.remove("hidden");
    loadWarehouses("", true);
    if (search) window.setTimeout(() => search.focus(), 50);
  }

  function closeWhModal() {
    const modal = document.getElementById("userWhModal");
    if (modal) modal.classList.add("hidden");
    activeField = null;
  }

  function bindWhModal() {
    const modal = document.getElementById("userWhModal");
    if (!modal) return;
    modal.querySelectorAll("[data-close='userWhModal']").forEach((el) => {
      el.addEventListener("click", closeWhModal);
    });
    const search = document.getElementById("userWhModalSearch");
    const clear = document.getElementById("userWhModalClear");
    if (search) {
      search.addEventListener("input", () => {
        window.clearTimeout(whSearchTimer);
        whSearchTimer = window.setTimeout(() => loadWarehouses(search.value, true), 280);
      });
    }
    if (clear) {
      clear.addEventListener("click", () => {
        if (search) search.value = "";
        loadWarehouses("", true);
      });
    }
    const table = document.getElementById("userWhModalTable");
    if (table) {
      table.addEventListener("click", (e) => {
        const row = e.target.closest("tbody tr[data-id]");
        if (!row || !activeField) return;
        setWhField(activeField, row.dataset.id || "", row.dataset.code || "", row.dataset.name || "");
        closeWhModal();
      });
    }
  }

  function bindField(field) {
    const picker = document.getElementById(field.pickerId);
    const display = document.getElementById(field.displayId);
    const clearBtn = document.getElementById(field.clearId);
    if (picker) picker.addEventListener("click", () => openWhModal(field));
    if (display) {
      display.addEventListener("keydown", (e) => {
        if (e.key === "F1") {
          e.preventDefault();
          openWhModal(field);
        }
      });
    }
    if (clearBtn) clearBtn.addEventListener("click", () => clearWhField(field));
  }

  function invalidateWarehouseCache() {
    whCacheKey = "";
    whRows = [];
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!whApiBase()) return;
    WH_FIELDS.forEach(bindField);
    bindWhModal();
    const tenantId = document.getElementById("tenant_id");
    if (tenantId) tenantId.addEventListener("change", invalidateWarehouseCache);
    const tenantTable = document.getElementById("tenantModalTable");
    if (tenantTable) {
      tenantTable.addEventListener("click", () => window.setTimeout(invalidateWarehouseCache, 0));
    }
  });
})();
