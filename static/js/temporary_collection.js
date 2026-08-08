// Temporary Collection Page JavaScript

let invoiceDetails = []; // Mirror of allInvoiceDetails (always full list for save/edit)
let allInvoiceDetails = []; // All invoice lines from API
/** Customer codes with invoice rows visible under the category row */
let expandedCustomers = new Set();
let isNewMode = false;
let saveInProgress = false;
/** After a successful save, stay locked until Back / full page navigation (stops double-save when PDF popup blocks redirect). */
let tcSaveCompleted = false;

/** Global token from ``base.html`` / JSON responses · prevents replay of the same POST. */
let tcSaveNonce =
  typeof window !== "undefined" && window.__GLOBAL_SAVE_NONCE
    ? String(window.__GLOBAL_SAVE_NONCE)
    : "";

function applyTemporaryCollectionSaveNonce(data) {
  if (data && typeof data.save_nonce === "string" && data.save_nonce) {
    tcSaveNonce = data.save_nonce;
    if (typeof window !== "undefined") {
      window.__GLOBAL_SAVE_NONCE = data.save_nonce;
    }
  }
}

// Initialize finalCollection for each invoice (defaults to collection amount)
function initializeFinalCollection() {
  invoiceDetails.forEach(item => {
    if (item.finalCollection === undefined) {
      item.finalCollection = item.collection || 0;
    }
  });
  allInvoiceDetails.forEach(item => {
    if (item.finalCollection === undefined) {
      item.finalCollection = item.collection || 0;
    }
  });
}

// Initialize page
document.addEventListener("DOMContentLoaded", () => {
  initializePage();
  setupEventListeners();
});

function initializePage() {
  fetchTransactionDate();
  // Always start in "new" mode (no New/Query buttons)
  handleNew();
  const urlParams = new URLSearchParams(window.location.search);
  const salesmanCodeFromUrl = urlParams.get('salesman_code');
  if (salesmanCodeFromUrl) {
    document.getElementById('salesmanCode').value = salesmanCodeFromUrl;
    setTimeout(() => handleSalesmanCodeEnter(), 300);
  }
}

function setupEventListeners() {
  document.getElementById('btnSave').addEventListener('click', handleSave);
  document.getElementById('btnExit').addEventListener('click', handleExit);
}

async function fetchTransactionDate() {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const billFromList = (urlParams.get('bill_date') || '').trim();
    if (billFromList.length >= 10) {
      const el = document.getElementById('transactionDate');
      if (el) el.value = billFromList.slice(0, 10);
      return;
    }
    const response = await fetch('/accounts/temporary-collection/api/transaction-date');
    const data = await response.json();
    if (data.success && data.transaction_date) {
      document.getElementById('transactionDate').value = data.transaction_date;
    }
  } catch (error) {
    console.error('Error fetching transaction date:', error);
  }
}

async function handleSalesmanCodeEnter() {
  const salesmanCode = document.getElementById('salesmanCode').value.trim();
  if (!salesmanCode) {
    alert('No salesman code on this page. Open Temporary Collection from the list and choose a salesman.');
    return;
  }

  if (!isNewMode) {
    alert('Please click New button first');
    return;
  }
  
  try {
    const response = await fetch(`/accounts/temporary-collection/api/salesman?salesman_code=${encodeURIComponent(salesmanCode)}`);
    const data = await response.json();
    
    if (data.success && data.salesman) {
      document.getElementById('salesmanName').value = data.salesman.salesmanname || '';
      // Load invoice details
      await loadInvoiceDetails();
    } else {
      alert('Salesman not found');
      document.getElementById('salesmanCode').value = '';
      document.getElementById('salesmanName').value = '';
    }
  } catch (error) {
    console.error('Error fetching salesman:', error);
    alert('Error fetching salesman information');
  }
}

