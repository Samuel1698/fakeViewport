import { fetchJSON } from "./_info.js";

// Store the last used limit value
let lastLogLimit = 10;

// Main logs functionality
export async function fetchAndDisplayLogs(limit) {
  const logCountSpan = document.getElementById("logCount");
  const logLimitInput = document.getElementById("logLimit");
  const logOutput = document.getElementById("logOutput");

  // Use provided limit, last used limit, or default 10
  const newLimit = limit !== undefined ? limit : lastLogLimit;

  // Sanitize the input
  const sanitizedLimit = Math.max(10, Math.min(600, parseInt(newLimit) || 10));

  // Update the stored value
  lastLogLimit = sanitizedLimit;

  // Update the input and display
  logLimitInput.value = sanitizedLimit;
  logCountSpan.textContent = sanitizedLimit;

  const res = await fetchJSON(`/api/logs?limit=${sanitizedLimit}`);
  if (res?.data?.logs) {
    // Clear the log output container
    logOutput.innerHTML = "";

    // Convert the log array to individual span elements
    res.data.logs.forEach((logText) => {
      const logEntry = document.createElement("div");
      logEntry.textContent = logText;
      logEntry.classList.add("log-entry");

      // Convert log text to lowercase once for all comparisons
      const lowerLogText = logText.toLowerCase();

      if (
        lowerLogText.includes("healthy") ||
        lowerLogText.includes("resumed") ||
        lowerLogText.includes("restart") ||
        lowerLogText.includes("fullscreen") ||
        lowerLogText.includes("saved") ||
        lowerLogText.includes("already running") ||
        lowerLogText.includes("started")
      ) {
        logEntry.classList.add("Green");
      } if (
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
        lowerLogText.includes("starting")
      ) {
        logEntry.classList.remove("Green");
        logEntry.classList.add("Blue");
      } if (
        lowerLogText.includes("=====") ||
        lowerLogText.includes("driver") ||
        lowerLogText.includes("deleted") ||
        lowerLogText.includes("get ")
      ) {
        logEntry.classList.remove("Green", "Blue");
        logEntry.classList.add("Yellow");
      } if (
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
        lowerLogText.includes("traceback") ||
        lowerLogText.includes("not found")
      ) {
        logEntry.classList.remove("Green", "Blue", "Yellow");
        logEntry.classList.add("Red");
      }
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
        currentValue = Math.min(600, currentValue + step);
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
    value = Math.max(10, Math.min(600, value));
    logLimitInput.value = value;
    document.getElementById("logCount").textContent = value;
    lastLogLimit = value; // Update stored value
  });

  logLimitInput.addEventListener("input", () => {
    let value = parseInt(logLimitInput.value) || lastLogLimit;
    document.getElementById("logCount").textContent = Math.min(600, value);
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