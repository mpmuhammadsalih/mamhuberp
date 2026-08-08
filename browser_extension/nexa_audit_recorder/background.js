'use strict';

const OFFSCREEN_URL = 'offscreen.html';

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) {
    return;
  }
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ['USER_MEDIA'],
    justification: 'Record Nexa ERP browser tab for transaction audit compliance',
  });
}

async function sendToOffscreen(message) {
  await ensureOffscreen();
  return chrome.runtime.sendMessage({ target: 'nexa-audit-offscreen', ...message });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.target !== 'nexa-audit-background') {
    return false;
  }

  (async () => {
    try {
      if (message.action === 'PING') {
        sendResponse({ ok: true, version: chrome.runtime.getManifest().version });
        return;
      }

      if (message.action === 'START_CAPTURE') {
        const tabId = sender.tab && sender.tab.id;
        if (!tabId) {
          sendResponse({ ok: false, error: 'No active tab' });
          return;
        }
        const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
        const result = await sendToOffscreen({
          action: 'START',
          streamId,
        });
        sendResponse(result || { ok: true });
        return;
      }

      if (message.action === 'STOP_CAPTURE') {
        const result = await sendToOffscreen({ action: 'STOP' });
        sendResponse(result || { ok: true });
        return;
      }

      sendResponse({ ok: false, error: 'Unknown action' });
    } catch (err) {
      sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
    }
  })();

  return true;
});
