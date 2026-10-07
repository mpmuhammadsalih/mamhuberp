(function () {
  const app = document.getElementById("periodClosingApp");
  if (!app) return;

  function stripPcSearchWrappers() {
    ["pcFy", "pcMonth", "pcType"].forEach((id) => {
      const sel = document.getElementById(id);
      if (!sel) return;
      const wrap = sel.closest(".dropdown-search-wrapper");
      if (!wrap || !wrap.parentNode) return;
      wrap.parentNode.insertBefore(sel, wrap);
      wrap.remove();
    });
  }
  // Run after global dropdown-search.js (also on DOMContentLoaded)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(stripPcSearchWrappers, 0);
    });
  } else {
    setTimeout(stripPcSearchWrappers, 0);
  }

  const previewUrl = app.dataset.previewUrl || "";
  const closeUrl = app.dataset.closeUrl || "";
  const reopenUrl = app.dataset.reopenUrl || "";
  const draftDeleteUrl = app.dataset.draftDeleteUrl || "";
  const stockAdjustNegUrl = app.dataset.stockAdjustNegUrl || "/purchase/stock-adjustment/new?from_negative=1";
  const canClose = app.dataset.canClose === "1";
  const canReopen = app.dataset.canReopen === "1";

  let lastPreview = null;
  let lastPeriod = null;
  let lastValidation = null;

  const fmt = (n) => {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  const esc = (s) => {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  };

  function params() {
    return {
      financial_year: (document.getElementById("pcFy") || {}).value || "",
      month: parseInt((document.getElementById("pcMonth") || {}).value || "0", 10),
      closing_type: (document.getElementById("pcType") || {}).value || "MONTHLY",
    };
  }

  function openModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove("hidden");
    document.body.classList.add("pc-modal-open");
  }
  function closeModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.add("hidden");
    if (!document.querySelector(".pc-modal:not(.hidden)")) {
      document.body.classList.remove("pc-modal-open");
    }
  }

  document.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", () => closeModal(el.getAttribute("data-close")));
  });

  function showProgress(msg) {
    const el = document.getElementById("pcProgress");
    const t = document.getElementById("pcProgressText");
    if (t) t.textContent = msg || "Working…";
    if (el) el.classList.remove("hidden");
    if (typeof window.showLoadingOverlay === "function") {
      window.showLoadingOverlay(msg || "Working…");
    }
  }
  function hideProgress() {
    const el = document.getElementById("pcProgress");
    if (el) el.classList.add("hidden");
    if (typeof window.hideLoadingOverlay === "function") {
      window.hideLoadingOverlay();
    }
  }

  function renderCards(cards) {
    if (!cards) return;
    const map = {
      financial_year: cards.financial_year,
      current_period: cards.current_period,
      status: cards.status,
      last_closed_by: cards.last_closed_by,
      last_closed_date: cards.last_closed_date,
    };
    Object.keys(map).forEach((k) => {
      const el = document.querySelector('[data-card="' + k + '"]');
      if (!el) return;
      el.textContent = map[k] == null || map[k] === "" ? "—" : String(map[k]);
      if (k === "status") {
        el.classList.toggle("is-closed", String(map[k] || "").toUpperCase() === "CLOSED");
      }
    });
  }

  function renderKpis(p) {
    if (!p) return;
    ["revenue", "expenses", "gross_profit", "net_profit", "retained_earnings_balance"].forEach((k) => {
      const el = document.querySelector('[data-kpi="' + k + '"]');
      if (el) el.textContent = fmt(p[k]);
    });
    ["revenue", "cogs", "other_expenses", "expenses", "net_profit"].forEach((k) => {
      const el = document.querySelector('[data-pl="' + k + '"]');
      if (el) el.textContent = fmt(p[k]);
    });
    const nar = document.getElementById("pcNarration");
    if (nar) nar.value = p.narration || "";
    const tbody = document.querySelector("#pcJournalTable tbody");
    if (tbody) {
      const lines = p.journal_preview || [];
      if (!lines.length) {
        tbody.innerHTML = '<tr><td colspan="3" style="color:#64748b;">No closing lines for this period.</td></tr>';
      } else {
        tbody.innerHTML = lines
          .map(
            (ln) =>
              "<tr><td>" +
              esc(ln.account) +
              '</td><td class="num">' +
              (ln.debit ? fmt(ln.debit) : "—") +
              '</td><td class="num">' +
              (ln.credit ? fmt(ln.credit) : "—") +
              "</td></tr>"
          )
          .join("");
      }
    }
  }

  function draftSalesActionsHtml(ch) {
    if (!ch || ch.ok || !ch.can_delete || !canClose) return "";
    const items = ch.items || [];
    let html =
      '<div class="pc-draft-actions">' +
      '<button type="button" class="pc-btn pc-btn--danger pc-btn--sm" data-delete-all-drafts="1">Delete all drafts</button>' +
      "</div>";
    if (items.length) {
      html +=
        '<div class="pc-draft-list-wrap"><table class="pc-table pc-draft-table"><thead><tr>' +
        "<th>Loc</th><th>Bill No</th><th>Date</th><th class=\"num\">Amount</th><th></th></tr></thead><tbody>";
      items.forEach((it) => {
        html +=
          "<tr><td>" +
          esc(it.locationcode) +
          "</td><td>" +
          esc(it.billno) +
          "</td><td>" +
          esc(it.billdate || "—") +
          '</td><td class="num">' +
          fmt(it.amount) +
          '</td><td><button type="button" class="pc-btn pc-btn--danger pc-btn--sm" data-del-draft-loc="' +
          esc(it.locationcode) +
          '" data-del-draft-bill="' +
          esc(it.billno) +
          '">Delete</button></td></tr>';
      });
      html += "</tbody></table></div>";
    }
    return html;
  }

  function stockIssueListHtml(ch) {
    if (!ch || ch.ok) return "";
    const items = ch.items || [];
    let html = "";
    if (ch.key === "negative_stock" && stockAdjustNegUrl) {
      html +=
        '<div class="pc-draft-actions">' +
        '<a class="pc-btn pc-btn--primary pc-btn--sm" href="' +
        esc(stockAdjustNegUrl) +
        '" target="_blank" rel="noopener">Adjust negative stock</a>' +
        "</div>";
    }
    if (ch.hint) {
      html += '<div class="pc-check-hint">' + esc(ch.hint) + "</div>";
    }
    if (!items.length) return html;
    const showCost = ch.key === "inventory_valuation";
    html +=
      '<div class="pc-draft-list-wrap"><table class="pc-table pc-draft-table"><thead><tr>' +
      "<th>Loc</th><th>Item</th><th>Name</th><th class=\"num\">Qty</th>" +
      (showCost ? '<th class="num">Avg Cost</th><th class="num">Cost</th>' : "") +
      "</tr></thead><tbody>";
    items.forEach((it) => {
      html +=
        "<tr><td>" +
        esc(it.locationcode) +
        "</td><td>" +
        esc(it.itemcode) +
        "</td><td>" +
        esc(it.itemname || "—") +
        '</td><td class="num">' +
        fmt(it.qty) +
        "</td>";
      if (showCost) {
        html +=
          '<td class="num">' +
          fmt(it.averagecost) +
          '</td><td class="num">' +
          fmt(it.costprice) +
          "</td>";
      }
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    if ((ch.count || 0) > items.length) {
      html +=
        '<div class="pc-check-detail">Showing first ' +
        items.length +
        " of " +
        esc(ch.count) +
        ".</div>";
    }
    return html;
  }

  function renderChecks(validation) {
    const ul = document.getElementById("pcChecks");
    if (!ul || !validation) return;
    const checks = validation.checks || [];
    ul.innerHTML = checks
      .map((ch) => {
        let extra = "";
        if (ch.key === "draft_sales") extra = draftSalesActionsHtml(ch);
        else if (ch.key === "inventory_valuation" || ch.key === "negative_stock") {
          extra = stockIssueListHtml(ch);
        }
        return (
          '<li data-check-key="' +
          esc(ch.key) +
          '"><span class="pc-check-icon ' +
          (ch.ok ? "ok" : "fail") +
          '">' +
          (ch.ok ? "✓" : "!") +
          '</span><div class="pc-check-body"><strong>' +
          esc(ch.label) +
          '</strong><div class="pc-check-detail">' +
          esc(ch.detail) +
          "</div>" +
          extra +
          "</div></li>"
        );
      })
      .join("");
  }

  async function deleteDraftSales(payload) {
    if (!canClose) {
      alert("Only administrators can delete draft sales.");
      return;
    }
    if (!draftDeleteUrl) return;
    showProgress("Deleting draft sales…");
    try {
      const res = await fetch(draftDeleteUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      hideProgress();
      if (!data.success) {
        alert(data.error || "Delete failed");
        return;
      }
      alert("Deleted " + (data.deleted || 0) + " draft bill(s).");
      await runPreview();
    } catch (e) {
      hideProgress();
      alert("Network error while deleting drafts.");
    }
  }

  document.getElementById("pcChecks")?.addEventListener("click", (e) => {
    const allBtn = e.target.closest("[data-delete-all-drafts]");
    if (allBtn) {
      e.preventDefault();
      if (
        !confirm(
          "Delete ALL draft sales invoices from TEMPBILLHDR?\n\nThis permanently removes hold/cart bills that were never finalized. This cannot be undone."
        )
      ) {
        return;
      }
      deleteDraftSales({ delete_all: true });
      return;
    }
    const oneBtn = e.target.closest("[data-del-draft-bill]");
    if (oneBtn) {
      e.preventDefault();
      const loc = oneBtn.getAttribute("data-del-draft-loc");
      const bill = oneBtn.getAttribute("data-del-draft-bill");
      if (!confirm("Delete draft bill " + bill + " (location " + loc + ")?")) return;
      deleteDraftSales({
        items: [{ locationcode: Number(loc), billno: Number(bill) }],
      });
    }
  });

  function renderPeriods(periods) {
    const tbody = document.querySelector("#pcPeriodsTable tbody");
    if (!tbody) return;
    const rows = periods || [];
    if (!rows.length) {
      tbody.innerHTML =
        '<tr><td colspan="6" style="color:#64748b;padding:16px;">No periods yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((row) => {
        const st = String(row.status || "OPEN").toUpperCase();
        const badge =
          st === "CLOSED" ? "pc-badge--closed" : "pc-badge--open";
        return (
          "<tr data-month=\"" +
          esc(row.month) +
          "\"><td>" +
          esc(row.period_label) +
          "</td><td>" +
          esc(row.start_date) +
          "</td><td>" +
          esc(row.end_date) +
          '</td><td><span class="pc-badge ' +
          badge +
          '">' +
          esc(st) +
          "</span></td><td>" +
          esc(row.closed_date || "—") +
          "</td><td>" +
          esc(row.closed_by || "—") +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function runPreview() {
    const p = params();
    if (!p.financial_year || !p.month) return;
    showProgress("Loading preview…");
    try {
      const q = new URLSearchParams({
        financial_year: p.financial_year,
        month: String(p.month),
      });
      const res = await fetch(previewUrl + "?" + q.toString());
      const data = await res.json();
      if (!data.success) {
        alert(data.error || "Preview failed");
        return;
      }
      lastPreview = data.preview;
      lastPeriod = data.period;
      lastValidation = data.validation;
      renderCards(data.cards);
      renderKpis(data.preview);
      renderChecks(data.validation);
      renderPeriods(data.periods);
    } catch (e) {
      alert("Network error loading preview.");
    } finally {
      hideProgress();
    }
  }

  function openCloseConfirm() {
    if (!canClose) {
      alert("Only administrators can close periods.");
      return;
    }
    if (!lastPreview || !lastPeriod) {
      runPreview().then(() => {
        if (lastPreview && lastPeriod) openCloseConfirm();
      });
      return;
    }
    if (lastValidation && !lastValidation.ok) {
      const fails = (lastValidation.checks || [])
        .filter((c) => !c.ok)
        .map((c) => "• " + c.label + ": " + c.detail)
        .join("\n");
      alert("Validation failed. Fix these before closing:\n\n" + fails);
      return;
    }
    if (String(lastPeriod.status || "").toUpperCase() === "CLOSED") {
      alert("This period is already closed.");
      return;
    }
    const p = params();
    document.getElementById("pcConfirmPeriod").textContent = lastPeriod.period_label || "—";
    document.getElementById("pcConfirmType").textContent =
      p.closing_type === "YEAR_END" ? "Year-End Close" : "Monthly Close";
    document.getElementById("pcConfirmRev").textContent = fmt(lastPreview.revenue);
    document.getElementById("pcConfirmExp").textContent = fmt(lastPreview.expenses);
    document.getElementById("pcConfirmProfit").textContent = fmt(lastPreview.net_profit);
    const plNote = document.getElementById("pcConfirmPlNote");
    if (plNote) plNote.style.display = "list-item";
    const yn = document.getElementById("pcConfirmYearNote");
    if (yn) yn.style.display = p.closing_type === "YEAR_END" ? "list-item" : "none";
    openModal("pcCloseModal");
  }

  function applySaveNonce(data) {
    if (data && typeof data.save_nonce === "string" && data.save_nonce) {
      window.__GLOBAL_SAVE_NONCE = data.save_nonce;
    }
  }

  async function doClose() {
    if (doClose._busy) return;
    doClose._busy = true;
    const btn = document.getElementById("pcConfirmClose");
    const startBtn = document.getElementById("pcBtnClose");
    if (btn) btn.disabled = true;
    if (startBtn) startBtn.disabled = true;
    const p = params();
    const nonce = typeof window.__GLOBAL_SAVE_NONCE === "string" ? window.__GLOBAL_SAVE_NONCE : "";
    closeModal("pcCloseModal");
    showProgress("Closing period…");
    try {
      const res = await fetch(closeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Save-Nonce": nonce,
        },
        body: JSON.stringify({
          financial_year: p.financial_year,
          month: p.month,
          closing_type: p.closing_type,
          save_nonce: nonce,
        }),
      });
      const data = await res.json();
      applySaveNonce(data);
      hideProgress();
      if (!data.success) {
        if (data.replay_blocked || res.status === 409) {
          alert(data.error || "Duplicate close blocked. Refresh and try once.");
          return;
        }
        if (data.save_session_locked || res.status === 423) {
          alert(data.error || "Closing already in progress. Please wait.");
          return;
        }
        if (data.validation && data.validation.checks) {
          renderChecks(data.validation);
          const fails = data.validation.checks
            .filter((c) => !c.ok)
            .map((c) => "• " + c.label + ": " + c.detail)
            .join("\n");
          alert((data.error || "Close failed") + (fails ? "\n\n" + fails : ""));
        } else {
          alert(data.error || "Close failed");
        }
        return;
      }
      document.getElementById("pcSuccessTitle").textContent = "Period Closed Successfully";
      let msg = "Closing No: " + (data.closing_number || "—");
      if (data.voucher_no) msg += "\nJournal: " + data.voucher_no;
      if (data.next_financial_year) msg += "\nNext FY created: " + data.next_financial_year;
      document.getElementById("pcSuccessMsg").textContent = msg;
      openModal("pcSuccessModal");
      await runPreview();
    } catch (e) {
      hideProgress();
      alert("Network error while closing.");
    } finally {
      doClose._busy = false;
      if (btn) btn.disabled = false;
      if (startBtn) startBtn.disabled = false;
    }
  }

  function openReopen() {
    if (!canReopen) {
      alert("Only administrators can reopen periods.");
      return;
    }
    const label =
      (lastPeriod && lastPeriod.period_label) ||
      ((document.getElementById("pcMonth") || {}).selectedOptions || [{}])[0].text +
        " " +
        ((document.getElementById("pcFy") || {}).value || "");
    document.getElementById("pcReopenPeriodLabel").textContent = label;
    document.getElementById("pcReopenReason").value = "";
    const revCb = document.getElementById("pcReopenReverseJournal");
    if (revCb) revCb.checked = true;
    openModal("pcReopenModal");
  }

  async function doReopen() {
    if (doReopen._busy) return;
    doReopen._busy = true;
    const btn = document.getElementById("pcConfirmReopen");
    const startBtn = document.getElementById("pcBtnReopen");
    if (btn) btn.disabled = true;
    if (startBtn) startBtn.disabled = true;
    const reason = (document.getElementById("pcReopenReason").value || "").trim();
    if (!reason) {
      doReopen._busy = false;
      if (btn) btn.disabled = false;
      if (startBtn) startBtn.disabled = false;
      alert("Reason is mandatory.");
      return;
    }
    const reverseJournal = !!(document.getElementById("pcReopenReverseJournal") || {}).checked;
    const p = params();
    const nonce = typeof window.__GLOBAL_SAVE_NONCE === "string" ? window.__GLOBAL_SAVE_NONCE : "";
    closeModal("pcReopenModal");
    showProgress(reverseJournal ? "Reopening period and reversing closing journal…" : "Reopening period…");
    try {
      const res = await fetch(reopenUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Save-Nonce": nonce,
        },
        body: JSON.stringify({
          financial_year: p.financial_year,
          month: p.month,
          reason: reason,
          reverse_closing_journal: reverseJournal,
          save_nonce: nonce,
        }),
      });
      const data = await res.json();
      applySaveNonce(data);
      hideProgress();
      if (!data.success) {
        if (data.replay_blocked || res.status === 409) {
          alert(data.error || "Duplicate reopen blocked. Refresh and try once.");
          return;
        }
        if (data.save_session_locked || res.status === 423) {
          alert(data.error || "Reopen already in progress. Please wait.");
          return;
        }
        alert(data.error || "Reopen failed");
        return;
      }
      document.getElementById("pcSuccessTitle").textContent = "Period Reopened";
      document.getElementById("pcSuccessMsg").textContent =
        data.message || "Period is open again.";
      openModal("pcSuccessModal");
      await runPreview();
    } catch (e) {
      hideProgress();
      alert("Network error while reopening.");
    } finally {
      doReopen._busy = false;
      if (btn) btn.disabled = false;
      if (startBtn) startBtn.disabled = false;
    }
  }

  document.getElementById("pcBtnPreview")?.addEventListener("click", runPreview);
  document.getElementById("pcBtnClose")?.addEventListener("click", openCloseConfirm);
  document.getElementById("pcBtnReopen")?.addEventListener("click", openReopen);
  document.getElementById("pcConfirmClose")?.addEventListener("click", doClose);
  document.getElementById("pcConfirmReopen")?.addEventListener("click", doReopen);
  document.getElementById("pcSuccessOk")?.addEventListener("click", () => closeModal("pcSuccessModal"));

  ["pcFy", "pcMonth", "pcType"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", () => {
      /* soft refresh on filter change */
    });
  });
})();
