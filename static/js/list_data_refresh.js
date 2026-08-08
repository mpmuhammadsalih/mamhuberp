/**
 * List data refresh helpers (manual full reload or JSON polling) — toolbar: #listRefreshAuto + #listRefreshNow
 * Full-page interval auto-reload was removed globally; use initJsonPolling for periodic data-only refresh.
 * Legacy SSR lists: manual "Refresh" only (full reload on demand).
 */
(function (global) {
  'use strict';

  /** @typedef {{ timerId:number|null }} TimerHolder */

  /** Full page reload (manual Refresh button on legacy list pages only). */
  function reloadPage() {
    try {
      if (typeof global.location !== 'undefined' && typeof global.location.reload === 'function') {
        global.location.reload();
      }
    } catch (e) {
      console.warn('List refresh reload failed', e);
    }
  }

  /**
   * Legacy list toolbars: wire manual Refresh only (no automatic full-page interval).
   */
  function initReloadToolbar() {
    var btn = document.getElementById('listRefreshNow');
    if (btn) {
      btn.addEventListener('click', function () {
        reloadPage();
      });
    }
    return { reload: reloadPage };
  }

  /**
   * @param {{
   *   getUrl: () => string,
   *   intervalMs?: number,
   *   fetchInit?: Record<string, unknown>,
   *   shouldSkipPoll?: () => boolean,
   *   onPayload: (payload: unknown) => void,
   * }} cfg
   */
  function initJsonPolling(cfg) {
    var intervalMs = cfg.intervalMs != null ? cfg.intervalMs : 5000;
    var busy = false;
    /** @type {TimerHolder} */
    var holder = { timerId: null };
    function poll(forceManual) {
      if (busy) return;
      var chk = document.getElementById('listRefreshAuto');
      if (!forceManual && chk && !chk.checked) return;
      if (cfg.shouldSkipPoll && cfg.shouldSkipPoll()) return;
      try {
        if (typeof document !== 'undefined' && document.hidden) return;
      } catch (e) {}
      busy = true;
      var fetchOpts = Object.assign({ credentials: 'same-origin', headers: { Accept: 'application/json' } }, cfg.fetchInit || {});
      global.fetch(cfg.getUrl(), fetchOpts)
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          try {
            cfg.onPayload(data);
          } catch (err2) {
            console.warn('List JSON refresh handler error', err2);
          }
        })
        .catch(function (err) {
          console.warn('List JSON refresh fetch failed', err);
        })
        .finally(function () {
          busy = false;
        });
    }
    function stop() {
      if (holder.timerId != null) {
        global.clearInterval(holder.timerId);
        holder.timerId = null;
      }
    }
    function start() {
      stop();
      holder.timerId = global.setInterval(poll, intervalMs);
    }
    function refreshNow() {
      poll(true);
    }
    var chk = document.getElementById('listRefreshAuto');
    var btn = document.getElementById('listRefreshNow');
    if (chk) {
      chk.addEventListener('change', function () {
        if (chk.checked) start(); else stop();
      });
    }
    if (btn) {
      btn.addEventListener('click', function () {
        refreshNow();
      });
    }
    start();
    return { start: start, stop: stop, refreshNow: refreshNow, poll: poll };
  }

  /** Auto-wire reload toolbars rendered by list_refresh_bar.html (skip JSON pages). */
  function bootstrapReloadToolbars() {
    var bar = document.querySelector('.list-refresh-toolbar');
    if (!bar || bar.getAttribute('data-bootstrap') === 'off') return null;
    return initReloadToolbar();
  }

  var ListDataRefresh = {
    initReloadToolbar: initReloadToolbar,
    initJsonPolling: initJsonPolling,
    bootstrapReloadToolbars: bootstrapReloadToolbars,
  };

  global.ListDataRefresh = ListDataRefresh;
})(typeof window !== 'undefined' ? window : this);
