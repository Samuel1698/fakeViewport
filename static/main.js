let lastScriptUptime = null;
document.addEventListener('DOMContentLoaded', () => {
  loadInfo();
  // auto-refresh every minute, but only if info is visible
  setInterval(loadInfo, 60_000);
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

  async function fetchJSON(path) {
    try {
      const r = await fetch(path);
      if (!r.ok) return null;
      return await r.json();
    } catch {
      return null;
    }
  }

  const sud = await fetchJSON('/api/script_uptime');
  const el = document.getElementById('scriptUptime');
  if (sud?.data && typeof sud.data.script_uptime === 'number') {
    const current = sud.data.script_uptime;

    // 2) If we’ve seen one value before and it didn’t change → Not Running
    if (lastScriptUptime !== null && current === lastScriptUptime) {
      el.textContent = 'Not Running';
    } else {
      el.textContent = formatDuration(current);
    }

    // 3) Update our “last seen” value
    lastScriptUptime = current;
  } else {
    // no data at all (empty file, 404, parse error…)
    el.textContent = 'Not Running';
    lastScriptUptime = null;
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
async function control(action, btn) {
  // 1) disable the button immediately
  btn.setAttribute('disabled', '');
  setTimeout(() => { btn.removeAttribute('disabled') }, 15_000);

  // 2) do your existing status-message logic
  const msgEl = document.querySelector('#statusMessage span');
  msgEl.textContent = '';
  msgEl.style.color = '';

  try {
    const res = await fetch(`/api/control/${action}`, { method: 'POST' });
    const js  = await res.json();

    if (js.status === 'ok') {
      msgEl.textContent = '✓ ' + js.message;
      msgEl.style.color   = 'green';
    } else {
      msgEl.textContent = '✗ ' + js.message;
      msgEl.style.color   = 'red';
    }
    await loadInfo();
    // reset the message after 15 seconds
    setTimeout(() => {
      msgEl.textContent = '';
      msgEl.style.color = '';
    }, 15_000);
    setTimeout(loadInfo, 15_000);
  } catch (e) {
    msgEl.textContent = '✗ ' + e;
    msgEl.style.color   = 'red';
  }
}