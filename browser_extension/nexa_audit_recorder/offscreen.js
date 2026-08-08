'use strict';

let recorder = null;
let chunks = [];
let stream = null;

function stopTracks() {
  if (stream) {
    stream.getTracks().forEach((t) => {
      try { t.stop(); } catch (_) { /* ignore */ }
    });
    stream = null;
  }
  recorder = null;
  chunks = [];
}

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return '';
  if (MediaRecorder.isTypeSupported('video/webm;codecs=vp9')) return 'video/webm;codecs=vp9';
  if (MediaRecorder.isTypeSupported('video/webm')) return 'video/webm';
  return '';
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    if (!blob) return resolve(null);
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function getTabStream(streamId) {
  const attempts = [
    {
      audio: false,
      video: {
        chromeMediaSource: 'tab',
        chromeMediaSourceId: streamId,
      },
    },
    {
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId,
        },
      },
    },
  ];
  let lastErr = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error('Could not open tab capture stream');
}

async function startCapture(streamId) {
  stopTracks();
  if (!streamId) {
    throw new Error('Missing tab capture stream id');
  }
  stream = await getTabStream(streamId);
  chunks = [];
  const mime = pickMimeType();
  recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size) chunks.push(event.data);
  };
  recorder.start(4000);
  return { ok: true };
}

async function stopCapture() {
  if (!recorder || recorder.state === 'inactive') {
    stopTracks();
    return { ok: true, videoBase64: null, mimeType: 'video/webm' };
  }

  const mimeType = recorder.mimeType || 'video/webm';
  const blob = await new Promise((resolve) => {
    recorder.onstop = () => {
      resolve(chunks.length ? new Blob(chunks, { type: mimeType }) : null);
    };
    try {
      if (recorder.state === 'recording') {
        recorder.requestData();
      }
      recorder.stop();
    } catch (_) {
      resolve(null);
    }
  });
  await new Promise((r) => setTimeout(r, 350));

  stopTracks();
  const videoBase64 = await blobToDataUrl(blob);
  return { ok: true, videoBase64, mimeType };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.target !== 'nexa-audit-offscreen') {
    return false;
  }

  (async () => {
    try {
      if (message.action === 'START') {
        sendResponse(await startCapture(message.streamId));
        return;
      }
      if (message.action === 'STOP') {
        sendResponse(await stopCapture());
        return;
      }
      sendResponse({ ok: false, error: 'Unknown offscreen action' });
    } catch (err) {
      sendResponse({ ok: false, error: String(err && err.message ? err.message : err) });
    }
  })();

  return true;
});
