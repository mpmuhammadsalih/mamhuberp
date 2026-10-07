const paymentInputs = document.querySelectorAll(".pay-input");
const totalEl = document.getElementById("payment-total");
const totalInput = document.getElementById("payment-total-input");
const totalBillAmount = document.getElementById("total-billamount");
const totalPaidAmount = document.getElementById("total-paidamount");
const totalBalance = document.getElementById("total-balance");
const totalPayAmount = document.getElementById("total-payamount");
const customerInput = document.getElementById("customerInput");
const customerClear = document.getElementById("customerClear");
const customerCode = document.getElementById("customerCode");
const customerPicker = document.getElementById("customerPicker");
const paymentsFilterForm = document.getElementById("paymentsFilterForm");
const customerModal = document.getElementById("customerModal");
const customerModalSearch = document.getElementById("customerModalSearch");
const customerModalClear = document.getElementById("customerModalClear");
const customerModalTable = document.getElementById("customerModalTable");
const salesmanInput = document.getElementById("salesmanInput");
const salesmanClear = document.getElementById("salesmanClear");
const salesmanCode = document.getElementById("salesmanCode");
const salesmanPicker = document.getElementById("salesmanPicker");
const salesmanModal = document.getElementById("salesmanModal");
const salesmanModalSearch = document.getElementById("salesmanModalSearch");
const salesmanModalClear = document.getElementById("salesmanModalClear");
const salesmanModalTable = document.getElementById("salesmanModalTable");

const parseNumber = (value) => {
  const cleaned = String(value).replace(/,/g, "").trim();
  const number = Number.parseFloat(cleaned);
  return Number.isNaN(number) ? 0 : number;
};

const updateTotal = () => {
  let total = 0;
  paymentInputs.forEach((input) => {
    total += parseNumber(input.value);
  });
  if (totalEl) {
    totalEl.textContent = total.toFixed(2);
  }
  if (totalInput) {
    totalInput.value = total.toFixed(2);
  }

  if (totalPayAmount) {
    totalPayAmount.textContent = total.toFixed(2);
  }

  let billSum = 0;
  let paidSum = 0;
  let balanceSum = 0;
  const rows = document.querySelectorAll("#payments-table tbody tr");
  rows.forEach((row) => {
    const billAmountCell = row.children[3];
    const paidAmountCell = row.children[4];
    const balanceCell = row.children[5];
    billSum += parseNumber(billAmountCell?.textContent || 0);
    paidSum += parseNumber(paidAmountCell?.textContent || 0);
    balanceSum += parseNumber(balanceCell?.textContent || 0);
  });
  if (totalBillAmount) totalBillAmount.textContent = billSum.toFixed(2);
  if (totalPaidAmount) totalPaidAmount.textContent = paidSum.toFixed(2);
  if (totalBalance) totalBalance.textContent = balanceSum.toFixed(2);
};

paymentInputs.forEach((input) => {
  input.addEventListener("input", (event) => {
    const cleaned = event.target.value.replace(/[^0-9.]/g, "");
    event.target.value = cleaned;
    const max = parseNumber(event.target.dataset.balance);
    let value = parseNumber(event.target.value);
    if (value < 0) value = 0;
    if (value > max) value = max;
    if (event.target.value === "") {
      updateTotal();
      return;
    }
    if (value > max) {
      event.target.value = String(max);
    }
    updateTotal();
  });

  input.addEventListener("blur", (event) => {
    const max = parseNumber(event.target.dataset.balance);
    let value = parseNumber(event.target.value);
    if (!event.target.value) {
      updateTotal();
      return;
    }
    if (value > max) {
      value = max;
    }
    if (value < 0) {
      value = 0;
    }
    event.target.value = String(value);
    updateTotal();
  });
});

updateTotal();

