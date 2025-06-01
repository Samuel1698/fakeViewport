import { initLogs } from "./_logs.js";
import { loadInfo, loadStatus, loadInfoData, setActiveTab } from "./_info.js";
import { checkForUpdate, CACHE_TTL, initUpdateButton } from "./_update.js";
import { control } from "./_control.js";
import { initSections } from "./_sections.js";

// Track refresh intervals so we can clear them
let statusRefreshInterval;
let infoRefreshInterval;

document.addEventListener("DOMContentLoaded", async () => {
  // Initialize all components
  setActiveTab("status"); // Set initial tab to status
  // Load data for both tabs on initial load
  await Promise.all([loadStatus(), loadInfoData()]);

  checkForUpdate();
  initUpdateButton();
  initLogs();
  initSections();

  // Set up intervals with different refresh rates
  statusRefreshInterval = setInterval(() => {
    if (document.getElementById("status").hasAttribute("hidden") === false) {
      loadInfo(); // Will only refresh status data
    }
  }, 15_000); // 5 seconds for status tab

  infoRefreshInterval = setInterval(() => {
    if (document.getElementById("info").hasAttribute("hidden") === false) {
      loadInfo(); // Will only refresh info data
    }
  }, CACHE_TTL);

  setInterval(checkForUpdate, CACHE_TTL);

  // Add event listeners for control buttons
  document.querySelectorAll(".controls button").forEach((btn) => {
    btn.addEventListener("click", () => {
      control(btn.dataset.action, btn);
    });
  });
});