async function loadInvoiceDetails() {
  const salesmanCode = document.getElementById('salesmanCode').value.trim();
  if (!salesmanCode) return;
  
  try {
    const qs = new URLSearchParams({ salesman_code: salesmanCode });
    const urlQs = new URLSearchParams(window.location.search);
    const billFromUrl = (urlQs.get('bill_date') || '').trim();
    if (billFromUrl.length >= 10) qs.set('bill_date', billFromUrl.slice(0, 10));
    const ls = (urlQs.get('line_status') || urlQs.get('online_status') || '').trim();
    if (ls === '0' || ls === '1' || ls === '2') qs.set('line_status', ls);
    const url = '/accounts/temporary-collection/api/invoice-details?' + qs.toString();

    const response = await fetch(url);
    const data = await response.json();
    
    console.log('[DEBUG] Invoice details response:', data);
    
    if (data.success) {
      allInvoiceDetails = data.invoices || [];
      invoiceDetails = allInvoiceDetails;
      expandedCustomers.clear();
      // Initialize finalCollection with collection amount
      initializeFinalCollection();
      console.log('[DEBUG] Loaded invoices:', allInvoiceDetails.length);
      
      // Show message if no data available
      if (allInvoiceDetails.length === 0) {
        alert('No data.');
      }

      renderCategoryTree();
    } else {
      console.error('[ERROR] Failed to load invoice details:', data.error);
      alert('Error loading invoice details: ' + (data.error || 'Unknown error'));
      allInvoiceDetails = [];
      invoiceDetails = [];
      expandedCustomers.clear();
      renderCategoryTree();
    }
  } catch (error) {
    console.error('[ERROR] Error loading invoice details:', error);
    alert('Error loading invoice details: ' + error.message);
    allInvoiceDetails = [];
    invoiceDetails = [];
    expandedCustomers.clear();
    renderCategoryTree();
  }
}

function buildCustomerSummaries() {
  const customerMap = new Map();

  allInvoiceDetails.forEach(item => {
    const customerCode = String(item.customercode || '').trim();
    const customerName = String(item.customername || '').trim();
    const collection = parseFloat(item.collection || 0);
    const finalCollection =
      item.finalCollection !== undefined ? parseFloat(item.finalCollection || 0) : collection;
    const hasEdited =
      item.finalCollection !== undefined && Math.abs(finalCollection - collection) > 0.01;

    if (!customerMap.has(customerCode)) {
      customerMap.set(customerCode, {
        customercode: customerCode,
        customername: customerName,
        invoiceCount: 0,
        totalCollection: 0,
        totalFinalCollection: 0,
        hasEdited: false
      });
    }

    const customer = customerMap.get(customerCode);
    customer.invoiceCount += 1;
    customer.totalCollection += collection;
    customer.totalFinalCollection += finalCollection;
    if (hasEdited) {
      customer.hasEdited = true;
    }
  });

  return Array.from(customerMap.values()).sort((a, b) => {
    return (a.customername || '').localeCompare(b.customername || '');
  });
}

function toggleCustomerExpand(customerCode) {
  if (expandedCustomers.has(customerCode)) {
    expandedCustomers.delete(customerCode);
  } else {
    expandedCustomers.add(customerCode);
  }
  renderCategoryTree();
}

