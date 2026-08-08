(function () {
  'use strict';

  const app = document.getElementById('traDashboardApp');
  if (!app) return;

  const api = app.dataset.api;

  const load = async () => {
    const res = await fetch(api);
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Load failed');

    document.getElementById('traDashToday').textContent = String(data.transactions_today ?? '—');
    document.getElementById('traDashAudited').textContent = String(data.audited_saved ?? '—');
    document.getElementById('traDashFailed').textContent = String(data.failed_saves ?? '—');

    const usersEl = document.getElementById('traDashUsers');
    const users = data.most_active_users || [];
    usersEl.innerHTML = users.length
      ? users.map((u) => `<li><span>${u.username}</span><strong>${u.count}</strong></li>`).join('')
      : '<li class="tra-empty">No activity in the last 30 days.</li>';

    const adjEl = document.getElementById('traDashAdjustments');
    const adj = data.recent_stock_adjustments || [];
    adjEl.innerHTML = adj.length
      ? adj.map((a) => `<tr>
          <td>${a.transaction_no || '—'}</td>
          <td>${a.username || ''}</td>
          <td>${(a.start_time || '').slice(0, 19).replace('T', ' ')}</td>
          <td><span class="tra-badge tra-badge--${(a.status || 'open').toLowerCase()}">${a.status || ''}</span></td>
        </tr>`).join('')
      : '<tr><td colspan="4" class="tra-empty">No recent stock adjustments.</td></tr>';
  };

  load().catch((err) => {
    document.getElementById('traDashToday').textContent = '!';
    alert(err.message || 'Dashboard load failed');
  });
})();
