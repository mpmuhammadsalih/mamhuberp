/**
 * Global Ctrl+S / Cmd+S: trigger the page's primary Save control (same as clicking Save).
 * - Open modal save wins over the main page (e.g. GRN Create item).
 * - Pages can set data-save-button on a container for an explicit selector.
 * - Set data-disable-ctrl-s-save="1" on <body> to opt out.
 */
(function () {
  'use strict';

  function isSaveShortcut(ev) {
    if (!ev || (!ev.ctrlKey && !ev.metaKey) || ev.altKey) return false;
    return String(ev.key || '').toLowerCase() === 's';
  }

  function isDisabled(el) {
    if (!el) return true;
    if (el.disabled) return true;
    if (el.getAttribute && el.getAttribute('aria-disabled') === 'true') return true;
    return false;
  }

  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    if (el.closest && el.closest('.hidden')) return false;
    var st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function isSaveable(el) {
    if (!el || isDisabled(el) || !isVisible(el)) return false;
    if (el.tagName === 'A') return false;
    return true;
  }

  function queryOne(selector) {
    if (!selector) return null;
    try {
      var el = document.querySelector(selector);
      return isSaveable(el) ? el : null;
    } catch (e) {
      return null;
    }
  }

  function findModalSaveButton() {
    var modals = document.querySelectorAll('.modal:not(.hidden), [role="dialog"]:not(.hidden)');
    var i;
    for (i = modals.length - 1; i >= 0; i -= 1) {
      var modal = modals[i];
      var explicit = modal.querySelector('[data-ctrl-s-save]');
      if (isSaveable(explicit)) return explicit;
      var selectors = ['#grnQitemSaveBtn', '.button--save', 'button.im-btn-save', 'button[type="submit"]'];
      var s;
      for (s = 0; s < selectors.length; s += 1) {
        var btn = modal.querySelector(selectors[s]);
        if (isSaveable(btn)) return btn;
      }
    }
    return null;
  }

  function findDataSaveButton() {
    var hosts = document.querySelectorAll('[data-save-button]');
    var i;
    for (i = 0; i < hosts.length; i += 1) {
      var btn = queryOne(hosts[i].getAttribute('data-save-button'));
      if (btn) return btn;
    }
    return null;
  }

  function findGenericSaveButton() {
    var selectors = [
      '[data-ctrl-s-save]',
      '#btnSave',
      '#btnSaveAdjustment',
      '#saveBtn',
      '#rpSave',
      '#osBtnPostAll',
      '#btnArPostReceipt',
      '#cfSubmitBtn',
      '#hccSaveSubmitBtn',
      '#stkAdjAcSave',
      '#posAcSave',
      'button[data-tra-save]',
      '.im-topbar .im-actions button.im-btn-save[type="button"]',
      'button.im-btn-save[type="submit"]',
      'form button.gs-btn-primary[type="submit"]',
      'form button.page-po__btn-primary[type="submit"]',
      'button.im-btn-save[type="button"]'
    ];
    var i;
    for (i = 0; i < selectors.length; i += 1) {
      var nodes = document.querySelectorAll(selectors[i]);
      var j;
      for (j = 0; j < nodes.length; j += 1) {
        var el = nodes[j];
        if (el.closest && el.closest('.modal.hidden')) continue;
        if (isSaveable(el)) return el;
      }
    }
    return null;
  }

  function findSaveButton() {
    return findModalSaveButton() || findDataSaveButton() || findGenericSaveButton();
  }

  function triggerSave(ev) {
    var root = document.body || document.documentElement;
    if (root && root.getAttribute('data-disable-ctrl-s-save') === '1') return false;

    var btn = findSaveButton();
    if (!btn) return false;

    ev.preventDefault();
    if (typeof ev.stopImmediatePropagation === 'function') ev.stopImmediatePropagation();
    else ev.stopPropagation();
    btn.click();
    return true;
  }

  document.addEventListener(
    'keydown',
    function (ev) {
      if (!isSaveShortcut(ev)) return;
      if (triggerSave(ev)) return;
      ev.preventDefault();
    },
    true
  );

  window.NexaCtrlSSave = {
    findSaveButton: findSaveButton,
    trigger: function () {
      var btn = findSaveButton();
      if (!btn) return false;
      btn.click();
      return true;
    }
  };
})();
