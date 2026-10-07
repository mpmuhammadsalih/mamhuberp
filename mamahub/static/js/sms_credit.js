document.addEventListener('DOMContentLoaded', () => {
    const smsCustomerTable = document.getElementById('smsCreditCustomerTable');
    const smsMessage = document.getElementById('smsMessageCredit');
    const smsMask = document.getElementById('smsMaskCredit');
    const smsContactNumber = document.getElementById('smsContactNumberCredit');
    const selectedCustomersList = document.getElementById('selectedCustomersListCredit');
    const selectedCount = document.getElementById('selectedCountCredit');
    const btnSendSingle = document.getElementById('btnSendSingleCredit');
    const btnSendAll = document.getElementById('btnSendAllCredit');
    const smsResults = document.getElementById('smsResultsCredit');
    const smsResultsContent = document.getElementById('smsResultsContentCredit');
    const dateFrom = document.getElementById('dateFromCredit');
    const dateTo = document.getElementById('dateToCredit');
    const btnFilter = document.getElementById('btnFilterCredit');
    const btnClearFilter = document.getElementById('btnClearFilterCredit');
    const btnExportExcel = document.getElementById('btnExportExcelCredit');
    const selectAllCheckbox = document.getElementById('selectAllCustomersCredit');

    const locationName = window.locationNameCredit || '';
    let selectedCustomers = new Map();

    if (btnFilter) {
        btnFilter.addEventListener('click', () => {
            const from = dateFrom ? dateFrom.value : '';
            const to = dateTo ? dateTo.value : '';
            const params = new URLSearchParams();
            if (from) params.append('date_from', from);
            if (to) params.append('date_to', to);
            window.location.href = '/sms-credit' + (params.toString() ? '?' + params.toString() : '');
        });
    }

    if (btnClearFilter) {
        btnClearFilter.addEventListener('click', () => {
            if (dateFrom) dateFrom.value = '';
            if (dateTo) dateTo.value = '';
            window.location.href = '/sms-credit';
        });
    }

    if (btnExportExcel) {
        btnExportExcel.addEventListener('click', () => {
            if (!smsCustomerTable) return;
            const rows = Array.from(smsCustomerTable.querySelectorAll('tbody tr'));
            if (rows.length === 0) {
                alert('No data to export.');
                return;
            }
            const headers = Array.from(smsCustomerTable.querySelectorAll('thead th'));
            const headerTexts = [];
            headers.forEach((th, index) => {
                if (index === 0) return;
                let text = th.textContent.trim();
                const sortIndicator = th.querySelector('.sort-indicator');
                if (sortIndicator) text = text.replace(sortIndicator.textContent, '').trim();
                headerTexts.push(text);
            });
            let csvContent = headerTexts.join(',') + '\n';
            rows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                const rowData = [];
                cells.forEach((cell, index) => {
                    if (index === 0) return;
                    let cellText = cell.textContent.trim();
                    if (cellText.includes(',') || cellText.includes('"') || cellText.includes('\n')) {
                        cellText = '"' + cellText.replace(/"/g, '""') + '"';
                    }
                    rowData.push(cellText);
                });
                csvContent += rowData.join(',') + '\n';
            });
            const tfoot = smsCustomerTable.querySelector('tfoot');
            if (tfoot && tfoot.querySelector('tr')) {
                const totalCells = Array.from(tfoot.querySelector('tr').querySelectorAll('td'));
                const totalData = [];
                totalCells.forEach((cell, index) => {
                    if (index === 0) return;
                    let cellText = cell.textContent.trim();
                    if (cellText.includes(',') || cellText.includes('"') || cellText.includes('\n')) {
                        cellText = '"' + cellText.replace(/"/g, '""') + '"';
                    }
                    totalData.push(cellText);
                });
                csvContent += totalData.join(',') + '\n';
            }
            const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.setAttribute('href', URL.createObjectURL(blob));
            link.setAttribute('download', 'sms_credit_customers_' + new Date().toISOString().split('T')[0] + '.csv');
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    if (smsCustomerTable) {
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                smsCustomerTable.querySelectorAll('.customer-checkbox-credit').forEach(cb => {
                    cb.checked = e.target.checked;
                    handleCustomerSelection(cb);
                });
            });
        }
        smsCustomerTable.addEventListener('change', (e) => {
            if (e.target.classList.contains('customer-checkbox-credit')) {
                handleCustomerSelection(e.target);
                updateSelectAllCheckbox();
            }
        });
        smsCustomerTable.addEventListener('click', (e) => {
            const row = e.target.closest('tbody tr');
            const checkbox = e.target.closest('.customer-checkbox-credit');
            if (row && !checkbox && e.target.tagName !== 'INPUT') {
                const rowCheckbox = row.querySelector('.customer-checkbox-credit');
                if (rowCheckbox) {
                    rowCheckbox.checked = !rowCheckbox.checked;
                    handleCustomerSelection(rowCheckbox);
                    updateSelectAllCheckbox();
                }
            }
        });
    }

    function handleCustomerSelection(checkbox) {
        const code = checkbox.value;
        const name = checkbox.dataset.name || '';
        const phone = checkbox.dataset.phone || '';
        const outstanding = checkbox.dataset.outstanding || '0.00';
        const pending = checkbox.dataset.pending || '0.00';
        const collection = checkbox.dataset.collection || '0.00';
        if (checkbox.checked) {
            selectedCustomers.set(code, { code, name, phone, outstanding, pending, collection });
            const row = checkbox.closest('tr');
            if (row) row.classList.add('table-row--selected');
        } else {
            selectedCustomers.delete(code);
            const row = checkbox.closest('tr');
            if (row) row.classList.remove('table-row--selected');
        }
        updateSelectedCustomersDisplay();
    }

    function updateSelectedCustomersDisplay() {
        if (!selectedCustomersList || !selectedCount) return;
        const count = selectedCustomers.size;
        selectedCount.textContent = count;
        if (count === 0) {
            selectedCustomersList.innerHTML = '<p class="page-po__muted" style="margin: 0; color: #9ca3af;">No customers selected</p>';
        } else {
            let html = '<div style="display: flex; flex-direction: column; gap: 4px;">';
            selectedCustomers.forEach((customer, code) => {
                html += '<div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 8px; background: #f3f4f6; border-radius: 4px;"><span>' + code + ' - ' + customer.name + '</span><button type="button" class="remove-customer-btn" data-code="' + code + '" style="background: none; border: none; color: #ef4444; cursor: pointer; font-size: 16px; padding: 0 4px;">×</button></div>';
            });
            html += '</div>';
            selectedCustomersList.innerHTML = html;
            selectedCustomersList.querySelectorAll('.remove-customer-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const code = btn.dataset.code;
                    const checkbox = smsCustomerTable && smsCustomerTable.querySelector('.customer-checkbox-credit[value="' + code + '"]');
                    if (checkbox) {
                        checkbox.checked = false;
                        handleCustomerSelection(checkbox);
                        updateSelectAllCheckbox();
                    }
                });
            });
        }
    }

    function updateSelectAllCheckbox() {
        if (!selectAllCheckbox || !smsCustomerTable) return;
        const checkboxes = smsCustomerTable.querySelectorAll('.customer-checkbox-credit');
        const checkedCount = smsCustomerTable.querySelectorAll('.customer-checkbox-credit:checked').length;
        selectAllCheckbox.checked = checkboxes.length > 0 && checkedCount === checkboxes.length;
        selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
    }

    const dateFromVal = () => dateFrom ? dateFrom.value : '';
    const dateToVal = () => dateTo ? dateTo.value : '';

    if (btnSendSingle) {
        btnSendSingle.addEventListener('click', async () => {
            const message = smsMessage.value.trim();
            if (selectedCustomers.size === 0) {
                alert('Please select at least one customer first.');
                return;
            }
            if (!message) {
                alert('Please enter a message.');
                smsMessage.focus();
                return;
            }
            if (!confirm('Send SMS to ' + selectedCustomers.size + ' selected customer(s)?')) return;
            btnSendSingle.disabled = true;
            btnSendSingle.textContent = 'Sending...';
            try {
                const results = [];
                const baseMessage = smsMessage.value.trim();
                for (const customer of selectedCustomers.values()) {
                    if (!customer.phone) {
                        results.push({ customer_code: customer.code, customer_name: customer.name, success: false, error: 'Phone number not available' });
                        continue;
                    }
                    let personalizedMessage = baseMessage
                        .replace(/\[Customer Name\]/g, customer.name || 'Customer')
                        .replace(/\[Location Name\]/g, locationName)
                        .replace(/\[Collected\]/g, customer.collection || '0.00')
                        .replace(/\[Amount\]/g, customer.outstanding || '0.00')
                        .replace(/\[Contact Number\]/g, smsContactNumber ? smsContactNumber.value : '');
                    const res = await fetch('/sms-credit/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            customer_code: customer.code,
                            message: personalizedMessage,
                            mask: smsMask ? smsMask.value : '',
                            send_all: false,
                            date_from: dateFromVal(),
                            date_to: dateToVal()
                        })
                    });
                    const data = await res.json();
                    if (data.results && data.results.length > 0) results.push(data.results[0]);
                }
                displayResults(results);
            } catch (e) {
                alert('Failed to send SMS: ' + e.message);
            } finally {
                btnSendSingle.disabled = false;
                btnSendSingle.textContent = 'Send to Selected Customers';
            }
        });
    }

    if (btnSendAll) {
        btnSendAll.addEventListener('click', async () => {
            const baseMessage = smsMessage.value.trim();
            if (!baseMessage) {
                alert('Message is required.');
                return;
            }
            const customerCount = smsCustomerTable ? smsCustomerTable.querySelectorAll('tbody tr').length : 0;
            if (customerCount === 0) {
                alert('No customers available.');
                return;
            }
            if (!confirm('Send SMS to ALL ' + customerCount + ' customers?')) return;
            btnSendAll.disabled = true;
            btnSendAll.textContent = 'Sending...';
            try {
                const allCustomers = [];
                const rows = smsCustomerTable.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const code = row.dataset.customerCode;
                    const phone = row.dataset.phone;
                    const outstanding = row.dataset.outstanding || '0.00';
                    const pending = row.dataset.pending || '0.00';
                    const collection = row.dataset.collection || '0.00';
                    const nameCell = row.cells[3];
                    const name = nameCell ? nameCell.textContent.trim() : '';
                    if (code && phone) allCustomers.push({ code, name, phone, outstanding, pending, collection });
                });
                const results = [];
                for (const customer of allCustomers) {
                    if (!customer.phone) {
                        results.push({ customer_code: customer.code, customer_name: customer.name, success: false, error: 'Phone number not available' });
                        continue;
                    }
                    let personalizedMessage = baseMessage
                        .replace(/\[Customer Name\]/g, customer.name || 'Customer')
                        .replace(/\[Location Name\]/g, locationName)
                        .replace(/\[Collected\]/g, customer.collection || '0.00')
                        .replace(/\[Amount\]/g, customer.outstanding || '0.00')
                        .replace(/\[Contact Number\]/g, smsContactNumber ? smsContactNumber.value : '');
                    const res = await fetch('/sms-credit/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            customer_code: customer.code,
                            message: personalizedMessage,
                            mask: smsMask ? smsMask.value : '',
                            send_all: false,
                            date_from: dateFromVal(),
                            date_to: dateToVal()
                        })
                    });
                    const data = await res.json();
                    if (data.results && data.results.length > 0) results.push(data.results[0]);
                }
                displayResults(results);
            } catch (e) {
                alert('Failed to send SMS: ' + e.message);
            } finally {
                btnSendAll.disabled = false;
                btnSendAll.textContent = 'Send to All Customers';
            }
        });
    }

    function displayResults(results) {
        if (!smsResults || !smsResultsContent) return;
        if (results.length === 0) {
            smsResultsContent.innerHTML = '<p class="page-po__muted">No results.</p>';
            smsResults.style.display = 'block';
            return;
        }
        const successCount = results.filter(r => r.success).length;
        const failedCount = results.length - successCount;
        let html = '<div class="sms-results-summary"><div><strong>Total:</strong> ' + results.length + '</div><div><strong>Success:</strong> <span style="color:#10b981;">' + successCount + '</span></div><div><strong>Failed:</strong> <span style="color:#ef4444;">' + failedCount + '</span></div></div><div class="scroll-table" style="max-height:300px;margin-top:12px;"><table class="table"><thead><tr><th>Customer Code</th><th>Customer Name</th><th>Phone</th><th>Status</th><th>Response</th></tr></thead><tbody>';
        results.forEach(result => {
            const statusClass = result.success ? 'success' : 'error';
            const statusText = result.success ? 'Success' : 'Failed';
            html += '<tr><td>' + (result.customer_code || '-') + '</td><td>' + (result.customer_name || '-') + '</td><td>' + (result.phone || '-') + '</td><td><span class="status-badge status-badge--' + statusClass + '">' + statusText + '</span></td><td>' + (result.response || result.error || '-') + '</td></tr>';
        });
        html += '</tbody></table></div>';
        smsResultsContent.innerHTML = html;
        smsResults.style.display = 'block';
        smsResults.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    if (smsCustomerTable) {
        const sortableHeaders = smsCustomerTable.querySelectorAll('th.sortable');
        let currentSort = '';
        let currentOrder = 'asc';
        sortableHeaders.forEach(header => {
            header.addEventListener('click', () => {
                const sortField = header.dataset.sort;
                if (currentSort === sortField) currentOrder = currentOrder === 'asc' ? 'desc' : 'asc';
                else currentOrder = 'asc';
                currentSort = sortField;
                sortableHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
                header.classList.add('sort-' + currentOrder);
                sortTable(sortField, currentOrder);
            });
        });
        function sortTable(sortField, order) {
            const tbody = smsCustomerTable.querySelector('tbody');
            if (!tbody) return;
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const targetHeader = smsCustomerTable.querySelector('th[data-sort="' + sortField + '"]');
            const headers = Array.from(smsCustomerTable.querySelectorAll('th'));
            const headerIndex = headers.indexOf(targetHeader);
            if (headerIndex === -1) return;
            rows.sort((a, b) => {
                const aCell = a.cells[headerIndex];
                const bCell = b.cells[headerIndex];
                if (!aCell || !bCell) return 0;
                let aVal = aCell.textContent.trim();
                let bVal = bCell.textContent.trim();
                if (['slno', 'invoicecount', 'outstandingamount', 'collectionamount'].indexOf(sortField) !== -1) {
                    aVal = parseFloat(aVal.replace(/,/g, '')) || 0;
                    bVal = parseFloat(bVal.replace(/,/g, '')) || 0;
                    return order === 'asc' ? aVal - bVal : bVal - aVal;
                }
                if (sortField === 'lastbilldate') {
                    const parseDate = (str) => {
                        if (!str || str === '-') return new Date(0);
                        const parts = str.split('-');
                        if (parts.length === 3) return new Date(parts[2], parts[1] - 1, parts[0]);
                        return new Date(0);
                    };
                    aVal = parseDate(aVal);
                    bVal = parseDate(bVal);
                    return order === 'asc' ? aVal - bVal : bVal - aVal;
                }
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
                if (aVal < bVal) return order === 'asc' ? -1 : 1;
                if (aVal > bVal) return order === 'asc' ? 1 : -1;
                return 0;
            });
            tbody.innerHTML = '';
            rows.forEach(row => tbody.appendChild(row));
        }
    }
});
