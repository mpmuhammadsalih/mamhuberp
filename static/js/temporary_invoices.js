document.addEventListener('DOMContentLoaded', () => {
  const table = document.getElementById('temporaryInvoicesTable');
  let activeInvoiceTab = 'all';

  const customerSelect = document.getElementById('tempInvoiceCustomer');
  const salesmanSelect = document.getElementById('tempInvoiceSalesman');
  const customerDisplay = document.getElementById('tempInvoiceCustomerDisplay');
  const salesmanDisplay = document.getElementById('tempInvoiceSalesmanDisplay');
  const customerPicker = document.getElementById('tempInvoiceCustomerPicker');
  const salesmanPicker = document.getElementById('tempInvoiceSalesmanPicker');
  const customerClear = document.getElementById('tempInvoiceCustomerClear');
  const salesmanClear = document.getElementById('tempInvoiceSalesmanClear');

  const customerModal = document.getElementById('tempInvoiceCustomerModal');
  const salesmanModal = document.getElementById('tempInvoiceSalesmanModal');
  const customerSearch = document.getElementById('tempInvoiceCustomerSearch');
  const salesmanSearch = document.getElementById('tempInvoiceSalesmanSearch');
  const customerSearchClear = document.getElementById('tempInvoiceCustomerSearchClear');
  const salesmanSearchClear = document.getElementById('tempInvoiceSalesmanSearchClear');
  const customerTable = document.getElementById('tempInvoiceCustomerTable');
  const salesmanTable = document.getElementById('tempInvoiceSalesmanTable');
  const dateFrom = document.getElementById('tempInvoiceDateFrom');
  const dateTo = document.getElementById('tempInvoiceDateTo');
  const billnoInput = document.getElementById('tempInvoiceBillno');
  const ordernoInput = document.getElementById('tempInvoiceOrderno');
  const billTypeSel = document.getElementById('tempInvoiceBillType');
  const txnKindSel = document.getElementById('tempInvoiceTxnKind');
  const createdByInput = document.getElementById('tempInvoiceCreatedBy');
  const netMinInput = document.getElementById('tempInvoiceNetMin');
  const netMaxInput = document.getElementById('tempInvoiceNetMax');
  const btnFilter = document.getElementById('tempInvoiceFilter');
  const btnClear = document.getElementById('tempInvoiceClear');
  const btnExport = document.getElementById('tempInvoiceExport');
  const perPageHidden = document.getElementById('tempInvoicePerPage');

  function getTempInvoicesPageUrl() {
    const el = document.getElementById('tempInvoicesPageUrl');
    if (!el || !el.textContent) return '/temporary-invoices';
    try {
      return JSON.parse(el.textContent);
    } catch (_) {
      return '/temporary-invoices';
    }
  }

  if (btnFilter) {
    btnFilter.addEventListener('click', () => {
      const params = new URLSearchParams();
      if (customerSelect && customerSelect.value) params.append('customercode', customerSelect.value);
      if (salesmanSelect && salesmanSelect.value) params.append('salesmancode', salesmanSelect.value);
      if (dateFrom && dateFrom.value) params.append('date_from', dateFrom.value);
      if (dateTo && dateTo.value) params.append('date_to', dateTo.value);
      if (billnoInput && billnoInput.value.trim()) params.append('billno', billnoInput.value.trim());
      if (ordernoInput && ordernoInput.value.trim()) params.append('orderno', ordernoInput.value.trim());
      if (billTypeSel && billTypeSel.value) params.append('bill_type', billTypeSel.value);
      if (txnKindSel && txnKindSel.value && txnKindSel.value !== 'all') {
        params.append('txn_kind', txnKindSel.value);
      }
      if (createdByInput && createdByInput.value.trim()) params.append('created_by', createdByInput.value.trim());
      if (netMinInput && netMinInput.value.trim()) params.append('net_min', netMinInput.value.trim());
      if (netMaxInput && netMaxInput.value.trim()) params.append('net_max', netMaxInput.value.trim());
      params.append('page', '1');
      if (perPageHidden && perPageHidden.value && String(perPageHidden.value).trim()) {
        params.append('per_page', String(perPageHidden.value).trim());
      }
      const base = getTempInvoicesPageUrl();
      window.location.href = base + (params.toString() ? `?${params.toString()}` : '');
    });
  }

  if (btnClear) {
    btnClear.addEventListener('click', () => {
      if (customerSelect) customerSelect.value = '';
      if (salesmanSelect) salesmanSelect.value = '';
      if (customerDisplay) customerDisplay.value = '';
      if (salesmanDisplay) salesmanDisplay.value = '';
      toggleClearButton(customerClear, '');
      toggleClearButton(salesmanClear, '');
      if (dateFrom) dateFrom.value = '';
      if (dateTo) dateTo.value = '';
      if (billnoInput) billnoInput.value = '';
      if (ordernoInput) ordernoInput.value = '';
      if (billTypeSel) billTypeSel.value = '';
      if (txnKindSel) txnKindSel.value = 'all';
      if (createdByInput) createdByInput.value = '';
      if (netMinInput) netMinInput.value = '';
      if (netMaxInput) netMaxInput.value = '';
      window.location.href = getTempInvoicesPageUrl();
    });
  }

  [billnoInput, ordernoInput, createdByInput, netMinInput, netMaxInput].forEach(inp => {
    if (!inp || !btnFilter) return;
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        btnFilter.click();
      }
    });
  });

  function applyInvoiceTab(tab) {
    if (!table) return;
    activeInvoiceTab = tab;
    const tabBar = document.getElementById('tempInvoiceTabBar');
    if (tabBar) {
      tabBar.querySelectorAll('.ti-inv-tab-btn').forEach(btn => {
        const on = btn.dataset.invTab === tab;
        btn.classList.toggle('is-active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
      });
    }
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const dataRows = Array.from(tbody.querySelectorAll('tr.ti-inv-data-row'));
    let visibleCount = 0;
    let sum = 0;
    dataRows.forEach(row => {
      const match = tab === 'all' || row.dataset.invoiceTab === tab;
      row.style.display = match ? '' : 'none';
      if (match) {
        visibleCount += 1;
        sum += parseFloat(row.dataset.netAmount || '0') || 0;
      }
    });
    const tabEmpty = document.getElementById('tempInvoicesTabEmpty');
    const tfoot = document.getElementById('tempInvoicesTableFoot');
    if (tabEmpty) {
      tabEmpty.style.display = visibleCount === 0 ? '' : 'none';
    }
    if (tfoot) {
      tfoot.style.display = visibleCount === 0 ? 'none' : '';
    }
    const totalEl = document.getElementById('tempInvoicesTotalAmount');
    if (totalEl) {
      totalEl.textContent = visibleCount === 0 ? '0.00' : sum.toFixed(2);
    }
    const slBase = table ? parseInt(table.dataset.slBase || '0', 10) || 0 : 0;
    let sl = slBase + 1;
    dataRows.forEach(row => {
      if (row.style.display !== 'none') {
        const slCell = row.children[0];
        if (slCell) slCell.textContent = String(sl++);
      }
    });
  }

  const tabBar = document.getElementById('tempInvoiceTabBar');
  if (tabBar && table) {
    tabBar.querySelectorAll('.ti-inv-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        applyInvoiceTab(btn.dataset.invTab || 'all');
      });
    });
    applyInvoiceTab(activeInvoiceTab);
  }

  function getTempInvoiceModifyUrl() {
    const el = document.getElementById('tempInvoiceModifyUrl');
    if (!el || !el.textContent) return '/temporary-invoices/modify';
    try {
      return JSON.parse(el.textContent);
    } catch (_) {
      return '/temporary-invoices/modify';
    }
  }

  function showTemporaryInvoiceModifyNavOverlay() {
    if (typeof window.showLoadingOverlay === 'function') {
      window.showLoadingOverlay('Opening modify…');
    }
  }

  function goToModifyInvoice(billno) {
    const bn = String(billno || '').trim();
    if (!bn) return;
    const base = getTempInvoiceModifyUrl();
    const sep = base.includes('?') ? '&' : '?';
    showTemporaryInvoiceModifyNavOverlay();
    window.location.href = `${base}${sep}billno=${encodeURIComponent(bn)}`;
  }

  const toolbarModify = document.getElementById('tempInvoiceToolbarModify');
  if (toolbarModify) {
    toolbarModify.addEventListener('click', () => {
      showTemporaryInvoiceModifyNavOverlay();
    });
  }

  if (table) {
    const listTbody = table.querySelector('tbody');
    if (listTbody) {
      listTbody.addEventListener('click', ev => {
        const el = ev.target;
        if (!(el instanceof Element)) return;

        const tr = el.closest('tr.ti-inv-data-row');
        if (!tr || tr.style.display === 'none') return;
        const bn = (tr.dataset.billno || '').trim();
        if (!bn) return;
        goToModifyInvoice(bn);
      });
    }
  }

  if (btnExport) {
    btnExport.addEventListener('click', () => {
      if (!table) return;
      const rows = Array.from(table.querySelectorAll('tbody tr.ti-inv-data-row')).filter(
        row => row.style.display !== 'none'
      );
      if (!rows.length) {
        alert('No data to export.');
        return;
      }

      const headers = Array.from(table.querySelectorAll('thead th')).filter(
        th => !th.classList.contains('ti-inv-csv-skip')
      );
      const headerTexts = headers.map(th => {
        let text = th.textContent.trim();
        const indicator = th.querySelector('.sort-indicator');
        if (indicator) {
          text = text.replace(indicator.textContent, '').trim();
        }
        return text;
      });

      let csvContent = headerTexts.join(',') + '\n';
      rows.forEach(row => {
        const cells = Array.from(row.querySelectorAll('td')).filter(
          cell => !cell.classList.contains('ti-inv-csv-skip')
        );
        const rowData = cells.map(cell => {
          let cellText = cell.textContent.trim();
          if (cellText.includes(',') || cellText.includes('"') || cellText.includes('\n')) {
            cellText = '"' + cellText.replace(/"/g, '""') + '"';
          }
          return cellText;
        });
        csvContent += rowData.join(',') + '\n';
      });

      const tfoot = table.querySelector('tfoot');
      if (tfoot && tfoot.style.display !== 'none') {
        const totalRow = tfoot.querySelector('tr');
        if (totalRow) {
          const totalCells = Array.from(totalRow.querySelectorAll('td')).filter(
            cell => !cell.classList.contains('ti-inv-csv-skip')
          );
          const totalData = totalCells.map(cell => {
            let cellText = cell.textContent.trim();
            if (cellText.includes(',') || cellText.includes('"') || cellText.includes('\n')) {
              cellText = '"' + cellText.replace(/"/g, '""') + '"';
            }
            return cellText;
          });
          csvContent += totalData.join(',') + '\n';
        }
      }

      const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      const dateStr = new Date().toISOString().split('T')[0];
      const tabSuffix = activeInvoiceTab ? `_${activeInvoiceTab}` : '';
      link.setAttribute('href', url);
      link.setAttribute('download', `temporary_invoices${tabSuffix}_${dateStr}.csv`);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  }

  if (table) {
    const headers = table.querySelectorAll('th.sortable');
    headers.forEach(header => {
      header.addEventListener('click', () => handleSort(header));
    });
  }

  initPopupSearch({
    displayInput: customerDisplay,
    hiddenInput: customerSelect,
    pickerButton: customerPicker,
    clearButton: customerClear,
    modal: customerModal,
    searchInput: customerSearch,
    searchClear: customerSearchClear,
    table: customerTable,
  });

  initPopupSearch({
    displayInput: salesmanDisplay,
    hiddenInput: salesmanSelect,
    pickerButton: salesmanPicker,
    clearButton: salesmanClear,
    modal: salesmanModal,
    searchInput: salesmanSearch,
    searchClear: salesmanSearchClear,
    table: salesmanTable,
  });

  function handleSort(header) {
    if (!table) return;
    const sortKey = header.dataset.sort;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr.ti-inv-data-row'));
    if (!rows.length) return;

    const currentDir = header.dataset.sortDir || 'none';
    const newDir = currentDir === 'asc' ? 'desc' : 'asc';
    table.querySelectorAll('th.sortable').forEach(th => {
      th.dataset.sortDir = 'none';
      const indicator = th.querySelector('.sort-indicator');
      if (indicator) indicator.textContent = '';
    });
    header.dataset.sortDir = newDir;
    const indicator = header.querySelector('.sort-indicator');
    if (indicator) indicator.textContent = newDir === 'asc' ? '▲' : '▼';

    rows.sort((a, b) => compareCells(a, b, sortKey, newDir));
    rows.forEach(row => tbody.appendChild(row));
    const tabEmpty = document.getElementById('tempInvoicesTabEmpty');
    if (tabEmpty) tbody.appendChild(tabEmpty);
    applyInvoiceTab(activeInvoiceTab);
  }

  function initPopupSearch(config) {
    const {
      displayInput,
      hiddenInput,
      pickerButton,
      clearButton,
      modal,
      searchInput,
      searchClear,
      table,
    } = config;

    if (!displayInput || !hiddenInput || !pickerButton || !modal || !searchInput || !table) return;

    const rows = Array.from(table.querySelectorAll('tbody tr'));

    function openModal() {
      modal.classList.remove('hidden');
      searchInput.value = '';
      filterRows('');
      searchInput.focus();
    }

    function closeModal() {
      modal.classList.add('hidden');
    }

    function filterRows(term) {
      const normalized = term.trim().toLowerCase();
      rows.forEach(row => {
        const code = (row.dataset.code || '').toLowerCase();
        const name = (row.dataset.name || '').toLowerCase();
        const visible = !normalized || code.includes(normalized) || name.includes(normalized);
        row.style.display = visible ? '' : 'none';
      });
    }

    function setSelection(code, name) {
      hiddenInput.value = code || '';
      if (code) {
        displayInput.value = name ? `${code} - ${name}` : code;
      } else {
        displayInput.value = '';
      }
      toggleClearButton(clearButton, hiddenInput.value);
    }

    function setDisplayFromCode() {
      if (!hiddenInput.value) {
        toggleClearButton(clearButton, '');
        return;
      }
      const match = rows.find(row => String(row.dataset.code) === String(hiddenInput.value));
      if (match) {
        setSelection(match.dataset.code || '', match.dataset.name || '');
      } else {
        toggleClearButton(clearButton, hiddenInput.value);
      }
    }

    pickerButton.addEventListener('click', openModal);
    displayInput.addEventListener('click', openModal);

    modal.addEventListener('click', event => {
      const target = event.target;
      if (target instanceof HTMLElement && target.dataset.close) {
        closeModal();
      }
    });

    const modalCloseButtons = modal.querySelectorAll('.modal__close, .modal__overlay');
    modalCloseButtons.forEach(button => {
      button.addEventListener('click', () => closeModal());
    });

    rows.forEach(row => {
      row.addEventListener('click', () => {
        setSelection(row.dataset.code || '', row.dataset.name || '');
        closeModal();
      });
    });

    searchInput.addEventListener('input', event => {
      const value = event.target.value || '';
      filterRows(value);
      toggleClearButton(searchClear, value);
    });

    if (searchClear) {
      searchClear.addEventListener('click', () => {
        searchInput.value = '';
        filterRows('');
        toggleClearButton(searchClear, '');
        searchInput.focus();
      });
    }

    if (clearButton) {
      clearButton.addEventListener('click', () => {
        hiddenInput.value = '';
        displayInput.value = '';
        toggleClearButton(clearButton, '');
      });
    }

    setDisplayFromCode();
  }

  function toggleClearButton(button, value) {
    if (!button) return;
    button.style.display = value ? 'inline-flex' : 'none';
  }

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (customerModal && !customerModal.classList.contains('hidden')) {
      customerModal.classList.add('hidden');
    }
    if (salesmanModal && !salesmanModal.classList.contains('hidden')) {
      salesmanModal.classList.add('hidden');
    }
  });

  function compareCells(a, b, sortKey, direction) {
    const indexMap = {
      slno: 0,
      billno: 1,
      billdate: 2,
      customercode: 3,
      customername: 4,
      orderno: 5,
      createdby: 6,
      netbillamount: 7,
      billtype: 8,
    };
    const index = indexMap[sortKey] ?? 0;
    const aText = (a.children[index]?.textContent || '').trim();
    const bText = (b.children[index]?.textContent || '').trim();

    let result = 0;
    if (sortKey === 'slno' || sortKey === 'billno' || sortKey === 'netbillamount') {
      result = parseFloat(aText || '0') - parseFloat(bText || '0');
    } else if (sortKey === 'billdate') {
      const aDate = parseDate(aText);
      const bDate = parseDate(bText);
      result = aDate - bDate;
    } else {
      result = aText.localeCompare(bText);
    }

    return direction === 'asc' ? result : -result;
  }

  function parseDate(value) {
    if (!value || value === '-') return 0;
    const parts = value.split('-');
    if (parts.length !== 3) return 0;
    const [day, monthStr, year] = parts;
    const month = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
      .indexOf(monthStr.toUpperCase());
    if (month < 0) return 0;
    return new Date(parseInt(year, 10), month, parseInt(day, 10)).getTime();
  }
});
