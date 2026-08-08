const searchInputs = document.querySelectorAll(".table-search");
const clearButtons = document.querySelectorAll(".search-clear");

const parseNumber = (value) => {
  const cleaned = value.replace(/,/g, "").trim();
  const number = Number.parseFloat(cleaned);
  return Number.isNaN(number) ? 0 : number;
};

const updateTotals = (tableId, countTargetId, amountTargetId, countIndex, amountIndex) => {
  const table = document.getElementById(tableId);
  if (!table) {
    return;
  }

  const rows = table.querySelectorAll("tbody tr");
  let countSum = 0;
  let amountSum = 0;

  rows.forEach((row) => {
    if (row.style.display === "none") {
      return;
    }
    const cells = row.querySelectorAll("td");
    if (cells[countIndex]) {
      countSum += parseNumber(cells[countIndex].innerText);
    }
    if (cells[amountIndex]) {
      amountSum += parseNumber(cells[amountIndex].innerText);
    }
  });

  const countTarget = document.getElementById(countTargetId);
  const amountTarget = document.getElementById(amountTargetId);
  if (countTarget) {
    countTarget.textContent = countSum;
  }
  if (amountTarget) {
    amountTarget.textContent = amountSum;
  }
};

const filterTable = (tableId, query) => {
  const table = document.getElementById(tableId);
  if (!table) {
    return;
  }

  const tokens = query.split(/\s+/).filter(Boolean);
  const rows = table.querySelectorAll("tbody tr");
  
  // Code column index is 1, Name column index is 2 (Sl No=0, Code=1, Name=2)
  const codeColumnIndex = 1;
  const nameColumnIndex = 2;
  
  rows.forEach((row) => {
    const cells = row.querySelectorAll("td");
    if (cells.length <= nameColumnIndex) {
      row.style.display = "";
      return;
    }
    
    const codeCell = cells[codeColumnIndex];
    const nameCell = cells[nameColumnIndex];
    const codeText = (codeCell.innerText || "").toLowerCase();
    const nameText = (nameCell.innerText || "").toLowerCase();
    
    // Combine code and name for searching
    const searchText = `${codeText} ${nameText}`;
    
    if (!query.trim()) {
      row.style.display = "";
    } else {
      const matches = tokens.every((token) => searchText.includes(token));
      row.style.display = matches ? "" : "none";
    }
  });

  // Update totals for other tables if needed
  if (tableId === "customer-table") {
    updateTotals("customer-table", "customer-total-count", "customer-total-amount", 4, 5);
  }
  if (tableId === "salesman-table") {
    updateTotals("salesman-table", "salesman-total-count", "salesman-total-amount", 3, 4);
  }
  if (tableId === "route-table") {
    updateTotals("route-table", "route-total-count", "route-total-amount", 3, 4);
  }
};

searchInputs.forEach((input) => {
  input.addEventListener("input", (event) => {
    const tableId = event.target.dataset.table;
    const query = event.target.value.toLowerCase();
    filterTable(tableId, query);
    
    // Show/hide clear button
    const clearBtn = document.querySelector(`.search-clear[data-table="${tableId}"]`);
    if (clearBtn) {
      clearBtn.style.display = query.trim() ? "block" : "none";
    }
  });
});

clearButtons.forEach((button) => {
  button.addEventListener("click", (event) => {
    const tableId = event.currentTarget.dataset.table;
    const input = document.querySelector(`.table-search[data-table="${tableId}"]`);
    if (!input) {
      return;
    }
    input.value = "";
    filterTable(tableId, "");
    event.currentTarget.style.display = "none";
    input.focus();
  });
});

updateTotals("customer-table", "customer-total-count", "customer-total-amount", 4, 5);
updateTotals("salesman-table", "salesman-total-count", "salesman-total-amount", 3, 4);
updateTotals("route-table", "route-total-count", "route-total-amount", 3, 4);

// Handle dbkey switch for admin users
const dbkeySelect = document.getElementById("dbkey-select");
if (dbkeySelect) {
  dbkeySelect.addEventListener("change", function() {
    const selectedDbkey = this.value;
    
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/dbkey/switch";
    
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "dbkey";
    input.value = selectedDbkey;
    form.appendChild(input);
    
    document.body.appendChild(form);
    form.submit();
  });
}

// Show popup message if database was switched
(function() {
  const urlParams = new URLSearchParams(window.location.search);
  const switched = urlParams.get('switched');
  if (switched) {
    // Wait for body to be ready
    if (document.body) {
      showPopup(switched);
    } else {
      window.addEventListener('DOMContentLoaded', function() {
        showPopup(switched);
      });
    }
  }
  
  function showPopup(dbkey) {
    const popup = document.createElement('div');
    popup.className = 'switch-popup';
    popup.textContent = `Switched to location: ${dbkey}`;
    document.body.appendChild(popup);
    
    // Remove popup after 3 seconds
    setTimeout(() => {
      popup.style.opacity = '0';
      setTimeout(() => {
        if (popup.parentNode) {
          popup.remove();
        }
      }, 300);
    }, 3000);
    
    // Clean URL
    const newUrl = window.location.pathname;
    window.history.replaceState({}, '', newUrl);
  }
})();
