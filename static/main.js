let updateCache = {
  timestamp: 0,
  data: null,    // { current, latest, changelog, releaseUrl }
};
let lastScriptUptime = null;
const CACHE_TTL = 60 * 60 * 1000; // 1 hour
document.addEventListener("DOMContentLoaded", () => {
  loadInfo();
  checkForUpdate();
  setInterval(loadInfo, 60_000);
  setInterval(checkForUpdate, CACHE_TTL);
});
// compares version of updates
function cmpVersions(a, b) {
  const pa = a.split(".").map(Number),
    pb = b.split(".").map(Number);
  for (let i = 0, n = Math.max(pa.length, pb.length); i < n; i++) {
    const x = pa[i] || 0,
      y = pb[i] || 0;
    if (x > y) return 1;
    if (x < y) return -1;
  }
  return 0;
}
//  Fetch both /update and /update/changelog in parallel, 
//  cache for an hour, return { current, latest, changelog, releaseUrl } 
async function loadUpdateData() {
  const now = Date.now();
  if (updateCache.data && now - updateCache.timestamp < CACHE_TTL) {
    return updateCache.data;
  }

  // parallel fetch
  const [verRes, logRes] = await Promise.all([
    fetchJSON('/update'),
    fetch('/update/changelog').then(r => r.json())
  ]);

  if (!verRes?.data) {
    throw new Error('Failed to fetch version info');
  }
  if (logRes.status !== 'ok') {
    throw new Error('Failed to fetch changelog');
  }

  const { current, latest } = verRes.data;
  const { changelog, release_url: releaseUrl } = logRes.data;

  updateCache = {
    timestamp: now,
    data: { current, latest, changelog, releaseUrl }
  };
  return updateCache.data;
}
// Call on page-load (and once per hour via setInterval)
// to reveal the banner if latest > current.
async function checkForUpdate() {
  try {
    const { current, latest } = await loadUpdateData();
    if (cmpVersions(latest, current) <= 0) return;

    const banner = document.getElementById('updateBanner');
    if (banner) banner.removeAttribute('hidden');
  } catch (err) {
    console.error('Update check failed:', err);
  }
}
// Just reads from the cache populated by checkForUpdate()
// and populates your modal.
function showChangelog() {
  const info = updateCache.data;
  if (!info) {
    console.error('No update data; did you call checkForUpdate()?');
    return;
  }
  const { latest, changelog, releaseUrl } = info;

  document
    .querySelector('#changelogModal .container h2')
    .textContent = `Release v${latest}`;

  document.getElementById('changelog-body').innerHTML =
    marked.parse(changelog);

  document.getElementById('changelog-link').href = releaseUrl;
  document.getElementById('changelogModal')
    .removeAttribute('hidden');
}
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
  return parts.length > 0 ? parts.join(" ") : "0s";
}
const formatter = new Intl.DateTimeFormat("en-US", {
  month: "short", // "May"
  day: "2-digit", // "09"
  year: "numeric", // "2025"
  hour: "2-digit", // "02"
  minute: "2-digit", // "00"
  hour12: false,
});
async function fetchJSON(path) {
  try {
    const r = await fetch(path);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}
// fetch+render all API data
async function loadInfo() {
  const sud = await fetchJSON("/api/script_uptime");
  const el = document.getElementById("scriptUptime");
  if (sud?.data && typeof sud.data.script_uptime === "number") {
    const current = sud.data.script_uptime;

    // 2) If we’ve seen one value before and it didn’t change → Not Running
    if (lastScriptUptime !== null && current === lastScriptUptime) {
      el.textContent = "Not Running";
    } else {
      el.textContent = formatDuration(current);
    }

    // 3) Update our “last seen” value
    lastScriptUptime = current;
  } else {
    // no data at all (empty file, 404, parse error…)
    el.textContent = "Not Running";
    lastScriptUptime = null;
  }
  // system uptime
  const syu = await fetchJSON("/api/system_uptime");
  if (syu?.data) {
    document.getElementById("systemUptime").textContent = formatDuration(
      syu.data.system_uptime
    );
  }

  // RAM usage (GiB)
  const ram = await fetchJSON("/api/ram");
  if (ram?.data) {
    const used = (ram.data.ram_used / 1024 ** 3).toFixed(1),
      tot = (ram.data.ram_total / 1024 ** 3).toFixed(1);
    document.getElementById("ram").textContent = `${used} GiB / ${tot} GiB`;
  }

  // intervals
  const hi = await fetchJSON("/api/health_interval");
  if (hi?.data) {
    // 1) convert seconds → minutes (round to nearest whole minute)
    const minutes = Math.round(hi.data.health_interval_sec / 60);
    // 2) render in “X min” format
    document.getElementById("healthInterval").textContent = `${minutes} min`;
  }
  const li = await fetchJSON("/api/log_interval");
  if (li?.data) {
    document.getElementById(
      "logInterval"
    ).textContent = `${li.data.log_interval_min} min`;
  }

  // last status, log entry & restart time
  const st = await fetchJSON("/api/status");
  if (st?.data) {
    document.getElementById("statusMsg").textContent = st.data.status;
  }
  const le = await fetchJSON("/api/log_entry");
  if (le?.data) {
    document.getElementById("logEntry").textContent = le.data.log_entry;
  }
  const sr = await fetchJSON("/api/next_restart");
  const srel = document.getElementById("scheduledRestart");

  if (sr?.data?.next_restart) {
    // parse into a Date object
    const next = new Date(sr.data.next_restart);

    // format & show
    srel.textContent = formatter.format(next).replace(/, /g, " ");

    // make sure it's visible
    srel.parentElement.removeAttribute("hidden");
  } else {
    // hide if no data
    srel.parentElement.setAttribute("hidden", "");
  }
}
// send control and update inline message
async function control(action, btn) {
  // disable the button immediately
  btn.setAttribute("disabled", "");
  setTimeout(() => {
    btn.removeAttribute("disabled");
  }, 15_000);

  const msgEl = document.querySelector("#statusMessage span");
  msgEl.textContent = "";
  msgEl.style.color = "";

  try {
    const res = await fetch(`/api/control/${action}`, { method: "POST" });
    const js = await res.json();

    if (js.status === "ok") {
      msgEl.textContent = "✓ " + js.message;
      msgEl.style.color = "green";
    } else {
      msgEl.textContent = "✗ " + js.message;
      msgEl.style.color = "red";
    }
    await loadInfo();
    // reset the message after 15 seconds
    setTimeout(() => {
      msgEl.textContent = "";
      msgEl.style.color = "";
    }, 15_000);
    setTimeout(loadInfo, 15_000);
  } catch (e) {
    msgEl.textContent = "✗ " + e;
    msgEl.style.color = "red";
  }
}
// send update
async function applyUpdate(btn) {
  btn.disabled = true;
  btn.textContent = "Updating…";
  try {
    const r = await fetch("/update/apply", { method: "POST" });
    const js = await r.json();
    btn.textContent = js?.data?.outcome?.startsWith("updated")
      ? "Updated - restarting…"
      : "Update failed";
    // give the backend a moment, then reload
    if (js?.data?.outcome?.startsWith("updated")) {
      const res = await fetch(`/api/control/restart`, { method: "POST" });
      const js = await res.json();
      if (js.status === "ok") {
        setTimeout(() => location.reload(), 5000);
      }
    }
  } catch {
    btn.textContent = "Update failed";
  }
}
const logsBtn   = document.getElementById("showLogsBtn");
const update    = document.getElementById("updateBanner");
const output    = document.getElementById("logOutput");
const modal     = document.getElementById("logsModal");
const modals    = document.querySelectorAll(".modal");
const closeBtns = document.querySelectorAll(".close");

logsBtn.addEventListener("click", async () => {
  // fetch the last 100 lines
  const res = await fetchJSON(`/api/logs?limit=100`);
  if (res?.data?.logs) {
    // join the array into one blob of text
    output.textContent = res.data.logs.join("");
    modal.removeAttribute("hidden");
  } else {
    // you could alert or console.error here
    modal.setAttribute("hidden", "");
  }
});
update.addEventListener("click", showChangelog);
// update.addEventListener('click', e => applyUpdate(e.target));
// close handlers
// clicking the backdrop (i.e. the modal itself) hides it
modals.forEach(modal => {
  modal.addEventListener('click', e => {
    if (e.target === modal) {
      modal.setAttribute('hidden', '');
    }
  });
});

// clicking any .close button hides *its* containing modal
closeBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const modal = btn.closest('.modal');
    if (modal) modal.setAttribute('hidden', '');
  });
});