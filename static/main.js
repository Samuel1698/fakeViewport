import { initLogs } from "./_logs.js";
import { loadInfo } from "./_info.js";
import { checkForUpdate, CACHE_TTL, initUpdateButton } from "./_update.js";
import { control } from "./_control.js";
import { initSections } from "./_sections.js";

document.addEventListener("DOMContentLoaded", () => {
  // Initialize all components
  loadInfo();
  checkForUpdate();
  initUpdateButton();
  initLogs();
  initSections();

  // Set up intervals
  setInterval(loadInfo, 60_000);
  setInterval(checkForUpdate, CACHE_TTL);

  // Add event listeners for control buttons
  document.querySelectorAll("#controls button").forEach((btn) => {
    btn.addEventListener("click", () => {
      control(btn.dataset.action, btn);
    });
  });
});