function appendInvoiceLeafRow(tbody, item, slNo) {
  const row = document.createElement('tr');
  row.classList.add('tc-cat-leaf');
  row.dataset.invoiceId = item.id || '';
  row.dataset.invoiceNo = item.billno || '';
  row.dataset.customerCode = String(item.customercode || '');
  row.dataset.customerName = String(item.customername || '');
  row.dataset.outstanding = item.outstanding || 0;
  row.dataset.collection = item.collection || 0;
  row.dataset.salesmanCode = item.salesmancode || '';

  if (item.finalCollection === undefined) {
    item.finalCollection = item.collection || 0;
  }

  const finalCollection = parseFloat(item.finalCollection || item.collection || 0);
  const billDate = item.billdate ? formatDate(item.billdate) : '-';
  const balance = parseFloat(item.balance) || 0;
  const collected = parseFloat(item.collection || 0);

  if (balance < collected) {
    row.style.backgroundColor = '#fecaca';
    row.style.color = '#991b1b';
  }

  row.innerHTML = `
      <td class="tc-cat-leaf-gutter" aria-hidden="true"></td>
      <td>${slNo}</td>
      <td>${item.customercode || '-'}</td>
      <td>${item.customername || '-'}</td>
      <td>${item.billno || '-'}</td>
      <td>${billDate}</td>
      <td style="text-align: right;">${formatNumber(item.outstanding || 0)}</td>
      <td style="text-align: right;">${formatNumber(balance)}</td>
      <td style="text-align: right;">${formatNumber(item.collection || 0)}</td>
      <td style="text-align: right;" class="editable-final-collection ${item.finalCollection !== undefined && item.finalCollection !== item.collection ? 'final-collection-edited' : ''}" data-original-value="${finalCollection}" data-invoice-id="${item.id || ''}" title="Click to edit">
        <span class="final-collection-display">${formatNumber(finalCollection)}</span>
        <input type="number" class="final-collection-input" style="display: none; width: 100px; text-align: right; padding: 4px; border: 1px solid #2563eb; border-radius: 4px;" step="0.01" min="0" max="${item.outstanding || 0}" value="${finalCollection}" />
      </td>
      <td>${item.id || '-'}</td>
      <td>${item.salesmancode || '-'}</td>
      <td>${item.salesmanname || '-'}</td>
      <td>
        <button type="button" class="button button--small button--danger remove-invoice-btn" data-invoice-id="${item.id || ''}" title="Remove invoice" style="padding: 4px 8px; font-size: 11px;">×</button>
      </td>
    `;

  const removeBtn = row.querySelector('.remove-invoice-btn');
  if (removeBtn) {
    removeBtn.addEventListener('click', e => {
      e.stopPropagation();
      removeInvoiceDetail(item.id);
    });
  }

  const finalCollectionCell = row.querySelector('.editable-final-collection');
  const finalCollectionDisplay = row.querySelector('.final-collection-display');
  const finalCollectionInput = row.querySelector('.final-collection-input');

  if (finalCollectionCell && finalCollectionDisplay && finalCollectionInput) {
    const enableEditing = e => {
      if (e) e.stopPropagation();
      if (finalCollectionInput.style.display === 'inline-block') return;

      document.querySelectorAll('.final-collection-input').forEach(input => {
        if (input !== finalCollectionInput && input.style.display === 'inline-block') {
          const otherRow = input.closest('tr');
          if (otherRow) {
            const otherCell = otherRow.querySelector('.editable-final-collection');
            const otherDisplay = otherRow.querySelector('.final-collection-display');
            if (otherCell && otherDisplay) {
              const otherOriginalValue = otherCell.dataset.originalValue;
              otherDisplay.textContent = formatNumber(parseFloat(otherOriginalValue || 0));
              otherDisplay.style.display = 'inline';
              input.style.display = 'none';
              input.value = otherOriginalValue;
            }
          }
        }
      });

      finalCollectionDisplay.style.display = 'none';
      finalCollectionInput.style.display = 'inline-block';
      setTimeout(() => {
        finalCollectionInput.focus();
        finalCollectionInput.select();
      }, 10);
    };

    finalCollectionCell.addEventListener('click', e => {
      e.stopPropagation();
      if (e.target !== finalCollectionInput) enableEditing(e);
    });

    finalCollectionDisplay.addEventListener('click', enableEditing);

    finalCollectionInput.addEventListener('click', e => {
      e.stopPropagation();
    });

    finalCollectionInput.addEventListener('blur', e => {
      e.stopPropagation();
      saveFinalCollectionAmount(row);
    });

    finalCollectionInput.addEventListener('keypress', e => {
      e.stopPropagation();
      if (e.key === 'Enter') {
        e.preventDefault();
        e.target.blur();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        finalCollectionInput.value = finalCollectionCell.dataset.originalValue;
        finalCollectionDisplay.style.display = 'inline';
        finalCollectionInput.style.display = 'none';
      }
    });

    finalCollectionInput.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        finalCollectionInput.value = finalCollectionCell.dataset.originalValue;
        finalCollectionDisplay.style.display = 'inline';
        finalCollectionInput.style.display = 'none';
      }
    });
  }

  tbody.appendChild(row);
}

