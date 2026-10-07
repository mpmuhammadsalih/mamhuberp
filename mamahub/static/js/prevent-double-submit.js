/**
 * Prevent multiple button presses / double submit across the project.
 * - Forms: block duplicate submit and disable submit buttons on first submit (POST etc.; GET forms are skipped).
 * - Primary action buttons (type="button"): disable for a short period on click.
 * - AJAX forms: call window.reEnableFormSubmit(form) on error to re-enable buttons.
 */
(function() {
  "use strict";

  var REENABLE_MS = 3000;

  function reEnableForm(form) {
    if (!form || form.tagName !== "FORM") return;
    form.dataset.submitting = "";
    form.querySelectorAll("button[type=submit], input[type=submit]").forEach(function(b) {
      b.disabled = false;
      b.classList.remove("is-submitting");
    });
  }

  function onFormSubmit(ev) {
    var form = ev.target;
    if (form.tagName !== "FORM") return;
    // GET navigations are safe to repeat; guarding them disables the button without
    // helping much and can block a second click if navigation was aborted or delayed.
    var method = (form.getAttribute("method") || "get").toLowerCase();
    if (method === "get") return;
    if (form.dataset.submitting === "true") {
      ev.preventDefault();
      ev.stopImmediatePropagation();
      return false;
    }
    form.dataset.submitting = "true";
    var buttons = Array.prototype.slice.call(
      form.querySelectorAll('button[type=submit], input[type=submit]')
    );
    // Defer disable: disabling during submit dispatch can drop the activating button from the POST
    // (successful controls omit disabled submits), breaking forms with multiple submit buttons / name=value.
    // Only disable if submission was not aborted (validators may call preventDefault + reEnableFormSubmit synchronously).
    window.setTimeout(function() {
      if (form.dataset.submitting !== "true") return;
      buttons.forEach(function(btn) {
        btn.disabled = true;
        btn.classList.add("is-submitting");
      });
    }, 0);
  }

  function onButtonClick(ev) {
    var btn = ev.target.closest("button");
    if (!btn || btn.type === "submit") return;
    if (btn.disabled) {
      ev.preventDefault();
      ev.stopImmediatePropagation();
      return false;
    }
    if (!btn.classList.contains("button--primary")) return;
    btn.disabled = true;
    btn.classList.add("is-submitting");
    setTimeout(function() {
      btn.disabled = false;
      btn.classList.remove("is-submitting");
    }, REENABLE_MS);
  }

  function init() {
    document.addEventListener("submit", onFormSubmit, true);
    document.addEventListener("submit", function(ev) {
      var form = ev.target;
      if (!form || form.tagName !== "FORM") return;
      if (!ev.defaultPrevented) return;
      if (form.dataset.traFormWrapped === "1" || form.dataset.traSubmitting === "1") return;
      reEnableForm(form);
    }, false);
    document.addEventListener("click", onButtonClick, true);
    window.reEnableFormSubmit = reEnableForm;
    window.addEventListener("pageshow", function(ev) {
      document.querySelectorAll("form").forEach(function(f) {
        reEnableForm(f);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
