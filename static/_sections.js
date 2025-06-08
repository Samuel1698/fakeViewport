// Export these if needed elsewhere
export const sections = {
  status: document.getElementById("status"),
  device: document.getElementById("device"),
  config: document.getElementById("config"),
  logs: document.getElementById("logs"),
  updateBanner: document.getElementById("update"),
};

export const buttons = {
  status: document.getElementById("statusBtn"),
  device: document.getElementById("deviceBtn"),
  config: document.getElementById("configBtn"),
  logs: document.getElementById("logsBtn"),
  updateBanner: document.getElementById("updateBtn"),
  refreshButton: document.getElementById("refreshButton"),
  logInput: document.querySelector("#navigation .log-controls"),
};

export const controls = document.getElementById("controls");
const groupDiv = document.querySelector(".group");

import { fetchAndDisplayLogs } from "./_logs.js";
import { activeTab, loadInfo, setActiveTab } from "./_device.js";
import { showChangelog } from "./_update.js";
import { scheduleRefresh } from "./_autoRefresh.js";

// Check if screen is in "desktop" mode (combined status/device/logs view)
export function isDesktopView() {
  return window.matchMedia("(min-width: 58.75rem)").matches;
}

// Handle responsive changes
function handleResponsiveChange() {
  const currentSection = Object.entries(buttons).find(
    ([_, btn]) => btn.getAttribute("aria-selected") === "true"
  )?.[0];

  if (isDesktopView()) {
    // Desktop view logic
    if (currentSection === "config" || currentSection === "updateBanner") {
      // Hide group div when config/update is selected in desktop view
      groupDiv.setAttribute("hidden", "true");
    } else {
      // On first load:
      // Show group div and ensure status is selected with all relevant elements visible
      groupDiv.removeAttribute("hidden");
      // Force toggle status so that the scheduledRefresh can start for all relevant sections
      toggleSection("status");
      // Ensure device and logs sections are visible in desktop view
      sections.device.removeAttribute("hidden");
      sections.logs.removeAttribute("hidden");
      buttons.logInput.removeAttribute("hidden");
    }
  } else {
    // Mobile view logic
    groupDiv.removeAttribute("hidden");
    
    // Only auto-select status if we're coming from desktop view with status selected
    // and not if config/update was selected
    if (currentSection === "status") {
      toggleSection("status");
    }
  }
}

// Initialize media query listener
function initResponsiveListener() {
  const mediaQuery = window.matchMedia("(min-width: 58.75rem)");
  mediaQuery.addEventListener("change", handleResponsiveChange);
  handleResponsiveChange(); // Run once on init
}

export function toggleSection(buttonId) {
  // Handle responsive behavior - if desktop view and trying to select a merged section,
  // ensure status is selected instead
  if (isDesktopView() && (buttonId === "device" || buttonId === "logs")) {
    buttonId = "status";
  }

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

  // Hide refresh button unless "status" or "device" or "config"
  if (buttonId === "status" || buttonId === "device" || buttonId === "config") {
    buttons.refreshButton.removeAttribute("hidden");
  } else {
    buttons.refreshButton.setAttribute("hidden", "true");
  }

  // Hide the control buttons
  if (!(buttonId === "status" || buttonId === "device")) {
    controls.setAttribute("hidden", "true");
  } else {
    controls.removeAttribute("hidden");
  }

  // Hide the log input button
  if (buttonId === "logs") {
    buttons.logInput.removeAttribute("hidden");
  } else {
    buttons.logInput.setAttribute("hidden", "true");
  }

  // Handle group div visibility for desktop view
  if (isDesktopView()) {
    if (buttonId === "config" || buttonId === "updateBanner") {
      groupDiv.setAttribute("hidden", "true");
    } else {
      // On button clicks
      groupDiv.removeAttribute("hidden");
      sections.status.removeAttribute("hidden");
      sections.device.removeAttribute("hidden");
      sections.logs.removeAttribute("hidden");
      buttons.logInput.removeAttribute("hidden");
    }
  } else {
    groupDiv.removeAttribute("hidden");
  }
  const refreshKey = isDesktopView()
      ? (["status","device","logs"].includes(buttonId) ? "desktop" : buttonId)
      : buttonId;
  scheduleRefresh(refreshKey, { immediate: false });
}

// Initialize section functionality
export function initSections() {
  // Initial state
  sections.status.removeAttribute("hidden");
  sections.device.setAttribute("hidden", "");
  sections.logs.setAttribute("hidden", "");
  sections.updateBanner.setAttribute("hidden", "");

  // Set initial aria-selected
  buttons.status.setAttribute("aria-selected", "true");
  buttons.device.setAttribute("aria-selected", "false");
  buttons.logs.setAttribute("aria-selected", "false");
  buttons.updateBanner.setAttribute("aria-selected", "false");

  // Show refresh button initially since status is default
  buttons.refreshButton.removeAttribute("hidden");

  // Add click handlers
  buttons.status.addEventListener("click", () => {
    toggleSection("status");
    setActiveTab("status");
  });
  buttons.device.addEventListener("click", () => {
    toggleSection(isDesktopView() ? "status" : "device");
    setActiveTab("device");
  });
  buttons.config.addEventListener("click", () => {
    toggleSection("config");
    setActiveTab("config");
  });
  buttons.logs.addEventListener("click", async () => {
    toggleSection(isDesktopView() ? "status" : "logs");
    await fetchAndDisplayLogs();
  });

  buttons.updateBanner.addEventListener("click", () => {
    toggleSection("updateBanner");
    showChangelog();
  });

  buttons.refreshButton.addEventListener("click", () => {
    loadInfo({ forceRefreshConfig: true });
    if (isDesktopView() && activeTab === "status") fetchAndDisplayLogs(); 
    buttons.refreshButton.classList.add("refreshing");
    setTimeout(() => {
      buttons.refreshButton.classList.remove("refreshing");
    }, 1000);
  });

  // Initialize responsive behavior
  initResponsiveListener();
}
