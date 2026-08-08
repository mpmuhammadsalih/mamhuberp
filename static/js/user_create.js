document.addEventListener("DOMContentLoaded", () => {
  const userCreateForm = document.querySelector("form.user-create-form");
  const usernameInput = document.getElementById("username");
  const usernameHint = document.getElementById("usernameHint");
  const employeeCodeInput = document.getElementById("employeecode");
  const locationDisplay = document.getElementById("locationDisplay");
  const tenantId = document.getElementById("tenant_id");
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
  const roleId = document.getElementById("role_id");
  const roleDisplay = document.getElementById("roleDisplay");
  const rolePicker = document.getElementById("rolePicker");
  const roleClear = document.getElementById("roleClear");
  const roleModal = document.getElementById("roleModal");
  const roleModalSearch = document.getElementById("roleModalSearch");
  const roleModalClear = document.getElementById("roleModalClear");
  const roleModalTable = document.getElementById("roleModalTable");
  const employeeNameDisplay = document.getElementById("employeeNameDisplay");
  const employeePicker = document.getElementById("employeePicker");
  const employeeClear = document.getElementById("employeeClear");
  const employeeModal = document.getElementById("employeeModal");
  const employeeModalSearch = document.getElementById("employeeModalSearch");
  const employeeModalClear = document.getElementById("employeeModalClear");
  const employeeModalTable = document.getElementById("employeeModalTable");
  const employeeModalBody = document.getElementById("employeeModalBody");
  const employeeApiUrl = typeof window.USER_CREATE_EMPLOYEE_API === "string" ? window.USER_CREATE_EMPLOYEE_API : "";

  let employeeItemsCache = null;
  let employeeItemsLoading = false;

  // Username validation
  if (usernameInput && usernameHint) {
    let checkTimer;
    usernameInput.addEventListener("input", () => {
      const value = usernameInput.value.trim();
      usernameHint.style.display = "none";
      usernameHint.textContent = "";
      if (checkTimer) {
        window.clearTimeout(checkTimer);
      }
      if (!value) return;
      checkTimer = window.setTimeout(async () => {
        try {
          const response = await fetch(`/users/check-username?username=${encodeURIComponent(value)}`);
          if (!response.ok) return;
          const data = await response.json();
          if (data.exists) {
            usernameHint.textContent = "Username already exists.";
            usernameHint.style.display = "block";
            usernameHint.style.color = "#c0392b";
          }
        } catch (err) {
          // Ignore network errors for inline check
        }
      }, 300);
    });
  }

  // Save-level validation: Employee Code is mandatory for user creation.
  if (userCreateForm && employeeCodeInput) {
    userCreateForm.addEventListener("submit", (event) => {
      const rawCode = String(employeeCodeInput.value || "").trim();
      employeeCodeInput.value = rawCode;
      if (!rawCode) {
        event.preventDefault();
        alert("Employee Code is required.");
        employeeCodeInput.focus();
        return;
      }
      if (rawCode.toUpperCase() !== "ADMIN" && !/^\d+$/.test(rawCode)) {
        event.preventDefault();
        alert("Employee Code must be numeric.");
        employeeCodeInput.focus();
      }
    });
  }

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

  function filterMultiTenantPickRows(q) {
    if (!multiTenantPickTable) return;
    const tokens = (q || "").toLowerCase().split(/\s+/).filter(Boolean);
    multiTenantPickTable.querySelectorAll("tbody tr.tenant-pick-multi-row").forEach((row) => {
      const text = (row.textContent || "").toLowerCase();
      const matches = tokens.every((token) => text.includes(token));
      row.style.display = matches ? "" : "none";
    });
  }

  if (allowedTenantsAddBtn) {
    allowedTenantsAddBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
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
      filterMultiTenantPickRows((event.target.value || "").toLowerCase());
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

  const closeTenantModal = () => {
    if (!tenantModal) return;
    tenantModal.classList.add("hidden");
  };

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
      setTimeout(() => tenantModalSearch.focus(), 100);
    }
  };

  if (tenantPicker) {
    tenantPicker.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openTenantModal();
    });
  }

  if (tenantDisplay) {
    tenantDisplay.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openTenantModal();
    });
  }

  if (tenantModal) {
    tenantModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target && (target.dataset.close === "tenantModal" || target.classList.contains("modal__close"))) {
        event.preventDefault();
        event.stopPropagation();
        closeTenantModal();
      }
    });
  }

  if (tenantModalSearch) {
    tenantModalSearch.addEventListener("input", (event) => {
      filterTenantRows((event.target.value || "").toLowerCase());
    });
  }

  if (tenantModalClear) {
    tenantModalClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (tenantModalSearch) {
        tenantModalSearch.value = "";
        filterTenantRows("");
        tenantModalSearch.focus();
      }
    });
  }

  if (tenantModalTable) {
    tenantModalTable.addEventListener("click", (event) => {
      const row = event.target.closest("tbody tr");
      if (!row || !row.hasAttribute || !row.hasAttribute("data-tenant-id")) return;
      event.preventDefault();
      event.stopPropagation();
      const selectedTenantId = row.getAttribute("data-tenant-id") || "";
      const selectedDisplayName = row.dataset.displayName || selectedTenantId;
      if (tenantId) tenantId.value = selectedTenantId;
      if (tenantDisplay) tenantDisplay.value = selectedDisplayName;
      if (tenantClear) tenantClear.style.display = selectedTenantId ? "block" : "none";
      const locHint = row.getAttribute("data-location-code");
      if (locHint !== null && String(locHint).trim() !== "") {
        const code = String(locHint).trim();
        if (locationDisplay) locationDisplay.value = code;
      }
      closeTenantModal();
    });
  }

  if (tenantClear) {
    tenantClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (tenantId) tenantId.value = "";
      if (tenantDisplay) tenantDisplay.value = "";
      tenantClear.style.display = "none";
      if (locationDisplay) locationDisplay.value = "";
    });
  }

  // Role popup
  const openRoleModal = () => {
    if (!roleModal) return;
    roleModal.classList.remove("hidden");
    if (roleModalSearch) {
      roleModalSearch.value = "";
      filterRoleRows("");
      setTimeout(() => roleModalSearch.focus(), 100);
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

  if (rolePicker) {
    rolePicker.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openRoleModal();
    });
  }

  if (roleDisplay) {
    roleDisplay.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openRoleModal();
    });
  }

  if (roleModal) {
    roleModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target && (target.dataset.close === "roleModal" || target.classList.contains("modal__close"))) {
        event.preventDefault();
        event.stopPropagation();
        closeRoleModal();
      }
    });
  }

  if (roleModalSearch) {
    roleModalSearch.addEventListener("input", (event) => {
      filterRoleRows((event.target.value || "").toLowerCase());
    });
  }

  if (roleModalClear) {
    roleModalClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (roleModalSearch) {
        roleModalSearch.value = "";
        filterRoleRows("");
        roleModalSearch.focus();
      }
    });
  }

  if (roleModalTable) {
    roleModalTable.addEventListener("click", (event) => {
      const row = event.target.closest("tbody tr");
      if (!row) return;
      event.preventDefault();
      event.stopPropagation();
      const selectedRoleId = row.dataset.roleId || "";
      const selectedRoleName = row.dataset.roleName || "";
      if (roleId) roleId.value = selectedRoleId;
      if (roleDisplay) {
        roleDisplay.value = selectedRoleId ? `${selectedRoleName} (${selectedRoleId})` : selectedRoleName;
      }
      if (roleClear) roleClear.style.display = selectedRoleId ? "block" : "none";
      closeRoleModal();
    });
  }

  if (roleClear) {
    roleClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (roleId) roleId.value = "";
      if (roleDisplay) roleDisplay.value = "";
      roleClear.style.display = "none";
    });
  }

  function syncEmployeeClear() {
    if (!employeeClear || !employeeCodeInput) return;
    const has = String(employeeCodeInput.value || "").trim().length > 0;
    employeeClear.style.display = has ? "block" : "none";
  }

  function setEmployeeSelection(code, name) {
    if (employeeCodeInput) employeeCodeInput.value = String(code || "").trim();
    if (employeeNameDisplay) employeeNameDisplay.value = String(name || "").trim();
    syncEmployeeClear();
  }

  function renderEmployeeModalRows(items, query) {
    if (!employeeModalBody) return;
    const tokens = (query || "").toLowerCase().split(/\s+/).filter(Boolean);
    const filtered = (items || []).filter((item) => {
      if (!tokens.length) return true;
      const text = [
        item.employeecode,
        item.employeename,
        item.designation,
      ]
        .join(" ")
        .toLowerCase();
      return tokens.every((token) => text.includes(token));
    });
    employeeModalBody.innerHTML = "";
    if (!filtered.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3;
      td.className = "muted";
      td.style.textAlign = "center";
      td.style.padding = "12px";
      td.textContent = items && items.length ? "No employees match your search." : "No employees found for this branch.";
      tr.appendChild(td);
      employeeModalBody.appendChild(tr);
      return;
    }
    filtered.forEach((item) => {
      const tr = document.createElement("tr");
      tr.className = "employee-pick-row";
      tr.dataset.employeeCode = String(item.employeecode || "").trim();
      tr.dataset.employeeName = String(item.employeename || "").trim();
      tr.style.cursor = "pointer";
      ["employeecode", "employeename", "designation"].forEach((key) => {
        const td = document.createElement("td");
        td.textContent = String(item[key] || "").trim();
        tr.appendChild(td);
      });
      employeeModalBody.appendChild(tr);
    });
  }

  async function loadEmployeeItems() {
    if (employeeItemsCache) return employeeItemsCache;
    if (!employeeApiUrl) return [];
    if (employeeItemsLoading) return employeeItemsCache || [];
    employeeItemsLoading = true;
    if (employeeModalBody) {
      employeeModalBody.innerHTML =
        '<tr><td colspan="3" class="muted" style="text-align:center;padding:12px;">Loading employees…</td></tr>';
    }
    try {
      const response = await fetch(employeeApiUrl);
      if (!response.ok) throw new Error("fetch failed");
      const data = await response.json();
      employeeItemsCache = data && data.success && Array.isArray(data.items) ? data.items : [];
    } catch (err) {
      employeeItemsCache = [];
      if (employeeModalBody) {
        employeeModalBody.innerHTML =
          '<tr><td colspan="3" class="muted" style="text-align:center;padding:12px;">Could not load employees.</td></tr>';
      }
    } finally {
      employeeItemsLoading = false;
    }
    return employeeItemsCache;
  }

  const closeEmployeeModal = () => {
    if (employeeModal) employeeModal.classList.add("hidden");
  };

  const openEmployeeModal = async () => {
    if (!employeeModal) return;
    employeeModal.classList.remove("hidden");
    const items = await loadEmployeeItems();
    const q = employeeModalSearch ? employeeModalSearch.value : "";
    renderEmployeeModalRows(items, q);
    if (employeeModalSearch) {
      setTimeout(() => employeeModalSearch.focus(), 100);
    }
  };

  if (employeePicker) {
    employeePicker.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openEmployeeModal();
    });
  }

  if (employeeCodeInput) {
    employeeCodeInput.addEventListener("input", () => {
      syncEmployeeClear();
      if (employeeNameDisplay && !employeeItemsCache) return;
      const code = String(employeeCodeInput.value || "").trim().toLowerCase();
      if (!code || !employeeItemsCache) {
        if (employeeNameDisplay && !code) employeeNameDisplay.value = "";
        return;
      }
      const match = employeeItemsCache.find(
        (item) => String(item.employeecode || "").trim().toLowerCase() === code
      );
      if (employeeNameDisplay) {
        employeeNameDisplay.value = match ? String(match.employeename || "").trim() : "";
      }
    });
    employeeCodeInput.addEventListener("keydown", (event) => {
      if (event.key === "F1") {
        event.preventDefault();
        openEmployeeModal();
      }
    });
    syncEmployeeClear();
  }

  if (employeeModal) {
    employeeModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target && (target.dataset.close === "employeeModal" || target.classList.contains("modal__close"))) {
        event.preventDefault();
        event.stopPropagation();
        closeEmployeeModal();
      }
    });
  }

  if (employeeModalSearch) {
    employeeModalSearch.addEventListener("input", (event) => {
      renderEmployeeModalRows(employeeItemsCache || [], (event.target.value || "").toLowerCase());
    });
  }

  if (employeeModalClear) {
    employeeModalClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (employeeModalSearch) {
        employeeModalSearch.value = "";
        renderEmployeeModalRows(employeeItemsCache || [], "");
        employeeModalSearch.focus();
      }
    });
  }

  if (employeeModalTable) {
    employeeModalTable.addEventListener("click", (event) => {
      const row = event.target.closest("tr.employee-pick-row");
      if (!row) return;
      event.preventDefault();
      event.stopPropagation();
      setEmployeeSelection(row.dataset.employeeCode, row.dataset.employeeName);
      closeEmployeeModal();
      if (employeeCodeInput) employeeCodeInput.focus();
    });
  }

  if (employeeClear) {
    employeeClear.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      setEmployeeSelection("", "");
      if (employeeCodeInput) employeeCodeInput.focus();
    });
  }

});
