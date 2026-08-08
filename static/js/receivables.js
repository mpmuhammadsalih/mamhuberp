const customerInput = document.getElementById("receivablesCustomerInput");
const customerClear = document.getElementById("receivablesCustomerClear");

const lockCustomer = () => {
  if (customerInput && customerInput.value.trim()) {
    customerInput.readOnly = true;
  }
};

const unlockCustomer = () => {
  if (customerInput) {
    customerInput.readOnly = false;
  }
};

if (customerInput) {
  if (customerInput.value.trim()) {
    lockCustomer();
  }
  customerInput.addEventListener("change", () => {
    lockCustomer();
  });
}

if (customerClear) {
  customerClear.addEventListener("click", () => {
    if (customerInput) {
      customerInput.value = "";
    }
    unlockCustomer();
  });
}
const tabs = document.querySelectorAll(".tab");
const wrappers = document.querySelectorAll(".table-wrapper");
const searchInput = document.getElementById("tableSearch");

const filterTableRows = (query) => {
  const activeWrapper = document.querySelector(".table-wrapper:not(.hidden)");
  if (!activeWrapper) {
    return;
  }

  const table = activeWrapper.querySelector("table");
  if (!table) {
    return;
  }

  const rows = table.querySelectorAll("tbody tr");
  rows.forEach((row) => {
    const text = row.innerText.toLowerCase();
    row.style.display = text.includes(query) ? "" : "none";
  });
};

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((btn) => btn.classList.remove("tab--active"));
    tab.classList.add("tab--active");

    const target = tab.dataset.target;
    wrappers.forEach((wrapper) => {
      wrapper.classList.toggle("hidden", wrapper.id !== target);
    });

    if (searchInput) {
      searchInput.value = "";
      filterTableRows("");
    }
  });
});

if (searchInput) {
  searchInput.addEventListener("input", (event) => {
    filterTableRows(event.target.value.toLowerCase());
  });
}
