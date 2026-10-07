(function () {
  'use strict';

  const changes = window.__TRA_REPLAY_CHANGES__ || [];
  const table = document.getElementById('traReplayTable');
  const rows = table ? Array.from(table.querySelectorAll('tbody tr[data-index]')) : [];
  const currentEl = document.getElementById('traReplayCurrent');
  const bar = document.getElementById('traReplayBar');
  const btnPlay = document.getElementById('traReplayPlay');
  const btnPause = document.getElementById('traReplayPause');

  let timer = null;
  let idx = -1;

  const showStep = (i) => {
    rows.forEach((r) => r.classList.remove('is-active'));
    if (i < 0 || i >= changes.length) {
      currentEl.innerHTML = '<p class="tra-replay-hint">Replay complete.</p>';
      bar.style.width = '100%';
      return;
    }
    rows[i]?.classList.add('is-active');
    rows[i]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const c = changes[i];
    const pct = changes.length ? Math.round(((i + 1) / changes.length) * 100) : 0;
    bar.style.width = `${pct}%`;
    currentEl.innerHTML = `
      <div class="tra-replay-highlight">
        <div><strong>Step ${i + 1} of ${changes.length}</strong> · ${(c.change_time || '').slice(11, 19)}</div>
        <div>Field: <strong>${c.field_name || ''}</strong></div>
        <div>Old: <span class="tra-old">${c.old_value || '—'}</span></div>
        <div>New: <span class="tra-new">${c.new_value || '—'}</span></div>
      </div>`;
  };

  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
    btnPlay.disabled = false;
    btnPause.disabled = true;
  };

  const play = () => {
    if (!changes.length) return;
    stop();
    btnPlay.disabled = true;
    btnPause.disabled = false;
    if (idx >= changes.length - 1) idx = -1;
    showStep(idx + 1);
    idx += 1;
    timer = setInterval(() => {
      if (idx >= changes.length) {
        stop();
        return;
      }
      showStep(idx);
      idx += 1;
    }, 1200);
  };

  btnPlay?.addEventListener('click', play);
  btnPause?.addEventListener('click', () => {
    stop();
  });
})();
