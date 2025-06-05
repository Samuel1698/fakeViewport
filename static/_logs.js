import { fetchJSON } from "./_device.js";

// Store the last used limit value
let lastLogLimit = 10;

export function colorLogEntry(logText, element) {
  const entry = element || document.createElement("div");
  let displayText = logText.trim();
  entry.classList.remove("Green", "Blue", "Yellow", "Red");

  // Convert log text to lowercase once for all comparisons
  const lowerLogText = displayText.toLowerCase();
  if (
    lowerLogText.includes("healthy") ||
    lowerLogText.includes("resumed") ||
    lowerLogText.includes("restart") ||
    lowerLogText.includes("fullscreen") ||
    lowerLogText.includes("saved") ||
    lowerLogText.includes("gracefully shutting down") ||
    lowerLogText.includes("already running") ||
    lowerLogText.includes("no errors found") ||
    lowerLogText.includes("started")
  ) {
    entry.classList.add("Green");
  }
  if (
    lowerLogText.includes("stopped") ||
    lowerLogText.includes("stopping") ||
    lowerLogText.includes("killed") ||
    lowerLogText.includes("attempting") ||
    lowerLogText.includes("restarting") ||
    lowerLogText.includes("loaded") ||
    lowerLogText.includes("crashed") ||
    lowerLogText.includes("retrying") ||
    lowerLogText.includes("checking") ||
    lowerLogText.includes("log-in") ||
    lowerLogText.includes("killing existing") ||
    lowerLogText.includes("starting")
  ) {
    entry.classList.remove("Green");
    entry.classList.add("Blue");
  }
  if (
    lowerLogText.includes("=====") ||
    lowerLogText.includes("driver") ||
    lowerLogText.includes("deleted") ||
    lowerLogText.includes("^^") ||
    lowerLogText.includes("get ")
  ) {
    entry.classList.remove("Green", "Blue");
    entry.classList.add("Yellow");
  }
  if (
    lowerLogText.includes("error") ||
    lowerLogText.includes("stuck") ||
    lowerLogText.includes("unsupported") ||
    lowerLogText.includes("timed") ||
    lowerLogText.includes("issue") ||
    lowerLogText.includes("couldn't") ||
    lowerLogText.includes("paused") ||
    lowerLogText.includes("offline") ||
    lowerLogText.includes("unresponsive") ||
    lowerLogText.includes("[error]") ||
    lowerLogText.includes(", line") ||
    lowerLogText.includes("exception") ||
    lowerLogText.includes("traceback") ||
    lowerLogText.includes("webdriver.") ||
    lowerLogText.includes("not found")
  ) {
    entry.classList.remove("Green", "Blue", "Yellow");
    entry.classList.add("Red");
  }
  if (!entry.classList.contains("Green", "Blue", "Yellow")){
    entry.classList.add("Red");
  }
  // If an existing element was passed, trim timestamp and log level
  if (element) {
    // Match timestamp followed by log level (e.g., "2023-01-01 12:00:00 [INFO] ")
    const prefixMatch = displayText.match(/^.*?\[(INFO|ERROR|WARN|DEBUG)\]\s*/);
    if (prefixMatch) {
      displayText = displayText.substring(prefixMatch[0].length);
    }
  }
  entry.textContent = displayText;
  return entry;
}
// Main logs functionality
export async function fetchAndDisplayLogs(limit) {
  const logCountSpan = document.getElementById("logCount");
  const logLimitInput = document.getElementById("logLimit");
  const logOutput = document.getElementById("logOutput");

  // Use provided limit, last used limit, or default 10
  const newLimit = limit !== undefined ? limit : lastLogLimit;

  // Sanitize the input
  const sanitizedLimit = Math.max(10, Math.min(1000, parseInt(newLimit) || 10));

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
}

// Initialize logs functionality
export function initLogs() {
  const searchLogsButton = document.getElementById("searchLogs");
  const logLimitInput = document.getElementById("logLimit");

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