function renderCategoryTree() {
  const tbody = document.getElementById('tcCategoryTreeBody');
  const footer = document.getElementById('tcCategoryTreeFooter');
  if (!tbody || !footer) return;

  tbody.innerHTML = '';

  if (allInvoiceDetails.length === 0) {
    footer.style.display = 'none';
    const salesmanEntered = document.getElementById('salesmanCode').value.trim();
    if (salesmanEntered) {
      tbody.innerHTML = '<tr class="table-empty"><td colspan="14">No data.</td></tr>';
    } else {
      tbody.innerHTML =
        '<tr class="table-empty"><td colspan="14">No salesman on this page. Open from Temporary Collection list and choose a salesman.</td></tr>';
    }
    updateTotals();
    return;
  }

  invoiceDetails = allInvoiceDetails;

  const summaries = buildCustomerSummaries();

  summaries.forEach(customer => {
    const expanded = expandedCustomers.has(customer.customercode);
    const chevron = expanded ? '\u25bc' : '\u25b6';
    const collectionCellClass = customer.hasEdited
      ? 'summary-collection-cell summary-collection-edited'
      : 'summary-collection-cell';

    const parentRow = document.createElement('tr');
    parentRow.className = 'tc-cat-parent';
    parentRow.dataset.customerCode = customer.customercode;
    parentRow.innerHTML = `
      <td class="tc-cat-tree-cell">
        <button type="button" class="tc-cat-toggle" aria-expanded="${expanded}" aria-label="Show or hide invoices for this customer">${chevron}</button>
      </td>
      <td class="tc-cat-parent-muted">\u2014</td>
      <td>${customer.customercode || '-'}</td>
      <td>${customer.customername || '-'}</td>
      <td class="tc-cat-parent-meta">${customer.invoiceCount} inv.</td>
      <td class="tc-cat-parent-muted">\u2014</td>
      <td class="tc-cat-parent-muted">\u2014</td>
      <td class="tc-cat-parent-muted">\u2014</td>
      <td style="text-align: right;">${formatNumber(customer.totalCollection)}</td>
      <td style="text-align: right;" class="${collectionCellClass}">${formatNumber(customer.totalFinalCollection)}</td>
      <td colspan="4" class="tc-cat-parent-muted"></td>
    `;

    parentRow.addEventListener('click', () => toggleCustomerExpand(customer.customercode));

    tbody.appendChild(parentRow);

    if (expanded) {
      const invoices = allInvoiceDetails.filter(
        it => String(it.customercode || '').trim() === customer.customercode
      );
      invoices.forEach((item, invIdx) => {
        appendInvoiceLeafRow(tbody, item, invIdx + 1);
      });
    }
  });

  footer.style.display = '';
  updateTotals();
}

function saveFinalCollectionAmount(row) {
  const finalCollectionCell = row.querySelector('.editable-final-collection');
  const finalCollectionDisplay = row.querySelector('.final-collection-display');
  const finalCollectionInput = row.querySelector('.final-collection-input');
  
  if (!finalCollectionCell || !finalCollectionDisplay || !finalCollectionInput) {
    console.error('[DEBUG] Missing elements in saveFinalCollectionAmount');
    return;
  }
  
  const newValue = parseFloat(finalCollectionInput.value) || 0;
  const outstanding = parseFloat(row.dataset.outstanding || 0);
  
  // Validate: final collection cannot exceed outstanding
  if (newValue > outstanding) {
    alert(`Final collection amount (${formatNumber(newValue)}) cannot exceed outstanding amount (${formatNumber(outstanding)})`);
    finalCollectionInput.value = finalCollectionCell.dataset.originalValue;
    finalCollectionDisplay.style.display = 'inline';
    finalCollectionInput.style.display = 'none';
    return;
  }
  
  // Check if value has changed from original collection amount
  const originalCollection = parseFloat(row.dataset.collection || 0);
  const hasChanged = Math.abs(newValue - originalCollection) > 0.01; // Allow for floating point precision
  
  // Update the display
  finalCollectionDisplay.textContent = formatNumber(newValue);
  finalCollectionDisplay.style.display = 'inline';
  finalCollectionInput.style.display = 'none';
  
  // Update the original value attribute for next edit
  finalCollectionCell.dataset.originalValue = newValue;
  
  // Add/remove edited class based on whether value changed
  if (hasChanged) {
    finalCollectionCell.classList.add('final-collection-edited');
  } else {
    finalCollectionCell.classList.remove('final-collection-edited');
  }
  
  // Update the data
  const invoiceId = row.dataset.invoiceId;
  const invoiceIndex = invoiceDetails.findIndex(item => String(item.id) === String(invoiceId));
  
  if (invoiceIndex !== -1) {
    // Explicitly set the finalCollection value
    invoiceDetails[invoiceIndex].finalCollection = newValue;
    console.log('[DEBUG] Updated invoiceDetails:', invoiceIndex, 'finalCollection:', newValue);
    
    // Also update in allInvoiceDetails
    const allIndex = allInvoiceDetails.findIndex(item => String(item.id) === String(invoiceId));
    if (allIndex !== -1) {
      allInvoiceDetails[allIndex].finalCollection = newValue;
      console.log('[DEBUG] Updated allInvoiceDetails:', allIndex, 'finalCollection:', newValue);
    } else {
      console.warn('[DEBUG] Invoice not found in allInvoiceDetails:', invoiceId);
    }
    
    // Parent totals + footer refresh
    renderCategoryTree();
  } else {
    console.error('[DEBUG] Invoice not found in invoiceDetails:', invoiceId, 'Available IDs:', invoiceDetails.map(i => i.id));
  }
}

