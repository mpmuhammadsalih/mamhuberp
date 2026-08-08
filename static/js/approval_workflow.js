(function () {
  const app = document.getElementById("approvalWorkflowApp");
  if (!app) return;

  const apiUrl = app.dataset.api || "";
  const saveUrl = app.dataset.save || "";
  const deleteBase = app.dataset.deleteBase || "";
  const actionUrl = app.dataset.action || "";
  const delegationUrl = app.dataset.delegation || "";
  const escalationUrl = app.dataset.escalation || "";

  let state = window.AWF_INITIAL || {};
  let selectedWorkflowId = null;

  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };

  const fmtMoney = (n) => {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  };

  function renderKpis(kpis) {
    if (!kpis) return;
    document.querySelectorAll("[data-kpi]").forEach((el) => {
      const k = el.dataset.kpi;
      if (kpis[k] != null) el.textContent = kpis[k];
    });
    const p = kpis.pending_approvals || 0;
    ["awfBadgePending", "awfPendingSectionBadge"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = p;
    });
    const my = document.getElementById("awfBadgeMy");
    if (my) my.textContent = kpis.my_approvals_today != null ? kpis.my_approvals_today : 0;
    const myToday = document.getElementById("awfMyTodayCount");
    if (myToday) myToday.textContent = kpis.my_approvals_today != null ? kpis.my_approvals_today : 0;
  }

  function renderFlowPreview(wf) {
    const host = document.getElementById("awfFlowPreview");
    if (!host) return;
    if (!wf) {
      host.innerHTML = '<p class="awf-panel-placeholder">Select a workflow row</p>';
      return;
    }
    const steps = (wf.levels || [])
      .map(
        (lv) => `
        <div class="awf-flow-step">
          <div class="awf-flow-dot">${lv.level_no}</div>
          <div>
            <strong>Level ${lv.level_no}</strong> — ${esc(lv.role_label)}
            <div><span class="awf-pill awf-pill--pending">Pending</span></div>
          </div>
        </div>`
      )
      .join("");
    host.innerHTML = `
      <div style="margin-bottom:10px;">
        <strong>${esc(wf.workflow_name)}</strong>
        <span class="awf-pill awf-pill--active">${esc(wf.status)}</span>
        <div style="font-size:0.75rem;color:#6c757d;margin-top:4px;">Amount: ${esc(wf.amount_range)}</div>
      </div>
      ${steps || "<p>No levels defined.</p>"}`;
  }

  function renderDetails(wf) {
    const list = document.getElementById("awfDetailList");
    if (!list) return;
    if (!wf) {
      list.innerHTML = '<li><span>Workflow Name</span><span>—</span></li>';
      return;
    }
    const rows = [
      ["Workflow Name", wf.workflow_name],
      ["Transaction Type", wf.transaction_label || wf.transaction_type],
      ["Amount Range", wf.amount_range],
      ["No. of Levels", wf.num_levels],
      ["Created By", wf.created_by || "—"],
      ["Created Date", wf.created_date || "—"],
      ["Status", wf.status],
    ];
    list.innerHTML = rows.map(([k, v]) => `<li><span>${esc(k)}</span><span>${esc(v)}</span></li>`).join("");
  }

  function renderRules(workflows) {
    const body = document.getElementById("awfRulesBody");
    if (!body) return;
    if (!workflows || !workflows.length) {
      body.innerHTML = '<tr><td colspan="7" style="padding:16px;color:#6c757d;">No workflows. Click + New Workflow.</td></tr>';
      return;
    }
    body.innerHTML = workflows
      .map((w) => {
        const sel = selectedWorkflowId === w.workflow_id ? " awf-row--sel" : "";
        const stCls = w.status === "ACTIVE" ? "awf-pill--active" : "awf-pill--inactive";
        return `<tr class="awf-rule-row${sel}" data-id="${w.workflow_id}">
          <td>${w.row_no}</td>
          <td>${esc(w.workflow_name)}</td>
          <td>${esc(w.transaction_label)}</td>
          <td>${esc(w.amount_range)}</td>
          <td>${w.num_levels}</td>
          <td><span class="awf-pill ${stCls}">${esc(w.status)}</span></td>
          <td>
            <button type="button" class="awf-icon-btn awf-icon-btn--edit" data-edit="${w.workflow_id}" title="Edit">✎</button>
            <button type="button" class="awf-icon-btn awf-icon-btn--del" data-del="${w.workflow_id}" title="Delete">🗑</button>
          </td>
        </tr>`;
      })
      .join("");
    body.querySelectorAll(".awf-rule-row").forEach((tr) => {
      tr.addEventListener("click", (e) => {
        if (e.target.closest("[data-edit],[data-del]")) return;
        selectWorkflow(Number(tr.dataset.id));
      });
    });
    body.querySelectorAll("[data-edit]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        openModal(Number(btn.dataset.edit)).catch((e) => alert(e.message));
      });
    });
    body.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteWorkflow(Number(btn.dataset.del));
      });
    });
  }

  function renderPending(rows) {
    const body = document.getElementById("awfPendingBody");
    if (!body) return;
    if (!rows || !rows.length) {
      body.innerHTML = '<tr><td colspan="8" style="padding:16px;color:#6c757d;">No pending approvals.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td><strong>${esc(r.document_no)}</strong></td>
          <td>${esc(r.transaction_label)}</td>
          <td>${esc(r.document_date)}</td>
          <td>${esc(r.created_by)}</td>
          <td>${fmtMoney(r.amount)}</td>
          <td>Level ${r.current_level}</td>
          <td>${esc(r.pending_at)}</td>
          <td>
            <button type="button" class="awf-btn awf-btn--ok awf-btn--sm" data-approve="${r.queue_id}">Approve</button>
            <button type="button" class="awf-btn awf-btn--err awf-btn--sm" data-reject="${r.queue_id}">Reject</button>
          </td>
        </tr>`
      )
      .join("");
    body.querySelectorAll("[data-approve]").forEach((b) => {
      b.addEventListener("click", () => queueAction(Number(b.dataset.approve), "APPROVE"));
    });
    body.querySelectorAll("[data-reject]").forEach((b) => {
      b.addEventListener("click", () => queueAction(Number(b.dataset.reject), "REJECT"));
    });
  }

  function renderTableBody(id, rows, cols, emptyMsg) {
    const body = document.getElementById(id);
    if (!body) return;
    if (!rows || !rows.length) {
      body.innerHTML = `<tr><td colspan="${cols}" style="padding:16px;color:#6c757d;">${emptyMsg}</td></tr>`;
      return;
    }
    return body;
  }

  function renderMyApprovals(rows) {
    const body = renderTableBody("awfMyBody", rows, 5, "No approvals recorded yet.");
    if (!body || !rows?.length) return;
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td><strong>${esc(r.document_no)}</strong></td>
          <td>${esc(r.transaction_label)}</td>
          <td>${fmtMoney(r.amount)}</td>
          <td><span class="awf-pill ${r.status === "APPROVED" ? "awf-pill--active" : "awf-pill--inactive"}">${esc(r.status)}</span></td>
          <td>${esc(r.action_at)}</td>
        </tr>`
      )
      .join("");
  }

  function renderHistory(rows) {
    const body = renderTableBody("awfHistoryBody", rows, 7, "No completed approvals yet.");
    if (!body || !rows?.length) return;
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td><strong>${esc(r.document_no)}</strong></td>
          <td>${esc(r.transaction_label)}</td>
          <td>${fmtMoney(r.amount)}</td>
          <td>${esc(r.status)}</td>
          <td>${esc(r.action_by)}</td>
          <td>${esc(r.action_at)}</td>
          <td>${esc(r.remarks)}</td>
        </tr>`
      )
      .join("");
  }

  function renderDelegations(rows) {
    const body = renderTableBody("awfDelegationBody", rows, 6, "No delegations. Click + Add.");
    if (!body || !rows?.length) return;
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td>${esc(r.delegator_user)}</td>
          <td>${esc(r.delegate_user)}</td>
          <td>${esc(r.date_from)}</td>
          <td>${esc(r.date_to)}</td>
          <td>${esc(r.status)}</td>
          <td>${esc(r.remarks)}</td>
        </tr>`
      )
      .join("");
  }

  function renderEscalations(rows) {
    const body = renderTableBody("awfEscalationBody", rows, 4, "No escalation rules.");
    if (!body || !rows?.length) return;
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td>${esc(r.transaction_label)}</td>
          <td>${r.hours_pending}</td>
          <td>${esc(r.escalate_to_role)}</td>
          <td>${esc(r.status)}</td>
        </tr>`
      )
      .join("");
  }

  function renderPendingFull(rows) {
    const body = document.getElementById("awfPendingFullBody");
    if (!body) return;
    if (!rows || !rows.length) {
      body.innerHTML = '<tr><td colspan="8" style="padding:16px;color:#6c757d;">No pending approvals.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(
        (r) => `<tr>
          <td><strong>${esc(r.document_no)}</strong></td>
          <td>${esc(r.transaction_label)}</td>
          <td>${esc(r.document_date)}</td>
          <td>${esc(r.created_by)}</td>
          <td>${fmtMoney(r.amount)}</td>
          <td>Level ${r.current_level}</td>
          <td>${esc(r.pending_at)}</td>
          <td>
            <button type="button" class="awf-btn awf-btn--ok awf-btn--sm" data-approve="${r.queue_id}">Approve</button>
            <button type="button" class="awf-btn awf-btn--err awf-btn--sm" data-reject="${r.queue_id}">Reject</button>
          </td>
        </tr>`
      )
      .join("");
    body.querySelectorAll("[data-approve]").forEach((b) => {
      b.addEventListener("click", () => queueAction(Number(b.dataset.approve), "APPROVE"));
    });
    body.querySelectorAll("[data-reject]").forEach((b) => {
      b.addEventListener("click", () => queueAction(Number(b.dataset.reject), "REJECT"));
    });
  }

  function applyPayload(payload) {
    state = payload || state;
    renderKpis(state.kpis);
    renderRules(state.workflows);
    renderPending(state.pending);
    renderPendingFull(state.pending);
    renderMyApprovals(state.my_approvals);
    renderHistory(state.history);
    renderDelegations(state.delegations);
    renderEscalations(state.escalations);
    const wf = state.selected_workflow;
    if (wf) {
      selectedWorkflowId = wf.workflow_id;
      renderFlowPreview(wf);
      renderDetails(wf);
    }
  }

  async function refresh(wfId) {
    const tx = document.getElementById("awfTxFilter")?.value || "ALL";
    let url = apiUrl + "?transaction_type=" + encodeURIComponent(tx);
    if (wfId) url += "&workflow_id=" + wfId;
    const res = await fetch(url);
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Load failed");
    applyPayload(data);
  }

  async function selectWorkflow(id) {
    selectedWorkflowId = id;
    await refresh(id);
    document.querySelectorAll(".awf-rule-row").forEach((tr) => {
      tr.classList.toggle("awf-row--sel", Number(tr.dataset.id) === id);
    });
  }

  const modal = document.getElementById("awfModal");
  async function openModal(editId) {
    let wf = null;
    if (editId) {
      const res = await fetch(apiUrl + "?workflow_id=" + editId);
      const data = await res.json();
      if (data.success) wf = data.selected_workflow;
    }
    document.getElementById("awfEditId").value = editId || "";
    document.getElementById("awfModalTitle").textContent = editId ? "Edit Workflow" : "New Workflow";
    document.getElementById("awfName").value = wf?.workflow_name || "";
    document.getElementById("awfTxType").value = wf?.transaction_type || "PO";
    document.getElementById("awfAnyAmount").checked = wf?.amount_any === "Y";
    document.getElementById("awfAmountMin").value = wf?.amount_min ?? 0;
    document.getElementById("awfAmountMax").value = wf?.amount_max ?? "";
    document.getElementById("awfNumLevels").value = wf?.num_levels || 1;
    document.getElementById("awfStatus").value = wf?.status || "ACTIVE";
    buildLevelFields(Number(document.getElementById("awfNumLevels").value), wf?.levels);
    toggleAmountFields();
    modal?.classList.remove("hidden");
  }

  function closeModal() {
    modal?.classList.add("hidden");
  }

  function toggleAmountFields() {
    const any = document.getElementById("awfAnyAmount")?.checked;
    const af = document.getElementById("awfAmountFields");
    if (af) af.style.display = any ? "none" : "block";
  }

  function buildLevelFields(n, existing) {
    const host = document.getElementById("awfLevelFields");
    if (!host) return;
    const map = {};
    (existing || []).forEach((lv) => {
      map[lv.level_no] = lv.role_label;
    });
    host.innerHTML = "";
    for (let i = 1; i <= n; i++) {
      const row = document.createElement("div");
      row.className = "awf-level-row";
      row.innerHTML = `<span>L${i}</span><input type="text" data-level="${i}" value="${esc(map[i] || `Level ${i} Approver`)}" />`;
      host.appendChild(row);
    }
  }

  async function saveModal() {
    const n = Number(document.getElementById("awfNumLevels").value || 1);
    const levels = [];
    document.querySelectorAll("#awfLevelFields input[data-level]").forEach((inp) => {
      levels.push({
        level_no: Number(inp.dataset.level),
        role_label: inp.value.trim() || `Level ${inp.dataset.level}`,
      });
    });
    const payload = {
      workflow_id: document.getElementById("awfEditId").value || null,
      workflow_name: document.getElementById("awfName").value,
      transaction_type: document.getElementById("awfTxType").value,
      amount_any: document.getElementById("awfAnyAmount").checked,
      amount_min: document.getElementById("awfAmountMin").value,
      amount_max: document.getElementById("awfAmountMax").value || null,
      num_levels: n,
      status: document.getElementById("awfStatus").value,
      levels,
    };
    const res = await fetch(saveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Save failed");
    closeModal();
    selectedWorkflowId = data.workflow_id;
    await refresh(data.workflow_id);
  }

  async function deleteWorkflow(id) {
    if (!confirm("Delete this workflow rule?")) return;
    const res = await fetch(deleteBase + "/" + id, { method: "DELETE" });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Delete failed");
    selectedWorkflowId = null;
    await refresh();
  }

  async function queueAction(qid, action) {
    const res = await fetch(actionUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ queue_id: qid, action }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Action failed");
    applyPayload(data);
  }

  document.getElementById("awfTabs")?.addEventListener("click", (e) => {
    const tab = e.target.closest(".awf-tab");
    if (!tab) return;
    const key = tab.dataset.tab;
    document.querySelectorAll(".awf-tab").forEach((t) => t.classList.toggle("awf-tab--active", t === tab));
    const views = {
      setup: "awfViewSetup",
      pending: "awfViewPending",
      my: "awfViewMy",
      history: "awfViewHistory",
      delegation: "awfViewDelegation",
      escalation: "awfViewEscalation",
    };
    Object.entries(views).forEach(([k, id]) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("awf-view--active", k === key);
    });
  });

  document.getElementById("awfTxFilter")?.addEventListener("change", () => refresh(selectedWorkflowId));
  document.getElementById("awfBtnNew")?.addEventListener("click", () => openModal(null).catch((e) => alert(e.message)));
  document.getElementById("awfModalSave")?.addEventListener("click", () => saveModal().catch((e) => alert(e.message)));
  document.getElementById("awfNumLevels")?.addEventListener("change", (e) => {
    buildLevelFields(Number(e.target.value || 1));
  });
  document.getElementById("awfAnyAmount")?.addEventListener("change", toggleAmountFields);
  document.getElementById("awfViewAllPending")?.addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelector('.awf-tab[data-tab="pending"]')?.click();
  });

  async function addDelegation() {
    const delegator = prompt("Delegator username:");
    if (!delegator) return;
    const delegate = prompt("Delegate username:");
    if (!delegate) return;
    const dateFrom = prompt("From date (YYYY-MM-DD):", new Date().toISOString().slice(0, 10));
    const dateTo = prompt("To date (YYYY-MM-DD):", "");
    const remarks = prompt("Remarks (optional):", "") || "";
    const res = await fetch(delegationUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        delegator_user: delegator,
        delegate_user: delegate,
        date_from: dateFrom,
        date_to: dateTo,
        remarks,
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Save failed");
    applyPayload(data);
  }

  async function addEscalation() {
    const tx = prompt("Transaction type code (LPO, GRN, STK_ADJ, PO, or ALL):", "ALL");
    if (!tx) return;
    const hrs = prompt("Hours pending before escalation:", "24");
    const role = prompt("Escalate to role label:", "Manager");
    const res = await fetch(escalationUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transaction_type: tx,
        hours_pending: Number(hrs || 24),
        escalate_to_role: role,
      }),
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || "Save failed");
    applyPayload(data);
  }

  document.getElementById("awfBtnAddDelegation")?.addEventListener("click", () => {
    addDelegation().catch((e) => alert(e.message));
  });
  document.getElementById("awfBtnAddEscalation")?.addEventListener("click", () => {
    addEscalation().catch((e) => alert(e.message));
  });

  modal?.addEventListener("click", (e) => {
    if (e.target.dataset.close === "awfModal" || e.target.classList.contains("awf-modal__backdrop")) closeModal();
  });

  applyPayload(state);
  if (state.workflows && state.workflows.length && state.selected_workflow) {
    selectedWorkflowId = state.selected_workflow.workflow_id;
  }
})();
