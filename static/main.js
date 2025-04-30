document.addEventListener('DOMContentLoaded', () => {
  loadInfo();
  // auto-refresh every minute, but only if info is visible
  setInterval(() => {
    loadInfo();
  }, 60_000);
});
// format seconds → “Dd Hh Mm Ss”
function formatDuration(sec) {
  // 1) break total seconds into days, leftover hours, minutes, seconds
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);

  // 2) collect non-zero components
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0) parts.push(`${s}s`);

  // 3) join with spaces, or return “0s” if none
  return parts.length > 0
    ? parts.join(' ')
    : '0s';
}

// fetch+render all API data
async function loadInfo() {
  const token   = localStorage.getItem('viewport_api_key'),
        headers = { 'X-API-KEY': token };

  async function fetchJSON(path) {
    try {
      const r = await fetch(path, { headers });
      if (!r.ok) return null;
      return await r.json();
    } catch {
      return null;
    }
  }

  // script uptime
  const sud = await fetchJSON('/api/script_uptime');
  if (sud?.data) {
    document.getElementById('scriptUptime')
            .textContent = formatDuration(sud.data.script_uptime);
  }

  // system uptime
  const syu = await fetchJSON('/api/system_uptime');
  if (syu?.data) {
    document.getElementById('systemUptime')
            .textContent = formatDuration(syu.data.system_uptime);
  }

  // RAM usage (GiB)
  const ram = await fetchJSON('/api/ram');
  if (ram?.data) {
    const used = (ram.data.ram_used/1024**3).toFixed(1),
          tot  = (ram.data.ram_total/1024**3).toFixed(1);
    document.getElementById('ram')
            .textContent = `${used} GiB / ${tot} GiB`;
  }

  // intervals
  const hi = await fetchJSON('/api/health_interval');
  if (hi?.data) {
    // 1) convert seconds → minutes (round to nearest whole minute)
    const minutes = Math.round(hi.data.health_interval_sec / 60);
    // 2) render in “X min” format
    document.getElementById('healthInterval')
            .textContent = `${minutes} min`;
  }
  const li = await fetchJSON('/api/log_interval');
  if (li?.data) {
    document.getElementById('logInterval')
            .textContent = `${li.data.log_interval_min} min`;
  }

  // last status & log entry
  const st = await fetchJSON('/api/status');
  if (st?.data) {
    document.getElementById('statusMsg')
            .textContent = st.data.status;
  }
  const le = await fetchJSON('/api/log_entry');
  if (le?.data) {
    document.getElementById('logEntry')
            .textContent = le.data.log_entry;
  }
}

// send control and update inline message
async function control(action) {
  const msgEl = document.getElementById('statusMessage');
  msgEl.textContent = '';
  const token = localStorage.getItem('viewport_api_key');
  if (!token) {
    msgEl.textContent = '✗ No API key saved';
    msgEl.style.color   = 'red';
    return;
  }

  try {
    const res = await fetch(`/api/control/${action}`, {
      method: 'POST', headers:{ 'X-API-KEY':token }
    });
    const js = await res.json();
    if (js.status==='ok') {
      msgEl.textContent = '✓ ' + js.message;
      msgEl.style.color = 'green';
    } else {
      msgEl.textContent = '✗ ' + js.message;
      msgEl.style.color = 'red';
    }
  } catch (e) {
    msgEl.textContent = '✗ ' + e;
    msgEl.style.color = 'red';
  }
}