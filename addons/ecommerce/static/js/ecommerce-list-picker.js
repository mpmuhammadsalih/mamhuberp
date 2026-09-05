/**
 * Modal list picker for ecommerce admin (ERP search-field--popup pattern).
 * Markup: [data-ec-list-picker] on wrapper with data-modal, data-display, data-hidden, data-clear, data-picker.
 */
(function () {
  'use strict';

  function initPicker(root) {
    if (!root || root.dataset.ecListPickerInit === '1') return;

    const modal = document.getElementById(root.dataset.modal || '');
    const display = document.getElementById(root.dataset.display || '');
    const hidden = document.getElementById(root.dataset.hidden || '');
    const pickerBtn = document.getElementById(root.dataset.picker || '');
    const clearBtn = document.getElementById(root.dataset.clear || '');
    const searchInput = root.dataset.search
      ? document.getElementById(root.dataset.search)
      : modal ? modal.querySelector('[data-ec-picker-search]') : null;
    const rowSelector = root.dataset.rowSelector || '.ec-picker-row';

    if (!modal || !display || !hidden) return;

    root.dataset.ecListPickerInit = '1';
    const rows = () => Array.from(modal.querySelectorAll(rowSelector));

    function syncClear() {
      if (!clearBtn) return;
      clearBtn.style.display = hidden.value ? 'block' : 'none';
    }

    function closeModal() {
      modal.classList.add('hidden');
      if (searchInput) {
        searchInput.value = '';
        filterRows('');
      }
    }

    function openModal() {
      modal.classList.remove('hidden');
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }

    function selectRow(row) {
      hidden.value = row.dataset.value || '';
      display.value = row.dataset.label || row.dataset.value || '';
      syncClear();
      closeModal();
      hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function filterRows(term) {
      const needle = (term || '').trim().toLowerCase();
      rows().forEach((row) => {
        const value = (row.dataset.value || '').toLowerCase();
        const label = (row.dataset.label || '').toLowerCase();
        const show = !needle || value.includes(needle) || label.includes(needle);
        row.style.display = show ? '' : 'none';
      });
    }

    function clearSelection() {
      hidden.value = '';
      display.value = '';
      syncClear();
      hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }

    if (pickerBtn) {
      pickerBtn.addEventListener('click', (e) => {
        e.preventDefault();
        openModal();
      });
    }

    display.addEventListener('click', openModal);

    if (clearBtn) {
      clearBtn.addEventListener('click', (e) => {
        e.preventDefault();
        clearSelection();
      });
    }

    modal.addEventListener('click', (e) => {
      if (
        e.target.classList.contains('modal__overlay')
        || e.target.classList.contains('modal__close')
        || e.target.closest('[data-ec-picker-close]')
      ) {
        closeModal();
      }
    });

    rows().forEach((row) => {
      row.addEventListener('click', () => selectRow(row));
    });

    if (searchInput) {
      searchInput.addEventListener('input', () => filterRows(searchInput.value));
      const clearSearch = modal.querySelector('[data-ec-picker-search-clear]');
      if (clearSearch) {
        clearSearch.addEventListener('click', () => {
          searchInput.value = '';
          filterRows('');
          searchInput.focus();
        });
      }
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
        closeModal();
      }
    });

    syncClear();
  }

  function boot() {
    document.querySelectorAll('[data-ec-list-picker]').forEach(initPicker);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
