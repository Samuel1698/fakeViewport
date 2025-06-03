// Export these if needed elsewhere
export const sections = {
  status: document.getElementById("status"),
  info: document.getElementById("info"),
  config: document.getElementById("config"),
  logs: document.getElementById("logs"),
  updateBanner: document.getElementById("update"),
};

export const buttons = {
  status: document.getElementById("statusBtn"),
  info: document.getElementById("infoBtn"),
  config: document.getElementById("configBtn"),
  logs: document.getElementById("logsBtn"),
  updateBanner: document.getElementById("updateBtn"),
  refreshButton: document.getElementById("refreshButton"),
  logInput: document.querySelector("#navigation .log-controls"),
};

// Import dependencies (adjust paths as needed)
import { fetchAndDisplayLogs } from "./_logs.js";
import { loadInfo, setActiveTab } from "./_info.js"; // Add setActiveTab import
import { showChangelog } from "./_update.js";

export function toggleSection(buttonId) {
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

  // Hide refresh button unless "status" or "info" or "config"
  if (buttonId === "status" || buttonId === "info" || buttonId === "config") {
    buttons.refreshButton.removeAttribute("hidden");
  } else {
    buttons.refreshButton.setAttribute("hidden", "true");
  }
  // Hide the log input button
  if (buttonId === "logs") {
    buttons.logInput.removeAttribute("hidden");
  } else {
    buttons.logInput.setAttribute("hidden", "true");
  }
}

// Initialize section functionality
export function initSections() {
  // Initial state
  sections.status.removeAttribute("hidden");
  sections.info.setAttribute("hidden", "");
  sections.logs.setAttribute("hidden", "");
  sections.updateBanner.setAttribute("hidden", "");

  // Set initial aria-selected
  buttons.status.setAttribute("aria-selected", "true");
  buttons.info.removeAttribute("aria-selected");
  buttons.logs.removeAttribute("aria-selected");
  buttons.updateBanner.removeAttribute("aria-selected");

  // Show refresh button initially since status is default
  buttons.refreshButton.removeAttribute("hidden");

  // Add click handlers
  buttons.status.addEventListener("click", () => {
    toggleSection("status");
    setActiveTab("status");
  });
  buttons.info.addEventListener("click", () => {
    toggleSection("info");
    setActiveTab("info");
  });
  buttons.config.addEventListener("click", () => {
    toggleSection("config");
    setActiveTab("config");
  });
  buttons.logs.addEventListener("click", async () => {
    toggleSection("logs");
    await fetchAndDisplayLogs();
  });

  buttons.updateBanner.addEventListener("click", () => {
    toggleSection("updateBanner");
    showChangelog();
  });

  buttons.refreshButton.addEventListener("click", () => {
    loadInfo({ forceRefreshConfig: true });
    buttons.refreshButton.classList.add("refreshing");
    setTimeout(() => {
      buttons.refreshButton.classList.remove("refreshing");
    }, 1000);
  });
}
