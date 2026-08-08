/**
 * Closed accounting-period date guard (Period Closing).
 * Usage: PeriodDateGuard.bind(inputEl, closedPeriods, { hintEl, onClosed })
 */
(function (global) {
  "use strict";

  function parsePeriods(raw) {
    if (Array.isArray(raw)) return raw;
    if (typeof raw === "string") {
      try {
        const parsed = JSON.parse(raw || "[]");
        return Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        return [];
      }
    }
    return [];
  }

  function closedPeriodForDate(isoDate, periods) {
    const d = String(isoDate || "").trim().slice(0, 10);
    if (!d || d.length < 10) return null;
    const list = periods || [];
    for (let i = 0; i < list.length; i++) {
      const p = list[i] || {};
      const a = String(p.start_date || "").slice(0, 10);
      const b = String(p.end_date || "").slice(0, 10);
      if (a && b && d >= a && d <= b) return p;
    }
    return null;
  }

  function messageForDate(isoDate, periods) {
    const p = closedPeriodForDate(isoDate, periods);
    if (!p) return "";
    const label = p.period_label || String(p.month || "") + " " + String(p.financial_year || "");
    return "Accounting period " + String(label).trim() + " is closed. Choose a date in an open period.";
  }

  function defaultHint(periods) {
    const list = periods || [];
    if (!list.length) {
      return "Closed accounting periods cannot be selected (Period Closing).";
    }
    const labels = list
      .slice(0, 6)
      .map(function (p) {
        return p.period_label || "";
      })
      .filter(Boolean);
    if (!labels.length) {
      return "Closed accounting periods cannot be selected (Period Closing).";
    }
    return (
      "Closed periods (read-only): " +
      labels.join(", ") +
      (list.length > 6 ? "…" : "") +
      ". Dates in those ranges cannot be posted."
    );
  }

  function bind(inputEl, closedPeriods, opts) {
    opts = opts || {};
    const input = typeof inputEl === "string" ? document.querySelector(inputEl) : inputEl;
    if (!input) return null;
    const periods = parsePeriods(closedPeriods);
    const hintEl =
      typeof opts.hintEl === "string"
        ? document.querySelector(opts.hintEl)
        : opts.hintEl || null;

    function refresh() {
      const msg = messageForDate(input.value, periods);
      if (msg) {
        input.setCustomValidity(msg);
        if (hintEl) {
          hintEl.textContent = msg;
          hintEl.style.color = "#b91c1c";
        }
      } else {
        input.setCustomValidity("");
        if (hintEl) {
          hintEl.textContent = defaultHint(periods);
          hintEl.style.color = "";
        }
      }
      if (typeof opts.onClosed === "function") {
        opts.onClosed(!!msg, msg);
      }
      return msg;
    }

    input.addEventListener("change", refresh);
    input.addEventListener("input", refresh);
    refresh();

    return {
      periods: periods,
      refresh: refresh,
      isClosed: function (isoDate) {
        return !!closedPeriodForDate(isoDate == null ? input.value : isoDate, periods);
      },
      message: function (isoDate) {
        return messageForDate(isoDate == null ? input.value : isoDate, periods);
      },
    };
  }

  function fromJsonScript(scriptId) {
    try {
      const el = document.getElementById(scriptId);
      return parsePeriods(el ? el.textContent || "[]" : "[]");
    } catch (e) {
      return [];
    }
  }

  global.PeriodDateGuard = {
    parsePeriods: parsePeriods,
    closedPeriodForDate: closedPeriodForDate,
    messageForDate: messageForDate,
    defaultHint: defaultHint,
    bind: bind,
    fromJsonScript: fromJsonScript,
  };
})(typeof window !== "undefined" ? window : this);
