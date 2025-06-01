let lastScriptUptime = null;
let activeTab = "status"; 
import { loadUpdateData } from "./_update.js";

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
function compareVersions(current, latest) {
  const currentParts = current.split(".").map(Number);
  const latestParts = latest.split(".").map(Number);

  // Compare major versions
  if (latestParts[0] > currentParts[0]) {
    return "major";
  }
  // Compare minor versions if majors are equal
  if (latestParts[1] > currentParts[1]) {
    return "minor";
  }
  // Compare patch versions if majors and minors are equal
  if (latestParts[2] > currentParts[2]) {
    return "patch";
  }
  return "current";
}
// -----------------------------------------------------------------------------
// Status-related updates (frequent updates)
// -----------------------------------------------------------------------------
export async function loadStatus() {
  const sud = await fetchJSON("/api/script_uptime");
  const el = document.getElementById("scriptUptime");
  if (sud?.data && typeof sud.data.script_uptime === "number") {
    const current = sud.data.script_uptime;
    el.classList.remove("Green", "Red");
    if (lastScriptUptime !== null && current === lastScriptUptime) {
      el.textContent = "Not Running";
      el.classList.add("Red");
    } else {
      el.textContent = formatDuration(current);
      el.classList.add("Green");
    }
    lastScriptUptime = current;
  } else {
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
  const st = await fetchJSON("/api/status");
  if (st?.data) {
    const entry = document.getElementById("statusMsg");
    entry.textContent = st.data.status;
    entry.classList.remove("Green", "Blue", "Red");
    if (
      entry.textContent.includes("Healthy") ||
      entry.textContent.includes("Resumed") ||
      entry.textContent.includes("restart") ||
      entry.textContent.includes("Fullscreen") ||
      entry.textContent.includes("Saved")
    ) {
      entry.classList.add("Green");
    } else if (
      entry.textContent.includes("Stopped") ||
      entry.textContent.includes("Killed") ||
      entry.textContent.includes("Restarting") ||
      entry.textContent.includes("Loaded") ||
      entry.textContent.includes("Crashed") ||
      entry.textContent.includes("Retrying") ||
      entry.textContent.includes("Starting")
    ) {
      entry.classList.add("Blue");
    } else if (
      entry.textContent.includes("Error") ||
      entry.textContent.includes("stuck") ||
      entry.textContent.includes("Unsupported") ||
      entry.textContent.includes("Timed") ||
      entry.textContent.includes("Issue") ||
      entry.textContent.includes("Couldn't") ||
      entry.textContent.includes("Paused") ||
      entry.textContent.includes("Offline") ||
      entry.textContent.includes("unresponsive") ||
      entry.textContent.includes("Not Found") ||
      entry.textContent.includes("Error")
    ) {
      entry.classList.add("Red");
    }
  }
  // RAM usage (GiB)
  const ram = await fetchJSON("/api/ram");
  if (ram?.data) {
    const used = (ram.data.ram_used / 1024 ** 3).toFixed(1);
    const tot = (ram.data.ram_total / 1024 ** 3).toFixed(1);
    const ramElement = document.getElementById("ram");

    const pctUsed = (ram.data.ram_used / ram.data.ram_total) * 100;
    ramElement.textContent = `${used} GiB / ${tot} GiB`;
    ramElement.classList.remove("Green", "Yellow", "Red");

    if (pctUsed <= 35) {
      ramElement.classList.add("Green");
    } else if (pctUsed <= 60) {
      ramElement.classList.add("Yellow");
    } else {
      ramElement.classList.add("Red");
    }
  }
}
// -----------------------------------------------------------------------------
// Info-related updates (less frequent updates)
// -----------------------------------------------------------------------------
export async function loadInfoData() {
  // Version
  try {
    const { current, latest } = await loadUpdateData();
    const versionElement = document.getElementById("version");

    const comparison = compareVersions(current, latest);
    versionElement.textContent = `${current}`;
    versionElement.classList.remove("Green", "Yellow", "Red");

    switch (comparison) {
      case "current":
        versionElement.classList.add("Green");
        break;
      case "patch":
        versionElement.classList.add("Yellow");
        break;
      case "minor":
        versionElement.classList.add("Red");
        break;
      case "major":
        versionElement.classList.add("Red");
        break;
      default:
        versionElement.classList.add("Green");
    }
  } catch (e) {
    versionElement.textContent = "Version info unavailable";
    versionElement.classList.remove("Green", "Yellow", "Red");
    console.error("Failed to load version info:", e);
  }

  // Next Restart
  const sr = await fetchJSON("/api/next_restart");
  const srel = document.getElementById("scheduledRestart");

  if (sr?.data?.next_restart) {
    const next = new Date(sr.data.next_restart);
    const now = new Date();
    const timeDiff = next.getTime() - now.getTime(); // Difference in milliseconds
    const hoursDiff = timeDiff / (1000 * 60 * 60); // Convert to hours

    srel.textContent = formatter.format(next).replace(/, /g, " ");
    srel.classList.remove("Yellow", "Green", "Red");

    // Add appropriate class based on time difference
    if (hoursDiff <= 1) {
      srel.classList.add("Yellow"); // Within 1 hour
    }

    srel.parentElement.removeAttribute("hidden");
  } else {
    srel.parentElement.setAttribute("hidden", "");
  }
  // intervals
  const hi = await fetchJSON("/api/health_interval");
  if (hi?.data) {
    const minutes = Math.round(hi.data.health_interval_sec / 60);
    document.getElementById("healthInterval").textContent = `${minutes} min`;
  }
  const li = await fetchJSON("/api/log_interval");
  if (li?.data) {
    document.getElementById(
      "logInterval"
    ).textContent = `${li.data.log_interval_min} min`;
  }
}

// -----------------------------------------------------------------------------
// Main function - loads data based on active tab
// -----------------------------------------------------------------------------
export async function loadInfo() {
  if (activeTab === "status") {
    await loadStatus();
  } else if (activeTab === "info") {
    await loadInfoData();
  }
}
// Set the active tab (call this when tabs are switched)
export function setActiveTab(tab) {
  activeTab = tab;
  // Immediately load data for the new active tab
  if (activeTab === "status") {
    loadInfo();
  }
}
