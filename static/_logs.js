import { fetchJSON } from "./_device.js";

// Store the last used limit value
let logRefreshInterval;
let lastLogControlsInteraction = 0;
let lastLogLimit = 50;
const MAX_AUTO_SCROLL_LOGS = 100;
const INTERACTION_PAUSE_MS = 2_500; 

// Helper function for logs
export function startLogsAutoRefresh(interval=5_000) {
  if (logRefreshInterval) return; // already running

  logRefreshInterval = setInterval(() => {
    if (shouldRefreshLogs()) fetchAndDisplayLogs(lastLogLimit);
  }, interval);
}
export function stopLogsAutoRefresh() {
  clearInterval(logRefreshInterval);
  logRefreshInterval = null;
}
function togglePauseIndicator(paused) {
  const badge = document.getElementById("logsPaused");
  if (!badge) return;
  badge.hidden = !paused;
}
function shouldRefreshLogs() {
  const logsSection = document.getElementById("logs");
  const logOutput = document.getElementById("logOutput");
  const visible = !!logsSection && !logsSection.hasAttribute("hidden");

  const atBottom =
    logOutput.scrollHeight - logOutput.scrollTop - logOutput.clientHeight < 40;

  const interactedRecently =
    Date.now() - lastLogControlsInteraction < INTERACTION_PAUSE_MS;

  // Show ⏸ badge whenever *either* condition blocks auto-refresh
  togglePauseIndicator(!atBottom || interactedRecently);

  return visible && atBottom && !interactedRecently;
}

export function colorLogEntry(logText, element) {
  const entry = element || document.createElement("div");
  let displayText = logText.trim();
  entry.classList.remove("Green", "Blue", "Yellow", "Red");

  // Convert log text to lowercase once for all comparisons
  const lowerLogText = displayText.toLowerCase();
  if (
    // Success
    lowerLogText.includes("healthy") ||
    lowerLogText.includes("resumed") ||
    lowerLogText.includes("reloaded") ||
    lowerLogText.includes("fullscreen activated") ||
    lowerLogText.includes("saved") ||
    lowerLogText.includes("gracefully shutting down") ||
    lowerLogText.includes("already running") ||
    lowerLogText.includes("successfully updated") ||
    lowerLogText.includes("no errors found") ||
    lowerLogText.includes("started")
  ) {
    entry.classList.add("Green");
  } else if (
    // Actions that raise an eyebrow
    lowerLogText.includes("[warning]") ||
    lowerLogText.includes("=====") ||
    lowerLogText.includes("chromedriver ") ||
    lowerLogText.includes("geckodriver ") ||
    lowerLogText.includes("response is 200") ||
    lowerLogText.includes("WebDriver version") ||
    lowerLogText.includes("download new driver") ||
    lowerLogText.includes("version") ||
    lowerLogText.includes("getting latest") ||
    lowerLogText.includes("^^") ||
    lowerLogText.includes("get ")
  ) {
    entry.classList.add("Yellow");
  } else if (
    // Normal actions
    lowerLogText.includes("[info]")
  ) {
    entry.classList.add("Blue");
  } else {
    // Errors and exceptions
    entry.classList.add("Red");
  }
  // If an existing element was passed, trim timestamp and log level
  if (element) {
    // Match timestamp followed by log level (e.g., "2023-01-01 12:00:00 [INFO] ")
    const prefixMatch = displayText.match(/^.*?\[(INFO|ERROR|WARNING|DEBUG)\]\s*/);
    if (prefixMatch) {
      displayText = displayText.substring(prefixMatch[0].length);
    }
  }
  entry.textContent = displayText;
  return entry;
}
// Main logs functionality
export async function fetchAndDisplayLogs(limit, scroll=true) {
  const logCountSpan = document.getElementById("logCount");
  const logLimitInput = document.getElementById("logLimit");
  const logOutput = document.getElementById("logOutput");

  // Use provided limit, last used limit, or default 50
  const newLimit = limit !== undefined ? limit : lastLogLimit;

  // Sanitize the input
  const sanitizedLimit = Math.max(10, Math.min(1000, parseInt(newLimit) || 50));

  // Update the stored value
  lastLogLimit = sanitizedLimit;

  // Update the input and display
  logLimitInput.value = sanitizedLimit;
  logCountSpan.textContent = sanitizedLimit;

  const res = await fetchJSON(`/api/logs?limit=${sanitizedLimit}`);
  if (res?.data?.logs) {
    // Clear the log output container
    logOutput.innerHTML = "";

    // Convert the log array to individual div elements
    res.data.logs.forEach((logText) => {
      const logEntry = colorLogEntry(logText);
      logEntry.classList.add("log-entry");
      logOutput.appendChild(logEntry);
    });
  }
  // Auto-scroll to bottom if logs are below threshold
  if (scroll && (logOutput.children.length <= MAX_AUTO_SCROLL_LOGS)) {
    logOutput.scrollTop = logOutput.scrollHeight;
  }
}