function updateTotals() {
  // Update Invoice Details totals
  let totalCollection = 0;
  let totalFinalCollection = 0;
  
  console.log('[DEBUG] updateTotals - invoiceDetails count:', invoiceDetails.length);
  
  invoiceDetails.forEach((item, idx) => {
    const collection = parseFloat(item.collection || 0);
    // Use finalCollection if it exists (including 0), otherwise fall back to collection
    let finalCollectionValue;
    if (item.hasOwnProperty('finalCollection')) {
      finalCollectionValue = parseFloat(item.finalCollection || 0);
    } else {
      finalCollectionValue = parseFloat(item.collection || 0);
    }
    
    totalCollection += collection;
    totalFinalCollection += finalCollectionValue;
    
    console.log(`[DEBUG] Item ${idx}: collection=${collection}, finalCollection=${finalCollectionValue}`);
  });
  
  console.log('[DEBUG] Calculated totals - Collection:', totalCollection, 'Final Collection:', totalFinalCollection);
  
  const footer = document.getElementById('tcCategoryTreeFooter');
  const totalCollectionEl = document.getElementById('detailsTotalCollection');
  const totalFinalCollectionEl = document.getElementById('detailsTotalFinalCollection');
  const summaryTotalCountEl = document.getElementById('summaryTotalCount');

  if (footer && invoiceDetails.length > 0) {
    footer.style.display = '';
    if (summaryTotalCountEl) {
      summaryTotalCountEl.textContent = String(invoiceDetails.length);
    }
    if (totalCollectionEl) {
      totalCollectionEl.textContent = formatNumber(totalCollection);
      console.log('[DEBUG] Updated detailsTotalCollection element:', formatNumber(totalCollection));
    } else {
      console.error('[DEBUG] detailsTotalCollection element not found');
    }
    if (totalFinalCollectionEl) {
      totalFinalCollectionEl.textContent = formatNumber(totalFinalCollection);
      console.log('[DEBUG] Updated detailsTotalFinalCollection element:', formatNumber(totalFinalCollection));
    } else {
      console.error('[DEBUG] detailsTotalFinalCollection element not found');
    }
  } else if (footer) {
    footer.style.display = 'none';
  } else {
    console.error('[DEBUG] tcCategoryTreeFooter element not found');
  }

}

function removeInvoiceDetail(invoiceId) {
  if (!invoiceId) return;
  
  if (!confirm('Are you sure you want to remove this invoice from the list?')) {
    return;
  }
  
  // Remove from invoiceDetails
  const invoiceIndex = invoiceDetails.findIndex(item => item.id === invoiceId);
  if (invoiceIndex !== -1) {
    invoiceDetails.splice(invoiceIndex, 1);
  }
  
  // Remove from allInvoiceDetails
  const allIndex = allInvoiceDetails.findIndex(item => item.id === invoiceId);
  if (allIndex !== -1) {
    allInvoiceDetails.splice(allIndex, 1);
  }

  invoiceDetails = allInvoiceDetails;
  renderCategoryTree();
}

function handleNew() {
  tcSaveCompleted = false;
  isNewMode = true;
  invoiceDetails = [];
  allInvoiceDetails = [];
  expandedCustomers.clear();

  const btnSave = document.getElementById('btnSave');
  if (btnSave) btnSave.disabled = false;

  fetchTransactionDate();

  const urlParams = new URLSearchParams(window.location.search);
  const salesmanCodeFromUrl = urlParams.get('salesman_code');
  if (!salesmanCodeFromUrl) {
    document.getElementById('salesmanCode').value = '';
    document.getElementById('salesmanName').value = '';
  }

  document.getElementById('remark').value = 'Pending Amount';

  renderCategoryTree();

  if (!salesmanCodeFromUrl) {
    document.getElementById('remark').focus();
  }
}