const attachLongPress = (input) => {
  let timer = null;
  const threshold = 600;

  const clearTimer = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    input.classList.remove("pay-input--hold");
  };

  const handleLongPress = () => {
    const max = parseNumber(input.dataset.balance);
    const current = parseNumber(input.value);
    if (current > 0) {
      input.value = "";
    } else {
      input.value = String(max);
    }
    updateTotal();
  };

  const start = (event) => {
    if (event.type === "mousedown" && event.button !== 0) return;
    clearTimer();
    input.classList.add("pay-input--hold");
    timer = setTimeout(handleLongPress, threshold);
  };

  input.addEventListener("mousedown", start);
  input.addEventListener("touchstart", start, { passive: true });
  input.addEventListener("mouseup", clearTimer);
  input.addEventListener("mouseleave", clearTimer);
  input.addEventListener("touchend", clearTimer);
  input.addEventListener("touchcancel", clearTimer);
};

paymentInputs.forEach((input) => {
  attachLongPress(input);
});

const openModal = async () => {
  if (!customerModal) return;
  customerModal.classList.remove("hidden");
  
  // Fetch customers from API if table is empty or has no data rows
  const tbody = customerModalTable?.querySelector("tbody");
  if (tbody) {
    // Check if tbody is empty or only has placeholder/loading rows
    const existingRows = tbody.querySelectorAll("tr[data-code]");
    const hasDataRows = existingRows.length > 0;
    
    if (!hasDataRows) {
      // Show loading state
      tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 20px;">Loading customers...</td></tr>';
      
      try {
        console.log("[DEBUG] Fetching customers from /api/customers");
        // Use absolute URL to ensure it works
        const apiUrl = window.location.origin + "/api/customers";
        console.log("[DEBUG] API URL:", apiUrl);
        const response = await fetch(apiUrl, {
          method: "GET",
          headers: {
            "Content-Type": "application/json"
          },
          credentials: "same-origin"
        });
        console.log("[DEBUG] Response status:", response.status);
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const result = await response.json();
        console.log("[DEBUG] Response data:", result);
        
        if (result.success && result.data && Array.isArray(result.data) && result.data.length > 0) {
          // Populate table with customers
          tbody.innerHTML = result.data.map(customer => {
            const code = String(customer.code || "").trim();
            const name = String(customer.name || "").trim();
            const outstanding = String(customer.outstanding || "0.00").trim();
            const text = `${code} ${name}`.toLowerCase();
            return `
              <tr data-code="${code}" data-name="${name}" data-text="${text}">
                <td>${code}</td>
                <td>${name}</td>
                <td>${outstanding}</td>
              </tr>
            `;
          }).join("");
          console.log(`[DEBUG] Loaded ${result.data.length} customers`);
        } else {
          tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 20px; color: #999;">No customers found</td></tr>';
          console.warn("[DEBUG] No customers in response:", result);
        }
      } catch (error) {
        console.error("Error fetching customers:", error);
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; padding: 20px; color: #dc2626;">Error loading customers: ${error.message}</td></tr>`;
      }
    }
  }
  
  if (customerModalSearch) {
    customerModalSearch.value = "";
    filterCustomerRows("");
    customerModalSearch.focus();
  }
};

const closeModal = () => {
  if (!customerModal) return;
  customerModal.classList.add("hidden");
};

const filterCustomerRows = (query) => {
  if (!customerModalTable) return;
  const tokens = query.split(/\s+/).filter(Boolean);
  const rows = customerModalTable.querySelectorAll("tbody tr");
  rows.forEach((row) => {
    const text = (row.dataset.text || "").toLowerCase();
    const matches = tokens.every((token) => text.includes(token));
    row.style.display = matches ? "" : "none";
  });
};

const resolveCustomerCode = (value) => {
  if (!customerCode || !customerModalTable) {
    return;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    customerCode.value = "";
    return;
  }
  const codeMatch = trimmed.split("-")[0].trim();
  const rows = customerModalTable.querySelectorAll("tbody tr");
  let matched = "";
  rows.forEach((row) => {
    const code = row.dataset.code || "";
    const text = (row.dataset.text || "").toLowerCase();
    if (codeMatch && code === codeMatch) {
      matched = code;
    } else if (!matched && text.includes(trimmed.toLowerCase())) {
      matched = code;
    }
  });
  customerCode.value = matched;
};

