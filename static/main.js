import { initLogs, startLogsAutoRefresh } from "./_logs.js";
import { scheduleRefresh } from "./_autoRefresh.js";
import { loadStatus, loadDeviceData, configCache } from "./_device.js";
import { checkForUpdate, CACHE_TTL, initUpdateButton } from "./_update.js";
import { control } from "./_control.js";
import { initSections, isDesktopView } from "./_sections.js";

document.addEventListener("DOMContentLoaded", async () => {
  // Light Theme toggle
  document.getElementById("themeToggle").addEventListener("click", () => {
    const html = document.documentElement;
    const currentTheme = html.getAttribute("data-theme");
    const newTheme = currentTheme === "light" ? "dark" : "light";

    html.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
  });
  // Check for saved theme preference
  if (typeof window !== "undefined") {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme) {
      document.documentElement.setAttribute("data-theme", savedTheme);
    }
  }
  function initTooltips() {
    const tooltipElements = document.querySelectorAll("[data-tooltip]");
    tooltipElements.forEach((element) => {
      if (element.parentElement?.classList.contains("tooltip")) {
        return; // already initialised
      }
      const tooltipText = element.getAttribute("data-tooltip");
      const elementClasses = element.className.split(' ').filter(c => c); // Get all classes from child element

      // Split and handle multiple | characters
      const parts = tooltipText
        .split("|")
        .map((s) => s.trim())
        .filter(Boolean);

      // Create tooltip container
      const tooltipDiv = document.createElement("div");
      tooltipDiv.className = "tooltip-text";
      tooltipDiv.setAttribute("role", "tooltip"); // Accessibility

      // Process first part (always shown in Blue)
      if (parts.length > 0) {
        const line1 = document.createElement("span");
        line1.className = "Blue";
        line1.textContent = parts[0];
        tooltipDiv.appendChild(line1);
      }

      // Process remaining parts
      for (let i = 1; i < parts.length; i++) {
        // Add line break before each additional part
        tooltipDiv.appendChild(document.createElement("br"));
        const line = document.createElement("span");
        line.textContent = parts[i];
        if (i == parts.length - 1 && parts.length > 2) {
          line.className = "Yellow";
        }
        tooltipDiv.appendChild(line);
      }

      // Handle case where there was no | character
      if (parts.length === 1) {
        tooltipDiv.querySelector(".Blue").style.display = "block";
      }

      // Create wrapper and insert into DOM
      const wrapper = document.createElement("span");
      wrapper.className = "tooltip";

      // Add all classes from the child element to the wrapper
      elementClasses.forEach(className => {
        if (className !== 'tooltip-trigger') { // Skip if it's the class we're about to add
          wrapper.classList.add(className);
        }
      });

      element.parentNode.insertBefore(wrapper, element);

      // Prepare the trigger element
      element.classList.add("tooltip-trigger");
      element.setAttribute("tabindex", "-1"); // Prevent focus outline
      element.setAttribute("aria-describedby", `tooltip-${Date.now()}`);
      tooltipDiv.id = element.getAttribute("aria-describedby");

      wrapper.appendChild(element);
      wrapper.appendChild(tooltipDiv);

      // Mobile touch handling
      element.addEventListener("touchstart", (e) => {
        e.preventDefault();
        document.querySelectorAll(".tooltip-trigger").forEach((t) => {
          if (t !== element) t.classList.remove("active");
        });
        element.classList.toggle("active");
      });
    });

    // Close tooltips when tapping elsewhere
    document.addEventListener("touchstart", (e) => {
      if (!e.target.closest(".tooltip-trigger")) {
        document.querySelectorAll(".tooltip-trigger").forEach((el) => {
          el.classList.remove("active");
        });
      }
    });
  }

  initTooltips();

  const isLoginPage =
    window.location.pathname.includes("login.html") ||
    window.location.pathname === "/login" ||
    document.getElementById("login");

  if (isLoginPage) return;
  // Initialize all components
  initSections();
  await Promise.all([
    loadStatus(),
    loadDeviceData(),
    configCache.get(true),
  ]);
  initLogs();
  // Check for update last
  checkForUpdate();
  initUpdateButton();
  startLogsAutoRefresh();
  setInterval(checkForUpdate, CACHE_TTL);
  scheduleRefresh(isDesktopView() ? "desktop" : "status", { immediate: false });
  // Control buttons
  const controls = document.getElementById("controls");
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

  const hidePanelButton = document.querySelector("button.hide-panel");
  const statusDevice = document.querySelector(".status-device");
  const logsSection = document.getElementById("logs");

  if (hidePanelButton && statusDevice) {
    hidePanelButton.addEventListener("click", () => {
      statusDevice.classList.toggle("contracted");
      logsSection.classList.toggle("expanded");
      logsSection.parentElement.classList.toggle("expanded");
      // Update aria-expanded attribute for accessibility
      const isContracted = statusDevice.classList.contains("contracted");
      hidePanelButton.setAttribute("aria-expanded", isContracted);

      // Update tooltip text based on state
      hidePanelButton.parentElement.querySelector(".tooltip-text span").textContent = isContracted
        ? "Show Panel"
        : "Hide Panel";

      const svg = hidePanelButton.parentElement.querySelector("svg");
      if (svg) {
        svg.classList = isContracted ? "rotated" : "";
      }
    });

    // Add keyboard support
    hidePanelButton.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        hidePanelButton.click();
      }
    });
  }
});
