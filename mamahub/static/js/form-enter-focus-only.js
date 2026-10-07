/**
 * Forms with class "form-enter-focus-only": Enter does not submit; it moves focus to
 * the next visible control. Submit still occurs when pressing Enter while focus is on
 * a submit button, or via mouse click.
 */
(function () {
  'use strict';

  function visibleFocusables(form) {
    var sel = form.querySelectorAll('input, select, textarea, button');
    var out = [];
    for (var i = 0; i < sel.length; i++) {
      var el = sel[i];
      if (!form.contains(el) || el.disabled) continue;
      if (el.type === 'hidden') continue;
      var st = window.getComputedStyle(el);
      if (st.display === 'none' || st.visibility === 'hidden') continue;
      if (typeof el.tabIndex === 'number' && el.tabIndex < 0) continue;
      out.push(el);
    }
    return out;
  }

  function shouldAdvanceFocusOnEnter(t) {
    if (!t) return false;
    if (t.tagName === 'TEXTAREA') return false;
    if (t.tagName === 'INPUT') {
      var ty = (t.type || '').toLowerCase();
      if (ty === 'submit' || ty === 'image') return false;
    }
    if (t.tagName === 'BUTTON') {
      var bty = (t.type || '').toLowerCase();
      if (bty === 'submit' || bty === '') return false;
    }
    return true;
  }

  document.addEventListener(
    'keydown',
    function (ev) {
      if (ev.key !== 'Enter' && ev.keyCode !== 13) return;
      var t = ev.target;
      var form = t && t.closest && t.closest('form.form-enter-focus-only');
      if (!form || !form.classList.contains('form-enter-focus-only')) return;
      if (!shouldAdvanceFocusOnEnter(t)) return;

      ev.preventDefault();
      var list = visibleFocusables(form);
      var idx = list.indexOf(t);
      if (idx < 0) return;
      if (idx < list.length - 1) {
        list[idx + 1].focus();
        return;
      }
      var submit =
        form.querySelector('button[type="submit"]:not([disabled])') ||
        form.querySelector('input[type="submit"]:not([disabled])');
      if (submit) submit.focus();
    },
    true
  );
})();