// Initialize logs functionality
export function initLogs() {
  const searchLogsButton = document.getElementById("searchLogs");
  const logLimitInput = document.getElementById("logLimit");
  const logControls = document.querySelector(".log-controls");

  // Set up event listeners
  document.querySelectorAll(".custom-spinner-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const step = parseInt(logLimitInput.step) || 10;
      let currentValue = parseInt(logLimitInput.value) || lastLogLimit;

      if (btn.dataset.action === "increment") {
        currentValue = Math.min(1000, currentValue + step);
      } else {
        currentValue = Math.max(10, currentValue - step);
      }

      logLimitInput.value = currentValue;
      logLimitInput.dispatchEvent(new Event("input"));
    });
  });

  searchLogsButton.addEventListener("click", async () => {
    await fetchAndDisplayLogs(logLimitInput.value);
  });

  logLimitInput.addEventListener("keypress", async (e) => {
    if (e.key === "Enter") {
      await fetchAndDisplayLogs(logLimitInput.value);
    }
  });

  logLimitInput.addEventListener("blur", () => {
    let value = parseInt(logLimitInput.value) || lastLogLimit;
    value = Math.max(10, Math.min(1000, value));
    logLimitInput.value = value;
    document.getElementById("logCount").textContent = value;
    lastLogLimit = value; // Update stored value
  });

  logLimitInput.addEventListener("input", () => {
    let value = parseInt(logLimitInput.value) || lastLogLimit;
    document.getElementById("logCount").textContent = Math.min(1000, value);
  });

  if (logControls) {
    // Any keypress, mouse click, or touch counts as “interaction”
    ['input','keydown','mousedown','touchstart'].forEach(evt =>
      logControls.addEventListener(evt, () => {
        lastLogControlsInteraction = Date.now();     // reset the timer
        togglePauseIndicator(true);                  // show ⏸ immediately
      })
    );
  }
  // Pause on scroll
    document.getElementById("logOutput").addEventListener("scroll", () =>
        togglePauseIndicator(!shouldRefreshLogs())
    );
  // Add expand button functionality
  const expandButton = document.getElementById("expandLogs");
  const logsSection = document.getElementById("logs");

  if (expandButton && logsSection) {
    expandButton.addEventListener("click", () => {
      logsSection.classList.toggle("expanded");

      // Update aria-expanded attribute for accessibility
      const isExpanded = logsSection.classList.contains("expanded");
      expandButton.setAttribute("aria-expanded", isExpanded);

      // Update button label
      expandButton.setAttribute(
        "aria-label",
        isExpanded ? "Collapse logs" : "Expand logs"
      );
      expandButton.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          expandButton.click();
        }
      });
    });
  }
  // Initial load with stored value
  fetchAndDisplayLogs(lastLogLimit);
}