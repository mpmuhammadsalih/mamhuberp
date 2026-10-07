(function () {
  'use strict';

  const app = document.getElementById('traViewerApp');
  if (!app) return;

  const apiList = app.dataset.apiList;
  const apiDetailBase = (app.dataset.apiDetail || '').replace(/\/0$/, '');
  const apiUsers = app.dataset.apiUsers;
  const fileBase = app.dataset.fileBase || '';
  const replayBase = app.dataset.replayBase || '';
  const tbody = document.getElementById('traTableBody');
  const form = document.getElementById('traFilterForm');
  const userSel = document.getElementById('traUser');

  const fmtTime = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso.slice(11, 19) || iso;
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const badge = (st) => {
    const s = (st || 'OPEN').toUpperCase();
    const cls = s === 'SAVED' ? 'saved' : (s === 'FAILED' ? 'failed' : 'open');
    return `<span class="tra-badge tra-badge--${cls}">${s}</span>`;
  };

  const openModal = (id, title, html) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    document.getElementById(id === 'traMediaModal' ? 'traMediaTitle' : 'traHistoryTitle').textContent = title;
    document.getElementById(id === 'traMediaModal' ? 'traMediaBody' : 'traHistoryBody').innerHTML = html;
    modal.classList.remove('hidden');
  };

  const closeModal = (id) => {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('hidden');
  };

  document.querySelectorAll('[data-close]').forEach((el) => {
    el.addEventListener('click', () => closeModal(el.dataset.close));
  });

  const loadUsers = async () => {
    try {
      const res = await fetch(apiUsers);
      const data = await res.json();
      (data.usernames || []).forEach((u) => {
        const opt = document.createElement('option');
        opt.value = u;
        opt.textContent = u;
        userSel.appendChild(opt);
      });
    } catch (_) { /* ignore */ }
  };

  const updateKpis = (rows) => {
    document.getElementById('traKpiCount').textContent = String(rows.length);
    document.getElementById('traKpiSaved').textContent = String(rows.filter((r) => (r.status || '').toUpperCase() === 'SAVED').length);
    document.getElementById('traKpiFailed').textContent = String(rows.filter((r) => (r.status || '').toUpperCase() === 'FAILED').length);
  };

  const renderRows = (rows) => {
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="tra-empty">No audit records found.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((r) => {
      const failed = (r.status || '').toUpperCase() === 'FAILED';
      const actions = [];
      if (r.before_image_path) {
        actions.push(`<button type="button" class="tra-action-btn" data-media="image" data-src="${fileBase}${r.before_image_path}">Before</button>`);
      }
      if (r.after_image_path) {
        actions.push(`<button type="button" class="tra-action-btn" data-media="image" data-src="${fileBase}${r.after_image_path}">After</button>`);
      }
      if (r.video_path) {
        actions.push(`<button type="button" class="tra-action-btn" data-media="video" data-src="${fileBase}${r.video_path}">Video</button>`);
      } else if ((r.before_image_path || r.after_image_path) && (r.status || '').toUpperCase() === 'SAVED') {
        actions.push(`<span class="tra-action-muted" title="No video was saved. Use the Nexa Audit Recorder extension on a transaction form (GRN, PO, etc.), click the form, then Save.">No video</span>`);
      }
      actions.push(`<button type="button" class="tra-action-btn" data-history="${r.audit_id}">History</button>`);
      actions.push(`<a class="tra-action-btn" href="${replayBase.replace('__ID__', r.audit_id)}">Replay</a>`);
      return `<tr class="${failed ? 'tra-row-failed' : ''}">
        <td>${r.transaction_type_label || r.transaction_type || ''}</td>
        <td>${r.transaction_no || '—'}</td>
        <td>${r.username || ''}</td>
        <td>${r.date || '—'}</td>
        <td>${fmtTime(r.start_time)}</td>
        <td>${fmtTime(r.end_time)}</td>
        <td>${r.duration_label || '—'}</td>
        <td>${badge(r.status)}</td>
        <td><div class="tra-actions">${actions.join('')}</div></td>
      </tr>`;
    }).join('');
  };

  const loadList = async () => {
    tbody.innerHTML = '<tr><td colspan="9" class="tra-empty">Loading…</td></tr>';
    const params = new URLSearchParams(new FormData(form));
    const res = await fetch(`${apiList}?${params.toString()}`);
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Load failed');
    renderRows(data.rows || []);
    updateKpis(data.rows || []);
  };

  tbody.addEventListener('click', async (e) => {
    const mediaBtn = e.target.closest('[data-media]');
    if (mediaBtn) {
      const src = mediaBtn.dataset.src;
      const kind = mediaBtn.dataset.media;
      const html = kind === 'video'
        ? `<video controls autoplay src="${src}"></video>`
        : `<img src="${src}" alt="Screenshot" />`;
      openModal('traMediaModal', mediaBtn.textContent.trim(), html);
      return;
    }
    const histBtn = e.target.closest('[data-history]');
    if (histBtn) {
      const id = histBtn.dataset.history;
      const res = await fetch(`${apiDetailBase}/${id}`);
      const data = await res.json();
      if (!data.success && !data.changes) {
        alert(data.error || 'Failed to load history');
        return;
      }
      const rows = (data.changes || []).map((c) =>
        `<tr><td>${(c.change_time || '').slice(11, 19)}</td><td>${c.field_name}</td><td class="tra-old">${c.old_value || ''}</td><td class="tra-new">${c.new_value || ''}</td></tr>`
      ).join('') || '<tr><td colspan="4" class="tra-empty">No changes recorded.</td></tr>';
      openModal('traHistoryModal', `Change History — #${id}`, `<table class="co-table tra-table"><thead><tr><th>Time</th><th>Field</th><th>Old</th><th>New</th></tr></thead><tbody>${rows}</tbody></table>`);
    }
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    loadList().catch((err) => alert(err.message || 'Search failed'));
  });

  document.getElementById('traResetFilters').addEventListener('click', () => {
    form.reset();
    loadList().catch(() => {});
  });

  const today = new Date();
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);
  const toIso = (d) => d.toISOString().slice(0, 10);
  document.getElementById('traDateFrom').value = toIso(monthAgo);
  document.getElementById('traDateTo').value = toIso(today);

  loadUsers().finally(() => loadList().catch((err) => {
    tbody.innerHTML = `<tr><td colspan="9" class="tra-empty">${err.message || 'Load failed'}</td></tr>`;
  }));
})();
