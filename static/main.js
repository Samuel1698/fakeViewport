import { initLogs } from "./_logs.js";
import { loadInfo, loadStatus, loadInfoData, setActiveTab } from "./_info.js";
import { checkForUpdate, CACHE_TTL, initUpdateButton } from "./_update.js";
import { control } from "./_control.js";
import { initSections } from "./_sections.js";

// Track refresh intervals so we can clear them
let statusRefreshInterval;
let infoRefreshInterval;
let configRefreshInterval;

document.addEventListener("DOMContentLoaded", async () => {
  // Initialize all components
  setActiveTab("status"); // Set initial tab to status
  // Load data for both tabs on initial load
  await Promise.all([loadStatus(), loadInfoData()]);

  checkForUpdate();
  initUpdateButton();
  initLogs();
  initSections();
  initTooltips();
  
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

  configRefreshInterval = setInterval(() => {
    if (document.getElementById("config").hasAttribute("hidden") === false) {
      loadInfo(); // Will only refresh config data
    }
  }, CACHE_TTL);
  
  setInterval(checkForUpdate, CACHE_TTL);

  const controls = document.querySelector(".controls");
  const parentTooltip = controls.parentElement;
  const buttons = controls.querySelectorAll("button");
  const COOLDOWN_TIME = 15_000; 

  // Store the original tooltip for restoration
  const originalTooltip = controls.getAttribute("data-tooltip");

  buttons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      // Disable all buttons and add visual feedback
      buttons.forEach((b) => {
        b.setAttribute("disabled", "");
        b.classList.add("processing");
      });
      // Update tooltip to show action is processing
      controls.setAttribute("data-tooltip", "Processing command...");
      parentTooltip.classList.add("show");
      try {
        await control(btn.dataset.action, btn);
      } catch (error) {
        console.error("Control action failed:", error);
        // Update tooltip to show error
        controls.setAttribute(
          "data-tooltip",
          "Action failed. " + (error.message || "")
        );
      } finally {
        // Re-enable buttons after cooldown
        setTimeout(() => {
          buttons.forEach((b) => {
            b.removeAttribute("disabled");
            b.classList.remove("processing");
          });
          parentTooltip.classList.remove("show");
          // Restore original tooltip
          controls.setAttribute("data-tooltip", originalTooltip);
        }, COOLDOWN_TIME);
      }
    });
  });

  function initTooltips() {
    // Find all elements with data-tooltip attribute
    const tooltipElements = document.querySelectorAll("[data-tooltip]");

    tooltipElements.forEach((element) => {
      // Create tooltip element
      const tooltip = document.createElement("span");
      tooltip.className = "tooltip-text";
      tooltip.textContent = element.getAttribute("data-tooltip");

      // Wrap the original content in a tooltip container
      const wrapper = document.createElement("span");
      wrapper.className = "tooltip";

      // Replace original element with wrapper
      element.parentNode.insertBefore(wrapper, element);
      wrapper.appendChild(element);
      wrapper.appendChild(tooltip);

      // Position adjustment for edge cases
      const updatePosition = () => {
        const rect = wrapper.getBoundingClientRect();
        if (rect.left < 100) {
          tooltip.style.left = "0";
          tooltip.style.transform = "none";
          tooltip.style.marginLeft = "10px";
        } else if (rect.right > window.innerWidth - 100) {
          tooltip.style.left = "auto";
          tooltip.style.right = "0";
          tooltip.style.transform = "none";
          tooltip.style.marginRight = "10px";
        }
      };

      // Set up event listeners
      wrapper.addEventListener("mouseenter", updatePosition);
      window.addEventListener("resize", updatePosition);
    });
  }
});
