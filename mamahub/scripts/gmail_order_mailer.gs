/**
 * MamaHub order / reset mailer.
 * Deploy as a Web app (Execute as: Me, Who has access: Anyone).
 * Script property: MAIL_SECRET = same value as GMAIL_WEBAPP_SECRET in .env
 */
function doGet() {
  return json_({ ok: true, ready: true });
}

function doPost(e) {
  var secret = PropertiesService.getScriptProperties().getProperty('MAIL_SECRET') || '';
  var body = {};
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return json_({ ok: false, error: 'Invalid JSON' });
  }
  if (!secret || body.secret !== secret) {
    return json_({ ok: false, error: 'Unauthorized' });
  }
  var to = String(body.to || '').trim();
  var subject = String(body.subject || '').trim();
  var html = String(body.html || body.text || '');
  if (!to || !subject || !html) {
    return json_({ ok: false, error: 'to, subject, and html are required' });
  }
  var options = { htmlBody: html, name: String(body.name || 'MamaHub') };
  var fromAddr = String(body.from || '').trim();
  var replyTo = String(body.replyTo || fromAddr || '').trim();
  if (fromAddr) {
    var match = fromAddr.match(/<([^>]+)>/);
    options.from = match ? match[1] : fromAddr;
  }
  if (replyTo) {
    var replyMatch = replyTo.match(/<([^>]+)>/);
    options.replyTo = replyMatch ? replyMatch[1] : replyTo;
  }
  GmailApp.sendEmail(to, subject, String(body.text || ''), options);
  return json_({ ok: true });
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
