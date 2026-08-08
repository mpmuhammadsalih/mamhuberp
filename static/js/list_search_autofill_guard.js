(function (window) {
  'use strict';

  function armSearchInput(input, onFilter, loginUsername) {
    if (!input) return;

    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocapitalize', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('data-lpignore', 'true');
    input.setAttribute('data-1p-ignore', '');
    input.setAttribute('data-form-type', 'other');

    if (!input.readOnly && input.getAttribute('data-nexa-list-search') !== '0') {
      input.setAttribute('readonly', 'readonly');
      input.setAttribute('data-nexa-list-search', '1');
    }

    var userTyped = false;
    var login = (loginUsername || '').trim().toLowerCase();

    function unlock() {
      if (input.getAttribute('data-nexa-list-search') === '1') {
        input.removeAttribute('readonly');
        input.removeAttribute('data-nexa-list-search');
      }
    }

    input.addEventListener('focus', unlock);
    input.addEventListener('mousedown', unlock);

    input.addEventListener('input', function () {
      userTyped = true;
    });

    function looksLikeAutofill(val) {
      if (!val || userTyped) return false;
      var lower = val.toLowerCase();
      if (login && lower === login) return true;
      if (/@/.test(val) && val.indexOf('@') > 0) return true;
      return false;
    }

    function clearSpuriousAutofill() {
      var v = (input.value || '').trim();
      if (!v || userTyped) return;
      if (looksLikeAutofill(v)) {
        input.value = '';
        if (typeof onFilter === 'function') onFilter();
      }
    }

    input.addEventListener('animationstart', function (e) {
      if (e.animationName && e.animationName.indexOf('nexaAutofill') !== -1) {
        clearSpuriousAutofill();
      }
    });

    setTimeout(clearSpuriousAutofill, 50);
    setTimeout(clearSpuriousAutofill, 250);
    setTimeout(clearSpuriousAutofill, 800);
    window.addEventListener('pageshow', clearSpuriousAutofill);
  }

  function armPasswordField(input) {
    if (!input) return;
    input.setAttribute('autocomplete', 'off');
  }

  function enablePasswordAutofill(input) {
    if (!input) return;
    input.setAttribute('autocomplete', 'current-password');
  }

  function disablePasswordAutofill(input) {
    if (!input) return;
    input.setAttribute('autocomplete', 'off');
    input.value = '';
  }

  window.NexaListSearchAutofillGuard = {
    armSearchInput: armSearchInput,
    armPasswordField: armPasswordField,
    enablePasswordAutofill: enablePasswordAutofill,
    disablePasswordAutofill: disablePasswordAutofill,
  };
})(window);
