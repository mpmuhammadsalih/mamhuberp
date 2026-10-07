document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('salesSummaryForm');
  const dateFrom = document.getElementById('salesSummaryDateFrom');
  const dateTo = document.getElementById('salesSummaryDateTo');
  const btnClear = document.getElementById('salesSummaryClear');
  const btnExport = document.getElementById('salesSummaryExport');
  const btnExportDetails = document.getElementById('salesSummaryExportDetails');
  const btnDetailed = document.getElementById('salesSummaryDetailed');

  if (btnClear) {
    btnClear.addEventListener('click', () => {
      const today = new Date().toISOString().split('T')[0];
      if (dateFrom) dateFrom.value = today;
      if (dateTo) dateTo.value = today;
      if (form) form.submit();
    });
  }

  if (btnExport) {
    btnExport.addEventListener('click', () => {
      const params = new URLSearchParams();
      if (dateFrom && dateFrom.value) params.append('date_from', dateFrom.value);
      if (dateTo && dateTo.value) params.append('date_to', dateTo.value);
      window.location.href = '/sales-summary/export' + (params.toString() ? `?${params.toString()}` : '');
    });
  }

  if (btnExportDetails) {
    btnExportDetails.addEventListener('click', () => {
      const params = new URLSearchParams();
      if (dateFrom && dateFrom.value) params.append('date_from', dateFrom.value);
      if (dateTo && dateTo.value) params.append('date_to', dateTo.value);
      window.location.href = '/sales-summary/export-details' + (params.toString() ? `?${params.toString()}` : '');
    });
  }

  if (btnDetailed) {
    btnDetailed.addEventListener('click', () => {
      const params = new URLSearchParams();
      if (dateFrom && dateFrom.value) params.append('date_from', dateFrom.value);
      if (dateTo && dateTo.value) params.append('date_to', dateTo.value);
      window.location.href = '/sales-summary/detailed' + (params.toString() ? `?${params.toString()}` : '');
    });
  }
});
