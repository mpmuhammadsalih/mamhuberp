'use strict';

const CHANNEL = 'NEXA_AUDIT_RECORDER';
const EXT_VERSION = chrome.runtime.getManifest().version;

function markExtensionReady() {
  try {
    document.documentElement.dataset.nexaAuditExt = '1';
    document.documentElement.dataset.nexaAuditExtVersion = EXT_VERSION;
  } catch (_) { /* ignore */ }
}

function replyToPage(payload) {
  window.postMessage({ channel: CHANNEL, ...payload }, '*');
}

function forwardToBackground(action, reqId, extra) {
  return chrome.runtime.sendMessage({
    target: 'nexa-audit-background',
    action,
    reqId,
    ...extra,
  });
}

markExtensionReady();

window.addEventListener('message', (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (!data || data.channel !== CHANNEL) return;

  const reqId = data.reqId || null;

  if (data.action === 'PING') {
    replyToPage({ action: 'PONG', reqId, ok: true, version: EXT_VERSION });
    return;
  }

  if (data.action === 'START') {
    forwardToBackground('START_CAPTURE', reqId)
      .then((resp) => {
        replyToPage({
          action: 'STARTED',
          reqId,
          ok: !!(resp && resp.ok !== false),
          error: resp && resp.error,
        });
      })
      .catch((err) => {
        replyToPage({
          action: 'STARTED',
          reqId,
          ok: false,
          error: String(err && err.message ? err.message : err),
        });
      });
    return;
  }

  if (data.action === 'STOP') {
    forwardToBackground('STOP_CAPTURE', reqId)
      .then((resp) => {
        replyToPage({
          action: 'STOPPED',
          reqId,
          ok: !!(resp && resp.ok !== false),
          videoBase64: resp && resp.videoBase64,
          mimeType: (resp && resp.mimeType) || 'video/webm',
          error: resp && resp.error,
        });
      })
      .catch((err) => {
        replyToPage({
          action: 'STOPPED',
          reqId,
          ok: false,
          error: String(err && err.message ? err.message : err),
        });
      });
  }
});

replyToPage({ action: 'READY', version: EXT_VERSION });
