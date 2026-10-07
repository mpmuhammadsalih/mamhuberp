# Nexa ERP Transaction Audit Recorder (Chrome extension)

Silent **tab video** recording for Nexa transaction audit pages — **no Chrome “Share your screen” dialog** after the extension is installed.

## What it does

- Records the **ERP browser tab** while you work on GRN, PO, sales, journal entry, etc.
- Works with the built-in `transaction_recording_client.js` (screenshots + field changes + video).
- Uses Chrome `tabCapture` + offscreen recording (install-time permission).

## What it does *not* do

- **Full desktop / entire monitor** capture without any prompt is **not possible** in normal Chrome for security reasons.
- This extension captures the **Nexa tab only** (everything visible in that tab while you scroll/work).

## Install (development / internal)

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select this folder:  
   `browser_extension/nexa_audit_recorder`
5. Pin the extension if you like (optional)

## Use

1. Install the extension once (above).
2. Open Nexa ERP on a supported URL, e.g.:
   - `https://test.nexuserp.store/...`
   - `http://localhost:5051/...`
3. Open any transaction page with audit enabled (GRN, PO, etc.).
4. Video starts **automatically** when the audit session starts — **no Share dialog**.

To **disable video** even with the extension installed, add on the page:

```html
data-enable-video="0"
```

To force the old browser Share dialog (without extension), set:

```html
data-enable-video="1"
```

(without the extension installed)

## Add your ERP domain

If you use another hostname, edit `manifest.json` → `host_permissions` and `content_scripts.matches`, then click **Reload** on `chrome://extensions`.

Example for production:

```json
"https://erp.yourcompany.com/*"
```

## Verify extension is connected

In DevTools console on a transaction page:

```javascript
document.documentElement.dataset.nexaAuditExt
// should be "1" when extension is active
```

If it is **undefined**, the extension is **not injected on this URL** (reload extension after manifest edits). Open a **transaction form** (GRN/PO), click once in the form, then save.

## Troubleshooting

| Issue | Fix |
|--------|-----|
| Extension installed but no video | ERP opened at `http://192.168.x.x:5051` — reload extension v1.0.1+ (includes LAN hosts) |
| `nexaAuditExt` not `"1"` | URL not in manifest `matches`; add host → **Reload** on `chrome://extensions` |
| No video after save | Click **inside the form once** before Save (Chrome gesture for tab capture) |

## Files

| File | Role |
|------|------|
| `manifest.json` | Extension config (MV3) |
| `background.js` | Tab capture + offscreen orchestration |
| `offscreen.html/js` | MediaRecorder in offscreen document |
| `content-bridge.js` | Bridge between ERP page and extension |
