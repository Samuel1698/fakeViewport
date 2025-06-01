let lastScriptUptime = null;
// ----------------------------------------------------------------------------- 
// Helper functions
// ----------------------------------------------------------------------------- 
export async function fetchJSON(path) {
  try {
    const r = await fetch(path);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}
// format seconds → “Dd Hh Mm Ss”
function formatDuration(sec) {
  // break total seconds into days, leftover hours, minutes, seconds
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);

  // collect non-zero components
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0) parts.push(`${s}s`);

  // join with spaces, or return “0s” if none
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
// ----------------------------------------------------------------------------- 
// Main function
// ----------------------------------------------------------------------------- 
export async function loadInfo() {
  const sud = await fetchJSON("/api/script_uptime");
  const el = document.getElementById("scriptUptime");
  if (sud?.data && typeof sud.data.script_uptime === "number") {
    const current = sud.data.script_uptime;
    el.classList.remove("Green", "Red");
    // If we’ve seen one value before and it didn’t change → Not Running
    if (lastScriptUptime !== null && current === lastScriptUptime) {
      el.textContent = "Not Running";
      el.classList.add("Red");
    } else {
      el.textContent = formatDuration(current);
      el.classList.add("Green");
    }
    // Update our “last seen” value
    lastScriptUptime = current;
  } else {
    // no data at all (empty file, 404, parse error…)
    el.textContent = "Not Running";
    el.classList.add("Red");
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
    const used = (ram.data.ram_used / 1024 ** 3).toFixed(1);
    const tot = (ram.data.ram_total / 1024 ** 3).toFixed(1);
    const ramElement = document.getElementById("ram");

    // Calculate percentage used (0-100)
    const pctUsed = (ram.data.ram_used / ram.data.ram_total) * 100;

    ramElement.textContent = `${used} GiB / ${tot} GiB`;
    ramElement.classList.remove("Green", "Yellow", "Red");

    // Add the appropriate class based on percentage
    if (pctUsed <= 35) {
      ramElement.classList.add("Green");
    } else if (pctUsed <= 60) {
      ramElement.classList.add("Yellow");
    } else {
      ramElement.classList.add("Red");
    }
  }

  // intervals
  const hi = await fetchJSON("/api/health_interval");
  if (hi?.data) {
    // convert seconds → minutes (round to nearest whole minute)
    const minutes = Math.round(hi.data.health_interval_sec / 60);
    // render in “X min” format
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
    const entry = document.getElementById("logEntry");
    entry.textContent = le.data.log_entry;
    entry.classList.remove("Green", "Blue", "Red");
    if (entry.textContent.includes("[INFO]")) {
      entry.classList.add("Green");
    } else if (entry.textContent.includes("[ERROR]")) {
      entry.classList.add("Red");
    } else if (entry.textContent.includes("[DEBUG]")) {
      entry.classList.add("Blue");
    }
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
