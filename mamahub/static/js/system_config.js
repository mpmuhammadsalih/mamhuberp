document.addEventListener("DOMContentLoaded", () => {
  const dblocationSelect = document.getElementById("dblocationSelect");
  const dblocationDisplay = document.getElementById("dblocationDisplay");
  const dblocationPicker = document.getElementById("dblocationPicker");
  const dblocationClear = document.getElementById("dblocationClear");
  const dblocationModal = document.getElementById("dblocationModal");
  const dblocationModalSearch = document.getElementById("dblocationModalSearch");
  const dblocationModalClear = document.getElementById("dblocationModalClear");
  const dblocationModalTable = document.getElementById("dblocationModalTable");

  const openModal = () => {
    if (!dblocationModal) return;
    dblocationModal.classList.remove("hidden");
    if (dblocationModalSearch) {
      dblocationModalSearch.value = "";
      filterRows("");
      dblocationModalSearch.focus();
    }
  };

  const closeModal = () => {
    if (!dblocationModal) return;
    dblocationModal.classList.add("hidden");
  };

  const filterRows = (query) => {
    if (!dblocationModalTable) return;
    const tokens = query.split(/\s+/).filter(Boolean);
    const rows = dblocationModalTable.querySelectorAll("tbody tr");
    rows.forEach((row) => {
      const text = (row.textContent || "").toLowerCase();
      const matches = tokens.every((token) => text.includes(token));
      row.style.display = matches ? "" : "none";
    });
  };

  if (dblocationPicker) {
    dblocationPicker.addEventListener("click", openModal);
  }
  if (dblocationDisplay) {
    dblocationDisplay.addEventListener("click", openModal);
  }
  if (dblocationModal) {
    dblocationModal.addEventListener("click", (event) => {
      const target = event.target;
      if (target && target.dataset && target.dataset.close === "dblocationModal") {
        closeModal();
      }
    });
  }
  if (dblocationModalSearch) {
    dblocationModalSearch.addEventListener("input", (event) => {
      filterRows(event.target.value.toLowerCase());
    });
  }
  if (dblocationModalClear) {
    dblocationModalClear.addEventListener("click", () => {
      if (dblocationModalSearch) {
        dblocationModalSearch.value = "";
        filterRows("");
        dblocationModalSearch.focus();
      }
    });
  }
  if (dblocationModalTable) {
    dblocationModalTable.addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      if (!row) return;
      const code = row.dataset.code || "";
      if (dblocationDisplay) {
        dblocationDisplay.value = code;
      }
      if (dblocationSelect) {
        dblocationSelect.value = code;
      }
      if (dblocationClear) {
        dblocationClear.style.display = code ? "block" : "none";
      }
      closeModal();
    });
  }
  if (dblocationClear) {
    dblocationClear.addEventListener("click", () => {
      if (dblocationDisplay) dblocationDisplay.value = "";
      if (dblocationSelect) dblocationSelect.value = "";
      if (dblocationClear) dblocationClear.style.display = "none";
    });
  }
});
