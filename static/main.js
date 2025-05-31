let updateCache = {
  timestamp: 0,
  data: null,    // { current, latest, changelog, releaseUrl }
};
let lastScriptUptime = null;
let lastLogLimit = 50; 
const CACHE_TTL = 60 * 15 * 1000; // 15 minutes
document.addEventListener("DOMContentLoaded", () => {
  loadInfo();
  checkForUpdate();
  setInterval(loadInfo, 60_000);
  setInterval(checkForUpdate, CACHE_TTL);
});
document.addEventListener("DOMContentLoaded", () => {
  // Initialize sections and buttons
  const sections = {
    status: document.getElementById("info"),
    logs: document.getElementById("logs"),
    updateBanner: document.getElementById("changelog"),
  };
  const buttons = {
    status: document.getElementById("status"),
    logs: document.getElementById("logsBtn"),
    updateBanner: document.getElementById("update"),
    refreshButton: document.getElementById("refreshButton"),
  };
  // Declare log variables
  const logCountSpan = document.getElementById('logCount');
  const logLimitInput = document.getElementById('logLimit');
  const searchLogsButton = document.getElementById('searchLogs');
  const logOutput = document.getElementById('logOutput');
  // Set initial state
  sections.status.removeAttribute("hidden");
  sections.logs.setAttribute("hidden", "");
  sections.updateBanner.setAttribute("hidden", "");

  // Set initial aria-selected
  buttons.status.setAttribute("aria-selected", "true");
  buttons.logs.removeAttribute("aria-selected", "false");
  buttons.updateBanner.removeAttribute("aria-selected", "false");

  // Add click handlers for all buttons
  buttons.status.addEventListener("click", () => {
    toggleSection("status");
    buttons.refreshButton.removeAttribute("hidden", "");
  });

  // LOGS
  async function fetchAndDisplayLogs(limit = lastLogLimit) {
    // Sanitize the input - ensure it's a number between 10-600
    limit = Math.max(10, Math.min(600, parseInt(limit) || lastLogLimit));

    // Store the valid limit for future use
    lastLogLimit = limit;

    // Update the input and display to match the sanitized value
    logLimitInput.value = limit;
    logCountSpan.textContent = limit;

    const res = await fetchJSON(`/api/logs?limit=${limit}`);
    if (res?.data?.logs) {
      logOutput.textContent = res.data.logs.join("");
    }
  }
  document.querySelectorAll(".custom-spinner-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = document.getElementById("logLimit");
      const step = parseInt(input.step) || 10;
      let currentValue = parseInt(input.value) || lastLogLimit;

      if (btn.dataset.action === "increment") {
        currentValue = Math.min(600, currentValue + step);
      } else {
        currentValue = Math.max(10, currentValue - step);
      }

      input.value = currentValue;
      // Trigger the input event to update the display
      input.dispatchEvent(new Event("input"));
    });
  });
  buttons.logs.addEventListener("click", async () => {
    toggleSection("logs");
    await fetchAndDisplayLogs(lastLogLimit); // Use stored value instead of default
  });
  // Search button click handler
  searchLogsButton.addEventListener("click", async () => {
    await fetchAndDisplayLogs(logLimitInput.value);
  });

  // Also allow Enter key in the input field
  logLimitInput.addEventListener("keypress", async (e) => {
    if (e.key === "Enter") {
      await fetchAndDisplayLogs(logLimitInput.value);
    }
  });
  logLimitInput.addEventListener("blur", () => {
    let value = parseInt(logLimitInput.value) || lastLogLimit;
    value = Math.max(10, Math.min(600, value));
    logLimitInput.value = value;
    logCountSpan.textContent = value;
    lastLogLimit = value;
  });
  logLimitInput.addEventListener("input", () => {
    let value = parseInt(logLimitInput.value) || lastLogLimit;
    // Don't show values above 600 even if typed
    logCountSpan.textContent = Math.min(600, value);
  });
  // Wire up the update button
  pushUpdate = sections.updateBanner.querySelector('button[type="submit"]');
  pushUpdate.addEventListener("click", () => applyUpdate(pushUpdate));

  buttons.updateBanner.addEventListener("click", () => {
    toggleSection("updateBanner");
    showChangelog();
  });
  buttons.refreshButton.addEventListener("click", () => {
    toggleSection("status");
    loadInfo();
    buttons.refreshButton.classList.add("refreshing");

    // Remove the class after animation completes (1000ms in this case)
    setTimeout(() => {
      buttons.refreshButton.classList.remove("refreshing");
    }, 1000);
  });
  function toggleSection(buttonId) {
    // Hide all sections first
    Object.values(sections).forEach((section) => {
      section.setAttribute("hidden", "");
    });

    // Show the selected section
    sections[buttonId].removeAttribute("hidden");

    // Update aria-selected for all buttons
    Object.entries(buttons).forEach(([id, button]) => {
      button.setAttribute("aria-selected", id === buttonId ? "true" : "false");
    });

    // Hide refresh button unless "status"
    if (buttonId != "status") {
      buttons.refreshButton.setAttribute("hidden", "true");
    }
  }
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

    const banner = document.getElementById("update");
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

  const title =  document.querySelector('#changelog .container h2');
  if (latest.includes("failed-to-fetch")) {
    title.textContent = "Failed to Fetch Changelog";
  } else {
    title.textContent = `Release v${latest}`;
  }

  document.getElementById('changelog-body').innerHTML =
    marked.parse(changelog);

  document.getElementById('changelog-link').href = releaseUrl;
  document.getElementById('changelog')
    .removeAttribute('hidden');
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
// send control and update inline message
async function control(action, btn) {
  // disable the button immediately
  btn.setAttribute("disabled", "");
  setTimeout(() => {
    btn.removeAttribute("disabled");
  }, 5_000);

  const msgEl = document.querySelector("#statusMessage span");
  msgEl.textContent = "";
  msgEl.classList.remove("Green", "Red");
  try {
    const res = await fetch(`/api/control/${action}`, { method: "POST" });
    const js = await res.json();

    if (js.status === "ok") {
      msgEl.textContent = "✓ " + js.message;
      msgEl.classList.add("Green");
    } else {
      msgEl.textContent = "✗ " + js.message;
      msgEl.classList.add("Red");
    }
    await loadInfo();
    // reset the message after 15 seconds
    setTimeout(() => {
      msgEl.textContent = "";
      msgEl.classList.remove("Green", "Red");
    }, 5_000);
    setTimeout(loadInfo, 5_000);
  } catch (e) {
    msgEl.textContent = "✗ " + e;
    msgEl.classList.add("Red");
  }
}
// send update
async function applyUpdate(btn) {
  const updateMessage = document.querySelector("#updateMessage span");
  const originalBtnText = btn.querySelector("span").textContent;
  const originalBtnDisabled = btn.disabled;

  // Reset message state
  updateMessage.textContent = "";
  updateMessage.className = "";
  btn.disabled = true;
  updateMessage.textContent = "Fetching Update...";
  updateMessage.classList.add("Green"); 
  try {
    // First API call - apply update
    const updateResponse = await fetch("/update/apply", { method: "POST" });

    if (!updateResponse.ok) {
      throw new Error(`Update failed with status ${updateResponse.status}`);
    }

    const updateData = await updateResponse.json();
    const outcome = updateData?.data?.outcome || updateData?.outcome;

    // Handle different outcome cases
    if (outcome === "already-current") {
      updateMessage.textContent = "✓ Your system is already up to date";
      updateMessage.classList.remove("Red");
      updateMessage.classList.add("Green");
      btn.querySelector("span").textContent = "Up to date";
      setTimeout(() => {
        btn.querySelector("span").textContent = originalBtnText;
        btn.disabled = originalBtnDisabled;
        updateMessage.textContent = "";
        updateMessage.className = "";
      }, 10_000);
      return;
    }

    // Handle successful updates
    if (outcome.startsWith("updated-to-")) {
      updateMessage.textContent =
        "✓ Update successful, preparing to restart...";
      updateMessage.classList.remove("Red");
      updateMessage.classList.add("Green");

      // Start restart sequence
      try {
        const [restartResponse, selfRestartResponse] = await Promise.all([
          fetch(`/api/control/restart`, { method: "POST" }),
          fetch(`/api/self/restart`, { method: "POST" }),
        ]);

        if (!restartResponse.ok || !selfRestartResponse.ok) {
          throw new Error("Restart commands failed");
        }

        const [restartData, selfRestartData] = await Promise.all([
          restartResponse.json(),
          selfRestartResponse.json(),
        ]);

        if (restartData.status === "ok" && selfRestartData.status === "ok") {
          updateMessage.textContent = "✓ System restarting...";
          setTimeout(() => location.reload(), 5000);
        } else {
          updateMessage.textContent =
            "✓ Update complete - please restart manually";
          btn.querySelector("span").textContent = "Restart required";
        }
      } catch (restartError) {
        updateMessage.textContent =
          "✓ Update complete - automatic restart failed";
        btn.querySelector("span").textContent = "Restart required";
        console.error("Restart failed:", restartError);
      }
    }
    // Handle failure case
    else if (outcome === "update-failed") {
      throw new Error("Update process failed");
    }
    // Unknown response
    else {
      throw new Error("Unexpected update response");
    }
  } catch (error) {
    console.error("Update failed:", error);
    updateMessage.classList.remove("Green");
    updateMessage.classList.add("Red");

    // More specific error messages
    if (error.message.includes("Failed to fetch")) {
      updateMessage.textContent =
        "✗ Network error - please check your connection";
    } else if (error.message.includes("Update process failed")) {
      updateMessage.textContent = "✗ Update failed - please try again";
    } else {
      updateMessage.textContent = "✗ Update error - please check logs";
    }

    // Revert button state
    btn.querySelector("span").textContent = "Retry";
    btn.disabled = false;
  }
}