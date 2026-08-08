document.addEventListener("DOMContentLoaded", () => {
  const locationDisplay = document.getElementById("locationDisplay");

  const tenantIdInput = document.getElementById("tenant_id");
  const tenantDisplay = document.getElementById("tenantDisplay");
  const tenantPicker = document.getElementById("tenantPicker");
  const tenantClear = document.getElementById("tenantClear");
  const tenantModal = document.getElementById("tenantModal");
  const tenantModalSearch = document.getElementById("tenantModalSearch");
  const tenantModalClear = document.getElementById("tenantModalClear");
  const tenantModalTable = document.getElementById("tenantModalTable");
  const multilocSelect = document.getElementById("multilocations_view");
  const allowedTenantsWrap = document.getElementById("allowedTenantsWrap");
  const allowedTenantsChips = document.getElementById("allowedTenantsChips");
  const allowedTenantIdsInput = document.getElementById("allowed_tenant_ids");
  const allowedTenantsAddBtn = document.getElementById("allowedTenantsAddBtn");
  const multiTenantPickModal = document.getElementById("multiTenantPickModal");
  const multiTenantPickTable = document.getElementById("multiTenantPickTable");
  const multiTenantPickSearch = document.getElementById("multiTenantPickSearch");
  const multiTenantPickClear = document.getElementById("multiTenantPickClear");
  const roleIdInput = document.getElementById("role_id");
  const roleDisplay = document.getElementById("roleDisplay");
  const rolePicker = document.getElementById("rolePicker");
  const roleClear = document.getElementById("roleClear");
  const roleModal = document.getElementById("roleModal");
  const roleModalSearch = document.getElementById("roleModalSearch");
  const roleModalClear = document.getElementById("roleModalClear");
  const roleModalTable = document.getElementById("roleModalTable");

  function syncMultilocLocationExtras() {
    if (!allowedTenantsWrap) return;
    const on = multilocSelect && String(multilocSelect.value || "").toUpperCase() === "Y";
    allowedTenantsWrap.classList.toggle("hidden", !on);
  }
  if (multilocSelect) {
    multilocSelect.addEventListener("change", syncMultilocLocationExtras);
    syncMultilocLocationExtras();
  }

  const tenantDisplayByIdLower = {};
  document.querySelectorAll("#multiTenantPickTable tbody tr.tenant-pick-multi-row").forEach((row) => {
    const tid = (row.dataset.tenantId || "").trim();
    if (!tid) return;
    tenantDisplayByIdLower[tid.toLowerCase()] = { canon: tid, name: String(row.dataset.displayName || tid).trim() };
  });

  let allowedOrder = [];

  function allowedKeySet() {
    return new Set(allowedOrder.map((t) => t.toLowerCase()));
  }

  function syncAllowedHidden() {
    if (allowedTenantIdsInput) allowedTenantIdsInput.value = allowedOrder.join(",");
  }

  function refreshAllowedPickRows() {
    const sel = allowedKeySet();
    if (!multiTenantPickTable) return;
    multiTenantPickTable.querySelectorAll("tbody tr.tenant-pick-multi-row").forEach((row) => {
      const tid = (row.dataset.tenantId || "").trim();
      row.classList.toggle("is-selected", tid ? sel.has(tid.toLowerCase()) : false);
    });
  }

  function renderAllowedChips() {
    if (!allowedTenantsChips) return;
    allowedTenantsChips.innerHTML = "";
    allowedOrder.forEach((tid) => {
      const lk = tid.toLowerCase();
      const meta = tenantDisplayByIdLower[lk];
      const name = meta ? meta.name : tid;
      const chip = document.createElement("span");
      chip.className = "allowed-tenant-chip";
      const codeEl = document.createElement("code");
      codeEl.textContent = tid;
      const lbl = document.createElement("span");
      lbl.textContent = " — " + name;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.setAttribute("aria-label", "Remove " + tid);
      rm.textContent = "×";
      rm.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        allowedOrder = allowedOrder.filter((x) => x.toLowerCase() !== lk);
        renderAllowedChips();
      });
      chip.appendChild(codeEl);
      chip.appendChild(lbl);
      chip.appendChild(rm);
      allowedTenantsChips.appendChild(chip);
    });
    syncAllowedHidden();
    refreshAllowedPickRows();
  }

  function initialAllowedFromInput() {
    const raw = allowedTenantIdsInput ? String(allowedTenantIdsInput.value || "").trim() : "";
    if (!raw) return;
    allowedOrder = [];
    raw.split(",").forEach((part) => {
      const s = part.trim();
      if (!s) return;
      const m = tenantDisplayByIdLower[s.toLowerCase()];
      const canon = m ? m.canon : s;
      if (!allowedKeySet().has(canon.toLowerCase())) allowedOrder.push(canon);
    });
    renderAllowedChips();
  }
  initialAllowedFromInput();

  function filterMultiTenantPickRows(q) {
    if (!multiTenantPickTable) return;
    const tokens = (q || "").toLowerCase().split(/\s+/).filter(Boolean);
    multiTenantPickTable.querySelectorAll("tbody tr.tenant-pick-multi-row").forEach((row) => {
      const text = (row.textContent || "").toLowerCase();
      const matches = tokens.every((token) => text.includes(token));
      row.style.display = matches ? "" : "none";
    });
  }

  function openMultiTenantPick() {
    if (!multiTenantPickModal) return;
    multiTenantPickModal.classList.remove("hidden");
    if (multiTenantPickSearch) {
      multiTenantPickSearch.value = "";
      filterMultiTenantPickRows("");
      setTimeout(() => multiTenantPickSearch.focus(), 80);
    }
    refreshAllowedPickRows();
  }

  function closeMultiTenantPick() {
    if (multiTenantPickModal) multiTenantPickModal.classList.add("hidden");
  }

  if (allowedTenantsAddBtn) {
    allowedTenantsAddBtn.addEventListener("click", (e) => {
      e.preventDefault();
      openMultiTenantPick();
    });
  }

  if (multiTenantPickModal) {
    multiTenantPickModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target && (target.dataset.close === "multiTenantPickModal" || target.classList.contains("modal__close"))) {
        event.preventDefault();
        closeMultiTenantPick();
      }
    });
  }

  if (multiTenantPickSearch) {
    multiTenantPickSearch.addEventListener("input", (event) => {
      filterMultiTenantPickRows(event.target.value || "");
    });
  }

  if (multiTenantPickClear) {
    multiTenantPickClear.addEventListener("click", (e) => {
      e.preventDefault();
      if (multiTenantPickSearch) {
        multiTenantPickSearch.value = "";
        filterMultiTenantPickRows("");
        multiTenantPickSearch.focus();
      }
    });
  }

  if (multiTenantPickTable) {
    multiTenantPickTable.addEventListener("click", (event) => {
      const row = event.target.closest("tr.tenant-pick-multi-row");
      if (!row) return;
      event.preventDefault();
      const tid = (row.dataset.tenantId || "").trim();
      if (!tid) return;
      const lk = tid.toLowerCase();
      if (allowedKeySet().has(lk)) return;
      const m = tenantDisplayByIdLower[lk];
      allowedOrder.push(m ? m.canon : tid);
      renderAllowedChips();
    });
  }

  const filterTenantRows = (query) => {
    if (!tenantModalTable) return;
    const tokens = query.split(/\s+/).filter(Boolean);
    const rows = tenantModalTable.querySelectorAll("tbody tr");
    rows.forEach((row) => {
      const text = (row.textContent || "").toLowerCase();
      const matches = tokens.every((token) => text.includes(token));
      row.style.display = matches ? "" : "none";
    });
  };

  const openTenantModal = () => {
    if (!tenantModal) return;
    tenantModal.classList.remove("hidden");
    if (tenantModalSearch) {
      tenantModalSearch.value = "";
      filterTenantRows("");
      tenantModalSearch.focus();
    }
  };

  const closeTenantModal = () => {
    if (!tenantModal) return;
    tenantModal.classList.add("hidden");
  };

  const openRoleModal = () => {
    if (!roleModal) return;
    roleModal.classList.remove("hidden");
    if (roleModalSearch) {
      roleModalSearch.value = "";
      filterRoleRows("");
      roleModalSearch.focus();
    }
  };

  const closeRoleModal = () => {
    if (!roleModal) return;
    roleModal.classList.add("hidden");
  };

  const filterRoleRows = (query) => {
    if (!roleModalTable) return;
    const tokens = query.split(/\s+/).filter(Boolean);
    const rows = roleModalTable.querySelectorAll("tbody tr");
    rows.forEach((row) => {
      const text = (row.textContent || "").toLowerCase();
      const matches = tokens.every((token) => text.includes(token));
      row.style.display = matches ? "" : "none";
    });
  };

  if (tenantPicker) {
    tenantPicker.addEventListener("click", openTenantModal);
  }
  if (tenantDisplay) {
    tenantDisplay.addEventListener("click", openTenantModal);
  }
  if (tenantModal) {
    tenantModal.addEventListener("click", (event) => {
      const target = event.target;
      if (
        target &&
        ((target.dataset && target.dataset.close === "tenantModal") || target.classList.contains("modal__close"))
      ) {
        closeTenantModal();
      }
    });
  }
  if (tenantModalSearch) {
    tenantModalSearch.addEventListener("input", (event) => {
      filterTenantRows(event.target.value.toLowerCase());
    });
  }
  if (tenantModalClear) {
    tenantModalClear.addEventListener("click", () => {
      if (tenantModalSearch) {
        tenantModalSearch.value = "";
        filterTenantRows("");
        tenantModalSearch.focus();
      }
    });
  }
  if (tenantModalTable) {
    tenantModalTable.addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      if (!row || !row.hasAttribute("data-tenant-id")) return;
      event.preventDefault();
      event.stopPropagation();
      const tenantIdVal = row.getAttribute("data-tenant-id") || "";
      const tenantDisplayVal =
        row.dataset.tenantDisplay !== undefined ? row.dataset.tenantDisplay : "";
      if (tenantDisplay) {
        tenantDisplay.value = tenantDisplayVal;
      }
      if (tenantIdInput) {
        tenantIdInput.value = tenantIdVal;
      }
      if (tenantClear) {
        tenantClear.style.display = tenantIdVal || tenantDisplayVal ? "block" : "none";
      }
      if (!tenantIdVal) {
        if (locationDisplay) locationDisplay.value = "";
      } else {
        const locHint = row.getAttribute("data-location-code");
        if (locHint !== null && String(locHint).trim() !== "") {
          const code = String(locHint).trim();
          if (locationDisplay) locationDisplay.value = code;
        }
      }
      closeTenantModal();
    });
  }
  if (tenantClear) {
    tenantClear.addEventListener("click", () => {
      if (tenantDisplay) tenantDisplay.value = "";
      if (tenantIdInput) tenantIdInput.value = "";
      tenantClear.style.display = "none";
      if (locationDisplay) locationDisplay.value = "";
    });
  }

  if (rolePicker) {
    rolePicker.addEventListener("click", openRoleModal);
  }
  if (roleDisplay) {
    roleDisplay.addEventListener("click", openRoleModal);
  }
  if (roleModal) {
    roleModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target && target.dataset && target.dataset.close === "roleModal") {
        closeRoleModal();
      }
    });
  }
  if (roleModalSearch) {
    roleModalSearch.addEventListener("input", (event) => {
      filterRoleRows(event.target.value.toLowerCase());
    });
  }
  if (roleModalClear) {
    roleModalClear.addEventListener("click", () => {
      if (roleModalSearch) {
        roleModalSearch.value = "";
        filterRoleRows("");
        roleModalSearch.focus();
      }
    });
  }
  if (roleModalTable) {
    roleModalTable.addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      if (!row) return;
      const roleId = row.dataset.roleId !== undefined ? row.dataset.roleId : "";
      const roleDisplayVal = row.dataset.roleDisplay !== undefined ? row.dataset.roleDisplay : "";
      if (roleDisplay) {
        roleDisplay.value = roleDisplayVal;
      }
      if (roleIdInput) {
        roleIdInput.value = roleId;
      }
      if (roleClear) {
        roleClear.style.display = roleId ? "block" : "none";
      }
      closeRoleModal();
    });
  }
  if (roleClear) {
    roleClear.addEventListener("click", () => {
      if (roleDisplay) roleDisplay.value = "No role (full access)";
      if (roleIdInput) roleIdInput.value = "";
      roleClear.style.display = "none";
    });
  }
});