function handleQuery() {
  tcSaveCompleted = false;
  isNewMode = false;
  invoiceDetails = [];
  allInvoiceDetails = [];
  expandedCustomers.clear();

  const btnSave = document.getElementById('btnSave');
  if (btnSave) btnSave.disabled = true;

  document.getElementById('salesmanCode').value = '';
  document.getElementById('salesmanName').value = '';
  document.getElementById('remark').value = '';
  document.getElementById('transactionDate').value = '';

  renderCategoryTree();

  document.getElementById('remark').focus();
}

async function handleSave() {
  if (tcSaveCompleted) {
    alert('This collection was already saved. Use Back to return to the list.');
    return;
  }
  if (saveInProgress) {
    return;
  }

  const transactionDate = document.getElementById('transactionDate').value.trim();
  const salesmanCode = document.getElementById('salesmanCode').value.trim();
  const remark = document.getElementById('remark').value.trim() || 'Pending Amount';

  if (!transactionDate) {
    alert('Transaction date is required. Reload the page or open receipt day if the date is empty.');
    return;
  }

  if (!salesmanCode) {
    alert('No salesman code on this page. Open Temporary Collection from the list with a salesman selected.');
    return;
  }

  const selectedInvoices = [];

  if (allInvoiceDetails.length === 0) {
    alert('No invoices available to save');
    return;
  }

  const alreadyPaid = allInvoiceDetails.some(item => {
    const balance = parseFloat(item.balance) || 0;
    const collected = parseFloat(item.finalCollection ?? item.collection ?? 0) || 0;
    return collected > 0 && balance < collected;
  });
  if (alreadyPaid) {
    alert('Cannot save. One or more invoices are already paid (balance is less than collected amount).');
    return;
  }

  allInvoiceDetails.forEach(item => {
    const finalCollection = parseFloat(item.finalCollection || item.collection || 0);
    if (finalCollection > 0) {
      selectedInvoices.push({
        invoice_no: item.billno || '',
        customer_code: String(item.customercode || '').trim(),
        customer_name: item.customername || '',
        amount: finalCollection,
        id: item.id || '',
        salesman_code: item.salesmancode || salesmanCode,
        bill_date: item.billdate || transactionDate,
        bill_amount: item.outstanding || finalCollection,
      });
    }
  });

  if (selectedInvoices.length === 0) {
    alert('No collection amounts to save');
    return;
  }

  const customerGroups = {};
  selectedInvoices.forEach(inv => {
    const custCode = inv.customer_code;
    if (!customerGroups[custCode]) {
      customerGroups[custCode] = {
        customer_code: custCode,
        customer_name: inv.customer_name || custCode,
        count: 0,
        total: 0,
      };
    }
    customerGroups[custCode].count++;
    customerGroups[custCode].total += inv.amount;
  });

  const customerList = Object.values(customerGroups)
    .map(
      c =>
        `  • ${c.customer_name} (${c.count} invoice(s), Total: ${formatNumber(c.total)})`
    )
    .join('\n');

  const confirmMessage =
    `Are you sure you want to save the collection?\n\n` +
    `A voucher number will be assigned automatically for each customer when saving:\n\n` +
    customerList +
    `\n\nTotal Customers: ${Object.keys(customerGroups).length}\n` +
    `Total Invoices: ${selectedInvoices.length}\n` +
    `Total Amount: ${formatNumber(selectedInvoices.reduce((sum, inv) => sum + inv.amount, 0))}`;

  saveInProgress = true;
  try {
    if (!confirm(confirmMessage)) {
      return;
    }

    const btnSave = document.getElementById('btnSave');
    const saveOverlay = document.getElementById('temporaryCollectionSaveOverlay');
    if (btnSave) btnSave.disabled = true;
    if (saveOverlay) saveOverlay.style.display = 'flex';

    console.log('[DEBUG handleSave] Sending request:', {
      transaction_date: transactionDate,
      salesman_code: salesmanCode,
      remark,
      item_count: selectedInvoices.length,
    });

    const response = await fetch('/accounts/temporary-collection/api/save', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        transaction_date: transactionDate,
        salesman_code: salesmanCode,
        remark: remark,
        collection_items: selectedInvoices,
        save_nonce: tcSaveNonce,
      }),
    });

    console.log('[DEBUG handleSave] Response status:', response.status);

    const responseText = await response.text();
    let data = null;
    try {
      data = responseText ? JSON.parse(responseText) : null;
    } catch (_) {
      data = null;
    }
    if (data) {
      applyTemporaryCollectionSaveNonce(data);
    }

    if (!response.ok) {
      console.error('[ERROR handleSave] Error response:', response.status, responseText);
      if (data && data.error) {
        alert(data.error);
      } else {
        alert(`Error saving collection: ${response.status}`);
      }
      return;
    }

    console.log('[DEBUG handleSave] Save response:', data);

    if (!data) {
      alert('Invalid response from server.');
      return;
    }

    if (data.success) {
      tcSaveCompleted = true;
      const btnSaveOk = document.getElementById('btnSave');
      if (btnSaveOk) {
        btnSaveOk.disabled = true;
        btnSaveOk.title = 'Already saved';
      }

      let pdfBlobUrl = null;
      if (data.pdf_base64 && data.pdf_filename) {
        try {
          const byteCharacters = atob(data.pdf_base64);
          const byteNumbers = new Array(byteCharacters.length);
          for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
          }
          const byteArray = new Uint8Array(byteNumbers);
          const blob = new Blob([byteArray], { type: 'application/pdf' });
          const url = window.URL.createObjectURL(blob);
          const opened = window.open(url, '_blank');
          if (opened) {
            opened.focus();
            setTimeout(() => window.URL.revokeObjectURL(url), 100);
          } else {
            pdfBlobUrl = url;
          }
        } catch (error) {
          console.error('Error displaying PDF:', error);
          alert('Error displaying PDF report');
        }
      }

      if (pdfBlobUrl) {
        showPdfBlockedDialog(pdfBlobUrl);
      } else {
        window.location.href = '/accounts/temporary-collection/list';
      }
    } else {
      console.error('Save failed:', data);
      alert(data.error || 'Error saving collection');
    }
  } catch (error) {
    console.error('Error saving collection:', error);
    alert(`Error saving collection: ${error.message || error}`);
  } finally {
    saveInProgress = false;
    const btnSaveFinal = document.getElementById('btnSave');
    const saveOverlayFinal = document.getElementById('temporaryCollectionSaveOverlay');
    if (saveOverlayFinal) saveOverlayFinal.style.display = 'none';
    if (!tcSaveCompleted && btnSaveFinal) {
      btnSaveFinal.disabled = false;
      btnSaveFinal.title = 'Save';
    }
  }
}

