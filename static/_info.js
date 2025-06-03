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

// Config cache with refresh capability
let configCache = {
  data: null,
  lastUpdated: 0,
  ttl: 360_0000, // 1 hour

  async get(forceRefresh = false) {
    const now = Date.now();
    if (forceRefresh || !this.data || now - this.lastUpdated > this.ttl) {
      this.data = await fetchJSON("/api/config");
      this.lastUpdated = now;
      this.updateConfigElements();
    }
    return this.data;
  },

  updateConfigElements() {
    if (!this.data?.data) return;

    const config = this.data.data;

    // Get sleep time in minutes for comparison
    const sleepTimeMinutes = config?.general?.health_interval_sec
      ? Math.round(config.general.health_interval_sec / 60)
      : null;

    // Formatting functions with color classes
    const formatTime = {
      seconds: (value, element) => {
        const formatted = `${value} Second${value !== 1 ? "s" : ""}`;
        if (element.id === "waitTime" && value <= 5) {
          element.classList.add("Red");
        } else {
          element.classList.add("Blue");
        }
        return formatted;
      },
      minutes: (value, element) => {
        const formatted = `${value} Minute${value !== 1 ? "s" : ""}`;
        if (element.id === "healthInterval" && value <= 1) {
          element.classList.add("Red");
        } else if (
          element.id === "logInterval" &&
          sleepTimeMinutes &&
          value < sleepTimeMinutes
        ) {
          element.classList.add("Yellow");
        } else {
          element.classList.add("Blue");
        }
        return formatted;
      },
      days: (value, element) => {
        const formatted = `${value} Day${value !== 1 ? "s" : ""}`;
        if (value > 7) {
          element.classList.add("Yellow");
        } else {
          element.classList.add("Blue");
        }
        return formatted;
      },
      hours: (value, element) => {
        const formatted = `${value} Hour${value !== 1 ? "s" : ""}`;
        element.classList.add("Blue");
        return formatted;
      },
      boolean: (value, element) => {
        const formatted = value ? "Yes" : "No";
        if (element.id === "headless" && value) {
          element.classList.add("Red");
        } else if (
          (element.id === "logFile" && !value) ||
          (element.id === "logConsole" && !value) ||
          (element.id === "errorLogging" && value) ||
          (element.id === "debugLogging" && value) ||
          (element.id === "screenshots" && value)
        ) {
          element.classList.add("Yellow");
        } else {
          element.classList.add("Blue");
        }
        return formatted;
      },
    };
    // Element configuration with formatting rules
    const elementConfig = [
      // General Section
      {
        id: "healthInterval",
        path: "general.health_interval_sec",
        format: (v, el) => formatTime.minutes(Math.round(v / 60), el),
      },
      {
        id: "waitTime",
        path: "general.wait_time_sec",
        format: (v, el) => formatTime.seconds(v, el),
      },
      {
        id: "maxRetries",
        path: "general.max_retries",
        format: (v, el) => {
          el.classList.add(v < 3 ? "Red" : "Blue");
          return `${v} Attempts`;
        },
      },
      {
        id: "restartTimes",
        path: "general.restart_times",
        format: (v, el) => {
          el.classList.add("Yellow");
          return Array.isArray(v) ? v.join(", ") : "-";
        },
      },
      {
        id: "scheduledRestart",
        path: "general.next_restart",
        format: (value, element) => {
          if (!value) {
            element.parentElement?.setAttribute("hidden", "");
            return "-";
          }

          const next = new Date(value);
          const now = new Date();
          const hoursDiff = (next.getTime() - now.getTime()) / (1000 * 60 * 60);

          element.classList.remove("Yellow", "Green", "Red");
          if (hoursDiff <= 1) element.classList.add("Yellow");

          element.parentElement?.removeAttribute("hidden");
          return formatter.format(next).replace(/, /g, " ");
        },
      },
      // Browser Section
      {
        id: "profilePath",
        path: "browser.profile_path",
        format: (v, el) => {
          if (!v) {
            el.classList.remove("Green", "Red");
            return "-";
          }
          const lowerPath = v.toLowerCase();
          const isValid =
            lowerPath.includes("chrome") ||
            lowerPath.includes("chromium") ||
            lowerPath.includes("firefox");
          el.classList.add(isValid ? "Green" : "Red");
          return v;
        },
      },
      {
        id: "profileBinary",
        path: "browser.binary_path",
        format: (v, el) => {
          if (!v) {
            el.classList.remove("Green", "Red");
            return "-";
          }
          const lowerBinary = v.toLowerCase();
          const isValid =
            lowerBinary.includes("chrome") ||
            lowerBinary.includes("chromium") ||
            lowerBinary.includes("firefox");
          el.classList.add(isValid ? "Green" : "Red");
          return v;
        },
      },
      {
        id: "headless",
        path: "browser.headless",
        format: (v, el) => formatTime.boolean(v, el),
      },

      // Logging Section
      {
        id: "logFile",
        path: "logging.log_file_flag",
        format: (v, el) => formatTime.boolean(v, el),
      },
      {
        id: "logConsole",
        path: "logging.log_console_flag",
        format: (v, el) => formatTime.boolean(v, el),
      },
      {
        id: "debugLogging",
        path: "logging.debug_logging",
        format: (v, el) => formatTime.boolean(v, el),
      },
      {
        id: "errorLogging",
        path: "logging.error_logging",
        format: (v, el) => formatTime.boolean(v, el),
      },
      {
        id: "screenshots",
        path: "logging.ERROR_PRTSCR",
        format: (v, el) => formatTime.boolean(v, el),
      },
      {
        id: "logDays",
        path: "logging.log_days",
        format: (v, el) => formatTime.days(v, el),
      },
      {
        id: "logInterval",
        path: "logging.log_interval_min",
        format: (v, el) => formatTime.minutes(v, el),
      },
    ];
    // Process all elements
    elementConfig.forEach(({ id, path, format }) => {
      const element = document.getElementById(id);
      if (!element) return;

      // Reset classes first
      element.classList.remove("Blue", "Yellow", "Red");

      // Get value from config
      const value = path.split(".").reduce((obj, key) => obj?.[key], config);

      // Apply formatting or default display
      if (value !== undefined && value !== null) {
        element.textContent = format
          ? format(value, element)
          : value.toString();
      } else {
        element.textContent = "-";
        element.classList.add("Blue");
      }
    });
  },
};

