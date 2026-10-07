(function () {
  const cfg = window.POS_PRICE_EDIT_REPORT || {};
  const filterFrom = document.getElementById("filterFrom");
  const filterTo = document.getElementById("filterTo");
  const filterCounter = document.getElementById("filterCounter");
  const filterShift = document.getElementById("filterShift");
  const reportStatus = document.getElementById("reportStatus");
  const reportBody = document.getElementById("reportBody");
  const btnLoad = document.getElementById("btnLoadReport");
  const btnExport = document.getElementById("btnExportCsv");

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function fmtNum(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return "0.00";
    return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function queryParams() {
    const p = new URLSearchParams();
    if (cfg.locationCode != null) p.set("location_code", String(cfg.locationCode));
    if (filterFrom && filterFrom.value) p.set("from", filterFrom.value);
    if (filterTo && filterTo.value) p.set("to", filterTo.value);
    if (filterCounter && filterCounter.value) p.set("counter_code", filterCounter.value);
    if (filterShift && filterShift.value.trim()) p.set("shift_code", filterShift.value.trim());
    return p;
  }

  async function loadCounters() {
    if (!filterCounter || !cfg.countersUrl) return;
    try {
      const p = new URLSearchParams();
      if (cfg.locationCode != null) p.set("location_code", String(cfg.locationCode));
      const res = await fetch(cfg.countersUrl + "?" + p.toString());
      const data = await res.json();
      const items = (data && data.counters) || (data && data.items) || [];
      items.forEach((c) => {
        const code = c.countercode != null ? c.countercode : c.code;
        if (code == null || code === "") return;
        const opt = document.createElement("option");
        opt.value = String(code);
        opt.textContent = (c.countername || c.name || "Counter") + " (" + code + ")";
        filterCounter.appendChild(opt);
      });
    } catch (_e) {
      /* ignore */
    }
  }

  function renderRows(rows) {
    if (!reportBody) return;
    reportBody.innerHTML = "";
    if (!rows || !rows.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="13" style="text-align:center;color:#94a3b8;padding:16px;">No price-edited lines for this filter.</td>';
      reportBody.appendChild(tr);
      return;
    }
    rows.forEach((r) => {
      const diff = Number(r.rate_diff) || 0;
      const diffCls = diff > 0 ? "pos-per-diff-up" : diff < 0 ? "pos-per-diff-down" : "";
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + esc(r.billno) + "</td>" +
        "<td>" + esc(r.billdate) + "</td>" +
        "<td>" + esc(r.countercode) + "</td>" +
        "<td>" + esc(r.createdby) + "</td>" +
        "<td>" + esc(r.slno) + "</td>" +
        "<td>" + esc(r.itemcode) + "</td>" +
        "<td>" + esc(r.itemname) + "</td>" +
        "<td>" + esc(r.uom) + "</td>" +
        '<td class="num">' + esc(r.quantity) + "</td>" +
        '<td class="num">' + fmtNum(r.original_rate) + "</td>" +
        '<td class="num">' + fmtNum(r.edited_rate) + "</td>" +
        '<td class="num ' + diffCls + '">' + fmtNum(diff) + "</td>" +
        '<td class="num ' + diffCls + '">' + fmtNum(r.line_impact) + "</td>";
      reportBody.appendChild(tr);
    });
  }

  async function loadReport() {
    if (!cfg.apiUrl) return;
    if (reportStatus) reportStatus.textContent = "Loading…";
    try {
      const res = await fetch(cfg.apiUrl + "?" + queryParams().toString());
      const data = await res.json();
      if (!data.success) {
        if (reportStatus) reportStatus.textContent = data.error || "Load failed.";
        renderRows([]);
        return;
      }
      const rep = data.report || {};
      const n = rep.line_count != null ? rep.line_count : (rep.rows || []).length;
      if (reportStatus) {
        reportStatus.textContent =
          "From " + (rep.from_date || "") + " to " + (rep.to_date || "") + " — " + n + " line(s) with edited price.";
      }
      renderRows(rep.rows || []);
    } catch (e) {
      if (reportStatus) reportStatus.textContent = "Load failed: " + (e.message || "network error");
      renderRows([]);
    }
  }

  if (btnLoad) btnLoad.addEventListener("click", loadReport);
  if (btnExport) {
    btnExport.addEventListener("click", () => {
      if (!cfg.exportUrl) return;
      window.location.href = cfg.exportUrl + "?" + queryParams().toString();
    });
  }

  loadCounters();
})();