function showPdfBlockedDialog(pdfBlobUrl) {
  const overlay = document.createElement('div');
  overlay.id = 'pdfBlockedOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';
  const box = document.createElement('div');
  box.style.cssText = 'background:#fff;padding:24px;border-radius:8px;max-width:400px;box-shadow:0 4px 20px rgba(0,0,0,0.2);';
  box.innerHTML = '<p style="margin:0 0 16px;font-size:14px;">Popup was blocked. Click the link below to open the PDF in a new tab, then continue.</p>' +
    '<p style="margin:0 0 16px;"><a href="#" id="pdfBlockedLink" target="_blank" rel="noopener" style="color:#2563eb;font-weight:600;font-size:14px;">Open PDF report in new tab</a></p>' +
    '<button type="button" id="pdfBlockedContinue" class="button button--primary" style="padding:8px 16px;">Continue to list</button>';
  const link = box.querySelector('#pdfBlockedLink');
  link.href = pdfBlobUrl;
  overlay.appendChild(box);
  document.body.appendChild(overlay);
  box.querySelector('#pdfBlockedContinue').addEventListener('click', function() {
    window.URL.revokeObjectURL(pdfBlobUrl);
    overlay.remove();
    window.location.href = '/accounts/temporary-collection/list';
  });
}

function handleExit() {
  // Redirect to temporary collection list page
  window.location.href = '/accounts/temporary-collection/list';
}

function formatNumber(value) {
  return parseFloat(value || 0).toFixed(2);
}

function formatDate(dateValue) {
  if (!dateValue) return '-';
  const date = new Date(dateValue);
  if (isNaN(date.getTime())) return dateValue;
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}
