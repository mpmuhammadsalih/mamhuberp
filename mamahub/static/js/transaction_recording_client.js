/**
 * Nexa ERP — Transaction screen recording & field-change audit (client).
 *
 * Usage on a transaction page:
 *   NexaTransactionAudit.init({
 *     transactionType: 'StockAdjustment',
 *     getTransactionNo: () => document.getElementById('adjNo').value || 'NEW',
 *     saveButton: '#btnSaveAdjustment',
 *     trackRoot: '.page',
 *     enableVideo: 'auto', // auto = silent tab video when Nexa Audit Recorder extension is installed
 *     interceptForm: '#journalForm',  // classic POST forms (bubble-phase intercept)
 *     onBeforeSave: async () => { ... optional extra hook ... },
 *     onAfterSave: async (result) => { ... },
 *   });
 */
(function (global) {
  'use strict';

  const API_BASE = '/audit/recording/api';
  const EXT_CHANNEL = 'NEXA_AUDIT_RECORDER';
  const state = {
    auditId: null,
    transactionType: '',
    transactionNo: 'NEW',
    fieldValues: new Map(),
    videoRecorder: null,
    videoChunks: [],
    videoStream: null,
    started: false,
    videoStartScheduled: false,
    extensionRecording: false,
    extensionAvailable: null,
    videoRecordStartedAt: 0,
    completing: false,
  };

  const el = (sel) => {
    if (!sel) return null;
    if (typeof sel === 'string') return document.querySelector(sel);
    return sel;
  };

  const machineName = () => {
    try {
      if (global.navigator.userAgentData && global.navigator.userAgentData.platform) {
        return global.navigator.userAgentData.platform;
      }
    } catch (_) { /* ignore */ }
    return global.navigator.platform || global.location.hostname || 'unknown';
  };

  const postJson = async (url, body) => {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await res.json(); } catch (_) { data = {}; }
    if (!res.ok || data.success === false) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
  };

  const loadHtml2Canvas = () => new Promise((resolve, reject) => {
    if (global.html2canvas) return resolve(global.html2canvas);
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    s.onload = () => resolve(global.html2canvas);
    s.onerror = () => reject(new Error('Failed to load html2canvas'));
    document.head.appendChild(s);
  });

  const captureScreenshot = async (rootSel) => {
    const root = el(rootSel) || document.body;
    try {
      const html2canvas = await loadHtml2Canvas();
      const canvas = await html2canvas(root, {
        useCORS: true,
        logging: false,
        scale: Math.min(2, global.devicePixelRatio || 1),
        windowWidth: root.scrollWidth,
        windowHeight: root.scrollHeight,
      });
      return canvas.toDataURL('image/png');
    } catch (err) {
      console.warn('[TransactionAudit] Screenshot failed:', err);
      return null;
    }
  };

  const fieldKey = (node) => {
    if (!node) return '';
    if (node.id) return node.id;
    if (node.name) return node.name;
    const label = node.closest('label');
    if (label && label.textContent) return label.textContent.trim().slice(0, 120);
    return node.tagName + (node.type ? `[${node.type}]` : '');
  };

  const trackFields = (rootSel) => {
    const root = el(rootSel) || document.body;
    const nodes = root.querySelectorAll('input, select, textarea');
    nodes.forEach((node) => {
      if (node.type === 'hidden' || node.disabled) return;
      const key = fieldKey(node);
      if (!key) return;
      state.fieldValues.set(node, node.value);
      const handler = () => {
        const oldVal = state.fieldValues.get(node);
        const newVal = node.value;
        if (oldVal === newVal) return;
        state.fieldValues.set(node, newVal);
        if (!state.auditId) return;
        postJson(`${API_BASE}/field-change`, {
          audit_id: state.auditId,
          field_name: key,
          old_value: oldVal,
          new_value: newVal,
        }).catch((err) => console.warn('[TransactionAudit] field-change:', err));
      };
      node.addEventListener('change', handler);
      node.addEventListener('blur', handler);
    });
  };

  const extensionRequest = (action, timeoutMs) => new Promise((resolve, reject) => {
    const reqId = `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    const expect = action === 'START' ? 'STARTED' : (action === 'STOP' ? 'STOPPED' : 'PONG');
    const onMsg = (ev) => {
      if (ev.source !== global || !ev.data || ev.data.channel !== EXT_CHANNEL) return;
      if (ev.data.reqId !== reqId && action !== 'PING') return;
      if (action === 'PING' && ev.data.action !== 'PONG' && ev.data.action !== 'READY') return;
      if (action !== 'PING' && ev.data.action !== expect) return;
      global.clearTimeout(timer);
      global.removeEventListener('message', onMsg);
      if (ev.data.ok === false) reject(new Error(ev.data.error || 'Extension recording failed'));
      else resolve(ev.data);
    };
    const timer = global.setTimeout(() => {
      global.removeEventListener('message', onMsg);
      reject(new Error('Nexa Audit Recorder extension timeout'));
    }, timeoutMs || 15000);
    global.addEventListener('message', onMsg);
    global.postMessage({ channel: EXT_CHANNEL, action, reqId }, '*');
  });

  const extensionAvailable = () => {
    if (state.extensionAvailable === true) return Promise.resolve(true);
    if (state.extensionAvailable === false) return Promise.resolve(false);
    if (global.document.documentElement.dataset.nexaAuditExt === '1') {
      state.extensionAvailable = true;
      return Promise.resolve(true);
    }
    return extensionRequest('PING', 1500)
      .then(() => {
        state.extensionAvailable = true;
        try { global.document.documentElement.dataset.nexaAuditExt = '1'; } catch (_) { /* ignore */ }
        return true;
      })
      .catch(() => {
        state.extensionAvailable = false;
        return false;
      });
  };

  const startExtensionVideo = async () => {
    if (state.extensionRecording) return;
    await extensionRequest('START', 12000);
    state.extensionRecording = true;
    state.videoRecordStartedAt = Date.now();
    console.info('[TransactionAudit] Tab video recording started.');
  };

  const stopExtensionVideo = async () => {
    if (!state.extensionRecording) return null;
    const elapsed = Date.now() - (state.videoRecordStartedAt || 0);
    if (elapsed < 800) {
      await new Promise((r) => setTimeout(r, 800 - elapsed));
    }
    try {
      const data = await extensionRequest('STOP', 45000);
      if (!data.videoBase64) {
        console.warn('[TransactionAudit] Extension returned no video data.');
        return null;
      }
      const res = await fetch(data.videoBase64);
      const blob = await res.blob();
      if (!blob || blob.size < 100) {
        console.warn('[TransactionAudit] Video file too small:', blob && blob.size);
        return null;
      }
      return blob;
    } catch (err) {
      console.warn('[TransactionAudit] extension stop:', err);
      return null;
    } finally {
      state.extensionRecording = false;
      state.videoRecordStartedAt = 0;
    }
  };

  const ensureVideoStarted = async (cfg) => {
    if (cfg && cfg.enableVideo === false) return;
    if (state.extensionRecording || state.videoRecorder || state.videoStream) return;
    await startVideo(cfg || { enableVideo: 'auto' });
  };

  const getDisplayMediaOptions = () => {
    const opts = {
      video: {
        cursor: 'always',
        width: { ideal: 1920, max: 3840 },
        height: { ideal: 1080, max: 2160 },
      },
      audio: false,
      preferCurrentTab: false,
    };
    // Prefer entire screen / monitor (not Chrome tab). Browser still shows one-time Share dialog.
    try {
      opts.video.displaySurface = 'monitor';
      opts.monitorTypeSurfaces = 'include';
    } catch (_) { /* ignore */ }
    return opts;
  };

  const startVideo = async (cfg) => {
    if (state.videoStream || state.videoRecorder || state.extensionRecording) return;
    if (cfg && cfg.enableVideo === false) return;

    if (await extensionAvailable()) {
      try {
        await startExtensionVideo();
        console.info('[TransactionAudit] Tab video via Nexa Audit Recorder extension (no Share dialog).');
        return;
      } catch (err) {
        console.warn('[TransactionAudit] Extension video failed:', err.message || err);
      }
    }

    if (!cfg || cfg.enableVideo !== true) return;
    if (!global.navigator.mediaDevices || !global.MediaRecorder) return;
    try {
      const stream = await global.navigator.mediaDevices.getDisplayMedia(getDisplayMediaOptions());
      state.videoStream = stream;
      state.videoChunks = [];
      const mime = global.MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
        ? 'video/webm;codecs=vp9'
        : (global.MediaRecorder.isTypeSupported('video/webm') ? 'video/webm' : '');
      state.videoRecorder = mime
        ? new global.MediaRecorder(stream, { mimeType: mime })
        : new global.MediaRecorder(stream);
      state.videoRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size) state.videoChunks.push(e.data);
      };
      state.videoRecorder.start(4000);
      stream.getVideoTracks()[0]?.addEventListener('ended', () => stopVideo());
    } catch (err) {
      console.info('[TransactionAudit] Video recording not started:', err.message || err);
    }
  };

  const stopVideo = async () => {
    if (state.extensionRecording) {
      return stopExtensionVideo();
    }
    const rec = state.videoRecorder;
    if (!rec || rec.state === 'inactive') {
      if (state.videoStream) {
        state.videoStream.getTracks().forEach((t) => t.stop());
        state.videoStream = null;
      }
      return null;
    }
    return new Promise((resolve) => {
      rec.onstop = () => {
        const blob = state.videoChunks.length ? new Blob(state.videoChunks, { type: rec.mimeType || 'video/webm' }) : null;
        state.videoRecorder = null;
        if (state.videoStream) {
          state.videoStream.getTracks().forEach((t) => t.stop());
          state.videoStream = null;
        }
        resolve(blob);
      };
      try { rec.stop(); } catch (_) { resolve(null); }
    });
  };

  const blobToBase64 = (blob) => new Promise((resolve, reject) => {
    if (!blob) return resolve(null);
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });

  const bindVideoStartOnGesture = (cfg) => {
    const root = el(cfg.trackRoot || 'body') || document.body;
    const once = () => {
      root.removeEventListener('pointerdown', once, true);
      if (cfg._videoSaveBtn) cfg._videoSaveBtn.removeEventListener('pointerdown', once, true);
      startVideo(cfg).catch((err) => {
        console.warn('[TransactionAudit] Video start failed:', err && err.message ? err.message : err);
      });
    };
    root.addEventListener('pointerdown', once, true);
    const saveBtn = el(cfg.saveButton);
    if (saveBtn) {
      cfg._videoSaveBtn = saveBtn;
      saveBtn.addEventListener('pointerdown', once, true);
    }
  };

  /** Extension + web video: start on first click (Chrome requires user gesture for capture). */
  const scheduleVideoStart = (cfg) => {
    if (cfg.enableVideo === false) return;
    if (state.videoStartScheduled) return;
    state.videoStartScheduled = true;

    extensionAvailable().then((ext) => {
      if (ext) {
        console.info('[TransactionAudit] Nexa Audit Recorder extension detected — click the form to start tab video.');
        bindVideoStartOnGesture(cfg);
        return;
      }
      console.warn(
        '[TransactionAudit] Extension not detected on',
        global.location.href,
        '— reload the extension after manifest changes, or use data-enable-video="0" for screenshots only.'
      );
      if (cfg.enableVideo !== true) return;
      bindVideoStartOnGesture(cfg);
    });
  };

  const startSession = async (cfg) => {
    if (state.started) return state.auditId;
    state.transactionType = cfg.transactionType || 'Purchase';
    state.transactionNo = (cfg.getTransactionNo && cfg.getTransactionNo()) || cfg.transactionNo || 'NEW';
    const data = await postJson(`${API_BASE}/start`, {
      transaction_type: state.transactionType,
      transaction_no: state.transactionNo,
      machine_name: machineName(),
    });
    state.auditId = data.audit_id;
    state.started = true;
    trackFields(cfg.trackRoot || 'body');
    scheduleVideoStart(cfg);
    return state.auditId;
  };

  const parseTxNoFromRedirect = (locationHeader) => {
    if (!locationHeader) return null;
    try {
      const u = new URL(locationHeader, global.location.origin);
      const qp = u.searchParams.get('open_receipt_voucher_pdf')
        || u.searchParams.get('open_payment_voucher_pdf')
        || u.searchParams.get('open_cash_payment_voucher_pdf');
      if (qp) return qp;
      const pathMatch = u.pathname.match(/journal-entry\/voucher\/([^/]+)/i)
        || u.pathname.match(/cash-payment-voucher\/([^/]+)/i);
      if (pathMatch) return decodeURIComponent(pathMatch[1]);
    } catch (_) { /* ignore */ }
    return null;
  };

  const runComplete = async (cfg, status, afterShot, txNoOverride) => {
    if (!state.auditId || state.completing) return;
    state.completing = true;
    try {
      const txNo = txNoOverride
        || (cfg.getTransactionNo && cfg.getTransactionNo())
        || state.transactionNo;
      const videoBlob = await stopVideo();
      const videoB64 = await blobToBase64(videoBlob);
      const payload = {
        audit_id: state.auditId,
        transaction_type: state.transactionType,
        transaction_no: txNo,
        status: status || 'SAVED',
      };
      if (afterShot) payload.after_image_base64 = afterShot;
      if (videoB64) {
        payload.video_base64 = videoB64;
        payload.video_ext = (videoBlob && videoBlob.type.includes('mp4')) ? 'mp4' : 'webm';
      }
      const result = await postJson(`${API_BASE}/complete`, payload);
      if (!result.video_saved && videoB64) {
        console.warn('[TransactionAudit] Save completed but server did not store video.');
      } else if (result.video_saved) {
        console.info('[TransactionAudit] Video saved for audit #' + state.auditId);
      }
    } catch (err) {
      console.warn('[TransactionAudit] complete failed:', err);
    } finally {
      state.completing = false;
    }
  };

  const wrapSave = (cfg) => {
    const saveBtn = el(cfg.saveButton);
    if (!saveBtn || saveBtn.dataset.traWrapped === '1') return;
    saveBtn.dataset.traWrapped = '1';

    saveBtn.addEventListener('click', async () => {
      if (!state.auditId) return;
      state.transactionNo = (cfg.getTransactionNo && cfg.getTransactionNo()) || state.transactionNo;
      try {
        await ensureVideoStarted(cfg);
        const beforeShot = await captureScreenshot(cfg.trackRoot || 'body');
        if (beforeShot) {
          await postJson(`${API_BASE}/before-screenshot`, {
            audit_id: state.auditId,
            transaction_type: state.transactionType,
            transaction_no: state.transactionNo,
            image_base64: beforeShot,
          });
        }
        if (typeof cfg.onBeforeSave === 'function') {
          await cfg.onBeforeSave({ auditId: state.auditId, beforeShot });
        }
        saveBtn.dataset.traPendingComplete = '1';
      } catch (err) {
        console.warn('[TransactionAudit] before-save capture:', err);
      }
    }, true);

    global.addEventListener('nexa-transaction-save-success', async (ev) => {
      if (!state.auditId) return;
      const detail = ev.detail || {};
      const afterShot = await captureScreenshot(cfg.trackRoot || 'body');
      await runComplete(cfg, 'SAVED', afterShot);
      if (typeof cfg.onAfterSave === 'function') cfg.onAfterSave(detail);
    });

    global.addEventListener('nexa-transaction-save-failed', async () => {
      if (!state.auditId) return;
      const afterShot = await captureScreenshot(cfg.trackRoot || 'body');
      await runComplete(cfg, 'FAILED', afterShot);
    });

    if (cfg.saveUrlPattern) {
      const origFetch = global.fetch.bind(global);
      global.fetch = async (...args) => {
        const res = await origFetch(...args);
        try {
          const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
          const method = (args[1] && args[1].method) || 'GET';
          if (method.toUpperCase() === 'POST' && cfg.saveUrlPattern.test(url) && saveBtn.dataset.traPendingComplete === '1') {
            saveBtn.dataset.traPendingComplete = '0';
            const clone = res.clone();
            let ok = res.ok;
            try {
              const data = await clone.json();
              ok = ok && (data.success !== false);
            } catch (_) { /* ignore */ }
            const afterShot = await captureScreenshot(cfg.trackRoot || 'body');
            await runComplete(cfg, ok ? 'SAVED' : 'FAILED', afterShot);
          }
        } catch (err) {
          console.warn('[TransactionAudit] fetch hook:', err);
        }
        return res;
      };
    }
  };

  /**
   * Intercept classic form POST submits (bubble phase — runs after capture-phase validators).
   * Use data-audit-intercept-form="#myForm" on the page root.
   */
  const resetInterceptedFormUi = (form) => {
    if (!form) return;
    form.dataset.apSubmitLocked = '0';
    form.dataset.traSubmitting = '0';
    form.dataset.submitLocked = '0';
    form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (btn) {
      btn.disabled = false;
      if (btn.dataset.traPrevLabel) {
        btn.textContent = btn.dataset.traPrevLabel;
      }
    });
    if (typeof global.hideLoadingOverlay === 'function') {
      global.hideLoadingOverlay();
    }
    if (typeof global.reEnableFormSubmit === 'function') {
      global.reEnableFormSubmit(form);
    }
  };

  const applySaveNonceFromJson = (data) => {
    if (!data || typeof data.save_nonce !== 'string' || !data.save_nonce) return;
    global.__GLOBAL_SAVE_NONCE = data.save_nonce;
    const h = document.querySelector('input[name="save_nonce"]');
    if (h) h.value = data.save_nonce;
  };

  const wrapFormSubmit = (cfg) => {
    const form = el(cfg.interceptForm);
    if (!form || form.dataset.traFormWrapped === '1') return;
    form.dataset.traFormWrapped = '1';

    form.addEventListener('submit', async (e) => {
      if (form.dataset.traAllowNative === '1') {
        form.dataset.traAllowNative = '0';
        return;
      }
      if (e.defaultPrevented) return;
      if (form.dataset.traSubmitting === '1') {
        e.preventDefault();
        return;
      }
      e.preventDefault();

      form.dataset.traSubmitting = '1';
      try {
        state.transactionNo = (cfg.getTransactionNo && cfg.getTransactionNo()) || state.transactionNo;
        // Never block the business save on audit video/screenshot failures or CDN hangs.
        try {
          await Promise.race([
            ensureVideoStarted(cfg),
            new Promise((resolve) => setTimeout(resolve, 2500)),
          ]);
        } catch (_) { /* ignore */ }
        let beforeShot = null;
        try {
          beforeShot = await Promise.race([
            captureScreenshot(cfg.trackRoot || 'body'),
            new Promise((resolve) => setTimeout(() => resolve(null), 4000)),
          ]);
        } catch (_) {
          beforeShot = null;
        }
        if (beforeShot && state.auditId) {
          try {
            await postJson(`${API_BASE}/before-screenshot`, {
              audit_id: state.auditId,
              transaction_type: state.transactionType,
              transaction_no: state.transactionNo,
              image_base64: beforeShot,
            });
          } catch (_) { /* ignore audit upload errors */ }
        }
        if (typeof cfg.onBeforeSave === 'function') {
          try {
            await cfg.onBeforeSave({ auditId: state.auditId, beforeShot });
          } catch (_) { /* ignore */ }
        }

        const formData = new FormData(form, e.submitter || undefined);
        const action = form.getAttribute('action') || form.action || global.location.href;
        const method = (form.getAttribute('method') || form.method || 'POST').toUpperCase();
        const res = await fetch(action, {
          method,
          body: formData,
          credentials: 'same-origin',
          redirect: 'manual',
          headers: { 'X-Nexa-Form-Ajax': '1' },
        });

        const afterShot = await captureScreenshot(cfg.trackRoot || 'body');
        const ct = (res.headers.get('Content-Type') || '').toLowerCase();

        if (ct.indexOf('application/json') !== -1) {
          let data = {};
          try { data = await res.json(); } catch (_) { data = {}; }
          applySaveNonceFromJson(data);
          if (res.ok && data.success !== false && data.redirect) {
            const parsedNo = parseTxNoFromRedirect(data.redirect);
            await runComplete(cfg, 'SAVED', afterShot, parsedNo);
            global.location.href = new URL(data.redirect, global.location.origin).href;
            return;
          }
          await runComplete(cfg, 'FAILED', afterShot);
          resetInterceptedFormUi(form);
          global.alert(data.error || ('Save failed (HTTP ' + res.status + ').'));
          return;
        }

        if (res.status >= 300 && res.status < 400) {
          const loc = res.headers.get('Location');
          const parsedNo = parseTxNoFromRedirect(loc);
          await runComplete(cfg, 'SAVED', afterShot, parsedNo);
          if (loc) {
            global.location.href = new URL(loc, global.location.origin).href;
          } else {
            global.location.reload();
          }
          return;
        }

        await runComplete(cfg, 'FAILED', afterShot);
        const html = await res.text();
        if (!html || html.trim().length < 80) {
          resetInterceptedFormUi(form);
          global.alert(
            'Save failed: empty server response (HTTP ' + res.status + '). '
            + 'Reload the page and try again.'
          );
          return;
        }
        try {
          global.document.open('text/html', 'replace');
          global.document.write(html);
          global.document.close();
        } catch (writeErr) {
          console.warn('[TransactionAudit] document.write failed:', writeErr);
          form.dataset.traAllowNative = '1';
          resetInterceptedFormUi(form);
          form.submit();
        }
      } catch (err) {
        console.warn('[TransactionAudit] form submit intercept failed:', err);
        const afterShot = await captureScreenshot(cfg.trackRoot || 'body').catch(() => null);
        await runComplete(cfg, 'FAILED', afterShot);
        resetInterceptedFormUi(form);
        global.alert(err.message || 'Save failed');
      } finally {
        form.dataset.traSubmitting = '0';
      }
    }, false);
  };

  const init = async (cfg) => {
    const enabled = global.__TX_RECORDING_ENABLED__;
    if (enabled === false || enabled === 'N' || enabled === 'n' || enabled === 0 || enabled === '0') {
      return null;
    }
    if (!cfg || !cfg.transactionType) {
      console.warn('[TransactionAudit] transactionType required');
      return null;
    }
    try {
      await startSession(cfg);
      if (cfg.interceptForm) {
        wrapFormSubmit(cfg);
      } else {
        wrapSave(cfg);
      }
      return state.auditId;
    } catch (err) {
      console.warn('[TransactionAudit] init failed:', err);
      return null;
    }
  };

  const getTransactionNoFromPage = (meta, txNoSel) => () => {
    if (meta.dataset.transactionNo) return meta.dataset.transactionNo;
    const editVno = document.querySelector('input[name="edit_voucher_no"]');
    if (editVno && editVno.value) return editVno.value;
    if (txNoSel) {
      const n = document.querySelector(txNoSel);
      if (n && n.value) return n.value;
    }
    return 'NEW';
  };

  const autoInitFromDom = () => {
    const enabled = global.__TX_RECORDING_ENABLED__;
    if (enabled === false || enabled === 'N' || enabled === 'n' || enabled === 0 || enabled === '0') {
      return;
    }
    const meta = document.querySelector('[data-transaction-audit]');
    if (!meta) return;
    const type = meta.dataset.transactionAudit || meta.getAttribute('data-transaction-audit');
    const txNoSel = meta.dataset.transactionNoSelector;
    const saveSel = meta.dataset.saveButton;
    const rootSel = meta.dataset.trackRoot || '.page';
    const videoDisabled = meta.dataset.enableVideo === '0' || meta.dataset.enableVideo === 'false';
    const videoForced = meta.dataset.enableVideo === '1' || meta.dataset.enableVideo === 'true';
    const savePattern = meta.dataset.saveUrlPattern;
    const interceptForm = meta.dataset.auditInterceptForm || meta.dataset.auditForm;
    init({
      transactionType: type,
      getTransactionNo: getTransactionNoFromPage(meta, txNoSel),
      saveButton: interceptForm ? null : (saveSel || '[data-tra-save], .im-btn-save, #btnSave, #btnSaveAdjustment'),
      interceptForm,
      trackRoot: rootSel,
      enableVideo: videoDisabled ? false : (videoForced ? true : 'auto'),
      saveUrlPattern: savePattern ? new RegExp(savePattern) : null,
    });
  };

  global.NexaTransactionAudit = {
    init,
    captureScreenshot,
    ensureVideoStarted,
    extensionAvailable,
    get auditId() { return state.auditId; },
    get hasVideoRecording() {
      return !!(state.extensionRecording || state.videoRecorder);
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInitFromDom);
  } else {
    autoInitFromDom();
  }
})(window);
