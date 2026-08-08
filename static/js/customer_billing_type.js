/**
 * Customer billing: CASH → BILLTYPE C; CREDIT → BILLTYPE R.
 */
(function (global) {
  function normalizeBillingType(raw) {
    const s = String(raw || "").trim().toUpperCase();
    if (s === "CREDIT" || s === "CR" || s === "R" || s === "2") return "CREDIT";
    return "CASH";
  }

  function billTypeFromBillingType(billingType) {
    return normalizeBillingType(billingType) === "CREDIT" ? "R" : "C";
  }

  function applyBillTypeFromBillingType(billTypeEl, billingType) {
    if (!billTypeEl) return;
    billTypeEl.value = billTypeFromBillingType(billingType);
  }

  function syncCustomerBillingFormSelect(selectEl) {
    if (!selectEl) return;
    const isCredit = normalizeBillingType(selectEl.value) === "CREDIT";
    const chk = document.getElementById("countersaleChk");
    const csHidden = document.getElementById("countersale");
    if (chk) {
      if (isCredit) {
        chk.checked = false;
        chk.disabled = true;
        chk.style.opacity = "0.4";
        chk.style.cursor = "not-allowed";
        if (csHidden) csHidden.value = "N";
      } else {
        chk.disabled = false;
        chk.style.opacity = "1";
        chk.style.cursor = "pointer";
      }
    }
  }

  global.NexaCustomerBilling = {
    normalizeBillingType,
    billTypeFromBillingType,
    applyBillTypeFromBillingType,
    syncCustomerBillingFormSelect,
  };
})(typeof window !== "undefined" ? window : globalThis);
