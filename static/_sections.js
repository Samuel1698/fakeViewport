// Export these if needed elsewhere
export const sections = {
  status: document.getElementById("info"),
  logs: document.getElementById("logs"),
  updateBanner: document.getElementById("changelog"),
};

export const buttons = {
  status: document.getElementById("status"),
  logs: document.getElementById("logsBtn"),
  updateBanner: document.getElementById("update"),
  refreshButton: document.getElementById("refreshButton"),
};

// Import dependencies (adjust paths as needed)
import { fetchAndDisplayLogs } from "./_logs.js";
import { loadInfo } from "./_info.js";
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

  // Hide refresh button unless "status"
  if (buttonId !== "status") {
    buttons.refreshButton.setAttribute("hidden", "true");
  }
}

// Initialize section functionality
export function initSections() {
  // Initial state
  sections.status.removeAttribute("hidden");
  sections.logs.setAttribute("hidden", "");
  sections.updateBanner.setAttribute("hidden", "");

  // Set initial aria-selected
  buttons.status.setAttribute("aria-selected", "true");
  buttons.logs.removeAttribute("aria-selected");
  buttons.updateBanner.removeAttribute("aria-selected");

  // Add click handlers
  buttons.status.addEventListener("click", () => {
    toggleSection("status");
    buttons.refreshButton.removeAttribute("hidden");
  });

  buttons.logs.addEventListener("click", async () => {
    toggleSection("logs");
    await fetchAndDisplayLogs(); // Let fetchAndDisplayLogs handle its own default
  });

  buttons.updateBanner.addEventListener("click", () => {
    toggleSection("updateBanner");
    showChangelog();
  });

  buttons.refreshButton.addEventListener("click", () => {
    loadInfo();
    buttons.refreshButton.classList.add("refreshing");
    setTimeout(() => {
      buttons.refreshButton.classList.remove("refreshing");
    }, 1000);
  });
}