if (customerInput) {
  customerInput.addEventListener("change", (event) => {
    resolveCustomerCode(event.target.value);
  });
}
if (customerPicker) {
  customerPicker.addEventListener("click", openModal);
}
if (customerClear) {
  customerClear.addEventListener("click", () => {
    if (customerInput) customerInput.value = "";
    if (customerCode) customerCode.value = "";
    if (customerInput) {
      customerInput.readOnly = false;
    }
    if (customerPicker) {
      customerPicker.disabled = false;
    }
  });
}
if (customerModal) {
  customerModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.dataset && target.dataset.close === "customerModal") {
      closeModal();
    }
  });
}
if (customerModalSearch) {
  customerModalSearch.addEventListener("input", (event) => {
    filterCustomerRows(event.target.value.toLowerCase());
  });
}
if (customerModalClear) {
  customerModalClear.addEventListener("click", () => {
    if (customerModalSearch) {
      customerModalSearch.value = "";
      filterCustomerRows("");
      customerModalSearch.focus();
    }
  });
}
if (customerModalTable) {
  customerModalTable.addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    const code = row.dataset.code || "";
    const name = row.dataset.name || "";
    if (customerInput) {
      customerInput.value = `${code} - ${name}`.trim();
    }
    if (customerCode) {
      customerCode.value = code;
    }
    if (customerInput) {
      customerInput.readOnly = true;
    }
    if (customerPicker) {
      customerPicker.disabled = true;
    }
    closeModal();
  });
}

const openSalesmanModal = () => {
  if (!salesmanModal) return;
  salesmanModal.classList.remove("hidden");
  if (salesmanModalSearch) {
    salesmanModalSearch.value = "";
    filterSalesmanRows("");
    salesmanModalSearch.focus();
  }
};

const closeSalesmanModal = () => {
  if (!salesmanModal) return;
  salesmanModal.classList.add("hidden");
};

const filterSalesmanRows = (query) => {
  if (!salesmanModalTable) return;
  const tokens = query.split(/\s+/).filter(Boolean);
  const rows = salesmanModalTable.querySelectorAll("tbody tr");
  rows.forEach((row) => {
    const text = (row.dataset.text || "").toLowerCase();
    const matches = tokens.every((token) => text.includes(token));
    row.style.display = matches ? "" : "none";
  });
};

if (salesmanPicker) {
  salesmanPicker.addEventListener("click", openSalesmanModal);
}
if (salesmanInput) {
  salesmanInput.addEventListener("click", openSalesmanModal);
}
if (salesmanClear) {
  salesmanClear.addEventListener("click", () => {
    if (salesmanInput) salesmanInput.value = "";
    if (salesmanCode) salesmanCode.value = "";
    salesmanClear.style.display = "none";
    if (paymentsFilterForm) {
      paymentsFilterForm.submit();
    }
  });
}
if (salesmanModal) {
  salesmanModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.dataset && target.dataset.close === "salesmanModal") {
      closeSalesmanModal();
    }
  });
}
if (salesmanModalSearch) {
  salesmanModalSearch.addEventListener("input", (event) => {
    filterSalesmanRows(event.target.value.toLowerCase());
  });
}
if (salesmanModalClear) {
  salesmanModalClear.addEventListener("click", () => {
    if (salesmanModalSearch) {
      salesmanModalSearch.value = "";
      filterSalesmanRows("");
      salesmanModalSearch.focus();
    }
  });
}
if (salesmanModalTable) {
  salesmanModalTable.addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    const code = row.dataset.code || "";
    const name = row.dataset.name || "";
    if (salesmanInput) {
      salesmanInput.value = code ? `${code} - ${name}`.trim() : name;
    }
    if (salesmanCode) {
      salesmanCode.value = code;
    }
    if (salesmanClear) {
      salesmanClear.style.display = code ? "block" : "none";
    }
    closeSalesmanModal();
    if (paymentsFilterForm) {
      paymentsFilterForm.submit();
    }
  });
}


if (paymentsFilterForm) {
  paymentsFilterForm.addEventListener("submit", (event) => {
    if (customerCode && !customerCode.value && customerInput && customerInput.value) {
      resolveCustomerCode(customerInput.value);
    }
    if (customerCode && !customerCode.value && (!customerInput || !customerInput.value)) {
      event.preventDefault();
      openModal();
    }
  });
}