// format seconds → "Dd Hh Mm Ss"
function formatDuration(sec) {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);

  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  if (s > 0) parts.push(`${s}s`);

  return parts.length > 0 ? parts.join(" ") : "0s";
}

const formatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function compareVersions(current, latest) {
  const currentParts = current.split(".").map(Number);
  const latestParts = latest.split(".").map(Number);

  if (latestParts[0] > currentParts[0]) return "major";
  if (latestParts[1] > currentParts[1]) return "minor";
  if (latestParts[2] > currentParts[2]) return "patch";
  return "current";
}
function formatSpeed(bytesPerSec) {
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(1)} B/s`;
  if (bytesPerSec < 1024*1024) return `${(bytesPerSec/1024).toFixed(1)} KB/s`;
  return `${(bytesPerSec/(1024*1024)).toFixed(1)} MB/s`;
}
// -----------------------------------------------------------------------------
// Status-related updates (frequent updates)
// -----------------------------------------------------------------------------
export async function loadStatus(forceRefreshConfig = false) {
  const [sud, st, sysInfo, le] = await Promise.all([
    fetchJSON("/api/script_uptime"),
    fetchJSON("/api/status"),
    fetchJSON("/api/system_info"),
    fetchJSON("/api/logs?limit=1"),
  ]);

  // Script uptime
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

  const entry = document.getElementById("statusMsg");
  // Status message
  if (st?.data && entry) {
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

  // System info
  if (sysInfo?.data) {
    const syuEl = document.getElementById("systemUptime");
    if (syuEl) syuEl.textContent = formatDuration(sysInfo.data.system_uptime);

    const upEl = document.getElementById("up");
    const dnEl = document.getElementById("down");
    if (upEl) {
      const network = sysInfo.data.network;
      const primary = network.primary_interface;
      const sent = formatSpeed(primary.upload);
      const recv = formatSpeed(primary.download);
      upEl.textContent = sent;
      dnEl.textContent = recv;
    }
  }

  // Log entry
  if (le?.data?.logs && le.data.logs.length > 0) {
    const entry = document.getElementById("logEntry");
    const logText = le.data.logs[0].trim();
    entry.textContent = logText;
    entry.classList.remove("Green", "Blue", "Red");

    if (logText.includes("[ERROR]")) {
      entry.classList.add("Red");
    } else if (logText.includes("[WARN]")) {
      entry.classList.add("Yellow");
    } else if (logText.includes("[DEBUG]")) {
      entry.classList.add("Blue");
    } else if (logText.includes("[INFO]")) {
      entry.classList.add("Green");
    } else {
      entry.classList.add("Green");
    }
  }

  // Get config with optional force refresh
  await configCache.get(forceRefreshConfig);
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
    console.error("Failed to load version info:", e);
  }

  // System Info
  const sysInfo = await fetchJSON("/api/system_info");
  if (sysInfo?.data) {
    const osEl = document.getElementById("osInfo");
    const hwEl = document.getElementById("hardwareInfo");
    const cpuEl = document.getElementById("cpuInfo");
    const ramEl = document.getElementById("ramInfo");
    const diskEl = document.getElementById("diskInfo");
    if (osEl) osEl.textContent = sysInfo.data.os_name;
    if (hwEl) hwEl.textContent = sysInfo.data.hardware_model;
    // Disk Usage
    if (diskEl) {
      diskEl.textContent = sysInfo.data.disk_available;
      diskEl.classList.remove("Green", "Yellow", "Red");
      if (sysInfo.data.disk_bytes < 200 * 1024 * 1024) {
        diskEl.classList.add("Red");
      } else if (sysInfo.data.disk_bytes < 1024 * 1024 * 1024) {
        diskEl.classList.add("Yellow");
      } else {
        diskEl.classList.add("Green");
      }
    }
    // CPU
    if (cpuEl) {
      const cpuPct = sysInfo.data.cpu.percent;
      cpuEl.textContent = `${cpuPct}%`;
      cpuEl.classList.remove("Green", "Yellow", "Red");
      if (cpuPct <= 35) {
        cpuEl.classList.add("Green");
      } else if (cpuPct <= 60) {
        cpuEl.classList.add("Yellow");
      } else {
        cpuEl.classList.add("Red");
      }
    }
    // RAM
    if (ramEl) {
      const used = (sysInfo.data.memory.used / 1024 ** 3).toFixed(1);
      const tot = (sysInfo.data.memory.total / 1024 ** 3).toFixed(1);
      const pctUsed = sysInfo.data.memory.percent;
      ramEl.textContent = `${used} GiB / ${tot} GiB`;
      ramEl.classList.remove("Green", "Yellow", "Red");
      if (pctUsed <= 35) {
        ramEl.classList.add("Green");
      } else if (pctUsed <= 60) {
        ramEl.classList.add("Yellow");
      } else {
        ramEl.classList.add("Red");
      }
    }
  }
}
// -----------------------------------------------------------------------------
// Main function - loads data based on active tab
// -----------------------------------------------------------------------------
export async function loadInfo(options = {}) {
  const { forceRefreshConfig = false } = options;
  if (activeTab === "status") {
    await loadStatus(forceRefreshConfig);
  } else if (activeTab === "info") {
    await loadInfoData();
  } else if (activeTab === "config") {
    await configCache.get(forceRefreshConfig);
  }
}

// Set the active tab (call this when tabs are switched)
export function setActiveTab(tab) {
  activeTab = tab;
  if (activeTab === "status") {
    loadInfo();
  }
}
